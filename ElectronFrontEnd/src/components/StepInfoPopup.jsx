import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';

const STEP_INFO = {
    '/region': {
        step: 1,
        title: 'Step 1 — Region Selection',
        why: 'Selecting your region ensures your brainwave data is processed and stored in compliance with local data sovereignty laws. This keeps your personal neural data private and legally protected.',
    },
    '/login': {
        step: 2,
        title: 'Step 2&3 — Sign In and Partner ID',
        why: 'Signing in links your EEG recordings to your Mindspeller account, enabling secure storage and comparison of your cognitive profiles over time. Without authentication, your session data cannot be saved or analysed. Entering your Partner ID connects your session to a specific partner.',
    },
    '/liveReading': {
        step: 4,
        title: 'Step 4 — Verify Live Signal',
        why: 'A live Bluetooth connection to your EEG headset allows the app to stream raw brainwave signals in real time. A stable, quality connection is required before any recordings can begin.',
    },
    '/baselineCalibration1': {
        step: 5,
        title: 'Step 5 — Baseline Calibration',
        why: 'Your personal baseline captures your brain\'s resting-state activity. Every cognitive metric measured during tasks is compared against this baseline, making your analysis uniquely accurate rather than relying on generic averages.',
    },
    '/taskSelection': {
        step: 6,
        title: 'Step 6 — Task Selection & Recording',
        why: 'Different cognitive tasks activate distinct brain regions. Choosing the right tasks maps specific mental abilities — focus, memory, creativity, and more — giving you a rich and personalised cognitive profile.',
    },
    '/upload': {
        step: 7,
        title: 'Step 7 — Upload & Analyse',
        why: 'Uploading your recordings sends them to the Mindspeller AI analysis pipeline, which computes your cognitive scores and generates a detailed brainwave report you can download and share.',
    },
};

const StepInfoPopup = () => {
    const { pathname } = useLocation();
    const [open, setOpen] = useState(false);

    const info = STEP_INFO[pathname];
    if (!info) return null;

    return (
        <>
            <button
                className="step-info-btn"
                onClick={() => setOpen(true)}
                aria-label="Why is this step important?"
                title="Why is this step important?"
            >
                <span className="step-info-btn-icon">?</span>
                <span className="step-info-btn-label">Why this step?</span>
            </button>

            {open && (
                <div className="step-info-overlay" onClick={() => setOpen(false)}>
                    <div className="step-info-modal" onClick={e => e.stopPropagation()}>
                        <button className="step-info-close" onClick={() => setOpen(false)} aria-label="Close">&#x2715;</button>
                        <div className="step-info-badge">Step {info.step}</div>
                        <h2 className="step-info-title">{info.title}</h2>
                        <p className="step-info-body">{info.why}</p>
                    </div>
                </div>
            )}
        </>
    );
};

export default StepInfoPopup;
