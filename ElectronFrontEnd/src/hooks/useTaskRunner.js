/**
 * useTaskRunner.js
 *
 * Shared hook for EEG task execution.
 * Manages: 5-second countdown → phase sequence → completion
 *
 * phases: [{ type, duration, record, instruction }]
 *   - type:        string label (cue, task, get_ready, viewing, thinking, ...)
 *   - duration:    seconds
 *   - record:      bool — collect bandPower during this phase
 *   - instruction: string shown to user
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import wsEegService from '../service/wsEegService';

// ── Audio helpers ────────────────────────────────────────────────────────────
export function playBeep(freq = 800, durationMs = 200) {
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

export function playCompletionBeeps() {
    playBeep(1000, 150);
    setTimeout(() => playBeep(1000, 150), 250);
}

// ── Hook ─────────────────────────────────────────────────────────────────────
const COUNTDOWN_FROM = 5;

export function useTaskRunner(phases) {
    const [runState, setRunState] = useState('idle');       // idle | countdown | running | done
    const [countdown, setCountdown] = useState(COUNTDOWN_FROM);
    const [phaseIndex, setPhaseIndex] = useState(0);
    const [elapsedPct, setElapsedPct] = useState(0);
    const [collectedSamples, setCollectedSamples] = useState([]);

    const timerRef = useRef(null);
    const unsubRef = useRef(null);
    const samplesRef = useRef([]);
    const elapsedRef = useRef(0);
    const phaseIdxRef = useRef(0);
    const onCompleteRef = useRef(null);
    const phasesRef = useRef(phases);

    // keep phasesRef current
    useEffect(() => { phasesRef.current = phases; }, [phases]);

    const stopRecording = useCallback(() => {
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
    }, []);

    const clearTimer = useCallback(() => {
        clearInterval(timerRef.current);
        timerRef.current = null;
    }, []);

    // ── Advance to next phase (called at end of each phase) ───────────────
    const advancePhase = useCallback(() => {
        const finishedPhase = phasesRef.current[phaseIdxRef.current];
        if (finishedPhase?.record) {
            wsEegService.logEvent('phase_done', {
                type:    finishedPhase.type,
                samples: samplesRef.current.length,
                index:   phaseIdxRef.current,
            });
        }
        stopRecording();
        const nextIdx = phaseIdxRef.current + 1;
        if (nextIdx >= phasesRef.current.length) {
            // All phases complete
            playCompletionBeeps();
            setRunState('done');
            setCollectedSamples([...samplesRef.current]);
            if (onCompleteRef.current) onCompleteRef.current([...samplesRef.current]);
            return;
        }
        startPhase(nextIdx);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [stopRecording]);

    // ── Start a specific phase ────────────────────────────────────────────
    const startPhase = useCallback((idx) => {
        stopRecording();
        clearTimer();

        phaseIdxRef.current = idx;
        setPhaseIndex(idx);
        elapsedRef.current = 0;
        setElapsedPct(0);

        const phase = phasesRef.current[idx];
        playBeep(800, 200);

        if (phase.record) {
            wsEegService.logEvent('phase_start', {
                type:     phase.type,
                duration: phase.duration,
                index:    idx,
            });
            unsubRef.current = wsEegService.on('raw', (sample) => {
                samplesRef.current.push(sample);
            });
        }

        timerRef.current = setInterval(() => {
            elapsedRef.current += 1;
            const pct = Math.min(100, Math.round((elapsedRef.current / phase.duration) * 100));
            setElapsedPct(pct);
            if (elapsedRef.current >= phase.duration) {
                clearTimer();
                advancePhase();
            }
        }, 1000);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [stopRecording, clearTimer, advancePhase]);

    // ── Public: start the task ────────────────────────────────────────────
    const start = useCallback((onComplete) => {
        samplesRef.current = [];
        onCompleteRef.current = onComplete;
        setRunState('countdown');
        let count = COUNTDOWN_FROM;
        setCountdown(count);
        playBeep(800, 200);

        timerRef.current = setInterval(() => {
            count -= 1;
            if (count > 0) {
                setCountdown(count);
                playBeep(800, 200);
            } else {
                clearTimer();
                setRunState('running');
                startPhase(0);
            }
        }, 1000);
    }, [clearTimer, startPhase]);

    // ── Public: abort ─────────────────────────────────────────────────────
    const abort = useCallback(() => {
        clearTimer();
        stopRecording();
        samplesRef.current = [];
        setRunState('idle');
        setCountdown(COUNTDOWN_FROM);
        setPhaseIndex(0);
        setElapsedPct(0);
    }, [clearTimer, stopRecording]);

    // Cleanup on unmount
    useEffect(() => () => { clearTimer(); stopRecording(); }, [clearTimer, stopRecording]);

    const currentPhase = (runState === 'running' && phases[phaseIndex]) ? phases[phaseIndex] : null;

    return {
        runState,
        countdown,
        phaseIndex,
        currentPhase,
        elapsedPct,
        collectedSamples,
        start,
        abort,
        isIdle: runState === 'idle',
        isCountingDown: runState === 'countdown',
        isRunning: runState === 'running',
        isDone: runState === 'done',
    };
}
