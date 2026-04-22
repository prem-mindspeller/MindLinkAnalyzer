import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    // {
    //     type: 'cue', duration: 8, record: false,
    //     instruction: 'INSTRUCTION: Attend only to your breathing. Count breaths 1–10 and restart. Close your eyes on the beep.',
    // },
    {
        type: 'task', duration: 52, record: true,
        instruction: 'FOCUS: Attend only to breathing. Count breaths 1–10 and restart; gently return if distracted. Eyes closed.',
    },
];

const AttentionFocusTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Focused Attention"
        eyesClosed={true}
        introText={[
            'Focus all attention on your breathing.',
            'Dont count your breaths — just feel the natural rhythm of your inhales and exhales.',
            'Silently count from 1 to 10 in your mind — it doesn\'t matter how fast or slow.',
            'When you reach 10, start again at 1.',
            'If your mind wanders, gently bring it back and restart from 1.',
            'Continue for 52 seconds with your eyes closed.',
        ]}
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default AttentionFocusTask;
