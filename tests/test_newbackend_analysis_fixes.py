import importlib.util
import json
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
