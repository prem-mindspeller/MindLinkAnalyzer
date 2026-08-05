/**
 * Tests for eegReportExport.mjs's buildEegReportSeedPayload() /
 * reportTextColumnValueFor() / buildEegReportExportDocument() -- the
 * local-export path a user can trigger to download exactly what would be
 * sent to POST /api/cas/eeg-reports/seed and exactly what ends up stored in
 * brainlink_eeg_reports.report_text, without performing the real upload.
 *
 * The real DB-column value is only ever visible server-side (built by
 * cas_api_controllers/eeg_report.py's seed_eeg_report(), lines ~299-309:
 * "Wrap compressed/base64 payloads in a JSON envelope so readers know how to
 * decode."). reportTextColumnValueFor() mirrors that exact transform, so this
 * file pins the contract between the two codebases: if either side's wrap
 * shape changes, this test -- not a real user's export -- should be what
 * breaks first.
 *
 * Run:
 *   node --test src/service/eegReportExport.test.mjs
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import { gunzipSync } from 'node:zlib';

import {
  buildEegReportSeedPayload,
  reportTextColumnValueFor,
  buildEegReportExportDocument,
} from './eegReportExport.mjs';

const NOW = new Date('2026-08-05T12:00:00.000Z');

function fakeStorage(values = {}) {
  return { getItem: (key) => (key in values ? values[key] : null) };
}

// buildNeuroprofileReportDocument() (reportDocument.mjs) reads
// analysisResults.neuroprofile_feature_export -- the actual
// mindspeller_eeg_feature_report_v3 dict /analyze returns, not the
// per_task/summary shape runAnalysis() also carries alongside it.
function sampleAnalysisResults() {
  return {
    neuroprofile_feature_export: {
      feature_report_version: 'mindspeller_eeg_feature_report_v3',
      protocol_session_depth: 'session_3',
      global_reliability: 'high',
      tasks: [
        { task_number: 1, canonical_task_id: 'adaptive_numerical_reasoning', features: [] },
        { task_number: 10, canonical_task_id: 'pattern_closure_visual_noise', features: [] },
      ],
    },
    per_task: {
      adaptive_numerical_reasoning: { sample_count: 100, p_value: 0.01, significant: true, effect_size: 1.1 },
      pattern_closure_visual_noise: { sample_count: 100, p_value: 0.2, significant: false, effect_size: 0.1 },
    },
    summary: { significant_tasks: 1, total_tasks: 2, baseline_sample_count: 200 },
  };
}

test('buildEegReportSeedPayload produces the same shape seedReport() POSTs', async () => {
  const payload = await buildEegReportSeedPayload(
    'user@example.com', 'advanced', sampleAnalysisResults(),
    { now: () => NOW, storage: fakeStorage({ partnerId: '42' }) },
  );

  assert.equal(payload.email, 'user@example.com');
  assert.equal(payload.protocol_type, 'advanced');
  assert.equal(payload.partner_id, '42');
  assert.equal(payload.is_compressed, true);
  assert.equal(payload.is_base64, true);
  assert.equal(payload.compression, 'gzip');
  assert.match(payload.session_id, /^session_\d{8}_\d{6}_[a-z0-9]{8}$/);
  assert.equal(typeof payload.report_text, 'string');
  assert.equal(typeof payload.report_sha256, 'string');
  assert.equal(payload.generation_meta.task_count, 2);
});

test('reportTextColumnValueFor mirrors the backend\'s exact envelope wrap', async () => {
  const payload = await buildEegReportSeedPayload(
    'user@example.com', 'advanced', sampleAnalysisResults(),
    { now: () => NOW, storage: fakeStorage() },
  );
  const columnValue = reportTextColumnValueFor(payload);

  // Must be the JSON envelope shape decodeReportEnvelope()/decode_report_text()
  // on both sides expect: {is_compressed, is_base64, report_text, report_sha256, encoding}.
  const parsed = JSON.parse(columnValue);
  assert.equal(parsed.is_compressed, true);
  assert.equal(parsed.is_base64, true);
  assert.equal(parsed.report_text, payload.report_text);
  assert.equal(parsed.report_sha256, payload.report_sha256);
  assert.equal(parsed.encoding, 'utf-8');
});

test('the column value actually decodes back to the real neuroprofile export JSON', async () => {
  // End-to-end proof, not just shape-checking: base64-decode -> gunzip -> the
  // exact bytes must parse as the mindspeller_eeg_feature_report_v3 the
  // analyzer built, byte-for-byte reproducible from what's downloaded.
  const payload = await buildEegReportSeedPayload(
    'user@example.com', 'advanced', sampleAnalysisResults(),
    { now: () => NOW, storage: fakeStorage() },
  );
  const columnValue = reportTextColumnValueFor(payload);
  const envelope = JSON.parse(columnValue);

  const compressedBytes = Buffer.from(envelope.report_text, 'base64');
  const decompressed = gunzipSync(compressedBytes).toString('utf-8');
  const report = JSON.parse(decompressed);

  assert.equal(report.feature_report_version, 'mindspeller_eeg_feature_report_v3');
  assert.ok(Array.isArray(report.tasks));
  assert.equal(report.tasks.length, 2);

  const { createHash } = await import('node:crypto');
  const actualSha256 = createHash('sha256').update(decompressed, 'utf-8').digest('hex');
  assert.equal(actualSha256, envelope.report_sha256, 'sha256 must match the decoded plaintext exactly');
});

test('a plain-text (uncompressed) payload passes through reportTextColumnValueFor unchanged', () => {
  // Mirrors the backend's own branch: "Plain-text reports are stored as-is."
  const plain = { report_text: 'plain report body', is_compressed: false, is_base64: false };
  assert.equal(reportTextColumnValueFor(plain), 'plain report body');
});

test('missing partner_id/storage does not throw', async () => {
  const payload = await buildEegReportSeedPayload(
    'user@example.com', 'initial', sampleAnalysisResults(),
    { now: () => NOW, storage: null },
  );
  assert.equal(payload.partner_id, undefined);
});

test('buildEegReportExportDocument bundles the column value with full traceability context', async () => {
  const doc = await buildEegReportExportDocument(
    'user@example.com', 'advanced', sampleAnalysisResults(),
    { now: () => NOW, storage: fakeStorage({ partnerId: '42' }) },
  );

  assert.equal(doc.export_contract, 'mindspeller_eeg_report_local_export_v1');
  assert.equal(doc.exported_at, NOW.toISOString());
  assert.equal(typeof doc.report_text_column_value, 'string');
  assert.deepEqual(
    JSON.parse(doc.report_text_column_value),
    JSON.parse(reportTextColumnValueFor(doc.seed_request_body)),
    'the bundled column value must match what reportTextColumnValueFor derives from the same request body',
  );
  assert.equal(doc.seed_request_body.protocol_type, 'advanced');
  assert.equal(doc.seed_request_body.partner_id, '42');
});

test('session_id is unique per call', async () => {
  const results = sampleAnalysisResults();
  const a = await buildEegReportSeedPayload('a@example.com', 'initial', results, { now: () => NOW, storage: fakeStorage() });
  const b = await buildEegReportSeedPayload('a@example.com', 'initial', results, { now: () => NOW, storage: fakeStorage() });
  assert.notEqual(a.session_id, b.session_id, 'the random suffix must differ even within the same millisecond');
});
