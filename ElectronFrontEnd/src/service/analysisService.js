/**
 * analysisService.js
 *
 * Service layer for Step 9: Multi-Task Analysis & Report Seeding.
 *
 * Responsibilities:
 *   runAnalysis()   — Reads baseline + task band-power samples from
 *                     sessionStorage and POSTs them to the Python backend
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

const BACKEND_HTTP = 'http://localhost:8000';

const API_ENDPOINTS = {
    en: 'https://en.mindspeller.com',
    nl: 'https://nl.mindspeller.com'
};

const TASK_NAMES = {
    visual_imagery: 'Visual Imagery',
    attention_focus: 'Focused Attention',
    mental_math: 'Mental Math',
    emotion_face: 'Emotion Recognition',
    working_memory: 'Working Memory',
    language_processing: 'Language Processing',
    motor_imagery: 'Motor Imagery',
    cognitive_load: 'Cognitive Load',
    diverse_thinking: 'Creative Fluency',
    reappraisal: 'Perspective Shift',
    curiosity: 'Curiosity Reveal',
    num_form: 'Numerical Preference',
    order_surprise: 'Order & Surprise',
    semantic_memory: 'Semantic Memory Retrieval',
    body_scan: 'Body Scan',
    color_perception: 'Color Perception',
};

/**
 * Read band-power samples stored by TaskSelection for a given key.
 * Returns [] when nothing is stored.
 */
function _loadSamples(sessionKey) {
    try {
        return JSON.parse(sessionStorage.getItem(sessionKey) || '[]');
    } catch {
        return [];
    }
}

/**
 * Run the multi-task EEG analysis.
 *
 * Reads baseline + completed-task data from sessionStorage and calls the
 * Python backend's POST /analyze endpoint.
 *
 * Returns:
 *   {
 *     per_task: { [taskId]: { sample_count, band_means, p_value, significant, effect_size } },
 *     summary:  { significant_tasks, total_tasks, baseline_sample_count }
 *   }
 *
 * Throws on network/backend error.
 */
export async function runAnalysis() {
    const completedIds = JSON.parse(sessionStorage.getItem('completedTasks') || '[]');

    // Collect baseline samples (eyes-closed and eyes-open recorded by BaselineCalibration)
    const baseline = {
        eyes_closed: _loadSamples('calibrationData_eyes_closed'),
        eyes_open: _loadSamples('calibrationData_eyes_open'),
    };

    if (baseline.eyes_closed.length === 0 && baseline.eyes_open.length === 0) {
        throw new Error(i18n.t('errors.noBaselineData'));
    }

    // Collect task samples
    const tasks = {};
    for (const id of completedIds) {
        const samples = _loadSamples(`taskData_${id}`);
        if (samples.length > 0) {
            tasks[id] = samples;
        }
    }

    if (Object.keys(tasks).length === 0) {
        throw new Error(i18n.t('errors.noTaskData'));
    }

    const res = await fetch(`${BACKEND_HTTP}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseline, tasks }),
    });

    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(i18n.t('errors.analysisFailedStatus', { status: res.status, message: text }));
    }

    const data = await res.json();
    if (data.error) throw new Error(data.error);


    const enriched = {};
    for (const [id, result] of Object.entries(data.per_task || {})) {
        enriched[id] = { ...result, name: i18n.t(`taskMeta.${id}.name`, { defaultValue: TASK_NAMES[id] || id }) };
    }

    return { ...data, per_task: enriched };
}

/**
 * Seed the analysis report to the Mindspeller API.
 *
 * @param {string} email          — user email to associate with the report
 * @param {'initial'|'advanced'} protocolType
 * @param {object} analysisResults — result of runAnalysis()
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

/**
 * Generate a plain-text report matching the legacy
 * EnhancedBrainLinkAnalyzerWindow.generate_report_all_tasks() format exactly.
 */
export function buildReportText(analysisResults) {
    const res = analysisResults;

    // Helper: format a value like Python's {:.6g}
    function fmt(v, none = 'NA') {
        if (v === null || v === undefined) return none;
        if (typeof v === 'number') {
            if (isNaN(v)) return none;
            return parseFloat(v.toPrecision(6)).toString();
        }
        return String(v);
    }

    const lines = [];

    // ── Header ────────────────────────────────────────────────────────────────
    lines.push('Mindlink Enhanced Multi-Task Analysis Report');
    lines.push('='.repeat(72));
    lines.push(`UTC Timestamp: ${new Date().toISOString()}`);

    const baselineKept = res.baseline_kept ?? 0;
    const ecSamplesRaw = res.ec_samples_raw ?? baselineKept;
    const baselineRej = res.baseline_rejected ?? 0;
    const rejNW = res.baseline_rejected_not_worn ?? 0;
    const rejArt = res.baseline_rejected_artifact ?? 0;
    const rejFL = res.baseline_rejected_flatline ?? 0;
    const eoWindows = res.eo_windows ?? 0;
    const taskCount = Object.keys(res.per_task || {}).length;
    const totalECSeen = baselineKept + baselineRej;
    const notWornRate = totalECSeen > 0 ? rejNW / totalECSeen : 0;

    lines.push(`Baseline EC samples: ${ecSamplesRaw} | EO samples: ${eoWindows}`);
    lines.push(`Tasks executed: ${taskCount}`);
    lines.push(`EC QC: kept=${baselineKept}, rejected=${baselineRej} (not_worn=${rejNW}, artifact=${rejArt}, flatline=${rejFL})`);
    if (res.ec_median_mad != null) {
        lines.push(`EC accepted-window median MAD-scale: ${fmt(res.ec_median_mad)} µV`);
    }
    lines.push('');

    // ── Data Quality ──────────────────────────────────────────────────────────
    lines.push('Data Quality Assessment');
    lines.push('-'.repeat(40));

    if (notWornRate >= 0.90) {
        lines.push('⚠️  WARNING: HEADSET LIKELY NOT WORN');
        lines.push(`   ${rejNW}/${totalECSeen} EC windows (${Math.round(notWornRate * 100)}%) rejected as 'not worn'`);
        lines.push('   Signal spread was consistently above the not-worn threshold.');
        lines.push('   All analysis results in this report are INVALID.');
        lines.push('   Please repeat the session with the headset properly worn.');
    } else if (notWornRate >= 0.50) {
        lines.push('⚠️  CAUTION: HIGH NOT-WORN REJECTION RATE');
        lines.push(`   ${rejNW}/${totalECSeen} EC windows (${Math.round(notWornRate * 100)}%) rejected as 'not worn'.`);
        lines.push('   Headset may have been partially worn or frequently displaced.');
        lines.push('   Analysis results should be interpreted with caution.');
    } else if (baselineKept === 0 && totalECSeen > 0) {
        lines.push('⚠️  WARNING: NO VALID EC BASELINE WINDOWS');
        lines.push('   All eyes-closed windows were rejected during quality control.');
        lines.push('   Analysis results are unreliable.');
    } else {
        lines.push('✅  Data quality: OK');
        if (res.ec_median_mad != null) {
            lines.push(`   Median EC noise floor: ${fmt(res.ec_median_mad)} µV`);
        }
    }

    lines.push('');
    lines.push('Per-Task Statistical Summaries');
    lines.push('-'.repeat(40));

    // ── Per-task results ──────────────────────────────────────────────────────
    const perTask = res.per_task || {};
    for (const tname of Object.keys(perTask).sort()) {
        const tinfo = perTask[tname] || {};
        const summary = tinfo.summary || {};
        const fisher = summary.fisher || {};
        const sumP = summary.sum_p || {};
        const comp = summary.composite || {};
        const decision = summary.feature_selection || {};

        lines.push(`[${tname}]`);

        // KM correlation line (only when available)
        if (fisher.km_mean_r != null && fisher.k_features) {
            lines.push(`  KM correlation: k=${fisher.k_features}, mean_offdiag_r=${fmt(fisher.km_mean_r)}, df_KM/(2k)=${fmt(fisher.km_df_ratio)}`);
        }

        lines.push(`  Fisher_KM_p=${fmt(fisher.km_p)} sig=${fisher.significant} df=${fmt(fisher.km_df)}`);

        // ESS block
        const meta = sumP.metadata || {};
        if (meta.ess_baseline != null || meta.ess_task != null || meta.n_blocks_used != null) {
            lines.push(`  ESS: baseline=${fmt(meta.ess_baseline)}, task=${fmt(meta.ess_task)}, n_blocks=${fmt(meta.n_blocks_used)}`);
        }

        lines.push(`  SumP=${fmt(sumP.value)} p=${fmt(sumP.perm_p)} sig=${sumP.significant} perm=${sumP.permutation_used}`);
        lines.push(`  CompositeScore=${fmt(comp.score)} Mean|d|=${fmt(summary.effect_size_mean)}`);

        if (decision && decision.alpha !== undefined) {
            lines.push(`  Decision thresholds (band-specific): p≤${fmt(decision.alpha)}, q≤${fmt(decision.fdr_alpha)}`);
            lines.push('    Effect sizes: α≥0.25, β≥0.35, γ≥0.30, θ≥0.30, ratios≥0.30');
            lines.push('    Percent change: relative features≥5%, absolute≥10%');
            if (decision.correlation_guard_active) {
                lines.push(`  Correlation guard factor=${fmt(decision.correlation_guard_factor)} (m_eff=${fmt(decision.effective_feature_count)}/${decision.nominal_feature_count})`);
            }
        }

        // Per-feature detail
        const analysis = tinfo.analysis || {};
        if (Object.keys(analysis).length > 0) {
            const featRows = [];
            for (const [fname, d] of Object.entries(analysis)) {
                if (fname.startsWith('gamma_') && d.gamma_evaluated === false) continue;
                const p = d.p_value ?? 1.0;
                featRows.push([p, fname, d]);
            }
            featRows.sort((a, b) => a[0] - b[0]);

            const sigRows = featRows.filter(([, , d]) => d.significant_change);
            lines.push('  Significant Features (adjusted thresholds, top 5 shown):');
            if (sigRows.length === 0) {
                lines.push('    (none)');
            } else {
                for (const [, fname, d] of sigRows.slice(0, 5)) {
                    lines.push(`    ${fname}: p=${fmt(d.p_value)} q=${fmt(d.q_value)} Δ=${fmt(d.delta)} d=${fmt(d.effect_size_d)} task_mean=${fmt(d.task_mean)} base_mean=${fmt(d.baseline_mean)} bin=${d.discrete_index}`);
                }
            }

            lines.push('  Top 5 Features (by p-value):');
            for (const [, fname, d] of featRows.slice(0, 5)) {
                const ratio = (d.task_mean != null && d.baseline_mean)
                    ? d.task_mean / (Math.abs(d.baseline_mean) + 1e-12)
                    : null;
                lines.push(`    ${fname}: p=${fmt(d.p_value)} q=${fmt(d.q_value)} sig=${d.significant_change} Δ=${fmt(d.delta)} d=${fmt(d.effect_size_d)} ratio=${fmt(ratio)}`);
            }
        }

        // ── Expectation-Alignment Analysis ────────────────────────────────────
        const ea = tinfo.expectation_alignment || summary.expectation_alignment || null;
        if (ea) {
            lines.push('  ⎯⎯⎯ Expectation-Alignment Analysis ⎯⎯⎯');
            lines.push(`  Grade: ${ea.grade || 'NA'}`);
            if (ea.counter_directional) {
                lines.push('  ⚠ Counter-directional: ≥70% of features moved opposite to task expectations');
            }
            const passed = ea.passed || [];
            lines.push(`  Passed Features (n=${passed.length}):`);
            if (passed.length === 0) {
                lines.push('    (none)');
            } else {
                for (const f of passed) {
                    let row = `    ${f.feature} (${f.direction}):`;
                    if (f.d != null) row += ` d=${fmt(f.d)},`;
                    if (f.delta_pct != null) row += ` Δ%=${fmt(f.delta_pct)},`;
                    if (f.p_dir != null) row += ` p_dir=${fmt(f.p_dir)}`;
                    if (f.rule) row += ` | rule=${f.rule}`;
                    lines.push(row);
                }
            }
            const drivers = ea.top_drivers || [];
            lines.push('  Top Drivers (by |d|):');
            if (drivers.length === 0) {
                lines.push('    (none)');
            } else {
                for (const dr of drivers) {
                    lines.push(`    ${dr.feature}: |d|=${fmt(dr.abs_d)}`);
                }
            }
            const notes = ea.notes || [];
            if (notes.length > 0) {
                lines.push('  Notes:');
                for (const note of notes) lines.push(`    • ${note}`);
            }
        }

        lines.push('');
    }

    // ── Combined aggregate ────────────────────────────────────────────────────
    lines.push('Combined Task Aggregate');
    lines.push('-'.repeat(30));
    const combined = res.combined || {};
    const combSum = combined.summary || {};
    const fisherC = combSum.fisher || {};
    const sumPC = combSum.sum_p || {};
    const compC = combSum.composite || {};
    const decisionC = combSum.feature_selection || {};

    lines.push(`Fisher_KM_p=${fmt(fisherC.km_p)} sig=${fisherC.significant} df=${fmt(fisherC.km_df)}`);
    lines.push(`SumP=${fmt(sumPC.value)} p=${fmt(sumPC.perm_p)} sig=${sumPC.significant} perm=${sumPC.permutation_used}`);
    lines.push(`CompositeScore=${fmt(compC.score)} Mean|d|=${fmt(combSum.effect_size_mean)}`);
    if (decisionC && decisionC.alpha !== undefined) {
        lines.push(`Decision thresholds (band-specific): p≤${fmt(decisionC.alpha)}, q≤${fmt(decisionC.fdr_alpha)}`);
        lines.push('  Effect sizes: α≥0.25, β≥0.35, γ≥0.30, θ≥0.30, ratios≥0.30');
        lines.push('  Percent change: relative features≥5%, absolute≥10%');
        if (decisionC.correlation_guard_active) {
            lines.push(`Correlation guard factor=${fmt(decisionC.correlation_guard_factor)} (m_eff=${fmt(decisionC.effective_feature_count)}/${decisionC.nominal_feature_count})`);
        }
    }
    lines.push('');

    // ── Across-task omnibus ───────────────────────────────────────────────────
    lines.push('Across-Task Omnibus (Feature Stability)');
    lines.push('-'.repeat(40));
    const across = res.across_task || {};
    if (Object.keys(across).length > 0) {
        if (across.ranking_only) {
            lines.push('Showing descriptive rankings only (median effect per task).');
            const featInfo = across.features || {};
            lines.push(`Features ranked: ${Object.keys(featInfo).length}`);
            lines.push('Sample feature rankings (up to 5):');
            let count = 0;
            for (const [fname, data] of Object.entries(featInfo)) {
                if (count >= 5) break;
                const rankStr = (data.ranking || [])
                    .map(r => `${r.task}(${fmt(r.median_effect)})`).join(' > ');
                lines.push(`  ${fname}: ${rankStr}`);
                count++;
            }
        } else {
            const featInfo = across.features || {};
            const fdrAlpha = (res.config || {}).fdr_alpha ?? 0.05;
            const sigFeats = Object.entries(featInfo)
                .filter(([, d]) => d.omnibus_sig).map(([f]) => f).sort();
            lines.push(`Features tested: ${Object.keys(featInfo).length} | Significant (FDR ${fdrAlpha}): ${sigFeats.length}`);
            if (sigFeats.length > 0) {
                lines.push('Significant features: ' + sigFeats.join(', '));
            }
            // Top omnibus stats sorted by stat descending
            const statsRows = Object.entries(featInfo)
                .filter(([, d]) => d.omnibus_stat != null)
                .sort((a, b) => (b[1].omnibus_stat || 0) - (a[1].omnibus_stat || 0))
                .slice(0, 5);
            if (statsRows.length > 0) {
                lines.push('Top Feature Omnibus Stats (up to 5):');
                for (const [fname, d] of statsRows) {
                    lines.push(`  ${fname}: stat=${fmt(d.omnibus_stat)} p=${fmt(d.omnibus_p)} q=${fmt(d.omnibus_q)}`);
                }
            }
        }
    } else {
        lines.push('Across-task analysis unavailable (insufficient task diversity).');
    }
    lines.push('');

    // ── Configuration & provenance ────────────────────────────────────────────
    lines.push('Configuration & Provenance');
    lines.push('-'.repeat(40));
    const cfg = res.config || {};
    lines.push(`Mode=${cfg.mode || 'NA'} | alpha=${cfg.alpha ?? 'NA'} | dependence=${cfg.dependence_correction || 'NA'}`);
    lines.push(`Permutation preset=${cfg.runtime_preset || 'None'} (n_perm=${cfg.n_perm ?? 'NA'}) | effect_measure=${cfg.effect_measure || 'NA'}`);
    lines.push(`Discretization bins=${cfg.discretization_bins ?? 'NA'} | FDR alpha=${cfg.fdr_alpha ?? 'NA'}`);
    lines.push('Baseline: eyes-closed only (eyes-open retained for reference, not pooled).');
    lines.push('');

    // ── Glossary ──────────────────────────────────────────────────────────────
    lines.push('Glossary of Metrics');
    lines.push('-'.repeat(40));
    lines.push('Fisher_KM: Fisher combined p-value adjusted with Kost–McDermott correlation correction');
    lines.push('SumP: Sum of per-feature p-values; permutation p-value gauges deviation from baseline');
    lines.push('CompositeScore: Sum of -log10 adjusted p-values as an aggregate strength indicator');
    lines.push("Mean|d|: Mean absolute Cohen's d effect size across significant features");
    lines.push('perm_p: Permutation-derived significance comparing observed statistic to shuffled baseline');
    lines.push('perm_used: Indicates whether permutations (vs analytic approximation) were applied');
    lines.push('km_df: Effective degrees of freedom used in Kost–McDermott chi-square approximation');
    lines.push('sig_feature_count: Number of features passing the FDR threshold when feature selection enabled');
    lines.push('sig_prop: Proportion of tested features that remained significant after FDR control');
    lines.push('omnibus_stat: Across-task Friedman/Wilcoxon statistic measuring feature variation between tasks');
    lines.push('omnibus_p: P-value for omnibus_stat before FDR adjustment');
    lines.push('omnibus_q: FDR-adjusted p-value for the across-task omnibus test');
    lines.push('omnibus_sig: True when omnibus_q is below the configured FDR alpha');
    lines.push('posthoc_q: Pairwise task comparison FDR-adjusted q-values (matrix form in exports)');
    lines.push('Δ: Absolute difference between task and baseline means for the feature');
    lines.push("d: Cohen's d effect size comparing task vs baseline distributions");
    lines.push('ratio: Task mean divided by baseline mean (signed) for quick proportional change');
    lines.push('bin: Discretized effect bin index relative to baseline distribution quantiles');

    return lines.join('\n');
}
