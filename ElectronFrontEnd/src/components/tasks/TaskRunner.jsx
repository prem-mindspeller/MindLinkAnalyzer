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
import { useTaskRunner } from '../../hooks/useTaskRunner';
import '../../styles/taskSelection.css';
import wsEegService from '../../service/wsEegService';

// Recording phase types
const RECORD_TYPES = new Set(['task', 'thinking', 'viewing', 'video', 'wait']);

const TaskRunner = ({ phases, taskName, eyesClosed, introText, onComplete, onBack }) => {
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
                <h2 className="task-runner-name">Read the instruction <strong>below before starting</strong></h2>
                <div className="task-runner-badges">
                    {eyesClosed !== undefined && (
                        <div className={`task-eyes-badge${eyesClosed ? ' eyes-closed' : ' eyes-open'}`}>
                            {eyesClosed ? ' Eyes Closed Task' : ' Eyes Open Task'}
                        </div>
                    )}
                    <div className="task-eyes-badge task-duration-badge">
                        ⏱ {totalDuration}s
                    </div>
                </div>
                <div className="task-runner-sound-notice">
                    🔊 Make sure your <strong>sound is on</strong> before starting.
                </div>
                <div className="task-runner-intro">
                    {Array.isArray(introText)
                        ? <ul className="task-runner-intro-bullets">{introText.map((line, i) => <li key={i}>{line}</li>)}</ul>
                        : introText}
                </div>
                <p className="task-runner-countdown-hint">
                    You will hear a <strong>5-second countdown beep</strong> before the task starts, and a <strong>double beep</strong> when it ends.
                </p>
                <div className="task-runner-actions">
                    <button className="task-runner-btn-back" onClick={onBack}>Cancel</button>
                    <button className="task-runner-btn-start" onClick={handleStart}>▶ Start task</button>
                </div>
            </div>
        );
    }

    if (isCountingDown) {
        return (
            <div className="task-runner-card task-runner-countdown-screen">
                <p className="task-runner-get-ready">Get ready…</p>
                <div className="task-runner-big-countdown">{countdown}</div>
                <p className="task-runner-countdown-caption">Listen for the beeps</p>
            </div>
        );
    }

    if (isRunning && currentPhase) {
        return (
            <div className={`task-runner-card task-runner-phase${isRecordingPhase ? ' phase-recording' : ' phase-cue'}`}>
                <div className="task-runner-phase-badge">
                    {isRecordingPhase
                        ? 'Recording'
                        : currentPhase.type === 'get_ready' ? ' Get Ready' : ' Read Instructions'}
                </div>
                <h3 className="task-runner-phase-instruction">
                    {eyesClosed && isRecordingPhase ? null : (currentPhase.instruction || taskName)}
                </h3>
                {currentPhase.image && (
                    <img
                        className="task-runner-face-image"
                        src={currentPhase.image}
                        alt="emotional face"
                    />
                )}
                {eyesClosed && isRecordingPhase && (
                    <p className="task-runner-eyes-hint">Keep your eyes <strong>closed</strong></p>
                )}
                {!eyesClosed && isRecordingPhase && (
                    <p className="task-runner-eyes-hint"> Keep your eyes <strong>open</strong></p>
                )}
                <div className="task-runner-progress-wrap">
                    <div className="task-runner-progress-bar" style={{ width: `${elapsedPct}%` }} />
                    <span className="task-runner-progress-text">{elapsedPct}%</span>
                </div>
                <button className="task-runner-btn-abort" onClick={handleAbort}>✕ Abort</button>
            </div>
        );
    }

    if (isDone) {
        return (
            <div className="task-runner-card task-runner-done-screen">
                <div className="task-runner-done-icon">✅</div>
                <h2 className="task-runner-done-title">{taskName} Complete!</h2>
                <p className="task-runner-done-msg">
                    EEG data has been recorded. You can now return to the task list.
                </p>
                <button className="task-runner-btn-start" onClick={onBack}>← Back to Tasks</button>
            </div>
        );
    }

    return null;
};

export default TaskRunner;
