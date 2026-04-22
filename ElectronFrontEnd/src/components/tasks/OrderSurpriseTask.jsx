import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    { type: 'get_ready', duration: 8, record: false, instruction: 'Get ready…' },
    { type: 'cue', duration: 8, record: false, instruction: 'ORDER: Count symmetrical / normal shapes in the upcoming image. Keep your gaze steady.' },
    { type: 'viewing', duration: 20, record: true, instruction: 'ORDER: Count symmetrical / normal shapes. Keep your gaze steady and minimise movement.' },
    { type: 'cue', duration: 8, record: false, instruction: 'SURPRISE: Count non-symmetrical / abnormal shapes in the upcoming image. Keep your gaze steady.' },
    { type: 'viewing', duration: 20, record: true, instruction: 'SURPRISE: Count non-symmetrical / abnormal shapes. Keep your gaze steady and minimise movement.' },
    { type: 'rest', duration: 2, record: false, instruction: 'Rest.' },
];

const OrderSurpriseTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Order & Surprise"
        eyesClosed={false}
        introText="You will look at a stimulus image in two phases: first count ORDER (symmetrical/normal shapes), then count SURPRISE (non-symmetrical/abnormal shapes). Eyes open throughout. Total duration ~60 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default OrderSurpriseTask;
