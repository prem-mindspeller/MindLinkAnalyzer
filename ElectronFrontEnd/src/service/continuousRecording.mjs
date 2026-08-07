const REQUIRED_CHANNELS = ['fp1', 'fp2', 'o1', 'o2'];

const monotonicNow = () => (
  typeof globalThis.performance?.now === 'function'
    ? globalThis.performance.now()
    : Date.now()
);

const normalizeChannelKey = (value) => String(value || '')
  .trim()
  .toLowerCase()
  .replace(/[-_\s]/g, '');

export function isFourChannelSample(sample) {
  if (!sample || typeof sample !== 'object' || Array.isArray(sample)) return false;
  const source = sample.channels && typeof sample.channels === 'object'
    ? sample.channels
    : sample;
  const normalized = Object.fromEntries(
    Object.entries(source).map(([key, value]) => [normalizeChannelKey(key), value]),
  );
  return REQUIRED_CHANNELS.every((channel) => (
    Object.hasOwn(normalized, channel) && Number.isFinite(Number(normalized[channel]))
  ));
}

function safeSampleRate(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 32 && numeric <= 4096 ? numeric : 500;
}

/**
 * Collect four-channel WebSocket batches without hiding acquisition gaps.
 *
 * WebSocket delivery may be batched, so continuity is evaluated per batch:
 * a long arrival interval is accepted when the batch contains enough samples
 * to cover that interval. Otherwise a new transport segment is opened. The
 * backend analyses each resulting segment separately and therefore cannot
 * stitch short pre/post-dropout fragments into a false 20-second run.
 */
export function createFourChannelBatchCollector({
  sampleRateHz = 500,
  startedAtMs = monotonicNow(),
  now = monotonicNow,
  gapToleranceMs = 250,
} = {}) {
  const fs = safeSampleRate(sampleRateHz);
  const sampleIntervalMs = 1000 / fs;
  const entries = [];
  let lastArrivalMs = null;
  let syntheticEndMs = 0;
  let segmentId = -1;
  let forceNewSegment = true;
  let invalidSampleCount = 0;
  let lastStreamEndSampleIndex = null;

  const appendBatch = (
    samples,
    receivedAtMs = now(),
    streamStartSampleIndex = null,
  ) => {
    const batch = Array.isArray(samples) ? samples : [];
    if (!batch.length) return { appended: 0, rejected: 0, openedSegment: false };

    const numericStreamStart = Number(streamStartSampleIndex);
    const hasStreamPosition = (
      streamStartSampleIndex != null
      && Number.isInteger(numericStreamStart)
      && numericStreamStart >= 0
    );
    if (!batch.every(isFourChannelSample)) {
      invalidSampleCount += batch.length;
      forceNewSegment = true;
      lastArrivalMs = Number(receivedAtMs);
      lastStreamEndSampleIndex = hasStreamPosition
        ? numericStreamStart + batch.length
        : null;
      return { appended: 0, rejected: batch.length, openedSegment: false };
    }

    const arrivalMs = Number.isFinite(Number(receivedAtMs)) ? Number(receivedAtMs) : now();
    const coveredDurationMs = batch.length * sampleIntervalMs;
    const observedGapMs = lastArrivalMs == null ? 0 : Math.max(0, arrivalMs - lastArrivalMs);
    const hasComparableStreamPosition = (
      hasStreamPosition && lastStreamEndSampleIndex != null
    );
    const transportGap = hasComparableStreamPosition
      ? numericStreamStart !== lastStreamEndSampleIndex
      : (
        lastArrivalMs != null
        && observedGapMs > coveredDurationMs + Math.max(0, Number(gapToleranceMs) || 0)
      );
    const openedSegment = forceNewSegment || transportGap;

    if (openedSegment) segmentId += 1;
    const arrivalElapsedMs = Math.max(0, arrivalMs - Number(startedAtMs));
    const batchStartMs = openedSegment
      ? Math.max(0, arrivalElapsedMs - coveredDurationMs)
      : syntheticEndMs;

    batch.forEach((sample, index) => {
      entries.push({
        sample,
        elapsed_ms: batchStartMs + index * sampleIntervalMs,
        segment_id: segmentId,
      });
    });

    syntheticEndMs = batchStartMs + coveredDurationMs;
    lastArrivalMs = arrivalMs;
    lastStreamEndSampleIndex = hasStreamPosition
      ? numericStreamStart + batch.length
      : null;
    forceNewSegment = false;
    return { appended: batch.length, rejected: 0, openedSegment };
  };

  const markGap = () => {
    forceNewSegment = true;
  };

  const snapshot = ({ endBeforeMs = Number.POSITIVE_INFINITY } = {}) => {
    const selected = entries.filter((entry) => entry.elapsed_ms < endBeforeMs);
    const segments = [];

    selected.forEach((entry, index) => {
      let segment = segments.at(-1);
      if (!segment || segment.segment_id !== entry.segment_id) {
        segment = {
          segment_id: entry.segment_id,
          start_sample_index: index,
          end_sample_index_exclusive: index,
          start_elapsed_ms: Math.round(entry.elapsed_ms),
          end_elapsed_ms: Math.round(entry.elapsed_ms),
          sample_count: 0,
          duration_seconds: 0,
        };
        segments.push(segment);
      }
      segment.end_sample_index_exclusive = index + 1;
      segment.sample_count += 1;
      segment.end_elapsed_ms = Math.round(entry.elapsed_ms + sampleIntervalMs);
      segment.duration_seconds = Number((segment.sample_count / fs).toFixed(3));
    });

    const maxContiguousSeconds = segments.reduce(
      (maximum, segment) => Math.max(maximum, segment.duration_seconds),
      0,
    );
    return {
      samples: selected.map((entry) => entry.sample),
      entries: selected,
      transport_segments: segments,
      sample_rate_hz: fs,
      invalid_sample_count: invalidSampleCount,
      max_contiguous_transport_seconds: maxContiguousSeconds,
      transport_gap_count: Math.max(0, segments.length - 1),
    };
  };

  return {
    appendBatch,
    markGap,
    snapshot,
    get sampleCount() { return entries.length; },
  };
}
