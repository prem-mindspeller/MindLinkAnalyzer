import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const ReappraisalTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'get_ready', duration: 8, record: false, instruction: t('taskContent.reappraisal.getReady1') },
        { type: 'cue', duration: 10, record: false, instruction: t('taskContent.reappraisal.cue1') },
        { type: 'thinking', duration: 30, record: true, instruction: t('taskContent.reappraisal.phase1') },
        { type: 'get_ready', duration: 8, record: false, instruction: t('taskContent.reappraisal.getReady2') },
        { type: 'cue', duration: 10, record: false, instruction: t('taskContent.reappraisal.cue2') },
        { type: 'thinking', duration: 30, record: true, instruction: t('taskContent.reappraisal.phase2') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.reappraisal.name')}
            eyesClosed={false}
            introText={t('taskContent.reappraisal.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default ReappraisalTask;
