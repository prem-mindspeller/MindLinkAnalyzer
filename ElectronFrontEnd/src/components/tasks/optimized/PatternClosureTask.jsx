import React from 'react';

import { TASK_IDS, closureRevealState } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 10 — Pattern Closure under Visual Noise.
 *
 * The target is drawn as 16 clipped fragments that fade in on a configured
 * schedule while an overlaid noise layer thins out. The "Recognized" button
 * is clickable from the start of the block (no minimum-exposure delay);
 * Speed of Closure is scored from how far the reveal schedule has actually
 * progressed at the moment of response, not from whether some elapsed-time
 * floor was cleared first. Guessing risk from the immediate button is offset
 * by CLOSURE_FORMS offering 6 plausible options instead of a response delay.
 */

function FragmentedClosureTarget({ form, reveal, fragmentOrder }) {
  return (
    <div
      className="optimized-closure-fragments"
      style={{ filter: `blur(${reveal.blurPx}px)` }}
      role="img"
      aria-label="Fragmented target embedded in visual noise"
    >
      {Array.from({ length: 16 }, (_, fragmentIndex) => {
        const row = Math.floor(fragmentIndex / 4);
        const column = fragmentIndex % 4;
        const revealRank = fragmentOrder.indexOf(fragmentIndex);
        const threshold = revealRank / 16;
        const fragmentOpacity = Math.max(
          0,
          Math.min(1, (reveal.fragmentProgress - threshold) * 20),
        ) * reveal.symbolOpacity;
        return (
          <span
            key={fragmentIndex}
            className="optimized-closure-fragment"
            aria-hidden="true"
            style={{
              clipPath: `inset(${row * 25}% ${(3 - column) * 25}% ${(3 - row) * 25}% ${column * 25}%)`,
              opacity: fragmentOpacity,
            }}
          >{form.symbol}</span>
        );
      })}
    </div>
  );
}

function Stimulus({
  form, presentation, elapsedSeconds, buttonRuntime, onDetect,
}) {
  // Once "Recognized" is pressed, freeze the reveal at that instant instead of
  // continuing to track live elapsed time -- otherwise a participant could
  // click as soon as the button enables and then keep watching the target
  // clarify for free, decoupling the recorded reaction time from how much of
  // the target they actually had to work with.
  const revealElapsedSeconds = buttonRuntime?.detected
    ? buttonRuntime.responseElapsedMs / 1000
    : elapsedSeconds;
  const reveal = closureRevealState(form, revealElapsedSeconds);
  if (!reveal) return null;
  return (
    <div className="optimized-closure-stimulus">
      <FragmentedClosureTarget
        form={form}
        reveal={reveal}
        fragmentOrder={form.revealSchedule?.fragmentOrder || presentation.fragmentOrder}
      />
      <div className="optimized-noise-layer" style={{ opacity: reveal.noiseOpacity }} />
      <button
        type="button"
        className="optimized-detect-button"
        onClick={onDetect}
        disabled={buttonRuntime?.detected === true}
      >{buttonRuntime?.detected ? 'RESPONSE REGISTERED · REMAIN STILL' : 'RECOGNIZED'}</button>
    </div>
  );
}

function ResponseFields({
  form, response, setResponse, buttonRuntime,
}) {
  return (
    <>
      <ResponseField label="What target did you recognize?">
        <select
          required
          value={response.target || ''}
          onChange={(event) => setResponse({ ...response, target: event.target.value })}
        >
          <option value="">Select…</option>
          {form.options.map((option) => <option key={option}>{option}</option>)}
        </select>
      </ResponseField>
      {buttonRuntime?.timedOut && (
        <p className="optimized-response-warning">
          No recognition button was pressed during the block; this attempt will fail behavioral validation.
        </p>
      )}
    </>
  );
}

export default {
  taskId: TASK_IDS.CLOSURE,
  Stimulus,
  ResponseFields,
};
