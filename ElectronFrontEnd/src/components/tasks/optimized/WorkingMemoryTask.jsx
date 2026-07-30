import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 2 — Working-Memory Manipulation.
 *
 * Audio-only. The initial sequence is deliberately never rendered on screen:
 * it is spoken once after scoring starts, so showing it would remove the
 * encoding load the task measures.
 */

function ResponseFields({ response, setResponse }) {
  return (
    <ResponseField label="Enter the final sequence in order (for example 4-7-2-5).">
      <input
        required
        value={response.finalSequence || ''}
        onChange={(event) => setResponse({ ...response, finalSequence: event.target.value })}
      />
    </ResponseField>
  );
}

export default {
  taskId: TASK_IDS.WORKING_MEMORY,
  ResponseFields,
};
