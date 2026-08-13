import assert from 'node:assert/strict';
import test from 'node:test';

import { hasPendingInTaskAudioTranslation } from './inTaskAudioAvailability.mjs';

test('the language-selector notice is shown only for languages without the Dutch cue pack', () => {
  assert.equal(hasPendingInTaskAudioTranslation('en'), false);
  assert.equal(hasPendingInTaskAudioTranslation('nl-BE'), false);
  assert.equal(hasPendingInTaskAudioTranslation('de'), true);
  assert.equal(hasPendingInTaskAudioTranslation('ja'), true);
});
