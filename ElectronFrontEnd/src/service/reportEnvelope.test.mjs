import assert from 'node:assert/strict';
import { gunzipSync } from 'node:zlib';

import {
  createCompressedReportEnvelope,
  uint8ArrayToBase64,
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
