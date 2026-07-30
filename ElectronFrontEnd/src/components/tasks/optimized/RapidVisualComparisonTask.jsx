import React from 'react';

import { TASK_IDS, visualComparisonFrame } from '../optimizedBatteryConfig.mjs';

/**
 * Task 9 — Rapid Visual Comparison.
 *
 * Two synchronized code strings update together until one character in the
 * lower row drifts away from the upper one. Reaction time is measured from the
 * frame that actually rendered the mismatch, so the reveal is a CSS transition
 * the runner times rather than an instant swap.
 *
 * The button press is the whole response; there is no post-block form.
 */

function ComparisonLine({ frame, revealMismatch, revealSeconds }) {
  return (
    <div
      className="optimized-comparison-line"
      aria-label={revealMismatch ? frame.changed : frame.base}
      style={{ '--mismatch-reveal-duration': `${revealSeconds}s` }}
    >
      {[...frame.base].map((character, index) => {
        if (index !== frame.mismatchIndex) return <span key={index}>{character}</span>;
        return (
          <span
            key={index}
            className={`optimized-comparison-character${revealMismatch ? ' is-revealing' : ''}`}
            aria-hidden="true"
          >
            <span className="optimized-comparison-original">{character}</span>
            {revealMismatch && (
              <span className="optimized-comparison-replacement">{frame.changed[index]}</span>
            )}
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
  form, elapsedSeconds, mismatchDue, buttonRuntime, onDetect,
}) {
  const frame = visualComparisonFrame(form, elapsedSeconds);
  if (!frame) return null;
  return (
    <div className="optimized-comparison-stimulus">
      <div>{frame.base}</div>
      <ComparisonLine
        frame={frame}
        revealMismatch={mismatchDue}
        revealSeconds={form.mismatchRevealSeconds}
      />
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
