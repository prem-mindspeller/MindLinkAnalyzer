import importlib.util
import asyncio
import json
import math
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


def _mindrove_alpha_samples(n=1000, fs=500, flat_channels=None):
    flat_channels = set(flat_channels or [])
    samples = []
    for i in range(n):
        t = i / fs
        samples.append({
            "fp1": 0.0 if "fp1" in flat_channels else 18.0 * math.sin(2.0 * math.pi * 10.0 * t),
            "fp2": 0.0 if "fp2" in flat_channels else 20.0 * math.sin(2.0 * math.pi * 10.0 * t),
            "o1": 0.0 if "o1" in flat_channels else 22.0 * math.sin(2.0 * math.pi * 10.0 * t),
            "o2": 0.0 if "o2" in flat_channels else 24.0 * math.sin(2.0 * math.pi * 10.0 * t),
        })
    return samples


def _mindrove_regional_samples(
    n=1000,
    fs=500,
    frontal_alpha=5.0,
    occipital_alpha=5.0,
    frontal_beta=5.0,
    occipital_beta=5.0,
):
    samples = []
    for i in range(n):
        t = i / fs
        f_alpha = frontal_alpha * math.sin(2.0 * math.pi * 10.0 * t)
        o_alpha = occipital_alpha * math.sin(2.0 * math.pi * 10.0 * t)
        f_beta = frontal_beta * math.sin(2.0 * math.pi * 20.0 * t)
        o_beta = occipital_beta * math.sin(2.0 * math.pi * 20.0 * t)
        samples.append({
            "fp1": f_alpha + f_beta,
            "fp2": 1.05 * f_alpha + 0.95 * f_beta,
            "o1": o_alpha + o_beta,
            "o2": 1.05 * o_alpha + 0.95 * o_beta,
        })
    return samples


def _mindrove_samples_with_frontal_dropout_after_first_window(n=30000, fs=500):
    samples = []
    for i in range(n):
        t = i / fs
        frontal_ok = i < int(2 * fs)
        f_alpha = 5.0 * math.sin(2.0 * math.pi * 10.0 * t) if frontal_ok else 0.0
        f_beta = 4.0 * math.sin(2.0 * math.pi * 20.0 * t) if frontal_ok else 0.0
        o_alpha = 18.0 * math.sin(2.0 * math.pi * 10.0 * t)
        o_beta = 2.0 * math.sin(2.0 * math.pi * 20.0 * t)
        samples.append({
            "fp1": f_alpha + f_beta,
            "fp2": 1.03 * f_alpha + 0.97 * f_beta,
            "o1": o_alpha + o_beta,
            "o2": 1.02 * o_alpha + 0.98 * o_beta,
        })
    return samples


def test_mindrove_four_channel_samples_use_existing_feature_schema():
    backend = _load_backend()

    rows = backend._samples_to_feature_rows(_mindrove_alpha_samples())

    assert len(rows) == 1
    row = rows[0]
    for key in ("alpha_power", "alpha_relative", "beta_alpha_ratio", "total_power"):
        assert key in row
        assert math.isfinite(row[key])
    assert row["alpha_power"] > 0
    assert not any(key.startswith(("fp1_", "fp2_", "o1_", "o2_")) for key in row)


def test_mindrove_connect_is_idempotent_while_reader_is_active(monkeypatch):
    backend = _load_backend()

    starts = []
    joins = []

    class FakeThread:
        def __init__(self, target, args=(), daemon=None, name=None):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name
            self.started = False

        def start(self):
            self.started = True
            starts.append((self.target, self.args))

        def is_alive(self):
            return self.started

        def join(self, timeout=None):
            joins.append(timeout)

    monkeypatch.setattr(backend.threading, "Thread", FakeThread)
    backend._reader_thread = None
    backend._status = "disconnected"
    backend._stop_event.clear()

    first = backend.connect({"port": "mindrove://wifi"})
    second = backend.connect({"port": "mindrove://wifi"})

    assert first["success"] is True
    assert second["success"] is True
    assert second["alreadyConnected"] is True
    assert len(starts) == 1
    assert joins == []


def test_websocket_keepalive_sends_heartbeat_without_device_disconnect():
    backend = _load_backend()

    class FakeWebSocket:
        def __init__(self):
            self.sent = []
            self.sent_event = asyncio.Event()

        async def receive_text(self):
            await asyncio.sleep(1)

        async def send_text(self, text):
            self.sent.append(json.loads(text))
            self.sent_event.set()

    async def run_check():
        ws = FakeWebSocket()
        task = asyncio.create_task(
            backend._websocket_keepalive(ws, interval_seconds=0.001)
        )
        try:
            await asyncio.wait_for(ws.sent_event.wait(), timeout=1)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return ws.sent

    sent = asyncio.run(run_check())

    assert sent[0]["type"] == "heartbeat"
    assert "ts" in sent[0]
    assert backend._status == "disconnected"


def test_mindrove_contact_state_matches_terminal_variance_gate():
    backend = _load_backend()
    worn_samples = _mindrove_alpha_samples(n=80)
    not_worn_samples = [
        {"fp1": 100.0, "fp2": -50.0, "o1": 0.0, "o2": 0.0}
        for _ in range(80)
    ]

    worn = backend._mindrove_contact_state_from_samples(worn_samples)
    not_worn = backend._mindrove_contact_state_from_samples(not_worn_samples)

    assert worn["worn"] is True
    assert worn["reason"] == "eeg_variance_fallback"
    assert worn["poor_signal"] == 0
    assert not_worn["worn"] is False
    assert not_worn["reason"] == "low_variance"
    assert not_worn["poor_signal"] == 200


def test_mindrove_contact_debouncer_blocks_single_false_good_window():
    backend = _load_backend()
    smoother = backend._MindRoveContactDebouncer(good_required=3, bad_required=1)

    states = [
        {"worn": False, "poor_signal": 200, "reason": "low_variance", "quality": 0.0},
        {"worn": True, "poor_signal": 0, "reason": "eeg_variance_fallback", "quality": 1.0},
        {"worn": False, "poor_signal": 200, "reason": "low_variance", "quality": 0.0},
    ]

    outputs = [smoother.update(state)["poor_signal"] for state in states]

    assert outputs == [200, 200, 200]


def test_mindrove_baseline_qc_rejects_all_flat_channels_as_flatline():
    backend = _load_backend()

    rows, qc = backend._baseline_feature_rows(_mindrove_alpha_samples(flat_channels={"fp1", "fp2", "o1", "o2"}))

    assert rows == []
    assert qc["kept"] == 0
    assert qc["rejected"] == 1
    assert qc["flatline"] == 1


def test_mindrove_baseline_qc_keeps_window_when_one_channel_is_flat():
    backend = _load_backend()

    rows, qc = backend._baseline_feature_rows(_mindrove_alpha_samples(flat_channels={"fp2"}))

    assert len(rows) == 1
    assert qc["kept"] == 1
    assert qc["rejected"] == 0
    assert rows[0]["alpha_power"] > 0


def test_visual_tasks_emphasize_occipital_alpha_without_changing_feature_keys():
    backend = _load_backend()
    samples = _mindrove_regional_samples(
        frontal_alpha=2.0,
        occipital_alpha=30.0,
        frontal_beta=1.0,
        occipital_beta=1.0,
    )

    visual_rows = backend._samples_to_feature_rows(samples, task_id="visual_imagery")
    attention_rows = backend._samples_to_feature_rows(samples, task_id="attention_focus")

    assert len(visual_rows) == 1
    assert len(attention_rows) == 1
    assert visual_rows[0]["alpha_power"] > attention_rows[0]["alpha_power"] * 2.0
    assert set(visual_rows[0].keys()) == set(attention_rows[0].keys())
    assert not any(
        key.startswith(("fp1_", "fp2_", "o1_", "o2_"))
        for key in visual_rows[0]
    )
    assert "posterior_anterior_alpha" in visual_rows[0]
    assert "occipital_alpha_advantage" in visual_rows[0]
    assert "frontal_attention_advantage" in visual_rows[0]


def test_attention_tasks_emphasize_frontal_beta_alpha_ratio():
    backend = _load_backend()
    samples = _mindrove_regional_samples(
        frontal_alpha=2.0,
        occipital_alpha=35.0,
        frontal_beta=24.0,
        occipital_beta=1.0,
    )

    attention_rows = backend._samples_to_feature_rows(samples, task_id="attention_focus")
    visual_rows = backend._samples_to_feature_rows(samples, task_id="visual_imagery")

    assert attention_rows[0]["beta_alpha_ratio"] > visual_rows[0]["beta_alpha_ratio"] * 2.0


def test_multichannel_windows_follow_sample_rate_not_fixed_sample_count():
    backend = _load_backend()
    samples = _mindrove_alpha_samples(n=800, fs=400)

    rows, qc = backend._multichannel_to_feature_rows(
        samples,
        fs=400,
        task_id="visual_imagery",
        apply_qc=False,
    )

    assert len(rows) == 1
    assert qc["kept"] == 1


def test_analyze_adds_montage_metadata_inside_existing_export():
    backend = _load_backend()
    baseline = _mindrove_regional_samples(
        n=4000,
        frontal_alpha=4.0,
        occipital_alpha=18.0,
        frontal_beta=2.0,
        occipital_beta=2.0,
    )
    task = _mindrove_regional_samples(
        n=4000,
        frontal_alpha=3.0,
        occipital_alpha=32.0,
        frontal_beta=2.0,
        occipital_beta=2.0,
    )

    result = backend.analyze({
        "baseline": {"eyes_closed": baseline},
        "tasks": {"visual_imagery": task},
        "block_seconds": 2.0,
    })

    export = result["neuroprofile_feature_export"]
    assert export["montage"]["device"] == "MindRove"
    assert export["montage"]["channels"] == ["Fp1", "Fp2", "O1", "O2"]
    assert export["headset_scope"] == "MindRove sparse montage: Fp1/Fp2 frontal + O1/O2 occipital"
    assert export["channel_quality"]["Fp1"]["seen_windows"] > 0
    assert export["channel_quality"]["O1"]["seen_windows"] > 0
    assert export["regional_reliability"]["frontal"] in {"medium", "high"}
    assert export["regional_reliability"]["occipital"] in {"medium", "high"}
    assert export["spatial_evidence"]["corr_Fp1_Fp2"] is not None
    assert export["multi_channel_gain"]["used_occipital_evidence"] is True
    assert export["multi_channel_gain"]["fallback_to_single_channel"] is False
    assert "per_task" in result
    assert "combined" in result
    assert "across_task" in result


def test_mixed_scalar_then_mindrove_samples_use_montage_subset():
    backend = _load_backend()
    samples = [0.0] * 20 + _mindrove_regional_samples(n=1000)

    rows = backend._samples_to_feature_rows(samples, task_id="emotion_face")

    assert len(rows) == 1
    assert rows[0]["alpha_power"] > 0
    assert "posterior_anterior_alpha" in rows[0]


def test_mixed_scalar_then_mindrove_baseline_uses_montage_subset():
    backend = _load_backend()
    samples = [0.0] * 20 + _mindrove_regional_samples(n=1000)

    rows, qc, montage = backend._baseline_feature_rows(
        samples,
        task_id="attention_focus",
        return_montage=True,
    )

    assert len(rows) == 1
    assert qc["kept"] == 1
    assert montage["device"] == "MindRove"


def test_analyze_handles_task_with_initial_scalar_fallback_then_mindrove_samples():
    backend = _load_backend()
    baseline = _mindrove_regional_samples(
        n=4000,
        frontal_alpha=4.0,
        occipital_alpha=18.0,
        frontal_beta=2.0,
        occipital_beta=2.0,
    )
    task = [0.0] * 20 + _mindrove_regional_samples(
        n=4000,
        frontal_alpha=3.0,
        occipital_alpha=28.0,
        frontal_beta=2.0,
        occipital_beta=2.0,
    )

    result = backend.analyze({
        "baseline": {"eyes_closed": baseline},
        "tasks": {"emotion_face": task},
        "block_seconds": 2.0,
    })

    assert "error" not in result
    assert result["per_task"]["emotion_face"]["sample_count"] > 0
    assert result["per_task"]["emotion_face"]["montage_evidence"]["device"] == "MindRove"


def test_analyze_uses_eyes_open_baseline_when_task_region_ec_support_is_low():
    backend = _load_backend()
    ec_baseline = _mindrove_samples_with_frontal_dropout_after_first_window(n=30000)
    eo_baseline = _mindrove_regional_samples(
        n=30000,
        frontal_alpha=5.0,
        occipital_alpha=18.0,
        frontal_beta=4.0,
        occipital_beta=2.0,
    )
    task = _mindrove_regional_samples(
        n=26000,
        frontal_alpha=4.0,
        occipital_alpha=16.0,
        frontal_beta=9.0,
        occipital_beta=2.0,
    )

    result = backend.analyze({
        "baseline": {
            "eyes_closed": ec_baseline,
            "eyes_open": eo_baseline,
        },
        "tasks": {"attention_focus": task},
    })

    ess = result["per_task"]["attention_focus"]["summary"]["ess"]
    assert ess["baseline_blocks"] > 1


def test_focused_attention_uses_frontal_montage_profile():
    backend = _load_backend()

    profile = backend._montage_profile_for_task("focused_attention")

    assert profile["primary_region"] == "frontal"
    assert profile["region_weights"]["frontal"] > profile["region_weights"]["occipital"]


def test_visual_task_rejects_window_without_occipital_region():
    backend = _load_backend()
    samples = _mindrove_alpha_samples(n=1000, flat_channels={"o1", "o2"})

    rows, qc = backend._multichannel_to_feature_rows(
        samples,
        task_id="visual_imagery",
        apply_qc=True,
    )

    assert rows == []
    assert qc["rejected"] == 1
    assert qc["artifact"] == 1


def test_multichannel_features_include_real_spatial_contrast_metrics():
    backend = _load_backend()
    samples = _mindrove_regional_samples(
        n=1000,
        frontal_alpha=2.0,
        occipital_alpha=20.0,
        frontal_beta=8.0,
        occipital_beta=2.0,
    )

    rows, qc = backend._multichannel_to_feature_rows(
        samples,
        task_id="visual_imagery",
        apply_qc=False,
    )

    assert qc["kept"] == 1
    row = rows[0]
    assert row["posterior_anterior_alpha"] > 0
    assert row["occipital_alpha_advantage"] > 1
    assert "front_occipital_beta_ratio" in row


def test_primary_region_low_channel_agreement_rejects_task_window():
    backend = _load_backend()
    samples = []
    for i in range(1000):
        t = i / 500
        frontal = math.sin(2.0 * math.pi * 10.0 * t)
        occ = math.sin(2.0 * math.pi * 10.0 * t)
        samples.append({
            "fp1": frontal,
            "fp2": frontal,
            "o1": occ,
            "o2": -occ,
        })

    rows, qc = backend._multichannel_to_feature_rows(
        samples,
        task_id="visual_imagery",
        apply_qc=False,
    )

    assert rows == []
    assert qc["rejected"] == 1


def test_duplicate_power_variants_are_not_inferred_as_separate_features():
    backend = _load_backend()

    rows = backend._select_inference_feature_names([
        "beta1_power",
        "beta1_power_raw",
        "beta1_peak_amp",
        "alpha_power",
        "alpha_power_raw",
        "alpha_relative",
    ])

    assert "beta1_power" in rows
    assert "beta1_power_raw" not in rows
    assert "beta1_peak_amp" not in rows
    assert "alpha_power" in rows
    assert "alpha_power_raw" not in rows
    assert "alpha_relative" in rows


def test_effect_size_only_changes_do_not_set_significant_change():
    backend = _load_backend()
    task_rows = [{"alpha_power": value, "_gamma_evaluated": 1.0} for value in [3.0, 4.0, 5.0, 6.0]]
    baseline_rows = [{"alpha_power": value, "_gamma_evaluated": 1.0} for value in [1.0, 2.0, 3.0, 4.0]]

    _summary, analysis = backend._analyze_task_vs_baseline(
        task_rows,
        baseline_rows,
        task_id="visual_imagery",
        windows_per_block=1,
    )

    assert analysis["alpha_power"]["effect_size_d"] > 0.3
    assert analysis["alpha_power"]["decision_flags"]["effect_pass"] is True
    assert analysis["alpha_power"]["decision_flags"]["q_pass"] is False
    assert analysis["alpha_power"]["decision_flags"]["pass_rule"] is None
    assert analysis["alpha_power"]["significant_change"] is False


def test_percent_change_is_bounded_for_near_zero_absolute_power_baseline():
    backend = _load_backend()
    task_rows = [
        {"total_power": value, "_gamma_evaluated": 1.0}
        for value in [10.0, 11.0, 9.5, 10.5]
    ]
    baseline_rows = [
        {"total_power": value, "_gamma_evaluated": 1.0}
        for value in [0.05, 0.04, 0.06, 0.05]
    ]

    _summary, analysis = backend._analyze_task_vs_baseline(
        task_rows,
        baseline_rows,
        task_id="visual_imagery",
        windows_per_block=1,
    )

    assert abs(analysis["total_power"]["percent_change"]) <= 200.0
    assert analysis["total_power"]["decision_flags"]["percent_change_method"] == "symmetric"


def test_sparse_montage_gamma_cannot_be_the_only_supporting_evidence():
    backend = _load_backend()
    task_rows = [
        {
            "gamma_power": gamma,
            "alpha_power": alpha,
            "_gamma_evaluated": 1.0,
            "_primary_channel_agreement": 0.9,
            "_primary_region_confidence": 0.95,
        }
        for gamma, alpha in zip(
            [10.0, 10.3, 10.1, 10.4, 10.2, 10.5],
            [1.0, 1.1, 0.9, 1.05, 0.95, 1.0],
        )
    ]
    baseline_rows = [
        {
            "gamma_power": gamma,
            "alpha_power": alpha,
            "_gamma_evaluated": 1.0,
            "_primary_channel_agreement": 0.9,
            "_primary_region_confidence": 0.95,
        }
        for gamma, alpha in zip(
            [1.0, 1.2, 1.1, 1.0, 1.3, 1.2],
            [1.0, 1.1, 0.9, 1.05, 0.95, 1.0],
        )
    ]

    _summary, analysis = backend._analyze_task_vs_baseline(
        task_rows,
        baseline_rows,
        task_id="visual_imagery",
        windows_per_block=1,
    )

    assert analysis["gamma_power"]["decision_flags"]["q_pass"] is True
    assert analysis["gamma_power"]["decision_flags"]["gamma_sparse_montage_guard"]["non_gamma_support"] is False
    assert analysis["gamma_power"]["significant_change"] is False
    assert analysis["alpha_power"]["significant_change"] is False


def test_single_block_analysis_does_not_emit_numpy_corrcoef_warnings():
    backend = _load_backend()
    task_rows = [{"alpha_power": 2.0, "beta_power": 1.0, "_gamma_evaluated": 1.0}]
    baseline_rows = [{"alpha_power": 1.0, "beta_power": 1.0, "_gamma_evaluated": 1.0}]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        backend._analyze_task_vs_baseline(
            task_rows,
            baseline_rows,
            task_id="visual_imagery",
            windows_per_block=1,
        )

    messages = [str(item.message) for item in caught]
    assert not any("Degrees of freedom <= 0" in message for message in messages)
    assert not any("divide by zero encountered in divide" in message for message in messages)
    assert not any("invalid value encountered in multiply" in message for message in messages)


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
