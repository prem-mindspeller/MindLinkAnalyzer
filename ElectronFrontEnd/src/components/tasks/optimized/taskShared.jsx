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

// Emphasise the ordering clause of the anomaly rule wherever it is shown, so
// participants notice the letter–hyphen–digits sequence must be in that order.
// Used by the runner's instruction list and by the Task 8 stimulus, which both
// render the same rule string.
const RULE_ORDER_PHRASE = 'in that same order';

export function renderRuleWithOrderEmphasis(text) {
  const value = String(text ?? '');
  const index = value.indexOf(RULE_ORDER_PHRASE);
  if (index < 0) return value;
  return [
    value.slice(0, index),
    <strong key="rule-order-emphasis">{RULE_ORDER_PHRASE}</strong>,
    value.slice(index + RULE_ORDER_PHRASE.length),
  ];
}
