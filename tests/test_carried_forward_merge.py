"""
Tests for the carried-forward task merge used by repetition-waived runs.

Run from repo root:
    pytest tests/test_carried_forward_merge.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "newBackend"))

from neuroprofile_traceability import (  # noqa: E402
    REPORT_MERGE_VERSION,
    _weakest_reliability,
    merge_carried_forward_tasks,
)

# Session 1 tasks, by canonical id and the task number the exporter assigns.
S1 = [
    ("adaptive_numerical_reasoning", 1),
    ("working_memory_manipulation", 2),
    ("auditory_target_counting", 3),
    ("semantic_induction_category_switching", 4),
]
# The five tasks Session 2 introduces.
S2_NEW = [
    ("visuospatial_transformation_orientation", 5),
    ("divergent_ideation", 6),
    ("dual_task_rule_switching", 7),
    ("rule_based_anomaly_detection", 8),
    ("rapid_visual_comparison", 9),
]
S3_NEW = [
    ("pattern_closure_visual_noise", 10),
    ("speech_in_noise_comprehension", 11),
    ("written_comprehension_synthesis", 12),
]


def _export(task_specs, reliability="high", abilities=None):
    """Minimal export document with just the fields the merge touches."""
    return {
        "feature_report_version": "mindspeller_eeg_feature_report_v3",
        "traceability_version": "mindspeller_eeg_feature_traceability_v8",
        "protocol_session_depth": "session_1",
        "global_reliability": reliability,
        "baseline_qc": {"kept": 100, "rejected": 0},
        "global_quality": {"overall_reliability": reliability},
        "allowed_ability_pool": list(abilities or ["Mathematical Reasoning"]),
        "theoretical_ability_pool": list(abilities or ["Mathematical Reasoning"]),
        "moderator_only_characteristics": [],
        "blocked_unsupported_labels": ["Reaction Time"],
        "feature_rows": [
            {"canonical_task_id": tid, "metric_name": f"{tid}_theta", "task_number": num}
            for tid, num in task_specs
        ],
        "tasks": [
            {"canonical_task_id": tid, "task_number": num, "repeat_status": "not_repeated"}
            for tid, num in task_specs
        ],
        "tasks_detected": [
            {"canonical_task_id": tid, "task_number": num, "repeat_status": "not_repeated"}
            for tid, num in task_specs
        ],
    }


def _ids(export):
    return [t["canonical_task_id"] for t in export["tasks"]]


# ── Coverage is restored, and the merged depth reflects it ──────────────────

def test_session_2_waived_run_regains_full_coverage():
    current = _export(S2_NEW, abilities=["Spatial Orientation"])
    carried = _export(S1, abilities=["Mathematical Reasoning"])

    merged = merge_carried_forward_tasks(current, carried, {"session_id": "s1"})

    assert len(merged["tasks"]) == 9
    assert set(_ids(merged)) == {tid for tid, _ in S1 + S2_NEW}
    assert merged["protocol_session_depth"] == "session_2"
    # tasks_detected is an alias and must not drift from tasks.
    assert merged["tasks_detected"] == merged["tasks"]


def test_merged_tasks_are_ordered_by_task_number():
    merged = merge_carried_forward_tasks(_export(S2_NEW), _export(S1))
    assert [t["task_number"] for t in merged["tasks"]] == list(range(1, 10))


def test_session_3_chains_from_an_already_merged_session_2():
    """The merged report is what gets uploaded, so Session 3 inherits all 9."""
    session_2_upload = merge_carried_forward_tasks(_export(S2_NEW), _export(S1))
    merged = merge_carried_forward_tasks(_export(S3_NEW), session_2_upload)

    assert len(merged["tasks"]) == 12
    assert merged["protocol_session_depth"] == "session_3"


# ── Derived fields are unions of the per-task slices ────────────────────────

def test_feature_rows_carry_only_the_carried_tasks():
    current = _export(S2_NEW)
    carried = _export(S1)
    merged = merge_carried_forward_tasks(current, carried)

    assert len(merged["feature_rows"]) == 9
    row_task_ids = {r["canonical_task_id"] for r in merged["feature_rows"]}
    assert row_task_ids == set(_ids(merged))


def test_ability_pools_union_without_duplicates():
    current = _export(S2_NEW, abilities=["Spatial Orientation", "Shared Ability"])
    carried = _export(S1, abilities=["Mathematical Reasoning", "Shared Ability"])

    merged = merge_carried_forward_tasks(current, carried)

    assert merged["allowed_ability_pool"] == [
        "Spatial Orientation", "Shared Ability", "Mathematical Reasoning",
    ]


# ── A merged report is only as good as its weakest run ──────────────────────

def test_reliability_takes_the_floor_of_both_runs():
    assert _weakest_reliability("high", "low") == "low"
    assert _weakest_reliability("medium", "high") == "medium"
    assert _weakest_reliability("high", "unknown") == "unknown"
    assert _weakest_reliability(None, None) == "unknown"


def test_low_quality_carried_run_drags_the_merged_cap_down():
    current = _export(S2_NEW, reliability="high")
    carried = _export(S1, reliability="low")

    merged = merge_carried_forward_tasks(current, carried)

    assert merged["global_reliability"] == "low"
    # session_2 alone would allow a strong trait cap; low reliability forbids it.
    assert merged["session_confidence_cap"]["implicit_trait_max"] == "weak"


def test_recording_session_fields_stay_with_the_current_run():
    current = _export(S2_NEW, reliability="high")
    current["baseline_qc"] = {"kept": 42, "rejected": 1}
    carried = _export(S1, reliability="low")
    carried["baseline_qc"] = {"kept": 999, "rejected": 999}

    merged = merge_carried_forward_tasks(current, carried)

    assert merged["baseline_qc"] == {"kept": 42, "rejected": 1}


# ── Provenance ──────────────────────────────────────────────────────────────

def test_composition_block_records_what_came_from_where():
    merged = merge_carried_forward_tasks(
        _export(S2_NEW, reliability="high"),
        _export(S1, reliability="medium"),
        {"session_id": "session_20260101_120000_abcd1234", "sha256": "abc"},
    )
    comp = merged["composition"]

    assert comp["merged"] is True
    assert comp["merge_version"] == REPORT_MERGE_VERSION
    assert comp["reason"] == "repetition_waived"
    assert comp["carried_task_ids"] == sorted(tid for tid, _ in S1)
    assert comp["current_run_task_ids"] == sorted(tid for tid, _ in S2_NEW)
    assert comp["current_run_reliability"] == "high"
    assert comp["carried_reliability"] == "medium"
    assert comp["carried_source"]["session_id"] == "session_20260101_120000_abcd1234"
    assert "baseline_qc" in comp["per_recording_session_fields_from_current_run"]


def test_unmerged_report_has_no_composition_block():
    """Absence is the signal that every task came from one sitting."""
    assert "composition" not in _export(S1)


# ── Refusals and no-ops ─────────────────────────────────────────────────────

def test_current_run_wins_for_a_task_measured_in_both():
    current = _export(S1 + S2_NEW)
    current["tasks"][0]["marker"] = "fresh"
    carried = _export(S1)
    carried["tasks"][0]["marker"] = "stale"

    merged = merge_carried_forward_tasks(current, carried)

    assert len(merged["tasks"]) == 9
    assert merged["tasks"][0]["marker"] == "fresh"
    # Fully covered by the current run, so nothing is carried at all.
    assert "composition" not in merged


def test_no_duplicate_feature_rows_when_tasks_overlap():
    current = _export(S1 + S2_NEW)
    merged = merge_carried_forward_tasks(current, _export(S1))
    assert len(merged["feature_rows"]) == 9


def test_missing_or_broken_carried_report_is_a_no_op():
    current = _export(S2_NEW)
    for carried in (None, {}, {"error": "export failed"}, {"tasks": "not-a-list"}):
        assert merge_carried_forward_tasks(current, carried) == current


def test_errored_current_export_is_returned_untouched():
    broken = {"error": "Neuroprofile export failed: boom"}
    assert merge_carried_forward_tasks(broken, _export(S1)) == broken


def test_current_export_is_not_mutated():
    current = _export(S2_NEW)
    before = len(current["tasks"])

    merge_carried_forward_tasks(current, _export(S1))

    assert len(current["tasks"]) == before
    assert "composition" not in current
