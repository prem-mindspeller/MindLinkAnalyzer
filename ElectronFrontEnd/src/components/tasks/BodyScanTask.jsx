import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const BodyScanTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();

    const phases = [
        { type: 'task', duration: 60, record: true, instruction: t('taskContent.bodyScan.phaseInstruction') },
    ];

    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.bodyScan.name')}
            eyesClosed={true}
            introText={[
                t('taskContent.bodyScan.intro1'),
                t('taskContent.bodyScan.intro2'),
                t('taskContent.bodyScan.intro3'),
                t('taskContent.bodyScan.intro4'),
            ]}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default BodyScanTask;
