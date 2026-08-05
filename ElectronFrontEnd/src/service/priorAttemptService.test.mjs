import assert from 'node:assert/strict';

import {
  loadPriorTaskAttempts,
  taskEntriesByCanonicalId,
  _resetPriorAttemptCache,
} from './priorAttemptService.mjs';

const fakeAuth = { getToken: () => 'fake-jwt-token', getRegion: () => 'en' };
const loggedOutAuth = { getToken: () => null, getRegion: () => 'en' };

function jsonResponse(body, { ok = true, status = ok ? 200 : 500 } = {}) {
  return { ok, status, json: async () => body };
}

function routedFetch(routes) {
  return async (url) => {
    for (const [pattern, handler] of routes) {
      if (typeof pattern === 'string' ? url.includes(pattern) : pattern.test(url)) {
        return handler(url);
      }
    }
    throw new Error(`Unmocked fetch: ${url}`);
  };
}

function reportEnvelopeFor(taskEntries) {
  const report = { feature_report_version: 'mindspeller_eeg_feature_report_v3', tasks: taskEntries };
  // Plain (uncompressed) report_text, matching decode_report_text()'s "neither flag" branch.
  return JSON.stringify(report);
}

// ---------------------------------------------------------------------------
// taskEntriesByCanonicalId() -- pure reshape, no network involved.
// ---------------------------------------------------------------------------

{
  const report = {
    tasks: [
      { canonical_task_id: 'adaptive_numerical_reasoning', features: [{ metric_name: 'theta_power' }], signal_quality: { quality_level: 'high' } },
      { canonical_task_id: 'working_memory_manipulation', features: [] }, // empty features array is still valid
      { canonical_task_id: null, features: [{ metric_name: 'x' }] }, // no canonical_task_id -- skipped
      { features: [{ metric_name: 'x' }] }, // missing canonical_task_id entirely -- skipped
      { canonical_task_id: 'no_features_field' }, // features not an array -- skipped
    ],
  };
  const byId = taskEntriesByCanonicalId(report);
  assert.deepEqual(Object.keys(byId).sort(), ['adaptive_numerical_reasoning', 'working_memory_manipulation']);
  assert.deepEqual(byId.adaptive_numerical_reasoning.features, [{ metric_name: 'theta_power' }]);
  assert.deepEqual(byId.adaptive_numerical_reasoning.signal_quality, { quality_level: 'high' });
  assert.equal(byId.working_memory_manipulation.signal_quality, null);
}

assert.deepEqual(taskEntriesByCanonicalId({}), {});
assert.deepEqual(taskEntriesByCanonicalId(null), {});
assert.deepEqual(taskEntriesByCanonicalId({ tasks: 'not-an-array' }), {});

// ---------------------------------------------------------------------------
// loadPriorTaskAttempts() -- happy path
// ---------------------------------------------------------------------------

_resetPriorAttemptCache();
{
  const fetchImpl = routedFetch([
    ['/api/cas/users/current_user', async () => jsonResponse({ id: 42, email: 'candidate@example.com' })],
    ['/api/cas/eeg-reports/42/latest', async () => jsonResponse({
      status: 'success',
      report: { report_text: reportEnvelopeFor([
        { canonical_task_id: 'adaptive_numerical_reasoning', features: [{ metric_name: 'theta_power', direction: 'increase' }], signal_quality: { quality_level: 'high' } },
      ]) },
    })],
  ]);
  const result = await loadPriorTaskAttempts({ fetchImpl, ...fakeAuth });
  assert.deepEqual(Object.keys(result), ['adaptive_numerical_reasoning']);
  assert.equal(result.adaptive_numerical_reasoning.features[0].metric_name, 'theta_power');
}

// User id is cached -- a second call must not re-fetch current_user.
{
  let currentUserCalls = 0;
  const fetchImpl = routedFetch([
    ['/api/cas/users/current_user', async () => { currentUserCalls += 1; return jsonResponse({ id: 42 }); }],
    ['/api/cas/eeg-reports/42/latest', async () => jsonResponse({ report: { report_text: reportEnvelopeFor([]) } })],
  ]);
  await loadPriorTaskAttempts({ fetchImpl, ...fakeAuth });
  await loadPriorTaskAttempts({ fetchImpl, ...fakeAuth });
  assert.equal(currentUserCalls, 0, 'cached from the prior test case — current_user should not be re-fetched');
}

// ---------------------------------------------------------------------------
// Failure paths -- every one must resolve to {} rather than throw, since a
// prior-attempt lookup is a best-effort enhancement that must never block a
// new session from starting.
// ---------------------------------------------------------------------------

_resetPriorAttemptCache();
{
  // No token at all (e.g. logged out) -- must not attempt any fetch.
  const fetchImpl = async (url) => { throw new Error(`should not fetch: ${url}`); };
  const result = await loadPriorTaskAttempts({ fetchImpl, ...loggedOutAuth });
  assert.deepEqual(result, {});
}

_resetPriorAttemptCache();
{
  // current_user fetch fails outright.
  const fetchImpl = routedFetch([
    ['/api/cas/users/current_user', async () => { throw new Error('network down'); }],
  ]);
  assert.deepEqual(await loadPriorTaskAttempts({ fetchImpl, ...fakeAuth }), {});
}

_resetPriorAttemptCache();
{
  // current_user resolves but eeg-reports/latest 404s -- first-ever session.
  const fetchImpl = routedFetch([
    ['/api/cas/users/current_user', async () => jsonResponse({ id: 7 })],
    ['/api/cas/eeg-reports/7/latest', async () => jsonResponse({ message: 'No EEG report found for user' }, { ok: false, status: 404 })],
  ]);
  assert.deepEqual(await loadPriorTaskAttempts({ fetchImpl, ...fakeAuth }), {});
}

_resetPriorAttemptCache();
{
  // Stored report_text is corrupt (fails to decode/parse).
  const fetchImpl = routedFetch([
    ['/api/cas/users/current_user', async () => jsonResponse({ id: 7 })],
    ['/api/cas/eeg-reports/7/latest', async () => jsonResponse({
      report: { report_text: JSON.stringify({ is_compressed: true, is_base64: true, report_text: 'not-valid-base64-gzip!!!' }) },
    })],
  ]);
  assert.deepEqual(await loadPriorTaskAttempts({ fetchImpl, ...fakeAuth }), {});
}

_resetPriorAttemptCache();
{
  // report_text present but empty string.
  const fetchImpl = routedFetch([
    ['/api/cas/users/current_user', async () => jsonResponse({ id: 7 })],
    ['/api/cas/eeg-reports/7/latest', async () => jsonResponse({ report: { report_text: '' } })],
  ]);
  assert.deepEqual(await loadPriorTaskAttempts({ fetchImpl, ...fakeAuth }), {});
}

_resetPriorAttemptCache();
{
  // current_user response has no usable id.
  const fetchImpl = routedFetch([
    ['/api/cas/users/current_user', async () => jsonResponse({ email: 'candidate@example.com' })],
  ]);
  assert.deepEqual(await loadPriorTaskAttempts({ fetchImpl, ...fakeAuth }), {});
}

_resetPriorAttemptCache();
{
  // No getToken/getRegion supplied at all (defensive default handling).
  const fetchImpl = async (url) => { throw new Error(`should not fetch: ${url}`); };
  assert.deepEqual(await loadPriorTaskAttempts({ fetchImpl }), {});
}
