import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import LoggedInHeader from '../components/LoggedInHeader';
import Footer from '../components/footer';
import EegWaveform from '../components/EegWaveform';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faCircleCheck, faMoon, faEye, faStar, faClock,
    faArrowRight, faPlay, faTriangleExclamation, faLock, faCircleInfo, faSpinner, faRotate,
} from '@fortawesome/free-solid-svg-icons';


import VisualImageryTask from '../components/tasks/VisualImageryTask';
import AttentionFocusTask from '../components/tasks/AttentionFocusTask';
import MentalMathTask from '../components/tasks/MentalMathTask';
import WorkingMemoryTask from '../components/tasks/WorkingMemoryTask';
import LanguageProcessingTask from '../components/tasks/LanguageProcessingTask';
import MotorImageryTask from '../components/tasks/MotorImageryTask';
import CognitiveLoadTask from '../components/tasks/CognitiveLoadTask';
import EmotionFaceTask from '../components/tasks/EmotionFaceTask';
import DiverseThinkingTask from '../components/tasks/DiverseThinkingTask';
import ReappraisalTask from '../components/tasks/ReappraisalTask';
import CuriosityTask from '../components/tasks/CuriosityTask';
import NumFormTask from '../components/tasks/NumFormTask';
import OrderSurpriseTask from '../components/tasks/OrderSurpriseTask';
import SemanticMemoryTask from '../components/tasks/SemanticMemoryTask';
import BodyScanTask from '../components/tasks/BodyScanTask';
import ColorPerceptionTask from '../components/tasks/ColorPerceptionTask';
import wsEegService, { CONNECTION_STATUS } from '../service/wsEegService';
import { runSingleTaskQualityCheck } from '../service/analysisService';
import { commitTaskAttempt, isRepeatSignalReady, resolveTaskQualityOutcome } from '../service/taskQualityGate.mjs';

import '../styles/liveEegReading.css';
import '../styles/taskSelection.css';


const TASK_META = {
    visual_imagery: { name: 'Visual Imagery', duration: 60, eyesClosed: true, description: 'Visual imagery captures the ability to generate and stabilize internal representations without external sensory input. It broadens the assessment to profile imaginative style and simulation strength, differentiating creative individuals from those who strictly excel under structured executive demand', advanced: false },
    attention_focus: { name: 'Focused Attention', duration: 60, eyesClosed: true, description: 'This task isolates the ability to maintain stable internal focus with minimal external stimulation, which is foundational to all other cognitive domains. It evaluates attentional volatility and lapse frequency while providing a clean, low-artefact calibration segment.', advanced: false },
    mental_math: { name: 'Mental Math', duration: 60, eyesClosed: true, description: 'This task imposes controlled executive demand to gauge processing efficiency and cognitive strain without requiring speech or movement. It serves as a primary index for distinguishing individuals who remain neurally efficient under pressure from those who require disproportionate effort.', advanced: false },
    emotion_face: { name: 'Emotion Recognition', duration: 114, eyesClosed: false, description: 'This task introduces affective appraisal into the battery, acting as a bridge between executive and emotional domains. It is highly valuable for evaluating socio-emotional attunement and motivational bias, such as approach versus withdrawal tendencies.', advanced: false },
    working_memory: { name: 'Working Memory', duration: 60, eyesClosed: true, description: 'A dedicated working-memory task isolates cognitive load effects cleanly, enabling interpretable capacity curves. This distinction is vital for separating high-capacity individuals from those who must rely on compensatory effort as task load increases.', advanced: true },
    language_processing: { name: 'Language Processing', duration: 60, eyesClosed: true, description: ' Language tasks introduce a conceptually structured domain that reflects reasoning, communication style, and semantic organization. It helps differentiate participants strong in verbal-semantic integration from those whose strengths lie in imagery or pure cognitive control.', advanced: true },
    motor_imagery: { name: 'Motor Imagery', duration: 60, eyesClosed: true, description: 'This task extends the simulation domain into action-oriented cognition by testing the ability to internally simulate action without overt movement. It complements visual imagery by probing embodied thinking styles and planning biases.', advanced: true },
    cognitive_load: { name: 'Cognitive Load', duration: 60, eyesClosed: true, description: 'This serves as a domain-general executive stress test by monitoring the brains behavior under conflict, switching, and interference. It is critical for understanding an individuals overload threshold and how they coordinate competing demands', advanced: true },
    diverse_thinking: { name: 'Creative Fluency', duration: 96, eyesClosed: false, description: 'Generate creative and unusual uses for two given objects/concepts.', advanced: true },
    reappraisal: { name: 'Perspective Shift', duration: 96, eyesClosed: false, description: 'Deliberately shift perspective on two contrasting scenarios.', advanced: true },
    curiosity: { name: 'Curiosity Reveal', duration: 45, eyesClosed: false, description: 'Watch a short reveal video with full attention and genuine curiosity.', advanced: true },
    num_form: { name: 'Numerical Preference', duration: 60, eyesClosed: false, description: 'Evaluate aesthetic preference between numbers and forms.', advanced: true },
    order_surprise: { name: 'Order & Surprise', duration: 60, eyesClosed: false, description: 'Count symmetrical (ORDER) vs non-symmetrical (SURPRISE) shapes.', advanced: true },
    semantic_memory: { name: 'Semantic Memory Retrieval', duration: 50, eyesClosed: true, description: 'Alternating retrieval and rest segments probing semantic access, category recall, and transition control.', advanced: false },
    body_scan: { name: 'Body Scan', duration: 60, eyesClosed: true, description: 'A guided internal-attention task probing interoceptive focus, calm-state stability, and post-load recovery.', advanced: false },
    color_perception: { name: 'Color Perception', duration: 60, eyesClosed: false, description: 'Sequential color-viewing task probing visual engagement, evaluative response, and habituation style.', advanced: false },
};


const PATHWAY_TASKS = {
    personal: ['working_memory', 'language_processing', 'diverse_thinking', 'motor_imagery', 'cognitive_load'],
    connection: ['motor_imagery', 'cognitive_load', 'reappraisal', 'curiosity'],
    lifestyle: ['motor_imagery', 'cognitive_load', 'order_surprise', 'num_form'],
};

// Always-visible general tasks (no booking required)
const COGNITIVE_TASKS = [
    'visual_imagery', 'attention_focus', 'mental_math', 'emotion_face',
];

const SESSION_THREE_TASKS = ['semantic_memory', 'body_scan', 'color_perception'];

// Task id → component
const TASK_COMPONENTS = {
    visual_imagery: VisualImageryTask,
    attention_focus: AttentionFocusTask,
    mental_math: MentalMathTask,
    working_memory: WorkingMemoryTask,
    language_processing: LanguageProcessingTask,
    motor_imagery: MotorImageryTask,
    cognitive_load: CognitiveLoadTask,
    emotion_face: EmotionFaceTask,
    diverse_thinking: DiverseThinkingTask,
    reappraisal: ReappraisalTask,
    curiosity: CuriosityTask,
    num_form: NumFormTask,
    order_surprise: OrderSurpriseTask,
    semantic_memory: SemanticMemoryTask,
    body_scan: BodyScanTask,
    color_perception: ColorPerceptionTask,
};


const FORCED_REPEAT_KEY = 'taskQualityForcedRepeats';

const signalDisplay = (t, status, poorSignal) => {
    const connected = status === CONNECTION_STATUS.CONNECTED;
    if (!connected) {
        return {
            good: false,
            cls: 'disconnected',
            text: t('taskSelection.signalDisconnected', { defaultValue: 'Device not connected' }),
        };
    }
    if (poorSignal >= 200) {
        return {
            good: false,
            cls: 'not-worn',
            text: t('taskSelection.signalNotWorn', { defaultValue: 'Signal: Not worn' }),
        };
    }
    if (poorSignal < 25) {
        return {
            good: true,
            cls: 'good',
            text: t('taskSelection.signalGood', { defaultValue: 'Signal: Good' }),
        };
    }
    return {
        good: false,
        cls: 'noisy',
        text: t('taskSelection.signalNoisy', { defaultValue: 'Signal: Noisy' }),
    };
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
    onKeep,
    t,
}) => {
    if (!qualityDialog) return null;

    const signal = signalDisplay(t, signalStatus, poorSignal);
    const stableSecondsRemaining = Math.max(0, Math.ceil((5000 - Number(goodSignalStableMs || 0)) / 1000));
    const mode = qualityDialog.mode;
    const repeatRequired = mode === 'force_repeat';
    const checkError = mode === 'check_error';
    const title = checkError
        ? t('taskSelection.qualityCheckErrorTitle', { defaultValue: 'Signal check could not finish' })
        : repeatRequired
            ? t('taskSelection.qualityRepeatTitle', { defaultValue: 'Repeat this task after improving the signal' })
            : t('taskSelection.qualitySavedWarningTitle', { defaultValue: 'Task saved after repeat' });
    const body = checkError
        ? t('taskSelection.qualityCheckErrorBody', { defaultValue: 'The task was saved, but the quick signal check was not available. You may repeat the task if the live signal is not good.' })
        : repeatRequired
            ? t('taskSelection.qualityRepeatBody', { defaultValue: 'This recording did not contain enough usable EEG evidence. Adjust the headset, wait for a stable good signal, then repeat the task.' })
            : t('taskSelection.qualitySavedWarningBody', { defaultValue: 'The required repeat was saved, but evidence may still be limited. You can repeat again after the signal is good, or continue with this saved attempt.' });

    return (
        <div className="ts-quality-modal-backdrop" role="presentation">
            <div className="ts-quality-modal" role="dialog" aria-modal="true" aria-labelledby="task-quality-title">
                <div className="ts-quality-modal-header">
                    <div>
                        <p className="ts-quality-kicker">{t('taskSelection.qualityKicker', { defaultValue: 'Task signal check' })}</p>
                        <h2 id="task-quality-title">{title}</h2>
                        <p>{t('taskSelection.qualityTaskName', { defaultValue: 'Task: {{taskName}}', taskName })}</p>
                    </div>
                    <div className={`ts-quality-signal-pill ${signal.cls}`}>
                        <FontAwesomeIcon icon={signal.good ? faCircleCheck : faTriangleExclamation} />
                        <span>{signal.text}</span>
                    </div>
                </div>

                <p className="ts-quality-modal-body">{body}</p>
                <div className="ts-quality-chart-wrap">
                    <div className="ts-quality-chart-header">
                        {t('taskSelection.qualityLivePlot', { defaultValue: 'Live EEG signal' })}
                    </div>
                    <div className="ts-quality-chart-area">
                        <EegWaveform status={signalStatus} />
                    </div>
                </div>

                <div className="ts-quality-stages">
                    <div className="ts-quality-stage">
                        <span className="ts-stage-number">1</span>
                        <div>
                            <strong>{t('taskSelection.qualityStageAdjustTitle', { defaultValue: 'Adjust the headset' })}</strong>
                            <p>{t('taskSelection.qualityStageAdjustBody', { defaultValue: 'Place the front sensor flat against the forehead, about two inches above the eyebrows. Move hair away from the contacts and press gently if the app says Not worn.' })}</p>
                        </div>
                    </div>
                    <div className="ts-quality-stage">
                        <span className="ts-stage-number">2</span>
                        <div>
                            <strong>{t('taskSelection.qualityStageStabilizeTitle', { defaultValue: 'Let the signal stabilize' })}</strong>
                            <p>{t('taskSelection.qualityStageStabilizeBody', { defaultValue: 'Stay still, relax your jaw and forehead, and wait 5 to 10 seconds until the status above shows Signal: Good.' })}</p>
                        </div>
                    </div>
                    <div className={`ts-quality-stage ${repeatSignalReady ? 'ready' : ''}`}>
                        <span className="ts-stage-number">3</span>
                        <div>
                            <strong>{t('taskSelection.qualityStageRepeatTitle', { defaultValue: 'Repeat the task' })}</strong>
                            <p>{repeatSignalReady
                                ? t('taskSelection.qualityStageReadyBody', { defaultValue: 'The signal is good. You can now repeat the task; the new recording will replace the previous one.' })
                                : isGoodSignal
                                    ? t('taskSelection.qualityStageStabilizingBody', { defaultValue: 'Keep the signal good for {{seconds}} more seconds. The repeat button unlocks after 5 continuous seconds of good signal.', seconds: stableSecondsRemaining })
                                    : t('taskSelection.qualityStageWaitingBody', { defaultValue: 'The repeat button unlocks when the live signal is good for 5 continuous seconds.' })}</p>
                        </div>
                    </div>
                </div>

                <div className="ts-quality-actions">
                    {!repeatRequired && (
                        <button className="ts-quality-secondary" onClick={onKeep}>
                            {t('taskSelection.qualityKeepAttempt', { defaultValue: 'Keep saved attempt' })}
                        </button>
                    )}
                    <button className="ts-quality-primary" onClick={onRepeat} disabled={!repeatSignalReady}>
                        <FontAwesomeIcon icon={faRotate} />
                        {repeatSignalReady
                            ? t('taskSelection.qualityRepeatButton', { defaultValue: 'Repeat task now' })
                            : isGoodSignal
                                ? t('taskSelection.qualityStabilizingButton', { defaultValue: 'Hold good signal for {{seconds}}s', seconds: stableSecondsRemaining })
                                : t('taskSelection.qualityWaitingButton', { defaultValue: 'Waiting for good signal' })}
                    </button>
                </div>
            </div>
        </div>
    );
};
const TaskSelection = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const pathway = sessionStorage.getItem('selectedPathway') || 'personal';
    const hasAdvancedBooking = sessionStorage.getItem('hasAdvancedBooking') === 'true';
    const hasSessionThree = sessionStorage.getItem('hasSessionThree') === 'true';

    // Build visible task list: cognitive + pathway-specific advanced
    const advancedTaskIds = PATHWAY_TASKS[pathway] || [];
    const visibleTaskIds = [...COGNITIVE_TASKS, ...advancedTaskIds];

    const [selectedId, setSelectedId] = useState(visibleTaskIds[0] || null);
    const [activeTaskId, setActiveTaskId] = useState(null); // currently executing
    const [completedIds, setCompletedIds] = useState(() => {
        try { return JSON.parse(sessionStorage.getItem('completedTasks') || '[]'); }
        catch { return []; }
    });

    // All tasks that are currently unlocked — must ALL be done before analysis
    const enabledTaskIds = [
        ...COGNITIVE_TASKS,
        ...(hasAdvancedBooking ? advancedTaskIds : []),
        ...(hasSessionThree ? SESSION_THREE_TASKS : []),
    ];
    const completedEnabledCount = enabledTaskIds.filter(id => completedIds.includes(id)).length;
    const allEnabledCompleted = completedEnabledCount === enabledTaskIds.length;
    const hasNewSessionUnlocked = hasAdvancedBooking || hasSessionThree;
    const pendingEnabledIds = enabledTaskIds.filter(id => !completedIds.includes(id));

    const selectedMeta = selectedId ? TASK_META[selectedId] : null;
    const [qualityCheckTaskId, setQualityCheckTaskId] = useState(null);
    const [qualityDialog, setQualityDialog] = useState(null);
    const [signalStatus, setSignalStatus] = useState(wsEegService.getStatus());
    const [poorSignal, setPoorSignal] = useState(wsEegService.getPoorSignal());
    const [forcedRepeatByTask, setForcedRepeatByTask] = useState(() => {
        try { return JSON.parse(sessionStorage.getItem(FORCED_REPEAT_KEY) || '{}'); }
        catch { return {}; }
    });
    const [goodSignalStableMs, setGoodSignalStableMs] = useState(0);

    const isGoodSignal = signalStatus === CONNECTION_STATUS.CONNECTED && poorSignal < 25;
    const repeatSignalReady = isRepeatSignalReady({ isGoodSignal, goodSignalStableMs });

    useEffect(() => {
        const unsubStatus = wsEegService.on('status', setSignalStatus);
        const unsubEeg = wsEegService.on('eegData', d => setPoorSignal(d.poorSignal));
        wsEegService.fetchStatus();
        return () => { unsubStatus(); unsubEeg(); };
    }, []);

    useEffect(() => {
        if (!qualityDialog || !isGoodSignal) {
            setGoodSignalStableMs(0);
            return undefined;
        }

        const startedAt = Date.now();
        setGoodSignalStableMs(0);
        const timer = setInterval(() => {
            setGoodSignalStableMs(Date.now() - startedAt);
        }, 250);
        return () => clearInterval(timer);
    }, [qualityDialog?.taskId, qualityDialog?.mode, isGoodSignal]);

    const updateForcedRepeatByTask = useCallback((updater) => {
        setForcedRepeatByTask(prev => {
            const next = typeof updater === 'function' ? updater(prev) : updater;
            sessionStorage.setItem(FORCED_REPEAT_KEY, JSON.stringify(next));
            return next;
        });
    }, []);

    const clearForcedRepeatForTask = useCallback((taskId) => {
        updateForcedRepeatByTask(prev => {
            const next = { ...prev };
            delete next[taskId];
            return next;
        });
    }, [updateForcedRepeatByTask]);

    const acceptTaskAttempt = useCallback((taskId, samples) => {
        const updated = commitTaskAttempt(taskId, samples);
        setCompletedIds(updated);
        clearForcedRepeatForTask(taskId);
    }, [clearForcedRepeatForTask]);

    const handleStartTask = useCallback(() => {
        if (!selectedId) return;
        if (completedIds.includes(selectedId)) {
            clearForcedRepeatForTask(selectedId);
        }
        setActiveTaskId(selectedId);
    }, [selectedId, completedIds, clearForcedRepeatForTask]);

    const handleTaskComplete = useCallback(async (taskId, samples, signalStats = null) => {
        setActiveTaskId(null);
        setQualityCheckTaskId(taskId);

        try {
            const { quality } = await runSingleTaskQualityCheck(taskId, samples, { signalStats });
            const outcome = resolveTaskQualityOutcome(quality, {
                forcedRepeatUsed: Boolean(forcedRepeatByTask[taskId]),
            });

            if (outcome === 'force_repeat') {
                updateForcedRepeatByTask(prev => ({ ...prev, [taskId]: true }));
                setQualityDialog({ taskId, quality, mode: 'force_repeat' });
                return;
            }

            acceptTaskAttempt(taskId, samples);
            if (outcome === 'accept_with_warning') {
                setQualityDialog({ taskId, quality, mode: 'accepted_warning' });
            }
        } catch (error) {
            acceptTaskAttempt(taskId, samples);
            setQualityDialog({
                taskId,
                mode: 'check_error',
                quality: {
                    usableFeatureCount: 0,
                    taskConfidence: 'unknown',
                    error: error?.message || String(error),
                },
            });
        } finally {
            setQualityCheckTaskId(null);
        }
    }, [forcedRepeatByTask, updateForcedRepeatByTask, acceptTaskAttempt]);

    const handleRepeatFromQualityDialog = useCallback(() => {
        if (!qualityDialog?.taskId) return;
        const taskId = qualityDialog.taskId;
        setSelectedId(taskId);
        setQualityDialog(null);
        setActiveTaskId(taskId);
    }, [qualityDialog]);

    const handleKeepQualityAttempt = useCallback(() => {
        setQualityDialog(null);
    }, []);

    const handleTaskBack = useCallback(() => {
        setActiveTaskId(null);
    }, []);

    if (activeTaskId) {
        const TaskComp = TASK_COMPONENTS[activeTaskId];
        return (
            <div className="app-container">
                <LoggedInHeader />
                <main className="app-main">
                    <div className="task-selection-page">
                        <div className="ts-task-exec-header">
                            <h1 className="ts-page-title">{t(`taskMeta.${activeTaskId}.name`, { defaultValue: TASK_META[activeTaskId]?.name })}</h1>
                            <p className="ts-page-subtitle">{t('taskSelection.taskSubtitle')}</p>
                        </div>
                        <TaskComp
                            onComplete={(samples, signalStats) => handleTaskComplete(activeTaskId, samples, signalStats)}
                            onBack={handleTaskBack}
                        />
                    </div>
                </main>
                <Footer />
            </div>
        );
    }


    const pathwayLabel = {
        personal: t('taskSelection.pathwayPersonal'),
        connection: t('taskSelection.pathwayConnection'),
        lifestyle: t('taskSelection.pathwayLifestyle'),
    }[pathway] || pathway;

    return (
        <div className="app-container">
            <LoggedInHeader />
            <main className="app-main">
                <div className="task-selection-page">

                    <div className="ts-page-header">
                        <h1 className="ts-page-title">{t('tasks.title')}</h1>
                        <p className="ts-page-subtitle">{t('taskSelection.subtitle', { pathway: pathwayLabel })}</p>
                    </div>

                    {hasNewSessionUnlocked && (
                        <div className={`ts-repeatability-notice${allEnabledCompleted ? ' ts-notice-complete' : ''}`}>
                            <FontAwesomeIcon
                                icon={allEnabledCompleted ? faCircleCheck : faCircleInfo}
                                className="ts-notice-icon"
                            />
                            <div className="ts-notice-content">
                                {allEnabledCompleted ? (
                                    <strong>{t('taskSelection.allTasksDone', { defaultValue: 'All tasks completed — ready for analysis!' })}</strong>
                                ) : (
                                    <>
                                        <strong>{t('taskSelection.repeatabilityTitle', { defaultValue: 'All sessions must be completed before analysis' })}</strong>
                                        <p>{t('taskSelection.repeatabilityBody', { defaultValue: 'You have unlocked new session tasks. To ensure the repeatability of your neural profile measurements, all enabled tasks — including those from earlier sessions — must be completed each time you run a full assessment. You are welcome to tackle the new tasks first, but please return to any remaining earlier tasks before continuing to analysis.' })}</p>
                                        {pendingEnabledIds.length > 0 && (
                                            <p className="ts-notice-pending">
                                                <strong>{t('taskSelection.stillNeeded', { defaultValue: 'Still needed:' })}</strong>{' '}
                                                {pendingEnabledIds.map(id => t(`taskMeta.${id}.name`, { defaultValue: TASK_META[id]?.name })).join(', ')}
                                            </p>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>
                    )}

                    <div className="ts-layout">
                        {/* ── Task list ── */}
                        <div className="ts-task-list">
                            {/* General tasks group */}
                            <p className="ts-group-label">
                                {t('taskSelection.generalTasks')}
                                <span className="ts-group-progress">
                                    {COGNITIVE_TASKS.filter(id => completedIds.includes(id)).length}/{COGNITIVE_TASKS.length}
                                </span>
                            </p>
                            {COGNITIVE_TASKS.map(id => {
                                const meta = TASK_META[id];
                                const done = completedIds.includes(id);
                                return (
                                    <button
                                        key={id}
                                        className={`ts-task-item${selectedId === id ? ' selected' : ''}${done ? ' done' : ''}`}
                                        onClick={() => setSelectedId(id)}
                                    >
                                        <span className="ts-task-item-icon">
                                            {done
                                                ? <FontAwesomeIcon icon={faCircleCheck} />
                                                : meta.eyesClosed
                                                    ? <FontAwesomeIcon icon={faMoon} />
                                                    : <FontAwesomeIcon icon={faEye} />}
                                        </span>
                                        <span className="ts-task-item-name">{t(`taskMeta.${id}.name`, { defaultValue: meta.name })}</span>
                                        <span className="ts-task-item-dur">{meta.duration}s</span>
                                    </button>
                                );
                            })}

                            {/* Advanced tasks group */}
                            {advancedTaskIds.length > 0 && (
                                <>
                                    <p className="ts-group-label" style={{ marginTop: 16 }}>
                                        {t('taskSelection.advancedTasks', { pathway: pathwayLabel })}
                                    </p>
                                    {advancedTaskIds.map(id => {
                                        const meta = TASK_META[id];
                                        const done = completedIds.includes(id);
                                        const locked = !hasAdvancedBooking;
                                        return (
                                            <button
                                                key={id}
                                                className={`ts-task-item ts-task-item-advanced${selectedId === id ? ' selected' : ''}${done ? ' done' : ''}${locked ? ' locked' : ''}`}
                                                onClick={() => !locked && setSelectedId(id)}
                                                disabled={locked}
                                            >
                                                <span className="ts-task-item-icon">
                                                    {locked
                                                        ? <FontAwesomeIcon icon={faLock} />
                                                        : done
                                                            ? <FontAwesomeIcon icon={faCircleCheck} />
                                                            : <FontAwesomeIcon icon={faStar} />}
                                                </span>
                                                <span className="ts-task-item-name">{t(`taskMeta.${id}.name`, { defaultValue: meta.name })}</span>
                                                <span className="ts-task-item-dur">{locked ? t('taskSelection.locked') : `${meta.duration}s`}</span>
                                            </button>
                                        );
                                    })}
                                </>
                            )}

                            <p className="ts-group-label" style={{ marginTop: 16 }}>
                                {t('taskSelection.sessionThreeTasks', { defaultValue: 'Session 3 — Moderatory Assessment' })}
                                {!hasSessionThree && (
                                    <span className="ts-group-lock-hint">
                                        &nbsp;· {t('taskSelection.sessionThreeLock', { defaultValue: 'Requires 2nd partner booking to unlock' })}
                                    </span>
                                )}
                                {hasSessionThree && (
                                    <span className="ts-group-progress">
                                        {SESSION_THREE_TASKS.filter(id => completedIds.includes(id)).length}/{SESSION_THREE_TASKS.length}
                                    </span>
                                )}
                            </p>
                            {SESSION_THREE_TASKS.map(id => {
                                const meta = TASK_META[id];
                                const done = completedIds.includes(id);
                                const locked = !hasSessionThree;
                                return (
                                    <button
                                        key={id}
                                        className={`ts-task-item ts-task-item-advanced${selectedId === id ? ' selected' : ''}${done ? ' done' : ''}${locked ? ' locked' : ''}`}
                                        onClick={() => !locked && setSelectedId(id)}
                                        disabled={locked}
                                    >
                                        <span className="ts-task-item-icon">
                                            {locked
                                                ? <FontAwesomeIcon icon={faLock} />
                                                : done
                                                    ? <FontAwesomeIcon icon={faCircleCheck} />
                                                    : meta.eyesClosed
                                                        ? <FontAwesomeIcon icon={faMoon} />
                                                        : <FontAwesomeIcon icon={faEye} />}
                                        </span>
                                        <span className="ts-task-item-name">{t(`taskMeta.${id}.name`, { defaultValue: meta.name })}</span>
                                        <span className="ts-task-item-dur">{locked ? t('taskSelection.locked') : `${meta.duration}s`}</span>
                                    </button>
                                );
                            })}
                        </div>

                        {/* ── Task detail panel ── */}
                        <div className="ts-detail-panel">
                            {selectedMeta ? (
                                <>
                                    <h2 className="ts-detail-name">
                                        {completedIds.includes(selectedId) && <span className="ts-done-badge"><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 4 }} />{t('taskSelection.completed')}</span>}
                                        {t(`taskMeta.${selectedId}.name`, { defaultValue: selectedMeta.name })}
                                    </h2>

                                    <div className="ts-detail-tags">
                                        <span className={`ts-tag${selectedMeta.eyesClosed ? ' tag-ec' : ' tag-eo'}`}>
                                            {selectedMeta.eyesClosed
                                                ? <><FontAwesomeIcon icon={faMoon} style={{ marginRight: 4 }} />{t('taskSelection.eyesClosed')}</>
                                                : <><FontAwesomeIcon icon={faEye} style={{ marginRight: 4 }} />{t('taskSelection.eyesOpen')}</>}
                                        </span>
                                        <span className="ts-tag tag-dur"><FontAwesomeIcon icon={faClock} style={{ marginRight: 4 }} />{selectedMeta.duration}s</span>
                                        {selectedMeta.advanced && <span className="ts-tag tag-adv"><FontAwesomeIcon icon={faStar} style={{ marginRight: 4 }} />{t('taskSelection.advanced')}</span>}
                                    </div>

                                    {completedIds.length >= 4 && (
                                        <p className="ts-detail-desc">{t(`taskMeta.${selectedId}.description`, { defaultValue: selectedMeta.description })}</p>
                                    )}

                                    {completedIds.includes(selectedId) ? (
                                        <p className="ts-already-done">
                                            <FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />
                                            {t('taskSelection.alreadyDone')}
                                        </p>
                                    ) : null}

                                    <button
                                        className="ts-start-btn"
                                        onClick={handleStartTask}
                                    >
                                        <FontAwesomeIcon icon={faPlay} style={{ marginRight: 8 }} />
                                        {completedIds.includes(selectedId) ? t('taskSelection.runAgain') : t('taskSelection.taskInstructions')}
                                    </button>
                                </>
                            ) : (
                                <p className="ts-detail-placeholder">{t('taskSelection.selectPlaceholder')}</p>
                            )}
                        </div>
                    </div>

                </div>
            </main>
            <div className="nav-sub-footer">
                <button
                    className="btn-next-eeg"
                    disabled={!allEnabledCompleted || Boolean(qualityCheckTaskId) || qualityDialog?.mode === 'force_repeat'}
                    onClick={() => navigate('/upload')}
                >
                    {t('nav.next')} ({completedEnabledCount}/{enabledTaskIds.length}) <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 6 }} />
                </button>
            </div>
            {qualityCheckTaskId && (
                <div className="ts-quality-blocking-overlay" role="alert" aria-live="assertive">
                    <div className="ts-quality-blocking-panel">
                        <FontAwesomeIcon icon={faSpinner} spin />
                        <strong>{t('taskSelection.qualityBlockingTitle', { defaultValue: 'Checking task signal quality' })}</strong>
                        <span>{t('taskSelection.qualityBlockingBody', { defaultValue: 'Please wait while the recording is checked. Analysis and navigation are blocked until this finishes.' })}</span>
                    </div>
                </div>
            )}
            <TaskQualityModal
                taskName={qualityDialog ? t(`taskMeta.${qualityDialog.taskId}.name`, { defaultValue: TASK_META[qualityDialog.taskId]?.name || qualityDialog.taskId }) : ''}
                signalStatus={signalStatus}
                poorSignal={poorSignal}
                qualityDialog={qualityDialog}
                isGoodSignal={isGoodSignal}
                repeatSignalReady={repeatSignalReady}
                goodSignalStableMs={goodSignalStableMs}
                onRepeat={handleRepeatFromQualityDialog}
                onKeep={handleKeepQualityAttempt}
                t={t}
            />
            <Footer />
        </div>
    );
};

export default TaskSelection;
