import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 11 — Speech-in-Noise Comprehension.
 *
 * Eyes-closed listening block with nothing on screen. The passage is a
 * premixed, SNR-calibrated asset rather than live synthesis, so the schedule
 * entry carries the asset URI and the runner resolves it through the audio
 * profile.
 */

function scheduleEvents({ form, presentation }) {
  return [{
    key: 'passage',
    at: form.passageOnsetSeconds ?? presentation.passageOnsetSeconds,
    type: 'spoken_passage_onset',
    text: form.passage,
    asset_uri: form.audioAssetUri || null,
  }];
}

function ResponseFields({ form, response, setResponse }) {
  return (
    <>
      <ResponseField label="Select the main interpretation.">
        <select
          required
          value={response.mainIdea || ''}
          onChange={(event) => setResponse({ ...response, mainIdea: event.target.value })}
        >
          <option value="">Select…</option>
          {form.mainIdeaOptions.map((option) => <option key={option}>{option}</option>)}
        </select>
      </ResponseField>
      <ResponseField label={form.keyDetailQuestion}>
        <select
          required
          value={response.keyDetail || ''}
          onChange={(event) => setResponse({ ...response, keyDetail: event.target.value })}
        >
          <option value="">Select…</option>
          {form.keyDetailOptions.map((option) => <option key={option}>{option}</option>)}
        </select>
      </ResponseField>
      <ResponseField label="Give one concise paraphrase of the passage.">
        <textarea
          rows="4"
          required
          value={response.paraphrase || ''}
          onChange={(event) => setResponse({ ...response, paraphrase: event.target.value })}
        />
      </ResponseField>
    </>
  );
}

export default {
  taskId: TASK_IDS.SPEECH_NOISE,
  scheduleEvents,
  ResponseFields,
};
