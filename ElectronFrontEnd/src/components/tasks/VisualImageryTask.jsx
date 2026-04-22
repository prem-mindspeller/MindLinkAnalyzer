import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    // {
    //     type: 'cue', duration: 8, record: false,
    //     instruction: 'INSTRUCTION: Prepare to visualize walking through your home in rich sensory detail. Close your eyes on the beep.',
    // },
    {
        type: 'task', duration: 52, record: true,
        instruction: 'IMAGERY: Visualize walking through your home in rich sensory detail continuously.',
    },
];

const VisualImageryTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Visual Imagery"
        eyesClosed={true}
        introText={[
            'Close your eyes and vividly imagine walking through your home.',
            'Engage all your senses — sight, sound, smell, and touch.',
            'Try to make the imagery as detailed and continuous as possible.',
            'Continue for 52 seconds without opening your eyes.',
        ]}
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default VisualImageryTask;
