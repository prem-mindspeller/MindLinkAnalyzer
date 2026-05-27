import numpy as np
from collections import deque

from focuscube.config import FocusCubeConfig
from focuscube.mindrove_source import (
    BRIGHT_EEG_LABELS,
    MindRoveRawSource,
    build_mindrove_input_params,
    contact_state_from_frame,
)


class FakeParams:
    def __init__(self):
        self.ip_address = ""
        self.ip_port = 0
        self.serial_port = ""
        self.timeout = 0


class FakeBoard:
    def __init__(self, data):
        self.data = data
        self.drained = False

    def get_board_data_count(self):
        return self.data.shape[1] if not self.drained else 0

    def get_board_data(self, count):
        self.drained = True
        return self.data[:, :count]


class SequenceBoard:
    def __init__(self, frames):
        self.frames = list(frames)

    def get_board_data_count(self):
        return self.frames[0].shape[1] if self.frames else 0

    def get_board_data(self, count):
        return self.frames.pop(0)


def test_build_mindrove_input_params_uses_wifi_defaults_and_optional_serial():
    config = FocusCubeConfig(mindrove_serial_port="COM9", mindrove_timeout=7)

    params = build_mindrove_input_params(config, FakeParams)

    assert params.ip_address == "192.168.4.1"
    assert params.ip_port == 4210
    assert params.serial_port == "COM9"
    assert params.timeout == 7


def test_mindrove_source_drains_eeg_rows_into_single_raw_sample_stream():
    data = np.zeros((39, 4))
    data[0] = [1.0, 2.0, 3.0, 4.0]
    data[1] = [5.0, 6.0, 7.0, 8.0]
    data[8] = [1000.0, 1000.0, 1000.0, 1000.0]
    data[9] = [1000.0, 1000.0, 1000.0, 1000.0]
    data[18] = [87.0, 88.0, 89.0, 90.0]
    source = MindRoveRawSource(
        FocusCubeConfig(
            sample_rate=500,
            window_size=4,
            overlap_size=2,
            worn_required_consecutive_frames=1,
        ),
        board=FakeBoard(data),
        eeg_channels=[0, 1],
        battery_channel=18,
        resistance_channels=[8, 9],
        sample_rate=500,
        device_name="MindRoveWifi",
    )

    source.drain_board_data()

    assert list(source.raw_samples) == [3.0, 4.0, 5.0, 6.0]
    assert source.battery == 90
    assert source.device_status["connected"] is True
    assert source.device_status["deviceName"] == "MindRoveWifi"
    assert source.device_status["sampleRate"] == 500
    assert source.device_status["eegChannels"] == [0, 1]
    assert source.device_status["worn"] is True


def test_bright_eeg_defaults_are_fp1_fp2_o1_o2_rows():
    source = MindRoveRawSource(FocusCubeConfig())

    assert source.eeg_channels == [0, 1, 4, 5]
    assert source.device_status["eegLabels"] == ["Fp1", "Fp2", "O1", "O2"]


def test_mindrove_source_auto_selects_four_active_sdk_rows_positionally():
    data = np.zeros((39, 8))
    data[0] = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    data[1] = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    data[2] = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    data[3] = [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]
    source = MindRoveRawSource(
        FocusCubeConfig(
            mindrove_eeg_rows=None,
            sample_rate=500,
            window_size=4,
            overlap_size=2,
            worn_min_active_eeg_rows=4,
            worn_required_consecutive_frames=1,
        ),
        board=FakeBoard(data),
        sdk_eeg_channels=[0, 1, 2, 3, 4, 5],
        sample_rate=500,
    )

    source.drain_board_data()

    assert source.eeg_channels == [0, 1, 2, 3]
    assert source.device_status["eegLabels"] == ["Fp1", "Fp2", "O1", "O2"]
    assert source.device_status["worn"] is True
    assert list(source.channel_samples[2]) == list(data[2])
    assert list(source.channel_samples[3]) == list(data[3])


def test_mindrove_source_blocks_floating_eeg_when_resistance_is_high():
    data = np.zeros((39, 4))
    data[0] = [1.0, 2.0, 3.0, 4.0]
    data[1] = [5.0, 6.0, 7.0, 8.0]
    data[8] = [10_000_000.0] * 4
    data[9] = [10_000_000.0] * 4
    source = MindRoveRawSource(
        FocusCubeConfig(
            sample_rate=500,
            window_size=4,
            overlap_size=2,
            worn_resistance_threshold=5_000_000.0,
            worn_min_good_resistance_pairs=2,
            contact_mode="resistance",
        ),
        board=FakeBoard(data),
        eeg_channels=[0, 1],
        resistance_channels=[8, 9],
        sample_rate=500,
    )

    source.drain_board_data()
    payload = source.payload()

    assert list(source.raw_samples) == []
    assert source.device_status["worn"] is False
    assert source.device_status["contactQuality"] == 0.0
    assert payload["mode"] == "device_not_worn"
    assert payload["attention"] == 0.0
    assert source.device_status["contactReason"] == "resistance"


def test_mindrove_source_accepts_eeg_when_resistance_is_good():
    data = np.zeros((39, 4))
    data[0] = [1.0, 2.0, 3.0, 4.0]
    data[1] = [5.0, 6.0, 7.0, 8.0]
    data[8] = [1000.0] * 4
    data[9] = [1000.0] * 4
    source = MindRoveRawSource(
        FocusCubeConfig(
            sample_rate=500,
            window_size=4,
            overlap_size=2,
            worn_resistance_threshold=5_000_000.0,
            worn_min_good_resistance_pairs=2,
            worn_required_consecutive_frames=1,
        ),
        board=FakeBoard(data),
        eeg_channels=[0, 1],
        resistance_channels=[8, 9],
        sample_rate=500,
    )

    source.drain_board_data()

    assert list(source.raw_samples) == [3.0, 4.0, 5.0, 6.0]
    assert source.device_status["worn"] is True
    assert source.device_status["contactQuality"] == 1.0


def test_mindrove_source_waits_for_stable_worn_state_before_accepting_samples():
    frame = np.zeros((39, 4))
    frame[0] = [1.0, 2.0, 3.0, 4.0]
    frame[1] = [5.0, 6.0, 7.0, 8.0]
    frame[8] = [1000.0] * 4
    frame[9] = [1000.0] * 4
    source = MindRoveRawSource(
        FocusCubeConfig(
            sample_rate=500,
            window_size=4,
            overlap_size=2,
            worn_resistance_threshold=5_000_000.0,
            worn_min_good_resistance_pairs=2,
            worn_required_consecutive_frames=3,
        ),
        board=SequenceBoard([frame.copy(), frame.copy(), frame.copy()]),
        eeg_channels=[0, 1],
        resistance_channels=[8, 9],
        sample_rate=500,
    )

    source.drain_board_data()
    assert list(source.raw_samples) == []
    assert source.device_status["worn"] is False
    assert source.device_status["contactReason"] == "resistance_stabilizing"
    assert source.device_status["contactStableFrames"] == 1

    source.drain_board_data()
    assert list(source.raw_samples) == []
    assert source.device_status["worn"] is False
    assert source.device_status["contactStableFrames"] == 2

    source.drain_board_data()
    assert list(source.raw_samples) == [3.0, 4.0, 5.0, 6.0]
    assert source.device_status["worn"] is True
    assert source.device_status["contactReason"] == "resistance"


def test_contact_state_from_frame_matches_capture_eeg_variance_fallback():
    data = np.zeros((39, 8))
    data[0] = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    data[1] = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    data[2] = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    data[3] = [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]

    contact = contact_state_from_frame(
        data,
        eeg_rows=[0, 1, 2, 3],
        resistance_rows=[],
        config=FocusCubeConfig(worn_min_active_eeg_rows=4),
    )

    assert contact.worn is True
    assert contact.quality == 1.0
    assert contact.reason == "eeg_variance_fallback"
    assert len(contact.eeg_row_std) == 4
    assert len(contact.eeg_row_abs_mean) == 4


def test_mindrove_source_auto_contact_accepts_plausible_eeg_when_resistance_is_high():
    data = np.zeros((39, 8))
    data[0] = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    data[1] = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    data[8] = [10_000_000.0] * 8
    data[9] = [10_000_000.0] * 8
    source = MindRoveRawSource(
        FocusCubeConfig(
            sample_rate=500,
            window_size=4,
            overlap_size=2,
            contact_mode="auto",
            worn_min_active_eeg_rows=2,
            worn_required_consecutive_frames=1,
        ),
        board=FakeBoard(data),
        eeg_channels=[0, 1],
        resistance_channels=[8, 9],
        sample_rate=500,
    )

    source.drain_board_data()

    assert source.device_status["worn"] is True
    assert source.device_status["contactReason"] == "eeg_variance_fallback"
    assert source.device_status["eegRowStd"][0] > 0.5


def test_mindrove_source_resistance_mode_rejects_high_resistance_even_with_eeg():
    data = np.zeros((39, 8))
    data[0] = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    data[1] = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    data[8] = [10_000_000.0] * 8
    data[9] = [10_000_000.0] * 8
    source = MindRoveRawSource(
        FocusCubeConfig(
            sample_rate=500,
            window_size=4,
            overlap_size=2,
            contact_mode="resistance",
        ),
        board=FakeBoard(data),
        eeg_channels=[0, 1],
        resistance_channels=[8, 9],
        sample_rate=500,
    )

    source.drain_board_data()

    assert source.device_status["worn"] is False
    assert source.device_status["contactReason"] == "resistance"


def test_mindrove_source_can_print_channel_wise_raw_preview(capsys):
    data = np.zeros((39, 4))
    data[0] = [1.0, 2.0, 3.0, 4.0]
    data[1] = [5.0, 6.0, 7.0, 8.0]
    data[8] = [1000.0] * 4
    data[9] = [1000.0] * 4
    source = MindRoveRawSource(
        FocusCubeConfig(
            print_raw=True,
            raw_print_rows=2,
            raw_print_samples=3,
            raw_print_interval=0,
            sample_rate=500,
            window_size=4,
            overlap_size=2,
        ),
        board=FakeBoard(data),
        eeg_channels=[0, 1],
        resistance_channels=[8, 9],
        sample_rate=500,
    )

    source.drain_board_data()

    output = capsys.readouterr().out
    assert "raw_sdk shape=39x4 eeg_rows=[0, 1]" in output
    assert "row0=[2.0,3.0,4.0]" in output
    assert "row1=[6.0,7.0,8.0]" in output


def test_mindrove_source_payload_uses_calibrated_channel_focus_index():
    config = FocusCubeConfig(
        calibration_windows=1,
        focus_smoothing=1.0,
        sample_rate=500,
        window_size=500,
        overlap_size=250,
        focus_update_stride_samples=0,
        disable_worn_gate=True,
    )
    source = MindRoveRawSource(config, eeg_channels=[0, 1, 4, 5], sample_rate=500)

    source.channel_samples = {
        row: deque(_signal([(10, 45), (18, 8)]), maxlen=6000)
        for row in [0, 1, 4, 5]
    }
    baseline_payload = source.payload()

    source.channel_samples = {
        0: deque(_signal([(10, 18), (18, 45)]), maxlen=6000),
        1: deque(_signal([(10, 18), (18, 45)]), maxlen=6000),
        4: deque(_signal([(10, 18), (18, 8)]), maxlen=6000),
        5: deque(_signal([(10, 18), (18, 8)]), maxlen=6000),
    }
    focus_payload = source.payload()

    assert baseline_payload["mode"] == "device"
    assert focus_payload["mode"] == "device"
    assert focus_payload["attention"] > 0.70
    assert focus_payload["normalized"]["focusIndex"] > 0.70
    assert "frontal" in focus_payload["regions"]
    assert "occipital" in focus_payload["regions"]


def test_mindrove_source_focus_works_when_sdk_rows_are_zero_to_three():
    config = FocusCubeConfig(
        calibration_windows=1,
        focus_smoothing=1.0,
        sample_rate=500,
        window_size=500,
        overlap_size=250,
        focus_update_stride_samples=0,
        disable_worn_gate=True,
    )
    source = MindRoveRawSource(
        config,
        eeg_channels=[0, 1, 2, 3],
        sample_rate=500,
    )

    source.channel_samples = {
        row: deque(_signal([(10, 45), (18, 8)]), maxlen=6000)
        for row in [0, 1, 2, 3]
    }
    source.payload()
    source.channel_samples = {
        0: deque(_signal([(10, 18), (18, 45)]), maxlen=6000),
        1: deque(_signal([(10, 18), (18, 45)]), maxlen=6000),
        2: deque(_signal([(10, 18), (18, 8)]), maxlen=6000),
        3: deque(_signal([(10, 18), (18, 8)]), maxlen=6000),
    }

    focus_payload = source.payload()

    assert focus_payload["attention"] > 0.70
    assert focus_payload["regions"]["occipital"]["relative"]["alpha"] > 0.55


def test_mindrove_source_visual_bands_are_live_normalized():
    config = FocusCubeConfig(
        calibration_windows=1,
        focus_smoothing=1.0,
        sample_rate=500,
        window_size=500,
        overlap_size=250,
        focus_update_stride_samples=0,
        disable_worn_gate=True,
    )
    source = MindRoveRawSource(config, eeg_channels=[0, 1, 4, 5], sample_rate=500)

    source.channel_samples = {
        row: deque(_signal([(10, 35), (18, 8)]), maxlen=6000)
        for row in [0, 1, 4, 5]
    }
    first = source.payload()
    source.channel_samples = {
        row: deque(_signal([(10, 70), (18, 8)]), maxlen=6000)
        for row in [0, 1, 4, 5]
    }
    second = source.payload()

    assert first["normalized"]["alpha"] == 0.5
    assert second["normalized"]["alpha"] > first["normalized"]["alpha"]


def test_calibration_progress_uses_monotonic_samples_after_buffer_maxes_out():
    config = FocusCubeConfig(
        calibration_windows=12,
        focus_smoothing=1.0,
        sample_rate=500,
        window_size=1000,
        overlap_size=500,
        focus_update_stride_samples=500,
        disable_worn_gate=True,
    )
    frame = np.zeros((39, 500))
    t = np.arange(0, 500) / 500
    for row in [0, 1, 4, 5]:
        frame[row] = 40 * np.sin(2 * np.pi * 10 * t)
    source = MindRoveRawSource(
        config,
        board=SequenceBoard([frame.copy() for _ in range(14)]),
        eeg_channels=[0, 1, 4, 5],
        sample_rate=500,
    )

    payload = None
    for _ in range(14):
        source.drain_board_data()
        maybe_payload = source.payload()
        if maybe_payload:
            payload = maybe_payload

    assert payload is not None
    assert payload["mode"] == "device"
    assert payload["focus"]["baselineCount"] == 12
    assert payload["focus"]["baselineRequired"] == 12


def _signal(components, fs=500, seconds=3):
    t = np.arange(0, seconds, 1 / fs)
    out = np.zeros_like(t)
    for freq, amplitude in components:
        out += amplitude * np.sin(2 * np.pi * freq * t)
    return out
