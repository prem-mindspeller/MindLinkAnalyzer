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
  const quality = evaluateTaskQuality(passingAnalysis, 'mental_math', {
    signalStats: {
      total: 300,
      good: 295,
      noisy: 5,
      notWorn: 0,
      worstPoorSignal: 80,
    },
  });

  assert.equal(quality.recordingSignal.acceptable, true);
  assert.equal(quality.sufficient, true);
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

// The live status stream delivers one sample per second, so a 90-second Task 2
// contributes ~91 samples. A fixed allowance would make the proportional ratio
// unreachable and tighten the gate as tasks get longer.
{
  const analysis = {
    neuroprofile_feature_export: { tasks: [], feature_rows: [] },
    per_task: {
      working_memory_manipulation: {
        scorable: true,
        task_qc: { meets_contiguous_clean_minimum: true },
        baseline_qc: { meets_contiguous_clean_minimum: true },
        invalid_reasons: [],
      },
    },
  };
  const evaluate = (signalStats) => evaluateTaskQuality(
    analysis,
    'working_memory_manipulation',
    { signalStats },
  );

  // A handful of blink/jaw seconds across a 90-second block stays acceptable.
  const occasionalNoise = evaluate({ total: 91, good: 81, noisy: 10, notWorn: 0, worstPoorSignal: 80 });
  assert.equal(occasionalNoise.recordingSignal.acceptable, true);
  assert.equal(occasionalNoise.sufficient, true);
  assert.equal(resolveTaskQualityOutcome(occasionalNoise), 'accept');

  // Sustained noise beyond the proportional tolerance still forces a repeat.
  const sustainedNoise = evaluate({ total: 91, good: 61, noisy: 30, notWorn: 0, worstPoorSignal: 120 });
  assert.equal(sustainedNoise.recordingSignal.acceptable, false);
  assert.equal(resolveTaskQualityOutcome(sustainedNoise), 'force_repeat');
  assert.match(sustainedNoise.recordingSignal.reason, /noisy for 30 of 91 seconds/);

  // The allowance scales with block length instead of shrinking.
  const shortBlock = evaluate({ total: 20, good: 16, noisy: 4, notWorn: 0, worstPoorSignal: 80 });
  const longBlock = evaluate({ total: 181, good: 154, noisy: 27, notWorn: 0, worstPoorSignal: 80 });
  assert.equal(shortBlock.recordingSignal.acceptable, true);
  assert.equal(longBlock.recordingSignal.acceptable, true);
  assert.ok(
    longBlock.recordingSignal.noisyAllowance > shortBlock.recordingSignal.noisyAllowance,
    'a longer block must not be held to a stricter absolute allowance',
  );

  // Short blocks keep the absolute floor rather than a tiny proportional share.
  assert.equal(shortBlock.recordingSignal.noisyAllowance, 4);

  // A headset that came off is still rejected outright, at any duration.
  const notWorn = evaluate({ total: 91, good: 88, noisy: 2, notWorn: 1, worstPoorSignal: 200 });
  assert.equal(notWorn.recordingSignal.acceptable, false);
  assert.match(notWorn.recordingSignal.reason, /not worn for 1 of 91 seconds/);

  // No live status stream at all remains unacceptable and is named as such.
  const noStatus = evaluate({ total: 0, good: 0, noisy: 0, notWorn: 0, worstPoorSignal: null });
  assert.equal(noStatus.recordingSignal.acceptable, false);
  assert.match(noStatus.recordingSignal.reason, /No live signal status samples/);
}
