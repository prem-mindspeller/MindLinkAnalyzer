import {
  ACTIVE_BATTERY_PROFILE,
  PROTOCOL_PROFILE_METADATA,
  TASK_DEFINITIONS,
  TASK_IDS,
  audioProfileForTask,
  closureRevealState,
  countWords,
  maximumWordsFor,
  normalizeText,
  normalizedSequence,
  scoringRubricFor,
  scoringThresholdsFor,
} from './optimizedBatteryConfig.mjs';

const PASSED = 'passed';
const FAILED = 'failed';
const PENDING = 'pending_review';

export const SPEED_FAST = 'fast';
export const SPEED_MEDIOCRE = 'mediocre';
export const SPEED_SLOW = 'slow';

/**
 * Classify a measured time against a task's configured speed bands.
 *
 * Speed-defined abilities (Reaction Time, Perceptual Speed, Speed of Closure)
 * are graded rather than merely gated: the grade travels with the behavioral
 * evidence into the neuroprofile, where it becomes part of the ability's
 * numeric score and therefore influences role ranking. Returns null when the
 * time was not measured or the task declares no bands, which callers must
 * treat as "ungraded", never as slow.
 *
 * @param {number|null} elapsedMs measured time (post-onset latency for Task 9,
 *   absolute elapsed time for Task 10 -- each task defines its own zero).
 * @param {{fastMaxMs: number, mediocreMaxMs: number}|null|undefined} bands
 */
export const classifySpeed = (elapsedMs, bands) => {
  if (elapsedMs == null || !bands) return null;
  const fastMax = numeric(bands.fastMaxMs);
  const mediocreMax = numeric(bands.mediocreMaxMs);
  if (fastMax == null || mediocreMax == null) return null;
  if (elapsedMs <= fastMax) return SPEED_FAST;
  if (elapsedMs <= mediocreMax) return SPEED_MEDIOCRE;
  return SPEED_SLOW;
};

export const ACCURACY_EXACT = 'exact';
export const ACCURACY_CLOSE = 'close';

/**
 * Classify an error magnitude against a task's configured accuracy
 * tolerance. Accuracy-defined abilities (e.g. Task 8's Problem Sensitivity,
 * Selective Attention, Deductive Reasoning, Information Ordering) are graded
 * rather than gated by a zero-tolerance cliff: a small miss still
 * demonstrates the ability, just less cleanly than an exact one. Returns
 * null -- ungraded, not credited -- when the error was not measured, the
 * task declares no tolerance, or the error exceeds the tolerated band
 * entirely (a genuine miss, not a minor one).
 *
 * @param {number|null} errorMagnitude non-negative distance from a perfect
 *   answer (e.g. |reported - actual| for a count, or
 *   expectedCount - effectiveCorrectCount for a set-recall task).
 * @param {{exactMaxError: number, closeMaxError: number}|null|undefined} tolerance
 */
export const classifyAccuracy = (errorMagnitude, tolerance) => {
  if (errorMagnitude == null || !tolerance) return null;
  const exactMax = numeric(tolerance.exactMaxError);
  const closeMax = numeric(tolerance.closeMaxError);
  if (exactMax == null || closeMax == null) return null;
  if (errorMagnitude <= exactMax) return ACCURACY_EXACT;
  if (errorMagnitude <= closeMax) return ACCURACY_CLOSE;
  return null;
};

const allAbilities = (taskId, status) => Object.fromEntries(
  (TASK_DEFINITIONS[taskId]?.abilities || []).map((ability) => [ability, status]),
);

const numeric = (value) => {
  // null/undefined/blank mean "not measured" and must not collapse to 0:
  // Number(null) and Number('') are both 0, which would silently turn a missing
  // reference cost into "no cost", or an empty answer field into the answer 0.
  if (value == null) return null;
  if (typeof value === 'string' && value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

// The key detail is chosen from `keyDetailOptions`, so it compares exactly the
// way the main idea does. It was previously free text matched by token overlap
// against an English answer key, which marked a correct answer written in any
// of the app's other nine languages as a failure — and could not distinguish
// that from a genuinely wrong answer. Selecting removes the language dependency
// entirely; the distractors carry the difficulty instead.
const keyDetailMatches = (value, expected) => (
  normalizeText(value) === normalizeText(expected)
);

const externalRubricStatus = (runtime, rubric) => {
  const assessment = runtime?.rubricAssessment;
  // rubric?.id (not just !==) so a rubric config missing its own id can never
  // "match" an assessment that is equally missing one.
  if (!assessment || !rubric?.id || assessment.rubricId !== rubric.id) return null;
  return assessment.status === PASSED || assessment.status === FAILED
    ? assessment.status
    : null;
};

/**
 * Rubric scores are only usable when they were produced for *this* rubric.
 * Without the id guard, an assessment carried over from another task or from a
 * superseded rubric version could silently satisfy these thresholds.
 */
const rubricScoresFor = (runtime, rubric) => {
  const assessment = runtime?.rubricAssessment;
  if (!assessment || !rubric?.id || assessment.rubricId !== rubric.id) return null;
  const scores = assessment.scores;
  return scores && typeof scores === 'object' ? scores : null;
};

const thresholdRubricStatus = (runtime, minimumRubricScores, rubric) => {
  if (!minimumRubricScores || typeof minimumRubricScores !== 'object') return null;
  const entries = Object.entries(minimumRubricScores);
  if (!entries.length) return null;
  const scores = rubricScoresFor(runtime, rubric);
  if (!scores) return null;
  const decisions = entries.map(([dimension, minimum]) => {
    const score = numeric(scores[dimension]);
    const threshold = numeric(minimum);
    return score == null || threshold == null ? null : score >= threshold;
  });
  if (decisions.some((decision) => decision == null)) return null;
  return decisions.every(Boolean) ? PASSED : FAILED;
};

function result(
  taskId,
  status,
  response,
  metrics,
  abilityValidation,
  scoringMethod,
  notes = [],
  configuration = null,
  abilityGrades = null,
) {
  return {
    task_id: taskId,
    status,
    valid_performance: status === PASSED,
    response,
    metrics,
    ability_validation: abilityValidation,
    // {abilityName: 'fast'|'mediocre'|'slow'} for speed-defined abilities only.
    // Omitted entirely (not an empty object) for tasks with no graded ability,
    // so downstream consumers can distinguish "this task grades nothing" from
    // "this task grades something but produced no grade this run".
    ...(abilityGrades ? { ability_grades: abilityGrades } : {}),
    scoring_method: scoringMethod,
    notes,
    configuration,
  };
}

/**
 * Score only outcomes for which the bundled form has an objective answer key.
 * Language/creative rubrics remain pending instead of receiving invented scores.
 */
export function scoreOptimizedTask(
  taskId,
  form,
  response = {},
  runtime = {},
  profile = ACTIVE_BATTERY_PROFILE,
) {
  // Default parameters only cover an omitted/undefined argument; an explicit
  // null (a real risk at this exported boundary, called from several sites
  // and directly by tests) would otherwise throw before any task branch runs.
  response = response || {};
  runtime = runtime || {};
  const rubric = scoringRubricFor(taskId, profile);
  const thresholds = scoringThresholdsFor(taskId, profile);
  const profileMetadata = profile.protocolProfile || PROTOCOL_PROFILE_METADATA;
  const scoringConfiguration = {
    profile_id: profileMetadata.profile_id,
    profile_version: profileMetadata.profile_version,
    rubric_set_id: profileMetadata.components.rubrics.id,
    rubric_set_version: profileMetadata.components.rubrics.version,
    threshold_set_id: profileMetadata.components.thresholds.id,
    threshold_set_version: profileMetadata.components.thresholds.version,
    applied_rubric_id: rubric.id,
    rubric_mode: rubric.mode,
    rubric_dimensions: Array.isArray(rubric.dimensions) ? [...rubric.dimensions] : [],
    validation_status: profileMetadata.validation_status,
  };
  const scoredResult = (
    configuredTaskId,
    status,
    configuredResponse,
    metrics,
    abilityValidation,
    scoringMethod,
    notes = [],
    abilityGrades = null,
  ) => result(
    configuredTaskId,
    status,
    configuredResponse,
    metrics,
    abilityValidation,
    // Each call site's own descriptive string (what algorithm actually scored
    // this), not rubric.id (which rubric config was nominally attached) — the
    // two were conflated here, silently discarding every call site's argument
    // in favour of rubric.id. The rubric identity is still fully recorded,
    // unconditionally, as configuration.applied_rubric_id below.
    scoringMethod,
    notes,
    scoringConfiguration,
    abilityGrades,
  );

  if (taskId === TASK_IDS.NUMERICAL) {
    const reported = numeric(response.finalValue);
    const finalError = reported == null ? null : reported - form.answer;
    const correct = finalError != null
      && Math.abs(finalError) <= thresholds.maximumAbsoluteFinalError;
    return scoredResult(taskId, correct ? PASSED : FAILED, response, {
      expected_final_value: form.answer,
      reported_final_value: reported,
      final_answer_error: finalError,
      final_answer_correct: correct,
    }, allAbilities(taskId, correct ? PASSED : FAILED), 'exact_final_answer');
  }

  if (taskId === TASK_IDS.WORKING_MEMORY) {
    const reported = normalizedSequence(response.finalSequence);
    const itemErrors = Math.max(reported.length, form.answer.length) - reported.reduce(
      (matches, value, index) => matches + (value === form.answer[index] ? 1 : 0),
      0,
    );
    const correct = itemErrors <= thresholds.maximumItemErrors;
    return scoredResult(taskId, correct ? PASSED : FAILED, response, {
      expected_final_sequence: form.answer,
      reported_final_sequence: reported,
      item_error_count: itemErrors,
      final_sequence_correct: correct,
    }, allAbilities(taskId, correct ? PASSED : FAILED), 'exact_final_sequence');
  }

  if (taskId === TASK_IDS.AUDITORY_COUNT) {
    const reported = numeric(response.targetCount);
    const error = reported == null ? null : reported - form.targetCount;
    const correct = error != null && Math.abs(error) <= thresholds.maximumAbsoluteCountError;
    return scoredResult(taskId, correct ? PASSED : FAILED, response, {
      actual_target_count: form.targetCount,
      reported_target_count: reported,
      counting_error: error,
      exact_count: error === 0,
      count_within_configured_threshold: correct,
    }, allAbilities(taskId, correct ? PASSED : FAILED), 'candidate_exact_count_threshold', [
      'The optimization document does not define the final performance threshold; exact count is the transparent bundled default.',
    ]);
  }

  if (taskId === TASK_IDS.SEMANTIC) {
    const ruleOneCorrect = normalizeText(response.ruleOne) === normalizeText(form.ruleOne);
    const ruleTwoCorrect = normalizeText(response.ruleTwo) === normalizeText(form.ruleTwo);
    const switchDetected = response.switchDetected === true || response.switchDetected === 'yes';
    const correct = (
      (!thresholds.requireBothRules || (ruleOneCorrect && ruleTwoCorrect))
      && (!thresholds.requireSwitchDetection || switchDetected)
    );
    return scoredResult(taskId, correct ? PASSED : FAILED, response, {
      rule_one_correct: ruleOneCorrect,
      rule_two_correct: ruleTwoCorrect,
      switch_detected: switchDetected,
    }, allAbilities(taskId, correct ? PASSED : FAILED), 'answer_key_and_switch');
  }

  if (taskId === TASK_IDS.VISUOSPATIAL) {
    const x = numeric(response.x);
    const y = numeric(response.y);
    const positionError = x == null || y == null
      ? null
      : Math.abs(x - form.answer.x) + Math.abs(y - form.answer.y);
    const positionCorrect = positionError != null
      && positionError <= thresholds.maximumPositionError;
    const orientationCorrect = normalizeText(response.orientation) === form.answer.orientation;
    const correct = positionCorrect
      && (!thresholds.requireOrientationMatch || orientationCorrect);
    return scoredResult(taskId, correct ? PASSED : FAILED, response, {
      expected_position: { x: form.answer.x, y: form.answer.y },
      reported_position: { x, y },
      expected_orientation: form.answer.orientation,
      reported_orientation: response.orientation || null,
      position_error: positionError,
      position_correct: positionCorrect,
      orientation_correct: orientationCorrect,
    }, allAbilities(taskId, correct ? PASSED : FAILED), 'position_and_orientation_key');
  }

  if (taskId === TASK_IDS.IDEATION) {
    const ideas = String(response.ideas || '').split(/\n+/).map((idea) => idea.trim()).filter(Boolean);
    const ideationScores = rubricScoresFor(runtime, rubric) || {};
    const relevantIdeaCount = numeric(ideationScores.relevantIdeaCount);
    const originalityScore = numeric(ideationScores.originality);
    const categoryDiversity = numeric(ideationScores.categoryDiversity);
    const configuredThresholdDecisionAvailable = [
      thresholds.minimumRelevantIdeas,
      thresholds.minimumCategoryDiversity,
      thresholds.minimumOriginality,
      relevantIdeaCount,
      originalityScore,
      categoryDiversity,
    ].every((value) => value != null);
    const configuredThresholdStatus = !configuredThresholdDecisionAvailable
      ? null
      : relevantIdeaCount >= thresholds.minimumRelevantIdeas
        && categoryDiversity >= thresholds.minimumCategoryDiversity
        && originalityScore >= thresholds.minimumOriginality
        ? PASSED
        : FAILED;
    const assessmentStatus = externalRubricStatus(runtime, rubric);
    const status = assessmentStatus || configuredThresholdStatus || PENDING;
    return scoredResult(taskId, status, response, {
      captured_idea_count: ideas.length,
      ideas,
      relevant_idea_count: relevantIdeaCount,
      originality_score: originalityScore,
      category_diversity: categoryDiversity,
      configured_threshold_decision_available: configuredThresholdDecisionAvailable,
      configured_thresholds: {
        minimum_relevant_ideas: thresholds.minimumRelevantIdeas,
        minimum_category_diversity: thresholds.minimumCategoryDiversity,
        minimum_originality: thresholds.minimumOriginality,
      },
    }, allAbilities(taskId, status), 'human_or_validated_rubric_required', [
      'Relevance, originality, and category diversity require a validated rubric and remain pending review.',
    ]);
  }

  if (taskId === TASK_IDS.DUAL_TASK) {
    const reportedCount = numeric(response.targetCount);
    const reportedValue = numeric(response.finalValue);
    const countError = reportedCount == null ? null : reportedCount - form.targetCount;
    const updateError = reportedValue == null ? null : reportedValue - form.finalValue;
    const outputsCorrect = (
      countError != null
      && updateError != null
      && Math.abs(countError) <= thresholds.maximumAbsoluteCountError
      && Math.abs(updateError) <= thresholds.maximumAbsoluteUpdateError
    );
    const dualTaskCost = numeric(runtime.dualTaskCost);
    const switchCost = numeric(runtime.switchCost);
    const costThresholdsAvailable = (
      thresholds.maximumDualTaskCost != null
      && thresholds.maximumSwitchCost != null
      && dualTaskCost != null
      && switchCost != null
    );
    const costsPass = costThresholdsAvailable
      && dualTaskCost <= thresholds.maximumDualTaskCost
      && switchCost <= thresholds.maximumSwitchCost;
    // Time Sharing is deliberately independent of outputsCorrect: with an
    // exact-output requirement, a passing attempt always has zero measured
    // cost (see dualTaskReferenceCosts.mjs), which made the cost caps
    // vacuous — they could accept but never reject. Judging Time Sharing
    // purely against the cost caps, whatever the raw count/update accuracy
    // was, lets it actually discriminate degrees of dual-task degradation. A
    // raw counting/arithmetic error is still a real failure — it fails the
    // task's other abilities and its overall status below — it just is not,
    // by itself, evidence about dual-task cost.
    const timeSharingStatus = costThresholdsAvailable ? (costsPass ? PASSED : FAILED) : PENDING;
    const abilityValidation = {
      ...allAbilities(taskId, outputsCorrect ? PASSED : FAILED),
      'Time Sharing': timeSharingStatus,
    };
    const status = !outputsCorrect ? FAILED : costThresholdsAvailable ? (costsPass ? PASSED : FAILED) : PENDING;
    return scoredResult(taskId, status, response, {
      actual_target_count: form.targetCount,
      reported_target_count: reportedCount,
      attention_count_error: countError,
      expected_final_value: form.finalValue,
      reported_final_value: reportedValue,
      numerical_update_error: updateError,
      outputs_correct: outputsCorrect,
      dual_task_cost: dualTaskCost,
      switch_cost: switchCost,
      reference_cost_metrics_available: dualTaskCost != null && switchCost != null,
      cost_thresholds_available: costThresholdsAvailable,
    }, abilityValidation, 'exact_outputs_plus_cost_gated_time_sharing', [
      'Dual-task and switch-cost fields remain null until the runner supplies matched Task 2/3 reference metrics (see dualTaskReferenceCosts.mjs).',
      'Time Sharing is scored independently of exact-output correctness: it can pass on an inexact attempt whose measured cost is within the configured caps, and can fail on an exact attempt only if cost metrics are unavailable (stays pending) or a cost cap is configured and exceeded.',
    ]);
  }

  if (taskId === TASK_IDS.ANOMALY) {
    const reportedCount = numeric(response.anomalyCount);
    const selectedTypes = [...new Set(
      Array.isArray(response.anomalyTypes) ? response.anomalyTypes : [],
    )];
    const expectedTypes = [...new Set(form.anomalyTypes)];

    // Count accuracy -> Problem Sensitivity + Selective Attention: noticing
    // something is wrong and sustaining attention across the whole stream.
    // Graded (exact/close/miss) instead of the previous zero-tolerance gate,
    // so a single miscount no longer scores identically to losing the thread
    // entirely.
    const countError = reportedCount == null ? null : reportedCount - form.anomalyCount;
    const countGrade = classifyAccuracy(
      countError == null ? null : Math.abs(countError),
      thresholds.countTolerance,
    );
    const countAcceptable = countGrade != null;

    // Type accuracy -> Deductive Reasoning + Information Ordering: applying
    // the rule to correctly categorize each violation. Extra (wrong)
    // selections count against the participant exactly like missed ones do,
    // so checking every box can never trivially maximise this score -- each
    // extra cancels one correct selection before the error magnitude is
    // graded.
    const correctlySelectedCount = expectedTypes.filter((type) => selectedTypes.includes(type)).length;
    const extraSelectedCount = selectedTypes.filter((type) => !expectedTypes.includes(type)).length;
    const effectiveTypeCorrect = Math.max(0, correctlySelectedCount - extraSelectedCount);
    const typeError = expectedTypes.length - effectiveTypeCorrect;
    const typeGrade = classifyAccuracy(typeError, thresholds.typeTolerance);
    const typeAcceptable = typeGrade != null;

    // Each ability group is gated independently: a clean count with a poor
    // type recall (or vice versa) credits only the abilities its own
    // dimension actually evidenced, rather than one verdict deciding all
    // four abilities together.
    const status = countAcceptable && typeAcceptable ? PASSED : FAILED;
    const abilityValidation = {
      'Problem Sensitivity': countAcceptable ? PASSED : FAILED,
      'Selective Attention': countAcceptable ? PASSED : FAILED,
      'Deductive Reasoning': typeAcceptable ? PASSED : FAILED,
      'Information Ordering': typeAcceptable ? PASSED : FAILED,
    };
    const abilityGrades = {
      ...(countAcceptable ? { 'Problem Sensitivity': countGrade, 'Selective Attention': countGrade } : {}),
      ...(typeAcceptable ? { 'Deductive Reasoning': typeGrade, 'Information Ordering': typeGrade } : {}),
    };

    return scoredResult(taskId, status, response, {
      actual_anomaly_count: form.anomalyCount,
      reported_anomaly_count: reportedCount,
      anomaly_count_error: countError,
      count_grade: countGrade,
      expected_anomaly_types: expectedTypes,
      reported_anomaly_types: selectedTypes,
      anomaly_type_correctly_selected: correctlySelectedCount,
      anomaly_type_extra_selected: extraSelectedCount,
      anomaly_type_effective_correct: effectiveTypeCorrect,
      type_grade: typeGrade,
      confidence: numeric(response.confidence),
    }, abilityValidation, 'count_and_type_accuracy_bands', [],
    Object.keys(abilityGrades).length ? abilityGrades : null);
  }

  if (taskId === TASK_IDS.VISUAL_COMPARISON) {
    const responseMs = numeric(runtime.responseElapsedMs);
    const plannedOnsetMs = form.mismatchOnset * 1000;
    const renderedOnsetMs = numeric(runtime.mismatchRenderedElapsedMs);
    const onsetMs = renderedOnsetMs == null && !thresholds.requireRenderedMismatchOnset
      ? plannedOnsetMs
      : renderedOnsetMs;
    const detected = runtime.detected === true;
    const falseAlarm = detected && responseMs != null && (onsetMs == null || responseMs < onsetMs);
    const reactionTimeMs = detected && !falseAlarm && responseMs != null ? responseMs - onsetMs : null;
    const latencyWithinRange = reactionTimeMs != null
      && reactionTimeMs >= thresholds.minimumPostOnsetLatencyMs
      && (thresholds.maximumReactionTimeMs == null || reactionTimeMs <= thresholds.maximumReactionTimeMs);
    const correct = detected && !falseAlarm && latencyWithinRange;
    // Graded, not just gated: reactionTimeMs is measured from the rendered
    // mismatch onset, so the grade is "how quickly did they notice", which is
    // exactly what Reaction Time and Perceptual Speed are. A response slower
    // than the mediocre bound already fails latencyWithinRange above, so a
    // graded task is never slow -- 'slow' is reachable only as the reason the
    // task failed, and is reported for traceability rather than credited.
    const speedGrade = classifySpeed(reactionTimeMs, thresholds.speedBands);
    const abilityGrades = correct && speedGrade
      ? Object.fromEntries(
        (TASK_DEFINITIONS[taskId]?.abilities || []).map((ability) => [ability, speedGrade]),
      )
      : null;
    return scoredResult(taskId, correct ? PASSED : FAILED, response, {
      planned_mismatch_onset_ms: plannedOnsetMs,
      rendered_mismatch_onset_ms: renderedOnsetMs,
      scoring_mismatch_onset_ms: onsetMs,
      button_response_ms: responseMs,
      detection_accuracy: correct,
      false_alarm: falseAlarm,
      reaction_time_ms: reactionTimeMs,
      latency_within_configured_range: latencyWithinRange,
      speed_grade: speedGrade,
      configured_speed_bands: thresholds.speedBands || null,
    }, allAbilities(taskId, correct ? PASSED : FAILED), 'single_rendered_onset_latency',
    [], abilityGrades);
  }

  if (taskId === TASK_IDS.CLOSURE) {
    const responseMs = numeric(runtime.responseElapsedMs);
    const revealState = closureRevealState(form, responseMs == null ? 0 : responseMs / 1000);
    // No minimum-exposure gate: the button is clickable immediately (see
    // optimizedBatteryProfile.mjs), so a genuine response is any detected
    // click with a recorded time -- guessing risk is offset by
    // CLOSURE_FORMS' 6 options instead of a response-timing floor.
    const responded = runtime.detected === true && responseMs != null;
    const targetCorrect = normalizeText(response.target) === normalizeText(form.target);
    const correct = responded && (!thresholds.requireCorrectTarget || targetCorrect);
    // Flexibility of Closure is now purely a recognition-accuracy construct:
    // did they identify the right object, regardless of when. The previous
    // reveal-fraction gate (respond before 50% revealed) was removed from it --
    // with the object only reliably recognisable in the low-40s, that made the
    // ability effectively unearnable. See the CLOSURE thresholds comment in
    // optimizedBatteryProfile.mjs.
    //
    // Speed of Closure carries the timing instead, graded on absolute elapsed
    // time. A slow response still demonstrates closure (they did recognise
    // it), so unlike Task 9 the ability is credited and the grade carries the
    // penalty downstream -- speed is the whole construct here, but recognition
    // is not in doubt.
    const speedGrade = classifySpeed(responseMs, thresholds.speedBands);
    const respondedBeforeRecognizable = correct
      && thresholds.recognizableFromMs != null
      && responseMs != null
      && responseMs < thresholds.recognizableFromMs;
    const abilityValidation = correct
      ? { 'Speed of Closure': PASSED, 'Flexibility of Closure': PASSED }
      : allAbilities(taskId, FAILED);
    const abilityGrades = correct && speedGrade ? { 'Speed of Closure': speedGrade } : null;
    const status = correct ? PASSED : FAILED;
    return scoredResult(taskId, status, response, {
      recognition_accuracy: targetCorrect,
      recognition_time_ms: responseMs,
      visibility_threshold_fraction: responseMs == null ? null : revealState.revealFraction,
      symbol_opacity_at_response: responseMs == null ? null : revealState.symbolOpacity,
      blur_px_at_response: responseMs == null ? null : revealState.blurPx,
      noise_opacity_at_response: responseMs == null ? null : revealState.noiseOpacity,
      speed_grade: speedGrade,
      configured_speed_bands: thresholds.speedBands || null,
      // With six options an early correct answer can be a 1-in-6 guess rather
      // than genuine early closure; surfaced so it is auditable rather than
      // silently graded fast.
      responded_before_recognizable: respondedBeforeRecognizable,
    }, abilityValidation, 'recognition_key_and_speed_bands', [
      'Flexibility of Closure is evidenced by identifying the correct object, independent of timing.',
      'Speed of Closure is graded fast/mediocre/slow from the configured response-time bands.',
      ...(respondedBeforeRecognizable
        ? ['Responded before the object was reliably recognizable; an early correct answer may be a guess.']
        : []),
    ], abilityGrades);
  }

  if (taskId === TASK_IDS.SPEECH_NOISE) {
    // Both answers are selected from a fixed option list (see
    // SpeechInNoiseTask.jsx), so this task is fully objective — no free text,
    // no rubric grading, no PENDING-on-assessment state. The only thing that
    // can still leave an ability PENDING rather than PASSED is the audio
    // itself not being acoustically calibrated.
    const mainIdeaCorrect = normalizeText(response.mainIdea) === normalizeText(form.mainIdea);
    const keyDetailCorrect = keyDetailMatches(response.keyDetail, form.keyDetail);
    const objectivePass = (!thresholds.requireMainIdea || mainIdeaCorrect) && keyDetailCorrect;
    const audioProfile = audioProfileForTask(taskId, profile);
    const snrCalibrated = audioProfile.acousticallyCalibrated === true;
    const calibrationPermitsPass = (
      !thresholds.calibratedSnrRequiredForAbilityPass || snrCalibrated
    );
    const status = !objectivePass ? FAILED : calibrationPermitsPass ? PASSED : PENDING;
    const abilityValidation = {
      'Oral Comprehension': !objectivePass ? FAILED : status,
      'Speech Recognition': !keyDetailCorrect ? FAILED : status,
      'Auditory Attention': !objectivePass ? FAILED : status,
    };
    return scoredResult(taskId, status, response, {
      main_idea_correct: mainIdeaCorrect,
      key_detail_correct: keyDetailCorrect,
      nominal_snr_db: audioProfile.nominalSnrDb,
      snr_calibrated: snrCalibrated,
      calibrated_snr_required_for_ability_pass: thresholds.calibratedSnrRequiredForAbilityPass,
    }, abilityValidation, 'objective_items', snrCalibrated
      ? []
      : [
        'The WebAudio/TTS candidate form records a nominal, not acoustically calibrated, SNR.',
        'All SNR-dependent abilities remain pending because browser TTS and noise playback are not acoustically calibrated.',
      ]);
  }

  if (taskId === TASK_IDS.WRITTEN) {
    const mainIdeaCorrect = normalizeText(response.mainIdea) === normalizeText(form.mainIdea);
    const summaryWordCount = countWords(response.summary);
    const summaryMaximumWords = maximumWordsFor(response.summary, thresholds.summaryMaximumWords);
    // A null bound means "no limit" — spelled out explicitly rather than
    // relying on `>= null` / `<= null` numeric coercion (only one direction of
    // which comes out right, and neither documents the intent at the call site).
    const lengthValid = (thresholds.summaryMinimumWords == null || summaryWordCount >= thresholds.summaryMinimumWords)
      && (summaryMaximumWords == null || summaryWordCount <= summaryMaximumWords);
    const objectivePass = (!thresholds.requireMainIdea || mainIdeaCorrect) && lengthValid;
    const assessmentStatus = externalRubricStatus(runtime, rubric)
      || thresholdRubricStatus(runtime, thresholds.minimumRubricScores, rubric);
    const status = !objectivePass ? FAILED : assessmentStatus || PENDING;
    const abilityValidation = {
      'Written Comprehension': mainIdeaCorrect ? PASSED : FAILED,
      'Written Expression': objectivePass ? status : FAILED,
      'Inductive Reasoning': mainIdeaCorrect ? (assessmentStatus || PENDING) : FAILED,
      'Information Ordering': objectivePass ? status : FAILED,
    };
    return scoredResult(taskId, status, response, {
      main_idea_correct: mainIdeaCorrect,
      summary_word_count: summaryWordCount,
      summary_length_valid: lengthValid,
      summary_quality: null,
      coherence: null,
      information_ordering: null,
      // The range actually applied, so this stays consistent with
      // summary_length_valid when a denser script widened the maximum.
      configured_summary_word_range: [
        thresholds.summaryMinimumWords,
        summaryMaximumWords,
      ],
    }, abilityValidation, 'objective_main_idea_plus_pending_summary_rubric', [
      'Written Expression and synthesis characteristics remain pending until the summary is reviewed.',
    ]);
  }

  return scoredResult(taskId, PENDING, response, {}, allAbilities(taskId, PENDING), 'unsupported_task_scoring');
}
