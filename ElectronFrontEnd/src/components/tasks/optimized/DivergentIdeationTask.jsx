import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 6 — Divergent Ideation.
 *
 * Silent generation block: the prompt is given in the pre-recording
 * instructions, and nothing is presented or scheduled during the block itself.
 */

function ResponseFields({ response, setResponse }) {
  return (
    <ResponseField label="Enter one idea per line. Relevance, category diversity, and originality remain pending expert/validated scoring.">
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
