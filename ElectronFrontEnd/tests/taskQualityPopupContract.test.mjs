import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const srcDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const taskSelectionSource = readFileSync(join(srcDir, 'pages', 'TaskSelection.jsx'), 'utf8');

assert.equal(taskSelectionSource.includes('qualityUsableFeatures'), false);
assert.equal(taskSelectionSource.includes('qualityConfidence'), false);
assert.equal(taskSelectionSource.includes('qualityRecordingSignal'), false);
assert.match(taskSelectionSource, /20 contiguous clean seconds/);
assert.match(taskSelectionSource, /cannot be stitched together/);
assert.match(taskSelectionSource, /isRepeatSignalReady/);
assert.match(taskSelectionSource, /ts-quality-blocking-overlay/);
assert.doesNotMatch(taskSelectionSource, /accept_with_warning|qualityKeepAttempt/);
assert.match(taskSelectionSource, /completedIds\.includes\(selectedId\)[\s\S]*?taskIsUnlocked\(selectedId\)/);
assert.match(taskSelectionSource, /Completed · accepted attempt locked/);
assert.doesNotMatch(taskSelectionSource, /Run this form again/);

const requiredTaskSelectionKeys = [
  'qualityKicker',
  'qualityRepeatTitle',
  'qualityCheckErrorTitle',
  'qualityLivePlot',
];

for (const fileName of readdirSync(join(srcDir, 'locales')).filter(name => name.endsWith('.json'))) {
  const locale = JSON.parse(readFileSync(join(srcDir, 'locales', fileName), 'utf8'));
  for (const key of requiredTaskSelectionKeys) {
    assert.ok(locale.taskSelection?.[key], `${fileName} missing taskSelection.${key}`);
  }
}
