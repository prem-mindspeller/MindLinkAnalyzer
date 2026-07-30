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
// notice them at a glance — e.g. the anomaly rule's ordering clause, or
// Task 7's warning that its instructions are shown only once. Used by the
// runner's instruction list and by the Task 8 stimulus, which both render
// rule/instruction strings through this same helper.
const EMPHASIZED_PHRASES = [
  'in that same order',
  'Read this very carefully',
];

export function renderRuleWithOrderEmphasis(text) {
  const value = String(text ?? '');
  for (const phrase of EMPHASIZED_PHRASES) {
    const index = value.indexOf(phrase);
    if (index < 0) continue;
    return [
      value.slice(0, index),
      <strong key={`emphasis-${phrase}`}>{phrase}</strong>,
      value.slice(index + phrase.length),
    ];
  }
  return value;
}
