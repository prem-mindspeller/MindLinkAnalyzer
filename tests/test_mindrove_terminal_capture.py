import csv
import importlib.util
import sys
import types
from pathlib import Path

import numpy as np


def _load_capture_module():
    backend_dir = Path(__file__).resolve().parents[1] / "newBackend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    spec = importlib.util.spec_from_file_location(
        "mindrove_terminal_capture_under_test",
        backend_dir / "mindrove_terminal_capture.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeParams:
    def __init__(self):
        self.ip_address = ""
        self.ip_port = 0
        self.serial_port = ""
        self.timeout = 0


def test_build_mindrove_input_params_matches_focus_cube_defaults():
    capture = _load_capture_module()
    config = capture.CaptureConfig(serial_port="COM9", timeout=7)

    params = capture.build_mindrove_input_params(config, FakeParams)

    assert params.ip_address == "192.168.4.1"
    assert params.ip_port == 4210
    assert params.serial_port == "COM9"
    assert params.timeout == 7


def test_parse_eeg_rows_requires_four_rows():
    capture = _load_capture_module()

    assert capture.parse_eeg_rows("0,1,4,5") == (0, 1, 4, 5)
    assert capture.parse_eeg_rows("auto") is None

    try:
        capture.parse_eeg_rows("0,1")
    except ValueError as exc:
        assert "exactly four" in str(exc)
    else:
        raise AssertionError("parse_eeg_rows should reject non-four-channel input")


def test_active_eeg_rows_selects_first_four_nonzero_sdk_rows():
    capture = _load_capture_module()
    data = np.zeros((39, 8))
    for row in (0, 1, 2, 3):
        data[row] = np.arange(8, dtype=float) + row
    data[4] = [0.0] * 8
    data[5] = [0.0] * 8

    rows, stds = capture.active_eeg_rows_from_frame(
        data,
        candidate_rows=(0, 1, 2, 3, 4, 5, 6, 7),
        config=capture.CaptureConfig(),
    )

    assert rows == [0, 1, 2, 3]
    assert stds[0] > 0.5
    assert stds[4] == 0.0


def test_contact_state_uses_good_resistance_when_available():
    capture = _load_capture_module()
    data = np.zeros((39, 8))
    data[0] = np.arange(8, dtype=float)
    data[1] = np.arange(8, dtype=float) + 1.0
    data[4] = np.arange(8, dtype=float) + 2.0
    data[5] = np.arange(8, dtype=float) + 3.0
    data[8] = [1000.0] * 8
    data[9] = [2000.0] * 8

    state = capture.contact_state_from_frame(
        data,
        eeg_rows=(0, 1, 4, 5),
        resistance_rows=(8, 9),
        config=capture.CaptureConfig(),
    )

    assert state.worn is True
    assert state.quality == 1.0
    assert state.reason == "resistance"
    assert state.resistance_ohms == [1000.0, 2000.0]
    assert len(state.eeg_row_std) == 4


def test_contact_state_auto_falls_back_to_eeg_variance():
    capture = _load_capture_module()
    data = np.zeros((39, 8))
    for row in (0, 1, 4, 5):
        data[row] = np.arange(8, dtype=float)
    data[8] = [10_000_000.0] * 8
    data[9] = [10_000_000.0] * 8

    state = capture.contact_state_from_frame(
        data,
        eeg_rows=(0, 1, 4, 5),
        resistance_rows=(8, 9),
        config=capture.CaptureConfig(contact_mode="auto"),
    )

    assert state.worn is True
    assert state.reason == "eeg_variance_fallback"
    assert state.quality == 1.0


def test_contact_state_auto_rejects_when_occipital_rows_are_zero():
    capture = _load_capture_module()
    data = np.zeros((39, 8))
    data[0] = np.arange(8, dtype=float)
    data[1] = np.arange(8, dtype=float) + 1.0
    data[4] = [0.0] * 8
    data[5] = [0.0] * 8

    state = capture.contact_state_from_frame(
        data,
        eeg_rows=(0, 1, 4, 5),
        resistance_rows=(),
        config=capture.CaptureConfig(contact_mode="auto"),
    )

    assert state.worn is False
    assert state.reason == "low_variance"
    assert state.quality == 0.5
    assert state.eeg_row_std[2] == 0.0
    assert state.eeg_row_std[3] == 0.0


def test_contact_state_auto_allows_large_dc_offsets_by_default():
    capture = _load_capture_module()
    data = np.zeros((39, 12))
    data[0] = 14900.0 + np.arange(12, dtype=float) * 2.0
    data[1] = 12200.0 + np.arange(12, dtype=float) * 2.0
    data[2] = 47500.0 + np.arange(12, dtype=float) * 2.0
    data[3] = 44800.0 + np.arange(12, dtype=float) * 2.0

    state = capture.contact_state_from_frame(
        data,
        eeg_rows=(0, 1, 2, 3),
        resistance_rows=(),
        config=capture.CaptureConfig(contact_mode="auto"),
    )

    assert state.worn is True
    assert state.reason == "eeg_variance_fallback"


def test_contact_state_auto_can_reject_large_dc_offsets_when_enabled():
    capture = _load_capture_module()
    data = np.zeros((39, 12))
    data[0] = 14900.0 + np.arange(12, dtype=float) * 2.0
    data[1] = 12200.0 + np.arange(12, dtype=float) * 2.0
    data[2] = 47500.0 + np.arange(12, dtype=float) * 2.0
    data[3] = 44800.0 + np.arange(12, dtype=float) * 2.0

    state = capture.contact_state_from_frame(
        data,
        eeg_rows=(0, 1, 2, 3),
        resistance_rows=(),
        config=capture.CaptureConfig(contact_mode="auto", worn_max_abs_mean=10_000.0),
    )

    assert state.worn is False
    assert state.reason == "dc_offset"


def test_contact_state_resistance_mode_rejects_high_resistance():
    capture = _load_capture_module()
    data = np.zeros((39, 8))
    for row in (0, 1, 4, 5):
        data[row] = np.arange(8, dtype=float)
    data[8] = [10_000_000.0] * 8
    data[9] = [10_000_000.0] * 8

    state = capture.contact_state_from_frame(
        data,
        eeg_rows=(0, 1, 4, 5),
        resistance_rows=(8, 9),
        config=capture.CaptureConfig(contact_mode="resistance"),
    )

    assert state.worn is False
    assert state.reason == "resistance"


def test_csv_records_preserve_four_mindrove_channels_and_contact_metadata():
    capture = _load_capture_module()
    data = np.zeros((39, 3))
    data[0] = [1.0, 2.0, 3.0]
    data[1] = [4.0, 5.0, 6.0]
    data[4] = [7.0, 8.0, 9.0]
    data[5] = [10.0, 11.0, 12.0]
    data[8] = [1000.0, 1001.0, 1002.0]
    data[9] = [2000.0, 2001.0, 2002.0]
    state = capture.ContactState(
        worn=True,
        quality=1.0,
        reason="resistance",
        resistance_ohms=[1002.0, 2002.0],
        eeg_row_std=[0.5, 0.6, 0.7, 0.8],
    )

    records = capture.records_from_frame(
        data,
        eeg_rows=(0, 1, 4, 5),
        resistance_rows=(8, 9),
        contact=state,
        sample_rate=500,
        start_sample_index=10,
        batch_end_timestamp=100.004,
        battery=88,
    )

    assert records[0]["sample_index"] == 10
    assert records[0]["timestamp"] == "100.000000"
    assert records[0]["fp1"] == "1.000000"
    assert records[0]["fp2"] == "4.000000"
    assert records[0]["o1"] == "7.000000"
    assert records[0]["o2"] == "10.000000"
    assert records[0]["worn"] == "true"
    assert records[0]["contact_reason"] == "resistance"
    assert records[0]["battery"] == 88
    assert records[2]["sample_index"] == 12
    assert records[2]["resistance_8"] == "1002.000000"
    assert records[2]["eeg_std_5"] == "0.800000"

    output = Path(__file__).resolve().parent / "_tmp_mindrove_capture_test.csv"
    try:
        capture.write_csv_records(output, records, capture.csv_fieldnames((8, 9), (0, 1, 4, 5)))
        with output.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

        assert len(rows) == 3
        assert rows[1]["sample_index"] == "11"
        assert rows[1]["o2"] == "11.000000"
    finally:
        output.unlink(missing_ok=True)


def test_channel_frame_values_include_aggregate_mean():
    capture = _load_capture_module()
    data = np.zeros((39, 3))
    data[0] = [1.0, 2.0, 3.0]
    data[1] = [4.0, 5.0, 6.0]
    data[2] = [7.0, 8.0, 9.0]
    data[3] = [10.0, 11.0, 12.0]

    values = capture.channel_frame_values(data, eeg_rows=(0, 1, 2, 3))

    assert values["fp1"] == [1.0, 2.0, 3.0]
    assert values["fp2"] == [4.0, 5.0, 6.0]
    assert values["o1"] == [7.0, 8.0, 9.0]
    assert values["o2"] == [10.0, 11.0, 12.0]
    assert values["aggregate"] == [5.5, 6.5, 7.5]


def test_rolling_plot_buffer_truncates_and_tracks_aggregate():
    capture = _load_capture_module()
    data = np.zeros((39, 4))
    data[0] = [1.0, 2.0, 3.0, 4.0]
    data[1] = [2.0, 3.0, 4.0, 5.0]
    data[2] = [3.0, 4.0, 5.0, 6.0]
    data[3] = [4.0, 5.0, 6.0, 7.0]
    buffer = capture.RollingPlotBuffer(max_samples=3)

    buffer.append_frame(data, eeg_rows=(0, 1, 2, 3))
    series = buffer.series()

    assert series["fp1"] == [2.0, 3.0, 4.0]
    assert series["fp2"] == [3.0, 4.0, 5.0]
    assert series["o1"] == [4.0, 5.0, 6.0]
    assert series["o2"] == [5.0, 6.0, 7.0]
    assert series["aggregate"] == [3.5, 4.5, 5.5]


def test_prepare_plot_series_demeans_each_channel_for_display():
    capture = _load_capture_module()
    series = {
        "fp1": [100.0, 101.0, 102.0],
        "fp2": [200.0, 201.0, 202.0],
        "o1": [300.0, 301.0, 302.0],
        "o2": [400.0, 401.0, 402.0],
        "aggregate": [250.0, 251.0, 252.0],
    }

    prepared = capture.prepare_plot_series(series, mode="demean")

    assert prepared["fp1"] == [-1.0, 0.0, 1.0]
    assert prepared["fp2"] == [-1.0, 0.0, 1.0]
    assert prepared["o1"] == [-1.0, 0.0, 1.0]
    assert prepared["o2"] == [-1.0, 0.0, 1.0]
    assert prepared["aggregate"] == [-1.0, 0.0, 1.0]


def test_prepare_plot_series_can_show_raw_values():
    capture = _load_capture_module()
    series = {"fp1": [100.0, 101.0], "aggregate": [200.0, 202.0]}

    prepared = capture.prepare_plot_series(series, mode="raw")

    assert prepared == series


def test_config_from_args_defaults_to_auto_eeg_rows():
    capture = _load_capture_module()

    args = capture.parse_args([])
    config = capture.config_from_args(args)

    assert config.eeg_rows is None


def test_config_from_args_enables_plot_mode():
    capture = _load_capture_module()

    args = capture.parse_args(["--plot", "--plot-window-seconds", "12"])
    config = capture.config_from_args(args)

    assert config.plot is True
    assert config.plot_window_seconds == 12.0
    assert config.plot_backend == "TkAgg"
    assert config.plot_mode == "demean"


def test_config_from_args_accepts_plot_backend_override():
    capture = _load_capture_module()

    args = capture.parse_args(["--plot", "--plot-backend", "WebAgg"])
    config = capture.config_from_args(args)

    assert config.plot_backend == "WebAgg"
