/**
 * Client for the backend free-text rubric grader.
 *
 * Three tasks in the battery produce responses that no answer key can score:
 * Task 6 (ideas), Task 11 (paraphrase) and Task 12 (written summary). This
 * module posts those responses to the backend grader and returns an assessment
 * shaped for `runtime.rubricAssessment`, which the scorer then evaluates
 * against the battery profile's configured thresholds.
 *
 * Failure is always silent and always safe: a missing token, an offline
 * backend, a timeout, a mismatched rubric id or any malformed payload yields
 * `null`. The scorer treats a null assessment exactly as it treated the absence
 * of a grader — the dependent abilities stay `pending_review`. Grading never
 * blocks a participant from completing the battery.
 */

import { TASK_IDS, scoringRubricFor } from '../components/tasks/optimizedBatteryConfig.mjs';

// Mirrors the regional endpoint map already duplicated in wsEegService.js.
const API_ENDPOINTS = {
  en: 'https://en.mindspeller.com',
  nl: 'https://nl.mindspeller.com',
};

const GRADING_PATH = '/api/cas/brainlink/task_battery/grade_rubric';

// The participant is waiting on this call before their result is saved, so it
// is bounded aggressively; exceeding it simply leaves the abilities pending.
export const GRADING_TIMEOUT_MS = 20000;

/** Tasks whose scoring depends on a free-text rubric assessment. */
export const GRADED_TASK_IDS = Object.freeze([
  TASK_IDS.IDEATION,
  TASK_IDS.SPEECH_NOISE,
  TASK_IDS.WRITTEN,
]);

export const taskNeedsRubricGrading = (taskId) => GRADED_TASK_IDS.includes(taskId);

// Which response field carries the free text, and which form field is the
// source material the grader judges it against.
const GRADING_INPUTS = {
  [TASK_IDS.IDEATION]: { responseField: 'ideas', referenceField: 'prompt' },
  [TASK_IDS.SPEECH_NOISE]: { responseField: 'paraphrase', referenceField: 'passage' },
  [TASK_IDS.WRITTEN]: { responseField: 'summary', referenceField: 'passage' },
};

/**
 * Build the grading request body. Pure: no network, no globals.
 * @returns {object|null} null when the task is not graded or the text is blank.
 */
export function gradingRequestFor(taskId, form, response, profile) {
  const inputs = GRADING_INPUTS[taskId];
  if (!inputs) return null;

  const responseText = String(response?.[inputs.responseField] || '').trim();
  if (!responseText) return null;

  const rubric = scoringRubricFor(taskId, profile);
  const referenceValue = form?.[inputs.referenceField];

  const body = {
    canonical_task_id: taskId,
    rubric_id: rubric.id,
    response_text: responseText,
  };
  if (referenceValue) body.reference = { [inputs.referenceField]: String(referenceValue) };
  return body;
}

/**
 * Validate what the backend returned before it can influence scoring.
 * The rubric id must match the rubric this client actually applied, otherwise
 * scores graded against a different rubric could satisfy these thresholds.
 */
export function normalizeAssessment(payload, expectedRubricId) {
  const assessment = payload?.assessment;
  if (!assessment || typeof assessment !== 'object') return null;
  // Requiring expectedRubricId to be truthy (not just !==) closes the case
  // where both sides are null/undefined, which would otherwise "match" and
  // defeat the entire point of this check: proving the assessment was
  // actually graded against the rubric this client is about to score with.
  if (!expectedRubricId || assessment.rubricId !== expectedRubricId) return null;
  const scores = assessment.scores;
  if (!scores || typeof scores !== 'object' || Array.isArray(scores)) return null;
  if (!Object.keys(scores).length) return null;
  return { rubricId: assessment.rubricId, scores };
}

/**
 * Request a rubric assessment for one task response.
 * @returns {Promise<{rubricId: string, scores: object}|null>}
 */
export async function requestRubricAssessment(taskId, form, response, options = {}) {
  const {
    profile,
    fetchImpl = (typeof fetch === 'function' ? fetch : null),
    timeoutMs = GRADING_TIMEOUT_MS,
    storage = globalThis.sessionStorage,
  } = options;

  const body = gradingRequestFor(taskId, form, response, profile);
  if (!body || !fetchImpl) return null;

  // Read the session directly rather than importing loginService: that module
  // is bundler-resolved (extensionless .js) and would make this one unloadable
  // under plain Node, which the unit tests use. These are the same two keys
  // loginService.getToken()/getRegion() read.
  let token;
  let baseUrl;
  try {
    token = storage?.getItem?.('jwtToken');
    baseUrl = API_ENDPOINTS[storage?.getItem?.('region') || 'en'];
  } catch {
    return null;
  }
  if (!token || !baseUrl) return null;

  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = controller && timeoutMs
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;

  try {
    const res = await fetchImpl(`${baseUrl}${GRADING_PATH}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      signal: controller ? controller.signal : undefined,
    });
    if (!res?.ok) return null;
    const payload = await res.json();
    return normalizeAssessment(payload, body.rubric_id);
  } catch {
    // Offline, aborted, non-JSON — all mean "not graded".
    return null;
  } finally {
    if (timer) clearTimeout(timer);
  }
}
