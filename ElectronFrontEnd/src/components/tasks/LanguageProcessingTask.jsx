import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const LanguageProcessingTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'task', duration: 52, record: true, instruction: t('taskContent.languageProcessing.phaseInstruction') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.languageProcessing.name')}
            eyesClosed={true}
            introText={t('taskContent.languageProcessing.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default LanguageProcessingTask;
