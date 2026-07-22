import assert from 'node:assert/strict';

import {
  expectedTaskIdsForSession,
  missingExpectedTaskIds,
  missingOrEmptyTaskRecordings,
  requiredBaselineConditionsForSession,
} from './analysisReadiness.mjs';

const sessionOne = expectedTaskIdsForSession('session_1');
const sessionTwo = expectedTaskIdsForSession('session_2');
const sessionThree = expectedTaskIdsForSession('session_3');

assert.equal(sessionOne.length, 4);
assert.equal(sessionTwo.length, 9);
assert.equal(sessionThree.length, 12);
assert.deepEqual(missingExpectedTaskIds(sessionOne, 'session_1'), []);
assert.deepEqual(
  missingExpectedTaskIds(sessionOne, 'session_2'),
  sessionTwo.filter((taskId) => !sessionOne.includes(taskId)),
);

const recordings = new Map(sessionOne.map((taskId) => [taskId, {
  taskId,
  samples: [{ fp1: 1, fp2: 2, o1: 3, o2: 4 }],
}]));
assert.deepEqual(missingOrEmptyTaskRecordings(sessionOne, recordings), []);

recordings.delete(sessionOne[0]);
recordings.set(sessionOne[1], { taskId: sessionOne[1], samples: [] });
assert.deepEqual(
  missingOrEmptyTaskRecordings(sessionOne, recordings),
  [sessionOne[0], sessionOne[1]],
);

// Duplicated completion IDs do not create duplicated analysis requirements.
assert.deepEqual(
  missingOrEmptyTaskRecordings([sessionOne[0], sessionOne[0]], new Map()),
  [sessionOne[0]],
);

assert.deepEqual(requiredBaselineConditionsForSession('session_1'), ['eyes_closed']);
assert.deepEqual(
  requiredBaselineConditionsForSession('session_2').sort(),
  ['eyes_closed', 'eyes_open'],
);
