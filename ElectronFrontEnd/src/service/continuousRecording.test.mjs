import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createFourChannelBatchCollector,
  isFourChannelSample,
} from './continuousRecording.mjs';

const sample = (value) => ({ fp1: value, fp2: value, o1: value, o2: value });

test('requires the complete Fp1/Fp2/O1/O2 montage', () => {
  assert.equal(isFourChannelSample(sample(1)), true);
  assert.equal(isFourChannelSample({ fp1: 1, fp2: 1, o1: 1 }), false);
  assert.equal(isFourChannelSample({ fp1: 1, fp2: Number.NaN, o1: 1, o2: 1 }), false);
  assert.equal(isFourChannelSample({ fp1: 1, fp2: 'not-a-number', o1: 1, o2: 1 }), false);
  assert.equal(isFourChannelSample(42), false);
});

test('keeps covered batches continuous but exposes an uncovered transport gap', () => {
  const collector = createFourChannelBatchCollector({
    sampleRateHz: 100,
    startedAtMs: 0,
    gapToleranceMs: 50,
  });

  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index)), 1000);
  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index + 100)), 2000);
  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index + 200)), 5000);

  const snapshot = collector.snapshot();
  assert.equal(snapshot.samples.length, 300);
  assert.equal(snapshot.transport_segments.length, 2);
  assert.deepEqual(snapshot.transport_segments.map((segment) => segment.sample_count), [200, 100]);
  assert.equal(snapshot.max_contiguous_transport_seconds, 2);
  assert.equal(snapshot.transport_gap_count, 1);
});

test('uses acquisition sequence instead of delayed browser arrival time', () => {
  const collector = createFourChannelBatchCollector({
    sampleRateHz: 100,
    startedAtMs: 0,
    gapToleranceMs: 50,
  });

  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index)), 1000, 5000);
  // The renderer handles this queued message three seconds late, but the
  // acquisition indices prove that no samples were lost.
  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index + 100)), 4000, 5100);

  const snapshot = collector.snapshot();
  assert.equal(snapshot.transport_segments.length, 1);
  assert.equal(snapshot.max_contiguous_transport_seconds, 2);
  assert.equal(snapshot.transport_gap_count, 0);
});

test('opens a segment when acquisition sequence proves samples are missing', () => {
  const collector = createFourChannelBatchCollector({
    sampleRateHz: 100,
    startedAtMs: 0,
  });

  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index)), 1000, 5000);
  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index + 100)), 2000, 5200);

  const snapshot = collector.snapshot();
  assert.equal(snapshot.transport_segments.length, 2);
  assert.equal(snapshot.transport_gap_count, 1);
});

test('trimming a button response also clips transport segment indices', () => {
  const collector = createFourChannelBatchCollector({ sampleRateHz: 100, startedAtMs: 0 });
  collector.appendBatch(Array.from({ length: 300 }, (_, index) => sample(index)), 3000);

  const snapshot = collector.snapshot({ endBeforeMs: 2000 });
  assert.equal(snapshot.samples.length, 200);
  assert.equal(snapshot.transport_segments[0].start_sample_index, 0);
  assert.equal(snapshot.transport_segments[0].end_sample_index_exclusive, 200);
  assert.equal(snapshot.transport_segments[0].duration_seconds, 2);
});

test('invalid or partial-channel batches are rejected and break continuity', () => {
  const collector = createFourChannelBatchCollector({ sampleRateHz: 100, startedAtMs: 0 });
  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index)), 1000);
  collector.appendBatch([{ fp1: 1, fp2: 1, o1: 1 }], 1100);
  collector.appendBatch(Array.from({ length: 100 }, (_, index) => sample(index + 100)), 2100);

  const snapshot = collector.snapshot();
  assert.equal(snapshot.invalid_sample_count, 1);
  assert.equal(snapshot.transport_segments.length, 2);
});
