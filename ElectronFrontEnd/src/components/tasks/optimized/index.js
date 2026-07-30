import { TASK_IDS } from '../optimizedBatteryConfig.mjs';

import numericalReasoning from './NumericalReasoningTask.jsx';
import workingMemory from './WorkingMemoryTask.jsx';
import auditoryTargetCounting from './AuditoryTargetCountingTask.jsx';
import semanticInduction from './SemanticInductionTask.jsx';
import visuospatial from './VisuospatialTask.jsx';
import divergentIdeation from './DivergentIdeationTask.jsx';
import dualTaskSwitching from './DualTaskSwitchingTask.jsx';
import anomalyDetection from './AnomalyDetectionTask.jsx';
import rapidVisualComparison from './RapidVisualComparisonTask.jsx';
import patternClosure from './PatternClosureTask.jsx';
import speechInNoise from './SpeechInNoiseTask.jsx';
import writtenComprehension from './WrittenComprehensionTask.jsx';

/**
 * Registry of the twelve optimized-battery task modules.
 *
 * Each module owns only what is specific to its task — the stimulus rendered
 * during the block, the response fields collected afterwards, its extra audit
 * schedule entries, and any response-validity gate. Everything shared (EEG
 * recording, audio delivery, timing, the quality gate) stays in the runner,
 * OptimizedBatteryTask.jsx.
 *
 * A module may omit any optional part: audio-only tasks have no `Stimulus`,
 * button-only tasks have no `ResponseFields`.
 *
 *   taskId          canonical id from TASK_IDS
 *   initialResponse ()                                          => object
 *   scheduleEvents  ({ form, definition, presentation })         => event[]
 *   IdleExtras      ({ previewingTone, onPreviewTone })          => node
 *   Stimulus        ({ form, presentation, elapsedSeconds,
 *                      mismatchDue, buttonRuntime, onDetect })   => node
 *   ResponseFields  ({ form, response, setResponse,
 *                      scoringThresholds, buttonRuntime })       => node
 *   isResponseValid ({ form, response, scoringThresholds })      => boolean
 */

const MODULES = [
  numericalReasoning,
  workingMemory,
  auditoryTargetCounting,
  semanticInduction,
  visuospatial,
  divergentIdeation,
  dualTaskSwitching,
  anomalyDetection,
  rapidVisualComparison,
  patternClosure,
  speechInNoise,
  writtenComprehension,
];

export const OPTIMIZED_TASK_MODULES = Object.freeze(
  Object.fromEntries(MODULES.map((module) => [module.taskId, module])),
);

// Fail at import time rather than rendering a blank task screen at run time if
// a canonical task ever loses its module (or two modules claim the same id).
const registered = Object.keys(OPTIMIZED_TASK_MODULES);
if (registered.length !== MODULES.length) {
  throw new Error('Duplicate taskId in the optimized task module registry');
}
for (const taskId of Object.values(TASK_IDS)) {
  if (!OPTIMIZED_TASK_MODULES[taskId]) {
    throw new Error(`No optimized task module registered for ${taskId}`);
  }
}

export function taskModuleFor(taskId) {
  const module = OPTIMIZED_TASK_MODULES[taskId];
  if (!module) throw new Error(`No optimized task module registered for ${taskId}`);
  return module;
}

export function initialResponseFor(taskId) {
  return OPTIMIZED_TASK_MODULES[taskId]?.initialResponse?.() ?? {};
}

export function taskScheduleEvents(taskId, context) {
  return OPTIMIZED_TASK_MODULES[taskId]?.scheduleEvents?.(context) ?? [];
}
