import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import LoggedInHeader from '../components/LoggedInHeader';
import Footer from '../components/footer';
import wsEegService, { CONNECTION_STATUS } from '../service/wsEegService';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faCircleCheck, faMoon, faEye, faBullseye, faVideo,
    faHourglass, faTriangleExclamation, faCircle, faArrowLeft, faArrowRight,
    faCircleXmark, faPlay,
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

// ── Constants ─────────────────────────────────────────────────────────────────
const PHASE_DURATION_S = 30;
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

// ── Component ─────────────────────────────────────────────────────────────────
const BaselineCalibration1 = () => {
    const navigate = useNavigate();
    const [phase, setPhase] = useState(PHASE.IDLE);
    const [countdown, setCountdown] = useState(COUNTDOWN_FROM);
    const [recordingProgress, setRecordingProgress] = useState(0);
    const [signalStatus, setSignalStatus] = useState({ icon: faCircle, text: 'Signal: Waiting...', cls: 'waiting' });
    const [statusMsg, setStatusMsg] = useState('Ready to start');
    const [phaseMsg, setPhaseMsg] = useState('');

    const bandSamplesRef = useRef([]);
    const baselineRef = useRef({ eyesClosed: null, eyesOpen: null });
    const countdownTimerRef = useRef(null);
    const recordingTimerRef = useRef(null);
    const unsubBpRef = useRef(null);
    const elapsedRef = useRef(0);

    // ── Signal quality polling ────────────────────────────────────────────────
    useEffect(() => {
        const id = setInterval(() => {
            const ps = wsEegService.getPoorSignal();
            const st = wsEegService.getStatus();
            if (st !== CONNECTION_STATUS.CONNECTED) {
                setSignalStatus({ icon: faCircle, text: 'Signal: Waiting...', cls: 'waiting' });
            } else if (ps >= 200) {
                setSignalStatus({ icon: faTriangleExclamation, text: 'Not Worn', cls: 'noisy' });
            } else if (ps < 25) {
                setSignalStatus({ icon: faCircleCheck, text: 'Signal: Good', cls: 'good' });
            } else {
                setSignalStatus({ icon: faTriangleExclamation, text: 'Signal: Noisy', cls: 'noisy' });
            }
        }, 500);
        return () => clearInterval(id);
    }, []);


    useEffect(() => () => {
        clearInterval(countdownTimerRef.current);
        clearInterval(recordingTimerRef.current);
        if (unsubBpRef.current) unsubBpRef.current();
    }, []);

    const startRecording = useCallback((isEC) => {
        bandSamplesRef.current = [];
        elapsedRef.current = 0;

        unsubBpRef.current = wsEegService.on('raw', (sample) => {
            bandSamplesRef.current.push(sample);
        });

        setPhase(isEC ? PHASE.RECORDING_EC : PHASE.RECORDING_EO);
        setStatusMsg(isEC ? 'Recording: Eyes Closed' : 'Recording: Eyes Open');
        setPhaseMsg(isEC
            ? 'Close your eyes and relax... (30 seconds)'
            : 'Keep your eyes open and stay relaxed... (30 seconds)');
        setRecordingProgress(0);

        recordingTimerRef.current = setInterval(() => {
            elapsedRef.current += 1;
            const pct = Math.round((elapsedRef.current / PHASE_DURATION_S) * 100);
            setRecordingProgress(pct);

            if (elapsedRef.current >= PHASE_DURATION_S) {
                clearInterval(recordingTimerRef.current);
                if (unsubBpRef.current) { unsubBpRef.current(); unsubBpRef.current = null; }

                playCompletionBeeps();

                const samples = bandSamplesRef.current;
                // avg is unused downstream but kept for legacy baselineCalibration key
                const avg = samples.length > 0
                    ? { raw_sample_count: samples.length }
                    : null;

                if (isEC) {
                    baselineRef.current.eyesClosed = avg;
                    sessionStorage.setItem('calibrationData_eyes_closed', JSON.stringify(samples));
                    setPhase(PHASE.DONE_EC);
                    setStatusMsg('Eyes Closed Complete!');
                    setPhaseMsg("Great! Now let's record with eyes open.");
                } else {
                    baselineRef.current.eyesOpen = avg;
                    sessionStorage.setItem('calibrationData_eyes_open', JSON.stringify(samples));
                    sessionStorage.setItem('baselineCalibration', JSON.stringify(baselineRef.current));
                    setPhase(PHASE.DONE_BOTH);
                    setStatusMsg('Calibration Complete!');
                    setPhaseMsg('Both baseline phases recorded successfully!');
                }
            }
        }, 1000);
    }, []);

    // ── 5-second countdown then start recording ───────────────────────────────
    const startCountdown = useCallback((isEC) => {
        setPhase(isEC ? PHASE.COUNTDOWN_EC : PHASE.COUNTDOWN_EO);
        let count = COUNTDOWN_FROM;
        setCountdown(count);
        setStatusMsg(`Countdown: ${count}`);
        setPhaseMsg('Get ready! Listen for the countdown...');
        playBeep(800, 200);

        countdownTimerRef.current = setInterval(() => {
            count -= 1;
            if (count > 0) {
                setCountdown(count);
                setStatusMsg(`Countdown: ${count}`);
                playBeep(800, 200);
            } else {
                clearInterval(countdownTimerRef.current);
                startRecording(isEC);
            }
        }, 1000);
    }, [startRecording]);

    const isBusy = [
        PHASE.COUNTDOWN_EC, PHASE.RECORDING_EC,
        PHASE.COUNTDOWN_EO, PHASE.RECORDING_EO,
    ].includes(phase);
    const isCountingDown = phase === PHASE.COUNTDOWN_EC || phase === PHASE.COUNTDOWN_EO;
    const isRecording = phase === PHASE.RECORDING_EC || phase === PHASE.RECORDING_EO;
    const ecDone = ![PHASE.IDLE, PHASE.PREP_EC, PHASE.COUNTDOWN_EC, PHASE.RECORDING_EC].includes(phase);
    const bothDone = phase === PHASE.DONE_BOTH;
    const showPrepModal = phase === PHASE.PREP_EC || phase === PHASE.PREP_EO;
    const prepIsEC = phase === PHASE.PREP_EC;

    const handleNext = () => {
        sessionStorage.setItem('selectedPathway', 'personal');
        navigate('/taskSelection');
    }

    return (
        <div className="app-container">
            <LoggedInHeader />

            <main className="app-main">
                <div className="calibration-page">

                    {/* ── Page header ── */}
                    <div className="calibration-header">
                        <h1 className="calibration-title">Baseline Calibration</h1>
                        <p className="calibration-subtitle">Step 5 of 7: Establish your baseline brain activity</p>
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
                        {/* Eyes Closed */}
                        <div className={`cal-phase-card${ecDone ? ' phase-done' : ''}`}>
                            <span className="cal-phase-icon"><FontAwesomeIcon icon={faMoon} /></span>
                            <div className="cal-phase-info">
                                <h3>Eyes Closed Baseline</h3>
                                <p>Relax with eyes closed for 30 seconds</p>
                            </div>
                            <button
                                className="cal-phase-btn"
                                disabled={isBusy || ecDone}
                                onClick={() => setPhase(PHASE.PREP_EC)}
                            >
                                {ecDone
                                    ? <><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 6 }} />Complete</>
                                    : <><FontAwesomeIcon icon={faBullseye} style={{ marginRight: 6 }} />Start</>}
                            </button>
                        </div>

                        {/* Eyes Open */}
                        <div className={`cal-phase-card${bothDone ? ' phase-done' : ''}${!ecDone ? ' phase-locked' : ''}`}>
                            <span className="cal-phase-icon"><FontAwesomeIcon icon={faEye} /></span>
                            <div className="cal-phase-info">
                                <h3>Eyes Open Baseline</h3>
                                <p>Stay relaxed with eyes open for 30 seconds</p>
                            </div>
                            <button
                                className="cal-phase-btn"
                                disabled={isBusy || !ecDone || bothDone}
                                onClick={() => setPhase(PHASE.PREP_EO)}
                            >
                                {bothDone
                                    ? <><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 6 }} />Complete</>
                                    : <><FontAwesomeIcon icon={faBullseye} style={{ marginRight: 6 }} />Start</>}
                            </button>
                        </div>
                    </div>


                    <div className="navigation-buttons-baseline">
                        <button className="btn-back-eeg" disabled={isBusy} onClick={() => navigate(-1)}>
                            <FontAwesomeIcon icon={faArrowLeft} style={{ marginRight: 6 }} />Back
                        </button>
                        <button
                            className="btn-next-eeg"
                            disabled={!bothDone}
                            onClick={handleNext}
                        >
                            Next <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 6 }} />
                        </button>
                    </div>
                </div>
            </main>

            {/* ── Prep modal ── */}
            {showPrepModal && (
                <div className="cal-modal-overlay">
                    <div className="cal-modal-card">
                        <h2 className="cal-modal-title">
                            <FontAwesomeIcon icon={prepIsEC ? faMoon : faEye} style={{ marginRight: 8 }} />
                            {prepIsEC ? 'Eyes Closed Baseline' : 'Eyes Open Baseline'}
                        </h2>

                        <div className="cal-modal-instructions">
                            {prepIsEC ? (
                                <span>
                                    <b>Get ready to close your eyes and relax.</b><br /><br />
                                    The sensors will record your baseline brainwave pattern for <b>30 seconds</b>.<br /><br />
                                    <b>What will happen:</b><br />
                                    1. Click 'Start Recording' below<br />
                                    2. You'll hear a countdown: <em>5, 4, 3, 2, 1 beeps</em><br />
                                    3. Please sit comfortably and relax<br />
                                    4. Try to let your mind wander naturally without focusing on anything specific<br />
                                    5. A sound will notify you when recording is complete<br /><br />
                                    <b style={{ color: '#dc2626' }}><FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />Important: Check your speakers/headphones are ON!</b>
                                </span>
                            ) : (
                                <span>
                                    <b>Get ready to keep your eyes open and stay relaxed.</b><br /><br />
                                    The sensors will record your eyes-open baseline for <b>30 seconds</b>.<br /><br />
                                    <b>What will happen:</b><br />
                                    1. Click 'Start Recording' below<br />
                                    2. You'll hear a countdown: <em>5, 4, 3, 2, 1 beeps</em><br />
                                    3. Keep your eyes open and relax for 30 seconds<br />
                                    4. Stay calm and focus on the single white cross in the middle of the screen<br />
                                    5. Do not worry about blinking.<br />
                                    6. A sound will notify you when recording is complete<br /><br />
                                    <b style={{ color: '#dc2626' }}><FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />Important: Keep eyes open but stay relaxed!</b>
                                </span>
                            )}
                        </div>

                        <div className={`cal-signal-badge cal-signal-${signalStatus.cls}`} style={{ margin: '0 auto 18px' }}>
                            {signalStatus.icon && <FontAwesomeIcon icon={signalStatus.icon} style={{ marginRight: 6 }} />}
                            {signalStatus.text}
                        </div>

                        <div className="cal-modal-buttons">
                            <button className="cal-btn-cancel" onClick={() => setPhase(PHASE.IDLE)}>
                                <FontAwesomeIcon icon={faCircleXmark} style={{ marginRight: 6 }} />Cancel
                            </button>
                            <button className="cal-btn-start" onClick={() => startCountdown(prepIsEC)}>
                                <FontAwesomeIcon icon={faPlay} style={{ marginRight: 8 }} />Start Recording
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