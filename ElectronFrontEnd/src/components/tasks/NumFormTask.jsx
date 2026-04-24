import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const NumFormTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'get_ready', duration: 8, record: false, instruction: t('taskContent.numForm.getReady') },
        { type: 'cue', duration: 8, record: false, instruction: t('taskContent.numForm.cue1') },
        { type: 'viewing', duration: 20, record: true, instruction: t('taskContent.numForm.phase1') },
        { type: 'cue', duration: 8, record: false, instruction: t('taskContent.numForm.cue2') },
        { type: 'viewing', duration: 20, record: true, instruction: t('taskContent.numForm.phase2') },
        { type: 'rest', duration: 2, record: false, instruction: t('taskContent.numForm.rest') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.numForm.name')}
            eyesClosed={false}
            introText={t('taskContent.numForm.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default NumFormTask;
