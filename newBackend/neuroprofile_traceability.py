"""
neuroprofile_traceability.py
────────────────────────────
Traceability constants, classifiers, and exporters for the Mindspeller EEG
neuroprofile pipeline.  Imported by main.py; does not import from main.py.

This module only produces *structured EEG evidence*.
Role matching, neuroprofile generation, and hiring decisions happen later in
the neuroprofile backend.

v7.1 additions
--------------
* Reliability-based confidence capping (global reliability -> per-feature/task cap)
* Statistical gate transparency per feature (passes_q_value, significance_basis,
  interpretation_safety)
* Baseline/task sample counts and means per feature
* session_confidence_cap block for downstream agents
* JSON export shape aligned with Implicit Agent consumption contract:
  - top-level "tasks" (primary) + "tasks_detected" alias for backward compat
  - flat "global_reliability" string
  - flat "baseline_qc" dict
  - "session_confidence_cap" block

v7.2 additions
--------------
* "feature_rows" — flat, denormalized array of all features across all tasks.
  One dict per feature, with task context fields prepended.  Intended as the
  primary machine-readable input for the Implicit Agent (no nested traversal).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Version stamps
# ---------------------------------------------------------------------------
TRACEABILITY_VERSION        = "mindspeller_eeg_feature_traceability_v7"
NEUROPROFILE_EXPORT_VERSION = "mindspeller_eeg_feature_report_v2"

# ---------------------------------------------------------------------------
# Session task gates
# ---------------------------------------------------------------------------
SESSION_TASK_GATES: Dict[str, List[int]] = {
    "session_1": [1, 2, 3, 4],
    "session_2": [1, 2, 3, 4, 5, 6, 7, 8, 9],
    "session_3": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
}

# ---------------------------------------------------------------------------
# Canonical tasks
# ---------------------------------------------------------------------------
CANONICAL_TASKS: Dict[int, Dict[str, str]] = {
    1:  {"id": "mental_math",                 "name": "Mental Math"},
    2:  {"id": "visual_imagery",              "name": "Visual Imagery"},
    3:  {"id": "focused_attention",           "name": "Focused Attention"},
    4:  {"id": "static_emotion_grasp",        "name": "Static Emotion Grasp"},
    5:  {"id": "working_memory",              "name": "Working Memory"},
    6:  {"id": "language_processing",         "name": "Language Processing"},
    7:  {"id": "motor_imagery",               "name": "Motor Imagery"},
    8:  {"id": "cognitive_load_multitasking", "name": "Cognitive Load / Multitasking"},
    9:  {"id": "divergent_thinking",          "name": "Divergent Thinking"},
    10: {"id": "body_scan",                   "name": "Body Scan"},
    11: {"id": "visual_colour_processing",    "name": "Visual Colour Processing"},
    12: {"id": "semantic_memory_retrieval",   "name": "Semantic Memory Retrieval"},
}

_CANONICAL_ID_TO_NUMBER: Dict[str, int] = {
    v["id"]: k for k, v in CANONICAL_TASKS.items()
}

# ---------------------------------------------------------------------------
# Task name aliases
# ---------------------------------------------------------------------------
TASK_NAME_ALIASES: Dict[str, str] = {
    "math":                        "mental_math",
    "mental_math":                 "mental_math",
    "serial_calculation":          "mental_math",
    "arithmetic":                  "mental_math",
    "visual_imagery":              "visual_imagery",
    "imagery":                     "visual_imagery",
    "internal_imagery":            "visual_imagery",
    "attention_focus":             "focused_attention",
    "focused_attention":           "focused_attention",
    "focus":                       "focused_attention",
    "emotion_face":                "static_emotion_grasp",
    "emotion_faces":               "static_emotion_grasp",
    "reappraisal":                 "static_emotion_grasp",
    "static_emotion_grasp":        "static_emotion_grasp",
    "working_memory":              "working_memory",
    "n_back":                      "working_memory",
    "wm":                          "working_memory",
    "language":                    "language_processing",
    "language_processing":         "language_processing",
    "semantic_processing":         "language_processing",
    "motor_imagery":               "motor_imagery",
    "movement_imagery":            "motor_imagery",
    "cognitive_load":              "cognitive_load_multitasking",
    "multitasking":                "cognitive_load_multitasking",
    "task_switching":              "cognitive_load_multitasking",
    "load_multitasking":           "cognitive_load_multitasking",
    "cognitive_load_multitasking": "cognitive_load_multitasking",
    "div_write":                   "divergent_thinking",
    "divergent_thinking":          "divergent_thinking",
    "creative_ideation":           "divergent_thinking",
    "body_scan":                   "body_scan",
    "interoception":               "body_scan",
    "colour_processing":           "visual_colour_processing",
    "color_processing":            "visual_colour_processing",
    "visual_colour_processing":    "visual_colour_processing",
    "visual_color_processing":     "visual_colour_processing",
    "semantic_memory":             "semantic_memory_retrieval",
    "semantic_retrieval":          "semantic_memory_retrieval",
    "semantic_memory_retrieval":   "semantic_memory_retrieval",
}

# ---------------------------------------------------------------------------
# Feature families
# ---------------------------------------------------------------------------
FEATURE_FAMILIES = {
    "spectral_power", "relative_power", "band_ratio", "peak_feature",
    "entropy_complexity", "signal_quality", "transition_recovery",
    "task_summary_stat", "behavioral_optional", "unknown",
}

# ---------------------------------------------------------------------------
# Effect-size thresholds per band/family keyword
# ---------------------------------------------------------------------------
EFFECT_SIZE_THRESHOLDS: Dict[str, float] = {
    "theta": 0.30, "alpha": 0.25, "beta": 0.35, "gamma": 0.30,
    "delta": 0.30, "ratio": 0.30, "entropy": 0.30,
    "peak":  0.30, "relative": 0.30, "transition": 0.30,
}

RELATIVE_PERCENT_CHANGE_MIN = 5.0
ABSOLUTE_PERCENT_CHANGE_MIN = 10.0

# ---------------------------------------------------------------------------
# Moderator-only tasks
# ---------------------------------------------------------------------------
_MODERATOR_ONLY_TASKS = {"static_emotion_grasp", "body_scan", "visual_colour_processing"}

# ---------------------------------------------------------------------------
# Reliability and session confidence caps
# ---------------------------------------------------------------------------

# Ordered from weakest to strongest — used for comparison/capping.
_STRENGTH_ORDER = ["rejected", "weak", "moderate", "strong"]

# Maximum feature/task confidence allowed at each global reliability level.
_RELIABILITY_CONFIDENCE_CAP: Dict[str, str] = {
    "high":    "strong",    # no cap
    "medium":  "moderate",  # strong -> moderate
    "low":     "weak",      # strong/moderate -> weak
    "unknown": "weak",
}

# Per-session caps on downstream inference (before reliability is applied).
_SESSION_CAPS: Dict[str, Dict[str, str]] = {
    "session_1": {
        "implicit_trait_max":      "moderate",
        "role_recommendation_max": "moderate",
        "reason": (
            "Session 1 only (Tasks 1-4); no repeated-task stability or "
            "executive expansion tasks available. "
            "Latent traits require convergence across tasks and sessions."
        ),
    },
    "session_2": {
        "implicit_trait_max":      "strong",
        "role_recommendation_max": "moderate",
        "reason": (
            "Session 2 (Tasks 1-9); executive expansion available "
            "but full calibration incomplete."
        ),
    },
    "session_3": {
        "implicit_trait_max":      "strong",
        "role_recommendation_max": "strong",
        "reason": "Session 3 complete (Tasks 1-12); full 12-task calibration.",
    },
    "partial_unknown": {
        "implicit_trait_max":      "weak",
        "role_recommendation_max": "weak",
        "reason": (
            "Partial or unknown session depth; insufficient for confident inference."
        ),
    },
}

# ---------------------------------------------------------------------------
# Task characteristic / ability / blocked matrices
# ---------------------------------------------------------------------------
_TASK_MATRIX: Dict[str, Dict[str, Any]] = {
    "mental_math": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "processing_efficiency_under_load", "quantitative_load_response",
            "effort_mobilisation", "working_memory_rule_sequence_load",
            "load_response_slope", "fatigue_drift_under_demand", "post_effort_recovery",
        ],
        "allowed_abilities": ["Mathematical Reasoning", "Number Facility", "Information Ordering"],
        "blocked": ["Speaking", "Oral Expression", "Reading Comprehension"],
    },
    "visual_imagery": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "internal_visual_simulation", "top_down_maintenance",
            "representation_stability", "imagery_control", "internal_attention_stability",
        ],
        "allowed_abilities": ["Visualization"],
        "blocked": ["Visual Color Discrimination", "Near Vision", "Far Vision",
                    "design skill by itself"],
    },
    "focused_attention": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery", "signal_quality",
        },
        "characteristics": [
            "sustained_attention", "attentional_stability", "drift_resistance",
            "reorientation_control", "low_artifact_calibration_stability",
        ],
        "allowed_abilities": ["Selective Attention"],
        "blocked": ["Active Listening", "Auditory Attention", "Speech Recognition"],
    },
    "static_emotion_grasp": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "affective_appraisal", "emotion_salience_response",
            "motivational_direction_bias", "salience_regulation",
            "regulation_under_affective_input",
        ],
        "allowed_abilities": [],
        "blocked": ["Social Perceptiveness", "Persuasion", "Service Orientation",
                    "Leadership ability"],
        "role_matching_status": "moderator_only",
    },
    "working_memory": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "working_memory_load_scaling", "maintenance_and_manipulation",
            "load_threshold", "executive_efficiency", "manipulation_cost", "capacity_proxy",
        ],
        "allowed_abilities": ["Information Ordering", "Memorization", "Deductive Reasoning"],
        "blocked": ["Reading Comprehension", "Written Comprehension", "Oral Comprehension"],
    },
    "language_processing": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "silent_semantic_integration", "semantic_control_cost",
            "retrieval_organization", "structured_semantic_processing",
            "symbolic_processing_effort",
        ],
        "allowed_abilities": [
            "Inductive Reasoning", "Information Ordering", "Category Flexibility",
        ],
        "blocked": [
            "Oral Comprehension", "Written Comprehension", "Reading Comprehension",
            "Oral Expression", "Written Expression", "Speaking", "Writing", "Active Listening",
        ],
    },
    "motor_imagery": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "embodied_simulation", "action_planning_imagery",
            "internal_action_sequencing", "simulation_maintenance", "planning_bias",
        ],
        "allowed_abilities": ["Visualization"],
        "blocked": ["Manual Dexterity", "Finger Dexterity", "Reaction Time", "Control Precision"],
    },
    "cognitive_load_multitasking": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "switching_cost", "interference_management", "overload_threshold",
            "executive_flexibility", "recovery_after_interference",
            "escalation_slope_under_competing_demands",
        ],
        "allowed_abilities": [
            "Time Sharing", "Category Flexibility", "Information Ordering",
            "Deductive Reasoning",
        ],
        "blocked": ["Coordination", "Active Listening", "Social Perceptiveness"],
    },
    "divergent_thinking": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "idea_fluency_dynamics", "originality_dynamics", "associative_breadth",
            "creative_control_style", "internal_attention_dominance",
        ],
        "allowed_abilities": ["Fluency of Ideas", "Originality", "Category Flexibility"],
        "blocked": ["Writing", "Speaking", "artistic achievement"],
    },
    "body_scan": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "interoceptive_attention", "internal_attention_stability",
            "post_load_recovery", "regulation_efficiency_proxy",
            "calm_state_stability", "reduced_volatility",
        ],
        "allowed_abilities": [],
        "blocked": ["diagnosis", "clinical regulation", "guaranteed stress resilience"],
        "role_matching_status": "moderator_only",
    },
    "visual_colour_processing": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "visual_engagement", "evaluative_preference_response",
            "approach_bias_candidate", "habituation_pattern", "evaluative_style_proxy",
        ],
        "allowed_abilities": [],
        "blocked": ["Visual Color Discrimination", "color vision ability",
                    "low-level sensory acuity"],
        "role_matching_status": "moderator_only",
    },
    "semantic_memory_retrieval": {
        "eligible_families": {
            "spectral_power", "relative_power", "band_ratio",
            "peak_feature", "entropy_complexity", "transition_recovery",
        },
        "characteristics": [
            "semantic_access_efficiency", "retrieval_effort", "category_access_pattern",
            "transition_control", "retrieval_rest_contrast_efficiency",
            "onset_offset_control",
        ],
        "allowed_abilities": [
            "Memorization", "Information Ordering", "Category Flexibility",
            "Inductive Reasoning",
        ],
        "blocked": [
            "Oral Expression", "Written Expression", "Speaking", "Writing",
            "Oral Comprehension", "Reading Comprehension",
        ],
    },
}


# ===========================================================================
# Public helpers
# ===========================================================================

def resolve_canonical_task(raw_task_id: str) -> Optional[str]:
    """Return the canonical task ID for a raw task label, or None if unknown."""
    return TASK_NAME_ALIASES.get((raw_task_id or "").strip().lower())


def canonical_task_number(canonical_task_id: str) -> Optional[int]:
    """Return the 1-based task number for a canonical task ID."""
    return _CANONICAL_ID_TO_NUMBER.get(canonical_task_id)


def classify_feature_family(metric_name: str) -> str:
    """Return the feature family for a metric emitted by the existing analyzer."""
    m = (metric_name or "").lower()
    if any(t in m for t in ["recovery", "fatigue", "habituation", "baseline_return", "stability"]):
        return "transition_recovery"
    if m in {"_emg_guard", "_gamma_evaluated"}:
        return "signal_quality"
    if m == "total_power":
        return "task_summary_stat"
    if m.endswith("_power") or m.endswith("_power_raw"):
        return "spectral_power"
    if m.endswith("_relative"):
        return "relative_power"
    if m.endswith("_ratio") or m in {
        "alpha_theta_ratio", "beta_alpha_ratio",
        "beta2_beta1_ratio", "theta2_theta1_ratio",
    }:
        return "band_ratio"
    if "peak" in m:
        return "peak_feature"
    if m.endswith("_entropy") or "entropy" in m:
        return "entropy_complexity"
    return "unknown"


def _effect_size_threshold_for_metric(metric_name: str) -> float:
    m = metric_name.lower()
    for band_key, thr in EFFECT_SIZE_THRESHOLDS.items():
        if band_key in m:
            return thr
    return 0.30


def _pct_threshold_for_metric(metric_name: str) -> float:
    m = metric_name.lower()
    if m.endswith("_relative") or "ratio" in m:
        return RELATIVE_PERCENT_CHANGE_MIN
    return ABSOLUTE_PERCENT_CHANGE_MIN


def _apply_reliability_cap(strength: str, reliability: str) -> str:
    """Cap feature/task strength downward based on global reliability.

    'rejected' is never changed. Only downward capping is applied.
    """
    if strength == "rejected":
        return "rejected"
    cap_str = _RELIABILITY_CONFIDENCE_CAP.get(reliability, "weak")
    cap_idx = _STRENGTH_ORDER.index(cap_str) if cap_str in _STRENGTH_ORDER else 1
    str_idx = _STRENGTH_ORDER.index(strength) if strength in _STRENGTH_ORDER else 1
    return _STRENGTH_ORDER[min(str_idx, cap_idx)]


def passes_neuroprofile_gate(feature: Dict[str, Any]) -> bool:
    """Return True if this feature is reportable downstream."""
    metric_name = feature.get("metric_name", "")
    m = metric_name.lower()
    family = feature.get("feature_family", classify_feature_family(metric_name))
    if family == "signal_quality":
        return False
    if "gamma" in m:
        if feature.get("_emg_guard", 0) == 1 or feature.get("_gamma_evaluated", 1) == 0:
            return False
    sig_flag = feature.get("significant_change")
    if sig_flag is True:
        pass_sig = True
    else:
        q = feature.get("q_value")
        p = feature.get("p_value")
        if q is not None:
            pass_sig = q <= 0.0119377
        elif p is not None:
            pass_sig = p <= 0.05
        else:
            return False
    if not pass_sig:
        return False
    d = feature.get("effect_size_d")
    if d is not None and abs(d) < _effect_size_threshold_for_metric(metric_name):
        return False
    pct = feature.get("percent_change")
    if pct is not None and abs(pct) < _pct_threshold_for_metric(metric_name):
        return False
    return True


def classify_feature_strength(feature: Dict[str, Any]) -> str:
    """Return 'rejected' | 'weak' | 'moderate' | 'strong'.

    Grade A/B -> strong (when d >= 0.80). Grade C -> moderate.
    Grade D or insufficient_metrics -> ungraded (no penalty).
    Does NOT apply reliability cap; call _apply_reliability_cap externally.
    """
    if not passes_neuroprofile_gate(feature):
        return "rejected"
    d = feature.get("effect_size_d")
    if d is None:
        return "weak"
    d_abs        = abs(d)
    raw_grade    = feature.get("grade")
    insufficient = feature.get("_insufficient_metrics", False)
    if raw_grade in ("A", "B") and not insufficient:
        effective_grade = raw_grade
    elif raw_grade == "C" and not insufficient:
        effective_grade = "C"
    else:
        effective_grade = None   # ungraded — no penalty
    if d_abs >= 0.80:
        return "strong" if effective_grade in ("A", "B", None) else "moderate"
    if d_abs >= 0.50:
        return "moderate"
    return "weak"


def map_feature_to_characteristics(
    canonical_task_id: str,
    metric_name: str,
    feature_family: str,
    direction: Optional[str],
    feature_strength: str,
) -> List[str]:
    """Return task-supported characteristic candidates for this feature."""
    if feature_strength == "rejected":
        return []
    matrix = _TASK_MATRIX.get(canonical_task_id)
    if matrix is None or feature_family not in matrix["eligible_families"]:
        return []
    return list(matrix["characteristics"])


def allowed_abilities_for_task(
    canonical_task_id: str,
    feature_strength: str,
    convergent: bool = False,
) -> List[str]:
    """Return downstream O*NET ability candidates."""
    if canonical_task_id in _MODERATOR_ONLY_TASKS:
        return []
    if feature_strength in ("rejected", "weak") and not convergent:
        return []
    matrix = _TASK_MATRIX.get(canonical_task_id)
    return list(matrix["allowed_abilities"]) if matrix else []


def blocked_inferences_for_task(canonical_task_id: str) -> List[str]:
    """Return labels that this task must never support."""
    matrix = _TASK_MATRIX.get(canonical_task_id)
    return list(matrix["blocked"]) if matrix else []


def role_matching_status_for_task(canonical_task_id: str) -> str:
    """Return 'eligible' | 'moderator_only' | 'not_eligible'."""
    if canonical_task_id in _MODERATOR_ONLY_TASKS:
        return "moderator_only"
    matrix = _TASK_MATRIX.get(canonical_task_id)
    if matrix is None:
        return "not_eligible"
    return matrix.get("role_matching_status", "eligible")


def _infer_session_depth(canonical_task_ids: List[str]) -> str:
    """Return the smallest session gate that fully contains all detected tasks."""
    task_numbers = {
        canonical_task_number(tid)
        for tid in canonical_task_ids
        if canonical_task_number(tid) is not None
    }
    if not task_numbers:
        return "partial_unknown"
    for session in ("session_1", "session_2", "session_3"):
        if task_numbers.issubset(set(SESSION_TASK_GATES[session])):
            return session
    return "partial_unknown"


def _infer_repeat_status(
    task_occurrences: int,
    direction_consistent: Optional[bool],
    quality_consistent: Optional[bool],
) -> str:
    if task_occurrences < 2:
        return "not_repeated"
    if direction_consistent is None or quality_consistent is None:
        return "insufficient"
    if direction_consistent and quality_consistent:
        return "repeated_stable"
    return "repeated_unstable"


def _feature_direction(feature: Dict[str, Any]) -> Optional[str]:
    delta = feature.get("delta") or feature.get("effect_measure")
    if delta is None:
        return None
    return "increase" if float(delta) > 0 else ("decrease" if float(delta) < 0 else "neutral")


def _band_from_metric(metric_name: str) -> Optional[str]:
    m = metric_name.lower()
    for band in ("delta", "theta1", "theta2", "theta",
                 "lowalpha", "highalpha", "lowbeta", "highbeta",
                 "lowgamma", "midgamma", "gamma", "alpha", "beta"):
        if m.startswith(band):
            return band
    return "ratio" if "ratio" in m else None


def _preliminary_reliability_from_baseline(existing_analysis: Dict[str, Any]) -> str:
    """Quick reliability estimate from baseline QC counters only (no task features)."""
    kept     = existing_analysis.get("baseline_kept", 0) or 0
    rejected = existing_analysis.get("baseline_rejected", 0) or 0
    total    = kept + rejected
    if total == 0:
        return "unknown"
    rate = kept / total
    if rate >= 0.70:
        return "high"
    if rate >= 0.40:
        return "medium"
    return "low"


def _compute_session_confidence_cap(
    session_depth: str,
    global_reliability: str,
) -> Dict[str, Any]:
    """Return the effective confidence cap block for downstream agents.

    Combines session-depth cap with global-reliability cap, taking the
    stricter (lower) for each dimension.
    """
    s_cap = _SESSION_CAPS.get(session_depth, _SESSION_CAPS["partial_unknown"])
    rel_cap_str = _RELIABILITY_CONFIDENCE_CAP.get(global_reliability, "weak")

    def _min_strength(a: str, b: str) -> str:
        ai = _STRENGTH_ORDER.index(a) if a in _STRENGTH_ORDER else 1
        bi = _STRENGTH_ORDER.index(b) if b in _STRENGTH_ORDER else 1
        return _STRENGTH_ORDER[min(ai, bi)]

    eff_trait = _min_strength(s_cap["implicit_trait_max"], rel_cap_str)
    eff_role  = _min_strength(s_cap["role_recommendation_max"], rel_cap_str)

    cap_reasons = [s_cap["reason"]]
    if global_reliability == "medium":
        cap_reasons.append("Global reliability is MEDIUM -- confidence capped at MODERATE.")
    elif global_reliability == "low":
        cap_reasons.append("Global reliability is LOW -- confidence capped at WEAK.")

    return {
        "implicit_trait_max":        eff_trait,
        "role_recommendation_max":   eff_role,
        "applied_session_cap":       s_cap["implicit_trait_max"],
        "applied_reliability_cap":   rel_cap_str,
        "reason":                    " ".join(cap_reasons),
    }


# ---------------------------------------------------------------------------
# Statistical gate transparency
# ---------------------------------------------------------------------------

def _gate_transparency(
    metric_name: str,
    feature_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the per-feature statistical gate transparency block.

    Lets downstream agents understand *why* a feature passed or failed,
    rather than seeing only the final strength label.
    """
    q_val   = feature_stats.get("q_value")
    d_abs   = abs(feature_stats.get("effect_size_d") or 0.0)
    pct_abs = abs(feature_stats.get("percent_change") or 0.0)
    flags   = feature_stats.get("decision_flags", {})
    pass_rule = flags.get("pass_rule")   # "p" | "d" | "pct" | None

    d_thr   = _effect_size_threshold_for_metric(metric_name)
    pct_thr = _pct_threshold_for_metric(metric_name)

    passes_q   = bool(q_val is not None and q_val <= 0.0119377)
    passes_eff = bool(d_abs >= d_thr)
    passes_pct = bool(pct_abs >= pct_thr)
    # Strict statistical gate = FDR q-value only
    passes_stat_gate = passes_q

    # Determine what drove the significant_change flag
    if passes_q:
        sig_basis = "fdr_q_value"
    elif pass_rule == "p":
        sig_basis = "directional_p_value"
    elif passes_eff and passes_pct:
        sig_basis = "effect_size_percent_fallback"
    elif pass_rule == "d" or passes_eff:
        sig_basis = "effect_size_fallback"
    elif pass_rule == "pct" or passes_pct:
        sig_basis = "percent_change_fallback"
    else:
        sig_basis = "none"

    # Interpretation safety
    if passes_q and passes_eff:
        interp = "standard"
    elif passes_q or flags.get("p_pass") or (passes_eff and passes_pct):
        interp = "use_with_caution"
    elif passes_eff or passes_pct:
        interp = "use_with_caution"
    else:
        interp = "do_not_use"

    return {
        "passes_q_value":                  passes_q,
        "passes_effect_size_threshold":    passes_eff,
        "passes_percent_change_threshold": passes_pct,
        "passes_statistical_gate":         passes_stat_gate,
        "significance_basis":              sig_basis,
        "interpretation_safety":           interp,
        "effect_size_threshold_used":      d_thr,
        "percent_change_threshold_used":   pct_thr,
    }


def _sample_counts(feature_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Extract baseline/task block counts and means from analyzer output."""
    n_base = feature_stats.get("n_blocks_baseline")
    n_task = feature_stats.get("n_blocks_task")
    eff    = min(n_base or 0, n_task or 0) or None
    return {
        "baseline_block_count":  n_base,
        "task_block_count":      n_task,
        "effective_sample_size": eff,
        "task_mean":             feature_stats.get("task_mean"),
        "baseline_mean":         feature_stats.get("baseline_mean"),
        "delta":                 feature_stats.get("delta"),
    }


# ---------------------------------------------------------------------------
# Feature builder
# ---------------------------------------------------------------------------

def _build_neuroprofile_feature(
    metric_name: str,
    feature_stats: Dict[str, Any],
    canonical_task_id: str,
    convergent: bool = False,
    expectation_grade: Optional[str] = None,
    insufficient_metrics: bool = False,
    reliability: str = "unknown",
) -> Dict[str, Any]:
    """Build a single neuroprofile feature dict from existing analyzer stats."""
    family    = classify_feature_family(metric_name)
    direction = _feature_direction(feature_stats)

    # Raw strength (unscaled by reliability)
    raw_strength = classify_feature_strength({
        **feature_stats,
        "metric_name":           metric_name,
        "feature_family":        family,
        "grade":                 expectation_grade,
        "_insufficient_metrics": insufficient_metrics,
    })
    # Apply reliability cap
    strength = _apply_reliability_cap(raw_strength, reliability)

    gate_pass = passes_neuroprofile_gate({
        **feature_stats,
        "metric_name":    metric_name,
        "feature_family": family,
    })

    rm_status       = role_matching_status_for_task(canonical_task_id)
    characteristics = map_feature_to_characteristics(
        canonical_task_id, metric_name, family, direction, strength
    )
    abilities = allowed_abilities_for_task(canonical_task_id, strength, convergent)
    blocked   = blocked_inferences_for_task(canonical_task_id)

    # Statistical gate transparency (v7.1)
    gate_info = _gate_transparency(metric_name, feature_stats)

    # Sample counts / means (v7.1)
    counts = _sample_counts(feature_stats)

    # Short bounded rationale
    if family in ("spectral_power", "relative_power", "band_ratio"):
        rationale = (
            f"EEG {family.replace('_', ' ')} change during "
            f"{canonical_task_id.replace('_', ' ')} treated as task-contextual evidence. "
            f"Significance basis: {gate_info['significance_basis']}."
        )
    else:
        rationale = (
            f"Feature family '{family}' during {canonical_task_id.replace('_', ' ')}. "
            f"Significance basis: {gate_info['significance_basis']}."
        )
    if blocked:
        rationale += f" Blocked inferences: {', '.join(blocked[:3])}."

    return {
        # --- Identity ---
        "metric_name":    metric_name,
        "feature_family": family,
        "band":           _band_from_metric(metric_name),
        # --- Core statistics ---
        "effect_size_d":  feature_stats.get("effect_size_d"),
        "p_value":        feature_stats.get("p_value"),
        "q_value":        feature_stats.get("q_value"),
        "percent_change": feature_stats.get("percent_change"),
        "direction":      direction,
        "grade":          expectation_grade,
        # --- Statistical gate transparency (v7.1) ---
        **gate_info,
        # --- Sample basis (v7.1) ---
        **counts,
        # --- Neuroprofile gate ---
        "passes_neuroprofile_gate":        gate_pass,
        "feature_strength":                strength,
        "feature_strength_before_cap":     raw_strength,
        # --- Mapping outputs ---
        "task_supported_characteristics":  characteristics,
        "allowed_onet_ability_candidates": abilities,
        "blocked_inferences":              blocked,
        "role_matching_status":            rm_status,
        "neuroprofile_rationale":          rationale,
    }


# ---------------------------------------------------------------------------
# Signal quality
# ---------------------------------------------------------------------------

def _signal_quality_for_task(
    features: List[Dict[str, Any]],
    analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """Summarise signal quality for one task from its feature list."""
    artifact_flags = []
    usable   = sum(1 for f in features if f["passes_neuroprofile_gate"])
    rejected = sum(1 for f in features if not f["passes_neuroprofile_gate"])
    emg_count = sum(
        1 for entry in analysis.values()
        if isinstance(entry, dict) and entry.get("_emg_guard", 0) == 1
    )
    if emg_count:
        artifact_flags.append(f"emg_guard_fired_on_{emg_count}_windows")
    if not features:
        return {
            "quality_level": "unknown", "artifact_flags": artifact_flags,
            "usable_feature_count": 0, "rejected_feature_count": 0,
            "notes": ["No features computed"],
        }
    frac = usable / max(1, len(features))
    quality = "high" if frac >= 0.60 else ("medium" if frac >= 0.30 else "low")
    return {
        "quality_level":          quality,
        "artifact_flags":         artifact_flags,
        "usable_feature_count":   usable,
        "rejected_feature_count": rejected,
        "notes": [],
    }


# ---------------------------------------------------------------------------
# Task summary block
# ---------------------------------------------------------------------------

def _task_summary_block(
    canonical_task_id: str,
    features: List[Dict[str, Any]],
    reliability: str = "unknown",
) -> Dict[str, Any]:
    """Build per-task summary; applies reliability cap to confidence."""
    all_chars:     List[str] = []
    all_abilities: List[str] = []
    all_blocked             = blocked_inferences_for_task(canonical_task_id)
    mod_chars:     List[str] = []

    for feat in features:
        if feat["passes_neuroprofile_gate"]:
            all_chars.extend(feat["task_supported_characteristics"])
            all_abilities.extend(feat["allowed_onet_ability_candidates"])

    # Deduplicate, preserve order
    seen_c: set = set();  unique_chars:     List[str] = []
    for c in all_chars:
        if c not in seen_c: seen_c.add(c); unique_chars.append(c)
    seen_a: set = set();  unique_abilities: List[str] = []
    for a in all_abilities:
        if a not in seen_a: seen_a.add(a); unique_abilities.append(a)

    if canonical_task_id in _MODERATOR_ONLY_TASKS:
        matrix = _TASK_MATRIX.get(canonical_task_id, {})
        mod_chars = list(matrix.get("characteristics", []))
        unique_chars     = []
        unique_abilities = []

    strong_ct  = sum(1 for f in features if f.get("feature_strength") == "strong")
    mod_ct     = sum(1 for f in features if f.get("feature_strength") == "moderate")
    weak_ct    = sum(1 for f in features if f.get("feature_strength") == "weak")
    total_pass = sum(1 for f in features if f.get("passes_neuroprofile_gate"))

    if total_pass == 0:
        raw_confidence = "insufficient"
    elif strong_ct >= 2:
        raw_confidence = "strong"
    elif strong_ct >= 1 or mod_ct >= 2:
        raw_confidence = "moderate"
    elif mod_ct >= 1 or weak_ct >= 2:
        raw_confidence = "weak"
    else:
        raw_confidence = "insufficient"

    # Apply reliability cap (does not cap "insufficient")
    confidence = (
        _apply_reliability_cap(raw_confidence, reliability)
        if raw_confidence != "insufficient"
        else "insufficient"
    )

    rm = role_matching_status_for_task(canonical_task_id)
    rel_cap_label = _RELIABILITY_CONFIDENCE_CAP.get(reliability, "weak")
    summary_text = (
        f"Task-contextual EEG evidence for {canonical_task_id.replace('_', ' ')}. "
        f"Role matching: {rm}. "
        f"Confidence: {confidence} (reliability cap: {rel_cap_label})."
    )

    return {
        "supported_characteristics":       unique_chars,
        "allowed_onet_ability_candidates": unique_abilities,
        "moderator_characteristics":       mod_chars,
        "blocked_inferences":              all_blocked,
        "confidence":                      confidence,
        "confidence_before_cap":           raw_confidence,
        "summary":                         summary_text,
    }


# ---------------------------------------------------------------------------
# Task entry builder
# ---------------------------------------------------------------------------

def build_neuroprofile_task_entry(
    raw_task_id: str,
    analysis: Dict[str, Any],
    summary: Dict[str, Any],
    reliability: str = "unknown",
) -> Dict[str, Any]:
    """Build a full task entry for the neuroprofile export block."""
    canonical_task_id = resolve_canonical_task(raw_task_id) or raw_task_id
    task_number       = canonical_task_number(canonical_task_id)
    task_info         = CANONICAL_TASKS.get(task_number, {}) if task_number else {}
    rm_status         = role_matching_status_for_task(canonical_task_id)

    exp_grade: Optional[str] = None
    insufficient_metrics: bool = False
    if summary:
        exp_block = summary.get("expectation") or {}
        raw_grade = exp_block.get("grade")
        insufficient_metrics = bool(exp_block.get("insufficient_metrics", False))
        if raw_grade in ("A", "B", "C") and not insufficient_metrics:
            exp_grade = raw_grade

    raw_features: list = []
    for metric_name, feat_stats in analysis.items():
        if not isinstance(feat_stats, dict) or metric_name.startswith("_"):
            continue
        fam = classify_feature_family(metric_name)
        if fam in ("signal_quality", "unknown"):
            continue
        dir_ = _feature_direction(feat_stats)
        raw_features.append((metric_name, feat_stats, fam, dir_))

    convergence_counts: Dict[tuple, int] = {}
    for _, _, fam, dir_ in raw_features:
        k = (fam, dir_ or "")
        convergence_counts[k] = convergence_counts.get(k, 0) + 1

    features_out: List[Dict[str, Any]] = []
    for metric_name, feat_stats, fam, dir_ in raw_features:
        k = (fam, dir_ or "")
        convergent = convergence_counts.get(k, 0) > 1
        f_entry = _build_neuroprofile_feature(
            metric_name, feat_stats, canonical_task_id,
            convergent=convergent,
            expectation_grade=exp_grade,
            insufficient_metrics=insufficient_metrics,
            reliability=reliability,
        )
        features_out.append(f_entry)

    sig_quality  = _signal_quality_for_task(features_out, analysis)
    task_summary = _task_summary_block(canonical_task_id, features_out, reliability)

    return {
        "task_number":          task_number,
        "canonical_task_id":    canonical_task_id,
        "canonical_task_name":  task_info.get("name", canonical_task_id),
        "raw_task_labels":      [raw_task_id],
        "repeat_status":        "not_repeated",
        "role_matching_status": rm_status,
        "signal_quality":       sig_quality,
        "features":             features_out,
        "task_summary":         task_summary,
    }


# ---------------------------------------------------------------------------
# Global quality
# ---------------------------------------------------------------------------

def compute_neuroprofile_global_quality(
    existing_analysis: Dict[str, Any],
    neuroprofile_tasks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return high/medium/low/unknown reliability for the full session."""
    baseline_kept     = existing_analysis.get("baseline_kept", 0) or 0
    baseline_rejected = existing_analysis.get("baseline_rejected", 0) or 0
    not_worn          = existing_analysis.get("baseline_rejected_not_worn", 0) or 0
    artifact          = existing_analysis.get("baseline_rejected_artifact", 0) or 0
    flatline          = existing_analysis.get("baseline_rejected_flatline", 0) or 0

    gamma_guard_count = sum(
        1 for t in neuroprofile_tasks
        if any("emg_guard" in flag
               for flag in t.get("signal_quality", {}).get("artifact_flags", []))
    )

    total_baseline = baseline_kept + baseline_rejected
    if total_baseline == 0:
        return {
            "overall_reliability":        "unknown",
            "baseline_kept":              None,
            "baseline_rejected":          None,
            "baseline_rejected_not_worn": None,
            "baseline_rejected_artifact": None,
            "baseline_rejected_flatline": None,
            "gamma_guard_count":          None,
            "notes":                      ["No baseline metadata"],
        }

    baseline_keep_rate = baseline_kept / total_baseline
    total_usable = sum(
        t.get("signal_quality", {}).get("usable_feature_count", 0)
        for t in neuroprofile_tasks
    )
    total_features = sum(
        t.get("signal_quality", {}).get("usable_feature_count", 0) +
        t.get("signal_quality", {}).get("rejected_feature_count", 0)
        for t in neuroprofile_tasks
    )
    feat_keep_rate = total_usable / max(1, total_features)

    notes = []
    if baseline_keep_rate >= 0.70 and feat_keep_rate >= 0.60 and gamma_guard_count <= 1:
        reliability = "high"
    elif baseline_keep_rate >= 0.40 and feat_keep_rate >= 0.30:
        reliability = "medium"
        notes.append("Partial data quality; some features or baseline windows rejected.")
    else:
        reliability = "low"
        notes.append("Major quality issues: high artifact rate or low baseline yield.")

    for label, val in [("not-worn", not_worn), ("artifact", artifact), ("flatline", flatline)]:
        if val:
            notes.append(f"Baseline {label} windows: {val}.")

    return {
        "overall_reliability":        reliability,
        "baseline_kept":              baseline_kept,
        "baseline_rejected":          baseline_rejected,
        "baseline_rejected_not_worn": not_worn,
        "baseline_rejected_artifact": artifact,
        "baseline_rejected_flatline": flatline,
        "gamma_guard_count":          gamma_guard_count,
        "notes":                      notes,
    }


# ---------------------------------------------------------------------------
# Top-level export builder
# ---------------------------------------------------------------------------

def build_neuroprofile_export(
    per_task: Dict[str, Any],
    existing_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the top-level ``neuroprofile_feature_export`` block.

    Args:
        per_task:          The ``per_task`` dict from the /analyze response.
        existing_analysis: The full /analyze response (for baseline QC counters).

    JSON shape (v2):
        feature_report_version, traceability_version, protocol_session_depth,
        headset_scope, global_reliability (flat str), baseline_qc (flat dict),
        session_confidence_cap, allowed_ability_pool,
        moderator_only_characteristics, blocked_unsupported_labels,
        feature_rows (flat denormalized array — primary for Implicit Agent),
        tasks (primary nested), tasks_detected (backward-compat alias), global_quality.
    """
    # Step 1: preliminary reliability from baseline QC only (no task data yet).
    prelim_reliability = _preliminary_reliability_from_baseline(existing_analysis)

    # Step 2: build task entries using the preliminary reliability cap.
    tasks, allowed_ability_pool, moderator_chars, blocked_unsupported, all_canonical_ids = \
        _build_all_task_entries(per_task, prelim_reliability)

    # Step 3: final global quality (uses task feature quality data).
    session_depth  = _infer_session_depth(all_canonical_ids)
    global_quality = compute_neuroprofile_global_quality(existing_analysis, tasks)
    final_reliability = global_quality["overall_reliability"]

    # Step 4: re-build if the final reliability differs from the preliminary estimate.
    if final_reliability != prelim_reliability:
        tasks, allowed_ability_pool, moderator_chars, blocked_unsupported, _ = \
            _build_all_task_entries(per_task, final_reliability)

    # Step 5: session confidence cap (combined session-depth + reliability).
    session_cap = _compute_session_confidence_cap(session_depth, final_reliability)

    # Step 6: flat baseline_qc block.
    baseline_qc = {
        "kept":     global_quality.get("baseline_kept"),
        "rejected": global_quality.get("baseline_rejected"),
        "not_worn": global_quality.get("baseline_rejected_not_worn"),
        "artifact": global_quality.get("baseline_rejected_artifact"),
        "flatline": global_quality.get("baseline_rejected_flatline"),
    }

    # Step 7: flat feature_rows for Implicit Agent consumption.
    feature_rows = _build_feature_rows(tasks)

    return {
        # Identity / version
        "feature_report_version":         NEUROPROFILE_EXPORT_VERSION,
        "traceability_version":           TRACEABILITY_VERSION,
        "protocol_session_depth":         session_depth,
        "headset_scope":                  "frontal/frontopolar, Fp1/Fp2-compatible",
        # Quality summary — flat for easy Implicit Agent consumption
        "global_reliability":             final_reliability,
        "baseline_qc":                    baseline_qc,
        # Confidence cap for downstream agents
        "session_confidence_cap":         session_cap,
        # Ability / characteristic pools
        "allowed_ability_pool":           allowed_ability_pool,
        "moderator_only_characteristics": moderator_chars,
        "blocked_unsupported_labels":     blocked_unsupported,
        # Flat feature rows — primary machine-readable format for Implicit Agent
        "feature_rows":                   feature_rows,
        # Per-task evidence — nested, for human review / structured traversal
        "tasks":                          tasks,
        # Backward-compatibility alias (same list object)
        "tasks_detected":                 tasks,
        # Full quality detail
        "global_quality":                 global_quality,
    }


def _build_feature_rows(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a flat, denormalized list of feature dicts for Implicit Agent use.

    Each row is a single feature enriched with its parent task context fields
    so the agent can filter/rank without nested traversal.

    Task context fields prepended to every row:
        task_number, canonical_task_id, canonical_task_name,
        task_role_matching_status, task_signal_quality, task_confidence,
        task_confidence_before_cap.

    Feature fields included verbatim (subset — excludes bulky list fields that
    are already aggregated at the export level):
        metric_name, feature_family, band, direction, grade,
        effect_size_d, p_value, q_value, percent_change,
        passes_q_value, passes_effect_size_threshold,
        passes_percent_change_threshold, passes_statistical_gate,
        significance_basis, interpretation_safety,
        effect_size_threshold_used, percent_change_threshold_used,
        baseline_block_count, task_block_count, effective_sample_size,
        task_mean, baseline_mean, delta,
        passes_neuroprofile_gate, feature_strength, feature_strength_before_cap,
        role_matching_status,
        task_supported_characteristics (list),
        allowed_onet_ability_candidates (list),
        blocked_inferences (list).
    """
    # Fields to carry through verbatim from the feature dict.
    _FEATURE_FIELDS = (
        "metric_name", "feature_family", "band", "direction", "grade",
        "effect_size_d", "p_value", "q_value", "percent_change",
        "passes_q_value", "passes_effect_size_threshold",
        "passes_percent_change_threshold", "passes_statistical_gate",
        "significance_basis", "interpretation_safety",
        "effect_size_threshold_used", "percent_change_threshold_used",
        "baseline_block_count", "task_block_count", "effective_sample_size",
        "task_mean", "baseline_mean", "delta",
        "passes_neuroprofile_gate", "feature_strength", "feature_strength_before_cap",
        "role_matching_status",
        "task_supported_characteristics",
        "allowed_onet_ability_candidates",
        "blocked_inferences",
    )

    rows: List[Dict[str, Any]] = []
    for task in tasks:
        ts = task.get("task_summary", {})
        task_ctx = {
            "task_number":              task.get("task_number"),
            "canonical_task_id":        task.get("canonical_task_id"),
            "canonical_task_name":      task.get("canonical_task_name"),
            "task_role_matching_status": task.get("role_matching_status"),
            "task_signal_quality":      task.get("signal_quality", {}).get("quality_level"),
            "task_confidence":          ts.get("confidence"),
            "task_confidence_before_cap": ts.get("confidence_before_cap"),
        }
        for feat in task.get("features", []):
            row = dict(task_ctx)
            for field in _FEATURE_FIELDS:
                row[field] = feat.get(field)
            rows.append(row)
    return rows


def _build_all_task_entries(
    per_task: Dict[str, Any],
    reliability: str,
) -> tuple:
    """Helper — builds task entries for all tasks in per_task.

    Returns (tasks, allowed_ability_pool, moderator_chars, blocked_unsupported,
             all_canonical_ids).
    """
    tasks:               List[Dict[str, Any]] = []
    all_canonical_ids:   List[str] = []
    allowed_ability_pool: List[str] = []
    moderator_chars:     List[str] = []
    blocked_unsupported: List[str] = []

    for raw_task_id, task_result in per_task.items():
        analysis = task_result.get("analysis", {})
        summary  = task_result.get("summary", {})
        entry    = build_neuroprofile_task_entry(
            raw_task_id, analysis, summary, reliability=reliability
        )
        tasks.append(entry)
        canonical_id = entry["canonical_task_id"]
        all_canonical_ids.append(canonical_id)

        task_blocked = set(blocked_inferences_for_task(canonical_id))
        for ability in entry["task_summary"].get("allowed_onet_ability_candidates", []):
            if ability not in task_blocked and ability not in allowed_ability_pool:
                allowed_ability_pool.append(ability)
        for mc in entry["task_summary"].get("moderator_characteristics", []):
            if mc not in moderator_chars:
                moderator_chars.append(mc)
        for bl in task_blocked:
            if bl not in blocked_unsupported:
                blocked_unsupported.append(bl)

    return tasks, allowed_ability_pool, moderator_chars, blocked_unsupported, all_canonical_ids
