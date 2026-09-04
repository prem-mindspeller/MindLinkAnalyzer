import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const OrderSurpriseTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const phases = [
        { type: 'get_ready', duration: 8, record: false, instruction: t('taskContent.orderSurprise.getReady') },
        { type: 'cue', duration: 8, record: false, instruction: t('taskContent.orderSurprise.cue1') },
        { type: 'viewing', duration: 20, record: true, instruction: t('taskContent.orderSurprise.phase1') },
        { type: 'cue', duration: 8, record: false, instruction: t('taskContent.orderSurprise.cue2') },
        { type: 'viewing', duration: 20, record: true, instruction: t('taskContent.orderSurprise.phase2') },
        { type: 'rest', duration: 2, record: false, instruction: t('taskContent.orderSurprise.rest') },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.orderSurprise.name')}
            eyesClosed={false}
            introText={t('taskContent.orderSurprise.intro')}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default OrderSurpriseTask;
