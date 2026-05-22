/**
 * TaskRunner.jsx
 *
 * Shared execution UI component used by all task components.
 * Handles: countdown display → cue/task phases → completion.
 *
 * Props:
 *   phases        – array (from useTaskRunner)
 *   taskName      – string  display name
 *   eyesClosed    – bool    whether user should close eyes
 *   introText     – string  shown before task starts
 *   onComplete    – (samples[]) => void
 *   onBack        – () => void
 */

import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useTaskRunner } from '../../hooks/useTaskRunner';
import '../../styles/taskSelection.css';
import wsEegService from '../../service/wsEegService';

// Recording phase types
const RECORD_TYPES = new Set(['task', 'thinking', 'viewing', 'video', 'wait']);

const TaskRunner = ({ phases, taskName, eyesClosed, introText, onComplete, onBack }) => {
    const { t } = useTranslation();
    const {
        runState, countdown, currentPhase, elapsedPct,
        start, abort, isIdle, isCountingDown, isRunning, isDone,
    } = useTaskRunner(phases);

    const handleStart = useCallback(() => {
        start(onComplete);
    }, [start, onComplete]);

    const handleAbort = useCallback(() => {
        abort();
        onBack();
    }, [abort, onBack]);


    const isRecordingPhase = currentPhase && RECORD_TYPES.has(currentPhase.type);
    const totalDuration = phases.reduce((sum, p) => sum + (p.duration || 0), 0);

    if (isIdle) {
        return (
            <div className="task-runner-card">
                <h2 className="task-runner-name">{t('taskRunner.readInstruction')}</h2>
                <div className="task-runner-badges">
                    {eyesClosed !== undefined && (
                        <div className={`task-eyes-badge${eyesClosed ? ' eyes-closed' : ' eyes-open'}`}>
                            {eyesClosed ? t('taskRunner.eyesClosed') : t('taskRunner.eyesOpen')}
                        </div>
                    )}
                    <div className="task-eyes-badge task-duration-badge">
                        ⏱ {totalDuration}s
                    </div>
                </div>
                <div className="task-runner-sound-notice">
                    🔊 {t('taskRunner.soundNotice')}
                </div>
                <div className="task-runner-intro">
                    {Array.isArray(introText)
                        ? <ul className="task-runner-intro-bullets">{introText.map((line, i) => <li key={i}>{line}</li>)}</ul>
                        : introText}
                </div>
                <p className="task-runner-countdown-hint">
                    {t('taskRunner.countdownHint')}
                </p>
                <div className="task-runner-actions">
                    <button className="task-runner-btn-back" onClick={onBack}>{t('taskRunner.cancel')}</button>
                    <button className="task-runner-btn-start" onClick={handleStart}>{t('taskRunner.start')}</button>
                </div>
            </div>
        );
    }

    if (isCountingDown) {
        return (
            <div className="task-runner-card task-runner-countdown-screen">
                <p className="task-runner-get-ready">{t('taskRunner.getReady')}</p>
                <div className="task-runner-big-countdown">{countdown}</div>
                <p className="task-runner-countdown-caption">{t('taskRunner.listenBeeps')}</p>
            </div>
        );
    }

    if (isRunning && currentPhase) {
        return (
            <div className={`task-runner-card task-runner-phase${isRecordingPhase ? ' phase-recording' : ' phase-cue'}`}>
                <div className="task-runner-phase-badge">
                    {isRecordingPhase
                        ? t('taskRunner.recording')
                        : currentPhase.type === 'get_ready' ? t('taskRunner.getReadyBadge') : t('taskRunner.readInstructions')}
                </div>
                <h3 className="task-runner-phase-instruction">
                    {eyesClosed && isRecordingPhase ? null : (currentPhase.instruction || taskName)}
                </h3>
                {currentPhase.image && (
                    <img
                        className="task-runner-face-image"
                        src={currentPhase.image}
                        alt={t('taskRunner.emotionalFaceAlt')}
                    />
                )}
                {eyesClosed && isRecordingPhase && (
                    <p className="task-runner-eyes-hint">{t('taskRunner.eyesClosedHint')}</p>
                )}
                {!eyesClosed && isRecordingPhase && (
                    <p className="task-runner-eyes-hint">{t('taskRunner.eyesOpenHint')}</p>
                )}
                <div className="task-runner-progress-wrap">
                    <div className="task-runner-progress-bar" style={{ width: `${elapsedPct}%` }} />
                    <span className="task-runner-progress-text">{elapsedPct}%</span>
                </div>
                <button className="task-runner-btn-abort" onClick={handleAbort}>{t('taskRunner.abort')}</button>
            </div>
        );
    }

    if (isDone) {
        return (
            <div className="task-runner-card task-runner-done-screen">
                <div className="task-runner-done-icon">✅</div>
                <h2 className="task-runner-done-title">{t('taskRunner.complete', { taskName })}</h2>
                <p className="task-runner-done-msg">
                    {t('taskRunner.doneMsg')}
                </p>
                <button className="task-runner-btn-start" onClick={onBack}>{t('taskRunner.backToTasks')}</button>
            </div>
        );
    }

    return null;
};

export default TaskRunner;
