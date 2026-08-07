import assert from 'node:assert/strict';

import {
  BASELINE_RECORDING_PHASE,
  deriveProtocolSession,
  invalidateBaselinePhase,
  isBaselinePhaseComplete,
  mergeCompletedBaselinePhase,
  resolveBaselineEntry,
} from './baselineSessionFlow.mjs';
import {
  loadBaselineRecording,
  saveBaselineRecording,
} from './recordingStore.mjs';

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

assert.equal(deriveProtocolSession(createStorage()), 1);
assert.equal(deriveProtocolSession(createStorage({ hasAdvancedBooking: 'true' })), 2);
assert.equal(deriveProtocolSession(createStorage({ hasSessionThree: 'true' })), 3);
assert.equal(deriveProtocolSession(createStorage({
  hasAdvancedBooking: 'true',
  hasSessionThree: 'true',
})), 3);

assert.deepEqual(resolveBaselineEntry(createStorage()), {
  protocolSession: 1,
  recordingPhase: BASELINE_RECORDING_PHASE.EYES_CLOSED,
  isEyesOpenCheckpoint: false,
  isRequestedCheckpoint: false,
});

assert.deepEqual(resolveBaselineEntry(createStorage({
  hasAdvancedBooking: 'true',
  requestedBaselinePhase: 'eyes_open',
})), {
  protocolSession: 2,
  recordingPhase: BASELINE_RECORDING_PHASE.EYES_OPEN,
  isEyesOpenCheckpoint: true,
  isRequestedCheckpoint: true,
});

assert.deepEqual(resolveBaselineEntry(createStorage({
  requestedBaselinePhase: 'eyes_closed',
})), {
  protocolSession: 1,
  recordingPhase: BASELINE_RECORDING_PHASE.EYES_CLOSED,
  isEyesOpenCheckpoint: false,
  isRequestedCheckpoint: true,
});

assert.equal(
  resolveBaselineEntry(createStorage({ requestedBaselinePhase: 'unsupported' })).recordingPhase,
  BASELINE_RECORDING_PHASE.EYES_CLOSED,
);

{
  const eyesClosed = { raw_sample_count: 25, protocol_session: 2, completed: true };
  const merged = mergeCompletedBaselinePhase(
    { eyesClosed, customMetadata: 'preserved' },
    {
      recordingPhase: BASELINE_RECORDING_PHASE.EYES_OPEN,
      sampleCount: 30,
      protocolSession: 2,
      batteryVersion: 'battery-v1',
      recordingMetadata: {
        sample_rate_hz: 500,
        transport_segments: [{ start_sample_index: 0, end_sample_index_exclusive: 30 }],
      },
    },
  );

  assert.deepEqual(merged.eyesClosed, eyesClosed);
  assert.equal(merged.eyesOpen.raw_sample_count, 30);
  assert.equal(merged.eyesOpen.protocol_session, 2);
  assert.equal(merged.eyesOpen.battery_version, 'battery-v1');
  assert.equal(merged.eyesOpen.sample_rate_hz, 500);
  assert.equal(merged.eyesOpen.transport_segments.length, 1);
  assert.equal(merged.customMetadata, 'preserved');
}

{
  const phaseMetadata = {
    raw_sample_count: 1,
    protocol_session: 3,
    battery_version: 'battery-v1',
    recording_id: 'ec-recording-1',
    completed: true,
  };
  const storage = createStorage({
    baselineCalibration: JSON.stringify({ eyesClosed: phaseMetadata }),
  });
  await saveBaselineRecording(
    BASELINE_RECORDING_PHASE.EYES_CLOSED,
    [{ raw: 1 }],
    phaseMetadata,
    storage,
  );

  assert.equal(await isBaselinePhaseComplete(storage, BASELINE_RECORDING_PHASE.EYES_CLOSED, 3, 'battery-v1'), true);
  assert.equal(await isBaselinePhaseComplete(storage, BASELINE_RECORDING_PHASE.EYES_CLOSED, 3, 'battery-v2'), false);
  assert.equal(await isBaselinePhaseComplete(storage, BASELINE_RECORDING_PHASE.EYES_CLOSED, 2, 'battery-v1'), false);
  assert.equal(await isBaselinePhaseComplete(storage, BASELINE_RECORDING_PHASE.EYES_OPEN, 3, 'battery-v1'), false);
}

{
  const legacyMetadata = {
    raw_sample_count: 1,
    protocol_session: 1,
    battery_version: 'legacy-battery',
    completed: true,
  };
  const storage = createStorage({
    calibrationData_eyes_closed: JSON.stringify([{ raw: 7 }]),
    baselineCalibration: JSON.stringify({ eyesClosed: legacyMetadata }),
  });

  assert.equal(await isBaselinePhaseComplete(
    storage,
    BASELINE_RECORDING_PHASE.EYES_CLOSED,
    1,
    'legacy-battery',
  ), true);
  assert.equal(storage.getItem('calibrationData_eyes_closed'), null);
  assert.deepEqual(
    (await loadBaselineRecording(BASELINE_RECORDING_PHASE.EYES_CLOSED, storage))?.metadata,
    legacyMetadata,
  );
}

{
  const eyesClosed = {
    raw_sample_count: 1,
    protocol_session: 2,
    battery_version: 'battery-v1',
    recording_id: 'ec-recording-2',
    completed: true,
  };
  const eyesOpen = {
    raw_sample_count: 1,
    protocol_session: 2,
    battery_version: 'battery-v1',
    recording_id: 'eo-recording-2',
    completed: true,
  };
  const storage = createStorage({
    baselineCalibration: JSON.stringify({
      eyesClosed,
      eyesOpen,
    }),
  });
  await saveBaselineRecording(BASELINE_RECORDING_PHASE.EYES_CLOSED, [{ raw: 1 }], eyesClosed, storage);
  await saveBaselineRecording(BASELINE_RECORDING_PHASE.EYES_OPEN, [{ raw: 2 }], eyesOpen, storage);

  const summary = await invalidateBaselinePhase(storage, BASELINE_RECORDING_PHASE.EYES_CLOSED);
  assert.equal(storage.getItem('calibrationData_eyes_closed'), null);
  assert.equal(summary.eyesClosed, undefined);
  assert.equal(summary.eyesOpen.completed, true);
  assert.equal(await loadBaselineRecording(BASELINE_RECORDING_PHASE.EYES_CLOSED, storage), null);
  assert.equal((await loadBaselineRecording(BASELINE_RECORDING_PHASE.EYES_OPEN, storage))?.samples.length, 1);
  assert.equal(await isBaselinePhaseComplete(storage, BASELINE_RECORDING_PHASE.EYES_CLOSED, 2), false);
}

// Neither side of the small-manifest/durable-record commit pair can claim
// completion on its own, and recording identities must agree.
{
  const metadata = {
    raw_sample_count: 1,
    protocol_session: 1,
    battery_version: 'battery-v1',
    recording_id: 'durable-only',
    completed: true,
  };
  const durableOnly = createStorage();
  await saveBaselineRecording(BASELINE_RECORDING_PHASE.EYES_CLOSED, [{ raw: 1 }], metadata, durableOnly);
  assert.equal(await isBaselinePhaseComplete(
    durableOnly,
    BASELINE_RECORDING_PHASE.EYES_CLOSED,
    1,
    'battery-v1',
  ), false);

  const summaryOnly = createStorage({
    baselineCalibration: JSON.stringify({ eyesClosed: metadata }),
  });
  assert.equal(await isBaselinePhaseComplete(
    summaryOnly,
    BASELINE_RECORDING_PHASE.EYES_CLOSED,
    1,
    'battery-v1',
  ), false);

  durableOnly.setItem('baselineCalibration', JSON.stringify({
    eyesClosed: { ...metadata, recording_id: 'different-attempt' },
  }));
  assert.equal(await isBaselinePhaseComplete(
    durableOnly,
    BASELINE_RECORDING_PHASE.EYES_CLOSED,
    1,
    'battery-v1',
  ), false);
}
