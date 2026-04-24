import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const MotorImageryTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'cue', duration: 8, record: false, instruction: t('taskContent.motorImagery.cueInstruction') },
        { type: 'task', duration: 52, record: true, instruction: t('taskContent.motorImagery.phaseInstruction') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.motorImagery.name')}
            eyesClosed={true}
            introText={t('taskContent.motorImagery.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default MotorImageryTask;
