import assert from 'node:assert/strict';
import test from 'node:test';

import { TASK_IDS, scoringRubricFor, taskFormForSession } from '../components/tasks/optimizedBatteryConfig.mjs';
import {
  GRADED_TASK_IDS,
  gradingRequestFor,
  normalizeAssessment,
  requestRubricAssessment,
  taskNeedsRubricGrading,
} from './rubricGradingService.mjs';

const form = (taskId) => taskFormForSession(taskId, 'session_3');
const rubricId = (taskId) => scoringRubricFor(taskId).id;

const storage = (entries = { jwtToken: 'test-token', region: 'en' }) => ({
  getItem: (key) => (key in entries ? entries[key] : null),
});

const okResponse = (assessment) => ({
  ok: true,
  json: async () => ({ assessment }),
});

const RESPONSES = {
  [TASK_IDS.IDEATION]: { ideas: 'door stop\nplant marker' },
  [TASK_IDS.WRITTEN]: { summary: 'A coordinated design approach reduces urban heat.' },
};

// ---------------------------------------------------------------------------
// Which tasks are graded
// ---------------------------------------------------------------------------

test('exactly the two free-text tasks are graded', () => {
  assert.deepEqual([...GRADED_TASK_IDS].sort(), [
    TASK_IDS.IDEATION, TASK_IDS.WRITTEN,
  ].sort());
  assert.equal(taskNeedsRubricGrading(TASK_IDS.NUMERICAL), false);
  assert.equal(taskNeedsRubricGrading(TASK_IDS.DUAL_TASK), false);
  // Task 11's main idea and key detail are both selected from a fixed option
  // list and scored objectively, so it needs no rubric grading either.
  assert.equal(taskNeedsRubricGrading(TASK_IDS.SPEECH_NOISE), false);
});

// ---------------------------------------------------------------------------
// Request construction
// ---------------------------------------------------------------------------

test('each graded task sends its free text with the matching source material', () => {
  const ideation = gradingRequestFor(TASK_IDS.IDEATION, form(TASK_IDS.IDEATION), RESPONSES[TASK_IDS.IDEATION]);
  assert.equal(ideation.canonical_task_id, TASK_IDS.IDEATION);
  assert.equal(ideation.rubric_id, rubricId(TASK_IDS.IDEATION));
  assert.match(ideation.response_text, /door stop/);
  assert.ok(ideation.reference.prompt, 'ideation is judged against its prompt');

  const written = gradingRequestFor(TASK_IDS.WRITTEN, form(TASK_IDS.WRITTEN), RESPONSES[TASK_IDS.WRITTEN]);
  assert.ok(written.reference.passage, 'the summary is judged against the read passage');
});

test('the request rubric id always matches the rubric the client will score with', () => {
  for (const taskId of GRADED_TASK_IDS) {
    const body = gradingRequestFor(taskId, form(taskId), RESPONSES[taskId]);
    assert.equal(body.rubric_id, rubricId(taskId));
  }
});

test('ungraded tasks and blank text produce no request', () => {
  assert.equal(gradingRequestFor(TASK_IDS.NUMERICAL, form(TASK_IDS.NUMERICAL), { finalValue: 5 }), null);
  for (const blank of [undefined, null, '', '   ']) {
    assert.equal(gradingRequestFor(TASK_IDS.WRITTEN, form(TASK_IDS.WRITTEN), { summary: blank }), null);
  }
});

// ---------------------------------------------------------------------------
// Response validation
// ---------------------------------------------------------------------------

test('an assessment is accepted only when its rubric id matches', () => {
  const good = normalizeAssessment({ assessment: { rubricId: 'r1', scores: { clarity: 4 } } }, 'r1');
  assert.deepEqual(good, { rubricId: 'r1', scores: { clarity: 4 } });

  // Scores graded against a different rubric must not satisfy these thresholds.
  assert.equal(normalizeAssessment({ assessment: { rubricId: 'other', scores: { clarity: 4 } } }, 'r1'), null);
});

test('a falsy expected rubric id can never accidentally match a falsy payload id', () => {
  // Both-sides-falsy must not "match": that would defeat the entire point of
  // the check, which is proving the assessment was graded against a real,
  // specific rubric -- not merely that neither side named one.
  assert.equal(normalizeAssessment({ assessment: { rubricId: null, scores: { a: 1 } } }, null), null);
  assert.equal(normalizeAssessment({ assessment: { scores: { a: 1 } } }, undefined), null);
  assert.equal(normalizeAssessment({ assessment: { rubricId: '', scores: { a: 1 } } }, ''), null);
});

test('malformed assessments are rejected', () => {
  for (const payload of [
    null,
    {},
    { assessment: null },
    { assessment: { rubricId: 'r1' } },
    { assessment: { rubricId: 'r1', scores: null } },
    { assessment: { rubricId: 'r1', scores: [] } },
    { assessment: { rubricId: 'r1', scores: {} } },
    { assessment: { rubricId: 'r1', scores: 'good' } },
  ]) {
    assert.equal(normalizeAssessment(payload, 'r1'), null, `should reject ${JSON.stringify(payload)}`);
  }
});

// ---------------------------------------------------------------------------
// Network behaviour — every failure mode must degrade to null, never throw
// ---------------------------------------------------------------------------

test('a successful grade returns the assessment', async () => {
  const taskId = TASK_IDS.WRITTEN;
  const scores = { clarity: 4, coherence: 4, completeness: 3, information_ordering: 3 };
  const result = await requestRubricAssessment(taskId, form(taskId), RESPONSES[taskId], {
    storage: storage(),
    fetchImpl: async () => okResponse({ rubricId: rubricId(taskId), scores }),
  });
  assert.deepEqual(result, { rubricId: rubricId(taskId), scores });
});

test('the request is authenticated and posted as JSON', async () => {
  const taskId = TASK_IDS.IDEATION;
  let captured = null;
  await requestRubricAssessment(taskId, form(taskId), RESPONSES[taskId], {
    storage: storage(),
    fetchImpl: async (url, init) => {
      captured = { url, init };
      return okResponse({ rubricId: rubricId(taskId), scores: { relevantIdeaCount: 5 } });
    },
  });
  assert.match(captured.url, /^https:\/\/en\.mindspeller\.com\/api\/cas\/brainlink\/task_battery\/grade_rubric$/);
  assert.equal(captured.init.method, 'POST');
  assert.equal(captured.init.headers['X-Authorization'], 'Bearer test-token');
  assert.equal(JSON.parse(captured.init.body).canonical_task_id, taskId);
});

test('the regional endpoint follows the stored region', async () => {
  const taskId = TASK_IDS.IDEATION;
  let url = null;
  await requestRubricAssessment(taskId, form(taskId), RESPONSES[taskId], {
    storage: storage({ jwtToken: 't', region: 'nl' }),
    fetchImpl: async (requestUrl) => {
      url = requestUrl;
      return okResponse({ rubricId: rubricId(taskId), scores: { relevantIdeaCount: 5 } });
    },
  });
  assert.match(url, /^https:\/\/nl\.mindspeller\.com\//);
});

test('grading is skipped without a session token', async () => {
  const taskId = TASK_IDS.WRITTEN;
  let called = false;
  const result = await requestRubricAssessment(taskId, form(taskId), RESPONSES[taskId], {
    storage: storage({ region: 'en' }),
    fetchImpl: async () => { called = true; return okResponse({}); },
  });
  assert.equal(result, null);
  assert.equal(called, false, 'an unauthenticated grade must not be attempted');
});

test('every transport failure degrades to null instead of throwing', async () => {
  const taskId = TASK_IDS.WRITTEN;
  const cases = [
    ['network error', async () => { throw new Error('offline'); }],
    ['http error', async () => ({ ok: false, json: async () => ({}) })],
    ['non-json body', async () => ({ ok: true, json: async () => { throw new Error('bad json'); } })],
    ['null assessment', async () => okResponse(null)],
    ['mismatched rubric', async () => okResponse({ rubricId: 'someone_elses_rubric', scores: { clarity: 5 } })],
  ];
  for (const [label, fetchImpl] of cases) {
    const result = await requestRubricAssessment(taskId, form(taskId), RESPONSES[taskId], {
      storage: storage(), fetchImpl,
    });
    assert.equal(result, null, `${label} should yield null`);
  }
});

test('a hung grader is abandoned rather than blocking the participant', async () => {
  const taskId = TASK_IDS.WRITTEN;
  const started = Date.now();
  const result = await requestRubricAssessment(taskId, form(taskId), RESPONSES[taskId], {
    storage: storage(),
    timeoutMs: 40,
    fetchImpl: (url, init) => new Promise((resolve, reject) => {
      // Never resolves on its own; only the abort signal ends it.
      init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
    }),
  });
  assert.equal(result, null);
  assert.ok(Date.now() - started < 2000, 'must not wait indefinitely');
});
