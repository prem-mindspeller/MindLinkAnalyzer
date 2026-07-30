import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ACTIVE_BATTERY_PROFILE,
  ACTIVE_STIMULUS_PACK,
  BATTERY_VERSION,
  EYES_OPEN_BASELINE_CHECKPOINT,
  FORM_REGISTRY_FOR_TESTS,
  PROTOCOL_PROFILE_METADATA,
  SESSION_SEQUENCES,
  TASK_DEFINITIONS,
  TASK_IDS,
  audioProfileForTask,
  closureRevealState,
  pacedPassageChunk,
  resolveSessionDepth,
  scoringRubricFor,
  scoringThresholdsFor,
  taskFormForSession,
  taskDefinitionForProfile,
  taskIdsForSession,
  taskIntroduction,
  taskPresentationFor,
  taskTimingFor,
  visualComparisonFrame,
  visualRouteState,
} from './optimizedBatteryConfig.mjs';

const makeStorage = (entries = {}) => ({ getItem: (key) => entries[key] ?? null });

test('battery exposes twelve unique canonical tasks numbered 1 through 12', () => {
  const definitions = Object.entries(TASK_DEFINITIONS);
  assert.equal(BATTERY_VERSION, 'task_battery_optimization_2.0.0-candidate.1');
  assert.equal(definitions.length, 12);
  assert.deepEqual(definitions.map(([, task]) => task.number).sort((a, b) => a - b), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  assert.equal(new Set(definitions.map(([id]) => id)).size, 12);
});

test('every canonical task resolves all runner configs (no missing-profile crash)', () => {
  // A missing presentation/timing/audio/rubric/threshold entry throws at task
  // mount and white-screens the renderer. Regression guard: divergent_ideation
  // had no presentation profile and crashed OptimizedBatteryTask on open.
  for (const taskId of Object.values(TASK_IDS)) {
    assert.doesNotThrow(() => taskPresentationFor(taskId), `presentation: ${taskId}`);
    assert.doesNotThrow(() => taskTimingFor(taskId), `timing: ${taskId}`);
    assert.doesNotThrow(() => audioProfileForTask(taskId), `audio: ${taskId}`);
    assert.doesNotThrow(() => scoringThresholdsFor(taskId), `thresholds: ${taskId}`);
    assert.doesNotThrow(() => scoringRubricFor(taskId), `rubric: ${taskId}`);
  }
});

test('all recording blocks and declared analysis phases respect protocol timing', () => {
  const expectedDurations = [90, 90, 120, 90, 90, 120, 120, 90, 60, 75, 120, 180];
  assert.deepEqual(
    Object.values(TASK_DEFINITIONS)
      .sort((left, right) => left.number - right.number)
      .map((definition) => definition.duration),
    expectedDurations,
  );
  for (const definition of Object.values(TASK_DEFINITIONS)) {
    assert.ok(definition.duration >= 60 && definition.duration <= 180, definition.name);
    assert.equal(definition.phases[0].start, 0, definition.name);
    assert.equal(definition.phases.at(-1).end, definition.duration, definition.name);
    for (const taskPhase of definition.phases) {
      assert.ok(taskPhase.duration >= 20, `${definition.name}: ${taskPhase.id}`);
    }
  }
});

test('sessions follow the optimized cumulative sequence and EO checkpoint', () => {
  assert.deepEqual(SESSION_SEQUENCES.session_1, [
    TASK_IDS.AUDITORY_COUNT,
    TASK_IDS.WORKING_MEMORY,
    TASK_IDS.NUMERICAL,
    TASK_IDS.SEMANTIC,
  ]);
  assert.deepEqual(SESSION_SEQUENCES.session_2, [
    ...SESSION_SEQUENCES.session_1,
    TASK_IDS.IDEATION,
    TASK_IDS.DUAL_TASK,
    EYES_OPEN_BASELINE_CHECKPOINT,
    TASK_IDS.VISUAL_COMPARISON,
    TASK_IDS.VISUOSPATIAL,
    TASK_IDS.ANOMALY,
  ]);
  assert.deepEqual(SESSION_SEQUENCES.session_3, [
    ...SESSION_SEQUENCES.session_1,
    TASK_IDS.IDEATION,
    TASK_IDS.DUAL_TASK,
    TASK_IDS.SPEECH_NOISE,
    EYES_OPEN_BASELINE_CHECKPOINT,
    TASK_IDS.VISUAL_COMPARISON,
    TASK_IDS.VISUOSPATIAL,
    TASK_IDS.ANOMALY,
    TASK_IDS.CLOSURE,
    TASK_IDS.WRITTEN,
  ]);
  assert.equal(taskIdsForSession('session_3').length, 12);
});

test('booking flags resolve to the intended session depth', () => {
  assert.equal(resolveSessionDepth(makeStorage()), 'session_1');
  assert.equal(resolveSessionDepth(makeStorage({ hasAdvancedBooking: 'true' })), 'session_2');
  assert.equal(resolveSessionDepth(makeStorage({ hasAdvancedBooking: 'true', hasSessionThree: 'true' })), 'session_3');
});

test('every task has three distinct versioned forms and repeats rotate forms', () => {
  for (const taskId of Object.keys(TASK_DEFINITIONS)) {
    const forms = FORM_REGISTRY_FOR_TESTS[taskId];
    assert.equal(forms.length, 3, taskId);
    assert.equal(new Set(forms.map((form) => form.id)).size, 3, taskId);
  }

  for (const taskId of SESSION_SEQUENCES.session_1) {
    assert.notEqual(taskFormForSession(taskId, 'session_1').id, taskFormForSession(taskId, 'session_2').id, taskId);
    assert.notEqual(taskFormForSession(taskId, 'session_2').id, taskFormForSession(taskId, 'session_3').id, taskId);
  }
  for (const taskId of [TASK_IDS.IDEATION, TASK_IDS.DUAL_TASK, TASK_IDS.VISUAL_COMPARISON, TASK_IDS.VISUOSPATIAL, TASK_IDS.ANOMALY]) {
    assert.equal(taskFormForSession(taskId, 'session_2').id, FORM_REGISTRY_FOR_TESTS[taskId][0].id, taskId);
    assert.equal(taskFormForSession(taskId, 'session_3').id, FORM_REGISTRY_FOR_TESTS[taskId][1].id, taskId);
  }
  for (const taskId of [TASK_IDS.SPEECH_NOISE, TASK_IDS.CLOSURE, TASK_IDS.WRITTEN]) {
    assert.equal(taskFormForSession(taskId, 'session_3').id, FORM_REGISTRY_FOR_TESTS[taskId][0].id, taskId);
  }
});

test('derived answer keys and paced stimuli are internally consistent', () => {
  for (const depth of ['session_1', 'session_2', 'session_3']) {
    const numerical = taskFormForSession(TASK_IDS.NUMERICAL, depth);
    assert.ok(Number.isFinite(numerical.answer));

    const memory = taskFormForSession(TASK_IDS.WORKING_MEMORY, depth);
    assert.equal(memory.answer.length, memory.initial.length);

    const auditory = taskFormForSession(TASK_IDS.AUDITORY_COUNT, depth);
    assert.equal(auditory.toneEvents.filter((event) => event.target).length, auditory.targetCount);
    assert.ok(auditory.toneEvents.at(-1).at <= TASK_DEFINITIONS[TASK_IDS.AUDITORY_COUNT].duration);

    const route = taskFormForSession(TASK_IDS.VISUOSPATIAL, depth);
    assert.deepEqual(visualRouteState(route, Number.POSITIVE_INFINITY), route.answer);

    const written = taskFormForSession(TASK_IDS.WRITTEN, depth);
    assert.ok(written.passage.trim().split(/\s+/).length >= 150);
    assert.ok(pacedPassageChunk(written, 0).length > 0);
    assert.ok(pacedPassageChunk(written, 119).length > 0);
  }
});

test('numerical stimulus scheduling preserves a final three-second quiet interval', () => {
  const duration = TASK_DEFINITIONS[TASK_IDS.NUMERICAL].duration;
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.NUMERICAL]) {
    assert.ok(form.spokenEvents.at(-1).at <= duration - 3, form.id);
  }
});

test('declared load boundaries coincide with the first higher-load stimulus', () => {
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.NUMERICAL]) {
    assert.equal(form.operations[6].at, TASK_DEFINITIONS[TASK_IDS.NUMERICAL].phases[1].start);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.WORKING_MEMORY]) {
    assert.equal(form.commands[2].at, TASK_DEFINITIONS[TASK_IDS.WORKING_MEMORY].phases[1].start);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUOSPATIAL]) {
    assert.equal(form.moves[4].at, TASK_DEFINITIONS[TASK_IDS.VISUOSPATIAL].phases[1].start);
  }
});

test('pre-recording instructions do not leak Task-2 encoding and fully state Task-7 rules', () => {
  for (const taskId of Object.keys(TASK_DEFINITIONS)) {
    assert.ok(taskIntroduction(taskId, FORM_REGISTRY_FOR_TESTS[taskId][0]).length >= 4, taskId);
  }

  const memory = FORM_REGISTRY_FOR_TESTS[TASK_IDS.WORKING_MEMORY][0];
  const memoryIntro = taskIntroduction(TASK_IDS.WORKING_MEMORY, memory).join(' ');
  assert.equal(memoryIntro.includes(memory.initial.join(' – ')), false);

  const dual = FORM_REGISTRY_FOR_TESTS[TASK_IDS.DUAL_TASK][0];
  const dualIntro = taskIntroduction(TASK_IDS.DUAL_TASK, dual).join(' ');
  assert.match(dualIntro, new RegExp(String(Math.abs(dual.beforeDelta))));
  assert.match(dualIntro, new RegExp(String(Math.abs(dual.afterDelta))));
  assert.deepEqual(
    dual.spokenEvents.filter((event) => event.at === 0).map((event) => event.text),
    [`Start with ${dual.startValue}.`],
  );
  const switchAt = TASK_DEFINITIONS[TASK_IDS.DUAL_TASK].phases[1].start;
  assert.deepEqual(
    dual.spokenEvents.filter((event) => event.at === switchAt).map((event) => event.text),
    ['Switch.'],
  );
});

test('every visuospatial turn changes position and orientation without leaving the grid', () => {
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUOSPATIAL]) {
    let previous = { ...form.start };
    for (const move of form.moves) {
      const current = visualRouteState(form, move.at);
      assert.notDeepEqual([current.x, current.y], [previous.x, previous.y], `${form.id} at ${move.at}s position`);
      assert.notEqual(current.orientation, previous.orientation, `${form.id} at ${move.at}s orientation`);
      assert.ok(current.x >= 0 && current.x <= 4 && current.y >= 0 && current.y <= 4, `${form.id} at ${move.at}s bounds`);
      previous = current;
    }
  }
});

test('dual-task forms keep canonical ids and Task-3-comparable tone streams', () => {
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.DUAL_TASK]) {
    assert.match(form.id, /^dual_[abc]$/);
    assert.ok(form.toneEvents.length >= 65 && form.toneEvents.length <= 75, form.id);
    assert.equal(form.toneEvents.filter((event) => event.target).length, form.targetCount, form.id);
  }
});

test('rapid visual comparison continuously updates synchronized code pairs', () => {
  const duration = TASK_DEFINITIONS[TASK_IDS.VISUAL_COMPARISON].duration;
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUAL_COMPARISON]) {
    assert.ok(form.mismatchOnset >= 20 && form.mismatchOnset <= 30, form.id);
    assert.ok(form.frames.length >= duration / form.updateIntervalSeconds, form.id);
    assert.ok(new Set(form.frames).size > 30, form.id);

    const early = visualComparisonFrame(form, form.mismatchOnset - 1);
    const later = visualComparisonFrame(form, form.mismatchOnset + 1);
    assert.notEqual(early.base, later.base, form.id);
    assert.equal(early.base.length, early.changed.length, form.id);
    assert.equal(
      [...later.base].filter((character, index) => character !== later.changed[index]).length,
      1,
      form.id,
    );
  }
});

test('closure visibility is derived from the same reveal schedule used by the form', () => {
  const form = FORM_REGISTRY_FOR_TESTS[TASK_IDS.CLOSURE][0];
  const before = closureRevealState(form, form.revealSchedule.revealStartSeconds - 1);
  const halfway = closureRevealState(form, (
    form.revealSchedule.revealStartSeconds + form.revealSchedule.fullyVisibleSeconds
  ) / 2);
  const complete = closureRevealState(form, form.revealSchedule.fullyVisibleSeconds);

  assert.equal(before.revealFraction, 0);
  assert.equal(before.responseEnabled, false);
  assert.equal(halfway.revealFraction, 0.5);
  assert.equal(complete.revealFraction, 1);
  assert.equal(complete.blurPx, 0);
  assert.equal(complete.noiseOpacity, form.revealSchedule.minimumNoiseOpacity);
});

test('active protocol is explicitly pilot/candidate and carries versioned component contracts', () => {
  assert.equal(PROTOCOL_PROFILE_METADATA.contract_version, 'mindspeller_protocol_profile_v1');
  assert.equal(PROTOCOL_PROFILE_METADATA.validation_status, 'pilot');
  assert.deepEqual(Object.keys(PROTOCOL_PROFILE_METADATA.components), [
    'stimuli', 'audio', 'rubrics', 'thresholds',
  ]);
  for (const component of Object.values(PROTOCOL_PROFILE_METADATA.components)) {
    assert.equal(component.validation_status, 'candidate');
    assert.ok(component.id);
    assert.ok(component.version);
  }
  assert.equal(ACTIVE_STIMULUS_PACK.validation_status, 'candidate');
});

test('stimulus schedules cover the corrected continuous windows', () => {
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.NUMERICAL]) {
    assert.ok(form.spokenEvents.at(-1).at >= 85);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.WORKING_MEMORY]) {
    assert.ok(form.spokenEvents.at(-1).at >= 85);
  }
  for (const taskId of [TASK_IDS.AUDITORY_COUNT, TASK_IDS.DUAL_TASK]) {
    const duration = TASK_DEFINITIONS[taskId].duration;
    for (const form of FORM_REGISTRY_FOR_TESTS[taskId]) {
      assert.ok(form.toneEvents.at(-1).at >= duration - 2, form.id);
      assert.ok(form.toneEvents.at(-1).at < duration, form.id);
    }
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.SEMANTIC]) {
    assert.ok(form.spokenEvents.at(-1).at >= 85, form.id);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUOSPATIAL]) {
    assert.ok(form.moves.at(-1).at >= 85, form.id);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.ANOMALY]) {
    assert.equal(form.entries.length * form.entryIntervalSeconds, 90, form.id);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.SPEECH_NOISE]) {
    const wordCount = form.passage.trim().split(/\s+/).length;
    assert.ok(wordCount >= 240 && wordCount <= 310, `${form.id}: ${wordCount} words`);
    // 103 = the shortest of the three calibrated Piper narrations
    // (tools/build_speech_in_noise_assets.py), kept conservative rather than
    // overstated.
    assert.equal(form.audioProfile.expectedDeliverySeconds, 103);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.WRITTEN]) {
    assert.equal(form.readingDurationSeconds, 120);
    assert.equal(form.synthesisDurationSeconds, 60);
    assert.notEqual(pacedPassageChunk(form, 95), pacedPassageChunk(form, 119));
  }
});

test('profile and stimulus-pack overrides are consumed without task-engine branches', () => {
  const profile = JSON.parse(JSON.stringify(ACTIVE_BATTERY_PROFILE));
  profile.taskTimings[TASK_IDS.NUMERICAL].durationSeconds = 123;
  profile.taskTimings[TASK_IDS.NUMERICAL].phases[1].endSeconds = 123;
  const definition = taskDefinitionForProfile(TASK_IDS.NUMERICAL, profile);
  assert.equal(definition.duration, 123);
  assert.equal(definition.phases.at(-1).end, 123);

  const replacement = { ...FORM_REGISTRY_FOR_TESTS[TASK_IDS.NUMERICAL][0], id: 'normalized_num_a' };
  const stimulusPack = {
    ...ACTIVE_STIMULUS_PACK,
    version: 'validated_test_pack',
    formsByTask: {
      ...ACTIVE_STIMULUS_PACK.formsByTask,
      [TASK_IDS.NUMERICAL]: [replacement],
    },
  };
  assert.equal(taskFormForSession(TASK_IDS.NUMERICAL, 'session_1', stimulusPack).id, 'normalized_num_a');
});

// Page 47 durations, the eyes-open/closed slide, and each task's
// "can provide evidence for" / "does not support direct claims regarding" lists.
// The backend repeats this table in neuroprofile_traceability.py, so drift here
// silently desynchronizes acquisition from ability gating.
const PDF_TASK_CONTRACT = [
  [1, TASK_IDS.NUMERICAL, 90, 'closed', 'eyes_closed',
    ['Mathematical Reasoning', 'Number Facility', 'Information Ordering', 'Deductive Reasoning'],
    ['Inductive Reasoning', 'Memorization', 'Reaction Time', 'Oral Comprehension', 'Oral Expression']],
  [2, TASK_IDS.WORKING_MEMORY, 90, 'closed', 'eyes_closed',
    ['Memorization', 'Information Ordering', 'Deductive Reasoning'],
    ['Inductive Reasoning', 'Category Flexibility', 'Time Sharing', 'Number Facility', 'Mathematical Reasoning', 'Oral Comprehension']],
  [3, TASK_IDS.AUDITORY_COUNT, 120, 'closed', 'eyes_closed',
    ['Selective Attention', 'Auditory Attention'],
    ['Reaction Time', 'Speech Recognition', 'Oral Comprehension', 'Time Sharing', 'Problem Sensitivity']],
  [4, TASK_IDS.SEMANTIC, 90, 'closed', 'eyes_closed',
    ['Inductive Reasoning', 'Category Flexibility'],
    ['Deductive Reasoning', 'Memorization', 'Fluency of Ideas', 'Originality', 'Oral Comprehension']],
  [5, TASK_IDS.VISUOSPATIAL, 90, 'open', 'eyes_open',
    ['Visualization', 'Spatial Orientation'],
    ['Perceptual Speed', 'Speed of Closure', 'Flexibility of Closure', 'Reaction Time', 'Visual sensory abilities']],
  [6, TASK_IDS.IDEATION, 120, 'closed', 'eyes_closed',
    ['Category Flexibility', 'Fluency of Ideas', 'Originality'],
    ['Written Expression', 'Oral Expression', 'Inductive Reasoning', 'Deductive Reasoning', 'Visualization']],
  [7, TASK_IDS.DUAL_TASK, 120, 'closed', 'eyes_closed',
    ['Time Sharing', 'Category Flexibility', 'Deductive Reasoning', 'Selective Attention', 'Information Ordering'],
    ['Mathematical Reasoning', 'Number Facility', 'Memorization', 'Reaction Time', 'Auditory Attention']],
  [8, TASK_IDS.ANOMALY, 90, 'open', 'eyes_open',
    ['Problem Sensitivity', 'Deductive Reasoning', 'Selective Attention', 'Information Ordering'],
    ['Inductive Reasoning', 'Perceptual Speed', 'Reaction Time', 'Speed of Closure', 'Flexibility of Closure']],
  [9, TASK_IDS.VISUAL_COMPARISON, 60, 'open', 'eyes_open',
    ['Perceptual Speed', 'Reaction Time'],
    ['Speed of Closure', 'Flexibility of Closure', 'Visualization', 'Spatial Orientation', 'Problem Sensitivity']],
  [10, TASK_IDS.CLOSURE, 75, 'open', 'eyes_open',
    ['Speed of Closure', 'Flexibility of Closure'],
    ['Perceptual Speed', 'Spatial Orientation', 'Problem Sensitivity', 'Reaction Time', 'Selective Attention']],
  [11, TASK_IDS.SPEECH_NOISE, 120, 'closed', 'eyes_closed',
    ['Oral Comprehension', 'Speech Recognition', 'Auditory Attention'],
    ['Oral Expression', 'Speech Clarity', 'Reaction Time', 'Written Comprehension', 'Written Expression']],
  [12, TASK_IDS.WRITTEN, 180, 'open', 'eyes_open',
    ['Written Comprehension', 'Written Expression', 'Inductive Reasoning', 'Information Ordering'],
    ['Oral Comprehension', 'Oral Expression', 'Speech Recognition', 'Speech Clarity', 'Fluency of Ideas', 'Originality']],
];

test('task eye states, matched baselines and ability claims match the optimization document', () => {
  assert.equal(PDF_TASK_CONTRACT.length, 12);
  for (const [number, taskId, duration, eyeState, baseline, abilities, blocked] of PDF_TASK_CONTRACT) {
    const definition = TASK_DEFINITIONS[taskId];
    assert.ok(definition, taskId);
    assert.equal(definition.number, number, taskId);
    assert.equal(definition.duration, duration, taskId);
    assert.equal(definition.eyeState, eyeState, taskId);
    assert.equal(definition.baseline, baseline, taskId);
    assert.deepEqual(definition.abilities, abilities, taskId);
    assert.deepEqual(definition.blocked, blocked, taskId);
    // "Never compare an eyes-open task only with an eyes-closed baseline."
    assert.equal(definition.baseline, `eyes_${eyeState}`, taskId);
    // No task may claim an ability it explicitly cannot support.
    for (const ability of abilities) {
      assert.ok(!blocked.includes(ability), `${taskId}: ${ability}`);
    }
  }
});

test('every eyes-open task is reached only after the eyes-open baseline checkpoint', () => {
  for (const [depth, sequence] of Object.entries(SESSION_SEQUENCES)) {
    const checkpointIndex = sequence.indexOf(EYES_OPEN_BASELINE_CHECKPOINT);
    sequence.forEach((entry, index) => {
      if (entry === EYES_OPEN_BASELINE_CHECKPOINT) return;
      if (TASK_DEFINITIONS[entry].eyeState !== 'open') return;
      assert.ok(checkpointIndex >= 0, `${depth} runs an eyes-open task without the checkpoint`);
      assert.ok(index > checkpointIndex, `${depth}: ${entry} precedes the eyes-open baseline`);
    });
  }
});

test('acoustic calibration can only be claimed for a real premixed asset', () => {
  // `acousticallyCalibrated: true` unlocks Speech Recognition and Oral
  // Comprehension, so it must never be assertable while audio is still being
  // synthesised by the browser at an unmeasured SNR. Calibration is a property
  // of a measured audio file, not a flag.
  const profiles = ACTIVE_BATTERY_PROFILE.audioProfiles;
  for (const [name, profile] of Object.entries(profiles)) {
    if (!profile || typeof profile !== 'object' || Array.isArray(profile)) continue;
    if (profile.acousticallyCalibrated !== true) continue;
    assert.equal(
      profile.mode, 'premixed_audio_asset',
      `audio profile "${name}" claims calibration but is delivered by ${profile.mode}`,
    );
    const hasAsset = Boolean(
      profile.assetUri
      || Object.keys(profile.assetsByForm || {}).length
      || Object.keys(profile.assetsByStimulusKey || {}).length,
    );
    assert.ok(hasAsset, `audio profile "${name}" claims calibration without supplying an asset`);
  }
});

test('the bundled speech-in-noise audio is a calibrated premixed asset with a matching form for each parallel form', () => {
  const speech = audioProfileForTask(TASK_IDS.SPEECH_NOISE);
  assert.equal(speech.acousticallyCalibrated, true);
  assert.equal(speech.mode, 'premixed_audio_asset');
  assert.ok(speech.nominalSnrDb, 'the calibrated SNR is recorded for audit');
  for (const formId of ['speech_a', 'speech_b', 'speech_c']) {
    const asset = speech.assetsByForm[formId];
    assert.ok(asset?.uri, `${formId} must have an asset uri`);
    assert.match(asset.sha256, /^[0-9a-f]{64}$/, `${formId} must record a sha256`);
  }
});
