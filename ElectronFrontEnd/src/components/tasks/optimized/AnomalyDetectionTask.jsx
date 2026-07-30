import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField, renderRuleWithOrderEmphasis } from './taskShared.jsx';

/**
 * Task 8 — Rule-Based Anomaly Detection.
 *
 * A continuous stream of codes, each shown for the configured interval. The
 * rule stays on screen so the task measures monitoring rather than rule recall.
 * No response is collected during the stream.
 */

const ANOMALY_TYPES = [
  'extra_letter',
  'wrong_order',
  'missing_separator',
  'missing_digit',
  'wrong_separator',
];

function initialResponse() {
  return { anomalyTypes: [], confidence: 3 };
}

function scheduleEvents({ form, presentation }) {
  return form.entries.map((entry, index) => ({
    key: `code:${index}`,
    at: entry.at ?? index * presentation.entryIntervalSeconds,
    type: 'code_entry_onset',
    stimulus_index: index,
    anomaly: Boolean(entry.type),
    anomaly_type: entry.type,
  }));
}

function Stimulus({ form, elapsedSeconds }) {
  const entry = form.entries[Math.min(form.entries.length - 1, Math.floor(elapsedSeconds / 2))];
  if (!entry) return null;
  return (
    <div className="optimized-code-stimulus">
      <small>{renderRuleWithOrderEmphasis(form.rule)}</small>
      <strong>{entry.value}</strong>
      <p>Count silently · no response during recording</p>
    </div>
  );
}

function ResponseFields({ response, setResponse }) {
  return (
    <>
      <ResponseField label="How many anomalies did you count?">
        <input
          type="number"
          min="0"
          required
          value={response.anomalyCount || ''}
          onChange={(event) => setResponse({ ...response, anomalyCount: event.target.value })}
        />
      </ResponseField>
      <fieldset className="optimized-checkboxes">
        <legend>Which anomaly types did you notice?</legend>
        {ANOMALY_TYPES.map((type) => (
          <label key={type}>
            <input
              type="checkbox"
              checked={response.anomalyTypes.includes(type)}
              onChange={(event) => {
                const values = event.target.checked
                  ? [...response.anomalyTypes, type]
                  : response.anomalyTypes.filter((value) => value !== type);
                setResponse({ ...response, anomalyTypes: values });
              }}
            /> {type.replaceAll('_', ' ')}
          </label>
        ))}
      </fieldset>
      <ResponseField label={`Confidence: ${response.confidence}/5`}>
        <input
          type="range"
          min="1"
          max="5"
          value={response.confidence}
          onChange={(event) => setResponse({ ...response, confidence: event.target.value })}
        />
      </ResponseField>
    </>
  );
}

export default {
  taskId: TASK_IDS.ANOMALY,
  initialResponse,
  scheduleEvents,
  Stimulus,
  ResponseFields,
};
