import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const DiverseThinkingTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'get_ready', duration: 8, record: false, instruction: t('taskContent.diverseThinking.getReady1') },
        { type: 'cue', duration: 10, record: false, instruction: t('taskContent.diverseThinking.cue1') },
        { type: 'thinking', duration: 30, record: true, instruction: t('taskContent.diverseThinking.phase1') },
        { type: 'get_ready', duration: 8, record: false, instruction: t('taskContent.diverseThinking.getReady2') },
        { type: 'cue', duration: 10, record: false, instruction: t('taskContent.diverseThinking.cue2') },
        { type: 'thinking', duration: 30, record: true, instruction: t('taskContent.diverseThinking.phase2') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.diverseThinking.name')}
            eyesClosed={false}
            introText={t('taskContent.diverseThinking.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default DiverseThinkingTask;
