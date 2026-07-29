import assert from 'node:assert/strict';
import test from 'node:test';

import { TASK_IDS, taskFormForSession } from './optimizedBatteryConfig.mjs';
import { dualTaskReferenceCosts, postSwitchUpdateCount } from './dualTaskReferenceCosts.mjs';

const dualForm = () => taskFormForSession(TASK_IDS.DUAL_TASK, 'session_2');

const auditoryReference = (countingError, actualTargetCount = 10) => ({
  [TASK_IDS.AUDITORY_COUNT]: {
    metrics: { actual_target_count: actualTargetCount, counting_error: countingError },
  },
});

test('post-switch update count is derived from the form without a phase boundary', () => {
  const form = dualForm();
  const derived = postSwitchUpdateCount(form);
  const expected = form.updateTimes.filter((_, index) => index >= form.updateTimes.length / 2).length;
  assert.equal(derived, expected);
  assert.equal(derived, 3);
});

test('post-switch count is unavailable when the rule change is not recoverable', () => {
  // Identical deltas mean the switch leaves no arithmetic signature.
  assert.equal(postSwitchUpdateCount({
    startValue: 0, beforeDelta: 2, afterDelta: 2, finalValue: 12, updateTimes: [1, 2, 3, 4, 5, 6],
  }), null);
  assert.equal(postSwitchUpdateCount(null), null);
  assert.equal(postSwitchUpdateCount({ startValue: 0 }), null);
});

test('exact dual-task performance against an exact reference yields zero cost', () => {
  const form = dualForm();
  const { dualTaskCost, switchCost } = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount, finalValue: form.finalValue },
    references: auditoryReference(0),
  });
  assert.equal(dualTaskCost, 0);
  assert.equal(switchCost, 0);
});

test('never applying the post-switch rule produces the maximum switch cost', () => {
  const form = dualForm();
  const unswitchedFinal = form.startValue + form.updateTimes.length * form.beforeDelta;
  const { switchCost, diagnostics } = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount, finalValue: unswitchedFinal },
    references: auditoryReference(0),
  });
  assert.equal(switchCost, 1);
  assert.equal(diagnostics.post_switch_update_count, 3);
  assert.equal(diagnostics.max_unswitched_error, 3 * Math.abs(form.beforeDelta - form.afterDelta));
});

test('a single missed post-switch update costs one third and stays inside the configured cap', () => {
  const form = dualForm();
  const deltaGap = Math.abs(form.beforeDelta - form.afterDelta);
  const { switchCost } = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount, finalValue: form.finalValue + deltaGap },
    references: auditoryReference(0),
  });
  assert.ok(Math.abs(switchCost - 1 / 3) < 1e-9);
  // The bundled candidate cap (0.34) is chosen to admit exactly one missed update.
  assert.ok(switchCost <= 0.34);
});

test('attention cost reflects degradation relative to the single-task reference', () => {
  const form = dualForm();
  // Two counting errors under dual load, none in the Task 3 single-task run.
  const degraded = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount - 2, finalValue: form.finalValue },
    references: auditoryReference(0, form.targetCount),
  });
  assert.ok(Math.abs(degraded.dualTaskCost - 2 / form.targetCount) < 1e-9);

  // The same dual-task error, but the participant was equally inaccurate alone:
  // no dual-specific degradation, so no cost.
  const equallyInaccurate = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount - 2, finalValue: form.finalValue },
    references: auditoryReference(-2, form.targetCount),
  });
  assert.equal(equallyInaccurate.dualTaskCost, 0);
});

test('cost is never negative when dual-task performance beats the reference', () => {
  const form = dualForm();
  const { dualTaskCost } = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount, finalValue: form.finalValue },
    references: auditoryReference(-3, form.targetCount),
  });
  assert.equal(dualTaskCost, 0);
});

test('a missing Task 3 reference leaves the dual-task cost unmeasured', () => {
  const form = dualForm();
  const { dualTaskCost, switchCost, diagnostics } = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount, finalValue: form.finalValue },
    references: {},
  });
  assert.equal(dualTaskCost, null, 'no reference means no measurable dual-task cost');
  assert.equal(diagnostics.attention_reference_available, false);
  // The switch cost needs no external reference, so it is still measurable.
  assert.equal(switchCost, 0);
});

test('a missing response leaves both costs unmeasured', () => {
  const form = dualForm();
  const { dualTaskCost, switchCost } = dualTaskReferenceCosts({
    form,
    response: {},
    references: auditoryReference(0),
  });
  assert.equal(dualTaskCost, null);
  assert.equal(switchCost, null);
});

test('the working-memory reference is reported for traceability, not folded into the cost', () => {
  const form = dualForm();
  const withWm = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount, finalValue: form.finalValue },
    references: {
      ...auditoryReference(0),
      [TASK_IDS.WORKING_MEMORY]: { metrics: { item_error_count: 2 } },
    },
  });
  const withoutWm = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount, finalValue: form.finalValue },
    references: auditoryReference(0),
  });
  assert.equal(withWm.diagnostics.working_memory_reference_available, true);
  assert.equal(withWm.diagnostics.working_memory_reference_item_errors, 2);
  assert.equal(withoutWm.diagnostics.working_memory_reference_available, false);
  // Identical costs: the working-memory reference must not change the number.
  assert.equal(withWm.dualTaskCost, withoutWm.dualTaskCost);
  assert.equal(withWm.switchCost, withoutWm.switchCost);
});

test('raw metrics objects are accepted as well as stored behavioral_evidence', () => {
  const form = dualForm();
  const viaMetrics = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount - 1, finalValue: form.finalValue },
    references: { [TASK_IDS.AUDITORY_COUNT]: { actual_target_count: form.targetCount, counting_error: 0 } },
  });
  const viaEvidence = dualTaskReferenceCosts({
    form,
    response: { targetCount: form.targetCount - 1, finalValue: form.finalValue },
    references: auditoryReference(0, form.targetCount),
  });
  assert.equal(viaMetrics.dualTaskCost, viaEvidence.dualTaskCost);
});
