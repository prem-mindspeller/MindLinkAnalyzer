# Optimized Task Battery candidate/pilot implementation contract

This note records how `Task_Battery_Optimization.pdf` is implemented in the
MindLink Analyzer. The current stimuli and scoring are a candidate/pilot
configuration, never validated production norms. Version identifiers in the
active protocol profile are stored with every task result.

## Implemented session contents

The protocol is cumulative. Users may complete the required tasks in any order;
the lists below define the required tasks, not an enforced sequence:

- Session 1: Task 3, Task 2, Task 1, Task 4.
- Session 2: Task 3, Task 2, Task 1, Task 4, Task 6, Task 7, eyes-open
  baseline, Task 9, Task 5, Task 8.
- Session 3: Task 3, Task 2, Task 1, Task 4, Task 6, Task 7, Task 11,
  eyes-open baseline, Task 9, Task 5, Task 8, Task 10, Task 12.

The session-1 eyes-closed baseline is required before any task. The eyes-open
fixation baseline is required before any eyes-open task in sessions 2 and 3.
Completion is scoped to both battery version and protocol session; an older
completion marker cannot unlock a new run.

## Canonical tasks and page-47 block durations

| # | Canonical task ID | Eyes | Matched baseline | Block seconds |
|---:|---|---|---|---:|
| 1 | `adaptive_numerical_reasoning` | closed | eyes closed | 90 |
| 2 | `working_memory_manipulation` | closed | eyes closed | 90 |
| 3 | `auditory_target_counting` | closed | eyes closed | 120 |
| 4 | `semantic_induction_category_switching` | closed | eyes closed | 90 |
| 5 | `visuospatial_transformation_orientation` | open | eyes open | 90 |
| 6 | `divergent_ideation` | closed | eyes closed | 120 |
| 7 | `dual_task_rule_switching` | closed | eyes closed | 120 |
| 8 | `rule_based_anomaly_detection` | open | eyes open | 90 |
| 9 | `rapid_visual_comparison` | open | eyes open | 60 |
| 10 | `pattern_closure_visual_noise` | open | eyes open | 75 |
| 11 | `speech_in_noise_comprehension` | closed | eyes closed | 120 |
| 12 | `written_comprehension_synthesis` | open | eyes open | 180 |

### Authoritative timing source and pilot pacing

Page 47 of the updated `Task_Battery_Optimization.pdf` is the timing authority.
Its twelve durations are, in task-number order: **90, 90, 120, 90, 90, 120,
120, 90, 60, 75, 120 and 180 seconds**. The detailed task pages still contain
their earlier shorter examples. Where those examples do not fill the page-47
window, the active candidate/pilot profile extends the stimulus pacing and
phase plan without changing the canonical task identity. Those extensions are
pilot defaults and must not be described as validated timing norms.

### Versioned configuration contract

The active protocol profile is `mindspeller_optimized_task_battery`, version
`2.0.0-candidate.1`, with `validation_status: pilot`. Its four independently
versioned components are all explicitly marked `candidate`:

| Component | Active ID | Active version |
|---|---|---|
| Stimuli | `mindspeller_parallel_forms_en` | `2.0.0-candidate.1` |
| Audio | `mindspeller_browser_generated_audio` | `1.1.0-candidate.1` |
| Rubrics | `mindspeller_candidate_rubrics` | `1.1.0-candidate.1` |
| Thresholds | `mindspeller_candidate_thresholds` | `1.1.0-candidate.1` |

Timings and phase plans, stimulus forms, audio source descriptors, rubric
definitions and scoring thresholds are data in the versioned profile rather
than constants embedded in the task runner. A future owner-approved profile
can therefore register normed parallel forms, fixed audio assets, approved
rubrics and validated thresholds and then become the active binding without a
rewrite of the React task engine. Activating such a profile still requires the
normal reviewed build and release process. Every result carries the profile
reference and component versions so analyses cannot silently combine different
configurations. A version, task-duration or component-reference mismatch is
rejected rather than being interpreted as the active protocol.

## Acquisition and analysis safeguards

- Only complete Fp1/Fp2/O1/O2 WebSocket batches enter a new task or baseline
  recording. Scalar fallback is prohibited for this battery.
- Each task is one continuous recording. Responses are captured after EEG
  scoring, except the single detection/recognition button used by Tasks 9 and
  10. For those two pilot tasks, clicking records the behavioural response but
  does not end acquisition: the block recording continues for the complete
  page-47 duration of 60 or 75 seconds. To prevent motor and post-response
  contamination, the analyzable trajectory ends two seconds before the actual
  response; the interval from `response - 2 s` through the scheduled block end
  is explicitly excluded. Thus the stored block duration remains exact while
  the scored EEG segment is deliberately pre-response and can be shorter.
- Spoken stimuli depend on the host's Web Speech API and are therefore currently
  Windows-only: Electron on Linux exposes the API but has no voices, so `speak()`
  fails immediately with `synthesis-failed`. Tasks 1, 2, 4, 7 and 11 cannot be
  delivered there and their attempts are rejected by the audio audit below rather
  than scored. Supplying premixed assets removes the dependency. See
  `ElectronFrontEnd/DOCUMENTATION.md` section 13.
- Spoken cues, tones and the Task-11 noise source have delivery-audit markers.
  The browser's actual speech start/end callbacks and WebAudio start/end state
  are recorded separately from planned dispatch markers. Missing, failed or
  unfinished required audio makes the attempt protocol-invalid and therefore
  unscorable; it is not silently accepted as a complete task.
- Transport discontinuities are stored as zero-based, end-exclusive segments.
  The backend analyzes segments independently and uses their elapsed-time
  origins for phase assignment. It never joins clean runs or inference blocks
  across a dropout.
- Analysis uses two-second rolling windows with 50% overlap. A task and its
  matched baseline each require at least 20 contiguous clean seconds.
- A failed quality check saves neither the recording nor task completion. The
  failed task, or its failed matched baseline, must be recorded again.
- A user may rerun any task. The accepted recording and behavioural metadata
  are replaced only when the new attempt passes quality control; a failed
  repeat leaves the previously accepted attempt intact.
- Task-versus-baseline comparison is eye-state matched. Eyes-open tasks are not
  evaluated only against the eyes-closed reference.
- A session baseline condition is analyzed once and reused by every task that
  matches its eye state. The pooled combined comparison therefore counts each
  baseline's windows a single time; it does not restate one eyes-closed
  recording as seven independent references because seven tasks matched it.
- Temporal output is descriptive and continuous (mean, standard deviation and
  slope per minute). Event markers are audit metadata, not ERP or
  stimulus-locked analysis inputs. Peak features are excluded from inference
  and export.
- Final analysis is blocked until every required baseline condition and every
  canonical task expected for the active session has a non-empty durable
  IndexedDB recording. Raw EC/EO arrays are not stored in Web Storage;
  `baselineCalibration` is only a compact, attempt-linked UI/compatibility
  manifest. Legacy `calibrationData_*` arrays migrate only after the durable
  copy commits.
- At 500 Hz, one 60-second four-channel baseline contains about 30,000 sample
  objects. Depending on integer width, its JSON occupies roughly 1.2–2.0 MiB
  before Web Storage's UTF-16 accounting; two phases can therefore consume
  roughly 4.8–8.0 MiB of DOM-storage budget. IndexedDB avoids that quota edge
  and the synchronous stringify/parse pause in the renderer.
- Baseline completion is bound to both protocol session and battery version.
  Finish and every logout clear both baseline conditions, completion markers,
  participant/session selectors and the entire IndexedDB recording namespace,
  including interrupted attempts, before another participant can begin.

## Behavioral and O*NET gating

EEG features are task-contextual evidence, not direct ability measurements.
The backend keeps theoretical task-to-ability candidates separate from the
abilities that pass behavioral validation. Per-ability validation is
authoritative; a pending or failed ability cannot be promoted by the task's
overall status.

The following limitations are deliberately represented as pending rather than
filled with invented scores:

- Task 3 uses exact target count as the transparent candidate threshold because
  the optimization document does not define a final tolerance.
- Task 6 stores the ideas, but relevance, category diversity and originality
  need an approved human or validated automated rubric.
- Task 7 validates the two exact outputs. Time Sharing remains pending until
  matched Task 2/3 behavioural cost metrics and a validated threshold are
  defined. Its EEG export does include explicitly descriptive, non-event-locked
  Task-7 versus Task-2/Task-3 feature-mean contrasts; these are not interpreted
  as validated dual-task or switch costs.
- Task 11 uses a calibrated, premixed audio asset (built via
  `tools/build_speech_in_noise_assets.py`), so SNR-dependent abilities are not
  gated on calibration status by default; the uncalibrated browser-TTS path
  remains available as a fallback profile and still leaves those abilities
  pending. Its main-idea and key-detail answers are both selected from a fixed
  option list and scored against the answer key, so Oral Comprehension
  resolves objectively rather than waiting on a rubric — the task collects no
  free text at all. Playback is slowed to 0.85x for comprehension, and the
  recording block ends as soon as the passage finishes rather than running to
  a fixed ceiling.
- Task 12 can objectively validate its main-idea item. Written Expression,
  synthesis and information-ordering judgments await an approved summary
  rubric.

Unknown or legacy task labels are not silently reinterpreted as one of the new
canonical tasks.

## Stimulus status

Three deterministic English parallel forms are supplied for each task and
rotate by first protocol exposure. They make the end-to-end recorder runnable,
reproducible and auditable. The enclosing profile is marked `pilot` and the
stimulus, audio, rubric and threshold components are each marked `candidate`;
none of these labels represents validated production norms. A production
research release still requires owner-approved, versioned and preferably
normed stimulus packs, including:

1. calibrated fixed-SNR audio files for Task 11;
2. validated parallel-form equivalence and performance thresholds;
3. approved rubrics for Tasks 6, 11 and 12; and
4. confirmation of language/localisation requirements.

Replacing a stimulus pack does not require changing the canonical task IDs or
rebuilding the task engine. Every stored task result includes the protocol and
component versions, form ID, eye state, phase plan, event audit trail,
transport segmentation, quality requirements and behavioral evidence.

Task 9 presents synchronously changing code pairs and introduces a mismatch at
one position. Reaction time is measured from the first animation frame on
which that mismatch was actually rendered, not from its nominal timer
dispatch. If it goes undetected, further positions drift apart on a fixed
schedule so the two rows keep diverging rather than staying at one
easy-to-miss difference for the rest of the block; only the first rendered
mismatch is used for scoring. Task
10 presents separately clipped target fragments in dense visual noise. Correct
identification can validate the candidate Speed of Closure outcome; Flexibility
of Closure remains pending until a validated visibility/noise threshold is
approved. For both tasks, the 60/75-second value denotes the full recorded
pilot block; as specified above, the analysis trajectory remains strictly
pre-response to protect it from response-related contamination.

## Release integration prerequisite

Electron starts `newBackend/dist/MindlinkBackend/MindlinkBackend.exe` in local
development and packages that same prebuilt directory as an extra resource.
The source implementation in `newBackend/main.py` and
`newBackend/neuroprofile_traceability.py` therefore does not reach the shipped
application until the Windows PyInstaller backend is rebuilt and copied into
that path. The repository currently contains no `newBackend/dist` directory.
Rebuild the backend, install the frontend dependencies, produce the Electron
bundle, and run a four-channel Mindrove end-to-end validation before treating
this as a production release.
