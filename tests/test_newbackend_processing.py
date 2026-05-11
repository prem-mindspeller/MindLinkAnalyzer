import importlib.util
import math
import sys
import types
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
    spec = importlib.util.spec_from_file_location("newbackend_main_under_test", backend_dir / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sine_window(freq=10.0, samples=1024, fs=512, amp=80.0):
    return [amp * math.sin(2.0 * math.pi * freq * i / fs) for i in range(samples)]


def test_raw_samples_convert_to_direct_two_second_feature_rows():
    backend = _load_backend()

    rows = backend._maybe_convert_raw(_sine_window())

    assert backend._RAW_WINDOW == 1024
    assert backend._WINDOW_DURATION_SEC == 2.0
    assert backend._WINDOWS_PER_BLOCK == 4
    assert len(rows) == 1
    assert "alpha_power" in rows[0]
    assert "lowAlpha" not in rows[0]


def test_analyze_rejects_flatline_ec_window_and_reports_real_qc_counts():
    backend = _load_backend()
    flatline = [0.0] * backend._RAW_WINDOW
    valid = _sine_window()
    task = _sine_window(freq=14.0) * 4

    result = backend.analyze({
        "baseline": {"eyes_closed": flatline + valid * 4},
        "tasks": {"attention_focus": task},
    })

    assert "error" not in result
    assert result["baseline_rejected"] == 1
    assert result["baseline_rejected_flatline"] == 1
    assert result["baseline_kept"] == 4


def test_across_task_results_include_holm_correction_block():
    backend = _load_backend()
    baseline = _sine_window(freq=10.0) * 4
    task_a = _sine_window(freq=14.0) * 4
    task_b = _sine_window(freq=6.0) * 4

    result = backend.analyze({
        "baseline": {"eyes_closed": baseline},
        "tasks": {"attention_focus": task_a, "relaxation": task_b},
    })

    correction = result["across_task"].get("cross_task_correction")
    assert correction is not None
    assert correction["method"] == "holm_bonferroni"
    assert correction["alpha"] == backend._ALPHA
    assert set(correction["tasks"]) == {"attention_focus", "relaxation"}
