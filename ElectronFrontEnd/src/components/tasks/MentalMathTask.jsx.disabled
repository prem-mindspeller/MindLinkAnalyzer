import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const MentalMathTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'task', duration: 52, record: true, instruction: t('taskContent.mentalMath.phaseInstruction') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.mentalMath.name')}
            eyesClosed={true}
            introText={t('taskContent.mentalMath.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default MentalMathTask;
