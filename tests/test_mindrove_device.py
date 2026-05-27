import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_mindrove_device(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1] / "newBackend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    spec = importlib.util.spec_from_file_location("mindrove_device_under_test", backend_dir / "mindrove_device.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "MINDROVE_SDK_AVAILABLE", True)
    monkeypatch.setattr(module, "BoardIds", types.SimpleNamespace(MINDROVE_WIFI_BOARD=0))
    monkeypatch.setattr(module, "MindRoveInputParams", lambda: types.SimpleNamespace())
    monkeypatch.setattr(module, "MindroveConfigMode", types.SimpleNamespace(EEG_MODE="eeg"))
    monkeypatch.setattr(module.time, "sleep", lambda *_args, **_kwargs: None)
    return module


def test_mindrove_connect_uses_descriptor_when_eeg_names_are_null(monkeypatch):
    module = _load_mindrove_device(monkeypatch)

    class FakeBoardShim:
        names_calls = 0
        created_params = None

        def __init__(self, board_id, params):
            self.board_id = board_id
            self.params = params
            FakeBoardShim.created_params = params

        def prepare_session(self):
            pass

        def start_stream(self):
            pass

        def config_board(self, _mode):
            pass

        @staticmethod
        def get_board_descr(_board_id):
            return {
                "sampling_rate": 500,
                "eeg_channels": [0, 1, 2, 3, 4, 5, 6, 7],
                "eeg_names": None,
            }

        @staticmethod
        def get_eeg_channels(_board_id):
            return [0, 1, 2, 3, 4, 5, 6, 7]

        @staticmethod
        def get_eeg_names(_board_id):
            FakeBoardShim.names_calls += 1
            raise RuntimeError("eeg_names is null")

        @staticmethod
        def get_sampling_rate(_board_id):
            return 500

    monkeypatch.setattr(module, "BoardShim", FakeBoardShim)

    device = module.MindRoveDevice()
    device.connect()

    assert FakeBoardShim.names_calls == 0
    assert FakeBoardShim.created_params.ip_address == "192.168.4.1"
    assert FakeBoardShim.created_params.ip_port == 4210
    assert FakeBoardShim.created_params.timeout == 10
    assert device.sample_rate == 500
    assert [(ch.key, ch.label, ch.row_index) for ch in device.channels] == [
        ("fp1", "FP1", 0),
        ("fp2", "FP2", 1),
        ("o1", "O1", 2),
        ("o2", "O2", 3),
    ]


def test_mindrove_read_samples_auto_selects_active_sdk_rows(monkeypatch):
    module = _load_mindrove_device(monkeypatch)
    monkeypatch.delenv("MINDROVE_EEG_ROWS", raising=False)

    class FakeBoardShim:
        def __init__(self, _board_id, _params):
            self.data = module.np.zeros((39, 4), dtype=float)
            self.data[0, :] = [10.0, 11.0, 12.0, 13.0]
            self.data[1, :] = [20.0, 21.0, 22.0, 23.0]
            self.data[2, :] = [30.0, 31.0, 32.0, 33.0]
            self.data[3, :] = [40.0, 41.0, 42.0, 43.0]
            self.data[4, :] = [0.0, 0.0, 0.0, 0.0]
            self.data[5, :] = [0.0, 0.0, 0.0, 0.0]

        def prepare_session(self):
            pass

        def start_stream(self):
            pass

        def config_board(self, _mode):
            pass

        def get_board_data_count(self):
            return self.data.shape[1]

        def get_board_data(self, n_samples):
            return self.data[:, -int(n_samples):]

        @staticmethod
        def get_board_descr(_board_id):
            return {
                "sampling_rate": 500,
                "eeg_channels": [0, 1, 2, 3, 4, 5, 6, 7],
                "eeg_names": None,
            }

        @staticmethod
        def get_eeg_channels(_board_id):
            return [0, 1, 2, 3, 4, 5, 6, 7]

        @staticmethod
        def get_sampling_rate(_board_id):
            return 500

    monkeypatch.setattr(module, "BoardShim", FakeBoardShim)

    device = module.MindRoveDevice()
    device.connect()
    samples = device.read_samples(max_samples=None)

    assert [(ch.key, ch.row_index) for ch in device.channels] == [
        ("fp1", 0),
        ("fp2", 1),
        ("o1", 2),
        ("o2", 3),
    ]
    assert len(samples) == 4
    assert samples[-1] == {"fp1": 13.0, "fp2": 23.0, "o1": 33.0, "o2": 43.0}


def test_mindrove_read_samples_updates_battery_from_sdk_channel(monkeypatch):
    module = _load_mindrove_device(monkeypatch)
    monkeypatch.delenv("MINDROVE_EEG_ROWS", raising=False)

    class FakeBoardShim:
        def __init__(self, _board_id, _params):
            self.data = module.np.zeros((39, 3), dtype=float)
            self.data[0, :] = [10.0, 11.0, 12.0]
            self.data[1, :] = [20.0, 21.0, 22.0]
            self.data[2, :] = [30.0, 31.0, 32.0]
            self.data[3, :] = [40.0, 41.0, 42.0]
            self.data[38, :] = [67.0, module.np.nan, 66.0]

        def prepare_session(self):
            pass

        def start_stream(self):
            pass

        def config_board(self, _mode):
            pass

        def get_board_data_count(self):
            return self.data.shape[1]

        def get_board_data(self, n_samples):
            return self.data[:, -int(n_samples):]

        @staticmethod
        def get_board_descr(_board_id):
            return {
                "sampling_rate": 500,
                "eeg_channels": [0, 1, 2, 3],
                "eeg_names": None,
            }

        @staticmethod
        def get_eeg_channels(_board_id):
            return [0, 1, 2, 3]

        @staticmethod
        def get_sampling_rate(_board_id):
            return 500

        @staticmethod
        def get_battery_channel(_board_id):
            return 38

    monkeypatch.setattr(module, "BoardShim", FakeBoardShim)

    device = module.MindRoveDevice()
    device.connect()

    assert device.battery_channel == 38
    assert device.battery_level is None

    device.read_samples(max_samples=None)

    assert device.battery_level == 66


def test_mindrove_eeg_rows_env_locks_explicit_mapping(monkeypatch):
    module = _load_mindrove_device(monkeypatch)
    monkeypatch.setenv("MINDROVE_EEG_ROWS", "0,1,4,5")

    class FakeBoardShim:
        def __init__(self, _board_id, _params):
            self.data = module.np.zeros((39, 3), dtype=float)
            self.data[0, :] = [1.0, 2.0, 3.0]
            self.data[1, :] = [4.0, 5.0, 6.0]
            self.data[2, :] = [100.0, 101.0, 102.0]
            self.data[3, :] = [200.0, 201.0, 202.0]
            self.data[4, :] = [7.0, 8.0, 9.0]
            self.data[5, :] = [10.0, 11.0, 12.0]

        def prepare_session(self):
            pass

        def start_stream(self):
            pass

        def config_board(self, _mode):
            pass

        def get_board_data_count(self):
            return self.data.shape[1]

        def get_board_data(self, n_samples):
            return self.data[:, -int(n_samples):]

        @staticmethod
        def get_board_descr(_board_id):
            return {
                "sampling_rate": 500,
                "eeg_channels": [0, 1, 2, 3, 4, 5, 6, 7],
                "eeg_names": None,
            }

        @staticmethod
        def get_sampling_rate(_board_id):
            return 500

    monkeypatch.setattr(module, "BoardShim", FakeBoardShim)

    device = module.MindRoveDevice()
    device.connect()
    samples = device.read_samples(max_samples=None)

    assert [(ch.key, ch.row_index) for ch in device.channels] == [
        ("fp1", 0),
        ("fp2", 1),
        ("o1", 4),
        ("o2", 5),
    ]
    assert samples[-1] == {"fp1": 3.0, "fp2": 6.0, "o1": 9.0, "o2": 12.0}


def test_mindrove_eeg_rows_env_requires_four_rows(monkeypatch):
    module = _load_mindrove_device(monkeypatch)
    monkeypatch.setenv("MINDROVE_EEG_ROWS", "0,1,2")

    with pytest.raises(ValueError, match="exactly four"):
        module.MindRoveDevice()


def test_mindrove_connect_releases_partial_session_on_failure(monkeypatch):
    module = _load_mindrove_device(monkeypatch)

    class FakeBoardShim:
        released = False
        stopped = False

        def __init__(self, board_id, params):
            self.board_id = board_id
            self.params = params

        def prepare_session(self):
            pass

        def start_stream(self):
            raise RuntimeError("stream failed")

        def stop_stream(self):
            FakeBoardShim.stopped = True

        def release_session(self):
            FakeBoardShim.released = True

        @staticmethod
        def get_board_descr(_board_id):
            return {
                "sampling_rate": 500,
                "eeg_channels": [0, 1, 2, 3],
                "eeg_names": None,
            }

    monkeypatch.setattr(module, "BoardShim", FakeBoardShim)

    device = module.MindRoveDevice()

    try:
        device.connect()
    except RuntimeError as exc:
        assert str(exc) == "stream failed"
    else:
        raise AssertionError("connect() should propagate the stream failure")

    assert FakeBoardShim.stopped is True
    assert FakeBoardShim.released is True
    assert device.board_shim is None
    assert device._connected is False


def test_mindrove_connect_constructs_board_before_metadata_lookup(monkeypatch):
    module = _load_mindrove_device(monkeypatch)

    class FakeBoardShim:
        constructed = False
        metadata_before_construct = False

        def __init__(self, _board_id, _params):
            FakeBoardShim.constructed = True

        def prepare_session(self):
            pass

        def start_stream(self):
            pass

        def config_board(self, _mode):
            pass

        @staticmethod
        def get_board_descr(_board_id):
            if not FakeBoardShim.constructed:
                FakeBoardShim.metadata_before_construct = True
                return {}
            return {
                "sampling_rate": 500,
                "eeg_channels": [0, 1, 2, 3],
                "eeg_names": None,
            }

        @staticmethod
        def get_eeg_channels(_board_id):
            return [0, 1, 2, 3]

        @staticmethod
        def get_sampling_rate(_board_id):
            return 500

    monkeypatch.setattr(module, "BoardShim", FakeBoardShim)

    device = module.MindRoveDevice()
    device.connect()

    assert FakeBoardShim.constructed is True
    assert FakeBoardShim.metadata_before_construct is False
    assert [(ch.key, ch.row_index) for ch in device.channels] == [
        ("fp1", 0),
        ("fp2", 1),
        ("o1", 2),
        ("o2", 3),
    ]
