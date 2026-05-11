# Copilot Prompt — Refactor Existing EEG Feature Extraction for Neuroprofile Traceability v7

Copy this prompt into Copilot while working in the EEG task software backend.

---

You are working in the existing Mindspeller EEG task software backend. The feature extraction pipeline already exists in `newBackend/main.py`, especially the `/analyze` endpoint. Do **not** rebuild feature extraction from scratch.

Your task is to **refactor and extend the existing `/analyze` output** so it becomes directly consumable by the neuroprofile backend Stage 2 Implicit Agent and later O*NET-based role matching.

## Current pipeline already exists

The backend already accepts this input:

```json
{
  "baseline": {
    "eyes_closed": [],
    "eyes_open": []
  },
  "tasks": {
    "task_id": []
  },
  "block_seconds": 8.0
}
```

It already supports two sample formats:

1. raw EEG numbers sampled at 512 Hz
2. TGAM-style band-power dictionaries with `delta`, `theta`, `lowAlpha`, `highAlpha`, `lowBeta`, `highBeta`, `lowGamma`, and `midGamma`

Raw numeric EEG is preferred.

The existing raw EEG path already:

- uses 512 Hz sampling
- processes fixed 2-second windows of 1024 samples
- uses 8-second default statistical blocks, each containing 4 windows
- removes window mean
- computes PSD using DPSS multitaper when available
- falls back to Hann-window FFT if DPSS is unavailable
- estimates a 10th-percentile PSD noise floor
- builds SNR-adjusted PSD
- emits band powers, peak descriptors, relative powers, entropy, ratios, total power, and EMG guard flags
- aggregates windows into blocks
- compares task blocks against baseline blocks
- computes Welch t-test p-values, Cohen's d, percent change, z-score, ratios, log2 ratios, BH FDR q-values, one-sided p-values, significance flags, task summaries, across-task analyses, and correction metadata

Keep all of that.

## Goal of this refactor

Add a new **neuroprofile traceability export layer** on top of the existing feature analysis.

The goal is not to change the signal-processing core. The goal is to enrich the existing `/analyze` response with:

```text
existing EEG feature statistics
-> feature family classification
-> canonical Mindspeller task mapping
-> task-supported characteristic candidates
-> allowed downstream O*NET ability candidates
-> blocked unsupported inference labels
-> neuroprofile-ready export block
```

This backend must still **not** generate jobs, roles, neuroprofiles, personality claims, medical claims, or hiring decisions.

It should only produce structured EEG evidence.

Role matching happens later in the neuroprofile backend.

---

# 1. Add traceability constants

Add constants in a clean location, preferably a new module:

```python
# newBackend/neuroprofile_traceability.py
```

or another appropriate config module if the project already has one.

Add:

```python
TRACEABILITY_VERSION = "mindspeller_eeg_feature_traceability_v7"
NEUROPROFILE_EXPORT_VERSION = "mindspeller_eeg_feature_report_v2"
```

## Session task gates

```python
SESSION_TASK_GATES = {
    "session_1": [1, 2, 3, 4],
    "session_2": [1, 2, 3, 4, 5, 6, 7, 8, 9],
    "session_3": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
}
```

## Canonical tasks

```python
CANONICAL_TASKS = {
    1: {"id": "mental_math", "name": "Mental Math"},
    2: {"id": "visual_imagery", "name": "Visual Imagery"},
    3: {"id": "focused_attention", "name": "Focused Attention"},
    4: {"id": "static_emotion_grasp", "name": "Static Emotion Grasp"},
    5: {"id": "working_memory", "name": "Working Memory"},
    6: {"id": "language_processing", "name": "Language Processing"},
    7: {"id": "motor_imagery", "name": "Motor Imagery"},
    8: {"id": "cognitive_load_multitasking", "name": "Cognitive Load / Multitasking"},
    9: {"id": "divergent_thinking", "name": "Divergent Thinking"},
    10: {"id": "body_scan", "name": "Body Scan"},
    11: {"id": "visual_colour_processing", "name": "Visual Colour Processing"},
    12: {"id": "semantic_memory_retrieval", "name": "Semantic Memory Retrieval"},
}
```

## Task aliases

Normalize old task labels and frontend task IDs:

```python
TASK_NAME_ALIASES = {
    "math": "mental_math",
    "mental_math": "mental_math",
    "serial_calculation": "mental_math",
    "arithmetic": "mental_math",

    "visual_imagery": "visual_imagery",
    "imagery": "visual_imagery",
    "internal_imagery": "visual_imagery",

    "attention_focus": "focused_attention",
    "focused_attention": "focused_attention",
    "focus": "focused_attention",

    "emotion_face": "static_emotion_grasp",
    "emotion_faces": "static_emotion_grasp",
    "reappraisal": "static_emotion_grasp",
    "static_emotion_grasp": "static_emotion_grasp",

    "working_memory": "working_memory",
    "n_back": "working_memory",
    "wm": "working_memory",

    "language": "language_processing",
    "language_processing": "language_processing",
    "semantic_processing": "language_processing",

    "motor_imagery": "motor_imagery",
    "movement_imagery": "motor_imagery",

    "cognitive_load": "cognitive_load_multitasking",
    "multitasking": "cognitive_load_multitasking",
    "task_switching": "cognitive_load_multitasking",
    "load_multitasking": "cognitive_load_multitasking",

    "div_write": "divergent_thinking",
    "divergent_thinking": "divergent_thinking",
    "creative_ideation": "divergent_thinking",

    "body_scan": "body_scan",
    "interoception": "body_scan",

    "colour_processing": "visual_colour_processing",
    "color_processing": "visual_colour_processing",
    "visual_colour_processing": "visual_colour_processing",
    "visual_color_processing": "visual_colour_processing",

    "semantic_memory": "semantic_memory_retrieval",
    "semantic_retrieval": "semantic_memory_retrieval",
    "semantic_memory_retrieval": "semantic_memory_retrieval",
}
```

---

# 2. Classify existing metrics into feature families

The backend already emits metrics such as:

- `{band}_power`
- `{band}_power_raw`
- `{band}_relative`
- `{band}_peak_freq`
- `{band}_peak_amp`
- `{band}_peak_rel_amp`
- `{band}_entropy`
- `alpha_theta_ratio`
- `beta_alpha_ratio`
- `beta2_beta1_ratio`
- `theta2_theta1_ratio`
- `total_power`
- `_emg_guard`
- `_gamma_evaluated`

Add a deterministic helper:

```python
def classify_feature_family(metric_name: str) -> str:
    """Return feature family for a metric emitted by the existing analyzer."""
```

Expected families:

```python
FEATURE_FAMILIES = {
    "spectral_power",
    "relative_power",
    "band_ratio",
    "peak_feature",
    "entropy_complexity",
    "signal_quality",
    "transition_recovery",
    "task_summary_stat",
    "behavioral_optional",
    "unknown",
}
```

Suggested rules:

```python
if metric_name.endswith("_power") or metric_name.endswith("_power_raw"):
    return "spectral_power"

if metric_name.endswith("_relative"):
    return "relative_power"

if metric_name.endswith("_ratio") or metric_name in {"alpha_theta_ratio", "beta_alpha_ratio", "beta2_beta1_ratio", "theta2_theta1_ratio"}:
    return "band_ratio"

if "peak" in metric_name:
    return "peak_feature"

if metric_name.endswith("_entropy") or "entropy" in metric_name:
    return "entropy_complexity"

if metric_name in {"_emg_guard", "_gamma_evaluated"}:
    return "signal_quality"

if metric_name in {"total_power"}:
    return "task_summary_stat"

# If future code adds recovery_slope, fatigue_drift, baseline_return_time, habituation_slope:
if any(token in metric_name for token in ["recovery", "fatigue", "habituation", "baseline_return", "stability"]):
    return "transition_recovery"

return "unknown"
```

Do not remove existing metrics. Add `feature_family` beside each analyzed feature.

---

# 3. Preserve existing statistics, add neuroprofile metadata

For each per-task feature already computed by the backend, preserve existing fields such as:

- task mean
- baseline mean
- delta
- Welch t-test p-value
- Cohen's d
- percent change
- z-score
- baseline/task ratio
- log2 ratio
- BH FDR q-value
- one-sided p-value
- significance flags
- expectation-alignment grade, if available

Add fields:

```json
{
  "feature_family": "spectral_power",
  "canonical_task_id": "working_memory",
  "canonical_task_name": "Working Memory",
  "task_number": 5,
  "passes_neuroprofile_gate": true,
  "feature_strength": "weak | moderate | strong | rejected",
  "task_supported_characteristics": [],
  "allowed_onet_ability_candidates": [],
  "blocked_inferences": [],
  "role_matching_status": "eligible | moderator_only | not_eligible",
  "neuroprofile_rationale": "short bounded technical rationale"
}
```

---

# 4. Use existing statistical outputs for neuroprofile gating

Do not recompute statistics from scratch. Use the existing per-feature statistical values.

Add:

```python
def passes_neuroprofile_gate(feature: dict) -> bool:
    """Use existing analyzer statistics to decide whether feature is reportable downstream."""
```

Gate rules:

- pass if existing significance flag is true, if available
- otherwise pass if q-value <= 0.0119377
- if q-value is absent, pass if p-value <= 0.05
- require effect-size threshold by feature family/band
- require percent-change threshold when available
- reject if signal quality flags indicate artifact contamination
- reject gamma if `_emg_guard == 1` or `_gamma_evaluated == 0`

Effect-size thresholds:

```python
EFFECT_SIZE_THRESHOLDS = {
    "theta": 0.30,
    "alpha": 0.25,
    "beta": 0.35,
    "gamma": 0.30,
    "delta": 0.30,
    "ratio": 0.30,
    "entropy": 0.30,
    "peak": 0.30,
    "relative": 0.30,
    "transition": 0.30,
}
```

Percent-change thresholds:

```python
RELATIVE_PERCENT_CHANGE_MIN = 5.0
ABSOLUTE_PERCENT_CHANGE_MIN = 10.0
```

Feature strength:

```python
def classify_feature_strength(feature: dict) -> str:
    # rejected: fails gate or artifact/gamma guard
    # weak: passes gate but abs(d) < 0.50
    # moderate: passes gate and 0.50 <= abs(d) < 0.80
    # strong: passes gate and abs(d) >= 0.80 and grade A/B if grade exists
```

Do not allow a single weak feature to produce downstream ability candidates unless it converges with other features in the same task or repeated task blocks.

---

# 5. Map task + feature family to characteristics

Add:

```python
def map_feature_to_characteristics(
    canonical_task_id: str,
    metric_name: str,
    feature_family: str,
    direction: str | None,
    feature_strength: str,
) -> list[str]:
    """Return task-supported characteristic candidates."""
```

Use this matrix.

## mental_math

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- processing_efficiency_under_load
- quantitative_load_response
- effort_mobilisation
- working_memory_rule_sequence_load
- load_response_slope
- fatigue_drift_under_demand
- post_effort_recovery

Allowed downstream abilities:

- Mathematical Reasoning
- Number Facility
- Information Ordering

Blocked:

- Speaking
- Oral Expression
- Reading Comprehension

## visual_imagery

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- internal_visual_simulation
- top_down_maintenance
- representation_stability
- imagery_control
- internal_attention_stability

Allowed downstream abilities:

- Visualization

Blocked:

- Visual Color Discrimination
- Near Vision
- Far Vision
- design skill by itself

## focused_attention

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery
- signal_quality

Characteristics:

- sustained_attention
- attentional_stability
- drift_resistance
- reorientation_control
- low_artifact_calibration_stability

Allowed downstream abilities:

- Selective Attention

Blocked:

- Active Listening
- Auditory Attention
- Speech Recognition

## static_emotion_grasp

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- entropy_complexity
- transition_recovery

Characteristics:

- affective_appraisal
- emotion_salience_response
- motivational_direction_bias
- salience_regulation
- regulation_under_affective_input

Allowed downstream abilities:

- none by default

Role matching status:

- moderator_only

Blocked:

- Social Perceptiveness
- Persuasion
- Service Orientation
- Leadership ability

## working_memory

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- working_memory_load_scaling
- maintenance_and_manipulation
- load_threshold
- executive_efficiency
- manipulation_cost
- capacity_proxy

Allowed downstream abilities:

- Information Ordering
- Memorization
- Deductive Reasoning

Blocked:

- Reading Comprehension
- Written Comprehension
- Oral Comprehension

## language_processing

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- silent_semantic_integration
- semantic_control_cost
- retrieval_organization
- structured_semantic_processing
- symbolic_processing_effort

Allowed downstream abilities:

- Inductive Reasoning
- Information Ordering
- Category Flexibility

Blocked:

- Oral Comprehension
- Written Comprehension
- Reading Comprehension
- Oral Expression
- Written Expression
- Speaking
- Writing
- Active Listening

## motor_imagery

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- embodied_simulation
- action_planning_imagery
- internal_action_sequencing
- simulation_maintenance
- planning_bias

Allowed downstream abilities:

- Visualization

Blocked:

- Manual Dexterity
- Finger Dexterity
- Reaction Time
- Control Precision

## cognitive_load_multitasking

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- switching_cost
- interference_management
- overload_threshold
- executive_flexibility
- recovery_after_interference
- escalation_slope_under_competing_demands

Allowed downstream abilities:

- Time Sharing
- Category Flexibility
- Information Ordering
- Deductive Reasoning

Blocked:

- Coordination
- Active Listening
- Social Perceptiveness

## divergent_thinking

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- idea_fluency_dynamics
- originality_dynamics
- associative_breadth
- creative_control_style
- internal_attention_dominance

Allowed downstream abilities:

- Fluency of Ideas
- Originality
- Category Flexibility

Blocked:

- Writing
- Speaking
- artistic achievement

## body_scan

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- interoceptive_attention
- internal_attention_stability
- post_load_recovery
- regulation_efficiency_proxy
- calm_state_stability
- reduced_volatility

Allowed downstream abilities:

- none by default

Role matching status:

- moderator_only

Blocked:

- diagnosis
- clinical regulation
- guaranteed stress resilience

## visual_colour_processing

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- visual_engagement
- evaluative_preference_response
- approach_bias_candidate
- habituation_pattern
- evaluative_style_proxy

Allowed downstream abilities:

- none by default

Role matching status:

- moderator_only

Blocked:

- Visual Color Discrimination
- color vision ability
- low-level sensory acuity

## semantic_memory_retrieval

Eligible feature families:

- spectral_power
- relative_power
- band_ratio
- peak_feature
- entropy_complexity
- transition_recovery

Characteristics:

- semantic_access_efficiency
- retrieval_effort
- category_access_pattern
- transition_control
- retrieval_rest_contrast_efficiency
- onset_offset_control

Allowed downstream abilities:

- Memorization
- Information Ordering
- Category Flexibility
- Inductive Reasoning

Blocked:

- Oral Expression
- Written Expression
- Speaking
- Writing
- Oral Comprehension
- Reading Comprehension

---

# 6. Add allowed ability attachment

Add:

```python
def allowed_abilities_for_task(canonical_task_id: str) -> list[str]:
    """Return downstream O*NET ability candidates for the task."""
```

Return abilities only if:

1. the feature passes the neuroprofile gate
2. feature strength is moderate or strong, OR weak-but-convergent
3. the task is not moderator-only
4. the ability is listed for that canonical task

For moderator-only tasks:

- static_emotion_grasp
- body_scan
- visual_colour_processing

return:

```python
allowed_onet_ability_candidates = []
role_matching_status = "moderator_only"
```

---

# 7. Add blocked inference attachment

Add:

```python
def blocked_inferences_for_task(canonical_task_id: str) -> list[str]:
    """Return labels that this task must never support."""
```

Ensure blocked labels never appear inside:

- `allowed_onet_ability_candidates`
- `task_supported_characteristics`
- `task_summary.supported_characteristics`
- `export_for_neuroprofile_backend.allowed_ability_pool`

---

# 8. Add repeat-task stability from existing blocks

The current backend already has per-task blocks, across-task analysis, and correction metadata.

Add repeat stability metadata when the same canonical task appears across sessions or multiple blocks:

```python
repeat_status = "not_repeated" | "repeated_stable" | "repeated_unstable" | "insufficient"
```

Suggested logic:

- not_repeated: only one occurrence or no session repeat info
- insufficient: fewer than 2 usable occurrences/windows/blocks
- repeated_stable: repeated occurrences have same direction for key feature families and no major quality downgrade
- repeated_unstable: repeated occurrences conflict in direction or feature strength, or quality differs sharply

Do not overengineer this initially. Make the first implementation transparent and conservative.

---

# 9. Add neuroprofile-ready export block to `/analyze`

Keep current output keys:

- `per_task`
- `combined`
- `across_task`
- baseline QC counters
- raw baseline sample counts
- eyes-open window count
- runtime config metadata

Add a new top-level key:

```json
"neuroprofile_feature_export": {
  "feature_report_version": "mindspeller_eeg_feature_report_v2",
  "traceability_version": "mindspeller_eeg_feature_traceability_v7",
  "protocol_session_depth": "session_1 | session_2 | session_3 | partial_unknown",
  "headset_scope": "frontal/frontopolar, Fp1/Fp2-compatible",
  "tasks_detected": [],
  "allowed_ability_pool": [],
  "moderator_only_characteristics": [],
  "blocked_unsupported_labels": [],
  "global_quality": {
    "overall_reliability": "high | medium | low | unknown",
    "baseline_kept": null,
    "baseline_rejected": null,
    "baseline_rejected_not_worn": null,
    "baseline_rejected_artifact": null,
    "baseline_rejected_flatline": null,
    "gamma_guard_count": null,
    "notes": []
  }
}
```

Each item in `tasks_detected` should look like:

```json
{
  "task_number": 5,
  "canonical_task_id": "working_memory",
  "canonical_task_name": "Working Memory",
  "raw_task_labels": ["working_memory"],
  "repeat_status": "not_repeated | repeated_stable | repeated_unstable | insufficient",
  "role_matching_status": "eligible | moderator_only | not_eligible",
  "signal_quality": {
    "quality_level": "high | medium | low | unknown",
    "artifact_flags": [],
    "usable_feature_count": 0,
    "rejected_feature_count": 0,
    "notes": []
  },
  "features": [
    {
      "metric_name": "theta_power_raw",
      "feature_family": "spectral_power",
      "band": "theta",
      "effect_size_d": 0.91,
      "p_value": 0.004,
      "q_value": 0.008,
      "percent_change": 18.2,
      "direction": "increase",
      "grade": "A",
      "passes_neuroprofile_gate": true,
      "feature_strength": "strong",
      "task_supported_characteristics": ["working_memory_load_scaling", "maintenance_and_manipulation"],
      "allowed_onet_ability_candidates": ["Information Ordering", "Memorization", "Deductive Reasoning"],
      "blocked_inferences": ["Reading Comprehension", "Written Comprehension", "Oral Comprehension"],
      "role_matching_status": "eligible",
      "neuroprofile_rationale": "Frontal theta change during Working Memory is treated as task-contextual evidence for load scaling and maintenance/manipulation, not as verbal comprehension."
    }
  ],
  "task_summary": {
    "supported_characteristics": ["working_memory_load_scaling"],
    "allowed_onet_ability_candidates": ["Information Ordering", "Memorization"],
    "moderator_characteristics": [],
    "blocked_inferences": ["Reading Comprehension", "Written Comprehension", "Oral Comprehension"],
    "confidence": "weak | moderate | strong | insufficient",
    "summary": "Bounded task-level summary for Stage 2."
  }
}
```

---

# 10. Global reliability

Use existing baseline QC and feature quality metadata to add:

```python
def compute_neuroprofile_global_quality(existing_analysis: dict, neuroprofile_tasks: list[dict]) -> dict:
    """Return high/medium/low/unknown reliability for neuroprofile export."""
```

Suggested rules:

- high: usable baseline exists, most tasks have clean features, low artifact counters, gamma guards limited, no major task omissions for detected session depth
- medium: partial but usable data, some artifacts or missing features
- low: major artifacts, many rejected baseline windows, few usable task features
- unknown: missing metadata

If all baseline windows are rejected, preserve existing error behavior:

```json
{"error": "No usable baseline data after quality control"}
```

---

# 11. Output compatibility

This refactor must be additive.

Do not break existing frontend or downstream users of `/analyze`.

- Keep existing response shape.
- Add `neuroprofile_feature_export` as a new top-level field.
- Do not rename existing keys unless absolutely necessary.
- Do not remove TGAM compatibility path.
- Raw EEG remains preferred.

---

# 12. Tests

Add tests for:

1. Raw numeric path still works.
2. TGAM path still works.
3. Baseline QC rejection still returns existing error when no baseline is usable.
4. Gamma guard still zeroes gamma features and sets `_emg_guard = 1`, `_gamma_evaluated = 0`.
5. `classify_feature_family("theta_power_raw") == "spectral_power"`.
6. `classify_feature_family("alpha_theta_ratio") == "band_ratio"`.
7. `classify_feature_family("theta_peak_freq") == "peak_feature"`.
8. `classify_feature_family("theta_entropy") == "entropy_complexity"`.
9. `language_processing` never emits Oral Comprehension, Written Comprehension, Reading Comprehension, Speaking, Writing, or Active Listening.
10. `motor_imagery` never emits Manual Dexterity, Finger Dexterity, Reaction Time, or Control Precision.
11. `visual_colour_processing` never emits Visual Color Discrimination.
12. `static_emotion_grasp` never emits Social Perceptiveness.
13. Moderator-only tasks have `role_matching_status = "moderator_only"` and empty `allowed_onet_ability_candidates`.
14. Session 1 tasks infer `protocol_session_depth = "session_1"`.
15. Session 2 tasks infer `protocol_session_depth = "session_2"`.
16. Session 3 tasks infer `protocol_session_depth = "session_3"`.
17. A single weak feature does not add to `allowed_ability_pool` unless convergent.
18. `neuroprofile_feature_export.allowed_ability_pool` contains only allowed downstream O*NET labels.
19. Existing `per_task`, `combined`, and `across_task` outputs remain present.

---

# 13. Acceptance criteria

Done when:

- `/analyze` still performs existing raw EEG and TGAM analysis.
- Existing output remains backward-compatible.
- New top-level `neuroprofile_feature_export` is present.
- Every analyzed task in the export has canonical task metadata.
- Every exported feature has `feature_family`.
- Passing features are mapped to task-supported characteristics.
- Eligible tasks attach allowed downstream O*NET ability candidates.
- Moderator-only tasks do not attach role-matching abilities.
- Unsupported labels are blocked.
- Gamma guarded features are not used as downstream evidence.
- Global reliability is reported.
- No role titles or job recommendations are emitted by this backend.

Remember:
This backend produces structured evidence only. Role matching and neuroprofile generation happen later in the neuroprofile backend.
