import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import LoggedInHeader from '../components/LoggedInHeader';
import Footer from '../components/footer';
import EegWaveform from '../components/EegWaveform';
import wsEegService, { CONNECTION_STATUS } from '../service/wsEegService';
import { evaluateBaselineSignalStats } from '../service/baselineQualityGate.mjs';
import { createFourChannelBatchCollector } from '../service/continuousRecording.mjs';
import { saveBaselineRecording } from '../service/recordingStore.mjs';
import { BATTERY_VERSION } from '../components/tasks/optimizedBatteryConfig.mjs';
import {
    BASELINE_PHASE_REQUEST_KEY,
    BASELINE_RECORDING_PHASE,
    isBaselinePhaseComplete,
    mergeCompletedBaselinePhase,
    readBaselineSummary,
    resolveBaselineEntry,
} from '../service/baselineSessionFlow.mjs';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faCircleCheck, faMoon, faEye, faBullseye, faVideo,
    faHourglass, faTriangleExclamation, faCircle, faArrowLeft, faArrowRight,
    faCircleXmark, faPlay, faRotate,
} from '@fortawesome/free-solid-svg-icons';
import '../styles/liveEegReading.css';
import '../styles/baselineCalibration.css';

// ── Audio helpers ─────────────────────────────────────────────────────────────
function playBeep(freq = 800, durationMs = 200) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = freq;
        osc.type = 'sine';
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durationMs / 1000);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + durationMs / 1000);
    } catch (_) { /* ignore */ }
}

function playCompletionBeeps() {
    for (let i = 0; i < 4; i++) setTimeout(() => playBeep(1000, 150), i * 200);
}

function createBaselineRecordingId() {
    try {
        if (typeof globalThis.crypto?.randomUUID === 'function') {
            return globalThis.crypto.randomUUID();
        }
    } catch (_) { /* fall through */ }
    return `baseline-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ── Constants ─────────────────────────────────────────────────────────────────
const PHASE_DURATION_S = 60;
const COUNTDOWN_FROM = 5;

const PHASE = {
    IDLE: 'idle',
    PREP_EC: 'prep_ec',
    COUNTDOWN_EC: 'countdown_ec',
    RECORDING_EC: 'recording_ec',
    DONE_EC: 'done_ec',
    PREP_EO: 'prep_eo',
    COUNTDOWN_EO: 'countdown_eo',
    RECORDING_EO: 'recording_eo',
    DONE_BOTH: 'done_both',
};


const BaselineCalibration1 = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [entryContext] = useState(() => resolveBaselineEntry(sessionStorage));
    const [phase, setPhase] = useState(PHASE.IDLE);
    const [baselineStateReady, setBaselineStateReady] = useState(false);
    const [countdown, setCountdown] = useState(COUNTDOWN_FROM);
    const [recordingProgress, setRecordingProgress] = useState(0);
    const [signalStatus, setSignalStatus] = useState({ icon: faCircle, text: t('baseline.signalWaiting'), cls: 'waiting' });
    const [connectionStatus, setConnectionStatus] = useState(wsEegService.getStatus());
    const [poorSignal, setPoorSignal] = useState(wsEegService.getPoorSignal());
    const [baselineQualityDialog, setBaselineQualityDialog] = useState(null);
    const [baselineStorageDialog, setBaselineStorageDialog] = useState(null);
    const [storageBusy, setStorageBusy] = useState(false);
    const [statusMsg, setStatusMsg] = useState(t('baseline.readyToStart'));
    const [phaseMsg, setPhaseMsg] = useState('');

    const batchCollectorRef = useRef(null);
    const signalStatsRef = useRef({ total: 0, good: 0, noisy: 0, notWorn: 0, worstPoorSignal: null });
    const baselineRef = useRef(readBaselineSummary(sessionStorage));
    const countdownTimerRef = useRef(null);
    const recordingTimerRef = useRef(null);
    const unsubBpRef = useRef(null);
    const elapsedRef = useRef(0);
    const pendingBaselineSaveRef = useRef(null);

    const resetSignalStats = useCallback(() => {
        signalStatsRef.current = { total: 0, good: 0, noisy: 0, notWorn: 0, worstPoorSignal: null };
    }, []);

    const recordSignalSample = useCallback((value) => {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return;
        const stats = signalStatsRef.current;
        stats.total += 1;
        stats.worstPoorSignal = stats.worstPoorSignal == null
            ? numeric
            : Math.max(stats.worstPoorSignal, numeric);
        if (numeric >= 200) stats.notWorn += 1;
        else if (numeric < 25) stats.good += 1;
        else stats.noisy += 1;
    }, []);

    const discardBaselinePhase = useCallback((isEC, quality) => {
        batchCollectorRef.current = null;
        pendingBaselineSaveRef.current = null;
        // A failed new attempt was never persisted. Keep any previously saved phase,
        // especially the eyes-closed baseline while recording the later EO checkpoint.
        setPhase(PHASE.IDLE);
        setRecordingProgress(0);
        setStatusMsg(t('baseline.qualityRepeatTitle', { defaultValue: 'Please repeat this baseline phase' }));
        setPhaseMsg(quality.reason);
        setBaselineQualityDialog({ isEC, quality });
    }, [t]);

    const isGoodSignal = connectionStatus === CONNECTION_STATUS.CONNECTED && poorSignal < 25;

    const checkStoredBaseline = useCallback(async () => {
        setStorageBusy(true);
        setBaselineStorageDialog(null);
        try {
            const complete = await isBaselinePhaseComplete(
                sessionStorage,
                entryContext.recordingPhase,
                entryContext.protocolSession,
                BATTERY_VERSION,
            );
            if (!entryContext.isRequestedCheckpoint && complete) {
                setPhase(PHASE.DONE_EC);
                setStatusMsg(t('baseline.ecComplete'));
                setPhaseMsg(t('baseline.ecCheckpointCompleteSub', {
                    defaultValue: 'Eyes-closed baseline saved. Continue to the task battery.',
                }));
            } else {
                setPhase(PHASE.IDLE);
                setStatusMsg(t('baseline.readyToStart'));
                setPhaseMsg('');
            }
            setBaselineStateReady(true);
        } catch (error) {
            setBaselineStateReady(false);
            setPhase(PHASE.IDLE);
            setStatusMsg(t('baseline.storageUnavailableTitle', {
                defaultValue: 'Baseline storage unavailable',
            }));
            const reason = error?.message || String(error);
            setPhaseMsg(reason);
            setBaselineStorageDialog({ operation: 'read', reason });
        } finally {
            setStorageBusy(false);
        }
    }, [entryContext.isRequestedCheckpoint, entryContext.protocolSession, entryContext.recordingPhase, t]);

    useEffect(() => {
        checkStoredBaseline();
    }, [checkStoredBaseline]);

    const persistBaselineAttempt = useCallback(async (pending) => {
        if (!pending) return false;
        const {
            isEC,
            samples,
            recordingMetadata,
            recordingId,
        } = pending;
        const recordingPhase = isEC
            ? BASELINE_RECORDING_PHASE.EYES_CLOSED
            : BASELINE_RECORDING_PHASE.EYES_OPEN;
        const nextSummary = mergeCompletedBaselinePhase(baselineRef.current, {
            recordingPhase,
            sampleCount: samples.length,
            protocolSession: entryContext.protocolSession,
            batteryVersion: BATTERY_VERSION,
            recordingMetadata: {
                ...recordingMetadata,
                recording_id: recordingId,
            },
        });
        const phaseMetadata = isEC ? nextSummary.eyesClosed : nextSummary.eyesOpen;

        setStorageBusy(true);
        setBaselineStorageDialog(null);
        setStatusMsg(t('baseline.savingRecording', { defaultValue: 'Saving baseline recording…' }));
        try {
            await saveBaselineRecording(recordingPhase, samples, phaseMetadata, sessionStorage);
            // The manifest is deliberately small, but remains a required UI and
            // compatibility commit marker alongside the durable raw recording.
            sessionStorage.setItem('baselineCalibration', JSON.stringify(nextSummary));
            baselineRef.current = nextSummary;
            pendingBaselineSaveRef.current = null;
            setBaselineStateReady(true);

            if (isEC) {
                if (entryContext.isRequestedCheckpoint) {
                    sessionStorage.removeItem(BASELINE_PHASE_REQUEST_KEY);
                }
                setPhase(PHASE.DONE_EC);
                setStatusMsg(t('baseline.ecComplete'));
                setPhaseMsg(t('baseline.ecCheckpointCompleteSub', {
                    defaultValue: 'Eyes-closed baseline saved. Continue to the task battery.',
                }));
            } else {
                sessionStorage.removeItem(BASELINE_PHASE_REQUEST_KEY);
                setPhase(PHASE.DONE_BOTH);
                setStatusMsg(t('baseline.calibComplete'));
                setPhaseMsg(t('baseline.eoCheckpointCompleteSub', {
                    defaultValue: 'Eyes-open baseline saved. Returning to the task battery.',
                }));
                navigate('/taskSelection', { replace: true });
            }
            return true;
        } catch (error) {
            const reason = error?.message || String(error);
            setBaselineStateReady(false);
            setPhase(PHASE.IDLE);
            setRecordingProgress(0);
            setStatusMsg(t('baseline.storageFailureTitle', {
                defaultValue: 'Baseline was not marked complete',
            }));
            setPhaseMsg(reason);
            setBaselineStorageDialog({ operation: 'write', isEC, reason });
            return false;
        } finally {
            setStorageBusy(false);
        }
    }, [entryContext.isRequestedCheckpoint, entryContext.protocolSession, navigate, t]);

    const retryBaselineStorage = useCallback(async () => {
        if (baselineStorageDialog?.operation === 'write') {
            await persistBaselineAttempt(pendingBaselineSaveRef.current);
            return;
        }
        await checkStoredBaseline();
    }, [baselineStorageDialog?.operation, checkStoredBaseline, persistBaselineAttempt]);

    const discardPendingBaselineSave = useCallback(async () => {
        pendingBaselineSaveRef.current = null;
        setBaselineStorageDialog(null);
        await checkStoredBaseline();
    }, [checkStoredBaseline]);

    useEffect(() => {
        const id = setInterval(() => {
            const ps = wsEegService.getPoorSignal();
            const st = wsEegService.getStatus();
            setPoorSignal(ps);
            setConnectionStatus(st);
            if (st !== CONNECTION_STATUS.CONNECTED) {
                setSignalStatus({ icon: faCircle, text: t('baseline.signalWaiting'), cls: 'waiting' });
            } else if (ps >= 200) {
                setSignalStatus({ icon: faTriangleExclamation, text: t('baseline.notWorn'), cls: 'noisy' });
            } else if (ps < 25) {
                setSignalStatus({ icon: faCircleCheck, text: t('baseline.signalGood'), cls: 'good' });
            } else {
                setSignalStatus({ icon: faTriangleExclamation, text: t('baseline.signalNoisy'), cls: 'noisy' });
            }
        }, 500);
        return () => clearInterval(id);
    }, [t]);


    useEffect(() => () => {
        clearInterval(countdownTimerRef.current);
        clearInterval(recordingTimerRef.current);
        if (unsubBpRef.current) unsubBpRef.current();
    }, []);

    useEffect(() => {
        if (!entryContext.isRequestedCheckpoint) return undefined;

        // Browser Back should not leave a stale checkpoint request that immediately
        // redirects the task page here again. A refresh does not emit popstate, so it
        // intentionally keeps the request and safely restarts this one phase.
        const clearCheckpointRequestOnBrowserBack = () => {
            sessionStorage.removeItem(BASELINE_PHASE_REQUEST_KEY);
        };
        window.addEventListener('popstate', clearCheckpointRequestOnBrowserBack);
        return () => window.removeEventListener('popstate', clearCheckpointRequestOnBrowserBack);
    }, [entryContext.isRequestedCheckpoint]);

    const startRecording = useCallback((isEC) => {
        resetSignalStats();
        recordSignalSample(wsEegService.getPoorSignal());
        elapsedRef.current = 0;

        const deviceInfo = wsEegService.getDeviceInfo?.() || {};
        const sampleRateHz = Number(deviceInfo.sampleRate) || 500;
        const startedAtMs = typeof globalThis.performance?.now === 'function'
            ? globalThis.performance.now()
            : Date.now();
        const collector = createFourChannelBatchCollector({ sampleRateHz, startedAtMs });
        batchCollectorRef.current = collector;
        const unsubRawMultiBatch = wsEegService.on('rawMultiBatch', (batch) => {
            collector.appendBatch(
                batch?.samples,
                batch?.receivedAtMs,
                batch?.streamStartSampleIndex,
            );
        });
        const unsubSignal = wsEegService.on('eegData', (data) => recordSignalSample(data?.poorSignal));
        unsubBpRef.current = () => {
            unsubRawMultiBatch();
            unsubSignal();
        };

        setPhase(isEC ? PHASE.RECORDING_EC : PHASE.RECORDING_EO);
        setStatusMsg(isEC ? t('baseline.recordingEC') : t('baseline.recordingEO'));
        setPhaseMsg(isEC ? t('baseline.phaseMsgEC') : t('baseline.phaseMsgEO'));
        setRecordingProgress(0);

        recordingTimerRef.current = setInterval(async () => {
            elapsedRef.current += 1;
            const pct = Math.round((elapsedRef.current / PHASE_DURATION_S) * 100);
            setRecordingProgress(pct);

            if (elapsedRef.current >= PHASE_DURATION_S) {
                clearInterval(recordingTimerRef.current);
                if (unsubBpRef.current) { unsubBpRef.current(); unsubBpRef.current = null; }

                playCompletionBeeps();

                const recording = collector.snapshot();
                const liveSignalQuality = evaluateBaselineSignalStats(signalStatsRef.current);
                const baselineSignalQuality = recording.max_contiguous_transport_seconds >= 20
                    ? liveSignalQuality
                    : {
                        ...liveSignalQuality,
                        acceptable: false,
                        reason: recording.samples.length === 0
                            ? 'No complete Fp1/Fp2/O1/O2 recording batches were received'
                            : 'Less than 20 seconds of contiguous four-channel data remained after transport gaps',
                    };
                if (!baselineSignalQuality.acceptable) {
                    discardBaselinePhase(isEC, baselineSignalQuality);
                    return;
                }

                const samples = recording.samples;
                const recordingMetadata = {
                    sample_rate_hz: recording.sample_rate_hz,
                    required_channels: ['Fp1', 'Fp2', 'O1', 'O2'],
                    transport_segments: recording.transport_segments,
                    max_contiguous_transport_seconds: recording.max_contiguous_transport_seconds,
                    transport_gap_count: recording.transport_gap_count,
                    invalid_channel_sample_count: recording.invalid_sample_count,
                };

                const pending = {
                    isEC,
                    samples,
                    recordingMetadata,
                    recordingId: createBaselineRecordingId(),
                };
                pendingBaselineSaveRef.current = pending;
                await persistBaselineAttempt(pending);
            }
        }, 1000);
    }, [discardBaselinePhase, persistBaselineAttempt, recordSignalSample, resetSignalStats, t]);
    const startCountdown = useCallback((isEC) => {
        setPhase(isEC ? PHASE.COUNTDOWN_EC : PHASE.COUNTDOWN_EO);
        let count = COUNTDOWN_FROM;
        setCountdown(count);
        setStatusMsg(t('baseline.countdown', { count }));
        setPhaseMsg(t('baseline.countdownReady'));
        playBeep(800, 200);

        countdownTimerRef.current = setInterval(() => {
            count -= 1;
            if (count > 0) {
                setCountdown(count);
                setStatusMsg(t('baseline.countdown', { count }));
                playBeep(800, 200);
            } else {
                clearInterval(countdownTimerRef.current);
                startRecording(isEC);
            }
        }, 1000);
    }, [startRecording, t]);

    const isBusy = [
        PHASE.COUNTDOWN_EC, PHASE.RECORDING_EC,
        PHASE.COUNTDOWN_EO, PHASE.RECORDING_EO,
    ].includes(phase);
    const isCountingDown = phase === PHASE.COUNTDOWN_EC || phase === PHASE.COUNTDOWN_EO;
    const isRecording = phase === PHASE.RECORDING_EC || phase === PHASE.RECORDING_EO;
    const ecDone = phase === PHASE.DONE_EC;
    const bothDone = phase === PHASE.DONE_BOTH;
    const showPrepModal = phase === PHASE.PREP_EC || phase === PHASE.PREP_EO;
    const prepIsEC = phase === PHASE.PREP_EC;

    const handleNext = () => {
        sessionStorage.removeItem(BASELINE_PHASE_REQUEST_KEY);
        sessionStorage.setItem('selectedPathway', 'personal');
        navigate('/taskSelection');
    };

    const handleBack = () => {
        if (entryContext.isRequestedCheckpoint) {
            sessionStorage.removeItem(BASELINE_PHASE_REQUEST_KEY);
            navigate('/taskSelection', { replace: true });
            return;
        }
        navigate('/liveReading');
    };

    return (
        <div className="app-container">
            <LoggedInHeader />

            <main className="app-main">
                <div className="calibration-page">

                    {/* ── Page header ── */}
                    <div className="calibration-header">
                        <h1 className="calibration-title">{t('baseline.title')}</h1>
                        <p className="calibration-subtitle">{t('baseline.subtitle')}</p>
                    </div>

                    {/* ── Signal quality badge ── */}
                    <div className={`cal-signal-badge cal-signal-${signalStatus.cls}`}>
                        {signalStatus.icon && <FontAwesomeIcon icon={signalStatus.icon} style={{ marginRight: 6 }} />}
                        {signalStatus.text}
                    </div>

                    {/* ── Status card ── */}
                    <div className="calibration-card">
                        <p className="calibration-status-label">
                            {isCountingDown && <FontAwesomeIcon icon={faHourglass} style={{ marginRight: 8 }} />}
                            {isRecording && <FontAwesomeIcon icon={faVideo} style={{ marginRight: 8 }} />}
                            {phase === PHASE.DONE_BOTH && <FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 8, color: '#16a34a' }} />}
                            {phase === PHASE.DONE_EC && !isRecording && <FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 8, color: '#16a34a' }} />}
                            {statusMsg}
                        </p>
                        {phaseMsg && <p className="calibration-phase-label">{phaseMsg}</p>}

                        {isCountingDown && (
                            <div className="cal-countdown-display">{countdown}</div>
                        )}

                        {isRecording && (
                            <div className="cal-progress-wrap">
                                <div className="cal-progress-bar" style={{ width: `${recordingProgress}%` }} />
                                <span className="cal-progress-text">{recordingProgress}%</span>
                            </div>
                        )}
                    </div>

                    {/* ── Phase cards ── */}
                    <div className="calibration-phases">
                        {!entryContext.isEyesOpenCheckpoint && (
                            <div className={`cal-phase-card${ecDone ? ' phase-done' : ''}`}>
                                <span className="cal-phase-icon"><FontAwesomeIcon icon={faMoon} /></span>
                                <div className="cal-phase-info">
                                    <h3>{t('baseline.ecCardTitle')}</h3>
                                    <p>{t('baseline.ecCardDesc')}</p>
                                </div>
                                <button
                                    className="cal-phase-btn"
                                    disabled={!baselineStateReady || storageBusy || isBusy || ecDone}
                                    onClick={() => setPhase(PHASE.PREP_EC)}
                                >
                                    {ecDone
                                        ? <><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 6 }} />{t('baseline.complete')}</>
                                        : <><FontAwesomeIcon icon={faBullseye} style={{ marginRight: 6 }} />{t('baseline.start')}</>}
                                </button>
                            </div>
                        )}

                        {entryContext.isEyesOpenCheckpoint && (
                            <div className={`cal-phase-card${bothDone ? ' phase-done' : ''}`}>
                                <span className="cal-phase-icon"><FontAwesomeIcon icon={faEye} /></span>
                                <div className="cal-phase-info">
                                    <h3>{t('baseline.eoCardTitle')}</h3>
                                    <p>{t('baseline.eoCardDesc')}</p>
                                </div>
                                <button
                                    className="cal-phase-btn"
                                    disabled={!baselineStateReady || storageBusy || isBusy || bothDone}
                                    onClick={() => setPhase(PHASE.PREP_EO)}
                                >
                                    {bothDone
                                        ? <><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 6 }} />{t('baseline.complete')}</>
                                        : <><FontAwesomeIcon icon={faBullseye} style={{ marginRight: 6 }} />{t('baseline.start')}</>}
                                </button>
                            </div>
                        )}
                    </div>


                </div>
            </main>
            <div className="nav-sub-footer">
                <button className="btn-back-eeg" disabled={isBusy || storageBusy} onClick={handleBack}>
                    <FontAwesomeIcon icon={faArrowLeft} style={{ marginRight: 6 }} />{t('nav.back')}
                </button>
                {!entryContext.isEyesOpenCheckpoint && (
                    <button
                        className="btn-next-eeg"
                        disabled={!ecDone}
                        onClick={handleNext}
                    >
                        {t('nav.next')} <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 6 }} />
                    </button>
                )}
            </div>

            {/* ── Prep modal ── */}
            {showPrepModal && (
                <div className="cal-modal-overlay">
                    <div className="cal-modal-card">
                        <h2 className="cal-modal-title">
                            <FontAwesomeIcon icon={prepIsEC ? faMoon : faEye} style={{ marginRight: 8 }} />
                            {prepIsEC ? t('baseline.modalECTitle') : t('baseline.modalEOTitle')}
                        </h2>

                        <div className="cal-modal-instructions">
                            {prepIsEC ? (
                                <span>
                                    <b>{t('baseline.modalECIntro')}</b><br /><br />
                                    {t('baseline.modalECDuration')}<br /><br />
                                    <b>{t('baseline.modalWhatWillHappen')}</b><br />
                                    1. {t('baseline.modalStep1')}<br />
                                    2. {t('baseline.modalStep2')}<br />
                                    3. {t('baseline.modalECStep3')}<br />
                                    4. {t('baseline.modalECStep4')}<br />
                                    5. {t('baseline.modalStep5')}<br /><br />
                                    <b style={{ color: '#dc2626' }}><FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />{t('baseline.modalECWarning')}</b>
                                </span>
                            ) : (
                                <span>
                                    <b>{t('baseline.modalEOIntro')}</b><br /><br />
                                    {t('baseline.modalEODuration')}<br /><br />
                                    <b>{t('baseline.modalWhatWillHappen')}</b><br />
                                    1. {t('baseline.modalStep1')}<br />
                                    2. {t('baseline.modalStep2')}<br />
                                    3. {t('baseline.modalEOStep3')}<br />
                                    4. {t('baseline.modalEOStep4')}<br />
                                    5. {t('baseline.modalEOStep5')}<br />
                                    6. {t('baseline.modalEOStep6')}<br /><br />
                                    <b style={{ color: '#dc2626' }}><FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />{t('baseline.modalEOWarning')}</b>
                                </span>
                            )}
                        </div>

                        <div className={`cal-signal-badge cal-signal-${signalStatus.cls}`} style={{ margin: '0 auto 18px' }}>
                            {signalStatus.icon && <FontAwesomeIcon icon={signalStatus.icon} style={{ marginRight: 6 }} />}
                            {signalStatus.text}
                        </div>

                        <div className="cal-modal-buttons">
                            <button className="cal-btn-cancel" onClick={() => setPhase(PHASE.IDLE)}>
                                <FontAwesomeIcon icon={faCircleXmark} style={{ marginRight: 6 }} />{t('baseline.cancel')}
                            </button>
                            <button className="cal-btn-start" onClick={() => startCountdown(prepIsEC)} disabled={!isGoodSignal || storageBusy}>
                                <FontAwesomeIcon icon={faPlay} style={{ marginRight: 8 }} />{isGoodSignal ? t('baseline.startRecording') : t('baseline.waitForGoodSignal', { defaultValue: 'Waiting for good signal' })}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {baselineQualityDialog && (
                <div className="cal-modal-overlay cal-quality-overlay">
                    <div className="cal-modal-card cal-quality-card" role="dialog" aria-modal="true">
                        <h2 className="cal-modal-title">
                            <FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 8 }} />
                            {t('baseline.qualityRepeatTitle', { defaultValue: 'Repeat this baseline phase' })}
                        </h2>
                        <p className="cal-quality-body">
                            {baselineQualityDialog.isEC
                                ? t('baseline.qualityRepeatECBody', { defaultValue: 'The eyes-closed baseline had too much signal instability, so it was not saved.' })
                                : t('baseline.qualityRepeatEOBody', { defaultValue: 'The eyes-open baseline had too much signal instability, so it was not saved.' })}
                        </p>
                        <div className="cal-quality-reason">
                            {t('baseline.qualityReason', { defaultValue: 'Reason: {{reason}}', reason: baselineQualityDialog.quality.reason })}
                        </div>
                        <div className={`cal-signal-badge cal-signal-${signalStatus.cls}`} style={{ margin: '0 auto 14px' }}>
                            {signalStatus.icon && <FontAwesomeIcon icon={signalStatus.icon} style={{ marginRight: 6 }} />}
                            {signalStatus.text}
                        </div>
                        <div className="cal-quality-chart">
                            <EegWaveform status={connectionStatus} />
                        </div>
                        <div className="cal-quality-steps">
                            <div><strong>1.</strong> {t('baseline.qualityStepAdjust', { defaultValue: 'Adjust the headset so the front sensor sits flat on the forehead, about two inches above the eyebrows.' })}</div>
                            <div><strong>2.</strong> {t('baseline.qualityStepStill', { defaultValue: 'Sit still, relax your jaw and forehead, and keep hair away from the sensor contacts.' })}</div>
                            <div><strong>3.</strong> {t('baseline.qualityStepWait', { defaultValue: 'Leave it for a few seconds until the signal stabilizes and shows Signal: Good.' })}</div>
                        </div>
                        <div className="cal-modal-buttons">
                            <button
                                className="cal-btn-start"
                                disabled={!isGoodSignal}
                                onClick={() => {
                                    const repeatIsEC = baselineQualityDialog.isEC;
                                    setBaselineQualityDialog(null);
                                    startCountdown(repeatIsEC);
                                }}
                            >
                                <FontAwesomeIcon icon={faRotate} style={{ marginRight: 8 }} />
                                {isGoodSignal
                                    ? t('baseline.qualityRepeatButton', { defaultValue: 'Repeat baseline now' })
                                    : t('baseline.waitForGoodSignal', { defaultValue: 'Waiting for good signal' })}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {baselineStorageDialog && (
                <div className="cal-modal-overlay cal-quality-overlay">
                    <div className="cal-modal-card cal-quality-card" role="alertdialog" aria-modal="true">
                        <h2 className="cal-modal-title">
                            <FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 8 }} />
                            {t('baseline.storageFailureTitle', {
                                defaultValue: 'Baseline storage needs attention',
                            })}
                        </h2>
                        <p className="cal-quality-body">
                            {baselineStorageDialog.operation === 'write'
                                ? t('baseline.storageWriteFailureBody', {
                                    defaultValue: 'The recording was not marked complete. The captured data is still available in this screen, so you can retry saving it without repeating the 60-second recording.',
                                })
                                : t('baseline.storageReadFailureBody', {
                                    defaultValue: 'Stored baseline data could not be checked. No task will be unlocked until durable storage is available.',
                                })}
                        </p>
                        <div className="cal-quality-reason">
                            {t('baseline.qualityReason', {
                                defaultValue: 'Reason: {{reason}}',
                                reason: baselineStorageDialog.reason,
                            })}
                        </div>
                        <div className="cal-modal-buttons">
                            {baselineStorageDialog.operation === 'write' && (
                                <button
                                    className="cal-btn-cancel"
                                    disabled={storageBusy}
                                    onClick={discardPendingBaselineSave}
                                >
                                    <FontAwesomeIcon icon={faRotate} style={{ marginRight: 8 }} />
                                    {t('baseline.recordAgain', { defaultValue: 'Record again' })}
                                </button>
                            )}
                            <button
                                className="cal-btn-start"
                                disabled={storageBusy}
                                onClick={retryBaselineStorage}
                            >
                                <FontAwesomeIcon icon={storageBusy ? faHourglass : faRotate} style={{ marginRight: 8 }} />
                                {storageBusy
                                    ? t('baseline.storageRetrying', { defaultValue: 'Retrying…' })
                                    : t('baseline.storageRetry', { defaultValue: 'Retry storage' })}
                            </button>
                        </div>
                    </div>
                </div>
            )}
            <Footer />

            {/* ── Eyes-open fixation cross overlay ── */}
            {(phase === PHASE.COUNTDOWN_EO || phase === PHASE.RECORDING_EO) && (
                <div className="cal-fixation-overlay">
                    <div className="cal-fixation-cross">
                        <div className="cal-fixation-h" />
                        <div className="cal-fixation-v" />
                    </div>
                    {phase === PHASE.COUNTDOWN_EO && (
                        <div className="cal-fixation-countdown">{countdown}</div>
                    )}
                    {phase === PHASE.RECORDING_EO && (
                        <div className="cal-fixation-progress">
                            <div className="cal-fixation-bar" style={{ width: `${recordingProgress}%` }} />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default BaselineCalibration1;
