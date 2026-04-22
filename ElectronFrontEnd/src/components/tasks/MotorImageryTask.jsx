import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    {
        type: 'cue', duration: 8, record: false,
        instruction: 'INSTRUCTION: Prepare to imagine throwing a ball — right hand then left, alternating. Close your eyes on the beep.',
    },
    {
        type: 'task', duration: 52, record: true,
        instruction: 'IMAGINE: Throw a ball with your right hand, then left hand, alternating. Feel the motion vividly. Eyes closed.',
    },
];

const MotorImageryTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Motor Imagery"
        eyesClosed={true}
        introText="Mentally imagine throwing a ball with your right hand, then your left hand, alternating continuously. Feel each movement as vividly as possible for 52 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default MotorImageryTask;
