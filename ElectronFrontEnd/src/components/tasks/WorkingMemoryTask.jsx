import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    {
        type: 'cue', duration: 8, record: false,
        instruction: 'INSTRUCTION: Prepare to remember and manipulate: 3-8-2-9-5-1. Add 2 to each number. Close your eyes on the beep.',
    },
    {
        type: 'task', duration: 52, record: true,
        instruction: 'REMEMBER: 3-8-2-9-5-1. Add 2 to each: 5-10-4-11-7-3. Keep cycling through the sequence. Eyes closed.',
    },
];

const WorkingMemoryTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Working Memory"
        eyesClosed={true}
        introText="Memorise the sequence 3-8-2-9-5-1. Then mentally add 2 to each digit repeatedly. Keep cycling through the modified sequence for 52 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default WorkingMemoryTask;
