import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const serviceDir = dirname(fileURLToPath(import.meta.url));
const analysisSource = readFileSync(join(serviceDir, 'analysisService.js'), 'utf8');
const qualitySource = readFileSync(join(serviceDir, 'taskQualityGate.mjs'), 'utf8');

for (const source of [analysisSource, qualitySource]) {
  assert.match(source, /loadBaselineRecording\(['"]eyes_closed['"]/);
  assert.match(source, /loadBaselineRecording\(['"]eyes_open['"]/);
  assert.match(source, /protocol_profile:\s*PROTOCOL_PROFILE_METADATA/);
  assert.doesNotMatch(source, /readJson\([^\n]*calibrationData_eyes_/);
}

assert.match(analysisSource, /loadTaskRecording/);
assert.match(qualitySource, /loadTaskRecording/);
