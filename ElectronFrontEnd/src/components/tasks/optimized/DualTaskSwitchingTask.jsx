import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 7 — Dual-Task Performance and Rule Switching.
 *
 * Audio-only: the tone stream and the spoken "Update"/"Switch" cues are both
 * scheduled generically from the form. Time Sharing is scored against the
 * matched Task 2 and Task 3 single-task attempts, which the runner resolves.
 */

function ResponseFields({ response, setResponse }) {
  return (
    <div className="optimized-response-grid">
      <ResponseField label="High-tone count">
        <input
          type="number"
          min="0"
          required
          value={response.targetCount || ''}
          onChange={(event) => setResponse({ ...response, targetCount: event.target.value })}
        />
      </ResponseField>
      <ResponseField label="Final number">
        <input
          type="number"
          required
          value={response.finalValue || ''}
          onChange={(event) => setResponse({ ...response, finalValue: event.target.value })}
        />
      </ResponseField>
    </div>
  );
}

export default {
  taskId: TASK_IDS.DUAL_TASK,
  ResponseFields,
};
