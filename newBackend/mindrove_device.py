"""MindRove Wi-Fi EEG acquisition adapter.

This module is intentionally small: it wraps the official MindRove ``BoardShim``
API and exposes FP1, FP2, O1, and O2 samples in a shape the active FastAPI
backend can broadcast and analyze.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover - exercised only on minimal installs
    np = None

try:
    from mindrove.board_shim import (
        BoardIds,
        BoardShim,
        MindRoveInputParams,
        MindroveConfigMode,
    )

    MINDROVE_SDK_AVAILABLE = True
except Exception:  # pragma: no cover - normal in CI without MindRove SDK
    BoardIds = None
    BoardShim = None
    MindRoveInputParams = None
    MindroveConfigMode = None
    MINDROVE_SDK_AVAILABLE = False


MINDROVE_CHANNEL_ORDER: Tuple[str, ...] = ("fp1", "fp2", "o1", "o2")
MINDROVE_CHANNEL_LABELS: Dict[str, str] = {
    "fp1": "FP1",
    "fp2": "FP2",
    "o1": "O1",
    "o2": "O2",
}
MINDROVE_CHANNEL_ROWS: Dict[str, int] = {
    "fp1": 0,
    "fp2": 1,
    "o1": 2,
    "o2": 3,
}
MINDROVE_DEFAULT_IP_ADDRESS = "192.168.4.1"
MINDROVE_DEFAULT_IP_PORT = 4210
MINDROVE_DEFAULT_TIMEOUT = 10
MINDROVE_DEFAULT_MIN_ACTIVE_STD = 0.5
MINDROVE_DEFAULT_MAX_ACTIVE_STD = 50000.0


@dataclass
class MindRoveChannel:
    key: str
    label: str
    row_index: int


def _normalize_label(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "").replace("_", "")


class MindRoveDevice:
    """Thin wrapper around the MindRove Wi-Fi BoardShim stream."""

    def __init__(self, target_channels: Sequence[str] = MINDROVE_CHANNEL_ORDER):
        if not MINDROVE_SDK_AVAILABLE:
            raise RuntimeError(
                "MindRove SDK is not available. Install it with "
                "`python -m pip install mindrove` in the backend environment."
            )

        self.target_channels = tuple(target_channels)
        self.board_id = BoardIds.MINDROVE_WIFI_BOARD
        self.board_shim = None
        self.sample_rate = 500
        self.channels: List[MindRoveChannel] = []
        self.sdk_eeg_rows: Tuple[int, ...] = ()
        self.battery_channel: Optional[int] = None
        self.battery_level: Optional[int] = None
        self._configured_eeg_rows = self._parse_eeg_rows_env(os.getenv("MINDROVE_EEG_ROWS", ""))
        self._rows_locked = self._configured_eeg_rows is not None
        self._auto_detect_rows = not self._rows_locked
        self._min_active_std = self._env_float("MINDROVE_WORN_MIN_EEG_STD", MINDROVE_DEFAULT_MIN_ACTIVE_STD)
        self._max_active_std = self._env_float("MINDROVE_WORN_MAX_EEG_STD", MINDROVE_DEFAULT_MAX_ACTIVE_STD)
        self._connected = False

    def connect(self) -> None:
        self.disconnect()

        params = MindRoveInputParams()

        params.ip_address = os.getenv("MINDROVE_IP_ADDRESS", "").strip() or MINDROVE_DEFAULT_IP_ADDRESS
        params.ip_port = self._env_int("MINDROVE_IP_PORT", MINDROVE_DEFAULT_IP_PORT)
        params.timeout = self._env_int("MINDROVE_TIMEOUT", MINDROVE_DEFAULT_TIMEOUT)

        serial_port = os.getenv("MINDROVE_SERIAL_PORT", "").strip()
        if serial_port:
            params.serial_port = serial_port

        try:
            self.board_shim = BoardShim(self.board_id, params)

            descriptor = self._get_board_descriptor()
            self.sample_rate = self._resolve_sample_rate(descriptor)
            self.channels = self._resolve_channels(descriptor)
            self.battery_channel = self._resolve_battery_channel(descriptor)

            self.board_shim.prepare_session()
            self.board_shim.start_stream()

            try:
                self.board_shim.config_board(MindroveConfigMode.EEG_MODE)
                time.sleep(0.25)
            except Exception:
                pass

            self._connected = True
        except Exception:
            self.disconnect()
            raise

    def _get_board_descriptor(self) -> Dict[str, Any]:
        try:
            descriptor = BoardShim.get_board_descr(self.board_id)
        except Exception:
            return {}
        return descriptor if isinstance(descriptor, dict) else {}

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        value = os.getenv(name, "").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        value = os.getenv(name, "").strip()
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @staticmethod
    def _parse_eeg_rows_env(value: str) -> Optional[Tuple[int, int, int, int]]:
        value = (value or "").strip()
        if not value or value.lower() == "auto":
            return None
        rows = tuple(int(part.strip()) for part in value.split(",") if part.strip())
        if len(rows) != 4:
            raise ValueError("MINDROVE_EEG_ROWS must contain exactly four comma-separated rows.")
        return rows  # type: ignore[return-value]

    @staticmethod
    def _coerce_int_list(value: object) -> List[int]:
        if value is None:
            return []
        if isinstance(value, (str, bytes)):
            return []
        try:
            return [int(v) for v in value]  # type: ignore[arg-type]
        except Exception:
            return []

    @staticmethod
    def _coerce_name_list(value: object) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, bytes):
            return []
        try:
            return [str(v) for v in value if v is not None]  # type: ignore[arg-type]
        except Exception:
            return []

    def _resolve_sample_rate(self, descriptor: Optional[Dict[str, Any]] = None) -> int:
        descriptor = descriptor or {}
        for key in ("sampling_rate", "sample_rate", "fs"):
            try:
                value = descriptor.get(key)
                if value is not None:
                    return int(round(float(value)))
            except Exception:
                pass
        return int(BoardShim.get_sampling_rate(self.board_id))

    def _resolve_battery_channel(self, descriptor: Optional[Dict[str, Any]] = None) -> Optional[int]:
        descriptor = descriptor or {}
        for key in ("battery_channel", "battery"):
            try:
                value = descriptor.get(key)
                if value is not None:
                    return int(value)
            except Exception:
                pass
        try:
            value = BoardShim.get_battery_channel(self.board_id)
            return int(value) if value is not None else None
        except Exception:
            return None

    def _resolve_channels(self, descriptor: Optional[Dict[str, Any]] = None) -> List[MindRoveChannel]:
        descriptor = descriptor or {}
        eeg_rows = self._coerce_int_list(descriptor.get("eeg_channels"))
        if not eeg_rows:
            eeg_rows = list(BoardShim.get_eeg_channels(self.board_id))
        if not eeg_rows:
            raise RuntimeError("MindRove board did not report EEG channels.")
        self.sdk_eeg_rows = tuple(int(row) for row in eeg_rows)

        if self._configured_eeg_rows is not None:
            missing_rows = [
                row for row in self._configured_eeg_rows
                if self.sdk_eeg_rows and row not in self.sdk_eeg_rows
            ]
            if missing_rows:
                raise RuntimeError(
                    "MINDROVE_EEG_ROWS contains rows not reported by the MindRove SDK: "
                    f"{missing_rows}. SDK EEG rows: {list(self.sdk_eeg_rows)}"
                )
            self._auto_detect_rows = False
            return self._channels_from_rows(self._configured_eeg_rows)

        if "eeg_names" in descriptor:
            names = self._coerce_name_list(descriptor.get("eeg_names"))
        else:
            try:
                names = list(BoardShim.get_eeg_names(self.board_id))
            except Exception:
                names = []

        by_name: Dict[str, int] = {}
        for idx, name in enumerate(names):
            if idx < len(eeg_rows):
                by_name[_normalize_label(name)] = eeg_rows[idx]

        selected: List[MindRoveChannel] = []
        for key in self.target_channels:
            target_name = _normalize_label(MINDROVE_CHANNEL_LABELS[key])
            row_index = by_name.get(target_name)
            if row_index is not None:
                selected.append(MindRoveChannel(key, MINDROVE_CHANNEL_LABELS[key], int(row_index)))

        if len(selected) == len(self.target_channels):
            self._auto_detect_rows = False
            return selected

        preferred_rows = [
            MINDROVE_CHANNEL_ROWS.get(key)
            for key in self.target_channels
        ]
        if all(row is not None and int(row) in eeg_rows for row in preferred_rows):
            self._auto_detect_rows = True
            return [
                MindRoveChannel(key, MINDROVE_CHANNEL_LABELS[key], int(MINDROVE_CHANNEL_ROWS[key]))
                for key in self.target_channels
            ]

        if len(eeg_rows) < len(self.target_channels):
            raise RuntimeError(
                f"MindRove board reported {len(eeg_rows)} EEG rows; "
                f"{len(self.target_channels)} are required."
            )

        self._auto_detect_rows = True
        return self._channels_from_rows(tuple(int(row) for row in eeg_rows[:len(self.target_channels)]))

    def _channels_from_rows(self, rows: Sequence[int]) -> List[MindRoveChannel]:
        return [
            MindRoveChannel(key, MINDROVE_CHANNEL_LABELS[key], int(row))
            for key, row in zip(self.target_channels, rows)
        ]

    def _maybe_update_active_rows(self, arr: Any) -> None:
        if not self._auto_detect_rows or np is None:
            return

        candidate_rows = self.sdk_eeg_rows or tuple(range(min(8, int(arr.shape[0]))))
        active_rows: List[int] = []
        for row in candidate_rows:
            row = int(row)
            if 0 <= row < arr.shape[0]:
                std = float(np.std(arr[row, :]))
            else:
                std = 0.0
            if self._min_active_std <= std <= self._max_active_std:
                active_rows.append(row)

        if len(active_rows) < len(self.target_channels):
            return

        selected = tuple(active_rows[:len(self.target_channels)])
        current = tuple(channel.row_index for channel in self.channels)
        if selected != current:
            self.channels = self._channels_from_rows(selected)

    def _update_battery(self, arr: Any) -> None:
        if self.battery_channel is None or np is None:
            return
        row = int(self.battery_channel)
        if 0 <= row < arr.shape[0]:
            values = arr[row, :]
            finite = values[np.isfinite(values)]
            if finite.size:
                self.battery_level = int(round(float(finite[-1])))

    def read_samples(self, max_samples: Optional[int] = 64) -> List[Dict[str, float]]:
        if not self._connected or self.board_shim is None:
            raise RuntimeError("MindRove device is not connected.")

        count = int(self.board_shim.get_board_data_count())
        if count <= 0:
            return []

        if max_samples is None:
            n_samples = count
        else:
            n_samples = max(1, min(int(max_samples), count))
        data = self.board_shim.get_board_data(n_samples)

        if np is None:
            raise RuntimeError("numpy is required to read MindRove samples.")

        arr = np.asarray(data, dtype=float)
        if arr.ndim != 2 or arr.shape[1] == 0:
            return []
        self._maybe_update_active_rows(arr)
        self._update_battery(arr)

        samples: List[Dict[str, float]] = []
        for col in range(arr.shape[1]):
            sample: Dict[str, float] = {}
            for channel in self.channels:
                if channel.row_index < arr.shape[0]:
                    sample[channel.key] = float(arr[channel.row_index, col])
            if len(sample) == len(self.channels):
                samples.append(sample)
        return samples

    def disconnect(self) -> None:
        if self.board_shim is None:
            self._connected = False
            return
        try:
            self.board_shim.stop_stream()
        except Exception:
            pass
        try:
            self.board_shim.release_session()
        except Exception:
            pass
        self.board_shim = None
        self._connected = False
