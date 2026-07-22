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

export function expectedTaskIdsForSession(sessionDepth) {
  return uniqueTaskIds(taskIdsForSession(sessionDepth));
}

export function missingExpectedTaskIds(completedIds, sessionDepth) {
  const completed = new Set(uniqueTaskIds(completedIds));
  return expectedTaskIdsForSession(sessionDepth).filter((taskId) => !completed.has(taskId));
}

export function missingOrEmptyTaskRecordings(completedIds, recordingsByTask) {
  return uniqueTaskIds(completedIds).filter((taskId) => {
    const recording = recordingsByTask instanceof Map
      ? recordingsByTask.get(taskId)
      : recordingsByTask?.[taskId];
    return !Array.isArray(recording?.samples) || recording.samples.length === 0;
  });
}

export function requiredBaselineConditionsForSession(sessionDepth) {
  return [...new Set(
    expectedTaskIdsForSession(sessionDepth)
      .map((taskId) => TASK_DEFINITIONS[taskId]?.baseline)
      .filter(Boolean),
  )];
}
