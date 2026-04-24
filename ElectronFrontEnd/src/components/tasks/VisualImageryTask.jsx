import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const VisualImageryTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'task', duration: 52, record: true, instruction: t('taskContent.visualImagery.phaseInstruction') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.visualImagery.name')}
            eyesClosed={true}
            introText={[
                t('taskContent.visualImagery.intro1'),
                t('taskContent.visualImagery.intro2'),
                t('taskContent.visualImagery.intro3'),
                t('taskContent.visualImagery.intro4'),
            ]}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default VisualImageryTask;
