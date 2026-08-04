# Optimized Task Battery: Traceability Reference

## Scope and status

This reference describes the `feature/task-battery-v2` implementation: what
each task asks the participant to do, which behavioural evidence it records,
which O*NET ability labels it can support, and how the evidence reaches the
Mindspeller report.

> **Important:** the active profile is
> `mindspeller_optimized_task_battery` `2.0.0-candidate.1`, with status
> **pilot**. Its stimuli, audio, rubrics, and thresholds are all candidate
> components. EEG is task-contextual evidence; it is not a direct measurement
> of an O*NET ability and this profile does not permit normative interpretation.

## End-to-end flow

```text
Task runner
  └─ continuous 4-channel EEG + task metadata + behavioural score
       └─ IndexedDB recording store
            └─ local POST /analyze
                 ├─ matched-baseline EEG analysis
                 ├─ quality, protocol, and provenance checks
                 └─ neuroprofile_feature_export
                      └─ JSON → compressed report envelope
                           └─ POST /api/cas/eeg-reports/seed (Mindspeller)
```

The final Mindspeller request contains the compressed
`neuroprofile_feature_export` JSON, checksum, compression metadata, session
metadata, and protocol type. It does **not** upload the raw EEG arrays.

## Shared acquisition, features, and gates

Every task is a single uninterrupted EEG block. The runner requires the
MindRove sparse montage (`Fp1`, `Fp2`, `O1`, `O2`), stores transport gaps, and
uses two-second rolling windows with 50% overlap. The task and its matched
baseline each need at least 20 contiguous clean seconds. Users can complete
the required tasks in any order and may rerun a task; a replacement is saved
only after its new attempt passes quality control.

For each EEG window, the backend derives 70 values:

- Nine bands: delta, theta, theta1, theta2, alpha, beta, beta1, beta2, gamma.
- Per band: power, raw power, relative power, peak frequency, peak amplitude,
  relative peak amplitude, and entropy.
- Ratios: alpha/theta, beta/alpha, beta2/beta1, and theta2/theta1.
- Total power plus EMG/gamma guard fields.

The traceability export uses the inference-eligible families: spectral power,
relative power, band ratios, entropy/complexity, and total-power summary. Peak
features are not mapped to abilities. Gamma is removed when the EMG guard
fires.

For every eligible task-vs-matched-baseline feature, the report records the
task and baseline means, delta, percentage change, Cohen's *d*, *p*, FDR
adjusted *q*, sample/block counts, direction, gate results, and feature
strength. A feature must clear the statistical/effect-size/percentage-change
gates to become task-contextual evidence; reliability can only reduce its
strength. Raw-power changes require 10%; relative-power and ratio changes
require 5%.

The tasks below share these extracted feature families. “Expected signature”
means a directional expectation used for alignment reporting, **not** an
ability score. Tasks without one are reported descriptively.

## Task-by-task guide

### 1. Adaptive Numerical Reasoning and Sequencing

- **Protocol:** 60 seconds (shortened from the page-47 example's 90s), eyes
  closed, eyes-closed baseline; 30 seconds of slower single operations (4
  operations) followed by 30 seconds of faster mixed operations (5
  operations). Lower-load pace matches the original protocol (~7.67s
  apart); higher-load is slower than the original (~6.75s vs. ~4.5s apart),
  per follow-up user feedback that the initial 60s conversion was too hard.
- **Behavioural evidence:** submitted final value, expected final value, signed
  answer error, and exact-answer flag. The bundled threshold is zero error.
- **Candidate abilities:** Mathematical Reasoning, Number Facility,
  Information Ordering, and Deductive Reasoning.
- **Expected signature:** theta-relative increase. The traceability context is
  continuous numerical updating, increasing calculation load, ordered rule
  application, and sustained calculation control.
- **Report effect:** an exact answer marks all four candidate abilities passed
  in `ability_validation`; they can enter `allowed_onet_ability_candidates`
  only if a scorable EEG feature also clears the traceability gate.

### 2. Working-Memory Manipulation

- **Protocol:** 60 seconds (shortened from the page-47 example's 90s), eyes
  closed, eyes-closed baseline; 30 seconds of maintenance-dominant work
  followed by 30 seconds of manipulation-dominant work. The manipulation
  phase's command count was reduced to keep its pace close to the original;
  the 2 maintenance-phase commands were already at their structural minimum,
  so that phase's spacing compresses instead (~25s -> ~10s apart). Both
  maintenance-phase commands are `maintain`-only (pure holding, no
  transformation), so the maintenance-vs-manipulation phase comparison isn't
  contaminated by a manipulation event landing in the maintenance window.
- **Behavioural evidence:** normalized submitted sequence, expected sequence,
  item-error count, and exact-sequence flag. The bundled threshold is zero
  item errors.
- **Candidate abilities:** Memorization, Information Ordering, and Deductive
  Reasoning.
- **Expected signature:** theta-relative increase. Traceability describes
  sequence maintenance, ordered updates, and the maintenance-to-manipulation
  load change.
- **Report effect:** only an exact sequence can validate these candidate
  abilities; EEG alone cannot promote them.

### 3. Auditory Target Counting

- **Protocol:** 75 seconds (shortened from the page-47 example's 120s; not
  60s, since 3 equal 20s phases would leave zero margin above the
  20-contiguous-clean-second analysis floor), eyes closed, eyes-closed
  baseline; an irregular stream of high target tones and low distractor
  tones, split into early, middle, and late monitoring phases of 25 seconds
  each. Tone and target counts were reduced to preserve the original average
  inter-tone interval and target density rather than compressing either.
- **Behavioural evidence:** target count, count error, exact-count flag, and
  threshold-pass flag. Exact count is a transparent candidate default because
  the source protocol has no final validated tolerance.
- **Candidate abilities:** Selective Attention and Auditory Attention.
- **Expected signature:** none fixed; the report describes modulation. Its
  task context is sustained target monitoring, distractor resistance,
  attention stability, and attention drift.
- **Report effect:** a passed count can validate the two candidate abilities;
  the export keeps the candidate-threshold note so it is not mistaken for a
  normed assessment.

### 4. Semantic Induction and Category Switching

- **Protocol:** 60 seconds (shortened from the page-47 example's 90s; item
  count per phase was reduced from 15 to 10 rather than compressing the pace,
  which stays exactly 3s/item), eyes closed, eyes-closed baseline; infer a
  first organising rule for 30 seconds, then recognise the second rule for 30
  seconds.
- **Behavioural evidence:** correctness of rule one, correctness of rule two,
  and whether the switch was detected. Both rules and the switch are required.
- **Candidate abilities:** Inductive Reasoning and Category Flexibility.
- **Expected signature:** theta-relative increase. Traceability context is
  semantic comparison, rule inference, semantic rule change, and rule
  selection demand.
- **Report effect:** failed or incomplete rule identification blocks both
  ability candidates even when EEG changes are statistically reportable.

### 5. Visuospatial Transformation and Orientation

- **Protocol:** 60 seconds (shortened from the page-47 example's 90s), eyes
  open, eyes-open baseline; lower-density then higher-density spatial
  transformations, 30 seconds each. Move counts were reduced (not the
  interval) to preserve pacing; higher-density stays close to the original
  (~7s -> ~6.75s apart), while lower-density still compresses somewhat
  (~11s -> ~9s apart) since only 18s of span remains available for it.
- **Behavioural evidence:** reported and expected grid position, Manhattan
  position error, reported and expected orientation, and correctness flags.
  Position and orientation must both match exactly.
- **Candidate abilities:** Visualization and Spatial Orientation.
- **Expected signature:** occipital alpha-relative decrease; theta-relative
  increase. Traceability context is visual tracking, spatial-state updating,
  orientation tracking, and controlled spatial transformation.
- **Report effect:** this task is compared only to the eyes-open reference;
  an eyes-closed baseline cannot support its report rows.

### 6. Divergent Ideation

- **Protocol:** 75 seconds (shortened from the page-47 example's 120s),
  eyes closed, eyes-closed baseline; silent idea generation in early, middle,
  and late phases of 25 seconds each, matching Task 3's identical 3-phase
  margin fix (25s/phase keeps a real buffer above the
  20-contiguous-clean-second floor, rather than sitting exactly on it). The
  object prompt is still spoken at the very start of the block. Ideas are
  entered after EEG scoring finishes.
- **Behavioural evidence:** captured idea count and text; optionally, an
  external rubric can supply relevant-idea count, originality, and category
  diversity.
- **Candidate abilities:** Category Flexibility, Fluency of Ideas, and
  Originality.
- **Expected signature:** none fixed; the report describes modulation in the
  context of ideation dynamics, associative breadth, and internal attention.
- **Report effect:** all three abilities remain `pending_review` unless a
  validated external rubric and configured thresholds provide a decision. The
  EEG rows remain useful task-contextual evidence but do not by themselves
  populate the allowed ability pool.

### 7. Dual-Task Performance and Rule Switching

- **Protocol:** 60 seconds (shortened from the page-47 example's 120s), eyes
  closed, eyes-closed baseline; target-tone counting and numerical updating
  run together, with a rule switch after 30 seconds. Unlike other shortened
  tasks, the 3+3 update structure was kept rather than reduced, so its
  spacing compresses uniformly (~20s -> ~9-10s apart) instead of being
  preserved; the tone stream was trimmed to preserve its original pacing.
- **Behavioural evidence:** target-count error, numerical-update error,
  optional dual-task cost, and optional switch cost. Both final outputs must
  be exact. Cost values need matched Tasks 2 and 3 reference metrics and
  validated thresholds.
- **Candidate abilities:** Time Sharing, Category Flexibility, Deductive
  Reasoning, Selective Attention, and Information Ordering.
- **Expected signature:** theta-relative increase. Traceability context is
  interference management, rule-switch demand, competing-stream control, and
  dual-task-cost context.
- **Report effect:** exact outputs can pass every candidate except Time
  Sharing. Time Sharing stays pending until a validated dual-task/switch-cost
  threshold exists. The backend also adds a descriptive continuous comparison
  with the single-task recordings; it is not an ERP or validated cost measure.

### 8. Rule-Based Anomaly Detection

- **Protocol:** 60 seconds (shortened from the page-47 example's 90s), eyes
  open, eyes-open baseline; monitor a visual code stream with lower then
  higher anomaly density, 30 seconds each. The 2s code-entry cadence is
  unchanged; only the number of entries (and anomalies within them) dropped
  with the shorter duration, keeping the density ratio between phases close
  to the original.
- **Behavioural evidence:** anomaly count, count error, selected anomaly
  types, expected types, exact type-recall flag, and optional confidence.
  The count and complete type set must match.
- **Candidate abilities:** Problem Sensitivity, Deductive Reasoning, Selective
  Attention, and Information Ordering.
- **Expected signature:** theta-relative increase and occipital
  alpha-relative decrease. Traceability context is rule monitoring, anomaly
  monitoring, visual inspection, and conflict monitoring.
- **Report effect:** behavioural evidence prevents generic visual activity
  from being labelled as Problem Sensitivity; only the stated task candidates
  can be emitted.

### 9. Rapid Visual Comparison

- **Protocol:** 60 seconds, eyes open, eyes-open baseline; compare changing
  central code pairs and press once after a mismatch is actually rendered. If
  missed, more positions drift apart on a fixed schedule so the rows keep
  diverging; only the first rendered mismatch is scored. Recording continues
  for the full block.
- **Behavioural evidence:** planned and rendered mismatch onset, button time,
  detection accuracy, false-alarm flag, reaction time, and latency-range flag.
  The onset used for scoring is the rendered frame, not the nominal timer.
- **Candidate abilities:** Perceptual Speed and Reaction Time.
- **Expected signature:** occipital alpha-relative decrease and theta-relative
  increase. Traceability context is visual comparison, mismatch monitoring,
  and pre-response visual state.
- **Report effect:** the two seconds immediately before response through the
  scheduled end are excluded from EEG scoring. This preserves a pre-response
  trajectory while retaining the full recorded block and prevents motor
  response contamination from becoming ability evidence.

### 10. Pattern Closure under Visual Noise

- **Protocol:** 60 seconds (shortened from 75s; the 50s reveal ramp itself is
  untouched, only the 20s pre-reveal buffer shrank to 5s), eyes open,
  eyes-open baseline; a target gradually emerges from noise. The response
  button is clickable from the start of the block -- there is no
  minimum-exposure delay -- and recording continues after the button press.
  CLOSURE_FORMS offers 6 plausible options instead of 4 to offset the
  guessing risk from the immediately-clickable button.
- **Behavioural evidence:** target correctness, response time, visibility
  fraction, symbol opacity, and noise opacity.
- **Candidate abilities:** Speed of Closure and Flexibility of Closure.
- **Expected signature:** occipital alpha-relative decrease and theta-relative
  increase. Traceability context is pattern extraction under noise, distractor
  resistance, progressive closure, and recognition threshold.
- **Report effect:** correct recognition supplies candidate Speed of Closure
  evidence. Flexibility of Closure stays pending until a validated
  visibility/noise threshold is configured; when one is, it is credited from
  the reveal fraction at the moment of response (including an immediate,
  correct one -- there is no separate minimum-exposure gate protecting it,
  only the 6-option answer list's 1-in-6 guessing odds).

### 11. Speech-in-Noise Comprehension

- **Protocol:** up to 120 seconds, eyes closed, eyes-closed baseline; a
  continuous passage is delivered with background noise. Recording ends as
  soon as the passage finishes rather than continuing to a fixed ceiling, so
  the scored window tracks each form's own (shorter) length instead of
  including a long silent tail.
- **Behavioural evidence:** main idea and key detail are each chosen from a
  fixed option list and scored against the answer key; the task collects no
  free text.
- **Candidate abilities:** Oral Comprehension, Speech Recognition, and
  Auditory Attention.
- **Expected signature:** none fixed; the report describes modulation in the
  context of listening effort, speech-in-noise attention, and attention drift.
- **Report effect:** fully objective — both items are compared to the answer
  key directly, so nothing here waits on a rubric. SNR-dependent abilities
  still remain pending if the active audio profile is not acoustically
  calibrated. Failed objective items are recorded as failed rather than
  silently upgraded by EEG.

### 12. Written Comprehension and Concise Synthesis

- **Protocol:** 180 seconds, eyes open, eyes-open baseline; 120 seconds of
  paced reading followed by 60 seconds of silent synthesis planning. The
  written response is captured after EEG scoring.
- **Behavioural evidence:** main-idea correctness, summary word count, a
  35–50 word candidate range, and optional rubric scores for quality,
  coherence, and information ordering.
- **Candidate abilities:** Written Comprehension, Written Expression,
  Inductive Reasoning, and Information Ordering.
- **Expected signature:** occipital alpha-relative decrease and theta-relative
  increase. Traceability context is reading engagement, silent synthesis,
  meaning integration, and response-organisation demand.
- **Report effect:** an accurate main idea can pass Written Comprehension.
  Written Expression, Inductive Reasoning, and Information Ordering remain
  pending unless the summary rubric supplies a validated decision.

## How abilities enter the report

Each feature row has three deliberately different ability fields:

| Field | Meaning |
|---|---|
| `theoretical_onet_ability_candidates` | The abilities the task is designed to address. This is not a measurement claim. |
| `behaviorally_validated_onet_ability_candidates` | Only abilities marked `passed` in the task's per-ability behavioural score. |
| `allowed_onet_ability_candidates` | Behaviourally validated abilities that also have scorable, gated, sufficiently strong/convergent EEG task evidence. |

The task summary and top-level `allowed_ability_pool` use the last field.
The export also preserves `blocked_inferences` for every task, preventing an
otherwise plausible label from being inferred from the wrong task. For example,
Task 5 cannot contribute Perceptual Speed and Task 9 cannot contribute Speed
of Closure.

## What is sent to Mindspeller

The local analysis response adds a `neuroprofile_feature_export` object. The
frontend serializes exactly that object, compresses it, and sends it to
`/api/cas/eeg-reports/seed` as the report payload. Its useful sections are:

- **Session identity and provenance:** feature and traceability versions,
  protocol session depth, profile ID/version/status, and whether normative
  interpretation is allowed.
- **Quality controls:** sparse-montage scope, baseline QC counters, global
  reliability, and session confidence cap.
- **Per-task evidence:** canonical task identity, eye-state baseline,
  behavioural evidence/status, task and baseline QC, validity reasons,
  protocol metadata, continuous time-series description, feature rows, and
  task summary.
- **Flat `feature_rows`:** machine-readable task context plus each feature's
  statistics, gates, strength before/after reliability capping, supported
  characteristics, ability fields, and blocked labels.
- **Session aggregation:** allowed and theoretical ability pools, blocked
  labels, and global quality.

No valid report is produced for a task with an incomplete audio delivery,
profile/version mismatch, wrong eye state, missing matched baseline, fewer
than 20 contiguous clean seconds, or another protocol-invalid condition. The
frontend rejects final analysis when `invalid_tasks` is non-empty, before the
Mindspeller seed request is made.

## Source map

- [Task configuration](../ElectronFrontEnd/src/components/tasks/optimizedBatteryConfig.mjs)
- [Pilot profile and thresholds](../ElectronFrontEnd/src/components/tasks/optimizedBatteryProfile.mjs)
- [Behavioural scoring](../ElectronFrontEnd/src/components/tasks/optimizedTaskScoring.mjs)
- [Task metadata construction](../ElectronFrontEnd/src/components/tasks/OptimizedBatteryTask.jsx)
- [Analysis request and Mindspeller upload](../ElectronFrontEnd/src/service/analysisService.js)
- [Report serializer](../ElectronFrontEnd/src/service/reportDocument.mjs)
- [Backend analysis endpoint](../newBackend/main.py)
- [Neuroprofile traceability export](../newBackend/neuroprofile_traceability.py)
