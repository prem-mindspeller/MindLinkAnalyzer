import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  BATTERY_RUN_STORAGE_KEYS,
  clearBatteryRunData,
} from '../src/service/batteryRunCleanup.mjs';
import {
  loadBaselineRecording,
  loadTaskRecording,
  RECORDING_STORE_SESSION_KEY,
  saveBaselineRecording,
  saveTaskRecording,
} from '../src/service/recordingStore.mjs';

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    get length() {
      return values.size;
    },
    key(index) {
      return [...values.keys()][index] ?? null;
    },
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

const storage = createStorage({
  jwtToken: 'auth-token-is-owned-by-login-service',
  loggedInUser: 'first@example.test',
  language: 'nl',
  region: 'nl',
  partnerId: 'participant-one',
  hasAdvancedBooking: 'true',
  hasSessionThree: 'false',
  userData: JSON.stringify({ initial_protocol: true }),
  selectedPathway: 'personal',
  calibrationData_eyes_closed: JSON.stringify([{ fp1: 1 }]),
  calibrationData_eyes_open: JSON.stringify([{ fp1: 2 }]),
  baselineCalibration: JSON.stringify({
    eyesClosed: { completed: true },
    eyesOpen: { completed: true },
  }),
  requestedBaselinePhase: 'eyes_open',
  taskBatteryVersion: 'optimized-v1',
  taskBatteryProtocolSession: '2',
  completedTasks: JSON.stringify(['shared_task']),
  taskData_interrupted_legacy_task: JSON.stringify([{ fp1: 99 }]),
});

// First participant/run: persist both a committed task and an interrupted task
// that deliberately does not appear in completedTasks.
await saveTaskRecording('shared_task', [{ owner: 'first' }], null, storage);
await saveTaskRecording('interrupted_task', [{ owner: 'first-orphan' }], null, storage);
await saveBaselineRecording(
  'eyes_closed',
  [{ owner: 'first-baseline' }],
  { completed: true, protocol_session: 2, battery_version: 'optimized-v1' },
  storage,
);
const firstSessionId = storage.getItem(RECORDING_STORE_SESSION_KEY);
assert.ok(firstSessionId);

await clearBatteryRunData(storage);

for (const key of BATTERY_RUN_STORAGE_KEYS) {
  assert.equal(storage.getItem(key), null, `${key} survived first-run cleanup`);
}
assert.equal(storage.getItem('taskData_interrupted_legacy_task'), null);
assert.equal(storage.getItem('jwtToken'), 'auth-token-is-owned-by-login-service');
assert.equal(storage.getItem('loggedInUser'), 'first@example.test');
assert.equal(storage.getItem('language'), 'nl');
assert.equal(storage.getItem('region'), 'nl');

// Second participant/run reuses the same browser Storage object and the same
// task ID. It must receive a new recording namespace and only its own samples.
storage.setItem('loggedInUser', 'second@example.test');
storage.setItem('completedTasks', JSON.stringify([]));
await saveTaskRecording('shared_task', [{ owner: 'second' }], null, storage);
const secondSessionId = storage.getItem(RECORDING_STORE_SESSION_KEY);
assert.ok(secondSessionId);
assert.notEqual(secondSessionId, firstSessionId);
assert.deepEqual(
  (await loadTaskRecording('shared_task', storage))?.samples,
  [{ owner: 'second' }],
);
assert.equal(await loadTaskRecording('interrupted_task', storage), null);
assert.equal(await loadBaselineRecording('eyes_closed', storage), null);

await clearBatteryRunData(storage);
assert.equal(storage.getItem(RECORDING_STORE_SESSION_KEY), null);
assert.equal(storage.getItem('completedTasks'), null);

// Both user-facing exit paths must await the one centralized cleanup owner.
const srcDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const serviceDir = join(srcDir, 'service');
const loginServiceSource = readFileSync(join(serviceDir, 'loginService.js'), 'utf8');
const headerSource = readFileSync(join(srcDir, 'components', 'header.jsx'), 'utf8');
const uploadSource = readFileSync(join(srcDir, 'pages', 'upload.jsx'), 'utf8');

assert.match(loginServiceSource, /await clearBatteryRunData\(sessionStorage\)/);
assert.match(loginServiceSource, /finally\s*\{[\s\S]*removeItem\('jwtToken'\)[\s\S]*app:logout/);
assert.match(headerSource, /await loginService\.logout\(\)/);
assert.match(uploadSource, /await loginService\.logout\(\)/);
assert.doesNotMatch(uploadSource, /clearTaskAttempts/);
