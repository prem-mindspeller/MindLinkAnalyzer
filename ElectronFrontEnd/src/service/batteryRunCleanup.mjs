import {
  clearRecordingSession,
  RECORDING_STORE_SESSION_KEY,
} from './recordingStore.mjs';
import { BASELINE_PHASE_REQUEST_KEY } from './baselineSessionFlow.mjs';
import { REPETITION_PREFERENCE_KEY } from './repetitionPreference.mjs';

export const BATTERY_RUN_STORAGE_KEYS = Object.freeze([
  'calibrationData_eyes_closed',
  'calibrationData_eyes_open',
  'baselineCalibration',
  'completedTasks',
  BASELINE_PHASE_REQUEST_KEY,
  'taskBatteryVersion',
  'taskBatteryProtocolSession',
  REPETITION_PREFERENCE_KEY,
  RECORDING_STORE_SESSION_KEY,
  'selectedPathway',
  // These values select a participant's protocol depth and must not cross a
  // logout boundary even though they are not EEG data themselves.
  'partnerId',
  'hasAdvancedBooking',
  'hasSessionThree',
  'userData',
]);

function defaultStorage() {
  try {
    return globalThis.sessionStorage || null;
  } catch {
    return null;
  }
}

function removeStorageValue(storage, key) {
  try {
    storage?.removeItem?.(key);
  } catch {
    // Continue clearing the remaining run-scoped values. A failed custom
    // Storage implementation must not prevent cleanup of unrelated keys.
  }
}

function storageKeys(storage) {
  const keys = [];
  try {
    const length = Number(storage?.length || 0);
    if (typeof storage?.key === 'function') {
      for (let index = 0; index < length; index += 1) {
        const key = storage.key(index);
        if (typeof key === 'string') keys.push(key);
      }
    }
  } catch {
    // Known keys are still removed below when enumeration is unavailable.
  }
  return keys;
}

/**
 * Clear all participant- and run-scoped task-battery state. Authentication
 * tokens and language/region preferences deliberately remain the caller's
 * responsibility so logout keeps its existing ownership of auth semantics.
 */
export async function clearBatteryRunData(storage = defaultStorage()) {
  let recordingCleanupError = null;
  try {
    await clearRecordingSession(storage);
  } catch (error) {
    recordingCleanupError = error;
  } finally {
    // Remove every known state marker and any pre-IndexedDB raw recording,
    // including interrupted attempts absent from completedTasks.
    for (const key of BATTERY_RUN_STORAGE_KEYS) removeStorageValue(storage, key);
    for (const key of storageKeys(storage)) {
      if (key.startsWith('taskData_')) removeStorageValue(storage, key);
    }
  }

  if (recordingCleanupError) throw recordingCleanupError;
}
