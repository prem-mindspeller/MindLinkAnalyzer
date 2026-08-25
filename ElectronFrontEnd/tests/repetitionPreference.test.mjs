import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  REPETITION_PREFERENCE_KEY,
  canDisableRepetition,
  clearRepetitionPreference,
  isRepetitionDisabled,
  saveRepetitionPreference,
} from '../src/service/repetitionPreference.mjs';
import {
  EYES_OPEN_BASELINE_CHECKPOINT,
  carriedOverTaskIds,
  firstSessionForTask,
  taskIdsForSession,
  taskSequenceForSession,
} from '../src/components/tasks/optimizedBatteryConfig.mjs';
import {
  expectedTaskIdsForSession,
  missingExpectedTaskIds,
  requiredBaselineConditionsForSession,
} from '../src/service/analysisReadiness.mjs';
import { BATTERY_RUN_STORAGE_KEYS } from '../src/service/batteryRunCleanup.mjs';

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  };
}

// ── The choice exists only from Session 2 onward ────────────────────────────
assert.equal(canDisableRepetition(1), false);
assert.equal(canDisableRepetition(2), true);
assert.equal(canDisableRepetition(3), true);

// ── Off by default ──────────────────────────────────────────────────────────
assert.equal(isRepetitionDisabled(createStorage(), 2), false);
assert.equal(isRepetitionDisabled(createStorage(), 3), false);

// ── Confirming the waiver persists it for that session ──────────────────────
const session2 = createStorage();
assert.equal(saveRepetitionPreference(true, 2, session2), true);
assert.equal(isRepetitionDisabled(session2, 2), true);

// ── Session 1 can never waive repetition, even if asked to ──────────────────
const session1 = createStorage();
assert.equal(saveRepetitionPreference(true, 1, session1), false);
assert.equal(session1.getItem(REPETITION_PREFERENCE_KEY), null);
assert.equal(isRepetitionDisabled(session1, 1), false);

// ── A waiver never leaks across protocol sessions ───────────────────────────
assert.equal(isRepetitionDisabled(session2, 3), false);
assert.equal(isRepetitionDisabled(session2, 1), false);

// ── A stale value from another session is ignored, not migrated ─────────────
const stale = createStorage({
  [REPETITION_PREFERENCE_KEY]: JSON.stringify({ disabled: true, protocol_session: 2 }),
});
assert.equal(isRepetitionDisabled(stale, 3), false);
assert.equal(isRepetitionDisabled(stale, 2), true);

// ── Malformed values fall back to the stricter default ──────────────────────
assert.equal(isRepetitionDisabled(createStorage({ [REPETITION_PREFERENCE_KEY]: 'not json' }), 2), false);
assert.equal(isRepetitionDisabled(createStorage({ [REPETITION_PREFERENCE_KEY]: 'true' }), 2), false);

// ── Turning repetition back on clears the waiver ────────────────────────────
clearRepetitionPreference(session2);
assert.equal(session2.getItem(REPETITION_PREFERENCE_KEY), null);
assert.equal(isRepetitionDisabled(session2, 2), false);
assert.equal(saveRepetitionPreference(false, 2, session2), false);

// ── A storage that rejects writes reports repetition as still enabled ───────
const readOnly = {
  getItem() { return null; },
  setItem() { throw new Error('quota exceeded'); },
  removeItem() {},
};
assert.equal(saveRepetitionPreference(true, 2, readOnly), false);

// ── Disabling repetition drops the carried-forward tasks ────────────────────
// Session 1 introduces every task it runs, so there is nothing to carry over.
assert.deepEqual(
  taskIdsForSession('session_1', { newTasksOnly: true }).sort(),
  taskIdsForSession('session_1').sort(),
);
assert.deepEqual(carriedOverTaskIds('session_1'), []);

// Session 2 runs 9 tasks; 5 of them are its own, 4 repeat Session 1.
assert.equal(taskIdsForSession('session_2').length, 9);
assert.equal(taskIdsForSession('session_2', { newTasksOnly: true }).length, 5);
assert.equal(carriedOverTaskIds('session_2').length, 4);
for (const taskId of taskIdsForSession('session_2', { newTasksOnly: true })) {
  assert.equal(firstSessionForTask(taskId), 2, `${taskId} is not introduced in session 2`);
}
for (const taskId of carriedOverTaskIds('session_2')) {
  assert.equal(firstSessionForTask(taskId), 1, `${taskId} is not carried over into session 2`);
}

// Session 3 runs 12 tasks; only 3 are its own.
assert.equal(taskIdsForSession('session_3').length, 12);
assert.equal(taskIdsForSession('session_3', { newTasksOnly: true }).length, 3);
assert.equal(carriedOverTaskIds('session_3').length, 9);

// The matched eyes-open reference belongs to this run, not to a repeated task,
// so it survives the filter.
assert.ok(taskSequenceForSession('session_2', { newTasksOnly: true })
  .includes(EYES_OPEN_BASELINE_CHECKPOINT));

// Omitting the option keeps the full repeated battery.
assert.deepEqual(taskSequenceForSession('session_2'), taskSequenceForSession('session_2', {}));

// ── Analysis stops expecting the tasks that are not repeated ────────────────
const session2New = taskIdsForSession('session_2', { newTasksOnly: true });
assert.deepEqual(
  missingExpectedTaskIds(session2New, 'session_2', { newTasksOnly: true }),
  [],
);
// The same completed set is still incomplete for a normal repeated run.
assert.deepEqual(
  missingExpectedTaskIds(session2New, 'session_2').sort(),
  carriedOverTaskIds('session_2').sort(),
);
assert.deepEqual(expectedTaskIdsForSession('session_2', { newTasksOnly: true }).sort(), session2New.sort());

// Baseline requirements follow the reduced set rather than the full battery.
assert.ok(requiredBaselineConditionsForSession('session_2', { newTasksOnly: true }).length > 0);

// ── The preference is cleared with the rest of the run ──────────────────────
assert.ok(BATTERY_RUN_STORAGE_KEYS.includes(REPETITION_PREFERENCE_KEY));

// ── Page contract: toggle, popup and single-presentation wiring ─────────────
const srcDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const taskSelectionSource = readFileSync(join(srcDir, 'pages', 'TaskSelection.jsx'), 'utf8');

// The toggle is gated on the session tier, not rendered unconditionally.
assert.match(taskSelectionSource, /repetitionChoiceAvailable && \(/);
assert.match(taskSelectionSource, /canDisableRepetition\(protocolSession\)/);
// Enabling the waiver goes through the popup; the popup writes the preference.
assert.match(taskSelectionSource, /setRepetitionDialogOpen\(true\)/);
assert.match(taskSelectionSource, /saveRepetitionPreference\(true, protocolSession, sessionStorage\)/);
// Cancelling leaves repetition enabled and writes nothing.
assert.match(taskSelectionSource, /cancelDisableRepetition = useCallback\(\(\) => setRepetitionDialogOpen\(false\)/);
// The preference drives the task set, which is the whole mechanism.
assert.match(taskSelectionSource, /newTasksOnly: repetitionDisabled/);
assert.match(taskSelectionSource, /taskIdsForSession\(sessionDepth, taskScope\)/);
assert.match(taskSelectionSource, /taskSequenceForSession\(sessionDepth, taskScope\)/);
// The booking tier still labels rows independently of the repetition choice.
assert.match(taskSelectionSource, /const bookedTaskIds = useMemo\(\) => taskIdsForSession\(sessionDepth\), \[sessionDepth\]\)|bookedTaskIds\.includes\(item\)/);
// Signal-quality repeats are a separate mechanism and stay untouched.
assert.match(taskSelectionSource, /setQualityDialog\(\{ taskId, quality, mode: 'force_repeat' \}\)/);
assert.doesNotMatch(taskSelectionSource, /annotateRepetitionWaiver|accept_without_repeat/);

const analysisSource = readFileSync(join(srcDir, 'service', 'analysisService.js'), 'utf8');
// Analysis must not demand tasks this run was never going to repeat.
assert.match(analysisSource, /isRepetitionDisabled\(storage, sessionNumberForDepth\(sessionDepth\)\)/);
assert.match(analysisSource, /missingExpectedTaskIds\(completedIds, sessionDepth, taskScope\)/);
assert.match(analysisSource, /repetition_disabled: newTasksOnly/);

const locale = JSON.parse(readFileSync(join(srcDir, 'locales', 'en.json'), 'utf8'));
for (const key of [
  'repetitionToggleLabel',
  'repetitionConfirmTitle',
  'repetitionConfirmBody',
  'repetitionWhyTitle',
  'repetitionCancel',
  'repetitionConfirm',
  'repetitionScopeNote',
]) {
  assert.ok(locale.taskSelection?.[key], `en.json missing taskSelection.${key}`);
}
