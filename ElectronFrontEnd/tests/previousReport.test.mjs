import assert from 'node:assert/strict';

import {
  createCompressedReportEnvelope,
  readCompressedReportEnvelope,
  readStoredReportJson,
} from '../src/service/reportEnvelope.mjs';
import { coveredTaskIds, fetchPreviousReport } from '../src/service/previousReport.mjs';

const REPORT = {
  protocol_session_depth: 'session_1',
  tasks: [
    { canonical_task_id: 'adaptive_numerical_reasoning', task_number: 1 },
    { canonical_task_id: 'working_memory_manipulation', task_number: 2 },
  ],
};

/** Build the exact string the seed endpoint writes into report_text. */
async function storedReportText(doc = REPORT, { omitFlags = false } = {}) {
  const env = await createCompressedReportEnvelope(JSON.stringify(doc), {
    contentType: 'application/json',
  });
  if (omitFlags) return JSON.stringify({ report_text: env.report_blob });
  return JSON.stringify({
    is_compressed: env.is_compressed,
    is_base64: env.is_base64,
    encoding: env.encoding,
    report_text: env.report_blob,
    report_sha256: env.sha256,
  });
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

// ── Envelope round-trip ─────────────────────────────────────────────────────

assert.deepEqual(await readStoredReportJson(await storedReportText()), REPORT);

// Uploads written before the format flags existed are detected by gzip magic.
assert.deepEqual(
  await readStoredReportJson(await storedReportText(REPORT, { omitFlags: true })),
  REPORT,
);

// An uncompressed report passes straight through.
assert.deepEqual(await readStoredReportJson(JSON.stringify(REPORT)), REPORT);

// ── Integrity is enforced, not advisory ─────────────────────────────────────

const tampered = JSON.parse(await storedReportText());
tampered.report_sha256 = 'not-the-real-digest';
await assert.rejects(
  () => readCompressedReportEnvelope(JSON.stringify(tampered)),
  /failed integrity check/,
  'a corrupt carried report must not be silently accepted as evidence',
);

// ── Fetching ────────────────────────────────────────────────────────────────

{
  const stored = await storedReportText();
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(200, {
      status: 'success',
      report: {
        id: 77,
        session_id: 'session_20260101_120000_abcd1234',
        protocol_type: 'initial',
        created_at: '2026-01-01T12:00:00',
        report_text: stored,
        generation_meta: { report_storage: { sha256: 'abc123' } },
      },
    });
  };

  const result = await fetchPreviousReport({
    baseUrl: 'https://en.mindspeller.com',
    token: 'tok',
    fetchImpl,
  });

  assert.equal(calls.length, 1);
  assert.ok(calls[0].url.endsWith('/api/cas/eeg-reports/latest/mine'));
  // The route resolves the user from the JWT; no id may appear in the URL.
  assert.ok(!/\d{2,}/.test(new URL(calls[0].url).pathname));
  assert.equal(calls[0].options.headers['X-Authorization'], 'Bearer tok');
  assert.deepEqual(result.report, REPORT);
  assert.equal(result.meta.report_id, 77);
  assert.equal(result.meta.sha256, 'abc123');
  assert.equal(result.meta.recorded_at, '2026-01-01T12:00:00');
}

// A participant with no earlier upload yields null, not an error: the caller
// decides whether that is expected.
assert.equal(
  await fetchPreviousReport({
    baseUrl: 'https://en.mindspeller.com',
    token: 'tok',
    fetchImpl: async () => jsonResponse(404, { status: 'error' }),
  }),
  null,
);

// A server error must never degrade into "no previous report".
await assert.rejects(
  () => fetchPreviousReport({
    baseUrl: 'https://en.mindspeller.com',
    token: 'tok',
    fetchImpl: async () => jsonResponse(500, { status: 'error' }),
  }),
  /HTTP 500/,
);

await assert.rejects(
  () => fetchPreviousReport({ baseUrl: 'https://en.mindspeller.com', token: null }),
  /Not authenticated/,
);

// ── Expired access token is refreshed once, as seedReport does ──────────────

{
  const stored = await storedReportText();
  const seen = [];
  const fetchImpl = async (url, options) => {
    seen.push(options.headers['X-Authorization']);
    if (options.headers['X-Authorization'] === 'Bearer stale') {
      return jsonResponse(401, { status: 'error' });
    }
    return jsonResponse(200, {
      status: 'success',
      report: { id: 1, report_text: stored },
    });
  };

  const result = await fetchPreviousReport({
    baseUrl: 'https://en.mindspeller.com',
    token: 'stale',
    fetchImpl,
    refreshToken: async () => 'fresh',
  });

  assert.deepEqual(seen, ['Bearer stale', 'Bearer fresh']);
  assert.deepEqual(result.report, REPORT);
}

// ── coveredTaskIds ──────────────────────────────────────────────────────────

assert.deepEqual(coveredTaskIds(REPORT), [
  'adaptive_numerical_reasoning',
  'working_memory_manipulation',
]);
assert.deepEqual(coveredTaskIds({ tasks_detected: REPORT.tasks }), [
  'adaptive_numerical_reasoning',
  'working_memory_manipulation',
]);
assert.deepEqual(coveredTaskIds(null), []);
assert.deepEqual(coveredTaskIds({ tasks: 'nope' }), []);

console.log('previousReport: all assertions passed');
