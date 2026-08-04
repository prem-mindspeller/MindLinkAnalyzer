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
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Version stamps
# ---------------------------------------------------------------------------
TRACEABILITY_VERSION        = "mindspeller_eeg_feature_traceability_v8"
NEUROPROFILE_EXPORT_VERSION = "mindspeller_eeg_feature_report_v3"

# The task engine consumes the concrete resources referenced by this profile;
# the backend records and validates their provenance.  Swapping a candidate
# pack for a normed pack therefore changes configuration rather than analysis
# code.  A profile may call itself ``validated`` only when every component is
# independently marked validated and carries a content anchor.  Either a
# ``content_hash`` (integrity identity) or ``config_uri`` (publisher-governed,
# pinned resource identity) is accepted.  This module validates the declared
# provenance contract; it deliberately does not fetch URIs or hash resources.
PROTOCOL_PROFILE_CONTRACT_VERSION = "mindspeller_protocol_profile_v1"
PROTOCOL_PROFILE_COMPONENTS = ("stimuli", "audio", "rubrics", "thresholds")
PROTOCOL_PROFILE_VALIDATION_STATUSES = {"candidate", "pilot", "validated"}

# ---------------------------------------------------------------------------
# Session task gates
# ---------------------------------------------------------------------------
SESSION_TASK_GATES: Dict[str, List[int]] = {
    # Cumulative protocol depth; list order is the prescribed presentation
    # order rather than numeric task order (optimization PDF pp. 48-50).
    "session_1": [3, 2, 1, 4],
    "session_2": [3, 2, 1, 4, 6, 7, 9, 5, 8],
    "session_3": [3, 2, 1, 4, 6, 7, 11, 9, 5, 8, 10, 12],
}

# ---------------------------------------------------------------------------
# Canonical tasks
# ---------------------------------------------------------------------------
CANONICAL_TASKS: Dict[int, Dict[str, str]] = {
    1:  {"id": "adaptive_numerical_reasoning", "name": "Adaptive Numerical Reasoning and Sequencing", "baseline": "eyes_closed"},
    2:  {"id": "working_memory_manipulation", "name": "Working-Memory Manipulation", "baseline": "eyes_closed"},
    3:  {"id": "auditory_target_counting", "name": "Auditory Target Counting", "baseline": "eyes_closed"},
    4:  {"id": "semantic_induction_category_switching", "name": "Semantic Induction and Category Switching", "baseline": "eyes_closed"},
    5:  {"id": "visuospatial_transformation_orientation", "name": "Visuospatial Transformation and Orientation", "baseline": "eyes_open"},
    6:  {"id": "divergent_ideation", "name": "Divergent Ideation", "baseline": "eyes_closed"},
    7:  {"id": "dual_task_rule_switching", "name": "Dual-Task Performance and Rule Switching", "baseline": "eyes_closed"},
    8:  {"id": "rule_based_anomaly_detection", "name": "Rule-Based Anomaly Detection", "baseline": "eyes_open"},
    9:  {"id": "rapid_visual_comparison", "name": "Rapid Visual Comparison", "baseline": "eyes_open"},
    10: {"id": "pattern_closure_visual_noise", "name": "Pattern Closure under Visual Noise", "baseline": "eyes_open"},
    11: {"id": "speech_in_noise_comprehension", "name": "Speech-in-Noise Comprehension", "baseline": "eyes_closed"},
    12: {"id": "written_comprehension_synthesis", "name": "Written Comprehension and Concise Synthesis", "baseline": "eyes_open"},
}

# Protocol-specified scored EEG durations from Task_Battery_Optimization.pdf p. 47.
# These are protocol durations, not appointment/slot estimates.
TASK_RECORDING_DURATIONS_SECONDS: Dict[str, int] = {
    # Task 1 shortened from the page-47 example's 90s to 60s; stimulus pacing
    # was preserved by removing operations rather than compressing the
    # interval between them (see optimizedBatteryConfig.mjs NUMERICAL_FORMS).
    CANONICAL_TASKS[1]["id"]: 60,
    # Task 2 shortened from the page-47 example's 90s to 60s; the
    # manipulation-phase command count was reduced (6 -> 4) to keep its pace
    # close to the original (see MEMORY_FORMS in optimizedBatteryConfig.mjs).
    # The 2 maintenance-phase commands are already at their structural
    # minimum, so that phase's spacing necessarily compresses (25s -> 10s).
    CANONICAL_TASKS[2]["id"]: 60,
    # Task 3 shortened from the page-47 example's 120s to 75s, not 60s: its 3
    # equal analysis phases would sit at exactly the 20-contiguous-clean-second
    # floor with zero margin at 60s, so 25s/phase (75s total) keeps a real
    # buffer. Tone/target counts were reduced (not the interval) to preserve
    # pacing and target density (see AUDITORY_FORMS in optimizedBatteryConfig.mjs).
    CANONICAL_TASKS[3]["id"]: 75,
    # Task 4 shortened from the page-47 example's 90s to 60s; item count per
    # phase was reduced (15 -> 10) rather than compressing the interval, so
    # the pace is exactly unchanged (3s/item either way -- see itemsPerPhase
    # and SEMANTIC_FORMS in optimizedBatteryConfig.mjs).
    CANONICAL_TASKS[4]["id"]: 60,
    # Task 5 shortened from the page-47 example's 90s to 60s; move counts were
    # reduced (4 lower + 7 higher -> 3 + 5) to preserve pacing rather than
    # compress it. The higher-density pace stays close to the original
    # (7s -> 6.75s); the lower-density pace still compresses (11s -> 9s)
    # since only 18s of span is available once the phase itself is 30s
    # (see ROUTE_FORMS in optimizedBatteryConfig.mjs).
    CANONICAL_TASKS[5]["id"]: 60,
    # Task 6 shortened from the page-47 example's 120s to 75s (25s/phase),
    # matching Task 3's same 3-equal-phase shape: a flat 60s (20s/phase) would
    # sit exactly on the 20-contiguous-clean-second floor with zero slack.
    # Behavioral scoring (minimumRelevantIdeas/etc.) is against the whole
    # response, not per-phase, so only the EEG early/middle/late comparison
    # ever carried this risk -- 25s/phase removes it.
    CANONICAL_TASKS[6]["id"]: 75,
    # Task 7 shortened from the page-47 example's 120s to 60s. Unlike other
    # tasks in this batch, the 3+3 update structure was kept rather than
    # reduced (per explicit user request), so its spacing compresses
    # uniformly by half (~20s -> ~9-10s apart) instead of being preserved.
    # The tone stream was trimmed the same way as Task 3's, to preserve
    # pacing. maximumSwitchCost's threshold did not need re-deriving, since
    # it assumes exactly 3 post-switch updates and that count didn't change.
    CANONICAL_TASKS[7]["id"]: 60,
    # Task 8 shortened from the page-47 example's 90s to 60s. entryIntervalSeconds
    # is a fixed 2s cadence (not derived from a span/count division), so the
    # pace was automatically unchanged -- entryCount just dropped (45 -> 30).
    # Anomaly slot positions were rescaled to the new phase boundaries and
    # reduced proportionally (3 lower + 6 higher -> 2 + 4) to keep the
    # lower/higher density ratio close to the original (see anomalyForm in
    # optimizedBatteryConfig.mjs).
    CANONICAL_TASKS[8]["id"]: 60,
    CANONICAL_TASKS[9]["id"]: 60,
    CANONICAL_TASKS[10]["id"]: 75,
    CANONICAL_TASKS[11]["id"]: 120,
    CANONICAL_TASKS[12]["id"]: 180,
}

_DEFAULT_CANDIDATE_COMPONENTS: Dict[str, Dict[str, str]] = {
    "stimuli": {
        "id": "mindspeller_parallel_forms_en",
        "version": "2.0.0-candidate.1",
        "validation_status": "candidate",
    },
    "audio": {
        "id": "mindspeller_browser_generated_audio",
        "version": "1.0.0-candidate.1",
        "validation_status": "candidate",
    },
    "rubrics": {
        "id": "mindspeller_candidate_rubrics",
        "version": "1.0.0-candidate.1",
        "validation_status": "candidate",
    },
    "thresholds": {
        "id": "mindspeller_candidate_thresholds",
        "version": "1.0.0-candidate.1",
        "validation_status": "candidate",
    },
}

_CANONICAL_ID_TO_NUMBER: Dict[str, int] = {
    v["id"]: k for k, v in CANONICAL_TASKS.items()
}

TASK_BASELINE_CONDITIONS: Dict[str, str] = {
    task["id"]: task["baseline"] for task in CANONICAL_TASKS.values()
}

# ---------------------------------------------------------------------------
# Task name aliases
# ---------------------------------------------------------------------------
TASK_NAME_ALIASES: Dict[str, str] = {
    **{task["id"]: task["id"] for task in CANONICAL_TASKS.values()},
    **{str(number): task["id"] for number, task in CANONICAL_TASKS.items()},

    "adaptive_numerical_reasoning_and_sequencing": "adaptive_numerical_reasoning",
    "semantic_induction_and_category_switching": "semantic_induction_category_switching",
    "visuospatial_transformation_and_orientation": "visuospatial_transformation_orientation",
    "dual_task_performance_and_rule_switching": "dual_task_rule_switching",
    "pattern_closure_under_visual_noise": "pattern_closure_visual_noise",
    "written_comprehension_and_concise_synthesis": "written_comprehension_synthesis",
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
_MODERATOR_ONLY_TASKS: set = set()

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
            "Session 1 only (Tasks 3, 2, 1, and 4); no repeated-task stability or "
            "executive expansion tasks available. "
            "Latent traits require convergence across tasks and sessions."
        ),
    },
    "session_2": {
        "implicit_trait_max":      "strong",
        "role_recommendation_max": "moderate",
        "reason": (
            "Session 2 foundational plus creativity, dual-task, visual-speed, "
            "spatial, and anomaly-detection tasks; executive expansion available "
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
_CONTINUOUS_EEG_FAMILIES = {
    "spectral_power", "relative_power", "band_ratio",
    "entropy_complexity", "transition_recovery", "task_summary_stat",
}

_TASK_MATRIX: Dict[str, Dict[str, Any]] = {
    "adaptive_numerical_reasoning": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["continuous_numerical_updating", "calculation_load_change", "ordered_rule_application", "sustained_control_during_calculation"],
        "allowed_abilities": ["Mathematical Reasoning", "Number Facility", "Information Ordering", "Deductive Reasoning"],
        "blocked": ["Inductive Reasoning", "Memorization", "Reaction Time", "Oral Comprehension", "Oral Expression"],
    },
    "working_memory_manipulation": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["continuous_sequence_maintenance", "working_memory_manipulation", "ordered_updates", "maintenance_to_manipulation_load_change"],
        "allowed_abilities": ["Memorization", "Information Ordering", "Deductive Reasoning"],
        "blocked": ["Inductive Reasoning", "Category Flexibility", "Time Sharing", "Number Facility", "Mathematical Reasoning", "Oral Comprehension"],
    },
    "auditory_target_counting": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["sustained_target_monitoring", "auditory_distractor_resistance", "attention_stability", "attention_drift"],
        "allowed_abilities": ["Selective Attention", "Auditory Attention"],
        "blocked": ["Reaction Time", "Speech Recognition", "Oral Comprehension", "Time Sharing", "Problem Sensitivity"],
    },
    "semantic_induction_category_switching": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["continuous_semantic_comparison", "rule_inference", "semantic_rule_change", "rule_selection_demand"],
        "allowed_abilities": ["Inductive Reasoning", "Category Flexibility"],
        "blocked": ["Deductive Reasoning", "Memorization", "Fluency of Ideas", "Originality", "Oral Comprehension"],
    },
    "visuospatial_transformation_orientation": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["continuous_visual_tracking", "spatial_state_updating", "orientation_tracking", "controlled_spatial_transformation"],
        "allowed_abilities": ["Visualization", "Spatial Orientation"],
        "blocked": ["Perceptual Speed", "Speed of Closure", "Flexibility of Closure", "Reaction Time", "Visual Sensory Abilities"],
    },
    "divergent_ideation": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["continuous_ideation", "idea_generation_dynamics", "associative_breadth", "internal_attention_dynamics"],
        "allowed_abilities": ["Category Flexibility", "Fluency of Ideas", "Originality"],
        "blocked": ["Written Expression", "Oral Expression", "Inductive Reasoning", "Deductive Reasoning", "Visualization"],
    },
    "dual_task_rule_switching": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["dual_task_interference_management", "rule_switching_demand", "competing_stream_control", "dual_task_cost_context"],
        "allowed_abilities": ["Time Sharing", "Category Flexibility", "Deductive Reasoning", "Selective Attention", "Information Ordering"],
        "blocked": ["Mathematical Reasoning", "Number Facility", "Memorization", "Reaction Time", "Auditory Attention"],
    },
    "rule_based_anomaly_detection": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["continuous_rule_monitoring", "anomaly_monitoring", "visual_inspection", "conflict_monitoring"],
        "allowed_abilities": ["Problem Sensitivity", "Deductive Reasoning", "Selective Attention", "Information Ordering"],
        "blocked": ["Inductive Reasoning", "Perceptual Speed", "Reaction Time", "Speed of Closure", "Flexibility of Closure"],
    },
    "rapid_visual_comparison": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["continuous_visual_comparison", "mismatch_monitoring", "pre_response_visual_state", "detection_latency_context"],
        "allowed_abilities": ["Perceptual Speed", "Reaction Time"],
        "blocked": ["Speed of Closure", "Flexibility of Closure", "Visualization", "Spatial Orientation", "Problem Sensitivity"],
    },
    "pattern_closure_visual_noise": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["pattern_extraction_under_noise", "distractor_resistance", "progressive_visual_closure", "recognition_threshold_context"],
        "allowed_abilities": ["Speed of Closure", "Flexibility of Closure"],
        "blocked": ["Perceptual Speed", "Spatial Orientation", "Problem Sensitivity", "Reaction Time", "Selective Attention"],
    },
    "speech_in_noise_comprehension": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["continuous_listening_effort", "speech_in_noise_attention", "auditory_attention_stability", "listening_effort_drift"],
        "allowed_abilities": ["Oral Comprehension", "Speech Recognition", "Auditory Attention"],
        "blocked": ["Oral Expression", "Speech Clarity", "Reaction Time", "Written Comprehension", "Written Expression"],
    },
    "written_comprehension_synthesis": {
        "eligible_families": _CONTINUOUS_EEG_FAMILIES,
        "characteristics": ["paced_reading_engagement", "silent_synthesis_planning", "meaning_integration", "response_organization_demand"],
        "allowed_abilities": ["Written Comprehension", "Written Expression", "Inductive Reasoning", "Information Ordering"],
        "blocked": ["Oral Comprehension", "Oral Expression", "Speech Recognition", "Speech Clarity", "Fluency of Ideas", "Originality"],
    },
}


# ===========================================================================
# Public helpers
# ===========================================================================

def resolve_canonical_task(raw_task_id: str) -> Optional[str]:
    """Return the canonical task ID for a raw task label, or None if unknown."""
    token = (raw_task_id or "").strip().lower()
    for separator in ("-", "‐", "‑", "‒", "–", "—", "/"):
        token = token.replace(separator, "_")
    token = token.replace("&", "and")
    token = "_".join(token.split())
    while "__" in token:
        token = token.replace("__", "_")
    return TASK_NAME_ALIASES.get(token.strip("_"))


def canonical_task_number(canonical_task_id: str) -> Optional[int]:
    """Return the 1-based task number for a canonical task ID."""
    return _CANONICAL_ID_TO_NUMBER.get(canonical_task_id)


def task_baseline_condition(canonical_task_id: str) -> Optional[str]:
    """Return the protocol-matched baseline condition for a canonical task."""
    return TASK_BASELINE_CONDITIONS.get(canonical_task_id)


_PROFILE_STATUS_ALIASES = {
    "candidate": "candidate",
    "research_candidate": "candidate",
    "research_candidate_not_normed": "candidate",
    "candidate_not_normed": "candidate",
    "pilot": "pilot",
    "pilot_not_normed": "pilot",
    "validated": "validated",
    "production_validated": "validated",
}


def normalize_protocol_validation_status(value: Any) -> Optional[str]:
    """Normalize profile/resource maturity without upgrading its claims."""
    if not isinstance(value, str):
        return None
    normalized = _PROFILE_STATUS_ALIASES.get(value.strip().lower())
    return normalized if normalized in PROTOCOL_PROFILE_VALIDATION_STATUSES else None


def candidate_protocol_profile() -> Dict[str, Any]:
    """Return a fresh copy of the built-in, explicitly non-normed profile."""
    return {
        "contract_version": PROTOCOL_PROFILE_CONTRACT_VERSION,
        "profile_id": "mindspeller_optimized_task_battery",
        "profile_version": "2.0.0-candidate.1",
        "validation_status": "pilot",
        "components": {
            name: dict(component)
            for name, component in _DEFAULT_CANDIDATE_COMPONENTS.items()
        },
        "task_durations_seconds": dict(TASK_RECORDING_DURATIONS_SECONDS),
        "normative_interpretation_allowed": False,
        "interpretation_scope": "candidate_or_pilot_only",
    }


def _profile_identifier(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    token = value.strip()
    return token if token and len(token) <= 160 else None


def _profile_duration(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0 or not numeric.is_integer():
        return None
    return int(numeric)


def _component_has_content_anchor(component: Any) -> bool:
    """Return whether a normalized component declares stable provenance.

    ``content_hash`` is the preferred byte-integrity anchor.  ``config_uri`` is
    also accepted for registries that expose immutable/version-pinned resource
    identities.  Both fields have already passed ``_profile_identifier`` when
    this helper is called.  Dereferencing or re-hashing the resource belongs to
    the configuration registry/deployment boundary, not this analysis module.
    """
    if not isinstance(component, dict):
        return False
    return any(component.get(key) is not None for key in ("content_hash", "config_uri"))


def normalize_protocol_profile(
    raw_profile: Any,
    *,
    declaration_source: str = "request",
) -> Tuple[Dict[str, Any], List[str]]:
    """Validate and normalize a versioned task-battery resource profile.

    The profile stores versioned references rather than hard-coding content in
    the analysis engine.  Explicit malformed profiles are returned with
    machine-readable errors so callers can fail closed.  Omitting a profile is
    supported for legacy recordings and resolves to the built-in candidate
    profile; this never grants normative interpretation.
    """
    if raw_profile is None:
        profile = candidate_protocol_profile()
        profile["declaration_source"] = "backend_candidate_default"
        return profile, []

    if not isinstance(raw_profile, dict):
        profile = candidate_protocol_profile()
        profile["declaration_source"] = declaration_source
        return profile, ["protocol_profile_must_be_an_object"]

    errors: List[str] = []
    contract_version = _profile_identifier(raw_profile.get("contract_version"))
    if contract_version != PROTOCOL_PROFILE_CONTRACT_VERSION:
        errors.append("unsupported_protocol_profile_contract_version")

    profile_id = _profile_identifier(raw_profile.get("profile_id"))
    if profile_id is None:
        errors.append("protocol_profile_id_missing_or_invalid")

    profile_version = _profile_identifier(raw_profile.get("profile_version"))
    if profile_version is None:
        errors.append("protocol_profile_version_missing_or_invalid")

    validation_status = normalize_protocol_validation_status(
        raw_profile.get("validation_status")
    )
    if validation_status is None:
        errors.append("protocol_profile_validation_status_invalid")

    raw_components = raw_profile.get("components")
    if not isinstance(raw_components, dict):
        raw_components = {}
        errors.append("protocol_profile_components_missing_or_invalid")

    components: Dict[str, Dict[str, Any]] = {}
    for component_name in PROTOCOL_PROFILE_COMPONENTS:
        raw_component = raw_components.get(component_name)
        if not isinstance(raw_component, dict):
            errors.append(f"protocol_profile_component_missing:{component_name}")
            continue
        component_id = _profile_identifier(raw_component.get("id"))
        version = _profile_identifier(raw_component.get("version"))
        component_status = normalize_protocol_validation_status(
            raw_component.get("validation_status")
        )
        if component_id is None:
            errors.append(f"protocol_profile_component_id_invalid:{component_name}")
        if version is None:
            errors.append(f"protocol_profile_component_version_invalid:{component_name}")
        if component_status is None:
            errors.append(f"protocol_profile_component_status_invalid:{component_name}")
        component: Dict[str, Any] = {
            "id": component_id,
            "version": version,
            "validation_status": component_status,
        }
        for optional_key in ("content_hash", "config_uri"):
            optional_value = raw_component.get(optional_key)
            if optional_value is not None:
                normalized_value = _profile_identifier(optional_value)
                if normalized_value is None:
                    errors.append(
                        f"protocol_profile_component_{optional_key}_invalid:{component_name}"
                    )
                else:
                    component[optional_key] = normalized_value
        components[component_name] = component

    raw_durations = raw_profile.get("task_durations_seconds")
    normalized_durations: Dict[str, Optional[int]] = {}
    if not isinstance(raw_durations, dict):
        raw_durations = {}
        errors.append("protocol_profile_task_durations_missing_or_invalid")
    declared_by_task: Dict[str, Any] = {}
    for raw_task_id, duration in raw_durations.items():
        canonical_task_id = resolve_canonical_task(str(raw_task_id))
        if canonical_task_id is None:
            errors.append(f"protocol_profile_unknown_duration_task:{raw_task_id}")
            continue
        if canonical_task_id in declared_by_task:
            errors.append(f"protocol_profile_duplicate_duration_task:{canonical_task_id}")
            continue
        declared_by_task[canonical_task_id] = duration

    for task_id, expected_duration in TASK_RECORDING_DURATIONS_SECONDS.items():
        duration = _profile_duration(declared_by_task.get(task_id))
        normalized_durations[task_id] = duration
        if duration is None:
            errors.append(f"protocol_profile_task_duration_invalid:{task_id}")
        elif duration != expected_duration:
            errors.append(
                f"protocol_profile_task_duration_mismatch:{task_id}:"
                f"expected_{expected_duration}:declared_{duration}"
            )

    all_components_validated = (
        len(components) == len(PROTOCOL_PROFILE_COMPONENTS)
        and all(
            components[name].get("validation_status") == "validated"
            for name in PROTOCOL_PROFILE_COMPONENTS
            if name in components
        )
    )
    if validation_status == "validated" and not all_components_validated:
        errors.append("validated_profile_requires_all_components_validated")

    all_components_content_anchored = (
        len(components) == len(PROTOCOL_PROFILE_COMPONENTS)
        and all(
            _component_has_content_anchor(components.get(name))
            for name in PROTOCOL_PROFILE_COMPONENTS
        )
    )
    if validation_status == "validated":
        for component_name in PROTOCOL_PROFILE_COMPONENTS:
            if not _component_has_content_anchor(components.get(component_name)):
                errors.append(
                    "validated_profile_component_content_anchor_missing:"
                    f"{component_name}"
                )

    normative_allowed = bool(
        not errors
        and validation_status == "validated"
        and all_components_validated
        and all_components_content_anchored
    )
    normalized: Dict[str, Any] = {
        "contract_version": contract_version,
        "profile_id": profile_id,
        "profile_version": profile_version,
        "validation_status": validation_status,
        "components": components,
        "task_durations_seconds": normalized_durations,
        "normative_interpretation_allowed": normative_allowed,
        "interpretation_scope": (
            "validated_production" if normative_allowed else "candidate_or_pilot_only"
        ),
        "declaration_source": declaration_source,
    }
    return normalized, list(dict.fromkeys(errors))


def protocol_profile_reference(
    profile: Any,
    canonical_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return compact, immutable provenance suitable for a per-task export."""
    normalized = profile if isinstance(profile, dict) else candidate_protocol_profile()
    components = normalized.get("components", {})
    reference: Dict[str, Any] = {
        "contract_version": normalized.get("contract_version"),
        "profile_id": normalized.get("profile_id"),
        "profile_version": normalized.get("profile_version"),
        "validation_status": normalized.get("validation_status"),
        "component_versions": {
            name: component.get("version")
            for name, component in components.items()
            if name in PROTOCOL_PROFILE_COMPONENTS and isinstance(component, dict)
        },
        "normative_interpretation_allowed": bool(
            normalized.get("normative_interpretation_allowed")
        ),
        "interpretation_scope": normalized.get("interpretation_scope"),
    }
    if canonical_task_id is not None:
        reference["canonical_task_id"] = canonical_task_id
        reference["expected_recording_duration_seconds"] = (
            normalized.get("task_durations_seconds", {}).get(canonical_task_id)
            if isinstance(normalized.get("task_durations_seconds"), dict)
            else None
        )
    return reference


_BEHAVIORAL_PASS_STATUSES = {
    "pass", "passed", "valid", "qualified", "meets_threshold",
    "threshold_met", "performance_valid",
}
_BEHAVIORAL_FAIL_STATUSES = {
    "fail", "failed", "invalid", "rejected", "below_threshold",
    "threshold_not_met", "performance_invalid",
}


def normalize_behavioral_status(evidence: Any) -> str:
    """Normalize behavioral evidence to passed/failed/missing/unverified.

    The ability gate is deliberately opt-in: merely submitting a response or a
    ``complete`` flag is not evidence that performance passed a predefined
    task-quality threshold.
    """
    if evidence is None:
        return "missing"
    if isinstance(evidence, bool):
        return "passed" if evidence else "failed"
    if isinstance(evidence, str):
        token = evidence.strip().lower()
        if token in _BEHAVIORAL_PASS_STATUSES:
            return "passed"
        if token in _BEHAVIORAL_FAIL_STATUSES:
            return "failed"
        return "missing" if not token else "unverified"
    if not isinstance(evidence, dict) or not evidence:
        return "missing"

    boolean_keys = (
        "passed", "valid", "meets_threshold", "quality_passed",
        "performance_passed",
    )
    explicit_values = [evidence[key] for key in boolean_keys if key in evidence]
    if any(value is False for value in explicit_values):
        return "failed"

    raw_status = evidence.get("status", evidence.get("behavioral_status"))
    if isinstance(raw_status, str):
        token = raw_status.strip().lower()
        if token in _BEHAVIORAL_FAIL_STATUSES:
            return "failed"
        if token in _BEHAVIORAL_PASS_STATUSES:
            return "passed"
    if any(value is True for value in explicit_values):
        return "passed"
    return "unverified"


def behavioral_evidence_passes(evidence: Any) -> bool:
    return normalize_behavioral_status(evidence) == "passed"


def theoretical_abilities_for_task(canonical_task_id: str) -> List[str]:
    """Return protocol candidates without implying measured support."""
    matrix = _TASK_MATRIX.get(canonical_task_id)
    return list(matrix["allowed_abilities"]) if matrix else []


def behaviorally_validated_abilities_for_task(
    canonical_task_id: str,
    evidence: Any,
) -> List[str]:
    """Return task abilities with explicit behavioral support.

    Multimodal tasks may validate only a subset of their theoretical abilities.
    When ``ability_validation`` is supplied, it is authoritative and abilities
    omitted from that map remain gated.  The overall evidence status is used
    only when no per-ability map is present.
    """
    theoretical = theoretical_abilities_for_task(canonical_task_id)
    ability_validation = (
        evidence.get("ability_validation") if isinstance(evidence, dict) else None
    )
    if isinstance(ability_validation, dict):
        by_name = {
            str(ability).strip().casefold(): status
            for ability, status in ability_validation.items()
        }
        return [
            ability
            for ability in theoretical
            if normalize_behavioral_status(by_name.get(ability.casefold())) == "passed"
        ]
    return theoretical if behavioral_evidence_passes(evidence) else []


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


def _feature_decision_flags(feature: Dict[str, Any]) -> Dict[str, Any]:
    flags = feature.get("decision_flags")
    return flags if isinstance(flags, dict) else {}


def _flag_or_threshold(
    flags: Dict[str, Any],
    flag_name: str,
    threshold_value: bool,
) -> bool:
    if flag_name in flags:
        return bool(flags.get(flag_name))
    return threshold_value


def _gamma_fallback_allowed(metric_name: str, flags: Dict[str, Any]) -> bool:
    if "gamma" not in metric_name.lower():
        return True
    guard = flags.get("gamma_sparse_montage_guard")
    if not isinstance(guard, dict):
        return False
    return bool(
        guard.get("emg_guard_clean")
        and guard.get("regional_agreement_ok")
        and guard.get("non_gamma_support")
    )


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

    gate = _gate_transparency(metric_name, feature)
    if gate["passes_statistical_gate"]:
        d = feature.get("effect_size_d")
        if d is not None and abs(d) < _effect_size_threshold_for_metric(metric_name):
            return False
        pct = feature.get("percent_change")
        if pct is not None and abs(pct) < _pct_threshold_for_metric(metric_name):
            return False
        return True

    flags = _feature_decision_flags(feature)
    direction_ok = bool(flags.get("direction_ok", True))
    if not direction_ok or not _gamma_fallback_allowed(metric_name, flags):
        return False
    return bool(
        gate["passes_effect_size_threshold"]
        and (
            gate["passes_percent_change_threshold"]
            or bool(flags.get("p_pass"))
        )
    )


def classify_feature_strength(feature: Dict[str, Any]) -> str:
    """Return 'rejected' | 'weak' | 'moderate' | 'strong'.

    Grade A/B -> strong (when d >= 0.80). Grade C -> moderate.
    Grade D or insufficient_metrics -> ungraded (no penalty).
    Does NOT apply reliability cap; call _apply_reliability_cap externally.
    """
    if not passes_neuroprofile_gate(feature):
        return "rejected"
    gate = _gate_transparency(feature.get("metric_name", ""), feature)
    if gate["significance_basis"] != "fdr_q_value":
        return "weak"
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
    behavioral_evidence: Any = None,
    scorable: bool = True,
) -> List[str]:
    """Return measured O*NET candidates after EEG and behavioral gates."""
    if canonical_task_id in _MODERATOR_ONLY_TASKS:
        return []
    if not scorable:
        return []
    if feature_strength in ("rejected", "weak") and not convergent:
        return []
    return behaviorally_validated_abilities_for_task(
        canonical_task_id,
        behavioral_evidence,
    )


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
    flags   = _feature_decision_flags(feature_stats)
    pass_rule = flags.get("pass_rule")   # "p" | "d" | "pct" | None

    d_thr   = _effect_size_threshold_for_metric(metric_name)
    pct_thr = _pct_threshold_for_metric(metric_name)

    passes_q   = bool(q_val is not None and q_val <= 0.0119377)
    passes_eff = _flag_or_threshold(flags, "effect_pass", bool(d_abs >= d_thr))
    passes_pct = _flag_or_threshold(flags, "percent_pass", bool(pct_abs >= pct_thr))
    direction_ok = bool(flags.get("direction_ok", True))
    # Strict statistical gate = FDR q-value only
    passes_stat_gate = passes_q

    # Determine what drove the significant_change flag
    if passes_q:
        sig_basis = "fdr_q_value"
    elif not direction_ok:
        sig_basis = "none"
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
    elif not direction_ok:
        interp = "do_not_use"
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
    behavioral_evidence: Any = None,
    scorable: bool = True,
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
    theoretical_abilities = (
        theoretical_abilities_for_task(canonical_task_id) if characteristics else []
    )
    behaviorally_validated_abilities = (
        behaviorally_validated_abilities_for_task(
            canonical_task_id,
            behavioral_evidence,
        )
        if characteristics
        else []
    )
    behavioral_status = normalize_behavioral_status(behavioral_evidence)
    abilities = (
        allowed_abilities_for_task(
            canonical_task_id,
            strength,
            convergent,
            behavioral_evidence=behavioral_evidence,
            scorable=scorable,
        )
        if characteristics
        else []
    )
    ability_gate_passed = bool(abilities)
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
        "theoretical_onet_ability_candidates": theoretical_abilities,
        "behaviorally_validated_onet_ability_candidates": behaviorally_validated_abilities,
        "allowed_onet_ability_candidates": abilities,
        "behavioral_evidence_status":      behavioral_status,
        "passes_behavioral_gate":          bool(behaviorally_validated_abilities),
        "passes_ability_gate":             ability_gate_passed,
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
    behavioral_evidence: Any = None,
    scorable: bool = True,
) -> Dict[str, Any]:
    """Build per-task summary; applies reliability cap to confidence."""
    all_chars:     List[str] = []
    all_abilities: List[str] = []
    all_blocked             = blocked_inferences_for_task(canonical_task_id)
    theoretical_abilities   = theoretical_abilities_for_task(canonical_task_id)
    behaviorally_validated_abilities = behaviorally_validated_abilities_for_task(
        canonical_task_id,
        behavioral_evidence,
    )
    behavioral_status       = normalize_behavioral_status(behavioral_evidence)
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
        "theoretical_onet_ability_candidates": theoretical_abilities,
        "behaviorally_validated_onet_ability_candidates": behaviorally_validated_abilities,
        "allowed_onet_ability_candidates": unique_abilities,
        "behavioral_evidence_status":      behavioral_status,
        "passes_behavioral_gate":          bool(behaviorally_validated_abilities),
        "passes_ability_gate":             bool(unique_abilities),
        "scorable":                        bool(scorable),
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
    task_metadata: Optional[Dict[str, Any]] = None,
    behavioral_evidence: Any = None,
    scorable: bool = True,
    raw_task_labels: Optional[List[str]] = None,
    task_qc: Optional[Dict[str, Any]] = None,
    baseline_qc: Optional[Dict[str, Any]] = None,
    continuous_time_series: Optional[Dict[str, Any]] = None,
    single_task_reference_comparison: Optional[Dict[str, Any]] = None,
    invalid_reasons: Optional[List[str]] = None,
    protocol_profile: Optional[Dict[str, Any]] = None,
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
        if fam in ("signal_quality", "unknown", "peak_feature"):
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
            behavioral_evidence=behavioral_evidence,
            scorable=scorable,
        )
        features_out.append(f_entry)

    sig_quality  = _signal_quality_for_task(features_out, analysis)
    task_summary = _task_summary_block(
        canonical_task_id,
        features_out,
        reliability,
        behavioral_evidence=behavioral_evidence,
        scorable=scorable,
    )

    return {
        "task_number":          task_number,
        "canonical_task_id":    canonical_task_id,
        "canonical_task_name":  task_info.get("name", canonical_task_id),
        "raw_task_labels":      list(raw_task_labels or [raw_task_id]),
        "repeat_status":        "not_repeated",
        "role_matching_status": rm_status,
        "baseline_condition":   task_baseline_condition(canonical_task_id),
        "task_metadata":        dict(task_metadata or {}),
        "protocol_profile":     dict(protocol_profile or {}),
        "behavioral_evidence":  behavioral_evidence,
        "behavioral_evidence_status": normalize_behavioral_status(behavioral_evidence),
        "scorable":             bool(scorable),
        "invalid_reasons":      list(invalid_reasons or []),
        "task_qc":              dict(task_qc or {}),
        "baseline_qc":          dict(baseline_qc or {}),
        "continuous_time_series": (
            dict(continuous_time_series)
            if isinstance(continuous_time_series, dict)
            else None
        ),
        "single_task_reference_comparison": (
            dict(single_task_reference_comparison)
            if isinstance(single_task_reference_comparison, dict)
            else None
        ),
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
    strict_usable = sum(
        1
        for task in neuroprofile_tasks
        for feature in task.get("features", [])
        if feature.get("passes_neuroprofile_gate")
        and feature.get("passes_statistical_gate")
    )
    strict_keep_rate = strict_usable / max(1, total_features)

    notes = []
    if baseline_keep_rate >= 0.70 and strict_keep_rate >= 0.60 and gamma_guard_count <= 1:
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
    raw_protocol_profile = existing_analysis.get("protocol_profile")
    protocol_profile, profile_errors = normalize_protocol_profile(
        raw_protocol_profile,
        declaration_source="analysis_response",
    )
    upstream_profile_validation = existing_analysis.get("protocol_profile_validation")
    if isinstance(upstream_profile_validation, dict):
        upstream_errors = upstream_profile_validation.get("errors")
        if isinstance(upstream_errors, list):
            profile_errors.extend(str(error) for error in upstream_errors if error)
    profile_errors = list(dict.fromkeys(profile_errors))

    # Step 1: preliminary reliability from baseline QC only (no task data yet).
    prelim_reliability = _preliminary_reliability_from_baseline(existing_analysis)

    # Step 2: build task entries using the preliminary reliability cap.
    tasks, allowed_ability_pool, theoretical_ability_pool, moderator_chars, blocked_unsupported, all_canonical_ids = \
        _build_all_task_entries(per_task, prelim_reliability)

    # Step 3: final global quality (uses task feature quality data).
    session_depth  = _infer_session_depth(all_canonical_ids)
    global_quality = compute_neuroprofile_global_quality(existing_analysis, tasks)
    final_reliability = global_quality["overall_reliability"]

    # Step 4: re-build if the final reliability differs from the preliminary estimate.
    if final_reliability != prelim_reliability:
        tasks, allowed_ability_pool, theoretical_ability_pool, moderator_chars, blocked_unsupported, _ = \
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
        "protocol_profile":               protocol_profile,
        "protocol_profile_validation": {
            "valid": not profile_errors,
            "errors": profile_errors,
            "normative_interpretation_allowed": bool(
                protocol_profile.get("normative_interpretation_allowed")
            ) and not profile_errors,
        },
        "headset_scope":                  "MindRove sparse montage: Fp1/Fp2 frontal + O1/O2 occipital",
        # Quality summary — flat for easy Implicit Agent consumption
        "global_reliability":             final_reliability,
        "baseline_qc":                    baseline_qc,
        # Confidence cap for downstream agents
        "session_confidence_cap":         session_cap,
        # Ability / characteristic pools
        "allowed_ability_pool":           allowed_ability_pool,
        "theoretical_ability_pool":       theoretical_ability_pool,
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
        "theoretical_onet_ability_candidates",
        "behaviorally_validated_onet_ability_candidates",
        "allowed_onet_ability_candidates",
        "behavioral_evidence_status", "passes_behavioral_gate", "passes_ability_gate",
        "blocked_inferences",
    )

    rows: List[Dict[str, Any]] = []
    for task in tasks:
        ts = task.get("task_summary", {})
        task_protocol_profile = task.get("protocol_profile", {})
        task_ctx = {
            "task_number":              task.get("task_number"),
            "canonical_task_id":        task.get("canonical_task_id"),
            "canonical_task_name":      task.get("canonical_task_name"),
            "task_role_matching_status": task.get("role_matching_status"),
            "task_signal_quality":      task.get("signal_quality", {}).get("quality_level"),
            "task_confidence":          ts.get("confidence"),
            "task_confidence_before_cap": ts.get("confidence_before_cap"),
            "task_scorable":            task.get("scorable"),
            "task_baseline_condition":  task.get("baseline_condition"),
            "task_behavioral_evidence_status": task.get("behavioral_evidence_status"),
            "task_protocol_profile_id": (
                task_protocol_profile.get("profile_id")
                if isinstance(task_protocol_profile, dict) else None
            ),
            "task_protocol_profile_version": (
                task_protocol_profile.get("profile_version")
                if isinstance(task_protocol_profile, dict) else None
            ),
            "task_protocol_validation_status": (
                task_protocol_profile.get("validation_status")
                if isinstance(task_protocol_profile, dict) else None
            ),
            "task_normative_interpretation_allowed": bool(
                task_protocol_profile.get("normative_interpretation_allowed")
            ) if isinstance(task_protocol_profile, dict) else False,
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

    Returns (tasks, allowed_ability_pool, theoretical_ability_pool,
             moderator_chars, blocked_unsupported, all_canonical_ids).
    """
    tasks:               List[Dict[str, Any]] = []
    all_canonical_ids:   List[str] = []
    allowed_ability_pool: List[str] = []
    theoretical_ability_pool: List[str] = []
    moderator_chars:     List[str] = []
    blocked_unsupported: List[str] = []

    for raw_task_id, task_result in per_task.items():
        analysis = task_result.get("analysis", {})
        summary  = task_result.get("summary", {})
        entry    = build_neuroprofile_task_entry(
            raw_task_id,
            analysis,
            summary,
            reliability=reliability,
            task_metadata=task_result.get("task_metadata"),
            behavioral_evidence=task_result.get("behavioral_evidence"),
            scorable=bool(task_result.get("scorable", True)),
            raw_task_labels=task_result.get("raw_task_labels"),
            task_qc=task_result.get("task_qc"),
            baseline_qc=task_result.get("baseline_qc"),
            continuous_time_series=task_result.get("continuous_time_series"),
            single_task_reference_comparison=task_result.get(
                "single_task_reference_comparison"
            ),
            invalid_reasons=task_result.get("invalid_reasons"),
            protocol_profile=task_result.get("protocol_profile"),
        )
        tasks.append(entry)
        canonical_id = entry["canonical_task_id"]
        all_canonical_ids.append(canonical_id)

        task_blocked = set(blocked_inferences_for_task(canonical_id))
        for ability in entry["task_summary"].get("allowed_onet_ability_candidates", []):
            if ability not in task_blocked and ability not in allowed_ability_pool:
                allowed_ability_pool.append(ability)
        for ability in entry["task_summary"].get("theoretical_onet_ability_candidates", []):
            if ability not in task_blocked and ability not in theoretical_ability_pool:
                theoretical_ability_pool.append(ability)
        for mc in entry["task_summary"].get("moderator_characteristics", []):
            if mc not in moderator_chars:
                moderator_chars.append(mc)
        for bl in task_blocked:
            if bl not in blocked_unsupported:
                blocked_unsupported.append(bl)

    return (
        tasks,
        allowed_ability_pool,
        theoretical_ability_pool,
        moderator_chars,
        blocked_unsupported,
        all_canonical_ids,
    )
