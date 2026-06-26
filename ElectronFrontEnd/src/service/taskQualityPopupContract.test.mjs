import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const serviceDir = dirname(fileURLToPath(import.meta.url));
const srcDir = join(serviceDir, '..');
const taskSelectionSource = readFileSync(join(srcDir, 'pages', 'TaskSelection.jsx'), 'utf8');

assert.equal(taskSelectionSource.includes('qualityUsableFeatures'), false);
assert.equal(taskSelectionSource.includes('qualityConfidence'), false);
assert.equal(taskSelectionSource.includes('qualityRecordingSignal'), false);
assert.match(taskSelectionSource, /5 to 10 seconds/);
assert.match(taskSelectionSource, /isRepeatSignalReady/);
assert.match(taskSelectionSource, /ts-quality-blocking-overlay/);
assert.match(taskSelectionSource, /qualityBlockingTitle/);

const requiredTaskSelectionKeys = [
  'qualityKicker',
  'qualityRepeatTitle',
  'qualitySavedWarningTitle',
  'qualityCheckErrorTitle',
  'qualityCheckErrorBody',
  'qualityRepeatBody',
  'qualitySavedWarningBody',
  'qualityLivePlot',
  'qualityStageAdjustTitle',
  'qualityStageAdjustBody',
  'qualityStageStabilizeTitle',
  'qualityStageStabilizeBody',
  'qualityStageRepeatTitle',
  'qualityStageReadyBody',
  'qualityStageWaitingBody',
  'qualityKeepAttempt',
  'qualityRepeatButton',
  'qualityWaitingButton',
  'qualityBlockingBody',
  'qualityBlockingTitle',
  'qualityStabilizingButton',
  'qualityStageStabilizingBody',
];

for (const fileName of readdirSync(join(srcDir, 'locales')).filter(name => name.endsWith('.json'))) {
  const locale = JSON.parse(readFileSync(join(srcDir, 'locales', fileName), 'utf8'));
  for (const key of requiredTaskSelectionKeys) {
    assert.ok(locale.taskSelection?.[key], `${fileName} missing taskSelection.${key}`);
  }
  assert.match(locale.taskSelection.qualityStageStabilizeBody, /5\s*(?:to|-|a|bis)\s*10|5.*10/i);
}
