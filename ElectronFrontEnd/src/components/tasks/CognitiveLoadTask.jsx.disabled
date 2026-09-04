import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const CognitiveLoadTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'task', duration: 52, record: true, instruction: t('taskContent.cognitiveLoad.phaseInstruction') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.cognitiveLoad.name')}
            eyesClosed={true}
            introText={t('taskContent.cognitiveLoad.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default CognitiveLoadTask;
