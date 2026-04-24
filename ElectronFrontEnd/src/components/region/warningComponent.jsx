import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCircleCheck, faVolumeHigh } from '@fortawesome/free-solid-svg-icons';

const WarningComponent = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    return (
        <div className="warning-card">
            <p className="warning-card-title">{t('warning.title')}</p>
            <ul className="warning-checklist">
                <li><FontAwesomeIcon icon={faCircleCheck} className="warning-check-icon" /> {t('warning.bluetooth')}</li>
                <li><FontAwesomeIcon icon={faCircleCheck} className="warning-check-icon" /> {t('warning.turnedOn')}</li>
                <li><FontAwesomeIcon icon={faVolumeHigh} className="warning-check-icon" /> {t('warning.sound')}</li>
            </ul>
            <p className="warning-card-note">
                {t('warning.note')} <button className="warning-help-link" onClick={() => navigate('/help')}>{t('warning.helpLink')}</button>
            </p>
        </div>
    );
};

export default WarningComponent;
