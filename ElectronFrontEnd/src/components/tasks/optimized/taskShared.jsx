import React from 'react';

/**
 * Presentation helpers shared by more than one optimized-battery task module.
 *
 * Anything used by a single task lives in that task's own file instead, so the
 * only things here are genuinely cross-task.
 */

export function ResponseField({ label, children }) {
  return (
    <label className="optimized-response-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

// Emphasise fixed phrases wherever they appear in task copy, so participants
// notice them at a glance — e.g. the anomaly rule's ordering clause, Task 7's
// warning that its instructions are shown only once, or Task 9's example
// highlighting the one character that differs between two otherwise-identical
// codes. A plain string bolds its whole match; {anchor, bold} locates the
// larger, guaranteed-unique `anchor` substring first and then bolds only the
// last occurrence of `bold` within it (e.g. the second, differing "M" in
// "YF4M-D5AM-FRYE", not the first one in "YF4M"). Used by the runner's
// instruction list and by the Task 8 stimulus, which both render
// rule/instruction strings through this same helper.
const EMPHASIZED_PHRASES = [
  'in that same order',
  'Read this very carefully',
  { anchor: '"YF4M-D5AM-FRYE"', bold: 'M' },
  // Anchored to the full phrase (not just "once") because Task 10 has its own,
  // differently-worded "press it only once you are sure" line that must stay
  // unemphasised.
  { anchor: 'once when you first notice it', bold: 'once' },
  'After 20 seconds',
];

export function renderRuleWithOrderEmphasis(text) {
  const value = String(text ?? '');
  for (const entry of EMPHASIZED_PHRASES) {
    const anchor = typeof entry === 'string' ? entry : entry.anchor;
    const anchorIndex = value.indexOf(anchor);
    if (anchorIndex < 0) continue;
    const bold = typeof entry === 'string' ? entry : entry.bold;
    const boldOffset = anchor.lastIndexOf(bold);
    const boldIndex = anchorIndex + boldOffset;
    return [
      value.slice(0, boldIndex),
      <strong key={`emphasis-${anchor}`}>{bold}</strong>,
      value.slice(boldIndex + bold.length),
    ];
  }
  return value;
}
