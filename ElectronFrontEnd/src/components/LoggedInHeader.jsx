import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import eegConnectService, { CONNECTION_STATUS } from '../service/wsEegService';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCircleCheck, faTriangleExclamation, faBatteryFull } from '@fortawesome/free-solid-svg-icons';
import StepInfoPopup from './StepInfoPopup';

const LoggedInHeader = () => {
    const { t, i18n } = useTranslation();

    const handleLanguageChange = (e) => {
        const lang = e.target.value;
        i18n.changeLanguage(lang);
        sessionStorage.setItem('language', lang);
    };
    const [battery, setBattery] = useState(eegConnectService.getBattery());
    const [poorSignal, setPoorSignal] = useState(eegConnectService.getPoorSignal());
    const [status, setStatus] = useState(eegConnectService.getStatus());

    useEffect(() => {
        const unsubBattery = eegConnectService.on('battery', setBattery);
        const unsubEeg = eegConnectService.on('eegData', d => setPoorSignal(d.poorSignal));
        const unsubStatus = eegConnectService.on('status', setStatus);
        eegConnectService.fetchStatus();
        return () => { unsubBattery(); unsubEeg(); unsubStatus(); };
    }, []);

    const isConnected = status === CONNECTION_STATUS.CONNECTED;

    const deviceText = {
        [CONNECTION_STATUS.DISCONNECTED]: t('loggedInHeader.disconnected'),
        [CONNECTION_STATUS.SEARCHING]: t('loggedInHeader.searching'),
        [CONNECTION_STATUS.CONNECTING]: t('loggedInHeader.connecting'),
        [CONNECTION_STATUS.CONNECTED]: t('loggedInHeader.connected'),
    }[status] || status;

    const signalText = !isConnected ? t('loggedInHeader.noDevice')
        : poorSignal >= 200 ? t('loggedInHeader.notWorn')
            : poorSignal < 25 ? t('loggedInHeader.signalGood')
                : t('loggedInHeader.signalNoisy');

    const signalClass = isConnected && poorSignal < 25 ? 'good' : 'warning';
    const deviceClass = isConnected ? 'good' : 'warning';

    return (
        <header className="eeg-header">
            <div className="header-left">
                <div className="battery-indicator">
                    <FontAwesomeIcon icon={faBatteryFull} style={{ marginRight: 6 }} />
                    {/* <span className="battery-label">Battery</span> */}
                    {battery != null ? (
                        <>
                            <div className="battery-bar-container">
                                <div className="battery-bar" style={{ width: `${battery}%` }} />
                            </div>
                            <span className="battery-percentage">{battery}%</span>
                        </>
                    ) : (
                        <span className="battery-percentage">--</span>
                    )}
                </div>
            </div>

            <div className="header-center">
                <div className="status-item">
                    <span className="status-label">{t('loggedInHeader.device')}</span>
                    <span className={`status-icon ${deviceClass}`}>
                        <FontAwesomeIcon icon={isConnected ? faCircleCheck : faTriangleExclamation} />
                    </span>
                    <span className={`status-value ${deviceClass}-text`}>{deviceText}</span>
                </div>
                <div className="status-divider">|</div>
                <div className="status-item">
                    <span className="status-label">{t('loggedInHeader.signal')}</span>
                    <span className={`status-icon ${signalClass}`}>
                        <FontAwesomeIcon icon={isConnected && poorSignal < 25 ? faCircleCheck : faTriangleExclamation} />
                    </span>
                    <span className={`status-value ${signalClass}-text`}>{signalText}</span>
                </div>
            </div>

            <div className="header-right">
                <StepInfoPopup />
                <div className="badge language-badge">
                    <select
                        className="language-select"
                        value={i18n.language}
                        onChange={handleLanguageChange}
                    >
                        <option value="en">English</option>
                        <option value="nl">Nederlands</option>
                    </select>
                    <span className="language-chevron">▾</span>
                </div>
                <span className="header-user">
                    {sessionStorage.getItem('loggedInUser') || ''}
                </span>
            </div>
        </header>
    );
};

export default LoggedInHeader;