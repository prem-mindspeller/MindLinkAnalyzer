import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from .config import FocusCubeConfig
from .features import (
    ChannelBandFeatureExtractor,
    FocusIndexEstimator,
    AdaptiveNormalizer,
    not_worn_frame,
)


DEFAULT_BRIGHT_EEG_ROWS = (0, 1, 4, 5)
BRIGHT_POSITION_LABELS = ("Fp1", "Fp2", "O1", "O2")
BRIGHT_EEG_LABELS = {
    0: "Fp1",
    1: "Fp2",
    4: "O1",
    5: "O2",
}


@dataclass(frozen=True)
class ContactState:
    worn: bool
    quality: float
    reason: str
    resistance_ohms: list[float] = field(default_factory=list)
    eeg_row_std: list[float] = field(default_factory=list)
    eeg_row_abs_mean: list[float] = field(default_factory=list)


def build_mindrove_input_params(config: FocusCubeConfig, params_cls):
    params = params_cls()
    params.ip_address = config.mindrove_ip_address
    params.ip_port = int(config.mindrove_ip_port)
    params.timeout = int(config.mindrove_timeout)
    if config.mindrove_serial_port:
        params.serial_port = config.mindrove_serial_port
    return params


class MindRoveRawSource:
    def __init__(
        self,
        config: FocusCubeConfig,
        board: Any | None = None,
        eeg_channels: list[int] | None = None,
        battery_channel: int | None = None,
        resistance_channels: list[int] | None = None,
        sample_rate: int | None = None,
        device_name: str | None = None,
        sdk_eeg_channels: list[int] | None = None,
    ) -> None:
        self.config = config
        self.board = board
        self._eeg_rows_locked = eeg_channels is not None or config.mindrove_eeg_rows is not None
        self.eeg_channels = list(eeg_channels or config.mindrove_eeg_rows or DEFAULT_BRIGHT_EEG_ROWS)
        self.sdk_eeg_channels = list(sdk_eeg_channels or [])
        self.battery_channel = battery_channel
        self.resistance_channels = list(resistance_channels or [])
        self.sample_rate = int(sample_rate or config.sample_rate)
        self.device_name = device_name or "MindRove Bright"
        self.raw_samples: deque[float] = deque(maxlen=self.sample_rate * 8)
        self.channel_samples: dict[int, deque[float]] = {
            row: deque(maxlen=self.sample_rate * 12)
            for row in self.eeg_channels
        }
        self.feature_extractor = self._create_feature_extractor()
        self.focus_estimator = FocusIndexEstimator(config)
        self.visual_normalizer = AdaptiveNormalizer(config.normalizer_window)
        self.battery: int | None = None
        self.worn = bool(config.disable_worn_gate)
        self.contact_quality = 1.0 if config.disable_worn_gate else 0.0
        self.latest_resistance_ohms: list[float] = []
        self.latest_eeg_row_std: list[float] = []
        self.latest_eeg_row_abs_mean: list[float] = []
        self.contact_reason = "disabled" if config.disable_worn_gate else "unknown"
        self._contact_worn_streak = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._open_event = threading.Event()
        self._open_error: Exception | None = None
        self._last_raw_print = 0.0
        self._last_focus_sample_count = 0
        self._accepted_sample_count = 0
        self._last_payload: dict | None = None

    def start(self) -> None:
        if self.board is None:
            self._create_board()

        self._thread = threading.Thread(target=self._run, name="mindrove-raw-source", daemon=True)
        self._thread.start()
        if not self._open_event.wait(timeout=self.config.mindrove_timeout + 5):
            raise RuntimeError("Timed out opening MindRove Bright stream")
        if self._open_error:
            raise RuntimeError(f"Could not start MindRove Bright stream: {self._open_error}") from self._open_error

    def stop(self) -> None:
        self._stop.set()
        if self.board is not None:
            try:
                self.board.stop_stream()
            except Exception:
                pass
            try:
                self.board.release_session()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)

    def drain_board_data(self) -> None:
        if self.board is None:
            return
        count = int(self.board.get_board_data_count())
        if count <= 0:
            return

        data = np.asarray(self.board.get_board_data(count), dtype=float)
        if data.ndim != 2 or data.shape[1] == 0:
            return

        self._maybe_update_auto_eeg_rows(data)
        valid_channels = [idx for idx in self.eeg_channels if 0 <= idx < data.shape[0]]
        if not valid_channels:
            return

        eeg = data[valid_channels, :]
        self._print_raw_eeg_preview(eeg, valid_channels, data.shape)
        self._update_contact_status(data)
        active = eeg[~np.all(np.isclose(eeg, 0.0), axis=1)]
        if active.size == 0 or not self.worn:
            self.raw_samples.clear()
            for values in self.channel_samples.values():
                values.clear()
            self.focus_estimator.reset()
            self._last_focus_sample_count = 0
            self._accepted_sample_count = 0
            self._last_payload = None
            return

        mono = np.mean(active, axis=0)
        self.raw_samples.extend(float(value) for value in mono if np.isfinite(value))
        accepted_in_batch = 0
        for channel, channel_values in zip(valid_channels, eeg, strict=False):
            target = self.channel_samples.setdefault(channel, deque(maxlen=self.sample_rate * 12))
            finite_values = [float(value) for value in channel_values if np.isfinite(value)]
            accepted_in_batch = max(accepted_in_batch, len(finite_values))
            target.extend(finite_values)
        self._accepted_sample_count += accepted_in_batch

        if self.battery_channel is not None and 0 <= self.battery_channel < data.shape[0]:
            battery_values = data[self.battery_channel, :]
            finite = battery_values[np.isfinite(battery_values)]
            if finite.size:
                self.battery = int(round(float(finite[-1])))

    def payload(self) -> dict | None:
        if not self.worn:
            return not_worn_frame(self.config, self.sample_count, self.device_status)
        min_count = self._min_channel_sample_count()
        if min_count < self.config.window_size:
            return None
        if (
            self._last_payload is not None
            and self._accepted_sample_count - self._last_focus_sample_count < self.config.focus_update_stride_samples
        ):
            return self._last_payload

        features = self.feature_extractor.compute(
            {
                row: list(samples)
                for row, samples in self.channel_samples.items()
                if len(samples) >= self.config.window_size
            }
        )
        focus = self.focus_estimator.update(features)
        self._last_focus_sample_count = self._accepted_sample_count
        self._last_payload = build_focus_payload(
            features,
            focus,
            self.config,
            self.device_status,
            self.visual_normalizer,
        )
        return self._last_payload

    def reset_calibration(self) -> None:
        self.focus_estimator.reset()
        self._last_payload = None
        self._last_focus_sample_count = 0

    @property
    def sample_count(self) -> int:
        return len(self.raw_samples)

    @property
    def device_status(self) -> dict:
        return {
            "connected": True,
            "source": "mindrove",
            "deviceName": self.device_name,
            "ipAddress": self.config.mindrove_ip_address,
            "ipPort": self.config.mindrove_ip_port,
            "serialPort": self.config.mindrove_serial_port,
            "battery": self.battery,
            "sampleRate": self.sample_rate,
            "eegChannels": list(self.eeg_channels),
            "eegLabels": [_position_label(index, row) for index, row in enumerate(self.eeg_channels)],
            "resistanceChannels": list(self.resistance_channels),
            "resistanceOhms": list(self.latest_resistance_ohms),
            "eegRowStd": list(self.latest_eeg_row_std),
            "eegRowAbsMean": list(self.latest_eeg_row_abs_mean),
            "worn": self.worn,
            "contactQuality": self.contact_quality,
            "contactReason": self.contact_reason,
            "contactStableFrames": self._contact_worn_streak,
            "contactRequiredStableFrames": self._required_worn_frames(),
            "sampleCount": self.sample_count,
            "channelSampleCount": self._min_channel_sample_count(),
        }

    def _create_board(self) -> None:
        from mindrove.board_shim import BoardIds, BoardShim, MindRoveInputParams

        board_id = BoardIds.MINDROVE_WIFI_BOARD
        params = build_mindrove_input_params(self.config, MindRoveInputParams)
        self.board = BoardShim(board_id, params)
        self.sdk_eeg_channels = list(BoardShim.get_eeg_channels(board_id))
        if self.config.mindrove_eeg_rows is not None:
            configured_rows = [
                row
                for row in self.config.mindrove_eeg_rows
                if not self.sdk_eeg_channels or row in self.sdk_eeg_channels
            ]
            self.eeg_channels = configured_rows or list(self.config.mindrove_eeg_rows)
        elif len(self.sdk_eeg_channels) >= 4:
            self.eeg_channels = self.sdk_eeg_channels[:4]
        else:
            self.eeg_channels = list(DEFAULT_BRIGHT_EEG_ROWS)
        self.sample_rate = int(BoardShim.get_sampling_rate(board_id))
        self.battery_channel = _optional_board_value(BoardShim.get_battery_channel, board_id)
        self.resistance_channels = list(_optional_board_value(BoardShim.get_resistance_channels, board_id) or [])
        self.device_name = _optional_board_value(BoardShim.get_device_name, board_id) or "MindRove Bright"
        self._reset_sample_buffers(reset_estimator=False)

    def _run(self) -> None:
        try:
            self.board.prepare_session()
            self.board.start_stream()
            self._configure_eeg_mode()
            self._open_event.set()
            while not self._stop.is_set():
                self.drain_board_data()
                time.sleep(0.02)
        except Exception as exc:
            self._open_error = exc
            self._open_event.set()

    def _configure_eeg_mode(self) -> None:
        try:
            from mindrove.board_shim import MindroveConfigMode

            self.board.config_board(MindroveConfigMode.EEG_MODE)
        except Exception:
            pass

    def _update_contact_status(self, data: np.ndarray) -> None:
        contact = contact_state_from_frame(
            data,
            self.eeg_channels,
            self.resistance_channels,
            self.config,
        )
        self.latest_resistance_ohms = contact.resistance_ohms
        self.latest_eeg_row_std = contact.eeg_row_std
        self.latest_eeg_row_abs_mean = contact.eeg_row_abs_mean

        if contact.worn:
            self._contact_worn_streak += 1
        else:
            self._contact_worn_streak = 0

        required = self._required_worn_frames()
        stable = contact.worn and self._contact_worn_streak >= required
        self.worn = bool(stable)
        self.contact_quality = contact.quality * min(1.0, self._contact_worn_streak / required)
        self.contact_reason = (
            contact.reason
            if stable or not contact.worn
            else f"{contact.reason}_stabilizing"
        )

    def _maybe_update_auto_eeg_rows(self, data: np.ndarray) -> None:
        if self._eeg_rows_locked:
            return
        candidate_rows = self.sdk_eeg_channels or list(range(min(8, data.shape[0])))
        active_rows = []
        for row in candidate_rows:
            if 0 <= int(row) < data.shape[0]:
                std = float(np.std(data[int(row), :]))
            else:
                std = 0.0
            if self.config.worn_min_eeg_std <= std <= self.config.worn_max_eeg_std:
                active_rows.append(int(row))
        if len(active_rows) < 4:
            return
        selected = active_rows[:4]
        if selected == self.eeg_channels:
            return
        self.eeg_channels = selected
        self._reset_sample_buffers(reset_estimator=True)

    def _min_channel_sample_count(self) -> int:
        counts = [
            len(self.channel_samples.get(row, []))
            for row in self.eeg_channels
        ]
        return min(counts) if counts else 0

    def _print_raw_eeg_preview(
        self,
        eeg: np.ndarray,
        valid_channels: list[int],
        data_shape: tuple[int, int],
    ) -> None:
        if not self.config.print_raw:
            return

        now = time.monotonic()
        if now - self._last_raw_print < self.config.raw_print_interval:
            return
        self._last_raw_print = now

        row_limit = max(1, min(int(self.config.raw_print_rows), len(valid_channels)))
        sample_limit = max(1, int(self.config.raw_print_samples))
        parts = []
        for row_index, channel in enumerate(valid_channels[:row_limit]):
            samples = eeg[row_index, -sample_limit:]
            sample_text = ",".join(f"{value:.1f}" for value in samples)
            zero_flag = " inactive_zero" if np.all(np.isclose(eeg[row_index], 0.0)) else ""
            parts.append(f"row{channel}{zero_flag}=[{sample_text}]")

        print(
            "[FocusCube] raw_sdk "
            f"shape={data_shape[0]}x{data_shape[1]} "
            f"eeg_rows={valid_channels} "
            + " ".join(parts),
            flush=True,
        )

    def _create_feature_extractor(self) -> ChannelBandFeatureExtractor:
        frontal_rows = tuple(self.eeg_channels[:2]) or (0, 1)
        occipital_rows = tuple(self.eeg_channels[2:4]) or tuple(self.eeg_channels[-2:]) or (4, 5)
        return ChannelBandFeatureExtractor(
            self.config,
            frontal_rows=frontal_rows,
            occipital_rows=occipital_rows,
        )

    def _reset_sample_buffers(self, reset_estimator: bool) -> None:
        self.raw_samples = deque(maxlen=self.sample_rate * 8)
        self.channel_samples = {
            row: deque(maxlen=self.sample_rate * 12)
            for row in self.eeg_channels
        }
        self.feature_extractor = self._create_feature_extractor()
        self.visual_normalizer = AdaptiveNormalizer(self.config.normalizer_window)
        self._last_payload = None
        self._last_focus_sample_count = 0
        self._accepted_sample_count = 0
        if reset_estimator:
            self.focus_estimator.reset()

    def _required_worn_frames(self) -> int:
        if self.config.disable_worn_gate:
            return 1
        return max(1, int(self.config.worn_required_consecutive_frames))


def _optional_board_value(func, board_id):
    try:
        return func(board_id)
    except Exception:
        return None


def _position_label(index: int, row: int) -> str:
    if index < len(BRIGHT_POSITION_LABELS):
        return BRIGHT_POSITION_LABELS[index]
    return BRIGHT_EEG_LABELS.get(row, f"row{row}")


def contact_state_from_frame(
    data: np.ndarray,
    eeg_rows: Sequence[int],
    resistance_rows: Sequence[int],
    config: FocusCubeConfig,
) -> ContactState:
    if config.disable_worn_gate:
        return ContactState(
            True,
            1.0,
            "disabled",
            [],
            _eeg_stds(data, eeg_rows),
            _eeg_abs_means(data, eeg_rows),
        )

    resistances = []
    for row in resistance_rows:
        row = int(row)
        if 0 <= row < data.shape[0]:
            values = data[row, :]
            finite = values[np.isfinite(values)]
            if finite.size:
                value = float(finite[-1])
                if value > 0:
                    resistances.append(value)

    resistance_available = bool(resistances)
    resistance_worn = False
    resistance_quality = 0.0
    if resistance_available:
        required = max(1, int(config.worn_min_good_resistance_pairs))
        good_count = sum(value <= config.worn_resistance_threshold for value in resistances)
        resistance_worn = good_count >= required
        resistance_quality = min(1.0, good_count / required)

    eeg_stds = _eeg_stds(data, eeg_rows)
    eeg_abs_means = _eeg_abs_means(data, eeg_rows)
    eeg_required = max(1, min(len(eeg_rows), int(config.worn_min_active_eeg_rows)))
    active_rows = sum(
        config.worn_min_eeg_std <= std <= config.worn_max_eeg_std
        for std in eeg_stds
    )
    use_abs_mean_guard = config.worn_max_abs_mean > 0
    stable_rows = (
        sum(value <= config.worn_max_abs_mean for value in eeg_abs_means)
        if use_abs_mean_guard
        else eeg_required
    )
    eeg_worn = active_rows >= eeg_required and stable_rows >= eeg_required
    eeg_quality = min(1.0, min(active_rows, stable_rows) / eeg_required)
    eeg_reason = "eeg_variance"
    if active_rows < eeg_required:
        eeg_reason = "low_variance"
    elif use_abs_mean_guard and stable_rows < eeg_required:
        eeg_reason = "dc_offset"

    if config.contact_mode == "resistance":
        return ContactState(resistance_worn, resistance_quality, "resistance", resistances, eeg_stds, eeg_abs_means)
    if config.contact_mode == "eeg":
        return ContactState(eeg_worn, eeg_quality, eeg_reason, resistances, eeg_stds, eeg_abs_means)
    if config.contact_mode != "auto":
        raise ValueError(f"Unsupported contact mode: {config.contact_mode}")

    if resistance_available and resistance_worn:
        return ContactState(True, resistance_quality, "resistance", resistances, eeg_stds, eeg_abs_means)
    if eeg_worn:
        return ContactState(True, eeg_quality, "eeg_variance_fallback", resistances, eeg_stds, eeg_abs_means)
    reason = eeg_reason if not resistance_available else "no_contact"
    return ContactState(False, max(resistance_quality, eeg_quality), reason, resistances, eeg_stds, eeg_abs_means)


def _eeg_stds(data: np.ndarray, eeg_rows: Sequence[int]) -> list[float]:
    return [
        float(np.std(data[int(row), :]))
        for row in eeg_rows
        if 0 <= int(row) < data.shape[0]
    ]


def _eeg_abs_means(data: np.ndarray, eeg_rows: Sequence[int]) -> list[float]:
    return [
        float(abs(np.mean(data[int(row), :])))
        for row in eeg_rows
        if 0 <= int(row) < data.shape[0]
    ]


def build_focus_payload(features, focus, config: FocusCubeConfig, device_status: dict, visual_normalizer=None) -> dict:
    frontal = features.regions.get("frontal")
    occipital = features.regions.get("occipital")
    all_region = features.regions.get("all") or frontal or occipital
    bands_source = all_region or next(iter(features.channel_features.values()))
    visual_normalizer = visual_normalizer or AdaptiveNormalizer(config.normalizer_window)
    normalized = {
        "alpha": visual_normalizer.normalize("alpha", _relative(occipital, "alpha")),
        "beta": visual_normalizer.normalize("beta", _relative(frontal, "beta")),
        "gamma": visual_normalizer.normalize("gamma", _relative(all_region, "gamma")),
        "focusIndex": focus.smoothed_attention,
        "frontalEngagement": focus.components.get("frontalEngagement", 0.0),
        "occipitalAlphaSuppression": focus.components.get("occipitalAlphaSuppression", 0.0),
        "occipitalAlphaActivation": focus.components.get("occipitalAlphaActivation", 0.0),
    }
    normalized["betaGamma"] = min(1.0, (normalized["beta"] + normalized["gamma"]) * 0.5)
    status = dict(device_status)
    status["baselineProgress"] = focus.baseline_progress
    status["baselineCount"] = focus.baseline_count
    status["baselineRequired"] = focus.baseline_required
    return {
        "timestamp": time.time(),
        "mode": focus.mode,
        "device": status,
        "quality": min(status.get("contactQuality", 1.0), focus.components.get("artifactPenalty", 1.0)),
        "attention": focus.smoothed_attention,
        "focus": {
            "raw": focus.attention,
            "smoothed": focus.smoothed_attention,
            "components": dict(focus.components),
            "metrics": dict(features.metrics),
            "baselineProgress": focus.baseline_progress,
            "baselineCount": focus.baseline_count,
            "baselineRequired": focus.baseline_required,
        },
        "bands": {
            "alpha": bands_source.bands["alpha"],
            "beta": bands_source.bands["beta"],
            "gamma": bands_source.bands["gamma"],
        },
        "relative": {
            "alpha": bands_source.relative["alpha"],
            "beta": bands_source.relative["beta"],
            "gamma": bands_source.relative["gamma"],
        },
        "regions": {
            name: {
                "bands": {
                    "theta": feature.bands["theta"],
                    "alpha": feature.bands["alpha"],
                    "beta": feature.bands["beta"],
                    "gamma": feature.bands["gamma"],
                },
                "relative": {
                    "theta": feature.relative["theta"],
                    "alpha": feature.relative["alpha"],
                    "beta": feature.relative["beta"],
                    "gamma": feature.relative["gamma"],
                },
                "metrics": dict(feature.metrics or {}),
            }
            for name, feature in features.regions.items()
        },
        "normalized": normalized,
    }


def _relative(feature, band: str) -> float:
    if feature is None:
        return 0.0
    return float(feature.relative.get(band, 0.0))
