/**
 * priorAttemptService.mjs
 *
 * Fetches this user's most recently stored neuroprofile report from the
 * Mindspeller REST API and reshapes its per-task entries into the
 * `prior_attempt` payload POST /analyze accepts -- closing the loop opened
 * by neuroprofile_traceability._infer_repeat_status(): that function can
 * classify a task as repeated_stable/repeated_unstable, but only when a
 * caller supplies what the prior attempt looked like. The analyzer itself
 * is stateless and has no session history of its own (see
 * _compare_task_attempts()'s docstring) -- this module is that caller.
 *
 * Best-effort by design: a user's first-ever session has no prior report
 * (404), and a network hiccup or corrupt stored payload must never block
 * starting a new battery. Every failure path here resolves to {} (no
 * prior_attempt data), which is exactly today's behaviour before this
 * module existed -- repeat_status simply stays "not_repeated".
 *
 * Auth (getToken/getRegion) is injected by the caller rather than imported
 * from loginService.js directly, so this module has no dependency on that
 * singleton (or its own i18n import chain) and stays trivially testable in
 * isolation -- see analysisService.js for the real wiring, which passes
 * loginService's own getToken/getRegion through.
 */
import { decodeReportEnvelope } from './reportEnvelope.mjs';

const API_ENDPOINTS = {
    en: 'https://en.mindspeller.com',
    nl: 'https://nl.mindspeller.com',
};

let _cachedUserId = null;

function _baseUrl(getRegion) {
    return API_ENDPOINTS[getRegion?.()] || API_ENDPOINTS.en;
}

async function _fetchNumericUserId(fetchImpl, getToken, getRegion) {
    if (_cachedUserId != null) return _cachedUserId;
    const token = getToken?.();
    if (!token) return null;

    try {
        const res = await fetchImpl(`${_baseUrl(getRegion)}/api/cas/users/current_user`, {
            headers: { 'X-Authorization': `Bearer ${token}` },
        });
        if (!res.ok) return null;
        const data = await res.json();
        const id = data?.id;
        if (typeof id === 'number') _cachedUserId = id;
        return _cachedUserId;
    } catch {
        return null;
    }
}

/** Test-only: clear the cached user id between runs. */
export function _resetPriorAttemptCache() {
    _cachedUserId = null;
}

/**
 * Reshape a stored neuroprofile_feature_export's tasks[] into
 * { [canonical_task_id]: { features, signal_quality } }, the shape
 * MindLinkAnalyzer's build_neuroprofile_task_entry() expects for its
 * prior_attempt parameter (see _compare_task_attempts()).
 */
export function taskEntriesByCanonicalId(report) {
    const tasks = Array.isArray(report?.tasks) ? report.tasks : [];
    const byTaskId = {};
    for (const task of tasks) {
        const cid = task?.canonical_task_id;
        if (cid && Array.isArray(task?.features)) {
            byTaskId[cid] = {
                features: task.features,
                signal_quality: task.signal_quality || null,
            };
        }
    }
    return byTaskId;
}

/**
 * Fetch and decode this user's latest stored report, returning its task
 * entries ready to pass as POST /analyze's `prior_attempt` field.
 *
 * Never throws. Returns {} when there is no prior report (first session),
 * the user isn't authenticated, or anything about the fetch/decode fails.
 *
 * @param {object} options
 * @param {Function} options.fetchImpl
 * @param {Function} options.getToken - () => string|null, e.g. loginService.getToken
 * @param {Function} options.getRegion - () => 'en'|'nl', e.g. loginService.getRegion
 */
export async function loadPriorTaskAttempts({
    fetchImpl = globalThis.fetch,
    getToken,
    getRegion,
} = {}) {
    try {
        const userId = await _fetchNumericUserId(fetchImpl, getToken, getRegion);
        if (userId == null) return {};

        const token = getToken?.();
        if (!token) return {};

        const res = await fetchImpl(`${_baseUrl(getRegion)}/api/cas/eeg-reports/${userId}/latest`, {
            headers: { 'X-Authorization': `Bearer ${token}` },
        });
        if (!res.ok) return {}; // includes 404: no prior report yet

        const data = await res.json();
        const rawReportText = data?.report?.report_text;
        if (!rawReportText) return {};

        const decoded = await decodeReportEnvelope(rawReportText);
        if (!decoded) return {};

        const report = JSON.parse(decoded);
        return taskEntriesByCanonicalId(report);
    } catch {
        return {};
    }
}
