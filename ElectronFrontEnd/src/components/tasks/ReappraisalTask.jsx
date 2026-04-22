import React from 'react';
import TaskRunner from './TaskRunner';


const PHASES = [
    { type: 'get_ready', duration: 8, record: false, instruction: 'Get ready for the thinking task…' },
    { type: 'cue', duration: 10, record: false, instruction: 'SCENARIO 1 — THINK POSITIVE: "Receiving unexpected feedback from a close friend." See the positive side.' },
    { type: 'thinking', duration: 30, record: true, instruction: 'THINK POSITIVE: What good could come from this feedback? What are the silver linings?' },
    { type: 'get_ready', duration: 8, record: false, instruction: 'Get ready for the next scenario…' },
    { type: 'cue', duration: 10, record: false, instruction: 'SCENARIO 2 — FOCUS ON NEGATIVES: "You are about to miss a flight." Focus on what went wrong.' },
    { type: 'thinking', duration: 30, record: true, instruction: 'FOCUS ON NEGATIVES: Think about what went wrong and the negative consequences of missing the flight.' },
];

const ReappraisalTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Perspective Shift"
        eyesClosed={false}
        introText="You will receive 2 scenarios. For each: deliberately shift your perspective as instructed — first see positives, then focus on negatives. Eyes open throughout. Total duration ~96 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default ReappraisalTask;
