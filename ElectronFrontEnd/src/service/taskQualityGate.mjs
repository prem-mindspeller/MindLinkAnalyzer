const PASSING_CONFIDENCE = new Set(['weak', 'moderate', 'strong']);
const MIN_USABLE_FEATURES = 2;
const MAX_NOISY_RECORDING_RATIO = 0.15;
const MAX_NOISY_RECORDING_EVENTS = 4;
export const REPEAT_SIGNAL_STABLE_MS = 5000;

function readJson(storage, key, fallback) {
  try {
    const raw = storage.getItem(key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function findTask(exportBlock, taskId) {
  const tasks = Array.isArray(exportBlock?.tasks) ? exportBlock.tasks : [];
  return tasks.find((task) => {
    const rawLabels = Array.isArray(task.raw_task_labels) ? task.raw_task_labels : [];
    return task.canonical_task_id === taskId || rawLabels.includes(taskId);
  }) || null;
}

function countReportableRows(exportBlock, taskId) {
  const rows = Array.isArray(exportBlock?.feature_rows) ? exportBlock.feature_rows : [];
  return rows.filter((row) => {
    const rowTask = row.canonical_task_id || row.task_id;
    return rowTask === taskId && row.passes_neuroprofile_gate === true;
  }).length;
}

function evaluateRecordingSignal(signalStats = null) {
  const total = Number(signalStats?.total || 0);
  const noisyCount = Number(signalStats?.noisy || 0);
  const notWornCount = Number(signalStats?.notWorn || 0);
  const goodCount = Number(signalStats?.good || 0);
  const noisyRatio = total > 0 ? noisyCount / total : 0;
  const acceptable = (
    total === 0 || (
      notWornCount === 0 &&
      noisyCount <= MAX_NOISY_RECORDING_EVENTS &&
      noisyRatio <= MAX_NOISY_RECORDING_RATIO
    )
  );
  let reason = 'Signal stable during recording';
  if (notWornCount > 0) {
    reason = 'Signal was not worn during the task recording';
  } else if (noisyCount > MAX_NOISY_RECORDING_EVENTS || noisyRatio > MAX_NOISY_RECORDING_RATIO) {
    reason = 'Signal was noisy too often during the task recording';
  } else if (total === 0) {
    reason = 'No live signal status samples were available during recording';
  }

  return {
    acceptable,
    total,
    goodCount,
    noisyCount,
    notWornCount,
    noisyRatio,
    worstPoorSignal: signalStats?.worstPoorSignal ?? null,
    reason,
  };
}

export function buildSingleTaskAnalysisPayload(taskId, samples, storage = sessionStorage) {
  return {
    baseline: {
      eyes_closed: readJson(storage, 'calibrationData_eyes_closed', []),
      eyes_open: readJson(storage, 'calibrationData_eyes_open', []),
    },
    tasks: {
      [taskId]: Array.isArray(samples) ? samples : [],
    },
  };
}

export function evaluateTaskQuality(analysis, taskId, { signalStats = null } = {}) {
  const exportBlock = analysis?.neuroprofile_feature_export || {};
  const task = findTask(exportBlock, taskId);
  const signalQuality = task?.signal_quality || {};
  const taskSummary = task?.task_summary || {};
  const usableFeatureCount = Number(signalQuality.usable_feature_count || 0);
  const reportableFeatureRows = countReportableRows(exportBlock, taskId);
  const taskConfidence = taskSummary.confidence || 'insufficient';
  const recordingSignal = evaluateRecordingSignal(signalStats);
  const evidenceSufficient = (
    PASSING_CONFIDENCE.has(taskConfidence) ||
    usableFeatureCount >= MIN_USABLE_FEATURES ||
    reportableFeatureRows >= MIN_USABLE_FEATURES
  );
  const sufficient = recordingSignal.acceptable && evidenceSufficient;

  return {
    sufficient,
    usableFeatureCount,
    rejectedFeatureCount: Number(signalQuality.rejected_feature_count || 0),
    reportableFeatureRows,
    taskConfidence,
    qualityLevel: signalQuality.quality_level || 'unknown',
    notes: Array.isArray(signalQuality.notes) ? signalQuality.notes : [],
    recordingSignal,
  };
}

export function isRepeatSignalReady({ isGoodSignal = false, goodSignalStableMs = 0 } = {}) {
  return Boolean(isGoodSignal) && Number(goodSignalStableMs || 0) >= REPEAT_SIGNAL_STABLE_MS;
}

export function resolveTaskQualityOutcome(quality, { forcedRepeatUsed = false } = {}) {
  if (quality?.sufficient) return 'accept';
  return forcedRepeatUsed ? 'accept_with_warning' : 'force_repeat';
}

export function commitTaskAttempt(taskId, samples, storage = sessionStorage) {
  storage.setItem(`taskData_${taskId}`, JSON.stringify(Array.isArray(samples) ? samples : []));
  const completed = readJson(storage, 'completedTasks', []);
  const updated = [...new Set([...completed, taskId])];
  storage.setItem('completedTasks', JSON.stringify(updated));
  return updated;
}
