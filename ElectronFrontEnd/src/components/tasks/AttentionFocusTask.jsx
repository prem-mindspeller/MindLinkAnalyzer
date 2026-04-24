import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const AttentionFocusTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'task', duration: 52, record: true, instruction: t('taskContent.attentionFocus.phaseInstruction') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.attentionFocus.name')}
            eyesClosed={true}
            introText={[
                t('taskContent.attentionFocus.intro1'),
                t('taskContent.attentionFocus.intro2'),
                t('taskContent.attentionFocus.intro3'),
                t('taskContent.attentionFocus.intro4'),
                t('taskContent.attentionFocus.intro5'),
                t('taskContent.attentionFocus.intro6'),
            ]}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default AttentionFocusTask;
