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
import { scoreOptimizedTask } from './optimizedTaskScoring.mjs';

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
  assert.equal(result.status, 'pending_review');
  assert.equal(result.metrics.visibility_threshold_fraction, 0.5);
  assert.equal(result.metrics.response_enabled_at_ms, closure.revealSchedule.responseEnabledSeconds * 1000);
  assert.equal(result.ability_validation['Speed of Closure'], 'passed');
  assert.equal(result.ability_validation['Flexibility of Closure'], 'pending_review');
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

test('speech key-detail matching rejects stopword-only answers and keeps uncalibrated abilities pending', () => {
  const speech = form(TASK_IDS.SPEECH_NOISE);
  const stopwordOnly = scoreOptimizedTask(TASK_IDS.SPEECH_NOISE, speech, {
    mainIdea: speech.mainIdea,
    keyDetail: 'the',
    paraphrase: 'A short candidate paraphrase.',
  });
  assert.equal(stopwordOnly.status, 'failed');
  assert.equal(stopwordOnly.metrics.key_detail_correct, false);

  const discriminativeDetail = scoreOptimizedTask(TASK_IDS.SPEECH_NOISE, speech, {
    mainIdea: speech.mainIdea,
    keyDetail: 'The marsh slowed it.',
    paraphrase: 'A short candidate paraphrase.',
  });
  assert.equal(discriminativeDetail.status, 'pending_review');
  assert.equal(discriminativeDetail.metrics.key_detail_correct, true);
  assert.equal(discriminativeDetail.metrics.snr_calibrated, false);
  assert.equal(discriminativeDetail.ability_validation['Speech Recognition'], 'pending_review');
  assert.equal(discriminativeDetail.ability_validation['Auditory Attention'], 'pending_review');
});

test('speech-in-noise answer scoring preserves non-Latin selected-language text', () => {
  const japanese = taskFormForSession(TASK_IDS.SPEECH_NOISE, 'session_3', undefined, 'ja');
  const result = scoreOptimizedTask(TASK_IDS.SPEECH_NOISE, japanese, {
    mainIdea: japanese.mainIdea,
    keyDetail: japanese.keyDetail,
    paraphrase: '要約です。',
  });
  assert.equal(result.metrics.main_idea_correct, true);
  assert.equal(result.metrics.key_detail_correct, true);
});

test('free-text constructs remain pending review', () => {
  const ideation = form(TASK_IDS.IDEATION);
  const ideas = scoreOptimizedTask(TASK_IDS.IDEATION, ideation, { ideas: 'door stop\nplant marker\npaper weight' });
  assert.equal(ideas.status, 'pending_review');
  assert.equal(ideas.metrics.captured_idea_count, 3);
  assert.equal(ideas.ability_validation.Originality, 'pending_review');

  const written = form(TASK_IDS.WRITTEN);
  const summary = Array.from({ length: 40 }, (_, index) => `word${index}`).join(' ');
  const writtenResult = scoreOptimizedTask(TASK_IDS.WRITTEN, written, {
    mainIdea: written.mainIdea,
    summary,
  });
  assert.equal(writtenResult.status, 'pending_review');
  assert.equal(writtenResult.ability_validation['Written Comprehension'], 'passed');
  assert.equal(writtenResult.ability_validation['Written Expression'], 'pending_review');
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
  assert.equal(result.scoring_method, 'validated_count_tolerance');
  assert.equal(result.configuration.profile_version, 'validated-test-profile');
  assert.equal(result.configuration.rubric_set_version, 'validated-rubrics-test');
  assert.equal(result.configuration.threshold_set_version, 'validated-thresholds-test');
  assert.equal(scoringRubricFor(TASK_IDS.AUDITORY_COUNT, profile).id, 'validated_count_tolerance');
  assert.equal(audioProfileForTask(TASK_IDS.SPEECH_NOISE, profile).mode, 'premixed_audio_asset');
  assert.equal(taskTimingFor(TASK_IDS.AUDITORY_COUNT, profile).durationSeconds, 135);
});
