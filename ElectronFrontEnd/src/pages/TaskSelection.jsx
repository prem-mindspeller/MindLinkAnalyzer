import React, {
    useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faArrowRight,
    faCircleCheck,
    faCircleInfo,
    faClock,
    faEye,
    faLock,
    faMoon,
    faPlay,
    faRotate,
    faSpinner,
    faTriangleExclamation,
} from '@fortawesome/free-solid-svg-icons';

import LoggedInHeader from '../components/LoggedInHeader';
import Footer from '../components/footer';
import EegWaveform from '../components/EegWaveform';
import OptimizedBatteryTask from '../components/tasks/OptimizedBatteryTask';
import {
    BATTERY_VERSION,
    EYES_OPEN_BASELINE_CHECKPOINT,
    TASK_DEFINITIONS,
    TASK_IDS,
    audioProfileForTask,
    resolveSessionDepth,
    taskIdsForSession,
    taskSequenceForSession,
} from '../components/tasks/optimizedBatteryConfig.mjs';
import wsEegService, { CONNECTION_STATUS } from '../service/wsEegService';
import { runSingleTaskQualityCheck } from '../service/analysisService';
import {
    commitTaskAttempt,
    isRepeatSignalReady,
} from '../service/taskQualityGate.mjs';
import {
    BASELINE_PHASE_REQUEST_KEY,
    BASELINE_RECORDING_PHASE,
    deriveProtocolSession,
    invalidateBaselinePhase,
    isBaselinePhaseComplete,
} from '../service/baselineSessionFlow.mjs';

import '../styles/liveEegReading.css';
import '../styles/taskSelection.css';

// Users choose task order. Required matched baselines still gate analysis.
const ALLOW_ANY_TASK_ORDER = true;
// A replacement is committed only after its new recording passes quality checks.
const ALLOW_RERUN_COMPLETED_TASKS = true;

const readCompletedTasks = () => {
    try {
        const parsed = JSON.parse(sessionStorage.getItem('completedTasks') || '[]');
        return Array.isArray(parsed) ? parsed.filter((id) => TASK_DEFINITIONS[id]) : [];
    } catch {
        return [];
    }
};

const signalDisplay = (t, status, poorSignal) => {
    if (status !== CONNECTION_STATUS.CONNECTED) {
        return { good: false, cls: 'disconnected', text: t('taskSelection.signalDisconnected', { defaultValue: 'Device not connected' }) };
    }
    if (poorSignal >= 200) {
        return { good: false, cls: 'not-worn', text: t('taskSelection.signalNotWorn', { defaultValue: 'Signal: Not worn' }) };
    }
    if (poorSignal < 25) {
        return { good: true, cls: 'good', text: t('taskSelection.signalGood', { defaultValue: 'Signal: Good' }) };
    }
    return { good: false, cls: 'noisy', text: t('taskSelection.signalNoisy', { defaultValue: 'Signal: Noisy' }) };
};

const TaskQualityModal = ({
    taskName,
    signalStatus,
    poorSignal,
    qualityDialog,
    isGoodSignal,
    repeatSignalReady,
    goodSignalStableMs,
    onRepeat,
    onRepeatBaseline,
    t,
}) => {
    if (!qualityDialog) return null;
    const signal = signalDisplay(t, signalStatus, poorSignal);
    const stableSecondsRemaining = Math.max(0, Math.ceil((5000 - Number(goodSignalStableMs || 0)) / 1000));
    const checkError = qualityDialog.mode === 'check_error';
    const baselineFailure = qualityDialog.quality?.needsBaselineRepeat === true;
    const backendReason = qualityDialog.quality?.reason
        || qualityDialog.quality?.invalidReasons?.join(' ')
        || qualityDialog.quality?.recordingSignal?.reason
        || qualityDialog.quality?.notes?.join(' ')
        || '';

    return (
        <div className="ts-quality-modal-backdrop" role="presentation">
            <div className="ts-quality-modal" role="dialog" aria-modal="true" aria-labelledby="task-quality-title">
                <div className="ts-quality-modal-header">
                    <div>
                        <p className="ts-quality-kicker">{t('taskSelection.qualityKicker', { defaultValue: 'Task signal check' })}</p>
                        <h2 id="task-quality-title">
                            {baselineFailure
                                ? 'The matched baseline must be recorded again'
                                : checkError
                                ? t('taskSelection.qualityCheckErrorTitle', { defaultValue: 'The signal check could not validate this recording' })
                                : t('taskSelection.qualityRepeatTitle', { defaultValue: 'Repeat this task after improving the signal' })}
                        </h2>
                        <p>{t('taskSelection.qualityTaskName', { defaultValue: 'Task: {{taskName}}', taskName })}</p>
                    </div>
                    <div className={`ts-quality-signal-pill ${signal.cls}`}>
                        <FontAwesomeIcon icon={signal.good ? faCircleCheck : faTriangleExclamation} />
                        <span>{signal.text}</span>
                    </div>
                </div>

                <p className="ts-quality-modal-body">
                    {baselineFailure
                        ? 'The task attempt was not saved because its matched baseline does not retain 20 contiguous clean seconds. Re-record that baseline before repeating the task.'
                        : checkError
                        ? 'The attempt was not saved because its required quality check did not complete. Repeat the task after the signal is stable.'
                        : 'At least 20 contiguous clean seconds are required. This attempt was not saved and cannot be stitched together from shorter clean fragments.'}
                    {backendReason ? ` ${backendReason}` : ''}
                </p>
                <div className="ts-quality-chart-wrap">
                    <div className="ts-quality-chart-header">{t('taskSelection.qualityLivePlot', { defaultValue: 'Live EEG signal' })}</div>
                    <div className="ts-quality-chart-area"><EegWaveform status={signalStatus} /></div>
                </div>

                <div className="ts-quality-stages">
                    <div className="ts-quality-stage">
                        <span className="ts-stage-number">1</span>
                        <div><strong>Adjust the headset</strong><p>Keep all four contacts stable, move hair away, and relax your forehead and jaw.</p></div>
                    </div>
                    <div className="ts-quality-stage">
                        <span className="ts-stage-number">2</span>
                        <div><strong>Let the signal stabilize</strong><p>Stay still until the status is continuously good.</p></div>
                    </div>
                    <div className={`ts-quality-stage ${repeatSignalReady ? 'ready' : ''}`}>
                        <span className="ts-stage-number">3</span>
                        <div>
                            <strong>Repeat the full continuous block</strong>
                            <p>{repeatSignalReady
                                ? 'The signal is ready. The same session form can now be repeated.'
                                : isGoodSignal
                                    ? `Keep the signal good for ${stableSecondsRemaining} more second(s).`
                                    : 'The repeat button unlocks after 5 continuous seconds of good signal.'}</p>
                        </div>
                    </div>
                </div>

                <div className="ts-quality-actions">
                    {baselineFailure ? (
                        <button className="ts-quality-primary" onClick={onRepeatBaseline}>
                            <FontAwesomeIcon icon={faRotate} /> Re-record matched baseline
                        </button>
                    ) : (
                        <button className="ts-quality-primary" onClick={onRepeat} disabled={!repeatSignalReady}>
                            <FontAwesomeIcon icon={faRotate} />
                            {repeatSignalReady ? 'Repeat task now' : isGoodSignal ? `Hold good signal for ${stableSecondsRemaining}s` : 'Waiting for good signal'}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

const TaskSelection = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const sessionDepth = useMemo(() => resolveSessionDepth(sessionStorage), []);
    const protocolSession = useMemo(() => deriveProtocolSession(sessionStorage), []);
    const sequence = useMemo(() => taskSequenceForSession(sessionDepth), [sessionDepth]);
    const enabledTaskIds = useMemo(() => taskIdsForSession(sessionDepth), [sessionDepth]);
    const allTaskIds = useMemo(() => taskIdsForSession('session_3'), []);

    const [completedIds, setCompletedIds] = useState(() => {
        const storedBatteryVersion = sessionStorage.getItem('taskBatteryVersion');
        const storedProtocolSession = Number(sessionStorage.getItem('taskBatteryProtocolSession') || 0);
        const sameRunContract = (
            storedBatteryVersion === BATTERY_VERSION
            && storedProtocolSession === protocolSession
        );
        const completed = sameRunContract ? readCompletedTasks() : [];
        sessionStorage.setItem('taskBatteryVersion', BATTERY_VERSION);
        sessionStorage.setItem('taskBatteryProtocolSession', String(protocolSession));
        sessionStorage.setItem('completedTasks', JSON.stringify(completed));
        return completed;
    });
    const [baselineStatus, setBaselineStatus] = useState({
        loaded: false,
        eyesOpen: false,
        eyesClosed: false,
        error: null,
    });

    const [soundChecking, setSoundChecking] = useState(false);
    const soundCheckContextRef = useRef(null);

    useEffect(() => () => {
        try { soundCheckContextRef.current?.close(); } catch (_) { /* ignore */ }
    }, []);

    // A single, page-level volume check: the same high (target) tone Task 3
    // counts, played through a standalone Web Audio oscillator rather than the
    // task runner. Lets a participant confirm their sound works once, before
    // picking a task, instead of every task's instructions repeating the
    // "audio is part of this form" reminder.
    const playSoundCheck = useCallback(() => {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;
        if (!soundCheckContextRef.current) soundCheckContextRef.current = new AudioContextClass();
        const context = soundCheckContextRef.current;
        if (context.state === 'suspended') context.resume().catch(() => {});
        const tone = audioProfileForTask(TASK_IDS.AUDITORY_COUNT);
        if (tone.mode !== 'web_audio_oscillator') return;
        const durationMs = Math.max(1, Number(tone.durationMs) || 115);
        const outputGain = Math.max(0.001, Number(tone.outputGain) || 0.22);
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.type = tone.waveform || 'sine';
        oscillator.frequency.value = tone.targetFrequencyHz;
        gain.gain.setValueAtTime(outputGain, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + durationMs / 1000);
        oscillator.onended = () => setSoundChecking(false);
        oscillator.start();
        oscillator.stop(context.currentTime + durationMs / 1000);
        setSoundChecking(true);
    }, []);

    useEffect(() => {
        let cancelled = false;
        Promise.all([
            isBaselinePhaseComplete(
                sessionStorage,
                BASELINE_RECORDING_PHASE.EYES_OPEN,
                protocolSession,
                BATTERY_VERSION,
            ),
            isBaselinePhaseComplete(
                sessionStorage,
                BASELINE_RECORDING_PHASE.EYES_CLOSED,
                protocolSession,
                BATTERY_VERSION,
            ),
        ]).then(([eyesOpen, eyesClosed]) => {
            if (!cancelled) setBaselineStatus({ loaded: true, eyesOpen, eyesClosed, error: null });
        }).catch((error) => {
            if (!cancelled) {
                setBaselineStatus({
                    loaded: true,
                    eyesOpen: false,
                    eyesClosed: false,
                    error: error?.message || String(error),
                });
            }
        });
        return () => { cancelled = true; };
    }, [protocolSession]);

    const eyesOpenBaselineDone = baselineStatus.eyesOpen;
    const eyesClosedBaselineDone = baselineStatus.eyesClosed;

    useEffect(() => {
        if (!baselineStatus.loaded) return;
        if (eyesClosedBaselineDone && eyesOpenBaselineDone) return;
        sessionStorage.removeItem(BASELINE_PHASE_REQUEST_KEY);
        navigate('/baselineCalibration1', { replace: true });
    }, [baselineStatus.loaded, eyesClosedBaselineDone, eyesOpenBaselineDone, navigate]);

    const isSequenceItemComplete = useCallback((item) => (
        item === EYES_OPEN_BASELINE_CHECKPOINT ? eyesOpenBaselineDone : completedIds.includes(item)
    ), [completedIds, eyesOpenBaselineDone]);
    const nextRequiredItem = sequence.find((item) => !isSequenceItemComplete(item)) || null;
    const allEnabledCompleted = nextRequiredItem == null;
    const completedEnabledCount = enabledTaskIds.filter((id) => completedIds.includes(id)).length;

    // The sidebar lists tasks by task number (1, 2, 3, ...), not by their order in
    // SESSION_SEQUENCES (a scientific grouping that starts with Task 3 for every
    // session). Default/auto-selection should follow what the participant sees, so
    // find the first incomplete task in that same number order instead of reusing
    // nextRequiredItem, which would otherwise always land on Task 3 on a fresh load.
    const firstIncompleteByDisplayOrder = useMemo(() => (
        enabledTaskIds
            .slice()
            .sort((left, right) => TASK_DEFINITIONS[left].number - TASK_DEFINITIONS[right].number)
            .find((id) => !completedIds.includes(id))
    ), [completedIds, enabledTaskIds]);

    const firstSelectable = nextRequiredItem === EYES_OPEN_BASELINE_CHECKPOINT
        ? EYES_OPEN_BASELINE_CHECKPOINT
        : firstIncompleteByDisplayOrder || enabledTaskIds[0];
    const [selectedId, setSelectedId] = useState(firstSelectable);
    const [activeTaskId, setActiveTaskId] = useState(null);
    const [qualityCheckTaskId, setQualityCheckTaskId] = useState(null);
    const [qualityDialog, setQualityDialog] = useState(null);
    const [signalStatus, setSignalStatus] = useState(wsEegService.getStatus());
    const [poorSignal, setPoorSignal] = useState(wsEegService.getPoorSignal());
    const [goodSignalStableMs, setGoodSignalStableMs] = useState(0);

    useEffect(() => {
        if (
            !selectedId
            || (selectedId === EYES_OPEN_BASELINE_CHECKPOINT && eyesOpenBaselineDone)
            || (selectedId !== EYES_OPEN_BASELINE_CHECKPOINT && !enabledTaskIds.includes(selectedId))
        ) {
            setSelectedId(firstSelectable);
        }
    }, [enabledTaskIds, eyesOpenBaselineDone, firstSelectable, selectedId]);

    useEffect(() => {
        const unsubStatus = wsEegService.on('status', setSignalStatus);
        const unsubEeg = wsEegService.on('eegData', (data) => setPoorSignal(data?.poorSignal));
        wsEegService.fetchStatus();
        return () => { unsubStatus(); unsubEeg(); };
    }, []);

    const isGoodSignal = signalStatus === CONNECTION_STATUS.CONNECTED && poorSignal < 25;
    const repeatSignalReady = isRepeatSignalReady({ isGoodSignal, goodSignalStableMs });

    useEffect(() => {
        if (!qualityDialog || !isGoodSignal) {
            setGoodSignalStableMs(0);
            return undefined;
        }
        const startedAt = Date.now();
        const timer = setInterval(() => setGoodSignalStableMs(Date.now() - startedAt), 250);
        return () => clearInterval(timer);
    }, [qualityDialog, isGoodSignal]);

    const positionOf = useCallback((item) => sequence.indexOf(item), [sequence]);
    const nextPosition = nextRequiredItem == null ? sequence.length : positionOf(nextRequiredItem);
    const taskIsUnlocked = useCallback((taskId) => {
        if (!baselineStatus.loaded || !eyesClosedBaselineDone || !eyesOpenBaselineDone || baselineStatus.error) return false;
        if (!enabledTaskIds.includes(taskId)) return false;
        const position = positionOf(taskId);
        if (position < 0) return false;
        if (ALLOW_ANY_TASK_ORDER) {
            // Tasks may run in any order, but the matched baseline stays mandatory: an
            // eyes-open task still needs the eyes-open baseline (its analysis
            // requires it too), so it unlocks only once that baseline is done.
            return TASK_DEFINITIONS[taskId]?.baseline !== 'eyes_open' || eyesOpenBaselineDone;
        }
        return position <= nextPosition || completedIds.includes(taskId);
    }, [baselineStatus.error, baselineStatus.loaded, completedIds, eyesClosedBaselineDone, eyesOpenBaselineDone, nextPosition, positionOf]);

    const acceptTaskAttempt = useCallback(async (taskId, samples, metadata) => {
        const updated = await commitTaskAttempt(taskId, samples, sessionStorage, metadata);
        const filtered = updated.filter((id) => TASK_DEFINITIONS[id]);
        sessionStorage.setItem('completedTasks', JSON.stringify(filtered));
        setCompletedIds(filtered);
        const next = sequence.find((item) => (
            item === EYES_OPEN_BASELINE_CHECKPOINT
                ? !eyesOpenBaselineDone
                : !filtered.includes(item)
        ));
        if (next) setSelectedId(next);
    }, [eyesOpenBaselineDone, sequence]);

    const handleTaskComplete = useCallback(async (taskId, samples, signalStats, metadata) => {
        setActiveTaskId(null);
        setQualityCheckTaskId(taskId);
        try {
            const { quality } = await runSingleTaskQualityCheck(taskId, samples, {
                signalStats,
                metadata,
            });
            if (!quality.sufficient) {
                setQualityDialog({ taskId, quality, mode: 'force_repeat' });
                return;
            }
            await acceptTaskAttempt(taskId, samples, metadata);
        } catch (error) {
            setQualityDialog({
                taskId,
                mode: 'check_error',
                quality: { reason: error?.message || String(error) },
            });
        } finally {
            setQualityCheckTaskId(null);
        }
    }, [acceptTaskAttempt]);

    const startSelected = useCallback(() => {
        if (!baselineStatus.loaded || baselineStatus.error || !eyesClosedBaselineDone) return;
        if (selectedId === EYES_OPEN_BASELINE_CHECKPOINT) {
            sessionStorage.setItem(BASELINE_PHASE_REQUEST_KEY, BASELINE_RECORDING_PHASE.EYES_OPEN);
            navigate('/baselineCalibration1');
            return;
        }
        // The existing accepted attempt remains until this replacement passes quality checks.
        if (
            !selectedId
            || (!ALLOW_RERUN_COMPLETED_TASKS && completedIds.includes(selectedId))
            || !taskIsUnlocked(selectedId)
            || !isGoodSignal
        ) return;
        setActiveTaskId(selectedId);
    }, [baselineStatus.error, baselineStatus.loaded, completedIds, eyesClosedBaselineDone, isGoodSignal, navigate, selectedId, taskIsUnlocked]);

    const repeatFromDialog = useCallback(() => {
        const taskId = qualityDialog?.taskId;
        if (!taskId) return;
        setQualityDialog(null);
        setSelectedId(taskId);
        setActiveTaskId(taskId);
    }, [qualityDialog]);

    const repeatBaselineFromDialog = useCallback(async () => {
        const taskId = qualityDialog?.taskId;
        const baselinePhase = TASK_DEFINITIONS[taskId]?.baseline;
        if (!baselinePhase) return;
        try {
            await invalidateBaselinePhase(sessionStorage, baselinePhase);
            sessionStorage.setItem(BASELINE_PHASE_REQUEST_KEY, baselinePhase);
            setQualityDialog(null);
            navigate('/baselineCalibration1');
        } catch (error) {
            setQualityDialog({
                taskId,
                mode: 'baseline_storage_error',
                quality: {
                    needsBaselineRepeat: true,
                    reason: `The stored baseline could not be invalidated safely. ${error?.message || String(error)}`,
                },
            });
        }
    }, [navigate, qualityDialog]);

    if (activeTaskId) {
        const task = TASK_DEFINITIONS[activeTaskId];
        return (
            <div className="app-container">
                <LoggedInHeader />
                <main className="app-main">
                    <div className="task-selection-page">
                        <div className="ts-task-exec-header">
                            <h1 className="ts-page-title">{task.name}</h1>
                            <p className="ts-page-subtitle">Session {protocolSession}</p>
                        </div>
                        <OptimizedBatteryTask
                            key={`${activeTaskId}:${sessionDepth}`}
                            taskId={activeTaskId}
                            sessionDepth={sessionDepth}
                            onComplete={(samples, signalStats, metadata) => handleTaskComplete(activeTaskId, samples, signalStats, metadata)}
                            onBack={() => setActiveTaskId(null)}
                        />
                    </div>
                </main>
                <Footer />
            </div>
        );
    }

    const selectedMeta = selectedId === EYES_OPEN_BASELINE_CHECKPOINT ? null : TASK_DEFINITIONS[selectedId];
    const sessionLabel = {
        session_1: 'Foundational profile',
        session_2: 'Expanded cognitive profile',
        session_3: 'Complete Neuroprofile battery',
    }[sessionDepth];

    return (
        <div className="app-container">
            <LoggedInHeader />
            <main className="app-main">
                <div className="task-selection-page">
                    <div className="ts-page-header">
                        <h1 className="ts-page-title">Optimized Cognitive Task Battery</h1>
                        <p className="ts-page-subtitle">Session {protocolSession} · {sessionLabel} · Complete the required blocks in any order</p>
                    </div>

                    <div className={`ts-repeatability-notice${allEnabledCompleted ? ' ts-notice-complete' : ''}`}>
                        <FontAwesomeIcon icon={allEnabledCompleted ? faCircleCheck : faCircleInfo} className="ts-notice-icon" />
                        <div className="ts-notice-content">
                            <strong>{allEnabledCompleted ? 'All required blocks are complete.' : 'One uninterrupted block per task'}</strong>
                            <p>{allEnabledCompleted
                                ? 'The matched baselines and every task required for this session are ready for analysis.'
                                : 'The device remains connected between tasks. Responses are collected only after EEG scoring ends; a task with less than 20 contiguous clean seconds must be repeated.'}</p>
                        </div>
                    </div>

                    <div className="ts-sound-check-notice">
                        <span className="ts-notice-icon">🔊</span>
                        <div className="ts-notice-content">
                            <strong>Audio is part of this task battery.</strong>
                            <p>Check your volume before starting a task.</p>
                        </div>
                        <button type="button" className="ts-sound-check-btn" onClick={playSoundCheck}>
                            {soundChecking ? '🔊' : '▶'} Test volume
                        </button>
                    </div>

                    <div className="ts-layout">
                        <div className="ts-task-list optimized-sequence-list">
                            <p className="ts-group-label">
                                Session tasks
                                <span className="ts-group-progress">{completedEnabledCount}/{enabledTaskIds.length}</span>
                            </p>
                            {allTaskIds.slice().sort((left, right) => TASK_DEFINITIONS[left].number - TASK_DEFINITIONS[right].number).map((item, index) => {
                                if (item === EYES_OPEN_BASELINE_CHECKPOINT) {
                                    const done = eyesOpenBaselineDone;
                                    const locked = (
                                        !baselineStatus.loaded
                                        || !eyesClosedBaselineDone
                                        || Boolean(baselineStatus.error)
                                        || (!ALLOW_ANY_TASK_ORDER && index > nextPosition)
                                    );
                                    return (
                                        <button
                                            key={item}
                                            className={`ts-task-item optimized-baseline-item${selectedId === item ? ' selected' : ''}${done ? ' done' : ''}${locked ? ' locked' : ''}`}
                                            onClick={() => !locked && setSelectedId(item)}
                                            disabled={locked}
                                        >
                                            <span className="ts-task-item-icon">{done ? <FontAwesomeIcon icon={faCircleCheck} /> : locked ? <FontAwesomeIcon icon={faLock} /> : <FontAwesomeIcon icon={faEye} />}</span>
                                            <span className="ts-task-item-name">Eyes-open fixation baseline</span>
                                            <span className="ts-task-item-dur">60s</span>
                                        </button>
                                    );
                                }
                                const meta = TASK_DEFINITIONS[item];
                                const done = completedIds.includes(item);
                                const booked = enabledTaskIds.includes(item);
                                const unlocked = taskIsUnlocked(item);
                                return (
                                    <>
                                        {[1, 5, 10].includes(meta.number) && (
                                            <p className="ts-group-label">
                                                {meta.number === 1 ? 'Session 1' : meta.number === 5 ? 'Session 2' : 'Session 3'}
                                            </p>
                                        )}
                                    <button
                                        key={item}
                                        className={`ts-task-item${selectedId === item ? ' selected' : ''}${done ? ' done' : ''}${!unlocked ? ' locked' : ''}`}
                                        onClick={() => unlocked && setSelectedId(item)}
                                        disabled={!unlocked}
                                    >
                                        <span className="optimized-sequence-number">{index + 1}</span>
                                        <span className="ts-task-item-icon">
                                            {done ? <FontAwesomeIcon icon={faCircleCheck} /> : !unlocked ? <FontAwesomeIcon icon={faLock} /> : <FontAwesomeIcon icon={meta.eyeState === 'closed' ? faMoon : faEye} />}
                                        </span>
                                        <span className="ts-task-item-name">{meta.shortName}</span>
                                        <span className="ts-task-item-dur">{booked ? `${meta.duration}s` : 'Booking required'}</span>
                                    </button>
                                    </>
                                );
                            })}
                        </div>

                        <div className="ts-detail-panel">
                            {selectedId === EYES_OPEN_BASELINE_CHECKPOINT ? (
                                <>
                                    <h2 className="ts-detail-name">Eyes-open fixation baseline</h2>
                                    <div className="ts-detail-tags">
                                        <span className="ts-tag tag-eo"><FontAwesomeIcon icon={faEye} /> Eyes open</span>
                                        <span className="ts-tag tag-dur"><FontAwesomeIcon icon={faClock} /> 60s</span>
                                    </div>
                                    <p className="ts-detail-desc">Record a low-demand central-fixation reference immediately before the visual task block. Visual tasks are never compared only with the eyes-closed baseline.</p>
                                    <button
                                        className="ts-start-btn"
                                        onClick={startSelected}
                                        disabled={
                                            eyesOpenBaselineDone
                                            || !baselineStatus.loaded
                                            || !eyesClosedBaselineDone
                                            || Boolean(baselineStatus.error)
                                        }
                                    >
                                        <FontAwesomeIcon icon={eyesOpenBaselineDone ? faCircleCheck : faPlay} /> {eyesOpenBaselineDone ? 'Baseline complete' : 'Record eyes-open baseline'}
                                    </button>
                                </>
                            ) : selectedMeta ? (
                                <>
                                    <h2 className="ts-detail-name">
                                        {completedIds.includes(selectedId) && <span className="ts-done-badge"><FontAwesomeIcon icon={faCircleCheck} /> Completed</span>}
                                        {selectedMeta.name}
                                    </h2>
                                    <div className="ts-detail-tags">
                                        <span className={`ts-tag tag-${selectedMeta.eyeState === 'closed' ? 'ec' : 'eo'}`}>
                                            <FontAwesomeIcon icon={selectedMeta.eyeState === 'closed' ? faMoon : faEye} /> Eyes {selectedMeta.eyeState}
                                        </span>
                                        <span className="ts-tag tag-dur"><FontAwesomeIcon icon={faClock} /> {selectedMeta.duration}s EEG</span>
                                    </div>
                                    <p className="ts-detail-desc">{selectedMeta.description}</p>
                                    <button
                                        className="ts-start-btn"
                                        onClick={startSelected}
                                        disabled={(completedIds.includes(selectedId) && !ALLOW_RERUN_COMPLETED_TASKS) || !taskIsUnlocked(selectedId) || !isGoodSignal}
                                    >
                                        <FontAwesomeIcon icon={completedIds.includes(selectedId) && !ALLOW_RERUN_COMPLETED_TASKS ? faCircleCheck : faPlay} /> {completedIds.includes(selectedId) && !ALLOW_RERUN_COMPLETED_TASKS ? 'Completed · accepted attempt locked' : !isGoodSignal ? 'Wait for good signal' : completedIds.includes(selectedId) ? 'Re-run task · replace accepted data' : 'Read task instructions'}
                                    </button>
                                </>
                            ) : null}
                        </div>
                    </div>
                </div>
            </main>

            <div className="nav-sub-footer">
                <button
                    className="btn-next-eeg"
                    disabled={!allEnabledCompleted || Boolean(qualityCheckTaskId) || Boolean(qualityDialog)}
                    onClick={() => navigate('/upload')}
                >
                    {t('nav.next')} ({completedEnabledCount}/{enabledTaskIds.length}) <FontAwesomeIcon icon={faArrowRight} />
                </button>
            </div>

            {qualityCheckTaskId && (
                <div className="ts-quality-blocking-overlay" role="alert" aria-live="assertive">
                    <div className="ts-quality-blocking-panel">
                        <FontAwesomeIcon icon={faSpinner} spin />
                        <strong>Checking contiguous clean EEG</strong>
                        <span>The recording cannot be saved until task-level signal quality is validated.</span>
                    </div>
                </div>
            )}
            <TaskQualityModal
                taskName={qualityDialog ? TASK_DEFINITIONS[qualityDialog.taskId]?.name || qualityDialog.taskId : ''}
                signalStatus={signalStatus}
                poorSignal={poorSignal}
                qualityDialog={qualityDialog}
                isGoodSignal={isGoodSignal}
                repeatSignalReady={repeatSignalReady}
                goodSignalStableMs={goodSignalStableMs}
                onRepeat={repeatFromDialog}
                onRepeatBaseline={repeatBaselineFromDialog}
                t={t}
            />
            <Footer />
        </div>
    );
};

export default TaskSelection;
