import React from 'react';

import { TASK_IDS, countWords, pacedPassageChunk } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 12 — Written Comprehension and Concise Synthesis.
 *
 * The passage is paced on screen in chunks for the reading window, then the
 * display switches to a silent-synthesis cue for the remainder of the block so
 * planning happens without typing artefact.
 */

function scheduleEvents({ presentation }) {
  const chunkInterval = presentation.readingDurationSeconds / presentation.chunkCount;
  return Array.from({ length: presentation.chunkCount }, (_, index) => ({
    key: `passage_chunk:${index}`,
    at: index * chunkInterval,
    type: 'paced_text_chunk',
    chunk_index: index,
  }));
}

function Stimulus({ form, presentation, elapsedSeconds }) {
  const chunk = elapsedSeconds < presentation.readingDurationSeconds
    ? pacedPassageChunk(form, elapsedSeconds)
    : null;
  return (
    <div className="optimized-paced-reading">
      {chunk
        ? <p>{chunk}</p>
        : (
          <>
            <strong>Silent synthesis</strong>
            <p>Keep your eyes open. Organize the main idea and supporting details in your mind. Do not type yet.</p>
          </>
        )}
    </div>
  );
}

// The summary length gate is a validity threshold, not a style preference: a
// "concise paraphrase" outside this range cannot be scored, so the runner
// blocks submission until it is satisfied.
function isResponseValid({ response, scoringThresholds }) {
  const wordCount = countWords(response.summary);
  return wordCount >= scoringThresholds.summaryMinimumWords
    && wordCount <= scoringThresholds.summaryMaximumWords;
}

function ResponseFields({ form, response, setResponse, scoringThresholds }) {
  const wordCount = countWords(response.summary);
  const lengthValid = isResponseValid({ response, scoringThresholds });
  return (
    <>
      <ResponseField label="Select the main idea.">
        <select
          required
          value={response.mainIdea || ''}
          onChange={(event) => setResponse({ ...response, mainIdea: event.target.value })}
        >
          <option value="">Select…</option>
          {form.mainIdeaOptions.map((option) => <option key={option}>{option}</option>)}
        </select>
      </ResponseField>
      <ResponseField label={`Write a ${scoringThresholds.summaryMinimumWords}–${scoringThresholds.summaryMaximumWords} word summary (${wordCount} words).`}>
        <textarea
          rows="7"
          required
          value={response.summary || ''}
          onChange={(event) => setResponse({ ...response, summary: event.target.value })}
        />
      </ResponseField>
      {!lengthValid && (
        <p className="optimized-response-warning">
          The summary must contain {scoringThresholds.summaryMinimumWords}–{scoringThresholds.summaryMaximumWords} words before it can be saved.
        </p>
      )}
    </>
  );
}

export default {
  taskId: TASK_IDS.WRITTEN,
  scheduleEvents,
  Stimulus,
  isResponseValid,
  ResponseFields,
};
