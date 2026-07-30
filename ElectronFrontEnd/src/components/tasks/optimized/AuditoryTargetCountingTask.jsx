import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 3 — Auditory Target Counting.
 *
 * Audio-only during the block. Before starting, the participant can audition
 * the two tones so they know which one to count; the runner owns the audio
 * path and passes the play handler down.
 */

function IdleExtras({ previewingTone, onPreviewTone }) {
  return (
    <div className="task-runner-tone-preview">
      <p className="task-runner-tone-preview-label">Listen to the two tones before you start:</p>
      <div className="task-runner-tone-preview-buttons">
        <button
          type="button"
          className="task-runner-btn-preview task-runner-btn-preview-low"
          onClick={() => onPreviewTone('low')}
        >
          {previewingTone === 'low' ? '🔊' : '▶'} Low tone (ignore)
        </button>
        <button
          type="button"
          className="task-runner-btn-preview task-runner-btn-preview-high"
          onClick={() => onPreviewTone('high')}
        >
          {previewingTone === 'high' ? '🔊' : '▶'} High tone (count)
        </button>
      </div>
    </div>
  );
}

function ResponseFields({ response, setResponse }) {
  return (
    <ResponseField label="How many high target tones did you count?">
      <input
        type="number"
        min="0"
        required
        value={response.targetCount || ''}
        onChange={(event) => setResponse({ ...response, targetCount: event.target.value })}
      />
    </ResponseField>
  );
}

export default {
  taskId: TASK_IDS.AUDITORY_COUNT,
  IdleExtras,
  ResponseFields,
};
