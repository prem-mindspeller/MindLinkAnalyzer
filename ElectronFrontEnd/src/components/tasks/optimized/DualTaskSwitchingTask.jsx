import React from 'react';

import { TASK_IDS } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 7 — Dual-Task Performance and Rule Switching.
 *
 * Audio-only: the tone stream and the spoken "Update"/"Switch" cues are both
 * scheduled generically from the form. Time Sharing is scored against the
 * matched Task 2 and Task 3 single-task attempts, which the runner resolves.
 * Before starting, the participant can audition all four cues (low tone, high
 * tone, "Update", "Switch") so nothing on the block is heard for the first
 * time while EEG is being scored.
 */

function IdleExtras({ previewingTone, onPreviewTone, previewingSpeech, onPreviewSpeech }) {
  return (
    <div className="task-runner-tone-preview">
      <p className="task-runner-tone-preview-label">Listen to the cues before you start:</p>
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
        <button
          type="button"
          className="task-runner-btn-preview task-runner-btn-preview-update"
          onClick={() => onPreviewSpeech('update', 'Update.')}
        >
          {previewingSpeech === 'update' ? '🔊' : '▶'} "Update" cue
        </button>
        <button
          type="button"
          className="task-runner-btn-preview task-runner-btn-preview-switch"
          onClick={() => onPreviewSpeech('switch', 'Switch.')}
        >
          {previewingSpeech === 'switch' ? '🔊' : '▶'} "Switch" cue
        </button>
      </div>
    </div>
  );
}

function ResponseFields({ response, setResponse }) {
  return (
    <div className="optimized-response-grid">
      <ResponseField label="Final number">
        <input
          type="number"
          required
          value={response.finalValue || ''}
          onChange={(event) => setResponse({ ...response, finalValue: event.target.value })}
        />
      </ResponseField>
      <ResponseField label="High-tone count">
        <input
          type="number"
          min="0"
          required
          value={response.targetCount || ''}
          onChange={(event) => setResponse({ ...response, targetCount: event.target.value })}
        />
      </ResponseField>
    </div>
  );
}

export default {
  taskId: TASK_IDS.DUAL_TASK,
  IdleExtras,
  ResponseFields,
};
