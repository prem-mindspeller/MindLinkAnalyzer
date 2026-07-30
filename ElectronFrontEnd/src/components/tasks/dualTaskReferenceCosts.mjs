/**
 * Behavioural dual-task and switch cost derivation for Task 7.
 *
 * The optimization document names Task 3 (Auditory Target Counting) as the
 * auditory-attention reference and Task 2 (Working-Memory Manipulation) as the
 * working-memory/updating reference, and requires "behavioural dual-task cost,
 * switch cost, attention-count error, and numerical-update error".
 *
 * Scope and honesty notes:
 *
 * - `dualTaskCost` is derived from the attention component only. Task 3 and
 *   Task 7 are built from the same tone-stream parameters, so their counting
 *   error rates are genuinely comparable. The updating component has no
 *   scale-matched single-task reference (Task 2 scores item errors over a
 *   maintained sequence, Task 7 scores arithmetic drift over a running total),
 *   so folding them into one number would be a false equivalence. The Task 2
 *   reference is reported for traceability instead.
 *
 * - `switchCost` needs no external reference: the post-switch rule change is
 *   recoverable from the form itself. A participant who never applies the new
 *   rule ends up exactly `postSwitchUpdates * |beforeDelta - afterDelta|` away
 *   from the expected total, which is the natural denominator.
 *
 * - Both costs are normalised to 0-1, where 0 is no measurable cost.
 *
 * Nothing here decides pass/fail; it only produces the metrics that
 * `scoreOptimizedTask` compares against the configured thresholds. When a
 * required reference is missing the cost stays null, which keeps Time Sharing
 * at pending_review rather than asserting a cost that was never measured.
 */

import { TASK_IDS } from './optimizedBatteryConfig.mjs';

const clamp01 = (value) => Math.max(0, Math.min(1, value));

const numeric = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const metricsOf = (attempt) => {
  if (!attempt || typeof attempt !== 'object') return null;
  // Accepts either a stored behavioral_evidence object or its metrics directly.
  const metrics = attempt.metrics && typeof attempt.metrics === 'object' ? attempt.metrics : attempt;
  return metrics && typeof metrics === 'object' ? metrics : null;
};

/**
 * Number of scheduled updates that fall after the rule switch.
 *
 * Derived algebraically from the form rather than from a phase boundary, so it
 * stays correct for any parallel form:
 *   final = start + (n - k) * before + k * after
 *   =>  k = (start + n * before - final) / (before - after)
 */
export function postSwitchUpdateCount(form) {
  const startValue = numeric(form?.startValue);
  const beforeDelta = numeric(form?.beforeDelta);
  const afterDelta = numeric(form?.afterDelta);
  const finalValue = numeric(form?.finalValue);
  const updateCount = Array.isArray(form?.updateTimes) ? form.updateTimes.length : null;
  if (startValue == null || beforeDelta == null || afterDelta == null
      || finalValue == null || updateCount == null) return null;
  const deltaGap = beforeDelta - afterDelta;
  if (deltaGap === 0) return null;
  const derived = (startValue + updateCount * beforeDelta - finalValue) / deltaGap;
  if (!Number.isInteger(derived) || derived < 0 || derived > updateCount) return null;
  return derived;
}

/**
 * @param {object} args
 * @param {object} args.form      the Task 7 form actually presented
 * @param {object} args.response  the participant's Task 7 response
 * @param {object} args.references stored attempts keyed by canonical task id
 * @returns {{dualTaskCost: number|null, switchCost: number|null, diagnostics: object}}
 */
export function dualTaskReferenceCosts({ form, response = {}, references = {} } = {}) {
  // Destructuring defaults only cover an omitted key, not an explicit null.
  references = references || {};
  const auditoryMetrics = metricsOf(references[TASK_IDS.AUDITORY_COUNT]);
  const workingMemoryMetrics = metricsOf(references[TASK_IDS.WORKING_MEMORY]);

  // ---- attention component: Task 7 versus the matched Task 3 reference ----
  const dualTargetCount = numeric(form?.targetCount);
  const reportedCount = numeric(response?.targetCount);
  const dualCountError = reportedCount == null || dualTargetCount == null
    ? null
    : reportedCount - dualTargetCount;

  const referenceTargetCount = numeric(auditoryMetrics?.actual_target_count);
  const referenceCountError = numeric(auditoryMetrics?.counting_error);

  const dualErrorRate = dualCountError == null || !dualTargetCount
    ? null
    : Math.abs(dualCountError) / dualTargetCount;
  const referenceErrorRate = referenceCountError == null || !referenceTargetCount
    ? null
    : Math.abs(referenceCountError) / referenceTargetCount;

  const dualTaskCost = dualErrorRate == null || referenceErrorRate == null
    ? null
    : clamp01(dualErrorRate - referenceErrorRate);

  // ---- switch component: recoverable from the Task 7 form alone ----
  const postSwitchUpdates = postSwitchUpdateCount(form);
  const beforeDelta = numeric(form?.beforeDelta);
  const afterDelta = numeric(form?.afterDelta);
  const expectedFinalValue = numeric(form?.finalValue);
  const reportedFinalValue = numeric(response?.finalValue);
  const updateError = reportedFinalValue == null || expectedFinalValue == null
    ? null
    : reportedFinalValue - expectedFinalValue;

  const maxUnswitchedError = postSwitchUpdates == null || beforeDelta == null || afterDelta == null
    ? null
    : postSwitchUpdates * Math.abs(beforeDelta - afterDelta);

  const switchCost = updateError == null || !maxUnswitchedError
    ? null
    : clamp01(Math.abs(updateError) / maxUnswitchedError);

  return {
    dualTaskCost,
    switchCost,
    diagnostics: {
      attention_reference_available: referenceErrorRate != null,
      attention_reference_task: TASK_IDS.AUDITORY_COUNT,
      dual_attention_error_rate: dualErrorRate,
      reference_attention_error_rate: referenceErrorRate,
      // Reported for traceability: the protocol names Task 2 as the updating
      // reference, but it is not scale-matched to the Task 7 running total, so
      // it is not folded into dualTaskCost.
      working_memory_reference_available: workingMemoryMetrics != null,
      working_memory_reference_task: TASK_IDS.WORKING_MEMORY,
      working_memory_reference_item_errors: numeric(workingMemoryMetrics?.item_error_count),
      post_switch_update_count: postSwitchUpdates,
      max_unswitched_error: maxUnswitchedError,
      numerical_update_error: updateError,
    },
  };
}
