/**
 * Versioned protocol configuration for the optimized battery.
 *
 * This module deliberately contains data, not task-runner behaviour. A future
 * validated profile can replace these values (and register its own stimulus
 * forms in optimizedBatteryConfig.mjs) without changing the React task engine.
 */

const deepFreeze = (value) => {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
};

const TASK = Object.freeze({
  NUMERICAL: 'adaptive_numerical_reasoning',
  WORKING_MEMORY: 'working_memory_manipulation',
  AUDITORY_COUNT: 'auditory_target_counting',
  SEMANTIC: 'semantic_induction_category_switching',
  VISUOSPATIAL: 'visuospatial_transformation_orientation',
  IDEATION: 'divergent_ideation',
  DUAL_TASK: 'dual_task_rule_switching',
  ANOMALY: 'rule_based_anomaly_detection',
  VISUAL_COMPARISON: 'rapid_visual_comparison',
  CLOSURE: 'pattern_closure_visual_noise',
  SPEECH_NOISE: 'speech_in_noise_comprehension',
  WRITTEN: 'written_comprehension_synthesis',
});

const phase = (id, label, startSeconds, endSeconds) => ({
  id,
  label,
  startSeconds,
  endSeconds,
});

const taskTimings = {
  [TASK.NUMERICAL]: {
    // Shortened from the page-47 example's 90s to 60s (see docs). Stimulus
    // pacing is preserved by removing operations rather than compressing the
    // interval between them -- see NUMERICAL_FORMS in optimizedBatteryConfig.mjs.
    durationSeconds: 60,
    phases: [
      phase('lower_load', 'Slower single operations', 0, 30),
      phase('higher_load', 'Faster mixed operations', 30, 60),
    ],
  },
  [TASK.WORKING_MEMORY]: {
    // Shortened from the page-47 example's 90s to 60s (see docs). The 2
    // maintenance-phase commands are already at the structural minimum for
    // this task (memoryForm hardcodes lowerCount = 2), so their spacing
    // necessarily compresses (25s -> 10s apart) -- there is nothing left to
    // remove there. The manipulation-phase count was reduced instead
    // (6 -> 4 commands) specifically to keep ITS pace close to the original
    // (8.4s -> 9s apart). See MEMORY_FORMS in optimizedBatteryConfig.mjs.
    durationSeconds: 60,
    phases: [
      phase('maintenance', 'Maintenance-dominant', 0, 30),
      phase('manipulation', 'Manipulation-dominant', 30, 60),
    ],
  },
  [TASK.AUDITORY_COUNT]: {
    // Shortened from the page-47 example's 120s to 75s (see docs), not to 60s:
    // 3 equal phases at exactly 20s each would clear the analysis floor with
    // zero margin, so 25s/phase keeps a real buffer. Tone count was reduced
    // (not the interval) to preserve pacing -- see AUDITORY_FORMS in
    // optimizedBatteryConfig.mjs.
    durationSeconds: 75,
    phases: [
      phase('early', 'Early monitoring', 0, 25),
      phase('middle', 'Middle monitoring', 25, 50),
      phase('late', 'Late monitoring', 50, 75),
    ],
  },
  [TASK.SEMANTIC]: {
    // Shortened from the page-47 example's 90s to 60s (see docs). Item count
    // per phase was reduced (15 -> 10) rather than compressing the interval
    // between items, so the per-item pace is unchanged (45/15 = 30/10 = 3s
    // exactly) -- see itemsPerPhase below and SEMANTIC_FORMS in
    // optimizedBatteryConfig.mjs.
    durationSeconds: 60,
    phases: [
      phase('rule_one', 'First organising principle', 0, 30),
      phase('rule_two', 'Second organising principle', 30, 60),
    ],
  },
  [TASK.VISUOSPATIAL]: {
    // Shortened from the page-47 example's 90s to 60s (see docs). Move
    // counts were reduced (4 lower + 7 higher -> 3 + 5) rather than
    // compressing the interval between moves. The lower-density pace still
    // compresses somewhat (11s -> 9s apart) because only 18s of span is
    // available for it once the phase itself is 30s; the higher-density
    // pace stays close to the original (7s -> 6.75s) -- see ROUTE_FORMS in
    // optimizedBatteryConfig.mjs.
    durationSeconds: 60,
    phases: [
      phase('lower_density', 'Lower transformation density', 0, 30),
      phase('higher_density', 'Higher transformation density', 30, 60),
    ],
  },
  [TASK.IDEATION]: {
    // Shortened from the page-47 example's 120s to 75s (25s/phase), matching
    // Task 3's same 3-equal-phase shape: a flat 60s (20s/phase) would sit
    // exactly on the 20-contiguous-clean-second analysis floor with zero
    // slack, so any brief signal artifact in a phase would zero out that
    // phase's early/middle/late comparison. 25s/phase keeps a real buffer.
    // minimumRelevantIdeas/minimumCategoryDiversity/minimumOriginality are
    // scored against the whole response, not per-phase, so behavioral
    // scoring itself was never affected by this -- only the EEG phase
    // comparison carries the risk this margin protects against.
    durationSeconds: 75,
    phases: [
      phase('early', 'Early ideation', 0, 25),
      phase('middle', 'Middle ideation', 25, 50),
      phase('late', 'Late ideation', 50, 75),
    ],
  },
  [TASK.DUAL_TASK]: {
    // Shortened from the page-47 example's 120s to 60s per explicit user
    // request. The 3+3 update structure was kept (not reduced), so its
    // spacing compresses uniformly by half (~20s -> ~9-10s apart) rather
    // than being preserved -- unlike most other tasks in this batch, this is
    // a deliberate choice to accept a tighter pace over losing trials, since
    // switchCost's threshold derivation assumes exactly 3 post-switch
    // updates (see thresholds[DUAL_TASK] below) and changing that count
    // would have required re-deriving it. The tone stream was trimmed the
    // same way as Task 3's, to preserve its pacing -- see dualTaskForm calls
    // in optimizedBatteryConfig.mjs.
    durationSeconds: 60,
    phases: [
      phase('before_switch', 'Before rule switch', 0, 30),
      phase('after_switch', 'After rule switch', 30, 60),
    ],
  },
  [TASK.ANOMALY]: {
    durationSeconds: 90,
    phases: [
      phase('lower_density', 'Lower anomaly density', 0, 45),
      phase('higher_density', 'Higher anomaly density', 45, 90),
    ],
  },
  [TASK.VISUAL_COMPARISON]: {
    durationSeconds: 60,
    phases: [phase('pre_response', 'Continuous comparison', 0, 60)],
  },
  [TASK.CLOSURE]: {
    durationSeconds: 75,
    phases: [phase('pre_response', 'Progressive visual closure', 0, 75)],
  },
  [TASK.SPEECH_NOISE]: {
    durationSeconds: 120,
    phases: [phase('listening', 'Continuous listening', 0, 120)],
  },
  [TASK.WRITTEN]: {
    durationSeconds: 180,
    phases: [
      phase('paced_reading', 'Paced central reading', 0, 120),
      phase('silent_synthesis', 'Silent synthesis', 120, 180),
    ],
  },
};

const audioProfiles = {
  supportedSourceModes: [
    'web_audio_oscillator',
    'browser_speech_synthesis',
    'browser_speech_synthesis_with_generated_noise',
    'premixed_audio_asset',
  ],
  countdown: {
    mode: 'web_audio_oscillator',
    waveform: 'sine',
    frequencyHz: 800,
    durationMs: 130,
    outputGain: 0.22,
  },
  spoken_stimuli: {
    mode: 'browser_speech_synthesis',
    assetUri: null,
    assetSha256: null,
    assetsByForm: {},
    assetsByStimulusKey: {},
    language: 'en-US',
    voiceId: null,
    rate: 0.94,
    pitch: 1,
    volume: 0.9,
    acousticallyCalibrated: false,
  },
  speech_in_noise: {
    mode: 'premixed_audio_asset',
    // Built with tools/build_speech_in_noise_assets.py from narration of the
    // (simplified, plain-language) passages in SPEECH_BASE_FORMS, mixed
    // against the same seeded noise `noise` below describes (seed 11011,
    // looped 2s buffer) and re-measured after mixing rather than assumed.
    // Narration source: Windows SAPI (Microsoft David Desktop voice) via
    // tools/synthesize_speech_a.ps1 — Piper TTS is not available in every
    // environment this repo is built in, but SAPI's WAV output (22050 Hz,
    // mono, 16-bit PCM) matches the mixer's expected format directly.
    // Regenerate with: python3 tools/build_speech_in_noise_assets.py
    // --narration-dir tools/narration --target-snr-db 11.5
    assetUri: null,
    assetSha256: null,
    assetsByForm: {
      speech_a: {
        uri: 'audio/speech_a_snr11p5.wav',
        sha256: '60146104135cd7b45cb4df3d7aaaeb983143f6deaa220b0b78c33e4a48fade9d',
      },
      speech_b: {
        uri: 'audio/speech_b_snr11p5.wav',
        sha256: 'abfb41097798a92f0f3ff62d70a5e768d47e481f13e7cb7d338dedb83ec8e737',
      },
      speech_c: {
        uri: 'audio/speech_c_snr11p5.wav',
        sha256: 'fba64eeef31477abc88a677169e562d072969cf1971f2e72b71ca7b076bf2d9e',
      },
    },
    assetsByStimulusKey: {},
    // rate/pitch/voiceId/language below are for the browser_speech_synthesis
    // fallback mode only; unused while mode is premixed_audio_asset.
    language: 'en-US',
    voiceId: null,
    rate: 0.88,
    pitch: 1,
    volume: 0.9,
    // <1 slows delivery down (Chromium/Electron's HTMLMediaElement applies
    // pitch-preserving time-stretching by default, so this narrows the pace
    // without a chipmunk/deep-voice pitch shift). Only meaningful for
    // premixed_audio_asset playback; read by speak() in OptimizedBatteryTask.jsx.
    playbackRate: 0.85,
    // 11.5 dB == noise RMS at 75% of its level at the previous 9 dB setting
    // (noise 25% quieter than before, not 25% quieter than the speech itself).
    nominalSnrDb: 11.5,
    acousticallyCalibrated: true,
    // Shortest of the three narrations (speech_a, 75.7s) played at
    // playbackRate above; kept conservative so this is never overstated
    // relative to what actually plays.
    expectedDeliverySeconds: 89,
    settlingSeconds: 5,
    // Documents the noise this asset was calibrated against, for audit and
    // regeneration; not read by the runtime while mode is premixed_audio_asset.
    noise: {
      type: 'seeded_white_noise',
      seed: 11011,
      bufferSeconds: 2,
      sampleAmplitude: 0.14,
      outputGain: 0.12,
    },
  },
  target_tones: {
    mode: 'web_audio_oscillator',
    targetAssetUri: null,
    targetAssetSha256: null,
    distractorAssetUri: null,
    distractorAssetSha256: null,
    assetsByForm: {},
    assetsByStimulusKey: {},
    waveform: 'sine',
    targetFrequencyHz: 880,
    distractorFrequencyHz: 440,
    durationMs: 115,
    outputGain: 0.22,
    acousticallyCalibrated: false,
  },
};

const presentation = {
  [TASK.NUMERICAL]: { finalQuietSeconds: 3, firstStimulusSeconds: 4 },
  [TASK.WORKING_MEMORY]: { finalQuietSeconds: 3, firstUpdateSeconds: 10 },
  [TASK.AUDITORY_COUNT]: { firstToneSeconds: 0.4, finalQuietSeconds: 1.4 },
  // Descriptive only -- the scheduler actually reads form.phaseOne.length /
  // form.phaseTwo.length (see SEMANTIC_FORMS), so keep this in sync by hand.
  [TASK.SEMANTIC]: { itemsPerPhase: 10 },
  [TASK.VISUOSPATIAL]: { finalQuietSeconds: 3 },
  // Divergent ideation is a silent generation block with no scheduled visual
  // stimuli (its only audio is the spoken prompt at task start), so it carries
  // no presentation timing parameters. The entry must still exist:
  // taskPresentationFor() throws for any unconfigured task.
  [TASK.IDEATION]: {},
  [TASK.DUAL_TASK]: { finalQuietSeconds: 3 },
  [TASK.ANOMALY]: { entryIntervalSeconds: 2 },
  [TASK.VISUAL_COMPARISON]: { updateIntervalSeconds: 3 },
  [TASK.CLOSURE]: {
    revealStartSeconds: 20,
    fullyVisibleSeconds: 70,
    responseEnabledSeconds: 25,
    maximumBlurPx: 18,
    initialNoiseOpacity: 1,
    minimumNoiseOpacity: 0.08,
    fragmentOrder: [5, 10, 1, 14, 7, 8, 2, 13, 4, 11, 0, 15, 6, 9, 3, 12],
  },
  [TASK.SPEECH_NOISE]: { passageOnsetSeconds: 0.5 },
  [TASK.WRITTEN]: {
    readingDurationSeconds: 120,
    synthesisDurationSeconds: 60,
    chunkCount: 5,
  },
};

const rubrics = {
  [TASK.NUMERICAL]: { id: 'exact_final_answer', mode: 'objective_key' },
  [TASK.WORKING_MEMORY]: { id: 'exact_final_sequence', mode: 'objective_key' },
  [TASK.AUDITORY_COUNT]: { id: 'candidate_counting_error', mode: 'objective_key' },
  [TASK.SEMANTIC]: { id: 'answer_key_and_switch', mode: 'objective_key' },
  [TASK.VISUOSPATIAL]: { id: 'position_and_orientation_key', mode: 'objective_key' },
  // Rubric ids must match cas_services/task_battery_rubric_grader.py in the
  // backend: the grader refuses to score when the client's id disagrees, so a
  // result is never recorded under a rubric it was not graded against.
  [TASK.IDEATION]: {
    id: 'ideation_model_rubric_v1',
    mode: 'model_rubric_plus_thresholds',
    dimensions: ['relevantIdeaCount', 'categoryDiversity', 'originality'],
  },
  [TASK.DUAL_TASK]: { id: 'exact_outputs_with_reference_costs', mode: 'objective_plus_thresholds' },
  [TASK.ANOMALY]: { id: 'count_and_anomaly_type_key', mode: 'objective_key' },
  [TASK.VISUAL_COMPARISON]: { id: 'single_rendered_onset_latency', mode: 'objective_key_and_latency' },
  [TASK.CLOSURE]: { id: 'recognition_and_visibility_schedule', mode: 'objective_plus_thresholds' },
  [TASK.SPEECH_NOISE]: {
    // Both main_idea and key_detail are selected from a fixed option list and
    // scored against the answer key — no free text, no model rubric.
    id: 'main_idea_and_key_detail_selection',
    mode: 'objective_key',
  },
  [TASK.WRITTEN]: {
    id: 'written_synthesis_model_rubric_v1',
    mode: 'objective_plus_model_rubric',
    dimensions: ['clarity', 'coherence', 'completeness', 'information_ordering'],
  },
};

const thresholds = {
  [TASK.NUMERICAL]: { maximumAbsoluteFinalError: 0 },
  [TASK.WORKING_MEMORY]: { maximumItemErrors: 0 },
  [TASK.AUDITORY_COUNT]: { maximumAbsoluteCountError: 0 },
  [TASK.SEMANTIC]: { requireBothRules: true, requireSwitchDetection: true },
  [TASK.VISUOSPATIAL]: { maximumPositionError: 0, requireOrientationMatch: true },
  [TASK.IDEATION]: {
    // Candidate engagement/validity floors, not performance norms. Published
    // Alternate-Uses fluency for a 120 s block sits well above these; they are
    // set low deliberately so they reject an empty or single-theme response
    // without asserting a normative creativity cut-off.
    // relevantIdeaCount: integer; categoryDiversity: integer count of distinct
    // use-categories; originality: mean 1-5 rubric rating.
    minimumRelevantIdeas: 4,
    minimumCategoryDiversity: 2,
    minimumOriginality: 2.5,
  },
  [TASK.DUAL_TASK]: {
    maximumAbsoluteCountError: 0,
    maximumAbsoluteUpdateError: 0,
    // Both costs are normalised 0-1 (see dualTaskReferenceCosts()).
    // maximumDualTaskCost: attention-error rate may rise by at most a quarter of
    // the target count relative to the matched Task 3 single-task reference.
    // maximumSwitchCost: 1.0 means the post-switch rule was never applied; with
    // three post-switch updates one missed update is 1/3, so 0.34 admits at most
    // a single missed post-switch update.
    maximumDualTaskCost: 0.25,
    maximumSwitchCost: 0.34,
  },
  [TASK.ANOMALY]: { maximumAbsoluteCountError: 0, requireExactTypeSet: true },
  [TASK.VISUAL_COMPARISON]: {
    requireRenderedMismatchOnset: true,
    minimumPostOnsetLatencyMs: 0,
    maximumReactionTimeMs: null,
  },
  [TASK.CLOSURE]: {
    requireCorrectTarget: true,
    // revealFraction runs 0 at revealStartSeconds to 1 at fullyVisibleSeconds,
    // and responses only become possible at 0.10. Crediting Flexibility of
    // Closure requires recognising the target while it is still embedded in
    // dense noise, so the midpoint of the reveal schedule is the candidate
    // boundary: at 0.50 the noise overlay is still ~54% opaque and blur is at
    // half maximum. Above it the target is largely visible and only Speed of
    // Closure is evidenced.
    flexibilityMaximumRevealFraction: 0.5,
  },
  [TASK.SPEECH_NOISE]: {
    // Both main_idea and key_detail are selected from a fixed option list, so
    // both are scored by exact comparison against the answer key — no free
    // text, no rubric, no length thresholds.
    requireMainIdea: true,
    calibratedSnrRequiredForAbilityPass: true,
  },
  [TASK.WRITTEN]: {
    summaryMinimumWords: 35,
    summaryMaximumWords: 50,
    requireMainIdea: true,
    // Rubric dimensions are rated 1-5; 3 is "adequate". main_idea is excluded
    // because it is already scored objectively against the answer key, and
    // double-gating it would let one wrong MCQ fail the same construct twice.
    minimumRubricScores: {
      clarity: 3,
      coherence: 3,
      completeness: 3,
      information_ordering: 3,
    },
  },
};

export const CANDIDATE_PILOT_PROFILE = deepFreeze({
  protocolProfile: {
    contract_version: 'mindspeller_protocol_profile_v1',
    profile_id: 'mindspeller_optimized_task_battery',
    profile_version: '2.0.0-candidate.1',
    validation_status: 'pilot',
    components: {
      stimuli: {
        id: 'mindspeller_parallel_forms_en',
        version: '2.0.0-candidate.1',
        validation_status: 'candidate',
      },
      audio: {
        // 1.1.0: speech_in_noise switched from live browser synthesis to a
        // premixed, SNR-calibrated asset (id kept for continuity — target_tones
        // and spoken_stimuli are still browser-generated).
        id: 'mindspeller_browser_generated_audio',
        version: '1.1.0-candidate.1',
        validation_status: 'candidate',
      },
      rubrics: {
        // 1.1.0: the three free-text rubrics are now scored by the backend
        // model grader rather than awaiting human review, so their ids and
        // modes name the model rubric they are actually graded against.
        id: 'mindspeller_candidate_rubrics',
        version: '1.1.0-candidate.1',
        validation_status: 'candidate',
      },
      thresholds: {
        // 1.1.0: candidate cut-offs supplied for the previously-null closure,
        // dual-task, ideation, paraphrase and written-synthesis thresholds so
        // those abilities can resolve instead of returning pending_review.
        // Every added value is a documented candidate default, not a
        // normative cut-off — see validation_status below, which is what
        // scoringConfiguration and the backend actually gate interpretation on.
        id: 'mindspeller_candidate_thresholds',
        version: '1.1.0-candidate.1',
        validation_status: 'candidate',
      },
    },
    task_durations_seconds: Object.fromEntries(
      Object.entries(taskTimings).map(([taskId, timing]) => [taskId, timing.durationSeconds]),
    ),
  },
  language: 'en',
  runner: {
    countdownSeconds: 5,
    responseExclusionMs: 2000,
  },
  recordingContract: {
    requiredChannels: ['Fp1', 'Fp2', 'O1', 'O2'],
    rollingWindowSeconds: 2,
    overlapFraction: 0.5,
    minimumContiguousCleanSeconds: 20,
  },
  taskTimings,
  presentation,
  audioProfiles,
  rubrics,
  thresholds,
});

// Switching this binding to a separately versioned validated profile is the
// only activation change required outside that future profile's own module.
export const ACTIVE_BATTERY_PROFILE = CANDIDATE_PILOT_PROFILE;
export const PROTOCOL_PROFILE_METADATA = ACTIVE_BATTERY_PROFILE.protocolProfile;
export const PROTOCOL_PROFILE_REF = deepFreeze({
  contract_version: PROTOCOL_PROFILE_METADATA.contract_version,
  profile_id: PROTOCOL_PROFILE_METADATA.profile_id,
  profile_version: PROTOCOL_PROFILE_METADATA.profile_version,
  validation_status: PROTOCOL_PROFILE_METADATA.validation_status,
});

export const protocolProfileRefForTask = (taskId, profile = ACTIVE_BATTERY_PROFILE) => {
  const timing = taskTimingFor(taskId, profile);
  return deepFreeze({
    contract_version: profile.protocolProfile.contract_version,
    profile_id: profile.protocolProfile.profile_id,
    profile_version: profile.protocolProfile.profile_version,
    validation_status: profile.protocolProfile.validation_status,
    component_versions: Object.fromEntries(
      Object.entries(profile.protocolProfile.components).map(([name, component]) => [name, component.version]),
    ),
    task_id: taskId,
    duration_seconds: timing.durationSeconds,
  });
};

const requireTaskConfig = (collection, taskId, label) => {
  const configured = collection?.[taskId];
  if (!configured) throw new Error(`No ${label} configured for ${taskId}`);
  return configured;
};

export const taskTimingFor = (taskId, profile = ACTIVE_BATTERY_PROFILE) => (
  requireTaskConfig(profile.taskTimings, taskId, 'task timing')
);

export const taskPresentationFor = (taskId, profile = ACTIVE_BATTERY_PROFILE) => (
  requireTaskConfig(profile.presentation, taskId, 'presentation profile')
);

export const scoringRubricFor = (taskId, profile = ACTIVE_BATTERY_PROFILE) => (
  requireTaskConfig(profile.rubrics, taskId, 'scoring rubric')
);

export const scoringThresholdsFor = (taskId, profile = ACTIVE_BATTERY_PROFILE) => (
  requireTaskConfig(profile.thresholds, taskId, 'scoring thresholds')
);

export const audioProfileForTask = (taskId, profile = ACTIVE_BATTERY_PROFILE) => {
  if (taskId === TASK.AUDITORY_COUNT || taskId === TASK.DUAL_TASK) return profile.audioProfiles.target_tones;
  if (taskId === TASK.SPEECH_NOISE) return profile.audioProfiles.speech_in_noise;
  return profile.audioProfiles.spoken_stimuli;
};

export const runnerProtocolFor = (profile = ACTIVE_BATTERY_PROFILE) => ({
  ...profile.runner,
  recordingContract: profile.recordingContract,
});

export const profileComponentRefs = (profile = ACTIVE_BATTERY_PROFILE) => (
  Object.fromEntries(Object.entries(profile.protocolProfile.components).map(([name, component]) => [
    name,
    { id: component.id, version: component.version, validation_status: component.validation_status },
  ]))
);
