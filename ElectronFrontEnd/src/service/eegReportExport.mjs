/**
 * Builds the exact data analysisService.js's seedReport() sends to
 * POST /api/cas/eeg-reports/seed, and the exact string the backend stores in
 * brainlink_eeg_reports.report_text -- without performing the network call.
 *
 * Kept dependency-free (no loginService, no i18n) so it can be unit tested
 * under plain Node -- same reasoning as priorAttemptService.mjs: loginService
 * is bundler-resolved (extensionless import) and i18n resolves to a
 * directory, neither loadable by Node's native ESM loader.
 */
import { createCompressedReportEnvelope } from './reportEnvelope.mjs';
import { buildNeuroprofileReportDocument } from './reportDocument.mjs';

/**
 * Build the exact request body seedReport() POSTs to
 * /api/cas/eeg-reports/seed, without sending it. Factored out so the upload
 * path and any local export/debug path build byte-identical payloads instead
 * of two implementations silently drifting apart over time.
 *
 * @param {string} email
 * @param {'initial'|'advanced'} protocolType
 * @param {object} analysisResults - result of runAnalysis()
 * @param {{now?: () => Date, storage?: Storage}} [options]
 */
export async function buildEegReportSeedPayload(email, protocolType, analysisResults, options = {}) {
    const now = options.now ? options.now() : new Date();
    const storage = options.storage || globalThis.sessionStorage;
    const partnerId = storage?.getItem?.('partnerId');
    // Generate session ID matching legacy format: session_YYYYMMDD_HHMMSS_xxxxxxxx
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

    return {
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
}

/**
 * Reproduce the exact string cas_api_controllers/eeg_report.py's
 * seed_eeg_report() writes into brainlink_eeg_reports.report_text, from a
 * seed payload built by buildEegReportSeedPayload(). Mirrors that endpoint's
 * own wrap-in-envelope step exactly (see its comment: "Wrap compressed/base64
 * payloads in a JSON envelope so readers know how to decode. Plain-text
 * reports are stored as-is."). Used only for local export/debugging, since
 * the real column value is otherwise only ever visible server-side.
 */
export function reportTextColumnValueFor(seedPayload) {
    const { report_text: reportText, is_compressed: isCompressed, is_base64: isBase64 } = seedPayload;
    if (!isCompressed && !isBase64) return reportText;
    return JSON.stringify({
        is_compressed: isCompressed,
        is_base64: isBase64,
        report_text: reportText,
        report_sha256: seedPayload.report_sha256,
        encoding: seedPayload.encoding || 'utf-8',
    });
}

/**
 * Build the full local-export document: the exact seed request payload, the
 * exact report_text DB-column value, and enough context (task count, sizes,
 * hash) to sanity-check the export without re-decoding it. This is the object
 * that gets written to disk when a user downloads their upload data instead
 * of (or alongside) actually uploading it.
 */
export async function buildEegReportExportDocument(email, protocolType, analysisResults, options = {}) {
    const seedRequestBody = await buildEegReportSeedPayload(email, protocolType, analysisResults, options);
    return {
        export_contract: 'mindspeller_eeg_report_local_export_v1',
        exported_at: (options.now ? options.now() : new Date()).toISOString(),
        note: (
            'report_text_column_value is what cas_api_controllers/eeg_report.py '
            + 'writes into brainlink_eeg_reports.report_text for this exact upload -- '
            + 'insert it verbatim into that column to reproduce this upload without '
            + 'going through the real /api/cas/eeg-reports/seed endpoint.'
        ),
        report_text_column_value: reportTextColumnValueFor(seedRequestBody),
        seed_request_body: seedRequestBody,
    };
}
