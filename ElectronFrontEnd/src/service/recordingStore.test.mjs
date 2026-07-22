import assert from 'node:assert/strict';

import {
  clearTaskRecordings,
  deleteBaselineRecording,
  deleteTaskRecording,
  loadBaselineRecording,
  loadBaselineSamples,
  loadTaskRecording,
  loadTaskSamples,
  RECORDING_STORE_SESSION_KEY,
  saveBaselineRecording,
  saveTaskRecording,
} from './recordingStore.mjs';
import { commitTaskAttempt } from './taskQualityGate.mjs';

function createStorage(initial = {}, { maxValueLength = Infinity } = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      const serialized = String(value);
      if (serialized.length > maxValueLength) throw new Error('QuotaExceededError');
      data.set(key, serialized);
    },
    removeItem(key) {
      data.delete(key);
    },
  };
}

{
  const storage = createStorage({}, { maxValueLength: 100 });
  const samples = Array.from({ length: 2_000 }, (_, index) => ({
    fp1: index,
    fp2: -index,
    o1: index + 1,
    o2: -index - 1,
  }));
  const metadata = {
    formId: 'parallel-a',
    markers: [{ type: 'task_start', sampleIndex: 0 }],
  };

  await saveTaskRecording('large_task', samples, metadata, storage);

  assert.ok(storage.getItem(RECORDING_STORE_SESSION_KEY));
  assert.equal(storage.getItem('taskData_large_task'), null);
  const restored = await loadTaskRecording('large_task', storage);
  assert.equal(restored.samples.length, 2_000);
  assert.deepEqual(restored.metadata, metadata);
}

{
  const firstStorage = createStorage({}, { maxValueLength: 1 });
  const secondStorage = createStorage({}, { maxValueLength: 1 });

  await saveTaskRecording('same_task', [{ source: 'first' }], null, firstStorage);
  await saveTaskRecording('same_task', [{ source: 'second' }], null, secondStorage);

  assert.deepEqual(await loadTaskSamples('same_task', firstStorage), [{ source: 'first' }]);
  assert.deepEqual(await loadTaskSamples('same_task', secondStorage), [{ source: 'second' }]);
}

{
  await saveTaskRecording('no_web_storage', [{ fp1: 42 }]);
  assert.deepEqual(await loadTaskSamples('no_web_storage'), [{ fp1: 42 }]);
  await deleteTaskRecording('no_web_storage');
}

{
  const storage = createStorage({
    taskData_legacy_task: JSON.stringify([{ fp1: 1 }, { fp1: 2 }]),
  });

  const migrated = await loadTaskRecording('legacy_task', storage);

  assert.deepEqual(migrated.samples, [{ fp1: 1 }, { fp1: 2 }]);
  assert.equal(migrated.metadata, null);
  assert.equal(storage.getItem('taskData_legacy_task'), null);
  assert.deepEqual(await loadTaskSamples('legacy_task', storage), [{ fp1: 1 }, { fp1: 2 }]);
}

{
  const storage = createStorage();
  await saveTaskRecording('delete_me', [{ fp1: 1 }], null, storage);
  await deleteTaskRecording('delete_me', storage);
  assert.equal(await loadTaskRecording('delete_me', storage), null);
}

{
  const storage = createStorage({ completedTasks: JSON.stringify(['first', 'second']) });
  await saveTaskRecording('first', [{ fp1: 1 }], null, storage);
  await saveTaskRecording('second', [{ fp1: 2 }], null, storage);

  await clearTaskRecordings(null, storage);

  assert.equal(await loadTaskRecording('first', storage), null);
  assert.equal(await loadTaskRecording('second', storage), null);
}

{
  const storage = createStorage({ taskData_broken: '{not-json' });
  assert.equal(await loadTaskRecording('broken', storage), null);
  assert.equal(storage.getItem('taskData_broken'), null);
}

await assert.rejects(() => saveTaskRecording('', [], null, createStorage()), /taskId/i);

// Raw baselines must not depend on a Web Storage value large enough to hold the
// EEG payload. Only the compact run identifier is written there.
{
  const storage = createStorage({}, { maxValueLength: 100 });
  const samples = Array.from({ length: 30_000 }, (_, index) => ({
    fp1: index,
    fp2: -index,
    o1: index + 1,
    o2: -index - 1,
  }));
  const metadata = {
    completed: true,
    protocol_session: 2,
    battery_version: 'pilot-v1',
    recording_id: 'baseline-large-1',
  };

  await saveBaselineRecording('eyes_closed', samples, metadata, storage);

  assert.ok(storage.getItem(RECORDING_STORE_SESSION_KEY));
  assert.equal(storage.getItem('calibrationData_eyes_closed'), null);
  const restored = await loadBaselineRecording('eyes_closed', storage);
  assert.equal(restored.recordType, 'baseline');
  assert.equal(restored.condition, 'eyes_closed');
  assert.equal(restored.samples.length, 30_000);
  assert.deepEqual(restored.metadata, metadata);

  await deleteBaselineRecording('eyes_closed', storage);
  assert.equal(await loadBaselineRecording('eyes_closed', storage), null);
}

// Legacy arrays are removed only after a durable/in-memory test copy exists,
// and inherit their compact baseline metadata.
{
  const metadata = {
    completed: true,
    protocol_session: 1,
    battery_version: 'legacy-v1',
  };
  const storage = createStorage({
    calibrationData_eyes_open: JSON.stringify([{ fp1: 1, fp2: 2, o1: 3, o2: 4 }]),
    baselineCalibration: JSON.stringify({ eyesOpen: metadata }),
  });

  assert.deepEqual(await loadBaselineSamples('eyes_open', storage), [
    { fp1: 1, fp2: 2, o1: 3, o2: 4 },
  ]);
  assert.equal(storage.getItem('calibrationData_eyes_open'), null);
  assert.deepEqual((await loadBaselineRecording('eyes_open', storage))?.metadata, metadata);
}

await assert.rejects(
  () => saveBaselineRecording('unsupported', [], null, createStorage()),
  /Unsupported baseline condition/i,
);

// Renderer runtimes must surface missing/failing IndexedDB instead of quietly
// accepting a volatile in-memory copy.
{
  const originalWindow = globalThis.window;
  const originalIndexedDb = globalThis.indexedDB;
  try {
    globalThis.window = {};
    delete globalThis.indexedDB;

    await assert.rejects(
      () => saveTaskRecording('renderer_without_indexeddb', [{ fp1: 1 }], null, createStorage()),
      /IndexedDB is unavailable/i,
    );
    await assert.rejects(
      () => saveBaselineRecording('eyes_closed', [{ fp1: 1 }], null, createStorage()),
      /IndexedDB is unavailable/i,
    );
    const legacyBaselineStorage = createStorage({
      calibrationData_eyes_closed: JSON.stringify([{ fp1: 1, fp2: 2, o1: 3, o2: 4 }]),
      baselineCalibration: JSON.stringify({
        eyesClosed: { completed: true, protocol_session: 1, battery_version: 'legacy-v1' },
      }),
    });
    await assert.rejects(
      () => loadBaselineRecording('eyes_closed', legacyBaselineStorage),
      /IndexedDB is unavailable/i,
    );
    assert.ok(legacyBaselineStorage.getItem('calibrationData_eyes_closed'));
    await assert.rejects(
      () => loadTaskRecording('renderer_without_indexeddb', createStorage()),
      /IndexedDB is unavailable/i,
    );
    const completionStorage = createStorage();
    await assert.rejects(
      () => commitTaskAttempt(
        'renderer_commit_without_indexeddb',
        [{ fp1: 1 }],
        completionStorage,
      ),
      /IndexedDB is unavailable/i,
    );
    assert.equal(completionStorage.getItem('completedTasks'), null);

    globalThis.indexedDB = {
      open() {
        throw new Error('simulated IndexedDB open failure');
      },
    };
    await assert.rejects(
      () => saveTaskRecording('renderer_open_failure', [{ fp1: 1 }], null, createStorage()),
      /simulated IndexedDB open failure/i,
    );

    const fakeDb = {
      close() {},
      transaction(_storeName, mode) {
        const transaction = {
          error: null,
          objectStore() {
            return {
              put() {
                queueMicrotask(() => {
                  transaction.error = new Error('simulated IndexedDB put failure');
                  transaction.onerror?.();
                });
              },
              get() {
                const request = { error: null };
                queueMicrotask(() => {
                  request.error = new Error('simulated IndexedDB get failure');
                  request.onerror?.();
                });
                return request;
              },
            };
          },
        };
        assert.ok(mode === 'readwrite' || mode === 'readonly');
        return transaction;
      },
    };
    globalThis.indexedDB = {
      open() {
        const request = { result: null };
        queueMicrotask(() => {
          request.result = fakeDb;
          request.onsuccess?.();
        });
        return request;
      },
    };
    await assert.rejects(
      () => saveTaskRecording('renderer_put_failure', [{ fp1: 1 }], null, createStorage()),
      /simulated IndexedDB put failure/i,
    );
    await assert.rejects(
      () => loadTaskRecording('renderer_get_failure', createStorage()),
      /simulated IndexedDB get failure/i,
    );
  } finally {
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    if (originalIndexedDb === undefined) delete globalThis.indexedDB;
    else globalThis.indexedDB = originalIndexedDb;
  }
}
