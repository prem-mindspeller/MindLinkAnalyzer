import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 1 — Adaptive Numerical Reasoning and Sequencing.
 *
 * Audio-only: the calculation chain is delivered through the form's
 * spokenEvents, which the runner schedules generically, so there is no
 * on-screen stimulus and no task-specific schedule entry.
 */

function ResponseFields({ response, setResponse }) {
  return (
    <ResponseField label="What was the final value?">
      <input
        type="number"
        required
        value={response.finalValue || ''}
        onChange={(event) => setResponse({ ...response, finalValue: event.target.value })}
      />
    </ResponseField>
  );
}

export default {
  taskId: TASK_IDS.NUMERICAL,
  ResponseFields,
};
