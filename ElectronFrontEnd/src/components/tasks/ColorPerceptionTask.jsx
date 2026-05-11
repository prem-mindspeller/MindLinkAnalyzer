/**
 * ColorPerceptionTask.jsx
 *
 * Session 3 — Color Perception & Analysis (Eyes Open)
 * Five solid colors shown sequentially, 12 s each (60 s total).
 * Uses useTaskRunner directly so each phase can render a full-color background.
 */

import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useTaskRunner } from '../../hooks/useTaskRunner';
import '../../styles/taskSelection.css';

const COLOR_PHASES = [
    { type: 'viewing', duration: 12, record: true, color: '#E53935', label: 'RED'    },
    { type: 'viewing', duration: 12, record: true, color: '#1E88E5', label: 'BLUE'   },
    { type: 'viewing', duration: 12, record: true, color: '#2E7D32', label: 'GREEN'  },
    { type: 'viewing', duration: 12, record: true, color: '#F9A825', label: 'YELLOW' },
    { type: 'viewing', duration: 12, record: true, color: '#6A1B9A', label: 'PURPLE' },
];

const ColorPerceptionTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const {
        countdown, currentPhase, elapsedPct,
        start, abort, isIdle, isCountingDown, isRunning, isDone,
    } = useTaskRunner(COLOR_PHASES);

    const handleStart  = useCallback(() => start(onComplete),       [start, onComplete]);
    const handleAbort  = useCallback(() => { abort(); onBack(); },   [abort, onBack]);

    if (isIdle) {
        return (
            <div className="task-runner-card">
                <h2 className="task-runner-name">
                    Read the instruction <strong>below before starting</strong>
                </h2>
                <div className="task-runner-badges">
                    <div className="task-eyes-badge eyes-open">{t('taskRunner.eyesOpen')}</div>
                    <div className="task-eyes-badge task-duration-badge">⏱ 60s</div>
                </div>
                <div className="task-runner-sound-notice">
                    🔊 {t('taskRunner.soundNotice')}
                </div>
                <div className="task-runner-intro">
                    <ul className="task-runner-intro-bullets">
                        <li>{t('taskContent.colorPerception.intro1')}</li>
                        <li>{t('taskContent.colorPerception.intro2')}</li>
                        <li>{t('taskContent.colorPerception.intro3')}</li>
                        <li>{t('taskContent.colorPerception.intro4')}</li>
                    </ul>
                </div>
                <p className="task-runner-countdown-hint">{t('taskRunner.countdownHint')}</p>
                <div className="task-runner-actions">
                    <button className="task-runner-btn-back"  onClick={onBack}>
                        {t('taskRunner.cancel')}
                    </button>
                    <button className="task-runner-btn-start" onClick={handleStart}>
                        {t('taskRunner.start')}
                    </button>
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
        const bg        = currentPhase.color || '#ffffff';
        const isDark    = currentPhase.label !== 'YELLOW';
        const textColor = isDark ? '#ffffff' : '#1a1a1a';

        return (
            <div
                className="task-runner-card task-runner-phase phase-recording"
                style={{ background: bg, borderColor: bg }}
            >
                <div className="task-runner-phase-badge">{t('taskRunner.recording')}</div>

                <div style={{
                    fontSize: '4.5rem',
                    fontWeight: 900,
                    letterSpacing: '0.08em',
                    color: textColor,
                    textShadow: isDark ? '0 2px 12px rgba(0,0,0,0.4)' : '0 1px 4px rgba(0,0,0,0.15)',
                    marginBottom: '0.75rem',
                }}>
                    {currentPhase.label}
                </div>

                <p style={{ color: textColor, opacity: 0.85, marginBottom: '1.5rem', fontSize: '0.95rem' }}>
                    {t('taskContent.colorPerception.phaseInstruction')}
                </p>

                <div className="task-runner-progress-wrap">
                    <div
                        className="task-runner-progress-bar"
                        style={{ width: `${elapsedPct}%`, background: isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.2)' }}
                    />
                    <span className="task-runner-progress-text" style={{ color: textColor }}>
                        {elapsedPct}%
                    </span>
                </div>

                <button className="task-runner-btn-abort" onClick={handleAbort}>
                    {t('taskRunner.abort')}
                </button>
            </div>
        );
    }

    if (isDone) {
        return (
            <div className="task-runner-card task-runner-done-screen">
                <div className="task-runner-done-icon">✅</div>
                <h2 className="task-runner-done-title">
                    {t('taskRunner.complete', { taskName: t('taskContent.colorPerception.name') })}
                </h2>
                <p className="task-runner-done-msg">{t('taskRunner.doneMsg')}</p>
                <button className="task-runner-btn-start" onClick={onBack}>
                    {t('taskRunner.backToTasks')}
                </button>
            </div>
        );
    }

    return null;
};

export default ColorPerceptionTask;
