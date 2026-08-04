import importlib.util
import asyncio
import json
import math
import random
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


def _tgam_feature_windows(n, offset=0.0):
    rows = []
    for i in range(n):
        wobble = float((i % 5) + 1)
        rows.append({
            "delta": 2.0 + wobble,
            "theta": 4.0 + offset + wobble,
            "lowAlpha": 8.0 + wobble,
            "highAlpha": 7.0 + wobble,
            "lowBeta": 3.0 + offset + wobble,
            "highBeta": 2.0 + wobble,
            "lowGamma": 1.0 + wobble * 0.1,
            "midGamma": 1.0 + wobble * 0.1,
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

    visual_rows = backend._samples_to_feature_rows(
        samples, task_id="visuospatial_transformation_orientation"
    )
    attention_rows = backend._samples_to_feature_rows(
        samples, task_id="auditory_target_counting"
    )

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

    attention_rows = backend._samples_to_feature_rows(
        samples, task_id="auditory_target_counting"
    )
    visual_rows = backend._samples_to_feature_rows(
        samples, task_id="visuospatial_transformation_orientation"
    )

    assert attention_rows[0]["beta_alpha_ratio"] > visual_rows[0]["beta_alpha_ratio"] * 2.0


def test_multichannel_windows_follow_sample_rate_not_fixed_sample_count():
    backend = _load_backend()
    samples = _mindrove_alpha_samples(n=800, fs=400)

    rows, qc = backend._multichannel_to_feature_rows(
        samples,
        fs=400,
        task_id="visuospatial_transformation_orientation",
        apply_qc=False,
    )

    assert len(rows) == 1
    assert qc["kept"] == 1


def test_raw_windows_use_two_seconds_with_fifty_percent_overlap():
    backend = _load_backend()
    samples = _mindrove_alpha_samples(n=3000, fs=500)

    rows, qc = backend._multichannel_to_feature_rows(
        samples,
        fs=500,
        task_id="adaptive_numerical_reasoning",
        apply_qc=False,
    )

    assert backend._raw_window_samples(500) == 1000
    assert backend._raw_step_samples(500) == 500
    assert len(rows) == 5
    assert qc["window_seconds"] == 2.0
    assert qc["window_overlap"] == 0.5
    assert qc["step_seconds"] == 1.0
    assert qc["max_contiguous_clean_seconds"] == 6.0


def test_qc_does_not_stitch_separate_clean_feature_runs():
    backend = _load_backend()
    samples = _tgam_feature_windows(10) + [None] + _tgam_feature_windows(10, offset=2.0)

    rows, qc = backend._baseline_feature_rows(samples)

    assert len(rows) == 20
    assert qc["kept"] == 20
    assert qc["max_contiguous_clean_seconds"] == 11.0
    assert qc["meets_contiguous_clean_minimum"] is False


def test_analyze_rejects_task_below_twenty_contiguous_clean_seconds():
    backend = _load_backend()
    backend._N_PERM = 10
    baseline = _tgam_feature_windows(19)
    too_short = _tgam_feature_windows(18, offset=2.0)

    result = backend.analyze({
        "baseline": {"eyes_closed": baseline},
        "tasks": {"adaptive_numerical_reasoning": too_short},
        "behavioral_evidence": {"adaptive_numerical_reasoning": {"status": "passed"}},
        "block_seconds": 2.0,
    })

    task = result["per_task"]["adaptive_numerical_reasoning"]
    assert task["scorable"] is False
    assert "task_has_less_than_20_contiguous_clean_seconds" in task["invalid_reasons"]
    assert task["analysis"] == {}
    assert task["task_qc"]["max_contiguous_clean_seconds"] == 19.0


def test_analyze_accepts_exactly_twenty_contiguous_clean_seconds():
    backend = _load_backend()
    backend._N_PERM = 10
    baseline = _tgam_feature_windows(19)
    task_samples = _tgam_feature_windows(19, offset=2.0)

    result = backend.analyze({
        "baseline": {"eyes_closed": baseline},
        "tasks": {"adaptive_numerical_reasoning": task_samples},
        "task_metadata": {
            "adaptive_numerical_reasoning": {
                "form_id": "nr-a",
                "eye_state": "eyes_closed",
            },
        },
        "behavioral_evidence": {
            "adaptive_numerical_reasoning": {
                "status": "passed",
                "accuracy": 1.0,
            },
        },
        "block_seconds": 2.0,
    })

    task = result["per_task"]["adaptive_numerical_reasoning"]
    assert task["scorable"] is True
    assert task["task_qc"]["max_contiguous_clean_seconds"] == 20.0
    assert task["task_metadata"]["form_id"] == "nr-a"
    assert task["behavioral_evidence"]["accuracy"] == 1.0
    exported = result["neuroprofile_feature_export"]["tasks"][0]
    assert exported["canonical_task_id"] == "adaptive_numerical_reasoning"
    assert exported["behavioral_evidence_status"] == "passed"


def test_analyze_accepts_behavioral_evidence_nested_in_task_metadata():
    backend = _load_backend()
    backend._N_PERM = 10
    samples = _tgam_feature_windows(19)
    evidence = {"status": "passed", "accuracy": 0.8}

    result = backend.analyze({
        "baseline": {"eyes_closed": samples},
        "tasks": {"working_memory_manipulation": _tgam_feature_windows(19, offset=1.0)},
        "task_metadata": {
            "working_memory_manipulation": {
                "eye_state": "eyes_closed",
                "behavioral_evidence": evidence,
            },
        },
        "block_seconds": 2.0,
    })

    task = result["per_task"]["working_memory_manipulation"]
    assert task["behavioral_evidence"] == evidence
    exported = result["neuroprofile_feature_export"]["tasks"][0]
    assert exported["behavioral_evidence_status"] == "passed"


def test_analyze_does_not_relabel_retired_legacy_task_ids():
    backend = _load_backend()
    samples = _tgam_feature_windows(19)

    result = backend.analyze({
        "baseline": {"eyes_closed": samples},
        "tasks": {"mental_math": _tgam_feature_windows(19, offset=1.0)},
    })

    task = result["per_task"]["mental_math"]
    assert task["canonical_task_id"] == "mental_math"
    assert task["scorable"] is False
    assert task["analysis"] == {}
    assert "unrecognized_non_core_task" in task["invalid_reasons"]


def test_visual_task_requires_eyes_open_baseline_without_cross_state_fallback():
    backend = _load_backend()
    baseline = _tgam_feature_windows(19)
    task_samples = _tgam_feature_windows(19, offset=2.0)

    result = backend.analyze({
        "baseline": {"eyes_closed": baseline},
        "tasks": {"rapid_visual_comparison": task_samples},
    })

    task = result["per_task"]["rapid_visual_comparison"]
    assert task["baseline_condition"] == "eyes_open"
    assert task["scorable"] is False
    assert "missing_eyes_open_baseline" in task["invalid_reasons"]
    assert task["analysis"] == {}


def test_explicit_task_eye_state_mismatch_is_not_scorable():
    backend = _load_backend()
    result = backend.analyze({
        "baseline": {"eyes_open": _tgam_feature_windows(19)},
        "tasks": {"rapid_visual_comparison": _tgam_feature_windows(19, offset=2.0)},
        "task_metadata": {"rapid_visual_comparison": {"eye_state": "eyes_closed"}},
    })

    task = result["per_task"]["rapid_visual_comparison"]
    assert task["scorable"] is False
    assert "task_eye_state_mismatch" in task["invalid_reasons"]


def test_analyze_adds_montage_metadata_inside_existing_export():
    backend = _load_backend()
    baseline = _mindrove_regional_samples(
        n=11000,
        frontal_alpha=4.0,
        occipital_alpha=18.0,
        frontal_beta=2.0,
        occipital_beta=2.0,
    )
    task = _mindrove_regional_samples(
        n=11000,
        frontal_alpha=3.0,
        occipital_alpha=32.0,
        frontal_beta=2.0,
        occipital_beta=2.0,
    )

    result = backend.analyze({
        "baseline": {"eyes_open": baseline},
        "tasks": {"visuospatial_transformation_orientation": task},
        "task_metadata": {"visuospatial_transformation_orientation": {"eye_state": "eyes_open"}},
        "behavioral_evidence": {"visuospatial_transformation_orientation": {"status": "passed"}},
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
        task_id="auditory_target_counting",
        return_montage=True,
    )

    assert len(rows) == 1
    assert qc["kept"] == 1
    assert montage["device"] == "MindRove"


def test_analyze_handles_task_with_initial_scalar_fallback_then_mindrove_samples():
    backend = _load_backend()
    baseline = _mindrove_regional_samples(
        n=11000,
        frontal_alpha=4.0,
        occipital_alpha=18.0,
        frontal_beta=2.0,
        occipital_beta=2.0,
    )
    task = [0.0] * 20 + _mindrove_regional_samples(
        n=11000,
        frontal_alpha=3.0,
        occipital_alpha=28.0,
        frontal_beta=2.0,
        occipital_beta=2.0,
    )

    result = backend.analyze({
        "baseline": {"eyes_open": baseline},
        "tasks": {"rule_based_anomaly_detection": task},
        "behavioral_evidence": {"rule_based_anomaly_detection": {"status": "passed"}},
        "block_seconds": 2.0,
    })

    assert "error" not in result
    assert result["per_task"]["rule_based_anomaly_detection"]["sample_count"] > 0
    assert result["per_task"]["rule_based_anomaly_detection"]["montage_evidence"]["device"] == "MindRove"


def test_analyze_uses_protocol_matched_eyes_open_baseline_for_visual_task():
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
        "tasks": {"rapid_visual_comparison": task},
        "task_metadata": {"rapid_visual_comparison": {"eye_state": "eyes_open"}},
        "behavioral_evidence": {"rapid_visual_comparison": {"status": "passed"}},
    })

    task_result = result["per_task"]["rapid_visual_comparison"]
    assert task_result["baseline_condition"] == "eyes_open"
    assert task_result["scorable"] is True
    ess = task_result["summary"]["ess"]
    assert ess["baseline_blocks"] > 1


def test_auditory_target_counting_uses_frontal_montage_profile():
    backend = _load_backend()

    profile = backend._montage_profile_for_task("auditory_target_counting")

    assert profile["primary_region"] == "frontal"
    assert profile["region_weights"]["frontal"] > profile["region_weights"]["occipital"]


def test_revised_task_montage_region_sets_match_protocol():
    backend = _load_backend()

    for task_id in (
        "adaptive_numerical_reasoning",
        "working_memory_manipulation",
        "auditory_target_counting",
        "semantic_induction_category_switching",
        "divergent_ideation",
        "dual_task_rule_switching",
        "speech_in_noise_comprehension",
    ):
        assert backend._montage_profile_for_task(task_id)["primary_region"] == "frontal"

    for task_id in (
        "visuospatial_transformation_orientation",
        "rapid_visual_comparison",
        "pattern_closure_visual_noise",
    ):
        assert backend._montage_profile_for_task(task_id)["primary_region"] == "occipital"

    for task_id in ("rule_based_anomaly_detection", "written_comprehension_synthesis"):
        assert backend._montage_profile_for_task(task_id)["primary_region"] == "frontal_occipital"


def test_visual_task_rejects_window_without_occipital_region():
    backend = _load_backend()
    samples = _mindrove_alpha_samples(n=1000, flat_channels={"o1", "o2"})

    rows, qc = backend._multichannel_to_feature_rows(
        samples,
        task_id="visuospatial_transformation_orientation",
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
        task_id="visuospatial_transformation_orientation",
        apply_qc=False,
    )

    assert qc["kept"] == 1
    row = rows[0]
    assert row["posterior_anterior_alpha"] > 0
    assert row["occipital_alpha_advantage"] > 1
    assert "front_occipital_beta_ratio" in row


def test_primary_region_low_channel_agreement_lowers_confidence_without_breaking_continuity():
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
        task_id="visuospatial_transformation_orientation",
        apply_qc=False,
    )

    assert len(rows) == 1
    assert qc["kept"] == 1
    assert qc["rejected"] == 0
    assert rows[0]["_primary_region_agreement_low"] == 1.0
    assert rows[0]["_primary_region_confidence"] < 1e-12


def test_duplicate_power_variants_are_not_inferred_as_separate_features():
    backend = _load_backend()

    rows = backend._select_inference_feature_names([
        "beta1_power",
        "beta1_power_raw",
        "beta1_peak_amp",
        "beta1_peak_freq",
        "beta1_peak_rel_amp",
        "alpha_power",
        "alpha_power_raw",
        "alpha_relative",
    ])

    assert "beta1_power" in rows
    assert "beta1_power_raw" not in rows
    assert "beta1_peak_amp" not in rows
    assert "beta1_peak_freq" not in rows
    assert "beta1_peak_rel_amp" not in rows
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
        task_id="divergent_ideation",
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
        task_id="visuospatial_transformation_orientation",
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
        task_id="visuospatial_transformation_orientation",
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
            task_id="visuospatial_transformation_orientation",
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
        task_id="auditory_target_counting",
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

    backend._analyze_task_vs_baseline(
        task_rows,
        baseline_rows,
        task_id="auditory_target_counting",
        windows_per_block=1,
    )
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

    backend._sum_p_perm(task_rows, baseline_rows, "auditory_target_counting")
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


def test_transport_segments_are_sanitized_and_never_stitched_for_qc_or_blocks():
    backend = _load_backend()
    metadata = {
        "recording": {
            "transport_segments": [
                {"start_sample_index": -2, "end_sample_index_exclusive": 12},
                {"start_sample_index": 10, "end_sample_index_exclusive": 24},
                {"start_sample_index": 24.5, "end_sample_index_exclusive": 30},
                {"start_sample_index": 99, "end_sample_index_exclusive": 120},
            ],
        },
    }

    rows, qc, _montage = backend._feature_rows_for_transport_segments(
        _tgam_feature_windows(24), metadata
    )

    segmentation = qc["transport_segmentation"]
    assert [(item["start_sample_index"], item["end_sample_index_exclusive"])
            for item in segmentation["segments"]] == [(0, 12), (12, 24)]
    assert segmentation["adjusted_segment_count"] == 2
    assert segmentation["rejected_segment_count"] == 2
    assert qc["max_contiguous_clean_seconds"] == 13.0
    assert qc["meets_contiguous_clean_minimum"] is False
    assert len({row["_transport_segment_id"] for row in rows}) == 2
    assert len(backend._build_blocks(rows, windows_per_block=8)) == 2


def test_malformed_declared_transport_metadata_never_falls_back_to_stitched_array():
    backend = _load_backend()

    rows, qc, _montage = backend._feature_rows_for_transport_segments(
        _tgam_feature_windows(39),
        {"recording": {"transport_segments": "invalid"}},
    )

    segmentation = qc["transport_segmentation"]
    assert rows == []
    assert qc["meets_contiguous_clean_minimum"] is False
    assert segmentation["provided"] is True
    assert segmentation["fallback_to_whole_array"] is False
    assert segmentation["metadata_invalidated_recording"] is True


def test_transport_elapsed_clock_keeps_post_gap_windows_in_their_real_phase():
    backend = _load_backend()
    samples = _tgam_feature_windows(42)
    metadata = {
        "recording": {
            "transport_segments": [
                {
                    "start_sample_index": 0,
                    "end_sample_index_exclusive": 21,
                    "start_elapsed_ms": 0,
                    "end_elapsed_ms": 22000,
                },
                {
                    "start_sample_index": 21,
                    "end_sample_index_exclusive": 42,
                    "start_elapsed_ms": 40000,
                    "end_elapsed_ms": 62000,
                },
            ],
        },
        "phases": [
            {
                "phase_id": "before_gap",
                "start_elapsed_ms": 0,
                "end_elapsed_ms": 22000,
                "planned_duration_ms": 22000,
            },
            {
                "phase_id": "after_gap",
                "start_elapsed_ms": 40000,
                "end_elapsed_ms": 62000,
                "planned_duration_ms": 22000,
            },
        ],
    }

    rows, qc, _montage = backend._feature_rows_for_transport_segments(samples, metadata)
    continuous = backend._continuous_time_series_summary(rows, metadata)

    starts_by_segment = {
        segment_id: min(row["_window_start_seconds"] for row in rows
                        if row["_transport_segment_id"].startswith(segment_id))
        for segment_id in ("0:", "1:")
    }
    assert starts_by_segment == {"0:": 0.0, "1:": 40.0}
    assert qc["meets_contiguous_clean_minimum"] is True
    assert [phase["n_clean_windows"] for phase in continuous["phases"]] == [21, 21]
    assert continuous["phase_comparison"]["status"] == "available"


def test_inference_blocks_never_join_clean_rows_across_a_rejected_window_gap():
    backend = _load_backend()
    starts = [0, 1, 2, 3, 4, 5, 10, 11, 12, 13]
    rows = [
        {
            "alpha_power": float(index),
            "_transport_segment_id": "same-transport-run",
            "_window_start_seconds": float(start),
            "_window_end_seconds": float(start + 2),
        }
        for index, start in enumerate(starts)
    ]

    blocks = backend._build_blocks(rows, windows_per_block=4)

    assert [block["alpha_power"] for block in blocks] == [1.5, 7.5]


def test_nonfinite_four_channel_sample_is_an_acquisition_gap_not_a_feature_row():
    backend = _load_backend()
    good = {"fp1": 1.0, "fp2": 2.0, "o1": 3.0, "o2": 4.0}
    invalid = {"fp1": 1.0, "fp2": float("nan"), "o1": 3.0, "o2": 4.0}
    samples = [good, good, invalid, good]

    assert backend._is_multichannel_raw_sample(invalid) is False
    assert backend._feature_dict_subset(samples) == []
    runs = backend._contiguous_sample_runs(samples, backend._is_multichannel_raw_sample)
    assert [len(run) for run in runs] == [2, 1]


def test_baseline_transport_segments_gate_matched_baseline_contiguity():
    backend = _load_backend()
    backend._N_PERM = 5

    result = backend.analyze({
        "baseline": {"eyes_closed": _tgam_feature_windows(24)},
        "baseline_metadata": {
            "eyes_closed": {
                "transport_segments": [
                    {"start_sample_index": 0, "end_sample_index_exclusive": 12},
                    {"start_sample_index": 12, "end_sample_index_exclusive": 24},
                ],
            },
        },
        "tasks": {
            "adaptive_numerical_reasoning": _tgam_feature_windows(19, offset=2.0),
        },
    })

    task = result["per_task"]["adaptive_numerical_reasoning"]
    assert task["scorable"] is False
    assert "eyes_closed_baseline_has_less_than_20_contiguous_clean_seconds" in task["invalid_reasons"]
    assert task["baseline_qc"]["max_contiguous_clean_seconds"] == 13.0
    assert result["baseline_qc_by_condition"]["eyes_closed"]["transport_segmentation"]["provided"] is True


def test_scorable_task_exports_non_event_locked_continuous_and_phase_descriptives():
    backend = _load_backend()
    backend._N_PERM = 5
    task_samples = _tgam_feature_windows(39, offset=1.0)
    for index, sample in enumerate(task_samples):
        sample["lowAlpha"] += index * 0.2
        sample["highAlpha"] += index * 0.2

    result = backend.analyze({
        "baseline": {"eyes_closed": _tgam_feature_windows(39)},
        "tasks": {"adaptive_numerical_reasoning": task_samples},
        "task_metadata": {
            "adaptive_numerical_reasoning": {
                "eye_state": "eyes_closed",
                "phases": [
                    {
                        "phase_id": "lower_load",
                        "start_elapsed_ms": 0,
                        "end_elapsed_ms": 20000,
                        "planned_duration_ms": 20000,
                    },
                    {
                        "phase_id": "higher_load",
                        "start_elapsed_ms": 20000,
                        "end_elapsed_ms": 40000,
                        "planned_duration_ms": 20000,
                    },
                    {
                        "phase_id": "too_short",
                        "start_elapsed_ms": 40000,
                        "end_elapsed_ms": 50000,
                        "planned_duration_ms": 10000,
                    },
                ],
            },
        },
    })

    task = result["per_task"]["adaptive_numerical_reasoning"]
    continuous = task["continuous_time_series"]
    assert task["scorable"] is True
    assert continuous["n_clean_windows"] == 39
    assert continuous["method"]["event_locked_analysis"] is False
    assert continuous["method"]["erp_analysis"] is False
    assert continuous["method"]["peak_metrics_included"] is False
    assert continuous["features"]["alpha_power"]["std"] > 0
    assert continuous["features"]["alpha_power"]["slope_per_minute"] > 0
    assert not any("peak" in name for name in continuous["selected_features"])
    assert [phase["max_contiguous_clean_seconds"] for phase in continuous["phases"]] == [20.0, 20.0]
    assert continuous["ignored_phases"] == [
        {"phase_id": "too_short", "reason": "planned_duration_below_20_seconds"}
    ]
    assert continuous["phase_comparison"]["status"] == "available"
    assert not any(name.startswith("_") or "peak" in name
                   for name in result["across_task"]["features"])


def test_phase_comparison_is_withheld_when_transport_breaks_phase_clean_run():
    backend = _load_backend()
    backend._N_PERM = 5
    task_samples = _tgam_feature_windows(59, offset=1.0)

    result = backend.analyze({
        "baseline": {"eyes_closed": _tgam_feature_windows(39)},
        "tasks": {"adaptive_numerical_reasoning": task_samples},
        "task_metadata": {
            "adaptive_numerical_reasoning": {
                "eye_state": "eyes_closed",
                "recording": {
                    "transport_segments": [
                        {"start_sample_index": 0, "end_sample_index_exclusive": 15},
                        {"start_sample_index": 15, "end_sample_index_exclusive": 59},
                    ],
                },
                "phases": [
                    {
                        "phase_id": "first",
                        "start_elapsed_ms": 0,
                        "end_elapsed_ms": 30000,
                        "planned_duration_ms": 30000,
                    },
                    {
                        "phase_id": "second",
                        "start_elapsed_ms": 30000,
                        "end_elapsed_ms": 60000,
                        "planned_duration_ms": 30000,
                    },
                ],
            },
        },
    })

    task = result["per_task"]["adaptive_numerical_reasoning"]
    continuous = task["continuous_time_series"]
    assert task["scorable"] is True
    assert continuous["phases"][0]["max_contiguous_clean_seconds"] == 16.0
    assert continuous["phases"][0]["features"] == {}
    assert continuous["phase_comparison"]["status"] == "withheld"
    assert continuous["phase_comparison"]["features"] == {}


def test_dual_task_retains_descriptive_task_two_and_three_reference_contrasts():
    backend = _load_backend()
    backend._N_PERM = 5

    result = backend.analyze({
        "baseline": {"eyes_closed": _tgam_feature_windows(39)},
        "tasks": {
            "auditory_target_counting": _tgam_feature_windows(39, offset=1.0),
            "working_memory_manipulation": _tgam_feature_windows(39, offset=2.0),
            "dual_task_rule_switching": _tgam_feature_windows(39, offset=4.0),
        },
    })

    comparison = result["per_task"]["dual_task_rule_switching"][
        "single_task_reference_comparison"
    ]
    assert comparison["status"] == "available"
    assert set(comparison["comparisons"]) == {
        "working_memory_manipulation",
        "auditory_target_counting",
    }
    assert comparison["behavioral_cost_threshold_available"] is False
    assert all(
        "peak" not in feature_name
        for reference in comparison["comparisons"].values()
        for feature_name in reference["features"]
    )


def _complete_audio_delivery(*, speech_count=0, tone_count=0, noise=False):
    return {
        "expected_speech_count": speech_count,
        "scheduled_speech_count": speech_count,
        "started_speech_count": speech_count,
        "ended_speech_count": speech_count,
        "incomplete_speech_keys": [],
        "expected_tone_count": tone_count,
        "scheduled_tone_count": tone_count,
        "started_tone_count": tone_count,
        "ended_tone_count": tone_count,
        "incomplete_tone_keys": [],
        "background_noise_required": noise,
        "background_noise_started": noise,
        "failed_audio_keys": [],
        "protocol_complete": True,
    }


def test_optimized_contract_requires_consistent_audio_delivery_audit():
    backend = _load_backend()
    backend._N_PERM = 5
    task_id = "adaptive_numerical_reasoning"
    profile, profile_errors = backend.normalize_protocol_profile(None)
    assert profile_errors == []
    profile_ref = backend.protocol_profile_reference(profile, task_id)
    base_payload = {
        "protocol_profile": profile,
        "baseline": {"eyes_closed": _tgam_feature_windows(39)},
        "tasks": {task_id: _tgam_feature_windows(39, offset=1.0)},
    }
    complete_metadata = {
        "contract_version": "mindspeller_continuous_task_result_v1",
        "protocol_valid": True,
        "protocol_profile_ref": profile_ref,
        "recording": {
            "audio_delivery": _complete_audio_delivery(speech_count=1),
        },
    }

    complete = backend.analyze({
        **base_payload,
        "task_metadata": {task_id: complete_metadata},
    })
    assert complete["per_task"][task_id]["scorable"] is True

    missing_profile_ref_metadata = json.loads(json.dumps(complete_metadata))
    del missing_profile_ref_metadata["protocol_profile_ref"]
    missing_profile_ref = backend.analyze({
        **base_payload,
        "task_metadata": {task_id: missing_profile_ref_metadata},
    })
    assert missing_profile_ref["per_task"][task_id]["scorable"] is False
    assert (
        "task_protocol_profile_ref_missing"
        in missing_profile_ref["per_task"][task_id]["invalid_reasons"]
    )

    nested_incomplete = json.loads(json.dumps(complete_metadata))
    nested_incomplete["recording"]["audio_delivery"]["protocol_complete"] = False
    inconsistent = backend.analyze({
        **base_payload,
        "task_metadata": {task_id: nested_incomplete},
    })
    assert inconsistent["per_task"][task_id]["scorable"] is False
    assert "task_audio_delivery_incomplete" in inconsistent["per_task"][task_id]["invalid_reasons"]

    missing_audit = backend.analyze({
        **base_payload,
        "task_metadata": {
            task_id: {
                "contract_version": "mindspeller_continuous_task_result_v1",
                "protocol_valid": True,
                "protocol_profile_ref": profile_ref,
            },
        },
    })
    assert missing_audit["per_task"][task_id]["scorable"] is False
    assert "task_audio_delivery_audit_missing" in missing_audit["per_task"][task_id]["invalid_reasons"]


def test_end_of_block_speech_waiver_is_accepted_but_not_abusable():
    backend = _load_backend()
    task_id = "working_memory_manipulation"

    def audio(started, ended, waived):
        return {
            "contract_version": "mindspeller_continuous_task_result_v1",
            "protocol_valid": True,
            "recording": {"audio_delivery": {
                "expected_speech_count": 9,
                "scheduled_speech_count": 9,
                "started_speech_count": started,
                "ended_speech_count": ended,
                "incomplete_speech_keys": [],
                "expected_tone_count": 0,
                "scheduled_tone_count": 0,
                "started_tone_count": 0,
                "ended_tone_count": 0,
                "incomplete_tone_keys": [],
                "background_noise_required": False,
                "background_noise_started": False,
                "failed_audio_keys": [],
                "speech_end_waived_keys": waived,
                "protocol_complete": True,
            }},
        }

    reasons = backend._task_audio_protocol_invalid_reasons
    # A final-second stimulus that started but could not fire onend before the
    # block ended is disclosed via speech_end_waived_keys and must be accepted.
    assert reasons(task_id, audio(9, 8, ["speech:8"])) == []
    # Full completion still passes.
    assert reasons(task_id, audio(9, 9, [])) == []
    # A missing end event that is NOT disclosed as waived is still rejected.
    assert "task_audio_delivery_incomplete" in reasons(task_id, audio(9, 8, []))
    # The waiver cannot excuse a stimulus that never started (started < expected).
    assert "task_audio_delivery_incomplete" in reasons(task_id, audio(8, 8, ["speech:8"]))


def test_speech_in_noise_contract_requires_running_noise_audit():
    backend = _load_backend()
    backend._N_PERM = 5
    task_id = "speech_in_noise_comprehension"
    profile, profile_errors = backend.normalize_protocol_profile(None)
    assert profile_errors == []
    audio_delivery = _complete_audio_delivery(speech_count=1)

    result = backend.analyze({
        "protocol_profile": profile,
        "baseline": {"eyes_closed": _tgam_feature_windows(39)},
        "tasks": {task_id: _tgam_feature_windows(39, offset=1.0)},
        "task_metadata": {
            task_id: {
                "contract_version": "mindspeller_continuous_task_result_v1",
                "protocol_valid": True,
                "protocol_profile_ref": backend.protocol_profile_reference(
                    profile, task_id
                ),
                "recording": {"audio_delivery": audio_delivery},
            },
        },
    })

    task = result["per_task"][task_id]
    assert task["scorable"] is False
    assert "task_required_noise_audit_missing" in task["invalid_reasons"]


def test_analyze_rejects_malformed_or_wrong_duration_protocol_profile():
    backend = _load_backend()
    profile, errors = backend.normalize_protocol_profile(None)
    assert errors == []
    profile["task_durations_seconds"]["rapid_visual_comparison"] = 40

    result = backend.analyze({
        "protocol_profile": profile,
        "baseline": {"eyes_open": _tgam_feature_windows(39)},
        "tasks": {"rapid_visual_comparison": _tgam_feature_windows(39)},
    })

    assert result["error"] == "Invalid protocol_profile"
    assert result["protocol_profile_validation"]["valid"] is False
    assert any(
        reason.startswith(
            "protocol_profile_task_duration_mismatch:rapid_visual_comparison"
        )
        for reason in result["protocol_profile_validation"]["errors"]
    )


def test_task_resource_versions_and_p47_planned_duration_match_profile():
    backend = _load_backend()
    backend._N_PERM = 5
    task_id = "adaptive_numerical_reasoning"
    profile, errors = backend.normalize_protocol_profile(None)
    assert errors == []
    reference = backend.protocol_profile_reference(profile, task_id)
    reference["task_id"] = reference.pop("canonical_task_id")
    reference["duration_seconds"] = reference.pop(
        "expected_recording_duration_seconds"
    )
    component_versions = reference["component_versions"]
    metadata = {
        "eye_state": "eyes_closed",
        "planned_recording_duration_ms": 60_000,
        "protocol_validation_status": "pilot",
        "stimulus_pack_version": component_versions["stimuli"],
        "audio_pack_version": component_versions["audio"],
        "rubric_set_version": component_versions["rubrics"],
        "threshold_set_version": component_versions["thresholds"],
        "protocol_profile_ref": reference,
    }
    evidence = {
        "status": "passed",
        "protocol_profile_ref": reference,
        "rubric_set_version": component_versions["rubrics"],
        "threshold_set_version": component_versions["thresholds"],
    }
    payload = {
        "protocol_profile": profile,
        "baseline": {"eyes_closed": _tgam_feature_windows(39)},
        "tasks": {task_id: _tgam_feature_windows(39, offset=1.0)},
        "task_metadata": {task_id: metadata},
        "behavioral_evidence": {task_id: evidence},
    }

    result = backend.analyze(payload)

    assert result["per_task"][task_id]["scorable"] is True
    assert result["protocol_profile_validation"] == {
        "valid": True,
        "errors": [],
        "normative_interpretation_allowed": False,
    }
    exported = result["neuroprofile_feature_export"]
    assert exported["protocol_profile"]["profile_id"] == profile["profile_id"]
    assert exported["protocol_profile_validation"][
        "normative_interpretation_allowed"
    ] is False
    exported_task = exported["tasks"][0]
    assert exported_task["protocol_profile"][
        "expected_recording_duration_seconds"
    ] == 60
    assert exported_task["protocol_profile"]["validation_status"] == "pilot"

    wrong_duration = json.loads(json.dumps(payload))
    wrong_duration["task_metadata"][task_id][
        "planned_recording_duration_ms"
    ] = 55_000
    rejected = backend.analyze(wrong_duration)
    assert rejected["per_task"][task_id]["scorable"] is False
    assert (
        "task_planned_recording_duration_profile_mismatch"
        in rejected["per_task"][task_id]["invalid_reasons"]
    )


def test_behavioral_scoring_profile_version_mismatch_is_not_scorable():
    backend = _load_backend()
    backend._N_PERM = 5
    task_id = "rapid_visual_comparison"
    profile, errors = backend.normalize_protocol_profile(None)
    assert errors == []
    reference = backend.protocol_profile_reference(profile, task_id)
    evidence = {
        "status": "passed",
        "protocol_profile_ref": reference,
        "configuration": {
            "profile_id": profile["profile_id"],
            "profile_version": profile["profile_version"],
            "validation_status": profile["validation_status"],
            "rubric_set_id": profile["components"]["rubrics"]["id"],
            "rubric_set_version": profile["components"]["rubrics"]["version"],
            "threshold_set_id": profile["components"]["thresholds"]["id"],
            "threshold_set_version": "different_thresholds_v2",
        },
    }

    result = backend.analyze({
        "protocol_profile": profile,
        "baseline": {"eyes_open": _tgam_feature_windows(39)},
        "tasks": {task_id: _tgam_feature_windows(39, offset=1.0)},
        "task_metadata": {
            task_id: {
                "eye_state": "eyes_open",
                "planned_recording_duration_seconds": 60,
                "protocol_profile_ref": reference,
            }
        },
        "behavioral_evidence": {task_id: evidence},
    })

    task = result["per_task"][task_id]
    assert task["scorable"] is False
    assert (
        "behavioral_scoring_thresholds_version_mismatch"
        in task["invalid_reasons"]
    )


def test_full_component_profile_refs_are_supported_and_checked_fail_closed():
    backend = _load_backend()
    task_id = "written_comprehension_synthesis"
    profile, errors = backend.normalize_protocol_profile(None)
    assert errors == []
    full_reference = {
        "contract_version": profile["contract_version"],
        "profile_id": profile["profile_id"],
        "profile_version": profile["profile_version"],
        "validation_status": profile["validation_status"],
        "components": json.loads(json.dumps(profile["components"])),
        "task_id": task_id,
        "duration_seconds": 90,
    }

    assert backend._protocol_profile_ref_invalid_reasons(
        full_reference,
        profile,
        prefix="test_ref",
        canonical_task_id=task_id,
    ) == []

    full_reference["components"]["rubrics"]["version"] = "other_rubrics_v2"
    reasons = backend._protocol_profile_ref_invalid_reasons(
        full_reference,
        profile,
        prefix="test_ref",
        canonical_task_id=task_id,
    )
    assert "test_ref_rubrics_version_mismatch" in reasons


# ---------------------------------------------------------------------------
# Task_Battery_Optimization.pdf conformance
# ---------------------------------------------------------------------------

# Page 47 durations (Task 1 deliberately shortened to 60s -- see
# neuroprofile_traceability.py TASK_RECORDING_DURATIONS_SECONDS), the
# eyes-open/closed slide, and each task's "After validation, the task can
# provide evidence for" list.
_PDF_TASK_CONTRACT = {
    1: ("adaptive_numerical_reasoning", 60, "eyes_closed", [
        "Mathematical Reasoning", "Number Facility", "Information Ordering",
        "Deductive Reasoning"]),
    2: ("working_memory_manipulation", 60, "eyes_closed", [
        "Memorization", "Information Ordering", "Deductive Reasoning"]),
    3: ("auditory_target_counting", 75, "eyes_closed", [
        "Selective Attention", "Auditory Attention"]),
    4: ("semantic_induction_category_switching", 60, "eyes_closed", [
        "Inductive Reasoning", "Category Flexibility"]),
    5: ("visuospatial_transformation_orientation", 60, "eyes_open", [
        "Visualization", "Spatial Orientation"]),
    6: ("divergent_ideation", 75, "eyes_closed", [
        "Category Flexibility", "Fluency of Ideas", "Originality"]),
    7: ("dual_task_rule_switching", 60, "eyes_closed", [
        "Time Sharing", "Category Flexibility", "Deductive Reasoning",
        "Selective Attention", "Information Ordering"]),
    8: ("rule_based_anomaly_detection", 60, "eyes_open", [
        "Problem Sensitivity", "Deductive Reasoning", "Selective Attention",
        "Information Ordering"]),
    9: ("rapid_visual_comparison", 60, "eyes_open", [
        "Perceptual Speed", "Reaction Time"]),
    10: ("pattern_closure_visual_noise", 60, "eyes_open", [
        "Speed of Closure", "Flexibility of Closure"]),
    11: ("speech_in_noise_comprehension", 60, "eyes_closed", [
        "Oral Comprehension", "Speech Recognition", "Auditory Attention"]),
    12: ("written_comprehension_synthesis", 90, "eyes_open", [
        "Written Comprehension", "Written Expression", "Inductive Reasoning",
        "Information Ordering"]),
}


def test_backend_task_table_matches_optimization_document():
    backend = _load_backend()
    import neuroprofile_traceability as traceability

    for number, (task_id, duration, baseline, abilities) in _PDF_TASK_CONTRACT.items():
        assert traceability.CANONICAL_TASKS[number]["id"] == task_id
        assert traceability.canonical_task_number(task_id) == number
        assert traceability.TASK_RECORDING_DURATIONS_SECONDS[task_id] == duration
        assert backend.task_baseline_condition(task_id) == baseline
        assert backend.theoretical_abilities_for_task(task_id) == abilities


def test_analysis_bands_and_windowing_match_common_methodology():
    backend = _load_backend()

    # "delta 0.5-4 Hz, theta 4-8 Hz, alpha 8-13 Hz, beta 13-30 Hz, gamma 30-45 Hz"
    for band, bounds in {
        "delta": (0.5, 4.0),
        "theta": (4.0, 8.0),
        "alpha": (8.0, 13.0),
        "beta": (13.0, 30.0),
        "gamma": (30.0, 45.0),
    }.items():
        assert backend._RAW_FEATURE_BANDS[band] == bounds

    # "two-second rolling windows with 50% overlap"
    assert backend._RAW_WINDOW_SECONDS == 2.0
    assert backend._RAW_WINDOW_OVERLAP == 0.5
    assert backend._raw_window_samples(500) == 1000
    assert backend._raw_step_samples(500) == 500

    # "at least one contiguous clean interval of 20 seconds"
    assert backend._MIN_CONTIGUOUS_CLEAN_SECONDS == 20.0


def test_band_power_localizes_a_known_sinusoid_to_its_own_band():
    backend = _load_backend()
    fs = 500
    neural_bands = ["delta", "theta", "alpha", "beta"]

    for frequency, expected in ((2.0, "delta"), (6.0, "theta"), (10.0, "alpha"), (20.0, "beta")):
        window = [
            50.0 * math.sin(2.0 * math.pi * frequency * (i / fs))
            for i in range(2 * fs)
        ]
        features = backend._raw_window_to_features(window, fs)
        powers = {band: features[f"{band}_power"] for band in neural_bands}
        assert max(powers, key=powers.get) == expected, (frequency, powers)
        assert abs(features[f"{expected}_peak_freq"] - frequency) <= 0.5


def _steady_montage_samples(n, fs=500, alpha=20.0, seed=1):
    rng = random.Random(seed)
    samples = []
    for i in range(n):
        t = i / fs
        a = alpha * math.sin(2.0 * math.pi * 10.0 * t)
        b = 6.0 * math.sin(2.0 * math.pi * 20.0 * t)
        samples.append({
            "fp1": a + b + rng.gauss(0, 2),
            "fp2": 1.04 * a + 0.96 * b + rng.gauss(0, 2),
            "o1": 1.10 * a + b + rng.gauss(0, 2),
            "o2": 1.05 * a + 0.98 * b + rng.gauss(0, 2),
        })
    return samples


def test_pooled_combined_baseline_counts_each_condition_once():
    """One session baseline must not be restated once per task that matches it.

    Two eyes-closed tasks share a single eyes-closed recording, so the pooled
    comparison must see that baseline's windows once, not twice.
    """
    backend = _load_backend()
    calls = []
    original = backend._analyze_task_vs_baseline

    def spy(task_rows, baseline_rows, *args, **kwargs):
        calls.append((len(task_rows), len(baseline_rows)))
        return original(task_rows, baseline_rows, *args, **kwargs)

    backend._analyze_task_vs_baseline = spy
    try:
        result = backend.analyze({
            "baseline": {
                "eyes_closed": _steady_montage_samples(15000, alpha=24.0, seed=7),
                "eyes_open": [],
            },
            "tasks": {
                "semantic_induction_category_switching": _steady_montage_samples(
                    15000, alpha=11.0, seed=13),
                "adaptive_numerical_reasoning": _steady_montage_samples(
                    15000, alpha=13.0, seed=17),
            },
        })
    finally:
        backend._analyze_task_vs_baseline = original

    per_task = result["per_task"]
    assert all(entry["scorable"] for entry in per_task.values()), {
        task_id: entry["invalid_reasons"] for task_id, entry in per_task.items()
    }

    per_task_calls = calls[:-1]
    combined_task_rows, combined_baseline_rows = calls[-1]
    single_baseline_rows = per_task_calls[0][1]

    assert len(per_task_calls) == 2
    assert all(baseline == single_baseline_rows for _, baseline in per_task_calls)
    # Task rows accumulate across tasks; the shared baseline must not.
    assert combined_task_rows == sum(task for task, _ in per_task_calls)
    assert combined_baseline_rows == single_baseline_rows


def test_pooled_combined_baseline_keeps_both_eye_states_once_each():
    """A mixed session pools eyes-closed and eyes-open baselines exactly once each."""
    backend = _load_backend()
    calls = []
    original = backend._analyze_task_vs_baseline

    def spy(task_rows, baseline_rows, *args, **kwargs):
        calls.append((kwargs.get("task_id") or (args[0] if args else None), len(baseline_rows)))
        return original(task_rows, baseline_rows, *args, **kwargs)

    backend._analyze_task_vs_baseline = spy
    try:
        result = backend.analyze({
            "baseline": {
                "eyes_closed": _steady_montage_samples(15000, alpha=24.0, seed=7),
                # The visual task is occipital-primary, so its matched baseline
                # needs a posterior-dominant signal to survive montage QC.
                "eyes_open": _mindrove_regional_samples(
                    n=15000, frontal_alpha=5.0, occipital_alpha=18.0,
                    frontal_beta=4.0, occipital_beta=2.0),
            },
            "tasks": {
                "semantic_induction_category_switching": _steady_montage_samples(
                    15000, alpha=11.0, seed=13),
                "adaptive_numerical_reasoning": _steady_montage_samples(
                    15000, alpha=13.0, seed=17),
                "rapid_visual_comparison": _mindrove_regional_samples(
                    n=15000, frontal_alpha=4.0, occipital_alpha=16.0,
                    frontal_beta=9.0, occipital_beta=2.0),
            },
            "task_metadata": {"rapid_visual_comparison": {"eye_state": "eyes_open"}},
        })
    finally:
        backend._analyze_task_vs_baseline = original

    per_task = result["per_task"]
    assert all(entry["scorable"] for entry in per_task.values()), {
        task_id: entry["invalid_reasons"] for task_id, entry in per_task.items()
    }
    assert per_task["rapid_visual_comparison"]["baseline_condition"] == "eyes_open"

    by_task = {task_id: rows for task_id, rows in calls[:-1]}
    combined_baseline_rows = calls[-1][1]
    eyes_closed_rows = by_task["adaptive_numerical_reasoning"]
    eyes_open_rows = by_task["rapid_visual_comparison"]

    assert eyes_closed_rows > 0 and eyes_open_rows > 0
    assert combined_baseline_rows == eyes_closed_rows + eyes_open_rows


def test_mindrove_signal_debouncer_is_quick_to_good_and_slow_to_bad():
    backend = _load_backend()
    deb = backend._MindRoveSignalDebouncer(good_required=1, bad_required=2)

    # One good window is enough to report good (0).
    assert deb.update({"good": True, "poor_signal": 0})["poor_signal"] == 0
    # A single noisy window is held off (needs 2 consecutive) — stays good.
    assert deb.update({"good": False, "poor_signal": 80})["poor_signal"] == 0
    # A second consecutive noisy window flips to noisy (80).
    assert deb.update({"good": False, "poor_signal": 80})["poor_signal"] == 80
    # Recovery is immediate on the next good window.
    assert deb.update({"good": True, "poor_signal": 0})["poor_signal"] == 0


def test_live_signal_window_is_longer_than_analysis_window():
    backend = _load_backend()
    assert backend._live_signal_window_samples(500) > backend._raw_window_samples(500)
    assert backend._live_signal_window_samples(500) == round(backend._LIVE_SIGNAL_WINDOW_SECONDS * 500)
