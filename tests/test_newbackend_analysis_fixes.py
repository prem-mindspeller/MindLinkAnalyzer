import importlib.util
import json
import sys
import types
import warnings
from pathlib import Path


def _load_backend():
    if "serial" not in sys.modules:
        serial_mod = types.ModuleType("serial")
        serial_mod.SerialException = OSError
        serial_mod.Serial = lambda *args, **kwargs: None
        tools_mod = types.ModuleType("serial.tools")
        list_ports_mod = types.ModuleType("serial.tools.list_ports")
        list_ports_mod.comports = lambda: []
        tools_mod.list_ports = list_ports_mod
        serial_mod.tools = tools_mod
        sys.modules["serial"] = serial_mod
        sys.modules["serial.tools"] = tools_mod
        sys.modules["serial.tools.list_ports"] = list_ports_mod

    if "fastapi" not in sys.modules:
        fastapi_mod = types.ModuleType("fastapi")

        class _FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def add_middleware(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda fn: fn

            def post(self, *args, **kwargs):
                return lambda fn: fn

            def websocket(self, *args, **kwargs):
                return lambda fn: fn

        fastapi_mod.FastAPI = _FastAPI
        fastapi_mod.WebSocket = object
        fastapi_mod.WebSocketDisconnect = Exception
        middleware_mod = types.ModuleType("fastapi.middleware")
        cors_mod = types.ModuleType("fastapi.middleware.cors")
        cors_mod.CORSMiddleware = object
        sys.modules["fastapi"] = fastapi_mod
        sys.modules["fastapi.middleware"] = middleware_mod
        sys.modules["fastapi.middleware.cors"] = cors_mod

    backend_dir = Path(__file__).resolve().parents[1] / "newBackend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    spec = importlib.util.spec_from_file_location("newbackend_analysis_fixes", backend_dir / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _feature_rows(n, offset=0.0):
    rows = []
    for i in range(n):
        value = offset + float(i)
        rows.append({
            "alpha_power": value,
            "beta_power": value * 0.5 + 1.0,
            "alpha_theta_ratio": value + 0.25,
            "_gamma_evaluated": 1.0,
        })
    return rows


def test_task_and_baseline_blocks_are_not_equalized():
    backend = _load_backend()

    summary, analysis = backend._analyze_task_vs_baseline(
        task_rows=_feature_rows(11, offset=10.0),
        baseline_rows=_feature_rows(7, offset=1.0),
        task_id="attention_focus",
        windows_per_block=1,
    )

    assert summary["ess"]["task_blocks"] == 11
    assert summary["ess"]["baseline_blocks"] == 7
    assert analysis["alpha_power"]["n_blocks_task"] == 11
    assert analysis["alpha_power"]["n_blocks_baseline"] == 7


def test_equalize_windows_helper_is_not_available_to_reintroduce_downsampling():
    backend = _load_backend()

    assert not hasattr(backend, "_equalize_windows")


def test_baseline_locale_copy_uses_sixty_seconds():
    locale_dir = Path(__file__).resolve().parents[1] / "ElectronFrontEnd" / "src" / "locales"
    checks = [
        ("en.json", "60", ("30-second", "30 seconds")),
        ("nl.json", "60", ("30 seconden",)),
    ]

    for filename, expected, forbidden_values in checks:
        data = json.loads((locale_dir / filename).read_text(encoding="utf-8"))
        baseline_copy = json.dumps(data["baseline"], ensure_ascii=False)
        manual_copy = data["manual"]["2"]["content"]

        assert expected in baseline_copy
        assert expected in manual_copy
        for forbidden in forbidden_values:
            assert forbidden not in baseline_copy
            assert forbidden not in manual_copy


def test_welch_t_skips_near_constant_series_without_runtime_warning():
    backend = _load_backend()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        t_stat, p_value = backend._welch_t(
            [1.0, 1.0, 1.0, 1.0 + 1e-13],
            [1.0, 1.0, 1.0, 1.0],
        )

    runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert runtime_warnings == []
    assert t_stat == 0.0
    assert p_value == 1.0


def test_sum_p_perm_skips_degenerate_features_without_runtime_warning():
    backend = _load_backend()
    task_rows = [
        {"alpha_power": 1.0, "beta_power": 2.10, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.20, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.15, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.30, "_gamma_evaluated": 1.0},
    ]
    baseline_rows = [
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.85, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.95, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.90, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.88, "_gamma_evaluated": 1.0},
    ]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        obs_sum, perm_p = backend._sum_p_perm(task_rows, baseline_rows)

    runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert runtime_warnings == []
    assert obs_sum is not None
    assert 0.0 <= perm_p <= 1.0


def test_analyze_task_handles_degenerate_feature_summary_without_logging(capsys):
    backend = _load_backend()
    task_rows = [
        {"alpha_power": 1.0, "beta_power": 2.10, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.20, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.15, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.30, "_gamma_evaluated": 1.0},
    ]
    baseline_rows = [
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.85, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.95, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.90, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.88, "_gamma_evaluated": 1.0},
    ]

    backend._analyze_task_vs_baseline(task_rows, baseline_rows, task_id="attention_focus", windows_per_block=1)
    out = capsys.readouterr().out

    assert out == ""


def test_sum_p_perm_handles_degenerate_feature_summary_without_logging(capsys):
    backend = _load_backend()
    task_rows = [
        {"alpha_power": 1.0, "beta_power": 2.10, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.20, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.15, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0, "beta_power": 2.30, "_gamma_evaluated": 1.0},
    ]
    baseline_rows = [
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.85, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.95, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.90, "_gamma_evaluated": 1.0},
        {"alpha_power": 1.0 + 1e-13, "beta_power": 1.88, "_gamma_evaluated": 1.0},
    ]

    backend._sum_p_perm(task_rows, baseline_rows, "attention_focus")
    out = capsys.readouterr().out

    assert out == ""


def test_baseline_calibration_runtime_uses_sixty_seconds():
    baseline_file = Path(__file__).resolve().parents[1] / "ElectronFrontEnd" / "src" / "pages" / "BaselineCalibration1.jsx"
    source = baseline_file.read_text(encoding="utf-8")

    assert "const PHASE_DURATION_S = 60;" in source


def test_battery_normalization_and_extraction_support_multiple_sdk_shapes():
    backend = _load_backend()

    class _Packet:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    assert backend._normalize_battery_level(42) == 42
    assert backend._normalize_battery_level("87") == 87
    assert backend._normalize_battery_level("87%") == 87
    assert backend._normalize_battery_level(150) == 100
    assert backend._normalize_battery_level(-5) == 0
    assert backend._normalize_battery_level("bad") is None

    assert backend._extract_battery_level(_Packet(battery=55)) == 55
    assert backend._extract_battery_level(_Packet(Battery="61")) == 61
    assert backend._extract_battery_level(_Packet(electricity=72.4)) == 72
    assert backend._extract_battery_level(_Packet(power=88)) == 88
    assert backend._extract_battery_level(_Packet(version="1.2")) is None
    assert backend._extract_sdk_extend_battery(_Packet(battery="64%")) == 64
    assert backend._extract_sdk_extend_battery(_Packet(Battery="61")) is None


def test_backend_restores_brainlink_sdk_dll_search_path_setup():
    backend_file = Path(__file__).resolve().parents[1] / "newBackend" / "main.py"
    source = backend_file.read_text(encoding="utf-8")

    assert "_BRAINLINK_PYD_DIR" in source
    assert "add_dll_directory" in source


def test_backend_prefers_cushyserial_message_transport_like_gui():
    backend_file = Path(__file__).resolve().parents[1] / "newBackend" / "main.py"
    source = backend_file.read_text(encoding="utf-8")

    assert "CushySerial" in source
    assert "_run_cushy_parser" in source
    assert "_HAVE_CUSHY_SERIAL" in source


def test_backend_sdk_path_has_tgam_sidecar_battery_fallback():
    backend_file = Path(__file__).resolve().parents[1] / "newBackend" / "main.py"
    source = backend_file.read_text(encoding="utf-8")

    assert "_sdk_sidecar_on_packet" in source
    assert "sdk_sidecar_tgam" in source
