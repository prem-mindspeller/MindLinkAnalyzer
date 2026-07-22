import assert from 'node:assert/strict';

import {
  buildSingleTaskAnalysisPayload,
  clearTaskAttempts,
  commitTaskAttempt,
  evaluateTaskQuality,
  isRepeatSignalReady,
  loadTaskAttempt,
  resolveTaskQualityOutcome,
} from './taskQualityGate.mjs';
import { PROTOCOL_PROFILE_METADATA } from '../components/tasks/optimizedBatteryProfile.mjs';

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
      scorable: true,
      task_qc: { meets_contiguous_clean_minimum: true },
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
      scorable: true,
      task_qc: { meets_contiguous_clean_minimum: true },
      signal_quality: { usable_feature_count: 1, rejected_feature_count: 5 },
      task_summary: { confidence: 'insufficient' },
    }],
    feature_rows: [],
  },
};

const goodSignalStats = {
  total: 20,
  good: 20,
  noisy: 0,
  notWorn: 0,
  worstPoorSignal: 0,
};

{
  const storage = createStorage({
    calibrationData_eyes_closed: JSON.stringify(baseline.eyes_closed),
    calibrationData_eyes_open: JSON.stringify(baseline.eyes_open),
    taskData_mental_math: JSON.stringify([{ stale: true }]),
    completedTasks: JSON.stringify(['visual_imagery', 'mental_math']),
    baselineCalibration: JSON.stringify({
      eyesClosed: { sample_rate_hz: 500, transport_segments: [{ start_sample_index: 0, end_sample_index_exclusive: 2 }] },
    }),
  });

  const payload = await buildSingleTaskAnalysisPayload('mental_math', [{ fresh: true }], storage);

  assert.deepEqual(payload.baseline, baseline);
  assert.deepEqual(payload.tasks, { mental_math: [{ fresh: true }] });
  assert.deepEqual(payload.baseline_metadata, {
    eyes_closed: { sample_rate_hz: 500, transport_segments: [{ start_sample_index: 0, end_sample_index_exclusive: 2 }] },
  });
  assert.deepEqual(payload.protocol_profile, PROTOCOL_PROFILE_METADATA);
  assert.equal(storage.getItem('calibrationData_eyes_closed'), null);
  assert.equal(storage.getItem('calibrationData_eyes_open'), null);
}

{
  const quality = evaluateTaskQuality(passingAnalysis, 'mental_math', {
    signalStats: goodSignalStats,
  });

  assert.equal(quality.sufficient, true);
  assert.equal(quality.usableFeatureCount, 2);
  assert.equal(quality.taskConfidence, 'weak');
}

{
  const quality = evaluateTaskQuality(failingAnalysis, 'mental_math', {
    signalStats: goodSignalStats,
  });

  assert.equal(quality.sufficient, true);
  assert.equal(quality.usableFeatureCount, 1);
  assert.equal(quality.taskConfidence, 'insufficient');
  assert.equal(quality.evidenceSufficient, false);
}

{
  const quality = evaluateTaskQuality({
    neuroprofile_feature_export: {
      tasks: [{
        canonical_task_id: 'mental_math',
        scorable: true,
        task_qc: { meets_contiguous_clean_minimum: true },
      }],
      feature_rows: [
        { canonical_task_id: 'mental_math', passes_neuroprofile_gate: true },
        { canonical_task_id: 'mental_math', passes_neuroprofile_gate: true },
        { canonical_task_id: 'mental_math', passes_neuroprofile_gate: false },
      ],
    },
  }, 'mental_math', { signalStats: goodSignalStats });

  assert.equal(quality.sufficient, true);
  assert.equal(quality.reportableFeatureRows, 2);
}

{
  const quality = evaluateTaskQuality({
    neuroprofile_feature_export: {
      tasks: [{
        canonical_task_id: 'mental_math',
        scorable: false,
        task_qc: { meets_contiguous_clean_minimum: false },
        signal_quality: { usable_feature_count: 8 },
        task_summary: { confidence: 'strong' },
      }],
      feature_rows: [],
    },
  }, 'mental_math', { signalStats: goodSignalStats });

  assert.equal(quality.sufficient, false);
  assert.equal(quality.backendScorable, false);
  assert.equal(quality.contiguousCleanSufficient, false);
}

{
  const quality = evaluateTaskQuality({
    per_task: {
      mental_math: {
        scorable: false,
        invalid_reasons: ['eyes_closed_baseline_has_less_than_20_contiguous_clean_seconds'],
        task_qc: { meets_contiguous_clean_minimum: true },
        baseline_qc: { meets_contiguous_clean_minimum: false },
      },
    },
    neuroprofile_feature_export: passingAnalysis.neuroprofile_feature_export,
  }, 'mental_math', { signalStats: goodSignalStats });

  assert.equal(quality.sufficient, false);
  assert.equal(quality.needsBaselineRepeat, true);
  assert.equal(quality.matchedBaselineSufficient, false);
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
    'force_repeat',
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

  const metadata = { formId: 'math-a', eyeState: 'closed' };
  const completed = await commitTaskAttempt('mental_math', [{ fresh: true }], storage, metadata);

  assert.equal(storage.getItem('taskData_mental_math'), null);
  assert.deepEqual(completed, ['visual_imagery', 'mental_math']);
  assert.deepEqual(JSON.parse(storage.getItem('completedTasks')), ['visual_imagery', 'mental_math']);
  const storedAttempt = await loadTaskAttempt('mental_math', storage);
  assert.deepEqual(storedAttempt, {
    key: `${storage.getItem('recordingStoreSessionId')}::mental_math`,
    sessionId: storage.getItem('recordingStoreSessionId'),
    taskId: 'mental_math',
    samples: [{ fresh: true }],
    metadata,
    updatedAt: storedAttempt.updatedAt,
  });

  const payload = await buildSingleTaskAnalysisPayload('mental_math', null, storage);
  assert.deepEqual(payload.tasks, { mental_math: [{ fresh: true }] });
  assert.deepEqual(payload.task_metadata, { mental_math: metadata });

  await clearTaskAttempts(['mental_math'], storage);
  assert.equal(await loadTaskAttempt('mental_math', storage), null);
}
