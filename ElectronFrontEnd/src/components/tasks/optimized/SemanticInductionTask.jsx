import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 4 — Semantic Induction and Category Switching.
 *
 * Audio-only: both word streams and the seamless switch between them are
 * delivered as spokenEvents.
 */

function ResponseFields({ form, response, setResponse }) {
  return (
    <>
      <ResponseField label="First organising principle">
        <select
          required
          value={response.ruleOne || ''}
          onChange={(event) => setResponse({ ...response, ruleOne: event.target.value })}
        >
          <option value="">Select…</option>
          {form.ruleOptions.map((option) => <option key={option}>{option}</option>)}
        </select>
      </ResponseField>
      <ResponseField label="Second organising principle">
        <select
          required
          value={response.ruleTwo || ''}
          onChange={(event) => setResponse({ ...response, ruleTwo: event.target.value })}
        >
          <option value="">Select…</option>
          {form.secondRuleOptions.map((option) => <option key={option}>{option}</option>)}
        </select>
      </ResponseField>
      <ResponseField label="Did you notice the rule switch?">
        <select
          required
          value={response.switchDetected || ''}
          onChange={(event) => setResponse({ ...response, switchDetected: event.target.value })}
        >
          <option value="">Select…</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      </ResponseField>
    </>
  );
}

export default {
  taskId: TASK_IDS.SEMANTIC,
  ResponseFields,
};
