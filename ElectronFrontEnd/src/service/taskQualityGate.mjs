import {
  clearTaskRecordings,
  loadBaselineRecording,
  loadTaskRecording,
  saveTaskRecording,
} from './recordingStore.mjs';
import { PROTOCOL_PROFILE_METADATA } from '../components/tasks/optimizedBatteryProfile.mjs';

const PASSING_CONFIDENCE = new Set(['weak', 'moderate', 'strong']);
const MIN_USABLE_FEATURES = 2;
// The live status stream carries one sample per second, so a task contributes
// as many samples as it lasts. The proportional ratio is the tolerance; the
// absolute count is only a floor, so short blocks still get a usable allowance.
// Combining them the other way round (whichever is smaller) would make the
// ratio unreachable and, worse, tighten the gate as tasks grow longer.
const MAX_NOISY_RECORDING_RATIO = 0.15;
const MIN_NOISY_RECORDING_ALLOWANCE = 4;

function noisyEventAllowance(total) {
  return Math.max(MIN_NOISY_RECORDING_ALLOWANCE, Math.floor(total * MAX_NOISY_RECORDING_RATIO));
}
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

function baselineMetadata(storage) {
  const summary = readJson(storage, 'baselineCalibration', {});
  if (!summary || typeof summary !== 'object' || Array.isArray(summary)) return null;
  const metadata = {};
  if (summary.eyesClosed && typeof summary.eyesClosed === 'object') {
    metadata.eyes_closed = summary.eyesClosed;
  }
  if (summary.eyesOpen && typeof summary.eyesOpen === 'object') {
    metadata.eyes_open = summary.eyesOpen;
  }
  return Object.keys(metadata).length > 0 ? metadata : null;
}

export function evaluateRecordingSignal(signalStats = null) {
  const total = Number(signalStats?.total || 0);
  const noisyCount = Number(signalStats?.noisy || 0);
  const notWornCount = Number(signalStats?.notWorn || 0);
  const goodCount = Number(signalStats?.good || 0);
  const noisyRatio = total > 0 ? noisyCount / total : 0;
  const noisyAllowance = noisyEventAllowance(total);
  const acceptable = (
    total > 0 && notWornCount === 0 && noisyCount <= noisyAllowance
  );
  let reason = 'Signal stable during recording';
  if (total === 0) {
    reason = 'No live signal status samples were available during recording';
  } else if (notWornCount > 0) {
    reason = `Signal was not worn for ${notWornCount} of ${total} seconds during the task recording`;
  } else if (noisyCount > noisyAllowance) {
    reason = `Signal was noisy for ${noisyCount} of ${total} seconds during the task recording, above the ${noisyAllowance}-second allowance`;
  }

  return {
    acceptable,
    total,
    goodCount,
    noisyCount,
    notWornCount,
    noisyRatio,
    noisyAllowance,
    worstPoorSignal: signalStats?.worstPoorSignal ?? null,
    reason,
  };
}
export async function buildSingleTaskAnalysisPayload(
  taskId,
  samples = null,
  storage = globalThis.sessionStorage,
  metadata = undefined,
) {
  const stored = Array.isArray(samples) ? null : await loadTaskRecording(taskId, storage);
  const resolvedSamples = Array.isArray(samples) ? samples : (stored?.samples || []);
  const resolvedMetadata = metadata === undefined ? (stored?.metadata ?? null) : metadata;
  const [eyesClosedRecord, eyesOpenRecord] = await Promise.all([
    loadBaselineRecording('eyes_closed', storage),
    loadBaselineRecording('eyes_open', storage),
  ]);
  const payload = {
    baseline: {
      eyes_closed: Array.isArray(eyesClosedRecord?.samples) ? eyesClosedRecord.samples : [],
      eyes_open: Array.isArray(eyesOpenRecord?.samples) ? eyesOpenRecord.samples : [],
    },
    tasks: {
      [taskId]: resolvedSamples,
    },
    protocol_profile: PROTOCOL_PROFILE_METADATA,
  };

  const manifestMetadata = baselineMetadata(storage) || {};
  const resolvedBaselineMetadata = {
    ...(eyesClosedRecord?.metadata || manifestMetadata.eyes_closed
      ? { eyes_closed: eyesClosedRecord?.metadata || manifestMetadata.eyes_closed }
      : {}),
    ...(eyesOpenRecord?.metadata || manifestMetadata.eyes_open
      ? { eyes_open: eyesOpenRecord?.metadata || manifestMetadata.eyes_open }
      : {}),
  };
  if (Object.keys(resolvedBaselineMetadata).length > 0) {
    payload.baseline_metadata = resolvedBaselineMetadata;
  }

  if (resolvedMetadata != null) {
    payload.task_metadata = { [taskId]: resolvedMetadata };
  }
  return payload;
}

export function evaluateTaskQuality(analysis, taskId, { signalStats = null } = {}) {
  const exportBlock = analysis?.neuroprofile_feature_export || {};
  const task = findTask(exportBlock, taskId);
  const perTask = analysis?.per_task?.[taskId] || null;
  const signalQuality = task?.signal_quality || {};
  const taskSummary = task?.task_summary || {};
  const usableFeatureCount = Number(signalQuality.usable_feature_count || 0);
  const reportableFeatureRows = countReportableRows(exportBlock, taskId);
  const taskConfidence = taskSummary.confidence || 'insufficient';
  const recordingSignal = evaluateRecordingSignal(signalStats);
  const taskQc = perTask?.task_qc || task?.task_qc || {};
  const baselineQc = perTask?.baseline_qc || task?.baseline_qc || {};
  const invalidReasons = Array.isArray(perTask?.invalid_reasons)
    ? perTask.invalid_reasons
    : (Array.isArray(task?.invalid_reasons) ? task.invalid_reasons : []);
  const backendScorable = (perTask?.scorable ?? task?.scorable) === true;
  const contiguousCleanSufficient = taskQc.meets_contiguous_clean_minimum === true;
  const matchedBaselineSufficient = baselineQc.meets_contiguous_clean_minimum !== false;
  const evidenceSufficient = (
    PASSING_CONFIDENCE.has(taskConfidence) ||
    usableFeatureCount >= MIN_USABLE_FEATURES ||
    reportableFeatureRows >= MIN_USABLE_FEATURES
  );
  const sufficient = (
    recordingSignal.acceptable
    && backendScorable
    && contiguousCleanSufficient
    && matchedBaselineSufficient
  );

  return {
    sufficient,
    usableFeatureCount,
    rejectedFeatureCount: Number(signalQuality.rejected_feature_count || 0),
    reportableFeatureRows,
    evidenceSufficient,
    taskConfidence,
    qualityLevel: signalQuality.quality_level || 'unknown',
    notes: Array.isArray(signalQuality.notes) ? signalQuality.notes : [],
    recordingSignal,
    backendScorable,
    contiguousCleanSufficient,
    matchedBaselineSufficient,
    taskQc,
    baselineQc,
    invalidReasons,
    needsBaselineRepeat: invalidReasons.some((reason) => String(reason).includes('_baseline')),
  };
}


export function isRepeatSignalReady({ isGoodSignal = false, goodSignalStableMs = 0 } = {}) {
  return Boolean(isGoodSignal) && Number(goodSignalStableMs || 0) >= REPEAT_SIGNAL_STABLE_MS;
}
export function resolveTaskQualityOutcome(quality) {
  if (quality?.sufficient) return 'accept';
  return 'force_repeat';
}

export async function commitTaskAttempt(
  taskId,
  samples,
  storage = globalThis.sessionStorage,
  metadata = null,
) {
  await saveTaskRecording(taskId, samples, metadata, storage);
  const storedCompleted = readJson(storage, 'completedTasks', []);
  const completed = Array.isArray(storedCompleted) ? storedCompleted : [];
  const updated = [...new Set([...completed, taskId])];
  storage.setItem('completedTasks', JSON.stringify(updated));
  return updated;
}

export async function loadTaskAttempt(taskId, storage = globalThis.sessionStorage) {
  return loadTaskRecording(taskId, storage);
}

export async function clearTaskAttempts(taskIds = null, storage = globalThis.sessionStorage) {
  await clearTaskRecordings(taskIds, storage);
}
