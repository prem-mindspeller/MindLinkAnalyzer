import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const srcDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

test('task and baseline record only explicit four-channel batches', () => {
  const sources = [
    readFileSync(join(srcDir, 'components', 'tasks', 'OptimizedBatteryTask.jsx'), 'utf8'),
    readFileSync(join(srcDir, 'pages', 'BaselineCalibration1.jsx'), 'utf8'),
  ];

  for (const source of sources) {
    assert.match(source, /rawMultiBatch/);
    assert.match(source, /createFourChannelBatchCollector/);
    assert.doesNotMatch(source, /wsEegService\.on\(['"]raw['"]/);
    assert.doesNotMatch(source, /wsEegService\.on\(['"]rawMulti['"]/);
  }
});

test('task metadata carries transport segments for backend no-stitch QC', () => {
  const source = readFileSync(
    join(srcDir, 'components', 'tasks', 'OptimizedBatteryTask.jsx'),
    'utf8',
  );
  assert.match(source, /transport_segments/);
  assert.match(source, /max_contiguous_transport_seconds/);
  assert.match(source, /required_channels/);
});

test('baseline raw samples commit through durable storage, not Web Storage', () => {
  const source = readFileSync(join(srcDir, 'pages', 'BaselineCalibration1.jsx'), 'utf8');

  assert.match(source, /await saveBaselineRecording/);
  assert.match(source, /baselineCalibration/);
  assert.doesNotMatch(source, /sessionStorage\.setItem\(['"]calibrationData_/);
  assert.match(source, /pendingBaselineSaveRef/);
  assert.match(source, /Retry storage/);
});

test('task audio audit is based on expected and actual delivery and fails closed', () => {
  const source = readFileSync(
    join(srcDir, 'components', 'tasks', 'OptimizedBatteryTask.jsx'),
    'utf8',
  );

  for (const contractToken of [
    'expectedSpeech',
    'expectedTones',
    'speech_playback_started',
    'speech_playback_ended',
    'tone_playback_started',
    'tone_playback_ended',
    'noise_playback_started',
    'noise_playback_ended_early',
    'protocol_complete',
    'protocol_valid',
  ]) {
    assert.match(source, new RegExp(contractToken));
  }
  assert.match(source, /context\.state !== 'running'/);
  assert.match(source, /audioAudit\.finalized = true/);
});

test('task runner consumes the versioned pilot profile instead of embedding resource rules', () => {
  const source = readFileSync(
    join(srcDir, 'components', 'tasks', 'OptimizedBatteryTask.jsx'),
    'utf8',
  );

  for (const contractToken of [
    'runnerProtocolFor',
    'taskPresentationFor',
    'audioProfileForTask',
    'scoringThresholdsFor',
    'protocolProfileRefForTask',
    'PROTOCOL_PROFILE_METADATA',
    'premixed_audio_asset',
    'protocol_profile_ref',
    'rubric_set_version',
    'threshold_set_version',
  ]) {
    assert.match(source, new RegExp(contractToken));
  }
  assert.doesNotMatch(source, /ENGLISH_SPEECH_LANGUAGE/);
  assert.doesNotMatch(source, /elapsedSeconds < 55/);
  assert.doesNotMatch(source, /research_candidate_not_normed/);
});

test('single-button tasks preserve the configured block timer and score only pre-response EEG', () => {
  const source = readFileSync(
    join(srcDir, 'components', 'tasks', 'OptimizedBatteryTask.jsx'),
    'utf8',
  );
  const detectionHandler = source.match(/const handleDetection = useCallback\(\(\) => \{[\s\S]*?\n  \}, \[[^\]]+\]\);/)?.[0] || '';

  assert.ok(detectionHandler);
  assert.doesNotMatch(detectionHandler, /finishRecording/);
  assert.match(detectionHandler, /buttonRuntimeRef\.current = runtime/);
  assert.match(source, /button_response_and_post_response_state/);
  assert.match(source, /snapshot\(\{ endBeforeMs: scoreEndMs \}\)/);
  assert.match(source, /elapsedMs >= definition\.duration \* 1000/);
});
