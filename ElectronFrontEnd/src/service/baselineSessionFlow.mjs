import {
  deleteBaselineRecording,
  loadBaselineRecording,
} from './recordingStore.mjs';

export const BASELINE_PHASE_REQUEST_KEY = 'requestedBaselinePhase';

export const BASELINE_RECORDING_PHASE = Object.freeze({
  EYES_CLOSED: 'eyes_closed',
  EYES_OPEN: 'eyes_open',
});

const STORAGE_KEY_BY_PHASE = Object.freeze({
  [BASELINE_RECORDING_PHASE.EYES_CLOSED]: 'calibrationData_eyes_closed',
  [BASELINE_RECORDING_PHASE.EYES_OPEN]: 'calibrationData_eyes_open',
});

const SUMMARY_KEY_BY_PHASE = Object.freeze({
  [BASELINE_RECORDING_PHASE.EYES_CLOSED]: 'eyesClosed',
  [BASELINE_RECORDING_PHASE.EYES_OPEN]: 'eyesOpen',
});

function readStorageValue(storage, key) {
  try {
    return storage?.getItem?.(key) ?? null;
  } catch {
    return null;
  }
}

function readJson(storage, key, fallback) {
  const raw = readStorageValue(storage, key);
  if (raw == null) return fallback;

  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function deriveProtocolSession(storage) {
  if (readStorageValue(storage, 'hasSessionThree') === 'true') return 3;
  if (readStorageValue(storage, 'hasAdvancedBooking') === 'true') return 2;
  return 1;
}

export function resolveBaselineEntry(storage) {
  const requestedPhase = readStorageValue(storage, BASELINE_PHASE_REQUEST_KEY);
  const requestedCheckpoint = Object.values(BASELINE_RECORDING_PHASE).includes(requestedPhase);
  const recordingPhase = requestedCheckpoint
    ? requestedPhase
    : BASELINE_RECORDING_PHASE.EYES_CLOSED;

  return {
    protocolSession: deriveProtocolSession(storage),
    recordingPhase,
    isEyesOpenCheckpoint: recordingPhase === BASELINE_RECORDING_PHASE.EYES_OPEN,
    isRequestedCheckpoint: requestedCheckpoint,
  };
}

export function readBaselineSummary(storage) {
  const summary = readJson(storage, 'baselineCalibration', {});
  return summary && typeof summary === 'object' && !Array.isArray(summary) ? summary : {};
}

export function mergeCompletedBaselinePhase(
  existingSummary,
  {
    recordingPhase,
    sampleCount,
    protocolSession,
    batteryVersion,
    recordingMetadata = {},
  },
) {
  const summaryKey = SUMMARY_KEY_BY_PHASE[recordingPhase];
  if (!summaryKey) return { ...(existingSummary || {}) };

  const safeSummary = existingSummary && typeof existingSummary === 'object' && !Array.isArray(existingSummary)
    ? existingSummary
    : {};
  const existingPhase = safeSummary[summaryKey] && typeof safeSummary[summaryKey] === 'object'
    ? safeSummary[summaryKey]
    : {};

  return {
    ...safeSummary,
    [summaryKey]: {
      ...existingPhase,
      ...(recordingMetadata && typeof recordingMetadata === 'object' ? recordingMetadata : {}),
      raw_sample_count: Math.max(0, Number(sampleCount) || 0),
      protocol_session: protocolSession,
      battery_version: batteryVersion || null,
      completed: true,
    },
  };
}

export async function isBaselinePhaseComplete(
  storage,
  recordingPhase,
  protocolSession,
  batteryVersion = null,
) {
  const summaryKey = SUMMARY_KEY_BY_PHASE[recordingPhase];
  if (!STORAGE_KEY_BY_PHASE[recordingPhase] || !summaryKey) return false;

  const record = await loadBaselineRecording(recordingPhase, storage);
  const samples = record?.samples;
  const phaseSummary = readBaselineSummary(storage)[summaryKey];
  const recordMetadata = record?.metadata && typeof record.metadata === 'object'
    ? record.metadata
    : null;
  const manifestRecordingId = phaseSummary?.recording_id || null;
  const recordRecordingId = recordMetadata?.recording_id || null;
  const recordingIdentityMatches = (
    manifestRecordingId == null && recordRecordingId == null
  ) || (
    manifestRecordingId != null
    && recordRecordingId != null
    && manifestRecordingId === recordRecordingId
  );

  return (
    Array.isArray(samples)
    && samples.length > 0
    && phaseSummary?.completed === true
    && recordMetadata?.completed === true
    && Number(phaseSummary?.protocol_session) === Number(protocolSession)
    && Number(recordMetadata?.protocol_session) === Number(protocolSession)
    && (batteryVersion == null || phaseSummary?.battery_version === batteryVersion)
    && (batteryVersion == null || recordMetadata?.battery_version === batteryVersion)
    && recordingIdentityMatches
  );
}

export async function invalidateBaselinePhase(storage, recordingPhase) {
  const storageKey = STORAGE_KEY_BY_PHASE[recordingPhase];
  const summaryKey = SUMMARY_KEY_BY_PHASE[recordingPhase];
  if (!storageKey || !summaryKey) return readBaselineSummary(storage);

  // Delete the durable source of truth before clearing its manifest. Failure is
  // surfaced so callers cannot claim a re-recording is required while the old
  // baseline still resolves as complete.
  await deleteBaselineRecording(recordingPhase, storage);

  const nextSummary = { ...readBaselineSummary(storage) };
  delete nextSummary[summaryKey];
  try {
    storage?.setItem?.('baselineCalibration', JSON.stringify(nextSummary));
  } catch {
    // Completion also requires a durable record, which has already been
    // deleted, so a stale manifest cannot make the phase valid again.
  }
  return nextSummary;
}
