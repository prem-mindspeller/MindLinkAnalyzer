import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Footer from '../components/footer';
import LoggedInHeader from '../components/LoggedInHeader';
import EegWaveform from '../components/EegWaveform';
import eegConnectService, { CONNECTION_STATUS } from '../service/wsEegService';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faArrowRight, faRotate, faTriangleExclamation, faCircleXmark,
    faCircleCheck, faSpinner,
} from '@fortawesome/free-solid-svg-icons';
import '../styles/liveEegReading.css';

const LiveEegReading = () => {
    const navigate = useNavigate();

    const [status, setStatus] = useState(eegConnectService.getStatus());
    const [poorSignal, setPoorSignal] = useState(eegConnectService.getPoorSignal());
    const [scanMessage, setScanMessage] = useState('');
    const [connectError, setConnectError] = useState('');

    const isConnected = status === CONNECTION_STATUS.CONNECTED;
    const isScanning = status === CONNECTION_STATUS.SEARCHING || status === CONNECTION_STATUS.CONNECTING;
    const isGoodSignal = isConnected && poorSignal < 25;

    // ── Subscribe to status + signal quality ─────────────────────────────────
    useEffect(() => {
        const unsubStatus = eegConnectService.on('status', setStatus);
        const unsubEeg = eegConnectService.on('eegData', d => setPoorSignal(d.poorSignal));
        return () => { unsubStatus(); unsubEeg(); };
    }, []);

    // ── Auto-scan on mount (always runs — never skip based on stale cached status) ──
    useEffect(() => {
        const scan = async () => {
            setScanMessage('');
            setConnectError('');
            const hwids = await eegConnectService.fetchAllowedHwids();
            const found = await eegConnectService.autoDetect(hwids);
            if (found) {
                const result = await eegConnectService.connect(found.path);
                if (!result.success) setConnectError(result.error || 'Connection failed.');
            } else {
                setScanMessage('No EEG device detected. Make sure the device is switched on and try again.');
            }
        };
        scan();
    }, []);

    const handleRescan = async () => {
        setScanMessage('');
        setConnectError('');
        const hwids = await eegConnectService.fetchAllowedHwids();
        const found = await eegConnectService.autoDetect(hwids);
        if (found) {
            const result = await eegConnectService.connect(found.path);
            if (!result.success) setConnectError(result.error || 'Connection failed.');
        } else {
            setScanMessage('No EEG device detected. Make sure the device is switched on and try again.');
        }
    };


    return (
        <div className="app-container">
            <LoggedInHeader />
            <main className="app-main">
                <div className="eeg-page" style={{ paddingTop: '20px' }}>
                    <h1 className='live-eeg-header'>Live EEG Reading</h1>
                    <p className="page-subtitle-eeg" style={{ textAlign: 'center', marginBottom: 16 }}>Step 4 of 7: Connect your EEG device</p>

                    {!isConnected && (
                        <div className="device-scan-section">
                            {isScanning ? (
                                <div className="scan-status scanning">
                                    <FontAwesomeIcon icon={faSpinner} spin style={{ marginRight: 8 }} />
                                    <span>
                                        {status === CONNECTION_STATUS.CONNECTING
                                            ? 'Connecting to device…'
                                            : 'Scanning for EEG device…'}
                                    </span>
                                </div>
                            ) : (
                                <>
                                    {scanMessage && (
                                        <div className="scan-status warn">
                                            <FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 8 }} />
                                            <span>{scanMessage}</span>
                                        </div>
                                    )}
                                    {connectError && (
                                        <div className="scan-status error">
                                            <FontAwesomeIcon icon={faCircleXmark} style={{ marginRight: 8 }} />
                                            <span>{connectError}</span>
                                        </div>
                                    )}
                                    <button className="rescan-btn" onClick={handleRescan}>
                                        <FontAwesomeIcon icon={faRotate} style={{ marginRight: 8 }} />Reconnect
                                    </button>
                                </>
                            )}
                        </div>
                    )}


                    <div className="eeg-chart-container">
                        <div className={`signal-quality-line ${isGoodSignal ? 'sig-good' : 'sig-warn'}`}>
                            {isGoodSignal ? (
                                <><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 6 }} />Signal quality: Good | Data flowing normally</>
                            ) : poorSignal >= 200 ? (
                                <><FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />Headset not worn — place it firmly against your forehead</>
                            ) : (
                                <><FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />Signal quality: Noisy — hold still and press the headset against your forehead</>
                            )}
                        </div>
                        <div className="chart-area" style={{ padding: 0, height: '360px' }}>
                            <EegWaveform status={status} />
                        </div>
                    </div>
                    {!isConnected && (
                        <>
                            <div className="info-box">
                                <div className="info-content">
                                    <p className="info-subtitle">Click on the <strong>Reconnect</strong> button above to connect to the device before proceeding</p>
                                </div>
                            </div></>
                    )}

                    {isConnected && (
                        <>
                            <div className="info-box">
                                <div className="info-content">
                                    <p className="info-subtitle">Do NOT proceed until you see <strong>Signal quality: Good </strong> in the header above.</p>
                                </div>
                            </div>
                        </>
                    )}

                    <div className="navigation-buttons-eeg">
                        <button
                            className="btn-next-eeg"
                            onClick={() => navigate('/baselineCalibration1')}
                            disabled={!isGoodSignal}
                            title={!isGoodSignal ? 'Wait for good signal quality before proceeding' : ''}
                        >
                            Next <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 6 }} />
                        </button>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default LiveEegReading;