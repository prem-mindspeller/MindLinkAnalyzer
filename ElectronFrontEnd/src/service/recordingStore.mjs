const DB_NAME = 'mindlink-analyzer-recordings';
const DB_VERSION = 1;
const OBJECT_STORE = 'taskRecordings';
export const RECORDING_STORE_SESSION_KEY = 'recordingStoreSessionId';
const SESSION_ID_KEY = RECORDING_STORE_SESSION_KEY;
const LEGACY_TASK_PREFIX = 'taskData_';
const BASELINE_RECORD_PREFIX = 'baseline::';
const LEGACY_BASELINE_KEY_BY_CONDITION = Object.freeze({
  eyes_closed: 'calibrationData_eyes_closed',
  eyes_open: 'calibrationData_eyes_open',
});
const BASELINE_SUMMARY_KEY_BY_CONDITION = Object.freeze({
  eyes_closed: 'eyesClosed',
  eyes_open: 'eyesOpen',
});

// Node's test runtime has no IndexedDB. The in-memory store is intentionally
// limited to that non-renderer environment: a browser/Electron renderer must
// never report a volatile copy as a successfully persisted EEG recording.
const memoryRecords = new Map();
let databasePromise = null;
const ephemeralSessionIds = new WeakMap();
let unscopedSessionId = null;

function defaultStorage() {
  try {
    return globalThis.sessionStorage || null;
  } catch {
    return null;
  }
}

function safeGet(storage, key) {
  try {
    return storage?.getItem?.(key) ?? null;
  } catch {
    return null;
  }
}

function safeSet(storage, key, value) {
  if (typeof storage?.setItem !== 'function') return false;
  try {
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function safeRemove(storage, key) {
  try {
    storage?.removeItem?.(key);
  } catch {
    // Cleanup of a legacy value is best-effort. The IndexedDB copy remains the
    // source of truth even when a custom Storage implementation rejects writes.
  }
}

function createSessionId() {
  try {
    if (typeof globalThis.crypto?.randomUUID === 'function') {
      return globalThis.crypto.randomUUID();
    }
  } catch {
    // Fall through to a dependency-free identifier.
  }
  return `recording-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function resolveSessionId(storage = defaultStorage()) {
  const existing = safeGet(storage, SESSION_ID_KEY);
  if (existing) return existing;

  const canScopeToStorage = storage !== null
    && (typeof storage === 'object' || typeof storage === 'function');
  if (canScopeToStorage) {
    const scoped = ephemeralSessionIds.get(storage);
    if (scoped) {
      // A previous write can fail transiently when legacy Web Storage is full.
      // Retry after migrations have freed space so a refresh does not orphan
      // otherwise durable IndexedDB recordings.
      if (safeSet(storage, SESSION_ID_KEY, scoped)) ephemeralSessionIds.delete(storage);
      return scoped;
    }
  } else if (unscopedSessionId) {
    return unscopedSessionId;
  }

  const generated = createSessionId();
  if (safeSet(storage, SESSION_ID_KEY, generated)) return generated;

  if (canScopeToStorage) {
    ephemeralSessionIds.set(storage, generated);
  } else {
    unscopedSessionId = generated;
  }
  return generated;
}

function normalizeTaskId(taskId) {
  const normalized = String(taskId || '').trim();
  if (!normalized) throw new Error('A non-empty taskId is required for a task recording.');
  return normalized;
}

function normalizeBaselineCondition(condition) {
  const normalized = String(condition || '').trim().toLowerCase();
  if (!Object.hasOwn(LEGACY_BASELINE_KEY_BY_CONDITION, normalized)) {
    throw new Error(`Unsupported baseline condition: ${condition || '(empty)'}.`);
  }
  return normalized;
}

function recordingKey(sessionId, taskId) {
  return `${sessionId}::${taskId}`;
}

function baselineRecordingKey(sessionId, condition) {
  return recordingKey(sessionId, `${BASELINE_RECORD_PREFIX}${condition}`);
}

function canUseIndexedDb() {
  return typeof globalThis.indexedDB !== 'undefined' && globalThis.indexedDB !== null;
}

function isBrowserRenderer() {
  return typeof globalThis.window !== 'undefined';
}

function canUseMemoryFallback() {
  return !isBrowserRenderer();
}

function openDatabase() {
  if (!canUseIndexedDb()) {
    if (isBrowserRenderer()) {
      return Promise.reject(new Error(
        'IndexedDB is unavailable; EEG recordings cannot be stored durably.',
      ));
    }
    return Promise.resolve(null);
  }
  if (databasePromise) return databasePromise;

  databasePromise = new Promise((resolve, reject) => {
    let request;
    try {
      request = globalThis.indexedDB.open(DB_NAME, DB_VERSION);
    } catch (error) {
      reject(error);
      return;
    }

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(OBJECT_STORE)) {
        db.createObjectStore(OBJECT_STORE, { keyPath: 'key' });
      }
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => db.close();
      resolve(db);
    };
    request.onerror = () => reject(request.error || new Error('Could not open the recording database.'));
    request.onblocked = () => reject(new Error('The recording database upgrade is blocked.'));
  }).catch((error) => {
    databasePromise = null;
    throw error;
  });

  return databasePromise;
}

function transactionDone(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error('Recording transaction failed.'));
    transaction.onabort = () => reject(transaction.error || new Error('Recording transaction was aborted.'));
  });
}

async function indexedDbPut(record) {
  const db = await openDatabase();
  if (!db) return false;
  const transaction = db.transaction(OBJECT_STORE, 'readwrite');
  transaction.objectStore(OBJECT_STORE).put(record);
  await transactionDone(transaction);
  return true;
}

async function indexedDbGet(key) {
  const db = await openDatabase();
  if (!db) return null;
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(OBJECT_STORE, 'readonly');
    const request = transaction.objectStore(OBJECT_STORE).get(key);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error || new Error('Could not read the EEG recording.'));
  });
}

async function indexedDbDelete(key) {
  const db = await openDatabase();
  if (!db) return false;
  const transaction = db.transaction(OBJECT_STORE, 'readwrite');
  transaction.objectStore(OBJECT_STORE).delete(key);
  await transactionDone(transaction);
  return true;
}

async function indexedDbDeleteSession(sessionId) {
  const db = await openDatabase();
  if (!db) return false;

  const transaction = db.transaction(OBJECT_STORE, 'readwrite');
  const request = transaction.objectStore(OBJECT_STORE).openCursor();
  request.onsuccess = () => {
    const cursor = request.result;
    if (!cursor) return;
    const record = cursor.value;
    if (
      record?.sessionId === sessionId
      || String(record?.key || '').startsWith(`${sessionId}::`)
    ) cursor.delete();
    cursor.continue();
  };
  request.onerror = () => transaction.abort();
  await transactionDone(transaction);
  return true;
}

function currentSessionId(storage = defaultStorage()) {
  const stored = safeGet(storage, SESSION_ID_KEY);
  if (stored) return stored;

  const canScopeToStorage = storage !== null
    && (typeof storage === 'object' || typeof storage === 'function');
  return canScopeToStorage ? (ephemeralSessionIds.get(storage) || null) : unscopedSessionId;
}

function normalizeLegacyRecording(taskId, parsed) {
  if (Array.isArray(parsed)) {
    return { taskId, samples: parsed, metadata: null };
  }
  if (parsed && typeof parsed === 'object' && Array.isArray(parsed.samples)) {
    return {
      taskId,
      samples: parsed.samples,
      metadata: parsed.metadata ?? null,
    };
  }
  return null;
}

function readLegacyBaselineMetadata(storage, condition) {
  let summary;
  try {
    summary = JSON.parse(safeGet(storage, 'baselineCalibration') || '{}');
  } catch {
    return null;
  }
  const summaryKey = BASELINE_SUMMARY_KEY_BY_CONDITION[condition];
  const metadata = summary?.[summaryKey];
  return metadata && typeof metadata === 'object' && !Array.isArray(metadata)
    ? metadata
    : null;
}

/**
 * Persist one task recording outside sessionStorage.
 *
 * metadata is deliberately schema-free so task components can attach markers,
 * form IDs, behavioural answers, eye state and sample-rate information without
 * another storage migration.
 */
export async function saveTaskRecording(
  taskId,
  samples,
  metadata = null,
  storage = defaultStorage(),
) {
  const normalizedTaskId = normalizeTaskId(taskId);
  const sessionId = resolveSessionId(storage);
  const key = recordingKey(sessionId, normalizedTaskId);
  const record = {
    key,
    sessionId,
    taskId: normalizedTaskId,
    samples: Array.isArray(samples) ? samples : [],
    metadata: metadata ?? null,
    updatedAt: new Date().toISOString(),
  };

  const persisted = await indexedDbPut(record);
  if (!persisted) {
    if (!canUseMemoryFallback()) {
      throw new Error('Task recording was not stored durably.');
    }
    memoryRecords.set(key, record);
  }

  // The new durable/in-memory copy is established before the legacy raw value
  // is removed, so migration never creates a gap where neither copy exists.
  safeRemove(storage, `${LEGACY_TASK_PREFIX}${normalizedTaskId}`);
  return record;
}

/**
 * Load a structured task recording. Legacy taskData_<id> arrays are migrated
 * lazily on first read and removed from sessionStorage after a successful copy.
 */
export async function loadTaskRecording(taskId, storage = defaultStorage()) {
  const normalizedTaskId = normalizeTaskId(taskId);
  const sessionId = resolveSessionId(storage);
  const key = recordingKey(sessionId, normalizedTaskId);

  let record = await indexedDbGet(key);
  if (!record && canUseMemoryFallback()) record = memoryRecords.get(key) || null;
  if (record) {
    // Retry best-effort cleanup in case the first post-commit removal was
    // temporarily rejected by Web Storage.
    safeRemove(storage, `${LEGACY_TASK_PREFIX}${normalizedTaskId}`);
    safeSet(storage, SESSION_ID_KEY, sessionId);
    return record;
  }

  const legacyKey = `${LEGACY_TASK_PREFIX}${normalizedTaskId}`;
  const legacyRaw = safeGet(storage, legacyKey);
  if (legacyRaw == null) return null;

  let parsed;
  try {
    parsed = JSON.parse(legacyRaw);
  } catch {
    safeRemove(storage, legacyKey);
    return null;
  }

  const legacy = normalizeLegacyRecording(normalizedTaskId, parsed);
  if (!legacy) {
    safeRemove(storage, legacyKey);
    return null;
  }
  return saveTaskRecording(legacy.taskId, legacy.samples, legacy.metadata, storage);
}

export async function loadTaskSamples(taskId, storage = defaultStorage()) {
  const record = await loadTaskRecording(taskId, storage);
  return Array.isArray(record?.samples) ? record.samples : [];
}

/**
 * Persist one raw baseline in the same run-scoped durable store as task EEG.
 * A distinct key namespace prevents baseline conditions from colliding with
 * canonical task IDs. Completion, protocol and transport metadata travel with
 * the samples so analysis never combines data with an unrelated manifest.
 */
export async function saveBaselineRecording(
  condition,
  samples,
  metadata = null,
  storage = defaultStorage(),
) {
  const normalizedCondition = normalizeBaselineCondition(condition);
  const sessionId = resolveSessionId(storage);
  const key = baselineRecordingKey(sessionId, normalizedCondition);
  const record = {
    key,
    sessionId,
    recordType: 'baseline',
    condition: normalizedCondition,
    samples: Array.isArray(samples) ? samples : [],
    metadata: metadata ?? null,
    updatedAt: new Date().toISOString(),
  };

  const persisted = await indexedDbPut(record);
  if (!persisted) {
    if (!canUseMemoryFallback()) {
      throw new Error('Baseline recording was not stored durably.');
    }
    memoryRecords.set(key, record);
  }

  // Establish the durable copy before retiring the Web Storage value. If the
  // put fails, the legacy recording remains available for a later retry.
  safeRemove(storage, LEGACY_BASELINE_KEY_BY_CONDITION[normalizedCondition]);
  // Retry a session-id write that may previously have failed due to the large
  // legacy value occupying the DOM Storage quota.
  safeSet(storage, SESSION_ID_KEY, sessionId);
  return record;
}

/**
 * Load a structured baseline recording. Pre-migration calibrationData_* arrays
 * are copied lazily, with metadata recovered from the compact manifest, and are
 * removed only after the durable copy commits.
 */
export async function loadBaselineRecording(condition, storage = defaultStorage()) {
  const normalizedCondition = normalizeBaselineCondition(condition);
  const sessionId = resolveSessionId(storage);
  const key = baselineRecordingKey(sessionId, normalizedCondition);

  let record = await indexedDbGet(key);
  if (!record && canUseMemoryFallback()) record = memoryRecords.get(key) || null;
  if (record) {
    // Retry best-effort cleanup in case the first post-commit removal was
    // temporarily rejected by Web Storage.
    safeRemove(storage, LEGACY_BASELINE_KEY_BY_CONDITION[normalizedCondition]);
    safeSet(storage, SESSION_ID_KEY, sessionId);
    return record;
  }

  const legacyKey = LEGACY_BASELINE_KEY_BY_CONDITION[normalizedCondition];
  const legacyRaw = safeGet(storage, legacyKey);
  if (legacyRaw == null) return null;

  let parsed;
  try {
    parsed = JSON.parse(legacyRaw);
  } catch {
    safeRemove(storage, legacyKey);
    return null;
  }
  if (!Array.isArray(parsed)) {
    safeRemove(storage, legacyKey);
    return null;
  }

  return saveBaselineRecording(
    normalizedCondition,
    parsed,
    readLegacyBaselineMetadata(storage, normalizedCondition),
    storage,
  );
}

export async function loadBaselineSamples(condition, storage = defaultStorage()) {
  const record = await loadBaselineRecording(condition, storage);
  return Array.isArray(record?.samples) ? record.samples : [];
}

export async function deleteTaskRecording(taskId, storage = defaultStorage()) {
  const normalizedTaskId = normalizeTaskId(taskId);
  const sessionId = resolveSessionId(storage);
  const key = recordingKey(sessionId, normalizedTaskId);

  const deleted = await indexedDbDelete(key);
  if (!deleted && !canUseMemoryFallback()) {
    throw new Error('Task recording could not be removed from durable storage.');
  }
  memoryRecords.delete(key);
  safeRemove(storage, `${LEGACY_TASK_PREFIX}${normalizedTaskId}`);
}

export async function deleteBaselineRecording(condition, storage = defaultStorage()) {
  const normalizedCondition = normalizeBaselineCondition(condition);
  const sessionId = resolveSessionId(storage);
  const key = baselineRecordingKey(sessionId, normalizedCondition);

  const deleted = await indexedDbDelete(key);
  if (!deleted && !canUseMemoryFallback()) {
    throw new Error('Baseline recording could not be removed from durable storage.');
  }
  memoryRecords.delete(key);
  safeRemove(storage, LEGACY_BASELINE_KEY_BY_CONDITION[normalizedCondition]);
}

export async function clearTaskRecordings(taskIds = null, storage = defaultStorage()) {
  let ids = taskIds;
  if (!Array.isArray(ids)) {
    try {
      const completed = JSON.parse(safeGet(storage, 'completedTasks') || '[]');
      ids = Array.isArray(completed) ? completed : [];
    } catch {
      ids = [];
    }
  }

  await Promise.all([...new Set(ids.map((id) => String(id || '').trim()).filter(Boolean))]
    .map((id) => deleteTaskRecording(id, storage)));
}

/**
 * Delete every recording belonging to the current battery run, including
 * interrupted attempts that were never added to completedTasks. The session
 * identifier is always retired after the deletion attempt, so even a storage
 * failure cannot make the old namespace reusable by a subsequent participant.
 */
export async function clearRecordingSession(storage = defaultStorage()) {
  const sessionId = currentSessionId(storage);
  try {
    if (sessionId) {
      const deletedDurably = await indexedDbDeleteSession(sessionId);
      if (!deletedDurably && !canUseMemoryFallback()) {
        throw new Error('EEG recording session could not be removed from durable storage.');
      }
    }
  } finally {
    for (const [key, record] of memoryRecords.entries()) {
      if (
        sessionId
        && (
          record?.sessionId === sessionId
          || String(record?.key || key).startsWith(`${sessionId}::`)
        )
      ) memoryRecords.delete(key);
    }
    safeRemove(storage, SESSION_ID_KEY);
    const canScopeToStorage = storage !== null
      && (typeof storage === 'object' || typeof storage === 'function');
    if (canScopeToStorage) ephemeralSessionIds.delete(storage);
    else unscopedSessionId = null;
  }

  return sessionId;
}
