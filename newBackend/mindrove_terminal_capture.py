"""Standalone MindRove terminal recorder.

Run this file directly when you need a fully logged MindRove connection check
and a raw FP1/FP2/O1/O2 CSV capture outside the FastAPI backend.
"""

from __future__ import annotations

import argparse
from collections import deque
import csv
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np


CHANNEL_KEYS = ("fp1", "fp2", "o1", "o2")
BRIGHT_EEG_ROWS = (0, 1, 4, 5)
BRIGHT_ROW_LABELS = {
    0: "Fp1",
    1: "Fp2",
    4: "O1",
    5: "O2",
}
DEFAULT_IP_ADDRESS = "192.168.4.1"
DEFAULT_IP_PORT = 4210
DEFAULT_TIMEOUT = 10
DEFAULT_DURATION_SECONDS = 300.0


@dataclass(frozen=True)
class CaptureConfig:
    ip_address: str = DEFAULT_IP_ADDRESS
    ip_port: int = DEFAULT_IP_PORT
    timeout: int = DEFAULT_TIMEOUT
    serial_port: str | None = None
    eeg_rows: tuple[int, int, int, int] | None = None
    output: Path | None = None
    duration_seconds: float = DEFAULT_DURATION_SECONDS
    wait_timeout_seconds: float = 120.0
    poll_interval_seconds: float = 0.02
    log_interval_seconds: float = 1.0
    resistance_threshold: float = 5_000_000.0
    min_good_resistance_pairs: int = 2
    contact_mode: str = "auto"
    worn_min_active_eeg_rows: int = 4
    worn_min_eeg_std: float = 0.5
    worn_max_eeg_std: float = 50_000.0
    worn_max_abs_mean: float = 0.0
    disable_worn_gate: bool = False
    print_raw: bool = False
    raw_print_rows: int = 8
    raw_print_samples: int = 8
    plot: bool = False
    plot_backend: str = "TkAgg"
    plot_mode: str = "demean"
    plot_window_seconds: float = 10.0
    plot_update_interval_seconds: float = 0.08


@dataclass(frozen=True)
class ContactState:
    worn: bool
    quality: float
    reason: str
    resistance_ohms: list[float] = field(default_factory=list)
    eeg_row_std: list[float] = field(default_factory=list)
    eeg_row_abs_mean: list[float] = field(default_factory=list)


def build_mindrove_input_params(config: CaptureConfig, params_cls):
    params = params_cls()
    params.ip_address = config.ip_address
    params.ip_port = int(config.ip_port)
    params.timeout = int(config.timeout)
    if config.serial_port:
        params.serial_port = config.serial_port
    return params


def parse_eeg_rows(value: str | Sequence[int]) -> tuple[int, int, int, int] | None:
    if isinstance(value, str):
        if value.strip().lower() == "auto":
            return None
        rows = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    else:
        rows = tuple(int(part) for part in value)
    if len(rows) != 4:
        raise ValueError("MindRove terminal capture expects exactly four EEG rows.")
    return rows  # type: ignore[return-value]


def active_eeg_rows_from_frame(
    data: np.ndarray,
    candidate_rows: Sequence[int],
    config: CaptureConfig,
) -> tuple[list[int], dict[int, float]]:
    stds: dict[int, float] = {}
    active_rows = []
    for row in candidate_rows:
        row = int(row)
        if 0 <= row < data.shape[0]:
            std = float(np.std(data[row, :]))
        else:
            std = 0.0
        stds[row] = std
        if config.worn_min_eeg_std <= std <= config.worn_max_eeg_std:
            active_rows.append(row)
    return active_rows, stds


def contact_state_from_frame(
    data: np.ndarray,
    eeg_rows: Sequence[int],
    resistance_rows: Sequence[int],
    config: CaptureConfig,
) -> ContactState:
    if config.disable_worn_gate:
        return ContactState(True, 1.0, "disabled", [], _eeg_stds(data, eeg_rows), _eeg_abs_means(data, eeg_rows))

    resistances = []
    for row in resistance_rows:
        if 0 <= int(row) < data.shape[0]:
            values = data[int(row), :]
            finite = values[np.isfinite(values)]
            if finite.size:
                value = float(finite[-1])
                if value > 0:
                    resistances.append(value)

    resistance_available = bool(resistances)
    resistance_worn = False
    resistance_quality = 0.0
    if resistance_available:
        required = max(1, int(config.min_good_resistance_pairs))
        good_count = sum(value <= config.resistance_threshold for value in resistances)
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


def records_from_frame(
    data: np.ndarray,
    eeg_rows: Sequence[int],
    resistance_rows: Sequence[int],
    contact: ContactState,
    sample_rate: int,
    start_sample_index: int,
    batch_end_timestamp: float,
    battery: int | None = None,
) -> list[dict[str, object]]:
    arr = np.asarray(data, dtype=float)
    if arr.ndim != 2 or arr.shape[1] == 0:
        return []

    n_samples = arr.shape[1]
    sample_rate = max(1, int(sample_rate))
    batch_start_timestamp = float(batch_end_timestamp) - ((n_samples - 1) / sample_rate)
    records = []
    for col in range(n_samples):
        record: dict[str, object] = {
            "timestamp": f"{batch_start_timestamp + (col / sample_rate):.6f}",
            "sample_index": int(start_sample_index + col),
            "fp1": _format_row_value(arr, eeg_rows[0], col),
            "fp2": _format_row_value(arr, eeg_rows[1], col),
            "o1": _format_row_value(arr, eeg_rows[2], col),
            "o2": _format_row_value(arr, eeg_rows[3], col),
            "worn": "true" if contact.worn else "false",
            "contact_quality": f"{contact.quality:.6f}",
            "contact_reason": contact.reason,
            "battery": "" if battery is None else int(battery),
        }
        for row in resistance_rows:
            record[f"resistance_{int(row)}"] = _format_row_value(arr, int(row), col)
        for idx, row in enumerate(eeg_rows):
            value = contact.eeg_row_std[idx] if idx < len(contact.eeg_row_std) else math.nan
            record[f"eeg_std_{int(row)}"] = _format_float(value)
        for idx, row in enumerate(eeg_rows):
            value = contact.eeg_row_abs_mean[idx] if idx < len(contact.eeg_row_abs_mean) else math.nan
            record[f"eeg_abs_mean_{int(row)}"] = _format_float(value)
        records.append(record)
    return records


def csv_fieldnames(resistance_rows: Sequence[int], eeg_rows: Sequence[int]) -> list[str]:
    fields = [
        "timestamp",
        "sample_index",
        "fp1",
        "fp2",
        "o1",
        "o2",
        "worn",
        "contact_quality",
        "contact_reason",
        "battery",
    ]
    fields.extend(f"resistance_{int(row)}" for row in resistance_rows)
    fields.extend(f"eeg_std_{int(row)}" for row in eeg_rows)
    fields.extend(f"eeg_abs_mean_{int(row)}" for row in eeg_rows)
    return fields


def write_csv_records(path: Path, records: Sequence[dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames), extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(records)


def channel_frame_values(data: np.ndarray, eeg_rows: Sequence[int]) -> dict[str, list[float]]:
    arr = np.asarray(data, dtype=float)
    values: dict[str, list[float]] = {}
    selected = []
    for key, row in zip(CHANNEL_KEYS, eeg_rows):
        row = int(row)
        if 0 <= row < arr.shape[0]:
            row_values = [float(value) for value in arr[row, :] if np.isfinite(value)]
        else:
            row_values = []
        values[key] = row_values
        selected.append(row_values)

    min_len = min((len(row_values) for row_values in selected), default=0)
    if min_len:
        aggregate = [
            float(sum(row_values[idx] for row_values in selected) / len(selected))
            for idx in range(min_len)
        ]
    else:
        aggregate = []
    values["aggregate"] = aggregate
    return values


class RollingPlotBuffer:
    def __init__(self, max_samples: int) -> None:
        self.max_samples = max(1, int(max_samples))
        self._values = {
            key: deque(maxlen=self.max_samples)
            for key in (*CHANNEL_KEYS, "aggregate")
        }

    def append_frame(self, data: np.ndarray, eeg_rows: Sequence[int]) -> None:
        frame_values = channel_frame_values(data, eeg_rows)
        for key, values in frame_values.items():
            self._values[key].extend(values)

    def series(self) -> dict[str, list[float]]:
        return {key: list(values) for key, values in self._values.items()}


def prepare_plot_series(series: dict[str, list[float]], mode: str = "demean") -> dict[str, list[float]]:
    if mode == "raw":
        return {key: list(values) for key, values in series.items()}
    if mode != "demean":
        raise ValueError(f"Unsupported plot mode: {mode}")

    prepared: dict[str, list[float]] = {}
    for key, values in series.items():
        if not values:
            prepared[key] = []
            continue
        mean_value = float(sum(values) / len(values))
        prepared[key] = [float(value - mean_value) for value in values]
    return prepared


class LiveMindRovePlot:
    def __init__(
        self,
        sample_rate: int,
        window_seconds: float,
        update_interval_seconds: float,
        backend: str = "TkAgg",
        mode: str = "demean",
    ) -> None:
        try:
            import matplotlib

            if backend and backend.lower() != "auto":
                matplotlib.use(backend, force=True)
            import matplotlib.pyplot as plt
        except Exception as exc:  # pragma: no cover - depends on local GUI deps
            raise RuntimeError(
                "Live plot mode requires matplotlib with a working interactive backend. "
                "Try `--plot-backend TkAgg` or install Tk/Matplotlib with "
                "`python -m pip install matplotlib`."
            ) from exc

        self.plt = plt
        self.sample_rate = max(1, int(sample_rate))
        self.update_interval_seconds = max(0.01, float(update_interval_seconds))
        self.mode = mode
        self.buffer = RollingPlotBuffer(max_samples=round(max(1.0, float(window_seconds)) * self.sample_rate))
        self.eeg_rows: tuple[int, ...] | None = None
        self.last_draw = 0.0
        self.plt.ion()
        self.fig, axes = self.plt.subplots(5, 1, sharex=True, figsize=(12, 8))
        self.axes = list(axes)
        self.lines = {}
        colors = {
            "fp1": "#1f77b4",
            "fp2": "#ff7f0e",
            "o1": "#2ca02c",
            "o2": "#d62728",
            "aggregate": "#111111",
        }
        for ax, key in zip(self.axes, (*CHANNEL_KEYS, "aggregate")):
            (line,) = ax.plot([], [], color=colors[key], linewidth=1.0)
            self.lines[key] = line
            ax.set_ylabel(key.upper())
            ax.grid(True, alpha=0.25)
        self.axes[-1].set_xlabel("Seconds")
        self.fig.tight_layout()

    def update(self, data: np.ndarray, eeg_rows: Sequence[int], contact: ContactState) -> bool:
        rows = tuple(int(row) for row in eeg_rows)
        if self.eeg_rows != rows:
            self.eeg_rows = rows
            for ax, key, row in zip(self.axes, (*CHANNEL_KEYS, "aggregate"), (*rows, -1)):
                if key == "aggregate":
                    ax.set_ylabel("AGG")
                else:
                    ax.set_ylabel(f"{key.upper()}\nrow{row}")

        self.buffer.append_frame(data, rows)
        now = time.monotonic()
        if now - self.last_draw < self.update_interval_seconds:
            return self.plt.fignum_exists(self.fig.number)
        self.last_draw = now
        series = prepare_plot_series(self.buffer.series(), self.mode)
        n_samples = max((len(values) for values in series.values()), default=0)
        if n_samples <= 0:
            return self.plt.fignum_exists(self.fig.number)
        x_values = np.arange(-n_samples + 1, 1, dtype=float) / self.sample_rate
        for ax, key in zip(self.axes, (*CHANNEL_KEYS, "aggregate")):
            y_values = series[key]
            x = x_values[-len(y_values):] if y_values else []
            self.lines[key].set_data(x, y_values)
            ax.relim()
            ax.autoscale_view(scalex=False, scaley=True)
            ax.set_xlim(x_values[0], 0)
        self.fig.suptitle(
            f"MindRove live EEG | rows={list(rows)} | worn={contact.worn} | reason={contact.reason}",
            fontsize=11,
        )
        self.fig.canvas.draw_idle()
        self.plt.pause(0.001)
        return self.plt.fignum_exists(self.fig.number)


class MindRoveTerminalRecorder:
    def __init__(self, config: CaptureConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("mindrove_capture")
        self.board = None
        self.board_shim_cls = None
        self.config_mode_cls = None
        self.board_id = None
        self.sample_rate = 500
        self.sdk_eeg_rows: tuple[int, ...] = ()
        self.eeg_rows = tuple(config.eeg_rows or BRIGHT_EEG_ROWS)
        self._eeg_rows_locked = config.eeg_rows is not None
        self.resistance_rows: tuple[int, ...] = ()
        self.battery_channel: int | None = None
        self.device_name = "MindRove Bright"
        self.battery: int | None = None
        self.sample_index = 0
        self._last_auto_scan_log = 0.0

    def run(self) -> Path:
        output = self.config.output or default_output_path()
        self.logger.info("MindRove terminal capture starting.")
        if self.config.plot:
            self.logger.info("Mode: live plot. CSV recording is disabled.")
        else:
            self.logger.info("Output CSV: %s", output)
        self.logger.info(
            "Target endpoint ip=%s port=%s timeout=%ss serial=%s",
            self.config.ip_address,
            self.config.ip_port,
            self.config.timeout,
            self.config.serial_port or "",
        )
        try:
            self._open_board()
            self._capture(output)
            return output
        finally:
            self._release_board()

    def _open_board(self) -> None:
        self.logger.info("Importing MindRove SDK.")
        from mindrove.board_shim import BoardIds, BoardShim, MindRoveInputParams, MindroveConfigMode

        self.board_shim_cls = BoardShim
        self.config_mode_cls = MindroveConfigMode
        self.board_id = BoardIds.MINDROVE_WIFI_BOARD
        self.logger.info("Board id: %s", self.board_id)

        params = build_mindrove_input_params(self.config, MindRoveInputParams)
        self.board = BoardShim(self.board_id, params)
        self._resolve_board_metadata(BoardShim)

        self.logger.info("Preparing MindRove session.")
        self.board.prepare_session()
        self.logger.info("Starting MindRove stream.")
        self.board.start_stream()
        try:
            self.logger.info("Switching MindRove board to EEG mode.")
            self.board.config_board(MindroveConfigMode.EEG_MODE)
            time.sleep(0.25)
        except Exception as exc:
            self.logger.warning("Could not switch board to EEG mode: %s", exc)

        self.logger.info(
            "MindRove stream open device=%s sample_rate=%s eeg_rows=%s resistance_rows=%s battery_channel=%s",
            self.device_name,
            self.sample_rate,
            list(self.eeg_rows),
            list(self.resistance_rows),
            self.battery_channel,
        )

    def _resolve_board_metadata(self, board_shim_cls) -> None:
        descriptor = _optional_board_value(board_shim_cls.get_board_descr, self.board_id)
        if descriptor:
            self.logger.info("Board descriptor: %s", descriptor)

        sdk_eeg_rows = _coerce_int_list(_optional_board_value(board_shim_cls.get_eeg_channels, self.board_id))
        self.sdk_eeg_rows = tuple(sdk_eeg_rows)
        configured = [
            row for row in (self.config.eeg_rows or ())
            if not sdk_eeg_rows or row in sdk_eeg_rows
        ]
        if self.config.eeg_rows is not None and len(configured) == 4:
            self.eeg_rows = tuple(configured)
        elif len(sdk_eeg_rows) >= 4:
            self.eeg_rows = tuple(sdk_eeg_rows[:4])
        else:
            raise RuntimeError(f"MindRove did not expose four EEG rows. SDK rows: {sdk_eeg_rows}")

        self.sample_rate = int(_optional_board_value(board_shim_cls.get_sampling_rate, self.board_id) or 500)
        self.battery_channel = _optional_board_value(board_shim_cls.get_battery_channel, self.board_id)
        self.resistance_rows = tuple(
            _coerce_int_list(_optional_board_value(board_shim_cls.get_resistance_channels, self.board_id))
        )
        self.device_name = _optional_board_value(board_shim_cls.get_device_name, self.board_id) or "MindRove Bright"
        self.logger.info("SDK EEG rows: %s", sdk_eeg_rows)
        if self._eeg_rows_locked:
            self.logger.info("Selected EEG rows: %s", list(self.eeg_rows))
        else:
            self.logger.info(
                "Initial EEG rows: %s; auto mode will switch to first four active SDK EEG rows.",
                list(self.eeg_rows),
            )
        self.logger.info("Selected EEG labels: %s", [_row_label(row) for row in self.eeg_rows])

    def _capture(self, output: Path) -> None:
        assert self.board is not None
        fieldnames: list[str] | None = None
        recording_started = False
        record_start = 0.0
        wait_start = time.monotonic()
        last_log = 0.0
        rows_written = 0
        plotter: LiveMindRovePlot | None = None
        self.logger.info(
            "Waiting for flowing signal and worn headset. contact_mode=%s wait_timeout=%ss",
            self.config.contact_mode,
            self.config.wait_timeout_seconds,
        )

        while True:
            now = time.monotonic()
            if not self.config.plot and not recording_started and self.config.wait_timeout_seconds > 0:
                if now - wait_start > self.config.wait_timeout_seconds:
                    raise TimeoutError("Timed out waiting for MindRove signal with worn/contact status.")
            if self.config.plot and self.config.duration_seconds > 0 and now - wait_start >= self.config.duration_seconds:
                break
            if not self.config.plot and recording_started and now - record_start >= self.config.duration_seconds:
                break

            count = int(self.board.get_board_data_count())
            if count <= 0:
                if now - last_log >= self.config.log_interval_seconds:
                    self.logger.info("No board samples available yet.")
                    last_log = now
                time.sleep(self.config.poll_interval_seconds)
                continue

            data = np.asarray(self.board.get_board_data(count), dtype=float)
            if data.ndim != 2 or data.shape[1] == 0:
                self.logger.warning("Ignoring malformed board data with shape=%s", getattr(data, "shape", None))
                time.sleep(self.config.poll_interval_seconds)
                continue

            self._maybe_update_auto_eeg_rows(data)
            contact = contact_state_from_frame(data, self.eeg_rows, self.resistance_rows, self.config)
            self._update_battery(data)

            if self.config.print_raw and now - last_log >= self.config.log_interval_seconds:
                self._print_raw_preview(data)

            if now - last_log >= self.config.log_interval_seconds:
                self._log_status(data, contact, rows_written)
                last_log = now

            if self.config.plot:
                if plotter is None:
                    plotter = LiveMindRovePlot(
                        sample_rate=self.sample_rate,
                        window_seconds=self.config.plot_window_seconds,
                        update_interval_seconds=self.config.plot_update_interval_seconds,
                        backend=self.config.plot_backend,
                        mode=self.config.plot_mode,
                    )
                    self.logger.info(
                        "Live plot opened. Showing rows %s plus aggregate mean. Close the plot or press Ctrl+C to stop.",
                        list(self.eeg_rows),
                    )
                if not plotter.update(data, self.eeg_rows, contact):
                    self.logger.info("Live plot window closed.")
                    break
                time.sleep(self.config.poll_interval_seconds)
                continue

            if not recording_started:
                if not contact.worn:
                    time.sleep(self.config.poll_interval_seconds)
                    continue
                recording_started = True
                record_start = now
                self.logger.info(
                    "Headset classified as worn. Recording %.1f seconds to %s.",
                    self.config.duration_seconds,
                    output,
                )

            records = records_from_frame(
                data,
                eeg_rows=self.eeg_rows,
                resistance_rows=self.resistance_rows,
                contact=contact,
                sample_rate=self.sample_rate,
                start_sample_index=self.sample_index,
                batch_end_timestamp=time.time(),
                battery=self.battery,
            )
            if fieldnames is None:
                fieldnames = csv_fieldnames(self.resistance_rows, self.eeg_rows)
            write_csv_records(output, records, fieldnames)
            rows_written += len(records)
            self.sample_index += len(records)
            time.sleep(self.config.poll_interval_seconds)

        self.logger.info("Capture complete. rows_written=%s output=%s", rows_written, output)

    def _maybe_update_auto_eeg_rows(self, data: np.ndarray) -> None:
        if self._eeg_rows_locked:
            return
        now = time.monotonic()
        candidate_rows = self.sdk_eeg_rows or tuple(range(min(8, data.shape[0])))
        active_rows, row_stds = active_eeg_rows_from_frame(data, candidate_rows, self.config)
        std_text = ", ".join(f"row{row}={std:.2f}" for row, std in row_stds.items())
        if len(active_rows) >= 4:
            selected = tuple(active_rows[:4])
            if selected != self.eeg_rows:
                self.eeg_rows = selected
                self._last_auto_scan_log = now
                self.logger.info(
                    "Auto-selected active EEG rows %s as fp1/fp2/o1/o2. SDK EEG stds: %s",
                    list(self.eeg_rows),
                    std_text,
                )
        elif now - self._last_auto_scan_log >= self.config.log_interval_seconds:
            self._last_auto_scan_log = now
            self.logger.info(
                "Auto EEG row scan has %s/4 active rows. Active=%s SDK EEG stds: %s",
                len(active_rows),
                active_rows,
                std_text,
            )

    def _update_battery(self, data: np.ndarray) -> None:
        if self.battery_channel is None:
            return
        row = int(self.battery_channel)
        if 0 <= row < data.shape[0]:
            finite = data[row, :][np.isfinite(data[row, :])]
            if finite.size:
                self.battery = int(round(float(finite[-1])))

    def _log_status(self, data: np.ndarray, contact: ContactState, rows_written: int) -> None:
        eeg_std = ",".join(f"{value:.2f}" for value in contact.eeg_row_std) or "n/a"
        resistance = ",".join(f"{value:.0f}" for value in contact.resistance_ohms) or "n/a"
        self.logger.info(
            "status samples=%s shape=%sx%s worn=%s quality=%.2f reason=%s "
            "resistance_ohms=[%s] eeg_std=[%s] eeg_abs_mean=[%s] battery=%s rows_written=%s",
            int(data.shape[1]),
            int(data.shape[0]),
            int(data.shape[1]),
            contact.worn,
            contact.quality,
            contact.reason,
            resistance,
            eeg_std,
            ",".join(f"{value:.0f}" for value in contact.eeg_row_abs_mean) or "n/a",
            self.battery if self.battery is not None else "n/a",
            rows_written,
        )

    def _print_raw_preview(self, data: np.ndarray) -> None:
        preview_rows = self.sdk_eeg_rows or self.eeg_rows
        row_limit = max(1, min(int(self.config.raw_print_rows), len(preview_rows)))
        sample_limit = max(1, int(self.config.raw_print_samples))
        parts = []
        for row in preview_rows[:row_limit]:
            if 0 <= int(row) < data.shape[0]:
                samples = data[int(row), -sample_limit:]
                text = ",".join(f"{value:.1f}" for value in samples)
                parts.append(f"row{int(row)}=[{text}]")
        if parts:
            self.logger.info("raw_sdk shape=%sx%s %s", data.shape[0], data.shape[1], " ".join(parts))

    def _release_board(self) -> None:
        if self.board is None:
            return
        self.logger.info("Stopping MindRove stream.")
        try:
            self.board.stop_stream()
        except Exception as exc:
            self.logger.warning("stop_stream failed: %s", exc)
        self.logger.info("Releasing MindRove session.")
        try:
            self.board.release_session()
        except Exception as exc:
            self.logger.warning("release_session failed: %s", exc)
        self.board = None


def default_output_path() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path.cwd() / f"mindrove_capture_{stamp}.csv"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Connect to MindRove and capture raw FP1/FP2/O1/O2 CSV data.")
    parser.add_argument("--mindrove-ip", default=os.getenv("MINDROVE_IP_ADDRESS", DEFAULT_IP_ADDRESS))
    parser.add_argument("--mindrove-port", type=int, default=int(os.getenv("MINDROVE_IP_PORT", DEFAULT_IP_PORT)))
    parser.add_argument("--mindrove-timeout", type=int, default=int(os.getenv("MINDROVE_TIMEOUT", DEFAULT_TIMEOUT)))
    parser.add_argument("--mindrove-serial-port", default=os.getenv("MINDROVE_SERIAL_PORT") or None)
    parser.add_argument("--eeg-rows", default=os.getenv("MINDROVE_EEG_ROWS", "auto"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration-seconds", type=float, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--wait-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.02)
    parser.add_argument("--log-interval-seconds", type=float, default=1.0)
    parser.add_argument("--resistance-threshold", type=float, default=5_000_000.0)
    parser.add_argument("--min-good-resistance-pairs", type=int, default=2)
    parser.add_argument("--contact-mode", choices=("auto", "resistance", "eeg"), default="auto")
    parser.add_argument("--worn-min-active-eeg-rows", type=int, default=4)
    parser.add_argument("--worn-min-eeg-std", type=float, default=0.5)
    parser.add_argument("--worn-max-eeg-std", type=float, default=50_000.0)
    parser.add_argument("--worn-max-abs-mean", type=float, default=0.0)
    parser.add_argument("--disable-worn-gate", action="store_true")
    parser.add_argument("--print-raw", action="store_true")
    parser.add_argument("--raw-print-rows", type=int, default=8)
    parser.add_argument("--raw-print-samples", type=int, default=8)
    parser.add_argument("--plot", action="store_true", help="Show live channel and aggregate plots instead of writing CSV.")
    parser.add_argument("--plot-backend", default="TkAgg", help="Matplotlib backend for --plot. Default avoids Qt.")
    parser.add_argument("--plot-mode", choices=("demean", "raw"), default="demean")
    parser.add_argument("--plot-window-seconds", type=float, default=10.0)
    parser.add_argument("--plot-update-interval-seconds", type=float, default=0.08)
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> CaptureConfig:
    return CaptureConfig(
        ip_address=args.mindrove_ip,
        ip_port=args.mindrove_port,
        timeout=args.mindrove_timeout,
        serial_port=args.mindrove_serial_port,
        eeg_rows=parse_eeg_rows(args.eeg_rows),
        output=args.output,
        duration_seconds=args.duration_seconds,
        wait_timeout_seconds=args.wait_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        log_interval_seconds=args.log_interval_seconds,
        resistance_threshold=args.resistance_threshold,
        min_good_resistance_pairs=args.min_good_resistance_pairs,
        contact_mode=args.contact_mode,
        worn_min_active_eeg_rows=args.worn_min_active_eeg_rows,
        worn_min_eeg_std=args.worn_min_eeg_std,
        worn_max_eeg_std=args.worn_max_eeg_std,
        worn_max_abs_mean=args.worn_max_abs_mean,
        disable_worn_gate=args.disable_worn_gate,
        print_raw=args.print_raw,
        raw_print_rows=args.raw_print_rows,
        raw_print_samples=args.raw_print_samples,
        plot=args.plot,
        plot_backend=args.plot_backend,
        plot_mode=args.plot_mode,
        plot_window_seconds=args.plot_window_seconds,
        plot_update_interval_seconds=args.plot_update_interval_seconds,
    )


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [MindRoveCapture] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("mindrove_capture")
    try:
        config = config_from_args(parse_args(argv))
        MindRoveTerminalRecorder(config, logger=logger).run()
        return 0
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception as exc:
        logger.exception("MindRove terminal capture failed: %s", exc)
        return 1


def _eeg_stds(data: np.ndarray, eeg_rows: Sequence[int]) -> list[float]:
    values = []
    for row in eeg_rows:
        row = int(row)
        if 0 <= row < data.shape[0]:
            values.append(float(np.std(data[row, :])))
    return values


def _eeg_abs_means(data: np.ndarray, eeg_rows: Sequence[int]) -> list[float]:
    values = []
    for row in eeg_rows:
        row = int(row)
        if 0 <= row < data.shape[0]:
            values.append(float(abs(np.mean(data[row, :]))))
    return values


def _format_row_value(data: np.ndarray, row: int, col: int) -> str:
    row = int(row)
    if 0 <= row < data.shape[0]:
        return _format_float(float(data[row, col]))
    return ""


def _format_float(value: float) -> str:
    if not math.isfinite(float(value)):
        return ""
    return f"{float(value):.6f}"


def _row_label(row: int) -> str:
    return BRIGHT_ROW_LABELS.get(int(row), f"row{int(row)}")


def _optional_board_value(func, board_id):
    try:
        return func(board_id)
    except Exception:
        return None


def _coerce_int_list(value: Any) -> list[int]:
    if value is None or isinstance(value, (str, bytes)):
        return []
    try:
        return [int(item) for item in value]
    except Exception:
        return []


if __name__ == "__main__":
    sys.exit(main())
