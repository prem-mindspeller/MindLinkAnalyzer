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
| 1 | `adaptive_numerical_reasoning` | closed | eyes closed | 60 |
| 2 | `working_memory_manipulation` | closed | eyes closed | 60 |
| 3 | `auditory_target_counting` | closed | eyes closed | 75 |
| 4 | `semantic_induction_category_switching` | closed | eyes closed | 60 |
| 5 | `visuospatial_transformation_orientation` | open | eyes open | 60 |
| 6 | `divergent_ideation` | closed | eyes closed | 75 |
| 7 | `dual_task_rule_switching` | closed | eyes closed | 60 |
| 8 | `rule_based_anomaly_detection` | open | eyes open | 60 |
| 9 | `rapid_visual_comparison` | open | eyes open | 60 |
| 10 | `pattern_closure_visual_noise` | open | eyes open | 60 |
| 11 | `speech_in_noise_comprehension` | closed | eyes closed | 60 |
| 12 | `written_comprehension_synthesis` | open | eyes open | 90 |

### Authoritative timing source and pilot pacing

Page 47 of the updated `Task_Battery_Optimization.pdf` is the timing authority.
Its twelve durations are, in task-number order: **90, 90, 120, 90, 90, 120,
120, 90, 60, 75, 120 and 180 seconds**. The detailed task pages still contain
their earlier shorter examples. Where those examples do not fill the page-47
window, the active candidate/pilot profile extends the stimulus pacing and
phase plan without changing the canonical task identity. Those extensions are
pilot defaults and must not be described as validated timing norms.

Tasks 1, 2, 3, 4, 5, 6, 7, 8, 10, 11 and 12 are deliberate exceptions in the
other direction: their active blocks are shorter than the page-47 example.
This is still a pilot default, not a validated timing norm.

- Task 1: operation count was first reduced (6 lower-load + 10 higher-load ->
  4 + 7, the 90s->60s conversion) to keep the per-operation pace effectively
  unchanged. After iterating on difficulty per user feedback (briefly 3 + 5,
  then 4 + 6), it settled at 4 + 5: lower-load matches the original pace
  (~7.67s), higher-load is slower than the original (~6.75s vs. ~4.5s).
- Task 2: the manipulation-phase command count was reduced (6 -> 4) the same
  way, keeping its pace close to the original (~8.4s -> ~9s). The
  maintenance-phase command count could not be reduced the same way -- it was
  already at its structural minimum of 2 -- so that phase's spacing
  necessarily compresses (~25s -> ~10s apart) as a direct consequence of the
  shorter block. Both maintenance-phase commands are now `maintain`-only
  (previously one of the two was itself a transformation); all shift/reverse/
  replace commands live in the manipulation phase. This keeps the phase
  comparison uncontaminated -- maintenance-phase EEG reflects pure holding,
  which is also what the Memorization ability claim is evidenced against.
  Both phases remain comfortably above the 20-contiguous-clean-second
  analysis floor (30s each).
- Task 3: shortened to 75s rather than 60s, specifically because it has 3
  equal phases (early/middle/late monitoring) rather than 2. At a flat 60s,
  3x20s phases would sit exactly on the 20-contiguous-clean-second floor with
  zero margin -- any brief signal artifact in any phase would zero out that
  phase's comparison. 25s/phase keeps a real buffer. Tone count and target
  count were both reduced (70/16, 68/15, 72/17 -> 43/10, 42/9, 45/11) to
  preserve the original average inter-tone interval (~1.64s-1.74s) and target
  density (~22-24%) rather than compressing either.
- Task 4: item count per phase was reduced (15 -> 10) rather than compressing
  the interval between items, so the pace is exactly unchanged (45s/15 =
  30s/10 = 3s/item either way).
- Task 5: move counts were reduced (4 lower-density + 7 higher-density -> 3 +
  5) rather than compressing the interval between moves. Higher-density
  pace stays close to the original (7s -> 6.75s); lower-density pace still
  compresses (11s -> 9s) since only 18s of span is available for it once the
  phase itself is 30s.
- Task 6: initially shortened to a flat 60s (3x20s phases), then bumped to
  75s (25s/phase) to match Task 3's same 3-equal-phase margin fix, once it
  became clear the zero-slack floor risk applied here too. The object prompt
  is still spoken at t=0 as required; nothing else is scheduled across the
  block, so there was no pacing to preserve -- the phase floor was the only
  real trade-off, and it affects the EEG early/middle/late comparison only
  (behavioral scoring is against the whole response, not per-phase).
- Task 7: unlike Tasks 1-6, the 3+3 update structure (per phase, before and
  after the rule switch) was deliberately kept rather than reduced, per
  explicit user request, so its spacing compresses uniformly by half
  (~20s -> ~9-10s apart) instead of being preserved. The tone stream was
  trimmed the same way as Task 3's (70/10, 68/10, 72/10 -> 34/5, 33/5, 35/5)
  to preserve its ~1.64-1.74s pacing. `maximumSwitchCost` did not need
  re-deriving: it assumes exactly 3 post-switch updates, and that count
  didn't change -- only their timing did.

  The tone stream and the spoken "Start"/"Update"/"Switch" cues are scheduled
  independently, so after the 60s conversion some cues landed close enough to
  a tone to overlap it in playback. `nudgeAwayFromTones` (in
  optimizedBatteryConfig.mjs) shifts only the audio-scheduling copy of each
  cue's time to the nearest moment at least 0.6s from every tone -- the
  logical `updateTimes` used for before/after-switch scoring are untouched,
  so this is audio-only and doesn't affect correctness.
- Task 8: entryIntervalSeconds is a fixed 2s cadence, not derived from
  dividing a span across a count, so the pace was automatically unchanged --
  entryCount simply dropped from 45 to 30 along with the shorter duration.
  Anomaly slot positions were rescaled to the new phase boundaries and
  reduced proportionally (3 lower-density + 6 higher-density -> 2 + 4) to
  keep the density *ratio* between phases -- the actual point of this task --
  close to the original (~13% -> ~27%, roughly double either way).
- Task 10: shortened from 75s to 60s. Its single phase spans the whole
  block, so the phase floor was never a risk; the constraint was the 50s
  reveal ramp itself (`revealStartSeconds` -> `fullyVisibleSeconds`), which
  IS the Speed/Flexibility of Closure manipulation and was left untouched --
  only the 20s pre-reveal buffer was trimmed, to 5s. Per explicit user
  request, `responseEnabledSeconds` (a minimum-exposure delay of 25s before
  a response could even be scored) was removed entirely: the "Recognized"
  button is now clickable from the start of the block, and the scoring gate
  that mirrored it (`clickedAfterMinimum` in optimizedTaskScoring.mjs) was
  removed the same way, so the frontend and the scorer agree on what counts
  as a valid response. To offset the resulting guessing risk, CLOSURE_FORMS
  now offers 6 plausible same-silhouette options instead of 4 (1-in-6 odds
  instead of 1-in-4 for a blind guess).
- Task 11: shortened from 120s to 60s. Unlike Tasks 1-8's repetition-count
  tasks, Task 11's core manipulation is a single narrated passage played
  against calibrated noise, so there was no repetition count to trim -- the
  passages in `SPEECH_BASE_FORMS` were shortened instead (~206-216 words ->
  ~101-110 words) so the same `playbackRate` (0.85) and noise calibration
  (11.5 dB SNR) still deliver the whole passage comfortably inside the
  shorter block. The first shortened revision was produced by trimming the
  original passages sentence-by-sentence; per user feedback that the result
  read as unclear/choppy by ear, the three passages were rewritten from
  scratch as short, simple single-character narratives (a lost dog following
  a smell home, a boy solving a rabbit problem, a librarian starting a
  reading club) instead -- one clear problem and one clear resolution each,
  in short plain sentences with no compound clauses. The narration was
  re-synthesized (Windows SAPI) and re-mixed against the same seeded noise
  at the same 11.5 dB target; the longest resulting narration (`speech_c`,
  42.38s raw) finishes at 0.5s onset + 42.38s / 0.85 = 50.4s, ~10s inside
  the 60s ceiling. Its single phase spans the whole block, so the
  20-contiguous-clean-second phase floor was never a risk at any point in
  this task's history. `mainIdea`/`keyDetail` answer keys and their
  distractor option lists were rewritten to match: each distractor is
  either an element the new passage actually names (e.g. the cloth and
  fence Sam tried before marigolds worked) or a plausible-but-unmentioned
  guess, matching the original design intent that no option should be
  dismissible on sight.
- Task 12: shortened from 180s to 90s. As with Task 11, the passage in
  `WRITTEN_BASE_FORMS` was condensed (~178-196 words -> ~91-97 words) rather
  than the reading window compressed around it, so the same paced-reading
  pace (~1.5-1.6 words/sec) is preserved. The original 120s/60s reading/
  synthesis ratio (2:1) was kept, just scaled down to 60s/30s; both phases
  stay well clear of the 20-contiguous-clean-second floor. Unlike Task 11,
  the summary word-count gate (`thresholds[TASK.WRITTEN].summaryMinimumWords`/
  `summaryMaximumWords`) was deliberately scaled down too, from 35-50 to
  20-30 words, so the required synthesis stays proportional to the shorter
  passage (roughly the same ~20-30% summary-to-passage ratio as before)
  rather than asking for a summary nearly as long as the passage itself.
  `written_c` needed one extra sentence break (5 -> 7 sentences) beyond the
  literal word trim: with exactly `chunkCount` (5) sentences, the paced-chunk
  algorithm's greedy word-share heuristic could land a chunk boundary with no
  sentences left to give it, producing an empty on-screen chunk -- the same
  class of edge case as Task 5's `route_c` grid-boundary issue, fixed the
  same way, by giving the algorithm slack rather than special-casing it.
  Per user feedback that these condensed passages read as unclear, they were
  later rewritten from scratch as short, simple single-character narratives
  (a boy retrieving a kite from a tree, a baker fixing a forgotten
  ingredient, a family relocating a tree before it damaged their house) at
  ~94-99 words each -- the same length as, not shorter than, the passages
  they replaced, and each with a comfortable 8-9 sentences so the
  `route_c`/`written_c`-style empty-chunk risk above has real margin rather
  than landing exactly on `chunkCount`. `mainIdea` and its distractor options
  were rewritten to match, with the correct answer's list position varied
  across the three forms so it is not positionally guessable. The free-text
  summary is graded by an external rubric service that reads `form.passage`
  as its reference material at grading time (`rubricGradingService.mjs`), so
  no grading-side code changes were needed -- the new stories flow through
  automatically.

### Multiple-choice option order

Four tasks render plain-text `<select>` options scored by comparing the
selected string's value, never its index: Task 4's `ruleOptions`/
`secondRuleOptions`, Task 10's `options`, Task 11's `mainIdeaOptions`/
`keyDetailOptions`, and Task 12's `mainIdeaOptions`. Auditing every form's
authored order found the correct answer at index 0 (the first rendered
option) in all three forms of both Task 4 and Task 10, with no exception --
an unintentional, learnable pattern. `randomizeMultipleChoiceOrder`
(`optimizedBatteryConfig.mjs`) now shuffles each of these fields with an
unseeded Fisher-Yates shuffle, applied once per task attempt in
`OptimizedBatteryTask.jsx` (memoized on `[taskId, sessionDepth]`, so it does
not reshuffle mid-attempt on the component's periodic re-renders) rather
than baked into the form data. This is deliberately unseeded, unlike the
stimulus generators elsewhere in the same file (`toneForm`/`anomalyForm`/
etc.), whose whole point is reproducible content: display order should be
genuinely unpredictable per attempt, not a fixed property of the form,
otherwise the correct answer's position is just as learnable as
always-first was -- both within one participant's three fixed sessions and
across many participants comparing notes. `taskFormForSession` itself stays
a pure, deterministic lookup (tests and scoring still rely on that), and
scoring is unaffected either way since every comparison is by value.

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
