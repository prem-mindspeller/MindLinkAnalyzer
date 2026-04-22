import React from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCircleCheck, faMinus } from '@fortawesome/free-solid-svg-icons';
import '../styles/upload.css';

const BAND_LABELS = {
    delta: 'Delta',
    theta: 'Theta',
    lowAlpha: 'Low Alpha',
    highAlpha: 'High Alpha',
    lowBeta: 'Low Beta',
    highBeta: 'High Beta',
    lowGamma: 'Low Gamma',
    midGamma: 'Mid Gamma',
};

const BANDS = ['delta', 'theta', 'lowAlpha', 'highAlpha', 'lowBeta', 'highBeta', 'lowGamma', 'midGamma'];

/**
 * Renders a small horizontal bar for one band value.
 */
function BandBar({ label, value, maxVal }) {
    const pct = maxVal > 0 ? Math.min(100, (value / maxVal) * 100) : 0;
    return (
        <div className="an-band-row">
            <span className="an-band-label">{label}</span>
            <div className="an-band-track">
                <div className="an-band-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="an-band-value">{value.toLocaleString()}</span>
        </div>
    );
}

/**
 * Card for one task's analysis result.
 * Accepts the new nested result structure from the backend.
 */
function TaskResultCard({ taskId, result, taskName }) {
    const summary = result.summary || {};
    const analysis = result.analysis || {};
    const fisher = summary.fisher || {};
    const sumP = summary.sum_p || {};

    // Significant if either Fisher or SumP is significant
    const significant = !!(fisher.significant || sumP.significant);
    const pValue = sumP.perm_p ?? fisher.km_p ?? null;
    const effectSize = summary.effect_size_mean ?? null;
    const sampleCount = result.sample_count ?? 0;

    // Extract band task_means from the analysis object
    const bandMeans = {};
    for (const band of BANDS) {
        const featureData = analysis[band];
        if (featureData && featureData.task_mean !== undefined) {
            bandMeans[band] = featureData.task_mean;
        }
    }
    const bandValues = Object.values(bandMeans);
    const maxVal = bandValues.length ? Math.max(...bandValues) : 1;

    const sigClass = significant ? 'an-sig-yes' : 'an-sig-no';
    const sigLabel = significant
        ? <><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 5 }} />Significant</>
        : <><FontAwesomeIcon icon={faMinus} style={{ marginRight: 5 }} />Not significant</>;

    const fmtNum = (v) => (v !== null && v !== undefined ? Number(v).toPrecision(4) : 'N/A');

    return (
        <div className={`an-task-card ${significant ? 'an-card-sig' : ''}`}>
            <div className="an-task-header">
                <span className="an-task-name">{taskName || taskId}</span>
                <span className={`an-sig-badge ${sigClass}`}>{sigLabel}</span>
            </div>

            <div className="an-task-stats">
                <div className="an-stat">
                    <span className="an-stat-label">p-value (SumP)</span>
                    <span className="an-stat-value">{fmtNum(pValue)}</span>
                </div>
                <div className="an-stat">
                    <span className="an-stat-label">Effect size (d)</span>
                    <span className="an-stat-value">{fmtNum(effectSize)}</span>
                </div>
                <div className="an-stat">
                    <span className="an-stat-label">Samples</span>
                    <span className="an-stat-value">{sampleCount}</span>
                </div>
            </div>

            {bandValues.length > 0 && (
                <div className="an-bands">
                    {BANDS.filter(b => bandMeans[b] !== undefined).map(band => (
                        <BandBar
                            key={band}
                            label={BAND_LABELS[band] || band}
                            value={bandMeans[band]}
                            maxVal={maxVal}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

/**
 * Summary bar at the top of the results section.
 */
function AnalysisSummary({ perTask, baselineKept }) {
    const totalTasks = Object.keys(perTask).length;
    const sigCount = Object.values(perTask).filter(r => {
        const fisher = r.summary?.fisher || {};
        const sumP = r.summary?.sum_p || {};
        return !!(fisher.significant || sumP.significant);
    }).length;

    return (
        <div className="an-summary">
            <div className="an-summary-stat">
                <span className="an-summary-num">{totalTasks}</span>
                <span className="an-summary-label">Tasks analysed</span>
            </div>
            <div className="an-summary-divider" />
            <div className="an-summary-stat">
                <span className="an-summary-num an-summary-sig">{sigCount}</span>
                <span className="an-summary-label">Significant (p &lt; 0.05)</span>
            </div>
            <div className="an-summary-divider" />
            <div className="an-summary-stat">
                <span className="an-summary-num">{baselineKept ?? 0}</span>
                <span className="an-summary-label">Baseline samples</span>
            </div>
        </div>
    );
}


const AnalysisResultsPanel = ({ results }) => {
    if (!results) return null;
    const { per_task = {}, baseline_kept } = results;

    return (
        <div className="an-panel">
            <AnalysisSummary perTask={per_task} baselineKept={baseline_kept} />
            <div className="an-task-grid">
                {Object.entries(per_task).map(([id, result]) => (
                    <TaskResultCard
                        key={id}
                        taskId={id}
                        result={result}
                        taskName={result.name}
                    />
                ))}
            </div>
        </div>
    );
};

export default AnalysisResultsPanel;

