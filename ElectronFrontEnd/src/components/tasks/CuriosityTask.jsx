import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const CuriosityTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'get_ready', duration: 8, record: false, instruction: t('taskContent.curiosity.getReady') },
        { type: 'cue', duration: 2, record: false, instruction: t('taskContent.curiosity.cue') },
        { type: 'wait', duration: 2, record: true, instruction: t('taskContent.curiosity.wait') },
        { type: 'video', duration: 33, record: true, instruction: t('taskContent.curiosity.phase') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.curiosity.name')}
            eyesClosed={false}
            introText={t('taskContent.curiosity.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default CuriosityTask;
