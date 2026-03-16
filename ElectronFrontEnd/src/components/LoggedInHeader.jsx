import React, { useState, useEffect } from 'react';
import eegConnectService, { CONNECTION_STATUS } from '../service/EegConnectService';

const LoggedInHeader = () => {
    const [battery, setBattery] = useState(eegConnectService.getBattery());
    const [poorSignal, setPoorSignal] = useState(eegConnectService.getPoorSignal());
    const [status, setStatus] = useState(eegConnectService.getStatus());

    useEffect(() => {
        const unsubBattery = eegConnectService.on('battery', setBattery);
        const unsubEeg = eegConnectService.on('eegData', d => setPoorSignal(d.poorSignal));
        const unsubStatus = eegConnectService.on('status', setStatus);
        return () => { unsubBattery(); unsubEeg(); unsubStatus(); };
    }, []);

    const isConnected = status === CONNECTION_STATUS.CONNECTED;

    const deviceText = {
        [CONNECTION_STATUS.DISCONNECTED]: 'Disconnected',
        [CONNECTION_STATUS.SEARCHING]: 'Searching…',
        [CONNECTION_STATUS.CONNECTING]: 'Connecting…',
        [CONNECTION_STATUS.CONNECTED]: 'Connected',
    }[status] || status;

    const signalText = !isConnected ? 'No Device'
        : poorSignal >= 200 ? 'Not Worn'
            : poorSignal < 25 ? 'Good'
                : 'Poor';

    const signalClass = isConnected && poorSignal < 25 ? 'good' : 'warning';
    const deviceClass = isConnected ? 'good' : 'warning';

    return (
        <header className="eeg-header">
            <div className="header-left">
                <div className="battery-indicator">
                    <span className="battery-label">Battery</span>
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
                    <span className="status-label">Device:</span>
                    <span className={`status-icon ${deviceClass}`}>
                        {isConnected ? '✅' : '⚠'}
                    </span>
                    <span className={`status-value ${deviceClass}-text`}>{deviceText}</span>
                </div>
                <div className="status-divider">|</div>
                <div className="status-item">
                    <span className="status-label">Signal:</span>
                    <span className={`status-icon ${signalClass}`}>
                        {isConnected && poorSignal < 25 ? '✅' : '⚠'}
                    </span>
                    <span className={`status-value ${signalClass}-text`}>{signalText}</span>
                </div>
            </div>

            <div className="header-right">
                <span className="header-user">
                    {sessionStorage.getItem('loggedInUser') || ''}
                </span>
            </div>
        </header>
    );
};

export default LoggedInHeader;