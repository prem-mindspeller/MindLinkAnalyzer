import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const WorkingMemoryTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'cue', duration: 8, record: false, instruction: t('taskContent.workingMemory.cueInstruction') },
        { type: 'task', duration: 52, record: true, instruction: t('taskContent.workingMemory.phaseInstruction') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.workingMemory.name')}
            eyesClosed={true}
            introText={t('taskContent.workingMemory.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default WorkingMemoryTask;
