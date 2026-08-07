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
    PROTOCOL_PROFILE_COMPONENTS,
    PROTOCOL_PROFILE_CONTRACT_VERSION,
    TASK_RECORDING_DURATIONS_SECONDS,
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
    CANONICAL_TASKS,
    TASK_BASELINE_CONDITIONS,
    normalize_behavioral_status,
    theoretical_abilities_for_task,
    candidate_protocol_profile,
    normalize_protocol_profile,
    protocol_profile_reference,
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
            "scorable": True,
            "behavioral_evidence": {"status": "passed"},
            "task_metadata": {},
            "task_qc": {"meets_contiguous_clean_minimum": True},
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


def _make_analysis_feature(
    metric_name: str,
    *,
    q: float = 0.5,
    d: float = 0.60,
    pct: float = 12.0,
    delta: float = 1.0,
    direction_ok: bool = True,
    p_pass: bool = False,
    effect_pass: bool = True,
    percent_pass: bool = True,
    significant: bool = False,
) -> dict:
    """Build one /analyze-style feature stats dict with decision flags."""
    return {
        "p_value": 0.04,
        "q_value": q,
        "effect_size_d": d,
        "percent_change": pct,
        "delta": delta,
        "task_mean": 2.0,
        "baseline_mean": 1.0,
        "n_blocks_task": 6,
        "n_blocks_baseline": 6,
        "significant_change": significant,
        "decision_flags": {
            "p_one_sided": 0.04,
            "p_pass": p_pass,
            "q_pass": q <= 0.0119377,
            "effect_pass": effect_pass,
            "percent_pass": percent_pass,
            "expected_direction": "up",
            "direction_ok": direction_ok,
            "pass_rule": "q" if q <= 0.0119377 else None,
        },
    }


# ─── Versioned candidate/pilot protocol profile ─────────────────────────────

def test_candidate_protocol_profile_uses_normative_p47_recording_durations():
    profile = candidate_protocol_profile()
    normalized, errors = normalize_protocol_profile(profile)

    assert errors == []
    assert normalized["contract_version"] == PROTOCOL_PROFILE_CONTRACT_VERSION
    assert normalized["validation_status"] == "pilot"
    assert normalized["normative_interpretation_allowed"] is False
    assert normalized["interpretation_scope"] == "candidate_or_pilot_only"
    assert normalized["task_durations_seconds"] == {
        "adaptive_numerical_reasoning": 90,
        "working_memory_manipulation": 90,
        "auditory_target_counting": 120,
        "semantic_induction_category_switching": 90,
        "visuospatial_transformation_orientation": 90,
        "divergent_ideation": 120,
        "dual_task_rule_switching": 120,
        "rule_based_anomaly_detection": 90,
        "rapid_visual_comparison": 60,
        "pattern_closure_visual_noise": 75,
        "speech_in_noise_comprehension": 120,
        "written_comprehension_synthesis": 180,
    }
    assert normalized["task_durations_seconds"] == TASK_RECORDING_DURATIONS_SECONDS
    assert set(normalized["components"]) == set(PROTOCOL_PROFILE_COMPONENTS)


def test_validated_profile_requires_every_resource_component_to_be_validated():
    profile = candidate_protocol_profile()
    profile["profile_id"] = "mindspeller_normed_profile"
    profile["profile_version"] = "2.0.0"
    profile["validation_status"] = "validated"
    for component_name, component in profile["components"].items():
        component["validation_status"] = "validated"
        component["version"] = "normed_v2"
        component["content_hash"] = f"sha256:test-fixture-{component_name}"

    normalized, errors = normalize_protocol_profile(profile)
    assert errors == []
    assert normalized["normative_interpretation_allowed"] is True
    assert normalized["interpretation_scope"] == "validated_production"

    profile["components"]["rubrics"]["validation_status"] = "pilot"
    normalized, errors = normalize_protocol_profile(profile)
    assert "validated_profile_requires_all_components_validated" in errors
    assert normalized["normative_interpretation_allowed"] is False


def test_validated_profile_requires_a_content_anchor_for_each_component():
    profile = candidate_protocol_profile()
    profile["profile_id"] = "mindspeller_normed_profile"
    profile["profile_version"] = "2.0.0"
    profile["validation_status"] = "validated"
    for index, (component_name, component) in enumerate(
        profile["components"].items()
    ):
        component["validation_status"] = "validated"
        component["version"] = "normed_v2"
        # Both supported provenance strategies are exercised: hashes provide
        # byte identity, while URIs identify publisher-governed pinned config.
        if index % 2 == 0:
            component["content_hash"] = f"sha256:test-fixture-{component_name}"
        else:
            component["config_uri"] = (
                f"urn:mindspeller:protocol-component:{component_name}:normed-v2"
            )

    normalized, errors = normalize_protocol_profile(profile)

    assert errors == []
    assert normalized["normative_interpretation_allowed"] is True
    assert normalized["components"]["stimuli"]["content_hash"].startswith(
        "sha256:"
    )
    assert normalized["components"]["audio"]["config_uri"].startswith("urn:")

    del profile["components"]["thresholds"]["config_uri"]
    normalized, errors = normalize_protocol_profile(profile)

    assert (
        "validated_profile_component_content_anchor_missing:thresholds" in errors
    )
    assert normalized["normative_interpretation_allowed"] is False


def test_candidate_profile_does_not_require_validated_content_anchors():
    profile = candidate_protocol_profile()
    assert all(
        "content_hash" not in component and "config_uri" not in component
        for component in profile["components"].values()
    )

    normalized, errors = normalize_protocol_profile(profile)

    assert errors == []
    assert normalized["validation_status"] == "pilot"
    assert normalized["normative_interpretation_allowed"] is False


def test_protocol_profile_rejects_changed_or_missing_normative_task_duration():
    profile = candidate_protocol_profile()
    profile["task_durations_seconds"]["rapid_visual_comparison"] = 40
    del profile["task_durations_seconds"]["written_comprehension_synthesis"]

    normalized, errors = normalize_protocol_profile(profile)

    assert normalized["normative_interpretation_allowed"] is False
    assert any(
        error.startswith(
            "protocol_profile_task_duration_mismatch:rapid_visual_comparison"
        )
        for error in errors
    )
    assert (
        "protocol_profile_task_duration_invalid:written_comprehension_synthesis"
        in errors
    )


def test_protocol_profile_reference_is_compact_and_task_specific():
    profile, errors = normalize_protocol_profile(candidate_protocol_profile())
    assert errors == []

    reference = protocol_profile_reference(
        profile, "speech_in_noise_comprehension"
    )

    assert reference["profile_id"] == profile["profile_id"]
    assert reference["component_versions"] == {
        name: profile["components"][name]["version"]
        for name in PROTOCOL_PROFILE_COMPONENTS
    }
    assert reference["expected_recording_duration_seconds"] == 120
    assert reference["normative_interpretation_allowed"] is False


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


# ─── Revised task matrix and retired-core protections ─────────────────────────

def test_written_comprehension_has_multimodal_candidates_and_explicit_blocks():
    task_id = "written_comprehension_synthesis"
    assert theoretical_abilities_for_task(task_id) == [
        "Written Comprehension", "Written Expression", "Inductive Reasoning",
        "Information Ordering",
    ]
    blocked = blocked_inferences_for_task(task_id)
    assert "Oral Comprehension" in blocked
    assert "Speech Clarity" in blocked


def test_visual_closure_does_not_claim_reaction_time_or_perceptual_speed():
    blocked = blocked_inferences_for_task("pattern_closure_visual_noise")
    assert "Reaction Time" in blocked
    assert "Perceptual Speed" in blocked


def test_removed_tasks_are_not_core_or_role_matching_eligible():
    canonical_ids = {task["id"] for task in CANONICAL_TASKS.values()}
    for task in ("static_emotion_grasp", "body_scan", "visual_colour_processing"):
        assert task not in canonical_ids
        assert resolve_canonical_task(task) is None
        assert role_matching_status_for_task(task) == "not_eligible"
        assert theoretical_abilities_for_task(task) == []


def test_behavioral_status_gate_is_explicit_and_conservative():
    task_id = "adaptive_numerical_reasoning"
    assert normalize_behavioral_status(None) == "missing"
    assert normalize_behavioral_status({"status": "complete"}) == "unverified"
    assert allowed_abilities_for_task(task_id, "strong") == []
    assert allowed_abilities_for_task(
        task_id,
        "strong",
        behavioral_evidence={"status": "passed"},
    ) == theoretical_abilities_for_task(task_id)


def test_per_ability_behavioral_validation_filters_multimodal_candidates():
    evidence = {
        "status": "pending_review",
        "ability_validation": {
            "Oral Comprehension": "pending_review",
            "Speech Recognition": "passed",
            "Auditory Attention": "failed",
        },
    }

    assert allowed_abilities_for_task(
        "speech_in_noise_comprehension",
        "strong",
        behavioral_evidence=evidence,
    ) == ["Speech Recognition"]


def test_export_keeps_partial_behavioral_validation_separate_from_theory():
    task_id = "speech_in_noise_comprehension"
    per_task = _make_per_task(task_id)
    per_task[task_id]["behavioral_evidence"] = {
        "status": "pending_review",
        "ability_validation": {
            "Oral Comprehension": "pending_review",
            "Speech Recognition": "passed",
            "Auditory Attention": "failed",
        },
    }
    existing = _make_existing_analysis(per_task)
    existing["baseline_kept"] = 20
    existing["baseline_rejected"] = 0

    export = build_neuroprofile_export(per_task, existing)
    task_summary = export["tasks"][0]["task_summary"]

    assert task_summary["theoretical_onet_ability_candidates"] == [
        "Oral Comprehension", "Speech Recognition", "Auditory Attention",
    ]
    assert task_summary["behaviorally_validated_onet_ability_candidates"] == [
        "Speech Recognition",
    ]
    assert task_summary["allowed_onet_ability_candidates"] == ["Speech Recognition"]
    assert export["allowed_ability_pool"] == ["Speech Recognition"]


# ─── Test 14–16: session depth inference ─────────────────────────────────────

def test_session_1_depth():
    canonical_ids = [CANONICAL_TASKS[n]["id"] for n in SESSION_TASK_GATES["session_1"]]
    depth = _infer_session_depth(canonical_ids)
    assert depth == "session_1"


def test_session_2_depth():
    canonical_ids = [CANONICAL_TASKS[n]["id"] for n in SESSION_TASK_GATES["session_2"]]
    assert _infer_session_depth(canonical_ids) == "session_2"


def test_session_3_depth():
    canonical_ids = [CANONICAL_TASKS[n]["id"] for n in SESSION_TASK_GATES["session_3"]]
    assert _infer_session_depth(canonical_ids) == "session_3"


def test_display_names_and_numbers_resolve_but_legacy_protocol_ids_do_not():
    assert resolve_canonical_task("1") == "adaptive_numerical_reasoning"
    assert resolve_canonical_task(
        "Adaptive Numerical Reasoning and Sequencing"
    ) == "adaptive_numerical_reasoning"
    assert resolve_canonical_task(
        "Semantic Induction and Category Switching"
    ) == "semantic_induction_category_switching"
    assert resolve_canonical_task(
        "Working-Memory Manipulation"
    ) == "working_memory_manipulation"
    for legacy_id in (
        "mental_math", "working_memory", "focused_attention",
        "visual_imagery", "motor_imagery", "language_processing",
        "semantic_memory", "divergent_thinking",
        "cognitive_load_multitasking",
    ):
        assert resolve_canonical_task(legacy_id) is None


# ─── Test 17: single weak feature does not populate ability pool ──────────────

def test_single_weak_feature_no_ability_pool():
    per_task = _make_per_task("working_memory_manipulation")
    # Override to weak feature (d < 0.50)
    per_task["working_memory_manipulation"]["analysis"]["theta_power_raw"]["effect_size_d"] = 0.20
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    # Allowed pool should be empty because single weak non-convergent feature
    # (All other features absent → no convergence)
    pool = export["allowed_ability_pool"]
    assert pool == [], f"Expected empty pool for single weak feature, got {pool}"


def test_theoretical_candidates_are_separate_from_behaviorally_gated_abilities():
    task_id = "adaptive_numerical_reasoning"
    per_task = {
        task_id: {
            "analysis": {
                "theta_power_raw": _make_analysis_feature(
                    "theta_power_raw", q=0.001, d=0.9, pct=25.0, significant=True
                ),
            },
            "summary": {"expectation": {"grade": "A"}},
            "sample_count": 20,
            "scorable": True,
        }
    }
    existing = _make_existing_analysis(per_task)
    existing["baseline_kept"] = 20
    existing["baseline_rejected"] = 0

    without_behavior = build_neuroprofile_export(per_task, existing)
    assert without_behavior["allowed_ability_pool"] == []
    assert without_behavior["theoretical_ability_pool"] == theoretical_abilities_for_task(task_id)

    per_task[task_id]["behavioral_evidence"] = {"status": "passed", "accuracy": 1.0}
    with_behavior = build_neuroprofile_export(per_task, existing)
    assert with_behavior["allowed_ability_pool"] == theoretical_abilities_for_task(task_id)
    feature = with_behavior["feature_rows"][0]
    assert feature["passes_behavioral_gate"] is True
    assert feature["passes_ability_gate"] is True


# ─── Test 18: allowed_ability_pool contains only allowed O*NET labels ─────────

def test_allowed_ability_pool_no_blocked_labels():
    per_task = {}
    per_task.update(_make_per_task("working_memory_manipulation"))
    per_task.update(_make_per_task("adaptive_numerical_reasoning"))
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    for task_entry in export["tasks_detected"]:
        task_pool = set(task_entry["task_summary"]["allowed_onet_ability_candidates"])
        task_blocked = set(blocked_inferences_for_task(task_entry["canonical_task_id"]))
        overlap = task_pool & task_blocked
        assert not overlap, f"Blocked labels in per-task ability pool: {overlap}"


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
        "tasks":    {"adaptive_numerical_reasoning": task_samples},
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
    per_task = _make_per_task("working_memory_manipulation")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)

    assert export["feature_report_version"] == "mindspeller_eeg_feature_report_v3"
    assert export["traceability_version"]   == "mindspeller_eeg_feature_traceability_v8"
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
    assert "theoretical_ability_pool" in export
    assert "blocked_unsupported_labels" in export


def test_task_export_retains_temporal_and_qc_provenance():
    per_task = _make_per_task("working_memory_manipulation")
    source = per_task["working_memory_manipulation"]
    source["baseline_qc"] = {"meets_contiguous_clean_minimum": True}
    source["continuous_time_series"] = {
        "status": "descriptive_only",
        "features": {"alpha_power": {"slope_per_minute": 0.25}},
    }
    source["single_task_reference_comparison"] = {
        "status": "available",
        "comparisons": {"auditory_target_counting": {"features": {}}},
    }
    source["invalid_reasons"] = []

    export = build_neuroprofile_export(per_task, _make_existing_analysis(per_task))
    task = export["tasks"][0]

    assert task["task_qc"]["meets_contiguous_clean_minimum"] is True
    assert task["baseline_qc"]["meets_contiguous_clean_minimum"] is True
    assert task["continuous_time_series"]["status"] == "descriptive_only"
    assert task["single_task_reference_comparison"]["status"] == "available"
    assert task["invalid_reasons"] == []


def test_task_entry_has_feature_family():
    per_task = _make_per_task("working_memory_manipulation")
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


def test_coherent_fallback_feature_is_reportable_but_cautious_and_weak():
    per_task = {
        "visuospatial_transformation_orientation": {
            "analysis": {
                "alpha_relative": _make_analysis_feature("alpha_relative"),
            },
            "summary": {
                "expectation": {"grade": "A"},
            },
            "sample_count": 6,
        }
    }
    existing = _make_existing_analysis(per_task)
    existing["baseline_kept"] = 20
    existing["baseline_rejected"] = 0

    export = build_neuroprofile_export(per_task, existing)
    feature = export["tasks"][0]["features"][0]

    assert feature["passes_statistical_gate"] is False
    assert feature["significance_basis"] == "effect_size_percent_fallback"
    assert feature["interpretation_safety"] == "use_with_caution"
    assert feature["passes_neuroprofile_gate"] is True
    assert feature["feature_strength_before_cap"] == "weak"
    assert feature["feature_strength"] == "weak"


def test_wrong_direction_fallback_stays_rejected():
    feat = {
        **_make_analysis_feature(
            "alpha_relative",
            direction_ok=False,
            delta=-1.0,
        ),
        "metric_name": "alpha_relative",
    }

    gate = _gate_transparency("alpha_relative", feat)

    assert gate["significance_basis"] == "none"
    assert gate["interpretation_safety"] == "do_not_use"
    assert passes_neuroprofile_gate(feat) is False


def test_gamma_fallback_stays_rejected_without_non_gamma_support():
    feat = {
        **_make_analysis_feature(
            "gamma_power",
            q=0.5,
            d=0.9,
            pct=20.0,
        ),
        "metric_name": "gamma_power",
    }
    feat["decision_flags"]["gamma_sparse_montage_guard"] = {
        "emg_guard_clean": True,
        "regional_agreement_ok": True,
        "non_gamma_support": False,
    }

    assert passes_neuroprofile_gate(feat) is False


def test_cautious_only_task_cannot_reach_moderate_or_strong_confidence():
    per_task = {
        "visuospatial_transformation_orientation": {
            "analysis": {
                "alpha_relative": _make_analysis_feature("alpha_relative", d=1.20),
                "alpha_theta_ratio": _make_analysis_feature("alpha_theta_ratio", d=1.10),
                "theta_relative": _make_analysis_feature("theta_relative", d=0.95),
            },
            "summary": {
                "expectation": {"grade": "A"},
            },
            "sample_count": 6,
        }
    }
    existing = _make_existing_analysis(per_task)
    existing["baseline_kept"] = 20
    existing["baseline_rejected"] = 0

    export = build_neuroprofile_export(per_task, existing)
    task = export["tasks"][0]

    assert {f["feature_strength"] for f in task["features"]} == {"weak"}
    assert all(f["passes_neuroprofile_gate"] for f in task["features"])
    assert task["task_summary"]["confidence_before_cap"] == "weak"
    assert task["task_summary"]["confidence"] == "weak"
    assert export["global_reliability"] == "medium"


def test_neuroprofile_export_schema_is_unchanged_for_tiered_evidence():
    per_task = {
        "visuospatial_transformation_orientation": {
            "analysis": {
                "alpha_relative": _make_analysis_feature("alpha_relative"),
            },
            "summary": {
                "expectation": {"grade": "A"},
            },
            "sample_count": 6,
        }
    }
    existing = _make_existing_analysis(per_task)
    existing["baseline_kept"] = 20
    existing["baseline_rejected"] = 0

    export = build_neuroprofile_export(per_task, existing)
    row = export["feature_rows"][0]

    assert export["protocol_profile"]["profile_id"] == (
        "mindspeller_optimized_task_battery"
    )
    assert export["protocol_profile"]["profile_version"] == "2.0.0-candidate.1"
    assert export["protocol_profile"]["validation_status"] == "pilot"
    assert export["protocol_profile_validation"] == {
        "valid": True,
        "errors": [],
        "normative_interpretation_allowed": False,
    }

    assert set(export) == {
        "feature_report_version",
        "traceability_version",
        "protocol_session_depth",
        "headset_scope",
        "global_reliability",
        "baseline_qc",
        "session_confidence_cap",
        "allowed_ability_pool",
        "theoretical_ability_pool",
        "moderator_only_characteristics",
        "blocked_unsupported_labels",
        "feature_rows",
        "tasks",
        "tasks_detected",
        "global_quality",
        "protocol_profile",
        "protocol_profile_validation",
    }
    assert set(row) == {
        "task_number",
        "canonical_task_id",
        "canonical_task_name",
        "task_role_matching_status",
        "task_signal_quality",
        "task_confidence",
        "task_confidence_before_cap",
        "task_scorable",
            "task_baseline_condition",
            "task_behavioral_evidence_status",
            "task_protocol_profile_id",
            "task_protocol_profile_version",
            "task_protocol_validation_status",
            "task_normative_interpretation_allowed",
            "metric_name",
        "feature_family",
        "band",
        "direction",
        "grade",
        "effect_size_d",
        "p_value",
        "q_value",
        "percent_change",
        "passes_q_value",
        "passes_effect_size_threshold",
        "passes_percent_change_threshold",
        "passes_statistical_gate",
        "significance_basis",
        "interpretation_safety",
        "effect_size_threshold_used",
        "percent_change_threshold_used",
        "baseline_block_count",
        "task_block_count",
        "effective_sample_size",
        "task_mean",
        "baseline_mean",
        "delta",
        "passes_neuroprofile_gate",
        "feature_strength",
        "feature_strength_before_cap",
        "role_matching_status",
        "task_supported_characteristics",
        "theoretical_onet_ability_candidates",
        "behaviorally_validated_onet_ability_candidates",
        "allowed_onet_ability_candidates",
        "behavioral_evidence_status",
        "passes_behavioral_gate",
        "passes_ability_gate",
        "blocked_inferences",
    }
    assert "evidence_tier" not in row
    assert "included_as_cautious_evidence" not in row
    assert "neuroprofile_evidence_summary" not in export


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
    per_task = _make_per_task("working_memory_manipulation")
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
    per_task = _make_per_task("adaptive_numerical_reasoning")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    cap = export["session_confidence_cap"]
    assert "implicit_trait_max" in cap
    assert "role_recommendation_max" in cap
    assert "reason" in cap


def test_session_1_cap_values():
    """Session 1 cap: both maxes should be at most moderate."""
    per_task = _make_per_task("adaptive_numerical_reasoning")
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
    per_task = _make_per_task("working_memory_manipulation")
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
    per_task = _make_per_task("working_memory_manipulation")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    assert "feature_rows" in export
    assert isinstance(export["feature_rows"], list)
    assert len(export["feature_rows"]) > 0


def test_feature_rows_have_task_context():
    per_task = _make_per_task("working_memory_manipulation")
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    for row in export["feature_rows"]:
        assert "task_number" in row
        assert "canonical_task_id" in row
        assert "canonical_task_name" in row
        assert "task_role_matching_status" in row
        assert "task_confidence" in row


def test_feature_rows_have_gate_fields():
    per_task = _make_per_task("working_memory_manipulation")
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
    per_task.update(_make_per_task("working_memory_manipulation"))
    per_task.update(_make_per_task("adaptive_numerical_reasoning"))
    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    nested_count = sum(len(t["features"]) for t in export["tasks"])
    assert len(export["feature_rows"]) == nested_count


def test_revised_complete_battery_produces_session_3_export():
    per_task = {}
    for task in CANONICAL_TASKS.values():
        per_task.update(_make_per_task(task["id"]))

    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)

    assert export["protocol_session_depth"] == "session_3"
    canonical_ids = {task["canonical_task_id"] for task in export["tasks"]}
    assert canonical_ids == {task["id"] for task in CANONICAL_TASKS.values()}


def test_retired_diverse_thinking_id_is_not_silently_relabelled():
    per_task = _make_per_task("diverse_thinking")

    existing = _make_existing_analysis(per_task)
    export = build_neuroprofile_export(per_task, existing)
    creative_task = next(
        task for task in export["tasks"]
        if "diverse_thinking" in task["raw_task_labels"]
    )

    assert creative_task["canonical_task_id"] == "diverse_thinking"
    assert creative_task["task_number"] is None
    assert creative_task["role_matching_status"] == "not_eligible"
    assert export["protocol_session_depth"] == "partial_unknown"
