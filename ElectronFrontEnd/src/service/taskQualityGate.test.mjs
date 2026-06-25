import assert from 'node:assert/strict';

import {
  buildSingleTaskAnalysisPayload,
  commitTaskAttempt,
  evaluateTaskQuality,
  isRepeatSignalReady,
  resolveTaskQualityOutcome,
} from './taskQualityGate.mjs';

function createStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      data.set(key, String(value));
    },
    removeItem(key) {
      data.delete(key);
    },
  };
}

const baseline = {
  eyes_closed: [{ fp1: 1 }, { fp1: 2 }],
  eyes_open: [{ fp1: 3 }],
};

const passingAnalysis = {
  neuroprofile_feature_export: {
    tasks: [{
      canonical_task_id: 'mental_math',
      signal_quality: { usable_feature_count: 2, rejected_feature_count: 4 },
      task_summary: { confidence: 'weak' },
    }],
    feature_rows: [],
  },
};

const failingAnalysis = {
  neuroprofile_feature_export: {
    tasks: [{
      canonical_task_id: 'mental_math',
      signal_quality: { usable_feature_count: 1, rejected_feature_count: 5 },
      task_summary: { confidence: 'insufficient' },
    }],
    feature_rows: [],
  },
};

{
  const storage = createStorage({
    calibrationData_eyes_closed: JSON.stringify(baseline.eyes_closed),
    calibrationData_eyes_open: JSON.stringify(baseline.eyes_open),
    taskData_mental_math: JSON.stringify([{ stale: true }]),
    completedTasks: JSON.stringify(['visual_imagery', 'mental_math']),
  });

  const payload = buildSingleTaskAnalysisPayload('mental_math', [{ fresh: true }], storage);

  assert.deepEqual(payload.baseline, baseline);
  assert.deepEqual(payload.tasks, { mental_math: [{ fresh: true }] });
}

{
  const quality = evaluateTaskQuality(passingAnalysis, 'mental_math');

  assert.equal(quality.sufficient, true);
  assert.equal(quality.usableFeatureCount, 2);
  assert.equal(quality.taskConfidence, 'weak');
}

{
  const quality = evaluateTaskQuality(failingAnalysis, 'mental_math');

  assert.equal(quality.sufficient, false);
  assert.equal(quality.usableFeatureCount, 1);
  assert.equal(quality.taskConfidence, 'insufficient');
}

{
  const quality = evaluateTaskQuality({
    neuroprofile_feature_export: {
      feature_rows: [
        { canonical_task_id: 'mental_math', passes_neuroprofile_gate: true },
        { canonical_task_id: 'mental_math', passes_neuroprofile_gate: true },
        { canonical_task_id: 'mental_math', passes_neuroprofile_gate: false },
      ],
    },
  }, 'mental_math');

  assert.equal(quality.sufficient, true);
  assert.equal(quality.reportableFeatureRows, 2);
}


{
  const quality = evaluateTaskQuality(passingAnalysis, 'mental_math', {
    signalStats: {
      total: 20,
      good: 10,
      noisy: 8,
      notWorn: 2,
      worstPoorSignal: 200,
    },
  });

  assert.equal(quality.sufficient, false);
  assert.equal(quality.recordingSignal.acceptable, false);
  assert.equal(quality.recordingSignal.notWornCount, 2);
  assert.match(quality.recordingSignal.reason, /not worn|noisy/i);
}
{
  assert.equal(
    resolveTaskQualityOutcome({ sufficient: false }, { forcedRepeatUsed: false }),
    'force_repeat',
  );
  assert.equal(
    resolveTaskQualityOutcome({ sufficient: false }, { forcedRepeatUsed: true }),
    'accept_with_warning',
  );
  assert.equal(
    resolveTaskQualityOutcome({ sufficient: true }, { forcedRepeatUsed: false }),
    'accept',
  );
}

{
  assert.equal(isRepeatSignalReady({ isGoodSignal: true, goodSignalStableMs: 4999 }), false);
  assert.equal(isRepeatSignalReady({ isGoodSignal: true, goodSignalStableMs: 5000 }), true);
  assert.equal(isRepeatSignalReady({ isGoodSignal: false, goodSignalStableMs: 9000 }), false);
}

{
  const storage = createStorage({
    taskData_mental_math: JSON.stringify([{ stale: true }]),
    completedTasks: JSON.stringify(['visual_imagery', 'mental_math']),
  });

  const completed = commitTaskAttempt('mental_math', [{ fresh: true }], storage);

  assert.deepEqual(JSON.parse(storage.getItem('taskData_mental_math')), [{ fresh: true }]);
  assert.deepEqual(completed, ['visual_imagery', 'mental_math']);
  assert.deepEqual(JSON.parse(storage.getItem('completedTasks')), ['visual_imagery', 'mental_math']);
}
