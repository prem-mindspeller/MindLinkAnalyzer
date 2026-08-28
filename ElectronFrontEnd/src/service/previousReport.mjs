import { readStoredReportJson } from './reportEnvelope.mjs';

/**
 * Fetch and decode the participant's previous EEG upload.
 *
 * Needed when a run waives repetition: the battery then records only the tasks
 * the session introduces, and the previous upload holds the earlier ones. The
 * route resolves the user from the JWT, so no user id is needed here.
 *
 * @returns {Promise<{report: object, meta: object}|null>} null when the
 *   participant has no previous upload.
 * @throws when the request fails or the stored report cannot be decoded --
 *   never returns a partial result, because the caller uses this to decide
 *   whether a complete battery can be assembled.
 */
export async function fetchPreviousReport({
  baseUrl,
  token,
  fetchImpl = globalThis.fetch,
  refreshToken = null,
} = {}) {
  if (!token) throw new Error('Not authenticated; cannot load the previous report.');

  const request = (bearer) => fetchImpl(`${baseUrl}/api/cas/eeg-reports/latest/mine`, {
    method: 'GET',
    headers: {
      'X-Authorization': `Bearer ${bearer}`,
      Accept: 'application/json',
    },
  });

  let res = await request(token);

  // Mirror seedReport: a battery run can outlive the access token, so refresh
  // once before treating this as a failure.
  if (res.status === 401 && typeof refreshToken === 'function') {
    const refreshed = await refreshToken();
    if (refreshed) res = await request(refreshed);
  }

  // No previous upload at all. Distinct from a failure: the caller decides
  // whether that is expected (Session 1) or a problem (repetition waived).
  if (res.status === 404) return null;

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Could not load the previous report (HTTP ${res.status}). ${detail}`.trim());
  }

  const body = await res.json();
  const stored = body?.report?.report_text;
  if (!stored) throw new Error('The previous report response contained no report content.');

  const report = await readStoredReportJson(stored);

  return {
    report,
    meta: {
      report_id: body.report.id ?? null,
      session_id: body.report.session_id ?? null,
      recorded_at: body.report.created_at ?? null,
      protocol_type: body.report.protocol_type ?? null,
      sha256: body.report.generation_meta?.report_storage?.sha256 ?? null,
    },
  };
}

/**
 * Summarise which canonical tasks a decoded report covers.
 * Used to report a still-incomplete battery in terms the participant's
 * operator can act on, rather than a bare task count.
 */
export function coveredTaskIds(report) {
  const tasks = report?.tasks || report?.tasks_detected || [];
  if (!Array.isArray(tasks)) return [];
  return [...new Set(
    tasks
      .map((task) => task?.canonical_task_id)
      .filter((id) => typeof id === 'string' && id.length > 0),
  )];
}
