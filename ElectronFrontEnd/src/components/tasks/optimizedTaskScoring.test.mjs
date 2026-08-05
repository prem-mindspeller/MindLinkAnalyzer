import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ACTIVE_BATTERY_PROFILE,
  TASK_IDS,
  audioProfileForTask,
  scoringRubricFor,
  taskFormForSession,
  taskTimingFor,
} from './optimizedBatteryConfig.mjs';
import { scoreOptimizedTask, classifySpeed } from './optimizedTaskScoring.mjs';

const form = (taskId) => taskFormForSession(taskId, 'session_1');

test('objective final answers pass and incorrect answers fail', () => {
  const numerical = form(TASK_IDS.NUMERICAL);
  assert.equal(scoreOptimizedTask(TASK_IDS.NUMERICAL, numerical, { finalValue: numerical.answer }).status, 'passed');
  assert.equal(scoreOptimizedTask(TASK_IDS.NUMERICAL, numerical, { finalValue: numerical.answer + 1 }).status, 'failed');

  const memory = form(TASK_IDS.WORKING_MEMORY);
  assert.equal(scoreOptimizedTask(TASK_IDS.WORKING_MEMORY, memory, { finalSequence: memory.answer.join('-') }).status, 'passed');
  assert.equal(scoreOptimizedTask(TASK_IDS.WORKING_MEMORY, memory, { finalSequence: '1-2-3-4' }).status, 'failed');
});

test('auditory and dual-task scores retain signed error metrics', () => {
  const auditory = form(TASK_IDS.AUDITORY_COUNT);
  const auditoryResult = scoreOptimizedTask(TASK_IDS.AUDITORY_COUNT, auditory, { targetCount: auditory.targetCount - 2 });
  assert.equal(auditoryResult.status, 'failed');
  assert.equal(auditoryResult.metrics.counting_error, -2);

  const dual = form(TASK_IDS.DUAL_TASK);
  const dualResult = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, {
    targetCount: dual.targetCount,
    finalValue: dual.finalValue,
  });
  assert.equal(dualResult.status, 'pending_review');
  assert.equal(dualResult.metrics.attention_count_error, 0);
  assert.equal(dualResult.metrics.numerical_update_error, 0);
  assert.equal(dualResult.metrics.dual_task_cost, null);
  assert.equal(dualResult.metrics.switch_cost, null);
  assert.equal(dualResult.ability_validation['Time Sharing'], 'pending_review');
  assert.equal(dualResult.ability_validation['Selective Attention'], 'passed');
});

test('missing values are never coerced into the number zero', () => {
  // Number(null) and Number('') are both 0, so an unguarded numeric() would
  // read a blank answer as the answer 0 and an unmeasured cost as "no cost".
  const numerical = form(TASK_IDS.NUMERICAL);
  for (const blank of [undefined, null, '', '   ']) {
    const result = scoreOptimizedTask(TASK_IDS.NUMERICAL, numerical, { finalValue: blank });
    assert.equal(result.metrics.reported_final_value, null, `blank ${JSON.stringify(blank)} must stay unreported`);
    assert.equal(result.status, 'failed');
  }

  const dual = form(TASK_IDS.DUAL_TASK);
  const unmeasured = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, {
    targetCount: dual.targetCount,
    finalValue: dual.finalValue,
  }, { dualTaskCost: null, switchCost: null });
  assert.equal(unmeasured.metrics.dual_task_cost, null);
  assert.equal(unmeasured.metrics.cost_thresholds_available, false);
  assert.equal(unmeasured.ability_validation['Time Sharing'], 'pending_review');
});

test('an explicit null response or runtime does not throw', () => {
  // Default parameters only cover an omitted/undefined argument, not an
  // explicit null -- a real risk at this exported, multiply-called boundary.
  const numerical = form(TASK_IDS.NUMERICAL);
  assert.doesNotThrow(() => scoreOptimizedTask(TASK_IDS.NUMERICAL, numerical, null));
  assert.equal(scoreOptimizedTask(TASK_IDS.NUMERICAL, numerical, null).status, 'failed');

  const dual = form(TASK_IDS.DUAL_TASK);
  const exactOutputs = { targetCount: dual.targetCount, finalValue: dual.finalValue };
  assert.doesNotThrow(() => scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, exactOutputs, null));
  assert.equal(scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, exactOutputs, null).ability_validation['Time Sharing'], 'pending_review');
});

test('time sharing resolves once reference costs are supplied by the runner', () => {
  const dual = form(TASK_IDS.DUAL_TASK);
  const exactOutputs = { targetCount: dual.targetCount, finalValue: dual.finalValue };

  // Costs measured and inside the configured caps: Time Sharing is evidenced.
  const withinCaps = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, exactOutputs, {
    dualTaskCost: 0,
    switchCost: 1 / 3,
  });
  assert.equal(withinCaps.metrics.cost_thresholds_available, true);
  assert.equal(withinCaps.ability_validation['Time Sharing'], 'passed');
  assert.equal(withinCaps.status, 'passed');

  // A switch cost above the cap fails the dual-task-specific ability.
  const missedSwitch = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, exactOutputs, {
    dualTaskCost: 0,
    switchCost: 1,
  });
  assert.equal(missedSwitch.ability_validation['Time Sharing'], 'failed');

  // An attention cost above the cap likewise fails it.
  const attentionCost = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, exactOutputs, {
    dualTaskCost: 0.9,
    switchCost: 0,
  });
  assert.equal(attentionCost.ability_validation['Time Sharing'], 'failed');

  // Missing reference data must not be treated as zero cost.
  const unmeasured = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, exactOutputs, {
    dualTaskCost: null,
    switchCost: 0,
  });
  assert.equal(unmeasured.metrics.cost_thresholds_available, false);
  assert.equal(unmeasured.ability_validation['Time Sharing'], 'pending_review');
});

test('time sharing is evaluated independently of exact-output correctness', () => {
  // With a zero-tolerance exactness gate, a passing attempt always has zero
  // measured cost, so the cost caps could accept but never reject — Time
  // Sharing could never actually discriminate degrees of dual-task
  // degradation. Decoupling it from outputsCorrect fixes that: it is judged
  // purely against the configured cost caps, whatever the raw count/update
  // accuracy was.
  const dual = form(TASK_IDS.DUAL_TASK);
  const exactOutputs = { targetCount: dual.targetCount, finalValue: dual.finalValue };
  const inexactOutputs = { targetCount: dual.targetCount + 1, finalValue: dual.finalValue + 1 };

  // Inexact raw outputs, but the runner's measured cost is within the caps:
  // Time Sharing passes even though the attempt is not otherwise correct.
  const costOkDespiteError = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, inexactOutputs, {
    dualTaskCost: 0,
    switchCost: 1 / 3,
  });
  assert.equal(costOkDespiteError.metrics.outputs_correct, false);
  assert.equal(costOkDespiteError.ability_validation['Time Sharing'], 'passed');
  // The overall attempt is still not a full success: raw output was wrong.
  assert.equal(costOkDespiteError.status, 'failed');
  // Only Time Sharing is decoupled — the task's other linked abilities still
  // require exact outputs.
  assert.equal(costOkDespiteError.ability_validation['Selective Attention'], 'failed');
  assert.equal(costOkDespiteError.ability_validation['Deductive Reasoning'], 'failed');

  // Inexact raw outputs AND a cost above the cap: Time Sharing fails too, but
  // for its own, independent reason (the cost cap, not the exactness gate).
  const costTooHighAndInexact = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, inexactOutputs, {
    dualTaskCost: 0.9,
    switchCost: 1,
  });
  assert.equal(costTooHighAndInexact.ability_validation['Time Sharing'], 'failed');
  assert.equal(costTooHighAndInexact.status, 'failed');

  // Exact raw outputs still resolve exactly as before this change.
  const exactAndWithinCaps = scoreOptimizedTask(TASK_IDS.DUAL_TASK, dual, exactOutputs, {
    dualTaskCost: 0, switchCost: 0,
  });
  assert.equal(exactAndWithinCaps.metrics.outputs_correct, true);
  assert.equal(exactAndWithinCaps.ability_validation['Time Sharing'], 'passed');
  assert.equal(exactAndWithinCaps.status, 'passed');
});

test('reaction time is measured only from an actual rendered mismatch onset', () => {
  const comparison = form(TASK_IDS.VISUAL_COMPARISON);
  const renderedOnsetMs = comparison.mismatchOnset * 1000 + 37;
  const valid = scoreOptimizedTask(TASK_IDS.VISUAL_COMPARISON, comparison, {}, {
    detected: true,
    mismatchRenderedElapsedMs: renderedOnsetMs,
    responseElapsedMs: renderedOnsetMs + 740,
  });
  assert.equal(valid.status, 'passed');
  assert.equal(valid.metrics.reaction_time_ms, 740);
  assert.equal(valid.metrics.rendered_mismatch_onset_ms, renderedOnsetMs);

  const falseAlarm = scoreOptimizedTask(TASK_IDS.VISUAL_COMPARISON, comparison, {}, {
    detected: true,
    mismatchRenderedElapsedMs: renderedOnsetMs,
    responseElapsedMs: comparison.mismatchOnset * 1000 - 1,
  });
  assert.equal(falseAlarm.status, 'failed');
  assert.equal(falseAlarm.metrics.false_alarm, true);
  assert.equal(falseAlarm.metrics.reaction_time_ms, null);

  const unmarked = scoreOptimizedTask(TASK_IDS.VISUAL_COMPARISON, comparison, {}, {
    detected: true,
    responseElapsedMs: comparison.mismatchOnset * 1000 + 1000,
  });
  assert.equal(unmarked.status, 'failed');
  assert.equal(unmarked.metrics.false_alarm, true);
});

test('closure scoring uses the configured reveal fraction instead of total task duration', () => {
  const closure = form(TASK_IDS.CLOSURE);
  const halfwaySeconds = (
    closure.revealSchedule.revealStartSeconds + closure.revealSchedule.fullyVisibleSeconds
  ) / 2;
  const result = scoreOptimizedTask(TASK_IDS.CLOSURE, closure, { target: closure.target }, {
    detected: true,
    responseElapsedMs: halfwaySeconds * 1000,
  });
  assert.equal(result.metrics.visibility_threshold_fraction, 0.5);
  assert.equal(result.ability_validation['Speed of Closure'], 'passed');
});

test('closure has no minimum-exposure delay -- an immediate correct response is credited', () => {
  const closure = form(TASK_IDS.CLOSURE);
  const immediate = scoreOptimizedTask(TASK_IDS.CLOSURE, closure, { target: closure.target }, {
    detected: true,
    responseElapsedMs: 0,
  });
  assert.equal(immediate.metrics.recognition_accuracy, true);
  assert.equal(immediate.metrics.visibility_threshold_fraction, 0);
  assert.equal(immediate.ability_validation['Speed of Closure'], 'passed');
  // Recognised at revealFraction 0 is the densest possible noise, so
  // Flexibility of Closure is credited too.
  assert.equal(immediate.ability_validation['Flexibility of Closure'], 'passed');
});

test('flexibility of closure is recognition accuracy only, independent of timing', () => {
  // Flexibility of Closure no longer depends on responding before a
  // reveal-fraction threshold: with the object only reliably recognizable in
  // the low-40s, that made the ability effectively unearnable. It is now
  // purely "did they identify the right object". Speed carries the timing.
  const closure = form(TASK_IDS.CLOSURE);

  const early = scoreOptimizedTask(TASK_IDS.CLOSURE, closure, { target: closure.target }, {
    detected: true,
    responseElapsedMs: 20000,
  });
  const late = scoreOptimizedTask(TASK_IDS.CLOSURE, closure, { target: closure.target }, {
    detected: true,
    responseElapsedMs: 58000,
  });
  for (const outcome of [early, late]) {
    assert.equal(outcome.ability_validation['Flexibility of Closure'], 'passed');
    assert.equal(outcome.ability_validation['Speed of Closure'], 'passed');
    assert.equal(outcome.status, 'passed');
  }

  // A wrong target fails both, regardless of how fast it was answered.
  const wrong = scoreOptimizedTask(TASK_IDS.CLOSURE, closure, { target: 'definitely_not_the_target' }, {
    detected: true,
    responseElapsedMs: 43000,
  });
  assert.equal(wrong.status, 'failed');
  assert.equal(wrong.ability_validation['Flexibility of Closure'], 'failed');
  assert.equal(wrong.ability_validation['Speed of Closure'], 'failed');
  assert.equal(wrong.ability_grades, undefined, 'a failed task grades nothing');
});

test('speed of closure is graded fast/mediocre/slow from the configured bands', () => {
  const closure = form(TASK_IDS.CLOSURE);
  const gradeAt = (ms) => scoreOptimizedTask(TASK_IDS.CLOSURE, closure, { target: closure.target }, {
    detected: true,
    responseElapsedMs: ms,
  });

  // Configured bands: <=47s fast, 47-50s mediocre, >50s slow.
  assert.equal(gradeAt(43000).metrics.speed_grade, 'fast');
  assert.equal(gradeAt(47000).metrics.speed_grade, 'fast', 'upper bound is inclusive');
  assert.equal(gradeAt(48500).metrics.speed_grade, 'mediocre');
  assert.equal(gradeAt(50000).metrics.speed_grade, 'mediocre', 'upper bound is inclusive');
  assert.equal(gradeAt(52000).metrics.speed_grade, 'slow');

  // The grade is published per ability so it can reach the backend's scoring.
  assert.deepEqual(gradeAt(43000).ability_grades, { 'Speed of Closure': 'fast' });
  assert.deepEqual(gradeAt(52000).ability_grades, { 'Speed of Closure': 'slow' });
  // A slow response still demonstrates closure -- the ability is credited and
  // the grade carries the penalty downstream.
  assert.equal(gradeAt(52000).ability_validation['Speed of Closure'], 'passed');

  // Responding before the object is reliably recognizable is graded fast but
  // flagged: with six options an early correct answer can be a 1-in-6 guess.
  assert.equal(gradeAt(20000).metrics.responded_before_recognizable, true);
  assert.equal(gradeAt(43000).metrics.responded_before_recognizable, false);
});

test('reaction time and perceptual speed are graded, and a too-slow response is not credited', () => {
  const compare = form(TASK_IDS.VISUAL_COMPARISON);
  const onsetMs = compare.mismatchOnset * 1000;
  const at = (reactionMs) => scoreOptimizedTask(TASK_IDS.VISUAL_COMPARISON, compare, {}, {
    detected: true,
    responseElapsedMs: onsetMs + reactionMs,
    mismatchRenderedElapsedMs: onsetMs,
  });

  // Bands are measured from the rendered mismatch onset: <=5s fast,
  // 5-15s mediocre, beyond that the ability is not credited at all.
  assert.equal(at(500).metrics.speed_grade, 'fast');
  assert.equal(at(5000).metrics.speed_grade, 'fast', 'upper bound is inclusive');
  assert.equal(at(8000).metrics.speed_grade, 'mediocre');
  assert.equal(at(15000).metrics.speed_grade, 'mediocre', 'upper bound is inclusive');

  assert.deepEqual(at(500).ability_grades, { 'Perceptual Speed': 'fast', 'Reaction Time': 'fast' });
  assert.deepEqual(at(8000).ability_grades, { 'Perceptual Speed': 'mediocre', 'Reaction Time': 'mediocre' });

  // The regression this replaces: maximumReactionTimeMs was null, so a
  // 20-second response was credited identically to a 50ms one.
  const tooSlow = at(20000);
  assert.equal(tooSlow.status, 'failed');
  assert.equal(tooSlow.ability_validation['Reaction Time'], 'failed');
  assert.equal(tooSlow.ability_validation['Perceptual Speed'], 'failed');
  assert.equal(tooSlow.ability_grades, undefined, 'a failed task grades nothing');

  // A press before the mismatch is rendered remains a false alarm, ungraded.
  const falseAlarm = scoreOptimizedTask(TASK_IDS.VISUAL_COMPARISON, compare, {}, {
    detected: true,
    responseElapsedMs: onsetMs - 1000,
    mismatchRenderedElapsedMs: onsetMs,
  });
  assert.equal(falseAlarm.status, 'failed');
  assert.equal(falseAlarm.metrics.false_alarm, true);
  assert.equal(falseAlarm.metrics.speed_grade, null);
});

test('classifySpeed treats an unmeasured time or missing bands as ungraded, never slow', () => {
  assert.equal(classifySpeed(null, { fastMaxMs: 5000, mediocreMaxMs: 15000 }), null);
  assert.equal(classifySpeed(1000, null), null);
  assert.equal(classifySpeed(1000, {}), null);
  assert.equal(classifySpeed(1000, { fastMaxMs: 5000 }), null, 'a partial band config grades nothing');
});

test('anomaly-type scoring rejects checkbox over-selection', () => {
  const anomaly = form(TASK_IDS.ANOMALY);
  const exact = scoreOptimizedTask(TASK_IDS.ANOMALY, anomaly, {
    anomalyCount: anomaly.anomalyCount,
    anomalyTypes: [...anomaly.anomalyTypes],
  });
  assert.equal(exact.status, 'passed');

  const overSelected = scoreOptimizedTask(TASK_IDS.ANOMALY, anomaly, {
    anomalyCount: anomaly.anomalyCount,
    anomalyTypes: [...anomaly.anomalyTypes, 'not_present_in_form'],
  });
  assert.equal(overSelected.status, 'failed');
  assert.equal(overSelected.metrics.anomaly_type_recall_correct, false);
});

test('speech key-detail rejects a wrong option and passes outright once calibrated and correct', () => {
  // Both answers are selected from a fixed option list (see
  // SpeechInNoiseTask.jsx), so this task is fully objective now — no free
  // text, no rubric, no PENDING-on-assessment state.
  const speech = form(TASK_IDS.SPEECH_NOISE);
  const wrongOption = scoreOptimizedTask(TASK_IDS.SPEECH_NOISE, speech, {
    mainIdea: speech.mainIdea,
    keyDetail: speech.keyDetailOptions.find((option) => option !== speech.keyDetail),
  });
  assert.equal(wrongOption.status, 'failed');
  assert.equal(wrongOption.metrics.key_detail_correct, false);
  assert.equal(wrongOption.ability_validation['Speech Recognition'], 'failed');

  // The bundled default audio is a calibrated premixed asset, so a fully
  // correct, fully objective response resolves straight to passed.
  const correct = scoreOptimizedTask(TASK_IDS.SPEECH_NOISE, speech, {
    mainIdea: speech.mainIdea,
    keyDetail: speech.keyDetail,
  });
  assert.equal(correct.status, 'passed');
  assert.equal(correct.metrics.key_detail_correct, true);
  assert.equal(correct.metrics.snr_calibrated, true);
  assert.equal(correct.ability_validation['Speech Recognition'], 'passed');
  assert.equal(correct.ability_validation['Auditory Attention'], 'passed');
  assert.equal(correct.ability_validation['Oral Comprehension'], 'passed');
});

test('a null summary word bound means unbounded, not unsatisfiable', () => {
  // `count <= null` coerces null to 0 and is always false, which would reject
  // every summary if a maximum were ever configured as null to mean "no
  // limit".
  const profile = JSON.parse(JSON.stringify(ACTIVE_BATTERY_PROFILE));
  profile.thresholds[TASK_IDS.WRITTEN].summaryMaximumWords = null;
  const written = form(TASK_IDS.WRITTEN);
  const longSummary = Array.from({ length: 200 }, (_, i) => `word${i}`).join(' ');
  const result = scoreOptimizedTask(TASK_IDS.WRITTEN, written, {
    mainIdea: written.mainIdea,
    summary: longSummary,
  }, {}, profile);
  assert.equal(result.metrics.summary_length_valid, true);
  assert.deepEqual(result.metrics.configured_summary_word_range, [
    profile.thresholds[TASK_IDS.WRITTEN].summaryMinimumWords, null,
  ]);
});

test('free-text constructs remain pending review', () => {
  const ideation = form(TASK_IDS.IDEATION);
  const ideas = scoreOptimizedTask(TASK_IDS.IDEATION, ideation, { ideas: 'door stop\nplant marker\npaper weight' });
  assert.equal(ideas.status, 'pending_review');
  assert.equal(ideas.metrics.captured_idea_count, 3);
  assert.equal(ideas.ability_validation.Originality, 'pending_review');

  const written = form(TASK_IDS.WRITTEN);
  const summary = Array.from({ length: 25 }, (_, index) => `word${index}`).join(' ');
  const writtenResult = scoreOptimizedTask(TASK_IDS.WRITTEN, written, {
    mainIdea: written.mainIdea,
    summary,
  });
  assert.equal(writtenResult.status, 'pending_review');
  assert.equal(writtenResult.ability_validation['Written Comprehension'], 'passed');
  assert.equal(writtenResult.ability_validation['Written Expression'], 'pending_review');
});

test('ideation abilities resolve once a rubric assessment is supplied', () => {
  const ideation = form(TASK_IDS.IDEATION);
  const rubricId = scoringRubricFor(TASK_IDS.IDEATION).id;
  const ideas = { ideas: 'door stop\nplant marker\npaper weight\ndoorstop wedge\nbook end' };

  const strong = scoreOptimizedTask(TASK_IDS.IDEATION, ideation, ideas, {
    rubricAssessment: {
      rubricId,
      scores: { relevantIdeaCount: 5, categoryDiversity: 3, originality: 3.5 },
    },
  });
  assert.equal(strong.status, 'passed');
  assert.equal(strong.ability_validation['Fluency of Ideas'], 'passed');
  assert.equal(strong.ability_validation.Originality, 'passed');

  // Below the configured ideation floors.
  const weak = scoreOptimizedTask(TASK_IDS.IDEATION, ideation, ideas, {
    rubricAssessment: {
      rubricId,
      scores: { relevantIdeaCount: 1, categoryDiversity: 1, originality: 1 },
    },
  });
  assert.equal(weak.ability_validation.Originality, 'failed');

  // Scores graded against a different rubric must not be honoured.
  const foreign = scoreOptimizedTask(TASK_IDS.IDEATION, ideation, ideas, {
    rubricAssessment: {
      rubricId: 'some_other_rubric',
      scores: { relevantIdeaCount: 5, categoryDiversity: 3, originality: 3.5 },
    },
  });
  assert.equal(foreign.ability_validation.Originality, 'pending_review');
});

test('written expression resolves once a rubric assessment is supplied', () => {
  const written = form(TASK_IDS.WRITTEN);
  const rubricId = scoringRubricFor(TASK_IDS.WRITTEN).id;
  const summary = Array.from({ length: 25 }, (_, index) => `word${index}`).join(' ');
  const response = { mainIdea: written.mainIdea, summary };

  const adequate = scoreOptimizedTask(TASK_IDS.WRITTEN, written, response, {
    rubricAssessment: {
      rubricId,
      scores: { clarity: 4, coherence: 4, completeness: 3, information_ordering: 3 },
    },
  });
  assert.equal(adequate.ability_validation['Written Expression'], 'passed');
  assert.equal(adequate.ability_validation['Written Comprehension'], 'passed');
  assert.equal(adequate.status, 'passed');

  const belowBar = scoreOptimizedTask(TASK_IDS.WRITTEN, written, response, {
    rubricAssessment: {
      rubricId,
      scores: { clarity: 2, coherence: 2, completeness: 2, information_ordering: 2 },
    },
  });
  assert.equal(belowBar.ability_validation['Written Expression'], 'failed');

  // A partial assessment cannot decide the threshold.
  const partial = scoreOptimizedTask(TASK_IDS.WRITTEN, written, response, {
    rubricAssessment: { rubricId, scores: { clarity: 5 } },
  });
  assert.equal(partial.ability_validation['Written Expression'], 'pending_review');
});

test('oral comprehension needs calibrated audio, independent of correctness', () => {
  const speech = form(TASK_IDS.SPEECH_NOISE);
  const response = {
    mainIdea: speech.mainIdea,
    keyDetail: speech.keyDetail,
  };

  // Correct answers, but on a profile whose audio is still browser TTS at an
  // uncalibrated SNR (the bundled default's prior state, kept here as an
  // explicit override so this behaviour stays covered).
  const uncalibratedProfile = JSON.parse(JSON.stringify(ACTIVE_BATTERY_PROFILE));
  uncalibratedProfile.audioProfiles.speech_in_noise.mode = 'browser_speech_synthesis_with_generated_noise';
  uncalibratedProfile.audioProfiles.speech_in_noise.acousticallyCalibrated = false;

  const uncalibrated = scoreOptimizedTask(TASK_IDS.SPEECH_NOISE, speech, response, {}, uncalibratedProfile);
  assert.equal(uncalibrated.metrics.snr_calibrated, false);
  assert.equal(uncalibrated.ability_validation['Oral Comprehension'], 'pending_review');
  assert.equal(uncalibrated.ability_validation['Speech Recognition'], 'pending_review');

  // The bundled default is now a calibrated premixed asset (built by
  // tools/build_speech_in_noise_assets.py), so both abilities resolve without
  // any profile override.
  const calibrated = scoreOptimizedTask(TASK_IDS.SPEECH_NOISE, speech, response);
  assert.equal(calibrated.metrics.snr_calibrated, true);
  assert.equal(calibrated.status, 'passed');
  assert.equal(calibrated.ability_validation['Oral Comprehension'], 'passed');
  assert.equal(calibrated.ability_validation['Speech Recognition'], 'passed');
  assert.equal(calibrated.ability_validation['Auditory Attention'], 'passed');
});

test('an injected profile changes thresholds, rubric identity, audio and timing data', () => {
  const profile = JSON.parse(JSON.stringify(ACTIVE_BATTERY_PROFILE));
  profile.protocolProfile.profile_version = 'validated-test-profile';
  profile.protocolProfile.components.rubrics.version = 'validated-rubrics-test';
  profile.protocolProfile.components.thresholds.version = 'validated-thresholds-test';
  profile.thresholds[TASK_IDS.AUDITORY_COUNT].maximumAbsoluteCountError = 2;
  profile.rubrics[TASK_IDS.AUDITORY_COUNT].id = 'validated_count_tolerance';
  profile.audioProfiles.speech_in_noise.mode = 'premixed_audio_asset';
  profile.audioProfiles.speech_in_noise.assetUri = 'asset://speech/validated-a.wav';
  profile.audioProfiles.speech_in_noise.acousticallyCalibrated = true;
  profile.taskTimings[TASK_IDS.AUDITORY_COUNT].durationSeconds = 135;

  const auditory = form(TASK_IDS.AUDITORY_COUNT);
  const result = scoreOptimizedTask(TASK_IDS.AUDITORY_COUNT, auditory, {
    targetCount: auditory.targetCount - 2,
  }, {}, profile);

  assert.equal(result.status, 'passed');
  // scoring_method names the algorithm that actually ran (fixed by the
  // taskId branch, not by the injected profile) — the injected rubric's
  // identity is tracked separately via configuration.applied_rubric_id.
  assert.equal(result.scoring_method, 'candidate_exact_count_threshold');
  assert.equal(result.configuration.applied_rubric_id, 'validated_count_tolerance');
  assert.equal(result.configuration.profile_version, 'validated-test-profile');
  assert.equal(result.configuration.rubric_set_version, 'validated-rubrics-test');
  assert.equal(result.configuration.threshold_set_version, 'validated-thresholds-test');
  assert.equal(scoringRubricFor(TASK_IDS.AUDITORY_COUNT, profile).id, 'validated_count_tolerance');
  assert.equal(audioProfileForTask(TASK_IDS.SPEECH_NOISE, profile).mode, 'premixed_audio_asset');
  assert.equal(taskTimingFor(TASK_IDS.AUDITORY_COUNT, profile).durationSeconds, 135);
});

test('a rubric config missing its own id can never accidentally match an assessment that is equally missing one', () => {
  // Every rubric in the shipped profile has a real id, so this cannot happen
  // today -- but the whole point of the rubricId comparison is proving an
  // assessment was actually graded against a specific rubric, and undefined
  // !== undefined being false would otherwise defeat that silently if a
  // future profile edit ever left an id unset.
  const profile = JSON.parse(JSON.stringify(ACTIVE_BATTERY_PROFILE));
  delete profile.rubrics[TASK_IDS.WRITTEN].id;

  const written = form(TASK_IDS.WRITTEN);
  const summary = Array.from({ length: 25 }, (_, index) => `word${index}`).join(' ');
  const result = scoreOptimizedTask(TASK_IDS.WRITTEN, written, { mainIdea: written.mainIdea, summary }, {
    // Also has no rubricId -- would "match" an unguarded undefined !== undefined.
    rubricAssessment: { scores: { clarity: 5, coherence: 5, completeness: 5, information_ordering: 5 } },
  }, profile);

  assert.equal(result.ability_validation['Written Expression'], 'pending_review');
  assert.notEqual(result.status, 'passed');
});
