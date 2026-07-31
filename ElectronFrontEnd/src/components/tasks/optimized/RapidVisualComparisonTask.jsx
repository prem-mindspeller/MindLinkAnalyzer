import React from 'react';

import { TASK_IDS, visualComparisonFrame } from '../optimizedBatteryConfig.mjs';

/**
 * Task 9 — Rapid Visual Comparison.
 *
 * Two synchronized code strings update together until one character in the
 * lower row drifts away from the upper one, with an instant swap rather than
 * a fade -- an animated reveal is itself a motion cue that would give the
 * mismatch away regardless of whether the participant is actually comparing
 * the rows. Reaction time is measured from the first animation frame that
 * actually rendered the mismatched character. After that, more positions
 * drift apart on a fixed schedule (see MISMATCH_ESCALATION_STEP_SECONDS in
 * optimizedBatteryConfig.mjs) so the rows become unmistakably different well
 * before the block ends, rather than staying at one easy-to-miss character
 * for the whole remainder.
 *
 * The button press is the whole response; there is no post-block form.
 */

function ComparisonLine({ frame }) {
  const mismatched = new Set(frame.mismatchIndices);
  return (
    <div
      className="optimized-comparison-line"
      aria-label={mismatched.size > 0 ? frame.changed : frame.base}
    >
      {[...frame.base].map((character, index) => {
        if (!mismatched.has(index)) return <span key={index}>{character}</span>;
        return (
          <span
            key={index}
            className="optimized-comparison-character is-mismatched"
            aria-hidden="true"
          >
            <span className="optimized-comparison-original">{character}</span>
            <span className="optimized-comparison-replacement">{frame.changed[index]}</span>
          </span>
        );
      })}
    </div>
  );
}

function scheduleEvents({ form }) {
  return [{ key: 'mismatch_due', at: form.mismatchOnset, type: 'mismatch_reveal_due' }];
}

function Stimulus({
  form, elapsedSeconds, buttonRuntime, onDetect,
}) {
  const frame = visualComparisonFrame(form, elapsedSeconds);
  if (!frame) return null;
  return (
    <div className="optimized-comparison-stimulus">
      <div>{frame.base}</div>
      <ComparisonLine frame={frame} />
      <button
        type="button"
        className="optimized-detect-button"
        onClick={onDetect}
        disabled={buttonRuntime?.detected === true}
      >{buttonRuntime?.detected ? 'RESPONSE REGISTERED · REMAIN STILL' : 'DETECT MISMATCH'}</button>
    </div>
  );
}

export default {
  taskId: TASK_IDS.VISUAL_COMPARISON,
  scheduleEvents,
  Stimulus,
};
