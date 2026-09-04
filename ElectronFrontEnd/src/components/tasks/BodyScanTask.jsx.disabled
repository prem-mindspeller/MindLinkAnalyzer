import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const BodyScanTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();

    const phases = [
        {
            type: 'task',
            duration: 60,
            record: true,
            instruction: t('taskContent.bodyScan.phaseInstruction', {
                defaultValue: 'BODY SCAN: Slowly move your attention from head to toes. Head → Forehead → Eyes → Neck → Shoulders → Chest → Abdomen → Legs → Feet. Eyes closed.',
            }),
        },
    ];

    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.bodyScan.name', { defaultValue: 'Body Scan' })}
            eyesClosed={true}
            introText={[
                t('taskContent.bodyScan.intro1', {
                    defaultValue: 'Close your eyes and slowly move your attention through your body from head to toes.',
                }),
                t('taskContent.bodyScan.intro2', {
                    defaultValue: 'Internal sequence: Head → Forehead → Eyes → Neck → Shoulders → Chest → Abdomen → Legs → Feet.',
                }),
                t('taskContent.bodyScan.intro3', {
                    defaultValue: 'Perform the scan silently with no physical movement, muscle contraction, or verbalization.',
                }),
                t('taskContent.bodyScan.intro4', {
                    defaultValue: 'Sustain your attention gently on each region for the full 60 seconds.',
                }),
            ]}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default BodyScanTask;
