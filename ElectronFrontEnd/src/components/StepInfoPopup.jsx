import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const STEP_KEYS = {
    '/region': 'region',
    '/login': 'login',
    '/liveReading': 'liveReading',
    '/baselineCalibration1': 'baseline',
    '/taskSelection': 'taskSelection',
    '/upload': 'upload',
};

const STEP_NUMBERS = {
    '/region': 1,
    '/login': 2,
    '/liveReading': 4,
    '/baselineCalibration1': 5,
    '/taskSelection': 6,
    '/upload': 7,
};

const StepInfoPopup = () => {
    const { pathname } = useLocation();
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);

    const key = STEP_KEYS[pathname];
    if (!key) return null;

    const stepNum = STEP_NUMBERS[pathname];

    return (
        <>
            <button
                className="step-info-btn"
                onClick={() => setOpen(true)}
                aria-label={t('stepInfo.btnAriaLabel')}
                title={t('stepInfo.btnAriaLabel')}
            >
                <span className="step-info-btn-icon">?</span>
                <span className="step-info-btn-label">{t('stepInfo.btnLabel')}</span>
            </button>

            {open && (
                <div className="step-info-overlay" onClick={() => setOpen(false)}>
                    <div className="step-info-modal" onClick={e => e.stopPropagation()}>
                        <button className="step-info-close" onClick={() => setOpen(false)} aria-label={t('stepInfo.closeAriaLabel')}>&#x2715;</button>
                        <div className="step-info-badge">{t('stepInfo.stepBadge', { step: stepNum })}</div>
                        <h2 className="step-info-title">{t(`stepInfo.steps.${key}.title`)}</h2>
                        <p className="step-info-body">{t(`stepInfo.steps.${key}.why`)}</p>
                    </div>
                </div>
            )}
        </>
    );
};

export default StepInfoPopup;
