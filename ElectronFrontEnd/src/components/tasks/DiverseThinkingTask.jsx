import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    { type: 'get_ready', duration: 8, record: false, instruction: 'Get ready for creative thinking…' },
    { type: 'cue', duration: 10, record: false, instruction: 'PROMPT 1 — PAPERCLIP: Think of as many creative and unusual uses for a PAPERCLIP as you can.' },
    { type: 'thinking', duration: 30, record: true, instruction: 'THINK: Creative uses for a PAPERCLIP. Be imaginative — go beyond the obvious!' },
    { type: 'get_ready', duration: 8, record: false, instruction: 'Get ready for the next prompt…' },
    { type: 'cue', duration: 10, record: false, instruction: 'PROMPT 2 — ARTIFICIAL INTELLIGENCE: Think of creative and innovative uses for AI.' },
    { type: 'thinking', duration: 30, record: true, instruction: 'THINK: Creative uses for ARTIFICIAL INTELLIGENCE. Consider current and future possibilities!' },
];

const DiverseThinkingTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Creative Fluency"
        eyesClosed={false}
        introText="You will receive 2 creative-thinking prompts. For each: read the prompt carefully, then think of as many creative and unusual uses as possible. Eyes open throughout. Total duration ~96 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default DiverseThinkingTask;
