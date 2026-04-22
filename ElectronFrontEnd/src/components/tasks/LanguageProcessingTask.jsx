import React from 'react';
import TaskRunner from './TaskRunner';

const PHASES = [
    // {
    //     type: 'cue', duration: 8, record: false,
    //     instruction: 'INSTRUCTION: Silently list as many words beginning with "S" as possible. Close your eyes on the beep.',
    // },
    {
        type: 'task', duration: 52, record: true,
        instruction: 'INSTRUCTION: Silently list distinct "S" words. Avoid repeats, keep a steady pace. Eyes closed.',
    },
];

const LanguageProcessingTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Language Processing"
        eyesClosed={true}
        introText="Silently generate as many words as possible that start with the letter 'S'. Avoid repeats and keep a steady mental pace for 52 seconds."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default LanguageProcessingTask;
