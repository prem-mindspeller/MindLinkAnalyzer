import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    // {
    //     type: 'cue', duration: 8, record: false,
    //     instruction: 'INSTRUCTION: Prepare to count backwards from 50 by 3s while visualising the numbers in blue. Close your eyes on the beep.',
    // },
    {
        type: 'task', duration: 52, record: true,
        instruction: 'COUNT & VISUALISE: 50, 47, 44, 41… Count backwards by 3s while seeing each number in blue. Eyes closed.',
    },
];

const CognitiveLoadTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Cognitive Load"
        eyesClosed={true}
        introText="Perform two mental tasks simultaneously: count backwards from 50 by 3s AND visualise each number in bright blue. Continue for 52 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default CognitiveLoadTask;
