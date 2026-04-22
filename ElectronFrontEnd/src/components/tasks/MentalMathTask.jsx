import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    // {
    //     type: 'cue', duration: 8, record: false,
    //     instruction: 'INSTRUCTION: Prepare to count backwards from 200 by 7s. Close your eyes on the beep.',
    // },
    {
        type: 'task', duration: 52, record: true,
        instruction: 'COUNT: 200, 193, 186, 179… Keep counting backwards by 7s. Eyes closed.',
    },
];

const MentalMathTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Mental Math"
        eyesClosed={true}
        introText="Start at 200. In your mind, subtract 7 each time (200, 193, 186, 179, 172, …). Continue mentally as quickly and accurately as you can for 52 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default MentalMathTask;
