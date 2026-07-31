import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 6 — Divergent Ideation.
 *
 * Silent generation block: the prompt is shown in the pre-recording
 * instructions and spoken once at task start (see IDEATION_FORMS'
 * spokenEvents in optimizedBatteryConfig.mjs); nothing else is presented or
 * scheduled during the block itself.
 */

function ResponseFields({ response, setResponse }) {
  return (
    <ResponseField label="Enter one idea per line (Shift+Enter will start a new line).">
      <textarea
        rows="8"
        required
        value={response.ideas || ''}
        onChange={(event) => setResponse({ ...response, ideas: event.target.value })}
      />
    </ResponseField>
  );
}

export default {
  taskId: TASK_IDS.IDEATION,
  ResponseFields,
};
