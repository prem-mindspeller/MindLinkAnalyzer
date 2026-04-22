import React from 'react';
import TaskRunner from './TaskRunner';

// 8s get_ready + 2s cue + 2s wait + 33s video = 45s
const PHASES = [
    { type: 'get_ready', duration: 8, record: false, instruction: 'Get ready for the reveal video…' },
    { type: 'cue', duration: 2, record: false, instruction: 'Video starting soon — watch with full attention!' },
    { type: 'wait', duration: 2, record: true, instruction: 'Video starting…' },
    { type: 'video', duration: 33, record: true, instruction: 'WATCH: View the video reveal with full attention. Let your curiosity guide you.' },
];

const CuriosityTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Curiosity Reveal"
        eyesClosed={false}
        introText="Watch a short reveal video with full attention and genuine curiosity. Let yourself be drawn in by what is revealed. Eyes open throughout. Total duration ~45 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default CuriosityTask;
