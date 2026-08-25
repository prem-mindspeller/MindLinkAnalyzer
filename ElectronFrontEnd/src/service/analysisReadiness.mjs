import {
  TASK_DEFINITIONS,
  taskIdsForSession,
} from '../components/tasks/optimizedBatteryConfig.mjs';

function uniqueTaskIds(taskIds) {
  return [...new Set(
    (Array.isArray(taskIds) ? taskIds : [])
      .map((taskId) => String(taskId || '').trim())
      .filter(Boolean),
  )];
}

/**
 * Which tasks this run is expected to produce. When the participant has
 * disabled repetition, the tasks carried forward from earlier sessions are not
 * expected, so analysis must not treat their absence as an incomplete run.
 */
export function expectedTaskIdsForSession(sessionDepth, options) {
  return uniqueTaskIds(taskIdsForSession(sessionDepth, options));
}

export function missingExpectedTaskIds(completedIds, sessionDepth, options) {
  const completed = new Set(uniqueTaskIds(completedIds));
  return expectedTaskIdsForSession(sessionDepth, options)
    .filter((taskId) => !completed.has(taskId));
}

export function missingOrEmptyTaskRecordings(completedIds, recordingsByTask) {
  return uniqueTaskIds(completedIds).filter((taskId) => {
    const recording = recordingsByTask instanceof Map
      ? recordingsByTask.get(taskId)
      : recordingsByTask?.[taskId];
    return !Array.isArray(recording?.samples) || recording.samples.length === 0;
  });
}

export function requiredBaselineConditionsForSession(sessionDepth, options) {
  return [...new Set(
    expectedTaskIdsForSession(sessionDepth, options)
      .map((taskId) => TASK_DEFINITIONS[taskId]?.baseline)
      .filter(Boolean),
  )];
}
