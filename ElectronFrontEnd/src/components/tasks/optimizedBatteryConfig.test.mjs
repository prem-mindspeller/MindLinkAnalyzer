import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';

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
  countWords,
  maximumWordsFor,
  normalizeText,
  pacedPassageChunk,
  randomizeMultipleChoiceOrder,
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
  // Tasks 1, 2, 4, 5, 7, 8, 10 and 11 deliberately shortened from the page-47
  // example's 90s/120s to 60s; Tasks 3 and 6 (both 3-equal-phase tasks)
  // shortened to 75s rather than a flat 60s, for the same
  // 20s-phase-floor-margin reason. Task 12 shortened from 180s to 90s.
  const expectedDurations = [60, 60, 75, 60, 60, 75, 60, 60, 60, 60, 60, 90];
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
    assert.ok(written.passage.trim().split(/\s+/).length >= 80);
    assert.ok(pacedPassageChunk(written, 0).length > 0);
    assert.ok(pacedPassageChunk(written, 59).length > 0);
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
    // 4 lower-load operations (indices 0-3) precede the first higher-load one.
    assert.equal(form.operations[4].at, TASK_DEFINITIONS[TASK_IDS.NUMERICAL].phases[1].start);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.WORKING_MEMORY]) {
    assert.equal(form.commands[2].at, TASK_DEFINITIONS[TASK_IDS.WORKING_MEMORY].phases[1].start);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUOSPATIAL]) {
    // 3 lower-density moves (indices 0-2) precede the first higher-density one.
    assert.equal(form.moves[3].at, TASK_DEFINITIONS[TASK_IDS.VISUOSPATIAL].phases[1].start);
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
  // The switch cue marks the phase boundary, but nudgeAwayFromTones may shift
  // it by up to its search window to keep it from being spoken over a tone
  // (an unheard "Switch." is worse than a slightly offset one). Assert the
  // contract that actually holds -- exactly one switch cue, close to the
  // boundary -- rather than exact equality, which only held by luck of where
  // the tones happened to fall.
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.DUAL_TASK]) {
    const switchCues = form.spokenEvents.filter((event) => event.text === 'Switch.');
    assert.equal(switchCues.length, 1, `${form.id} switch cue count`);
    assert.ok(
      Math.abs(switchCues[0].at - switchAt) <= 1.2,
      `${form.id} switch cue at ${switchCues[0].at}s is too far from the ${switchAt}s boundary`,
    );
    // Every post-switch update must still fall after the boundary, or the
    // before/after classification the switch cost depends on would break.
    for (const at of form.updateTimes.filter((time) => time > switchAt)) {
      assert.ok(at > switchCues[0].at, `${form.id}: update at ${at}s must follow the switch cue`);
    }
  }
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
    // Trimmed from the 120s original's 65-75 tones to preserve pacing at 60s.
    assert.ok(form.toneEvents.length >= 30 && form.toneEvents.length <= 38, form.id);
    assert.equal(form.toneEvents.filter((event) => event.target).length, form.targetCount, form.id);
  }
});

test('dual-task spoken cues never play close enough to a tone to overlap it', () => {
  // The tone stream and the spoken update/switch cues are scheduled
  // independently, so nothing guarantees they land apart -- this is what
  // dualTaskForm's nudgeAwayFromTones step is responsible for.
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.DUAL_TASK]) {
    for (const spoken of form.spokenEvents) {
      const nearestGap = Math.min(...form.toneEvents.map((tone) => Math.abs(tone.at - spoken.at)));
      assert.ok(nearestGap >= 0.6, `${form.id} "${spoken.text}" at ${spoken.at}s is only ${nearestGap.toFixed(2)}s from a tone`);
    }
  }
});

test('rapid visual comparison continuously updates synchronized code pairs', () => {
  const duration = TASK_DEFINITIONS[TASK_IDS.VISUAL_COMPARISON].duration;
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUAL_COMPARISON]) {
    assert.ok(form.mismatchOnset >= 20 && form.mismatchOnset <= 30, form.id);
    assert.ok(form.frames.length >= duration / form.updateIntervalSeconds, form.id);
    assert.ok(new Set(form.frames).size > form.frames.length / 2, form.id);

    const early = visualComparisonFrame(form, form.mismatchOnset - 1);
    const later = visualComparisonFrame(form, form.mismatchOnset + 1);
    assert.notEqual(early.base, later.base, form.id);
    assert.equal(early.base.length, early.changed.length, form.id);
    assert.equal(early.mismatchIndices.length, 0, form.id);
    assert.equal(
      [...later.base].filter((character, index) => character !== later.changed[index]).length,
      1,
      form.id,
    );
  }
});

test('comparison mismatches grow from one difference to many well before the block ends', () => {
  const duration = TASK_DEFINITIONS[TASK_IDS.VISUAL_COMPARISON].duration;
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUAL_COMPARISON]) {
    const justAfterOnset = visualComparisonFrame(form, form.mismatchOnset + 1);
    assert.equal(justAfterOnset.mismatchIndices.length, 1, form.id);

    const nearEnd = visualComparisonFrame(form, duration - 2);
    assert.equal(nearEnd.mismatchIndices.length, form.mismatchIndices.length, form.id);
    assert.ok(nearEnd.mismatchIndices.length > 1, form.id);

    // The count never shrinks as time passes, and it never revisits a
    // position it has already revealed.
    let previousCount = 0;
    for (let elapsed = form.mismatchOnset; elapsed <= duration; elapsed += 1) {
      const frame = visualComparisonFrame(form, elapsed);
      assert.ok(frame.mismatchIndices.length >= previousCount, `${form.id} at ${elapsed}s`);
      assert.equal(new Set(frame.mismatchIndices).size, frame.mismatchIndices.length, `${form.id} at ${elapsed}s`);
      previousCount = frame.mismatchIndices.length;
    }
  }
});

test('every mismatch, including the first, only appears exactly when the code refreshes', () => {
  const duration = TASK_DEFINITIONS[TASK_IDS.VISUAL_COMPARISON].duration;
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUAL_COMPARISON]) {
    const interval = form.updateIntervalSeconds;
    // mismatchOnset is itself a multiple of updateIntervalSeconds, so even the
    // very first mismatch -- the instant reaction time is scored from -- lands
    // on a refresh instead of appearing mid-display on an already-shown pair.
    assert.equal(form.mismatchOnset % interval, 0, form.id);
    for (let frameStart = 0; frameStart + interval <= duration; frameStart += interval) {
      const atRefresh = visualComparisonFrame(form, frameStart).mismatchIndices.length;
      const justBeforeNextRefresh = visualComparisonFrame(
        form, frameStart + interval - 0.01,
      ).mismatchIndices.length;
      assert.equal(
        atRefresh, justBeforeNextRefresh,
        `${form.id} mismatch count changed mid-display within [${frameStart}, ${frameStart + interval})`,
      );
    }
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
    // Task 1 is 60s (shortened from 90s); the last operation lands at
    // duration - finalQuietSeconds = 57.
    assert.ok(form.spokenEvents.at(-1).at >= 55);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.WORKING_MEMORY]) {
    // Task 2 is 60s (shortened from 90s); the last command lands at
    // duration - finalQuietSeconds = 57.
    assert.ok(form.spokenEvents.at(-1).at >= 55);
  }
  for (const taskId of [TASK_IDS.AUDITORY_COUNT, TASK_IDS.DUAL_TASK]) {
    const duration = TASK_DEFINITIONS[taskId].duration;
    for (const form of FORM_REGISTRY_FOR_TESTS[taskId]) {
      assert.ok(form.toneEvents.at(-1).at >= duration - 2, form.id);
      assert.ok(form.toneEvents.at(-1).at < duration, form.id);
    }
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.SEMANTIC]) {
    // Task 4 is 60s (shortened from 90s); the last item lands at t=57.
    assert.ok(form.spokenEvents.at(-1).at >= 55, form.id);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.VISUOSPATIAL]) {
    // Task 5 is 60s (shortened from 90s); the last move lands at t=57.
    assert.ok(form.moves.at(-1).at >= 55, form.id);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.ANOMALY]) {
    // Task 8 is 60s (shortened from 90s); entryIntervalSeconds is unchanged.
    assert.equal(form.entries.length * form.entryIntervalSeconds, 60, form.id);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.SPEECH_NOISE]) {
    const wordCount = form.passage.trim().split(/\s+/).length;
    // Short simple narratives at ~101-110 words (see SPEECH_BASE_FORMS) so
    // the same playbackRate/SNR-safety budget fits inside the shortened 60s
    // block.
    assert.ok(wordCount >= 90 && wordCount <= 120, `${form.id}: ${wordCount} words`);
    // 47 = the shortest of the three calibrated narrations
    // (tools/build_speech_in_noise_assets.py) played at the profile's
    // playbackRate, kept conservative rather than overstated.
    assert.equal(form.audioProfile.expectedDeliverySeconds, 47);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.WRITTEN]) {
    assert.equal(form.readingDurationSeconds, 60);
    assert.equal(form.synthesisDurationSeconds, 30);
    assert.notEqual(pacedPassageChunk(form, 12), pacedPassageChunk(form, 48));
  }
});

test('word counts are correct for every script the app is localized in', () => {
  // The battery ships ten locales and participants may answer in any of them.
  // Splitting on whitespace counted a whole Japanese/Chinese/Thai response as
  // one word, which made Task 11's and Task 12's minimum-length gates
  // unreachable and blocked submission outright.
  assert.ok(countWords('沼地が波を遅くしました') > 1, 'Japanese must not count as one word');
  assert.ok(countWords('沼泽减缓了海浪的速度') > 1, 'Chinese must not count as one word');
  assert.ok(countWords('บึงชะลอคลื่น') > 1, 'Thai must not count as one word');

  // Space-delimited scripts must be unchanged: this replaced whitespace
  // splitting, and every shipped passage/threshold was calibrated against it.
  const whitespaceCount = (value) => String(value || '').trim().split(/\s+/).filter(Boolean).length;
  for (const taskId of [TASK_IDS.WRITTEN, TASK_IDS.SPEECH_NOISE]) {
    for (const form of FORM_REGISTRY_FOR_TESTS[taskId]) {
      assert.equal(countWords(form.passage), whitespaceCount(form.passage), form.id);
    }
  }
  for (const latin of [
    'well-made state-of-the-art products',
    "the shop's own job isn't easy",
    'le marais a ralenti la vague à café',
  ]) {
    assert.equal(countWords(latin), whitespaceCount(latin), latin);
  }

  assert.equal(countWords(''), 0);
  assert.equal(countWords('   '), 0);
  // Punctuation alone is not a word, so it cannot satisfy a minimum-word gate.
  assert.equal(countWords('!!! ???'), 0);
});

test('every multiple-choice answer is selectable and its option list has no duplicates', () => {
  for (const taskId of [TASK_IDS.SPEECH_NOISE, TASK_IDS.WRITTEN]) {
    for (const form of FORM_REGISTRY_FOR_TESTS[taskId]) {
      // The scorer compares the response to `mainIdea`/`keyDetail`, so an
      // answer missing from its own option list would be unreachable and the
      // task could never be passed.
      assert.ok(form.mainIdeaOptions.includes(form.mainIdea), `${form.id} main idea`);
      assert.equal(new Set(form.mainIdeaOptions).size, form.mainIdeaOptions.length, `${form.id} main idea duplicates`);

      if (!form.keyDetailOptions) continue;
      assert.ok(form.keyDetailOptions.includes(form.keyDetail), `${form.id} key detail`);
      assert.equal(new Set(form.keyDetailOptions).size, form.keyDetailOptions.length, `${form.id} key detail duplicates`);
      // Four options rather than three keep the blind-guess rate at 25% for the
      // one item that decides Speech Recognition.
      assert.equal(form.keyDetailOptions.length, 4, `${form.id} key detail option count`);
    }
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.SEMANTIC]) {
    assert.ok(form.ruleOptions.includes(form.ruleOne), `${form.id} rule one`);
    assert.equal(new Set(form.ruleOptions).size, form.ruleOptions.length, `${form.id} rule one duplicates`);
    assert.ok(form.secondRuleOptions.includes(form.ruleTwo), `${form.id} rule two`);
    assert.equal(new Set(form.secondRuleOptions).size, form.secondRuleOptions.length, `${form.id} rule two duplicates`);
  }
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.CLOSURE]) {
    assert.ok(form.options.includes(form.target), `${form.id} target`);
    assert.equal(new Set(form.options).size, form.options.length, `${form.id} option duplicates`);
  }
});

// Position-learnability is now guarded by actual per-attempt randomization
// (randomizeMultipleChoiceOrder, applied once per task attempt in
// OptimizedBatteryTask.jsx) rather than by hand-varying each form's authored
// order -- a static order, however varied, is still the same on every replay
// of a given form and was found clustering the correct answer at index 0 in
// every SEMANTIC and CLOSURE form.
test('multiple-choice randomization preserves content and actually varies position', () => {
  const cases = [
    [TASK_IDS.SEMANTIC, 'ruleOptions', 'ruleOne'],
    [TASK_IDS.SEMANTIC, 'secondRuleOptions', 'ruleTwo'],
    [TASK_IDS.CLOSURE, 'options', 'target'],
    [TASK_IDS.SPEECH_NOISE, 'mainIdeaOptions', 'mainIdea'],
    [TASK_IDS.SPEECH_NOISE, 'keyDetailOptions', 'keyDetail'],
    [TASK_IDS.WRITTEN, 'mainIdeaOptions', 'mainIdea'],
  ];
  for (const [taskId, optionsField, answerField] of cases) {
    const form = FORM_REGISTRY_FOR_TESTS[taskId][0];
    const originalOptions = [...form[optionsField]];
    const positionsSeen = new Set();
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const randomized = randomizeMultipleChoiceOrder(taskId, form);
      // Same items, just reordered -- content and correctness never change.
      assert.deepEqual([...randomized[optionsField]].sort(), [...originalOptions].sort(), `${taskId}/${optionsField} content`);
      assert.ok(randomized[optionsField].includes(form[answerField]), `${taskId}/${optionsField} still has the answer`);
      positionsSeen.add(randomized[optionsField].indexOf(form[answerField]));
    }
    // The original form object is never mutated by randomization.
    assert.deepEqual(form[optionsField], originalOptions, `${taskId}/${optionsField} source untouched`);
    // Over 100 attempts, an unbiased shuffle of >= 3 options should not land
    // the answer on the same index every single time (astronomically
    // unlikely by chance -- this is the actual regression guard for "always
    // first").
    assert.ok(positionsSeen.size > 1, `${taskId}/${optionsField} answer position never varied across 100 attempts`);
  }
  // A task with no configured multiple-choice fields is returned unchanged.
  const numerical = FORM_REGISTRY_FOR_TESTS[TASK_IDS.NUMERICAL][0];
  assert.equal(randomizeMultipleChoiceOrder(TASK_IDS.NUMERICAL, numerical), numerical);
});

test('the summary word ceiling widens only for scripts that segment more finely', () => {
  // Task 12's configured 20-30 word range (see thresholds[TASK.WRITTEN] in
  // optimizedBatteryProfile.mjs) is calibrated against English; 50 below is
  // just an arbitrary ceiling exercising the pure function. Japanese
  // expresses the same content in ~1.55x as many segmented words, so a fixed
  // English ceiling rejected an otherwise valid answer.
  assert.equal(maximumWordsFor('a plain english summary', 50), 50);
  assert.equal(maximumWordsFor('', 50), 50);
  assert.equal(maximumWordsFor('le marais a ralenti la vague', 50), 50);
  assert.ok(maximumWordsFor('沼地が波を遅くしました', 50) > 50);
  // A null/absent ceiling stays absent rather than becoming a number.
  assert.equal(maximumWordsFor('沼地が波を遅くしました', null), null);
});

test('text normalization preserves non-Latin answers instead of erasing them', () => {
  // An ASCII-only character class silently normalized every Arabic, Japanese
  // or Devanagari answer to an empty string, and stripped accents off Latin
  // ones, before any comparison could be made.
  for (const nonLatin of ['沼地', 'بركة', 'दलदल', 'บึง']) {
    assert.equal(normalizeText(nonLatin), nonLatin, nonLatin);
  }
  assert.equal(normalizeText('café'), 'café');
  // Punctuation and case are still normalized away.
  assert.equal(normalizeText('  The Marsh!  '), 'the marsh');
  // Selected answers are compared after normalization, so two distinct options
  // must never normalize to the same string — that would let a wrong choice
  // score as correct. Punctuation stripping makes this a real risk.
  for (const taskId of [TASK_IDS.WRITTEN, TASK_IDS.SPEECH_NOISE]) {
    for (const form of FORM_REGISTRY_FOR_TESTS[taskId]) {
      for (const options of [form.mainIdeaOptions, form.keyDetailOptions]) {
        if (!options) continue;
        const normalized = options.map(normalizeText);
        assert.equal(new Set(normalized).size, options.length, `${form.id} options collide once normalized`);
        assert.ok(normalized.every(Boolean), `${form.id} has an option that normalizes to nothing`);
      }
    }
  }
});

test('paced reading chunks never split a sentence and cover the whole passage', () => {
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.WRITTEN]) {
    const passageWordCount = form.passage.trim().split(/\s+/).filter(Boolean).length;
    let coveredWordCount = 0;
    for (let elapsed = 0; elapsed < form.readingDurationSeconds; elapsed += 12) {
      const chunk = pacedPassageChunk(form, elapsed);
      assert.ok(chunk.length > 0, `${form.id} at ${elapsed}s should not be empty`);
      // Every chunk must end at a sentence boundary, not mid-sentence.
      assert.match(chunk.trim(), /[.!?]”?$/, `${form.id} at ${elapsed}s: "${chunk}"`);
      coveredWordCount += chunk.trim().split(/\s+/).filter(Boolean).length;
    }
    // The chunks partition the passage: no words dropped or duplicated.
    assert.equal(coveredWordCount, passageWordCount, form.id);
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

// Page 47 durations (Tasks 1, 2, 4, 5, 7, 8, 10 and 11 deliberately shortened
// to 60s, Tasks 3 and 6 to 75s, Task 12 to 90s -- see
// optimizedBatteryProfile.mjs), the
// eyes-open/closed slide, and each task's "can provide evidence for" / "does
// not support direct claims regarding" lists. The backend repeats this table in
// neuroprofile_traceability.py, so drift here silently desynchronizes
// acquisition from ability gating.
const PDF_TASK_CONTRACT = [
  [1, TASK_IDS.NUMERICAL, 60, 'closed', 'eyes_closed',
    ['Mathematical Reasoning', 'Number Facility', 'Information Ordering', 'Deductive Reasoning'],
    ['Inductive Reasoning', 'Memorization', 'Reaction Time', 'Oral Comprehension', 'Oral Expression']],
  [2, TASK_IDS.WORKING_MEMORY, 60, 'closed', 'eyes_closed',
    ['Memorization', 'Information Ordering', 'Deductive Reasoning'],
    ['Inductive Reasoning', 'Category Flexibility', 'Time Sharing', 'Number Facility', 'Mathematical Reasoning', 'Oral Comprehension']],
  [3, TASK_IDS.AUDITORY_COUNT, 75, 'closed', 'eyes_closed',
    ['Selective Attention', 'Auditory Attention'],
    ['Reaction Time', 'Speech Recognition', 'Oral Comprehension', 'Time Sharing', 'Problem Sensitivity']],
  [4, TASK_IDS.SEMANTIC, 60, 'closed', 'eyes_closed',
    ['Inductive Reasoning', 'Category Flexibility'],
    ['Deductive Reasoning', 'Memorization', 'Fluency of Ideas', 'Originality', 'Oral Comprehension']],
  [5, TASK_IDS.VISUOSPATIAL, 60, 'open', 'eyes_open',
    ['Visualization', 'Spatial Orientation'],
    ['Perceptual Speed', 'Speed of Closure', 'Flexibility of Closure', 'Reaction Time', 'Visual sensory abilities']],
  [6, TASK_IDS.IDEATION, 75, 'closed', 'eyes_closed',
    ['Category Flexibility', 'Fluency of Ideas', 'Originality'],
    ['Written Expression', 'Oral Expression', 'Inductive Reasoning', 'Deductive Reasoning', 'Visualization']],
  [7, TASK_IDS.DUAL_TASK, 60, 'closed', 'eyes_closed',
    ['Time Sharing', 'Category Flexibility', 'Deductive Reasoning', 'Selective Attention', 'Information Ordering'],
    ['Mathematical Reasoning', 'Number Facility', 'Memorization', 'Reaction Time', 'Auditory Attention']],
  [8, TASK_IDS.ANOMALY, 60, 'open', 'eyes_open',
    ['Problem Sensitivity', 'Deductive Reasoning', 'Selective Attention', 'Information Ordering'],
    ['Inductive Reasoning', 'Perceptual Speed', 'Reaction Time', 'Speed of Closure', 'Flexibility of Closure']],
  [9, TASK_IDS.VISUAL_COMPARISON, 60, 'open', 'eyes_open',
    ['Perceptual Speed', 'Reaction Time'],
    ['Speed of Closure', 'Flexibility of Closure', 'Visualization', 'Spatial Orientation', 'Problem Sensitivity']],
  [10, TASK_IDS.CLOSURE, 60, 'open', 'eyes_open',
    ['Speed of Closure', 'Flexibility of Closure'],
    ['Perceptual Speed', 'Spatial Orientation', 'Problem Sensitivity', 'Reaction Time', 'Selective Attention']],
  [11, TASK_IDS.SPEECH_NOISE, 60, 'closed', 'eyes_closed',
    ['Oral Comprehension', 'Speech Recognition', 'Auditory Attention'],
    ['Oral Expression', 'Speech Clarity', 'Reaction Time', 'Written Comprehension', 'Written Expression']],
  [12, TASK_IDS.WRITTEN, 90, 'open', 'eyes_open',
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

// `acousticallyCalibrated: true` is what unlocks Speech Recognition and Oral
// Comprehension, and it is a claim about a *measured file*. Recording a hash
// without checking it means a regenerated WAV (or a profile edited without
// regenerating) would ship audio whose real SNR nobody verified, while the
// export still asserts calibration. These two tests close that loop.
test('every shipped speech-in-noise asset matches the sha256 the profile calibrates against', () => {
  const speech = audioProfileForTask(TASK_IDS.SPEECH_NOISE);
  const assetsDir = new URL('../../assets/', import.meta.url);
  for (const [formId, asset] of Object.entries(speech.assetsByForm)) {
    const file = new URL(asset.uri, assetsDir);
    assert.ok(existsSync(file), `${formId}: ${asset.uri} is missing from src/assets`);
    const actual = createHash('sha256').update(readFileSync(file)).digest('hex');
    assert.equal(
      actual, asset.sha256,
      `${formId}: shipped audio does not match the calibrated sha256 -- regenerate with `
      + 'tools/build_speech_in_noise_assets.py --target-snr-db 11.5 and update the profile',
    );
  }
});

test('the narration text the audio was generated from still matches the scored passage', () => {
  // The passage in SPEECH_BASE_FORMS is the answer key's source, while the WAV
  // is generated from tools/narration/<id>_text.txt. If those drift, the
  // participant hears one story and is scored against another -- silently, and
  // with no failing signal anywhere else in the suite.
  const narrationDir = new URL('../../../tools/narration/', import.meta.url);
  for (const form of FORM_REGISTRY_FOR_TESTS[TASK_IDS.SPEECH_NOISE]) {
    const file = new URL(`${form.id}_text.txt`, narrationDir);
    assert.ok(existsSync(file), `${form.id}_text.txt is missing`);
    assert.equal(
      readFileSync(file, 'utf8').trim(), form.passage.trim(),
      `${form.id}: narration text has drifted from the scored passage -- re-export it and `
      + 'regenerate the narration (see tools/README.md)',
    );
  }
});
