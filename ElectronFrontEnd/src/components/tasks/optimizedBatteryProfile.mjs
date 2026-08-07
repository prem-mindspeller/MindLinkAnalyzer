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
    durationSeconds: 90,
    phases: [
      phase('lower_load', 'Slower single operations', 0, 45),
      phase('higher_load', 'Faster mixed operations', 45, 90),
    ],
  },
  [TASK.WORKING_MEMORY]: {
    durationSeconds: 90,
    phases: [
      phase('maintenance', 'Maintenance-dominant', 0, 45),
      phase('manipulation', 'Manipulation-dominant', 45, 90),
    ],
  },
  [TASK.AUDITORY_COUNT]: {
    durationSeconds: 120,
    phases: [
      phase('early', 'Early monitoring', 0, 40),
      phase('middle', 'Middle monitoring', 40, 80),
      phase('late', 'Late monitoring', 80, 120),
    ],
  },
  [TASK.SEMANTIC]: {
    durationSeconds: 90,
    phases: [
      phase('rule_one', 'First organising principle', 0, 45),
      phase('rule_two', 'Second organising principle', 45, 90),
    ],
  },
  [TASK.VISUOSPATIAL]: {
    durationSeconds: 90,
    phases: [
      phase('lower_density', 'Lower transformation density', 0, 45),
      phase('higher_density', 'Higher transformation density', 45, 90),
    ],
  },
  [TASK.IDEATION]: {
    durationSeconds: 120,
    phases: [
      phase('early', 'Early ideation', 0, 40),
      phase('middle', 'Middle ideation', 40, 80),
      phase('late', 'Late ideation', 80, 120),
    ],
  },
  [TASK.DUAL_TASK]: {
    durationSeconds: 120,
    phases: [
      phase('before_switch', 'Before rule switch', 0, 60),
      phase('after_switch', 'After rule switch', 60, 120),
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
    mode: 'browser_speech_synthesis_with_generated_noise',
    // A validated profile switches mode to premixed_audio_asset and supplies
    // these two fields; the runner need only implement the generic source
    // descriptor, not a task-specific audio branch.
    assetUri: null,
    assetSha256: null,
    assetsByForm: {},
    assetsByStimulusKey: {},
    language: 'en-US',
    voiceId: null,
    rate: 0.88,
    pitch: 1,
    volume: 0.9,
    nominalSnrDb: 8,
    acousticallyCalibrated: false,
    expectedDeliverySeconds: 115,
    settlingSeconds: 5,
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
  [TASK.SEMANTIC]: { itemsPerPhase: 15 },
  [TASK.VISUOSPATIAL]: { finalQuietSeconds: 3 },
  // Divergent ideation is a silent generation block with no scheduled audio or
  // visual stimuli, so it carries no presentation timing parameters. The entry
  // must still exist: taskPresentationFor() throws for any unconfigured task.
  [TASK.IDEATION]: {},
  [TASK.DUAL_TASK]: { finalQuietSeconds: 3 },
  [TASK.ANOMALY]: { entryIntervalSeconds: 2 },
  [TASK.VISUAL_COMPARISON]: { updateIntervalSeconds: 1, mismatchRevealSeconds: 2 },
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
  [TASK.IDEATION]: {
    id: 'ideation_human_review_candidate',
    mode: 'pending_validated_review',
    dimensions: ['relevance', 'fluency', 'category_diversity', 'originality'],
  },
  [TASK.DUAL_TASK]: { id: 'exact_outputs_with_reference_costs', mode: 'objective_plus_thresholds' },
  [TASK.ANOMALY]: { id: 'count_and_anomaly_type_key', mode: 'objective_key' },
  [TASK.VISUAL_COMPARISON]: { id: 'single_rendered_onset_latency', mode: 'objective_key_and_latency' },
  [TASK.CLOSURE]: { id: 'recognition_and_visibility_schedule', mode: 'objective_plus_thresholds' },
  [TASK.SPEECH_NOISE]: {
    id: 'speech_comprehension_candidate_review',
    mode: 'objective_plus_pending_validated_review',
    dimensions: ['main_idea', 'key_detail', 'paraphrase_accuracy', 'paraphrase_completeness'],
  },
  [TASK.WRITTEN]: {
    id: 'written_synthesis_candidate_review',
    mode: 'objective_plus_pending_validated_review',
    dimensions: ['main_idea', 'clarity', 'coherence', 'completeness', 'information_ordering'],
  },
};

const thresholds = {
  [TASK.NUMERICAL]: { maximumAbsoluteFinalError: 0 },
  [TASK.WORKING_MEMORY]: { maximumItemErrors: 0 },
  [TASK.AUDITORY_COUNT]: { maximumAbsoluteCountError: 0, validated: false },
  [TASK.SEMANTIC]: { requireBothRules: true, requireSwitchDetection: true },
  [TASK.VISUOSPATIAL]: { maximumPositionError: 0, requireOrientationMatch: true },
  [TASK.IDEATION]: {
    minimumRelevantIdeas: null,
    minimumCategoryDiversity: null,
    minimumOriginality: null,
  },
  [TASK.DUAL_TASK]: {
    maximumAbsoluteCountError: 0,
    maximumAbsoluteUpdateError: 0,
    maximumDualTaskCost: null,
    maximumSwitchCost: null,
  },
  [TASK.ANOMALY]: { maximumAbsoluteCountError: 0, requireExactTypeSet: true },
  [TASK.VISUAL_COMPARISON]: {
    requireRenderedMismatchOnset: true,
    minimumPostOnsetLatencyMs: 0,
    maximumReactionTimeMs: null,
  },
  [TASK.CLOSURE]: {
    requireCorrectTarget: true,
    flexibilityMaximumRevealFraction: null,
  },
  [TASK.SPEECH_NOISE]: {
    keyDetailMinimumTokenLength: 3,
    keyDetailMinimumMatches: 2,
    keyDetailMinimumMatchRatio: 0.6,
    requireMainIdea: true,
    paraphraseMinimumWords: null,
    calibratedSnrRequiredForAbilityPass: true,
  },
  [TASK.WRITTEN]: {
    summaryMinimumWords: 35,
    summaryMaximumWords: 50,
    requireMainIdea: true,
    minimumRubricScores: null,
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
        id: 'mindspeller_browser_generated_audio',
        version: '1.0.0-candidate.1',
        validation_status: 'candidate',
      },
      rubrics: {
        id: 'mindspeller_candidate_rubrics',
        version: '1.0.0-candidate.1',
        validation_status: 'candidate',
      },
      thresholds: {
        id: 'mindspeller_candidate_thresholds',
        version: '1.0.0-candidate.1',
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
