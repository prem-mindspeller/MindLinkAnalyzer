import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    { type: 'get_ready', duration: 8, record: false, instruction: 'Get ready…' },
    { type: 'cue', duration: 8, record: false, instruction: 'NUMBERS: On the next screen, look for the numbers. Keep your gaze steady.' },
    { type: 'viewing', duration: 20, record: true, instruction: 'NUMBERS: Look at the numbers. Keep your gaze steady and minimise movement.' },
    { type: 'cue', duration: 8, record: false, instruction: 'FORMS: On the next screen, look for the shapes. Keep your gaze steady.' },
    { type: 'viewing', duration: 20, record: true, instruction: 'FORMS: Look at the shapes. Keep your gaze steady and minimise movement.' },
    { type: 'rest', duration: 2, record: false, instruction: 'Rest.' },
];

const NumFormTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Numerical Preference"
        eyesClosed={false}
        introText="You will look at a stimulus image in two phases: first focus on NUMBERS, then on FORMS (shapes). Keep your gaze steady and minimise movement. Eyes open throughout. Total duration ~60 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default NumFormTask;
