import assert from 'node:assert/strict';
import { gunzipSync, gzipSync } from 'node:zlib';

import {
  createCompressedReportEnvelope,
  decodeReportEnvelope,
  uint8ArrayToBase64,
  base64ToUint8Array,
} from './reportEnvelope.mjs';

const reportText = JSON.stringify({
  feature_report_version: 'mindspeller_eeg_feature_report_v2',
  tasks: [{ canonical_task_id: 'mental_math' }],
});

const envelope = await createCompressedReportEnvelope(reportText, {
  contentType: 'application/json',
  now: () => new Date('2026-05-21T10:00:00.000Z'),
});

assert.equal(envelope.storage_format, 'gzip+base64+utf8');
assert.equal(envelope.content_type, 'application/json');
assert.equal(envelope.encoding, 'utf-8');
assert.equal(envelope.compression, 'gzip');
assert.equal(envelope.is_compressed, true);
assert.equal(envelope.is_base64, true);
assert.equal(envelope.original_size_bytes, new TextEncoder().encode(reportText).byteLength);
assert.ok(envelope.compressed_size_bytes < envelope.original_size_bytes);
assert.match(envelope.sha256, /^[a-f0-9]{64}$/);
assert.equal(envelope.generated_at, '2026-05-21T10:00:00.000Z');

const compressedBytes = Buffer.from(envelope.report_blob, 'base64');
assert.equal(compressedBytes[0], 0x1f);
assert.equal(compressedBytes[1], 0x8b);
const restoredText = gunzipSync(compressedBytes).toString('utf8');
assert.equal(restoredText, reportText);

assert.equal(uint8ArrayToBase64(new Uint8Array([77, 105, 110, 100])), 'TWluZA==');
assert.deepEqual(base64ToUint8Array('TWluZA=='), new Uint8Array([77, 105, 110, 100]));

// ---------------------------------------------------------------------------
// decodeReportEnvelope() -- the inverse direction. Round-trips against the
// exact envelope shape createCompressedReportEnvelope() produces, plus the
// three transport shapes eeg_report.decode_report_text() (backend) accepts:
// compressed+base64, base64-only, and plain text with no wrapper at all.
// ---------------------------------------------------------------------------

// Round-trip: encode with the real function, decode it back.
{
  const decoded = await decodeReportEnvelope(JSON.stringify({
    is_compressed: envelope.is_compressed,
    is_base64: envelope.is_base64,
    report_text: envelope.report_blob,
    report_sha256: envelope.sha256,
    encoding: envelope.encoding,
  }));
  assert.equal(decoded, reportText);
}

// A stored report the backend never compressed (plain text, no envelope at all).
{
  const plain = JSON.stringify({ feature_report_version: 'mindspeller_eeg_feature_report_v3', tasks: [] });
  const decoded = await decodeReportEnvelope(plain);
  assert.equal(decoded, plain);
}

// base64-only (is_base64 true, is_compressed false) -- decode_report_text()'s second branch.
{
  const innerText = JSON.stringify({ tasks: [{ canonical_task_id: 'adaptive_numerical_reasoning' }] });
  const envelopeStr = JSON.stringify({
    is_compressed: false,
    is_base64: true,
    report_text: Buffer.from(innerText, 'utf8').toString('base64'),
    encoding: 'utf-8',
  });
  const decoded = await decodeReportEnvelope(envelopeStr);
  assert.equal(decoded, innerText);
}

// Envelope built the way the backend's own DB row actually looks (gzipSync,
// not this module's own gzip path), to catch any format mismatch between
// the two independent implementations.
{
  const innerText = JSON.stringify({ tasks: [{ canonical_task_id: 'working_memory_manipulation', features: [] }] });
  const compressed = gzipSync(Buffer.from(innerText, 'utf8'));
  const envelopeStr = JSON.stringify({
    is_compressed: true,
    is_base64: true,
    report_text: compressed.toString('base64'),
    encoding: 'utf-8',
  });
  const decoded = await decodeReportEnvelope(envelopeStr);
  assert.equal(decoded, innerText);
}

// A sha256 mismatch must be caught, not silently accepted.
{
  const innerText = 'some report text';
  const compressed = gzipSync(Buffer.from(innerText, 'utf8'));
  const envelopeStr = JSON.stringify({
    is_compressed: true,
    is_base64: true,
    report_text: compressed.toString('base64'),
    report_sha256: 'not-the-real-hash',
  });
  await assert.rejects(() => decodeReportEnvelope(envelopeStr), /SHA-256 mismatch/);
}

// Falsy input -> null, not an error (callers treat this as "no prior data").
assert.equal(await decodeReportEnvelope(null), null);
assert.equal(await decodeReportEnvelope(''), null);

// Valid JSON that isn't the envelope shape (e.g. the report document
// itself, with no report_text key) -- returned unchanged rather than misread.
{
  const notAnEnvelope = JSON.stringify({ feature_report_version: 'mindspeller_eeg_feature_report_v3' });
  assert.equal(await decodeReportEnvelope(notAnEnvelope), notAnEnvelope);
}
