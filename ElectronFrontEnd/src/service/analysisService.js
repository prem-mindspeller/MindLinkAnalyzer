/**
 * analysisService.js
 *
 * Service layer for Step 9: Multi-Task Analysis & Report Seeding.
 *
 * Responsibilities:
 *   runAnalysis()   — Reads IndexedDB-backed baseline and task recordings and
 *                     POSTs them to the Python backend
 *                     POST /analyze, returning per-task p-values + effect sizes.
 *
 *   seedReport()    — Sends the analysis results to the Mindspeller REST API
 *                     POST /api/cas/brainlink_data, authenticated with the
 *                     JWT token stored by loginService.
 */
import loginService from './loginService';
import i18n from '../i18n';
import { createCompressedReportEnvelope } from './reportEnvelope.mjs';
import { buildNeuroprofileReportDocument } from './reportDocument.mjs';
import {
    buildSingleTaskAnalysisPayload,
    evaluateTaskQuality,
} from './taskQualityGate.mjs';
import {
    loadBaselineRecording,
    loadTaskRecording,
} from './recordingStore.mjs';
import {
    missingExpectedTaskIds,
    missingOrEmptyTaskRecordings,
    requiredBaselineConditionsForSession,
} from './analysisReadiness.mjs';
import {
    BATTERY_VERSION,
    resolveSessionDepth,
} from '../components/tasks/optimizedBatteryConfig.mjs';
import { PROTOCOL_PROFILE_METADATA } from '../components/tasks/optimizedBatteryProfile.mjs';

const BACKEND_HTTP = 'http://localhost:8000';

const API_ENDPOINTS = {
    en: 'https://en.mindspeller.com',
    nl: 'https://nl.mindspeller.com'
};

const TASK_NAMES = {
    adaptive_numerical_reasoning: 'Adaptive Numerical Reasoning and Sequencing',
    working_memory_manipulation: 'Working-Memory Manipulation',
    auditory_target_counting: 'Auditory Target Counting',
    semantic_induction_category_switching: 'Semantic Induction and Category Switching',
    visuospatial_transformation_orientation: 'Visuospatial Transformation and Orientation',
    divergent_ideation: 'Divergent Ideation',
    dual_task_rule_switching: 'Dual-Task Performance and Rule Switching',
    rule_based_anomaly_detection: 'Rule-Based Anomaly Detection',
    rapid_visual_comparison: 'Rapid Visual Comparison',
    pattern_closure_visual_noise: 'Pattern Closure under Visual Noise',
    speech_in_noise_comprehension: 'Speech-in-Noise Comprehension',
    written_comprehension_synthesis: 'Written Comprehension and Concise Synthesis',
};

function _loadCompletedIds(storage = globalThis.sessionStorage) {
    try {
        const ids = JSON.parse(storage?.getItem('completedTasks') || '[]');
        return Array.isArray(ids) ? ids : [];
    } catch {
        return [];
    }
}

function _loadBaselineMetadata(storage = globalThis.sessionStorage) {
    let summary;
    try {
        summary = JSON.parse(storage?.getItem('baselineCalibration') || '{}');
    } catch {
        return {};
    }

    if (!summary || typeof summary !== 'object' || Array.isArray(summary)) return {};
    const metadata = {};
    if (summary.eyesClosed && typeof summary.eyesClosed === 'object' && !Array.isArray(summary.eyesClosed)) {
        metadata.eyes_closed = summary.eyesClosed;
    }
    if (summary.eyesOpen && typeof summary.eyesOpen === 'object' && !Array.isArray(summary.eyesOpen)) {
        metadata.eyes_open = summary.eyesOpen;
    }
    return metadata;
}

/**
 * Run the multi-task EEG analysis.
 *
 * Reads baseline and task recordings from the asynchronous recording store,
 * then calls POST /analyze.
 *
 * Returns:
 *   {
 *     per_task: { [taskId]: { sample_count, band_means, p_value, significant, effect_size } },
 *     summary:  { significant_tasks, total_tasks, baseline_sample_count }
 *   }
 *
 * Throws on network/backend error.
 */
export async function runAnalysis({
    storage = globalThis.sessionStorage,
    fetchImpl = globalThis.fetch,
} = {}) {
    const completedIds = _loadCompletedIds(storage);
    const sessionDepth = resolveSessionDepth(storage);

    // Collect matched baseline samples from the same durable run namespace as
    // task recordings. loadBaselineRecording also migrates legacy Web Storage
    // arrays only after their IndexedDB copies commit.
    const [eyesClosedRecord, eyesOpenRecord] = await Promise.all([
        loadBaselineRecording('eyes_closed', storage),
        loadBaselineRecording('eyes_open', storage),
    ]);
    const baseline = {
        eyes_closed: Array.isArray(eyesClosedRecord?.samples) ? eyesClosedRecord.samples : [],
        eyes_open: Array.isArray(eyesOpenRecord?.samples) ? eyesOpenRecord.samples : [],
    };

    if (baseline.eyes_closed.length === 0 && baseline.eyes_open.length === 0) {
        throw new Error(i18n.t('errors.noBaselineData'));
    }

    const missingBaselines = requiredBaselineConditionsForSession(sessionDepth)
        .filter((condition) => !Array.isArray(baseline[condition]) || baseline[condition].length === 0);
    if (missingBaselines.length > 0) {
        throw new Error(`Matched baseline recording(s) are missing: ${missingBaselines.join(', ')}.`);
    }

    const manifestMetadata = _loadBaselineMetadata(storage);
    const baselineMetadata = {
        ...(eyesClosedRecord?.metadata || manifestMetadata.eyes_closed
            ? { eyes_closed: eyesClosedRecord?.metadata || manifestMetadata.eyes_closed }
            : {}),
        ...(eyesOpenRecord?.metadata || manifestMetadata.eyes_open
            ? { eyes_open: eyesOpenRecord?.metadata || manifestMetadata.eyes_open }
            : {}),
    };
    const incompatibleBaselines = requiredBaselineConditionsForSession(sessionDepth)
        .filter((condition) => baselineMetadata[condition]?.battery_version !== BATTERY_VERSION);
    if (incompatibleBaselines.length > 0) {
        throw new Error(
            `Matched baseline recording(s) do not belong to ${BATTERY_VERSION}: ${incompatibleBaselines.join(', ')}.`,
        );
    }

    const missingExpected = missingExpectedTaskIds(completedIds, sessionDepth);
    if (missingExpected.length > 0) {
        throw new Error(
            `Task battery is incomplete for ${sessionDepth}: missing completed task(s): ${missingExpected.join(', ')}.`,
        );
    }

    // Collect task samples
    const tasks = {};
    const taskMetadata = {};
    const recordingsByTask = new Map();
    for (const id of completedIds) {
        const recording = await loadTaskRecording(id, storage);
        recordingsByTask.set(id, recording);
        const samples = Array.isArray(recording?.samples) ? recording.samples : [];
        if (samples.length > 0) {
            tasks[id] = samples;
            if (recording?.metadata != null) taskMetadata[id] = recording.metadata;
        }
    }

    const missingRecordings = missingOrEmptyTaskRecordings(completedIds, recordingsByTask);
    if (missingRecordings.length > 0) {
        throw new Error(
            `Completed task recording(s) are missing or empty: ${missingRecordings.join(', ')}.`,
        );
    }

    if (Object.keys(tasks).length === 0) {
        throw new Error(i18n.t('errors.noTaskData'));
    }

    const analysisPayload = {
        baseline,
        tasks,
        protocol_profile: PROTOCOL_PROFILE_METADATA,
    };
    if (Object.keys(baselineMetadata).length > 0) {
        analysisPayload.baseline_metadata = baselineMetadata;
    }
    if (Object.keys(taskMetadata).length > 0) {
        analysisPayload.task_metadata = taskMetadata;
    }

    const res = await fetchImpl(`${BACKEND_HTTP}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(analysisPayload),
    });

    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(i18n.t('errors.analysisFailedStatus', { status: res.status, message: text }));
    }

    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (Array.isArray(data.invalid_tasks) && data.invalid_tasks.length > 0) {
        throw new Error(
            `Final analysis rejected invalid task recording(s): ${data.invalid_tasks.join(', ')}.`,
        );
    }


    const enriched = {};
    for (const [id, result] of Object.entries(data.per_task || {})) {
        enriched[id] = { ...result, name: i18n.t(`taskMeta.${id}.name`, { defaultValue: TASK_NAMES[id] || id }) };
    }

    return { ...data, per_task: enriched };
}

/**
 * Run a quick evidence check for one just-completed task.
 *
 * This reuses POST /analyze with the current baseline and only the new task
 * attempt. It does not write report data and does not alter the final upload
 * envelope.
 */
export async function runSingleTaskQualityCheck(taskId, samples = null, {
    signalStats = null,
    metadata = undefined,
    storage = globalThis.sessionStorage,
    fetchImpl = globalThis.fetch,
} = {}) {
    const payload = await buildSingleTaskAnalysisPayload(taskId, samples, storage, metadata);
    const resolvedSamples = payload.tasks?.[taskId] || [];

    if ((payload.baseline.eyes_closed.length === 0) && (payload.baseline.eyes_open.length === 0)) {
        throw new Error(i18n.t('errors.noBaselineData'));
    }
    if (!Array.isArray(resolvedSamples) || resolvedSamples.length === 0) {
        throw new Error(i18n.t('errors.noTaskData'));
    }

    const res = await fetchImpl(`${BACKEND_HTTP}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(i18n.t('errors.analysisFailedStatus', { status: res.status, message: text }));
    }

    const analysis = await res.json();
    if (analysis.error) throw new Error(analysis.error);

    return {
        analysis,
        quality: evaluateTaskQuality(analysis, taskId, { signalStats }),
    };
}

/**
 * Seed the analysis report to the Mindspeller API.
 *
 * @param {string} email          - user email to associate with the report
 * @param {'initial'|'advanced'} protocolType
 * @param {object} analysisResults - result of runAnalysis()
 *
 * Returns { success: true } or throws on error.
 */
export async function seedReport(email, protocolType, analysisResults) {
    const token = loginService.getToken();
    const region = loginService.getRegion();
    const baseUrl = API_ENDPOINTS[region] || API_ENDPOINTS.en;

    if (!token) throw new Error(i18n.t('errors.notAuthenticated'));

    const partnerId = sessionStorage.getItem('partnerId');
    // Generate session ID matching legacy format: session_YYYYMMDD_HHMMSS_xxxxxxxx
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const datePart = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
    const timePart = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
    const randPart = Math.random().toString(36).substring(2, 10);
    const sessionId = `session_${datePart}_${timePart}_${randPart}`;

    // Seed the canonical neuroprofile export as compressed JSON.
    const reportJson = buildNeuroprofileReportDocument(analysisResults);
    const reportEnvelope = await createCompressedReportEnvelope(reportJson, {
        contentType: 'application/json',
        now: () => now,
    });

    const taskCount = Object.keys(analysisResults.per_task || {}).length;

    const payload = {
        email,
        report_text: reportEnvelope.report_blob,
        is_base64: reportEnvelope.is_base64,
        is_compressed: reportEnvelope.is_compressed,
        compression: reportEnvelope.compression,
        storage_format: reportEnvelope.storage_format,
        content_type: reportEnvelope.content_type,
        encoding: reportEnvelope.encoding,
        original_size_bytes: reportEnvelope.original_size_bytes,
        compressed_size_bytes: reportEnvelope.compressed_size_bytes,
        report_sha256: reportEnvelope.sha256,
        protocol_type: protocolType,
        partner_id: partnerId,
        session_id: sessionId,
        generation_meta: {
            generated_at: now.toISOString(),
            analyzer_version: '1.0',
            workflow: 'electron_frontend',
            task_count: taskCount,
            report_contract: 'neuroprofile_feature_export',
            report_storage: {
                storage_format: reportEnvelope.storage_format,
                compression: reportEnvelope.compression,
                original_size_bytes: reportEnvelope.original_size_bytes,
                compressed_size_bytes: reportEnvelope.compressed_size_bytes,
                sha256: reportEnvelope.sha256,
            },
        },
    };

    const res = await fetch(`${baseUrl}/api/cas/eeg-reports/seed`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
    });

    // On 401, refresh the token once and retry
    if (res.status === 401) {
        await loginService.refreshToken();
        const newToken = loginService.getToken();
        if (!newToken) throw new Error(i18n.t('errors.sessionExpired'));

        const retryRes = await fetch(`${baseUrl}/api/cas/eeg-reports/seed`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Authorization': `Bearer ${newToken}`,
            },
            body: JSON.stringify(payload),
        });

        if (!retryRes.ok) {
            const text = await retryRes.text().catch(() => '');
            throw new Error(i18n.t('errors.seedingFailedStatus', { status: retryRes.status, message: text }));
        }
        return { success: true };
    }

    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(i18n.t('errors.seedingFailedStatus', { status: res.status, message: text }));
    }

    return { success: true };
}
