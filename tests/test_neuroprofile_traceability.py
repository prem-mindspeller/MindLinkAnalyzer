"""
Tests for neuroprofile traceability layer (prompt v7 acceptance criteria).

Run from repo root:
    pytest tests/test_neuroprofile_traceability.py -v
"""
import math
import sys
import os

# Ensure newBackend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "newBackend"))

from neuroprofile_traceability import (
    classify_feature_family,
    passes_neuroprofile_gate,
    classify_feature_strength,
    allowed_abilities_for_task,
    blocked_inferences_for_task,
    role_matching_status_for_task,
    resolve_canonical_task,
    canonical_task_number,
    build_neuroprofile_export,
    SESSION_TASK_GATES,
    _infer_session_depth,
    _apply_reliability_cap,
    _compute_session_confidence_cap,
    _gate_transparency,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_feature(
    metric_name: str = "theta_power_raw",
    significant: bool = True,
    d: float = 0.50,
    pct: float = 15.0,
    q: float = 0.008,
    p: float = 0.02,
    delta: float = 5.0,
    emg_guard: int = 0,
    gamma_evaluated: int = 1,
) -> dict:
    return {
        "metric_name":      metric_name,
        "significant_change": significant,
        "effect_size_d":    d,
        "percent_change":   pct,
        "q_value":          q,
        "p_value":          p,
        "delta":            delta,
        "_emg_guard":       emg_guard,
        "_gamma_evaluated": gamma_evaluated,
    }


def _make_per_task(canonical_task_id: str, include_feature: bool = True) -> dict:
    """Build a minimal per_task dict for one task (as returned by /analyze)."""
    analysis = {}
    if include_feature:
        analysis["theta_power_raw"] = _make_feature()
    return {
        canonical_task_id: {
            "analysis": analysis,
            "summary": {
                "feature_selection": {"sig_feature_count": 1},
                "expectation": {"grade": "A"},
            },
            "sample_count": 10,
        }
    }


def _make_existing_analysis(per_task: dict) -> dict:
    """Minimal /analyze-style response wrapper."""
    return {
        "per_task":                    per_task,
        "baseline_kept":               8,
        "baseline_rejected":           2,
        "baseline_rejected_not_worn":  1,
        "baseline_rejected_artifact":  1,
        "baseline_rejected_flatline":  0,
    }


# ─── Test 5–8: classify_feature_family ────────────────────────────────────────

def test_classify_spectral_power():
    assert classify_feature_family("theta_power_raw") == "spectral_power"


def test_classify_band_ratio():
    assert classify_feature_family("alpha_theta_ratio") == "band_ratio"


def test_classify_peak_feature():
    assert classify_feature_family("theta_peak_freq") == "peak_feature"


def test_classify_entropy():
    assert classify_feature_family("theta_entropy") == "entropy_complexity"


def test_classify_relative_power():
    assert classify_feature_family("alpha_relative") == "relative_power"


def test_classify_signal_quality():
    assert classify_feature_family("_emg_guard") == "signal_quality"
    assert classify_feature_family("_gamma_evaluated") == "signal_quality"


def test_classify_total_power():
    assert classify_feature_family("total_power") == "task_summary_stat"


def test_classify_unknown():
    assert classify_feature_family("some_unknown_metric") == "unknown"


# ─── Test 9: language_processing blocked labels ────────────────────────────────

def test_language_processing_blocked_labels():
    blocked = blocked_inferences_for_task("language_processing")
    for label in [
        "Oral Comprehension", "Written Comprehension", "Reading Comprehension",
        "Speaking", "Writing", "Active Listening",
        "Oral Expression", "Written Expression",
    ]:
        assert label in blocked, f"Expected '{label}' in language_processing blocked list"


def test_language_processing_abilities_not_blocked():
    abilities = allowed_abilities_for_task("language_processing", "moderate", convergent=False)
    blocked   = blocked_inferences_for_task("language_processing")
    for a in abilities:
        assert a not in blocked, f"Ability '{a}' appears in blocked list"


# ─── Test 10: motor_imagery blocked labels ────────────────────────────────────

def test_motor_imagery_blocked_labels():
    blocked = blocked_inferences_for_task("motor_imagery")
    for label in ["Manual Dexterity", "Finger Dexterity", "Reaction Time", "Control Precision"]:
        assert label in blocked


# ─── Test 11: visual_colour_processing blocked ───────────────────────────────

def test_visual_colour_processing_blocked():
    blocked = blocked_inferences_for_task("visual_colour_processing")
    assert "Visual Color Discrimination" in blocked


# ─── Test 12: static_emotion_grasp blocked ───────────────────────────────────

def test_static_emotion_grasp_blocked():
    blocked = blocked_inferences_for_task("static_emotion_grasp")
    assert "Social Perceptiveness" in blocked


# ─── Test 13: moderator-only tasks ───────────────────────────────────────────

def test_moderator_only_role_matching_status():
    for task in ("static_emotion_grasp", "body_scan", "visual_colour_processing"):
        assert role_matching_status_for_task(task) == "moderator_only"


def test_moderator_only_abilities_empty():
    for task in ("static_emotion_grasp", "body_scan", "visual_colour_processing"):
        abilities = allowed_abilities_for_task(task, "strong", convergent=True)
        assert abilities == [], f"{task} should have no allowed abilities"


# ─── Test 14–16: session depth inference ─────────────────────────────────────

def test_session_1_depth():
    canonical_ids = [
        resolve_canonical_task(str(n)) or _id
        for n, _id in [(1, "mental_math"), (2, "visual_imagery"),
                       (3, "focused_attention"), (4, "static_emotion_grasp")]
    ]
    depth = _infer_session_depth(canonical_ids)
    assert depth == "session_1"


def test_session_2_depth():
    canonical_ids = [
        "mental_math", "visual_imagery", "focused_attention", "static_emotion_grasp",
        "working_memory", "language_processing", "motor_imagery",
        "cognitive_load_multitasking", "divergent_thinking",
    ]
    assert _infer_session_depth(canonical_ids) == "session_2"


def test_session_3_depth():
    canonical_ids = [
        "mental_math", "visual_imagery", "focused_attention", "static_emotion_grasp",
        "working_memory", "language_processing", "motor_imagery",
        "cognitive_load_multitasking", "divergent_thinking",
        "body_scan", "visual_colour_processing", "semantic_memory_retrieval",
    ]
    assert _infer_session_depth(canonical_ids) == "session_3"


def test_frontend_session_3_task_aliases_resolve_to_canonical_ids():
    assert resolve_canonical_task("body_scan") == "body_scan"
    assert resolve_canonical_task("semantic_memory") == "semantic_memory_retrieval"
    assert resolve_canonical_task("color_perception") == "visual_colour_processing"


# ─── Test 17: single weak feature does not populate ability pool ──────────────

def test_single_weak_feature_no_ability_pool():
    per_task = _make_per_task("working_memory")
    # Override to weak feature (d < 0.50)
    per_task["working_memory"]["analysis"]["theta_power_raw"]["effect_size_d"] = 0.20
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    # Allowed pool should be empty because single weak non-convergent feature
    # (All other features absent → no convergence)
    pool = export["allowed_ability_pool"]
    assert pool == [], f"Expected empty pool for single weak feature, got {pool}"


# ─── Test 18: allowed_ability_pool contains only allowed O*NET labels ─────────

def test_allowed_ability_pool_no_blocked_labels():
    per_task = {}
    per_task.update(_make_per_task("working_memory"))
    per_task.update(_make_per_task("mental_math"))
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    pool = set(export["allowed_ability_pool"])
    blocked_all: set = set()
    for task_entry in export["tasks_detected"]:
        blocked_all.update(blocked_inferences_for_task(task_entry["canonical_task_id"]))
    overlap = pool & blocked_all
    assert not overlap, f"Blocked labels in ability pool: {overlap}"


# ─── Test 19: existing per_task, combined, across_task keys preserved ─────────

def test_analyze_existing_keys_preserved():
    """Verify the /analyze endpoint still returns the original response keys."""
    import importlib
    try:
        import fastapi.testclient
    except ImportError:
        import pytest
        pytest.skip("fastapi[testclient] not installed")

    from fastapi.testclient import TestClient
    import main as _main

    client = TestClient(_main.app)
    # Minimal synthetic data: raw EEG zeroes (will fail QC or produce trivial results)
    # Use 2048 samples (2 windows of 1024) for baseline and task
    baseline_samples = [0.0] * 2048
    task_samples     = [1.0] * 2048

    resp = client.post("/analyze", json={
        "baseline": {"eyes_closed": baseline_samples},
        "tasks":    {"mental_math": task_samples},
    })
    assert resp.status_code == 200
    data = resp.json()
    # If baseline rejected, allow error key
    if "error" in data:
        return
    for key in ("per_task", "combined", "across_task"):
        assert key in data, f"Missing key: {key}"
    assert "neuroprofile_feature_export" in data


# ─── Additional: neuroprofile export keys present ─────────────────────────────

def test_neuroprofile_export_structure():
    per_task = _make_per_task("working_memory")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)

    assert export["feature_report_version"] == "mindspeller_eeg_feature_report_v2"
    assert export["traceability_version"]   == "mindspeller_eeg_feature_traceability_v7"
    # Primary key
    assert "tasks" in export
    # Backward-compat alias
    assert "tasks_detected" in export
    assert export["tasks"] is export["tasks_detected"]
    # New v7.1 top-level keys
    assert "global_reliability" in export
    assert "baseline_qc" in export
    assert "session_confidence_cap" in export
    # Retained keys
    assert "global_quality"  in export
    assert "allowed_ability_pool" in export
    assert "blocked_unsupported_labels" in export


def test_task_entry_has_feature_family():
    per_task = _make_per_task("working_memory")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    for task_entry in export["tasks"]:
        for feat in task_entry["features"]:
            assert "feature_family" in feat
            assert feat["feature_family"] in (
                "spectral_power", "relative_power", "band_ratio",
                "peak_feature", "entropy_complexity", "signal_quality",
                "transition_recovery", "task_summary_stat",
                "behavioral_optional", "unknown",
            )


def test_gamma_guard_feature_rejected():
    """Gamma feature with emg_guard=1 must be rejected by gate."""
    feat = _make_feature(
        metric_name="gamma_power",
        significant=True,
        d=0.90,
        emg_guard=1,
        gamma_evaluated=0,
    )
    assert not passes_neuroprofile_gate(feat)


def test_feature_strength_strong():
    feat = _make_feature(d=0.85, pct=25.0, significant=True, q=0.005)
    feat["metric_name"] = "theta_power_raw"
    feat["grade"] = "A"
    assert classify_feature_strength(feat) == "strong"


def test_feature_strength_moderate():
    feat = _make_feature(d=0.60, pct=15.0, significant=True, q=0.01)
    feat["metric_name"] = "alpha_relative"
    assert classify_feature_strength(feat) == "moderate"


def test_feature_strength_weak():
    feat = _make_feature(d=0.30, pct=12.0, significant=True, q=0.01)
    feat["metric_name"] = "theta_relative"
    assert classify_feature_strength(feat) == "weak"


def test_feature_strength_rejected_low_effect():
    feat = _make_feature(d=0.10, pct=3.0, significant=False, q=0.5, p=0.4)
    feat["metric_name"] = "theta_power"
    assert classify_feature_strength(feat) == "rejected"


# ─── New v7.1: reliability cap tests ────────────────────────────────────────

def test_reliability_cap_medium_caps_strong_to_moderate():
    assert _apply_reliability_cap("strong", "medium") == "moderate"


def test_reliability_cap_low_caps_strong_to_weak():
    assert _apply_reliability_cap("strong", "low") == "weak"


def test_reliability_cap_high_does_not_cap():
    assert _apply_reliability_cap("strong", "high") == "strong"


def test_reliability_cap_never_upgrades_rejected():
    assert _apply_reliability_cap("rejected", "high") == "rejected"


def test_export_medium_reliability_caps_task_confidence():
    """When baseline_kept/total is 0.8 but feat_keep_rate is low -> medium reliability
    -> task confidence must be capped at moderate."""
    per_task = _make_per_task("working_memory")
    # Force medium reliability: give a high baseline yield but poor feature keep
    existing = _make_existing_analysis(per_task)
    existing["baseline_kept"]     = 50
    existing["baseline_rejected"] = 10  # 83% keep rate -> 'high' baseline
    # Signal quality will be low because we have few usable features.
    # Use default test feature which passes gate -> but only 1 feature means
    # frac_usable=1.0 -> 'high' -> reliability=high for these defaults.
    # To force medium: set keep rate to 55%
    existing["baseline_kept"]     = 11
    existing["baseline_rejected"] = 9   # 55% keep rate -> 'medium'
    export = build_neuroprofile_export(per_task, existing)
    assert export["global_reliability"] == "medium"
    for task in export["tasks"]:
        conf = task["task_summary"]["confidence"]
        assert conf != "strong", f"Expected confidence capped below strong, got {conf}"


# ─── New v7.1: session_confidence_cap block tests ────────────────────────────

def test_session_confidence_cap_present():
    per_task = _make_per_task("mental_math")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    cap = export["session_confidence_cap"]
    assert "implicit_trait_max" in cap
    assert "role_recommendation_max" in cap
    assert "reason" in cap


def test_session_1_cap_values():
    """Session 1 cap: both maxes should be at most moderate."""
    per_task = _make_per_task("mental_math")
    existing = _make_existing_analysis(per_task)
    existing["baseline_kept"]     = 20
    existing["baseline_rejected"] = 0  # 100% -> high
    export = build_neuroprofile_export(per_task, existing)
    assert export["protocol_session_depth"] == "session_1"
    cap = export["session_confidence_cap"]
    # Session 1 + high reliability: session cap applies -> moderate
    assert cap["implicit_trait_max"] == "moderate"
    assert cap["role_recommendation_max"] == "moderate"


# ─── New v7.1: statistical gate transparency tests ───────────────────────────

def test_gate_transparency_fdr_basis():
    stats = {"q_value": 0.005, "effect_size_d": 0.80, "percent_change": 20.0}
    gt = _gate_transparency("theta_power_raw", stats)
    assert gt["passes_q_value"] is True
    assert gt["passes_statistical_gate"] is True
    assert gt["significance_basis"] == "fdr_q_value"
    assert gt["interpretation_safety"] == "standard"


def test_gate_transparency_fallback_effect_size():
    stats = {"q_value": 0.5, "effect_size_d": 0.85, "percent_change": 20.0,
             "decision_flags": {"pass_rule": "d"}}
    gt = _gate_transparency("theta_power_raw", stats)
    assert gt["passes_q_value"] is False
    assert gt["passes_statistical_gate"] is False
    assert "fallback" in gt["significance_basis"]
    assert gt["interpretation_safety"] == "use_with_caution"


def test_gate_transparency_none_basis():
    stats = {"q_value": 0.9, "effect_size_d": 0.05, "percent_change": 1.0}
    gt = _gate_transparency("theta_power_raw", stats)
    assert gt["significance_basis"] == "none"
    assert gt["interpretation_safety"] == "do_not_use"


def test_feature_has_gate_transparency_fields():
    per_task = _make_per_task("working_memory")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    for task in export["tasks"]:
        for feat in task["features"]:
            assert "passes_q_value" in feat
            assert "passes_statistical_gate" in feat
            assert "significance_basis" in feat
            assert "interpretation_safety" in feat
            assert "baseline_block_count" in feat
            assert "task_block_count" in feat
            assert "feature_strength_before_cap" in feat


# --- New v7.2: feature_rows tests -------------------------------------------

def test_feature_rows_present():
    per_task = _make_per_task("working_memory")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    assert "feature_rows" in export
    assert isinstance(export["feature_rows"], list)
    assert len(export["feature_rows"]) > 0


def test_feature_rows_have_task_context():
    per_task = _make_per_task("working_memory")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    for row in export["feature_rows"]:
        assert "task_number" in row
        assert "canonical_task_id" in row
        assert "canonical_task_name" in row
        assert "task_role_matching_status" in row
        assert "task_confidence" in row


def test_feature_rows_have_gate_fields():
    per_task = _make_per_task("working_memory")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    for row in export["feature_rows"]:
        assert "passes_neuroprofile_gate" in row
        assert "passes_q_value" in row
        assert "passes_statistical_gate" in row
        assert "significance_basis" in row
        assert "interpretation_safety" in row
        assert "feature_strength" in row
        assert "baseline_block_count" in row
        assert "task_block_count" in row


def test_feature_rows_count_matches_nested():
    """Total feature_rows count must equal sum of features across all tasks."""
    per_task = {}
    per_task.update(_make_per_task("working_memory"))
    per_task.update(_make_per_task("mental_math"))
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    nested_count = sum(len(t["features"]) for t in export["tasks"])
    assert len(export["feature_rows"]) == nested_count


def test_frontend_session_3_raw_task_ids_produce_session_3_export():
    per_task = {}
    per_task.update(_make_per_task("mental_math"))
    per_task.update(_make_per_task("visual_imagery"))
    per_task.update(_make_per_task("focused_attention"))
    per_task.update(_make_per_task("static_emotion_grasp"))
    per_task.update(_make_per_task("working_memory"))
    per_task.update(_make_per_task("language_processing"))
    per_task.update(_make_per_task("motor_imagery"))
    per_task.update(_make_per_task("cognitive_load_multitasking"))
    per_task.update(_make_per_task("divergent_thinking"))
    per_task["body_scan"] = _make_per_task("body_scan")["body_scan"]
    per_task["semantic_memory"] = _make_per_task("semantic_memory")["semantic_memory"]
    per_task["color_perception"] = _make_per_task("color_perception")["color_perception"]

    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)

    assert export["protocol_session_depth"] == "session_3"
    canonical_ids = {task["canonical_task_id"] for task in export["tasks"]}
    assert "body_scan" in canonical_ids
    assert "semantic_memory_retrieval" in canonical_ids
    assert "visual_colour_processing" in canonical_ids
