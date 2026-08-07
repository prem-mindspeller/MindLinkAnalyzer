import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
    const { t } = useTranslation();

    const [status, setStatus] = useState(eegConnectService.getStatus());
    const [poorSignal, setPoorSignal] = useState(eegConnectService.getPoorSignal());
    const [scanMessage, setScanMessage] = useState('');
    const [connectError, setConnectError] = useState('');

    const isConnected = status === CONNECTION_STATUS.CONNECTED;
    const isScanning = status === CONNECTION_STATUS.SEARCHING || status === CONNECTION_STATUS.CONNECTING;
    const isGoodSignal = isConnected && poorSignal < 25;

    const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    const waitForConnectedStatus = (timeoutMs = 3500) => new Promise((resolve) => {
        if (eegConnectService.getStatus() === CONNECTION_STATUS.CONNECTED) {
            resolve(true);
            return;
        }

        const timeout = setTimeout(() => {
            unsubStatus();
            resolve(eegConnectService.getStatus() === CONNECTION_STATUS.CONNECTED);
        }, timeoutMs);

        const unsubStatus = eegConnectService.on('status', (nextStatus) => {
            if (nextStatus === CONNECTION_STATUS.CONNECTED) {
                clearTimeout(timeout);
                unsubStatus();
                resolve(true);
            }
        });
    });

    const connectWithRetry = async (portPath, attempts = 3) => {
        let lastError = '';
        for (let attempt = 1; attempt <= attempts; attempt += 1) {
            const result = await eegConnectService.connect(portPath);
            if (!result.success) {
                lastError = result.error || t('errors.connectionFailed');
            } else if (await waitForConnectedStatus()) {
                return { success: true };
            } else {
                lastError = t('errors.connectionFailed');
            }

            if (attempt < attempts) {
                await wait(1200);
            }
        }
        return { success: false, error: lastError || t('errors.connectionFailed') };
    };

    const scanAndConnect = async () => {
        setScanMessage('');
        setConnectError('');
        const hwids = await eegConnectService.fetchAllowedHwids();
        const found = await eegConnectService.autoDetect(hwids);
        if (found) {
            const result = await connectWithRetry(found.path);
            if (!result.success) setConnectError(result.error || t('errors.connectionFailed'));
        } else {
            setScanMessage(t('liveEeg.noDeviceDetected'));
        }
    };

    // ── Subscribe to status + signal quality ─────────────────────────────────
    useEffect(() => {
        const unsubStatus = eegConnectService.on('status', setStatus);
        const unsubEeg = eegConnectService.on('eegData', d => setPoorSignal(d.poorSignal));
        return () => { unsubStatus(); unsubEeg(); };
    }, []);

    // ── On mount: adopt an existing live connection, otherwise scan. ──────────
    // The Python backend owns the device across navigation. Re-scanning while it
    // is already connected clobbers the CONNECTED status with SEARCHING, and
    // because /connect is idempotent it never re-emits 'connected' — leaving the
    // status stuck on "No Device / Searching" even though data still streams
    // (e.g. returning here from the baseline screen). Verify the authoritative
    // backend status first, then only scan when there is no connection to adopt.
    useEffect(() => {
        let cancelled = false;
        const init = async () => {
            await eegConnectService.fetchStatus();
            if (cancelled) return;
            if (eegConnectService.getStatus() === CONNECTION_STATUS.CONNECTED) return;
            await scanAndConnect();
        };
        init().catch((error) => {
            if (!cancelled) setConnectError(error?.message || t('errors.connectionFailed'));
        });
        return () => { cancelled = true; };
    }, [t]);

    const handleRescan = async () => {
        await scanAndConnect();
    };


    return (
        <div className="app-container">
            <LoggedInHeader />
            <main className="app-main">
                <div className="eeg-page" style={{ paddingTop: '20px' }}>
                    <h1 className='live-eeg-header'>{t('liveEeg.title')}</h1>
                    <p className="page-subtitle-eeg" style={{ textAlign: 'center', marginBottom: 16 }}>{t('liveEeg.subtitle')}</p>

                    {!isConnected && (
                        <div className="device-scan-section">
                            {isScanning ? (
                                <div className="scan-status scanning">
                                    <FontAwesomeIcon icon={faSpinner} spin style={{ marginRight: 8 }} />
                                    <span>
                                        {status === CONNECTION_STATUS.CONNECTING
                                            ? t('liveEeg.connecting')
                                            : t('liveEeg.scanning')}
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
                                        <FontAwesomeIcon icon={faRotate} style={{ marginRight: 8 }} />{t('liveEeg.reconnect')}
                                    </button>
                                </>
                            )}
                        </div>
                    )}


                    <div className="eeg-chart-container">
                        <div className={`signal-quality-line ${isGoodSignal ? 'sig-good' : 'sig-warn'}`}>
                            {isGoodSignal ? (
                                <><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 6 }} />{t('liveEeg.signalGood')}</>
                            ) : poorSignal >= 200 ? (
                                <><FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />{t('liveEeg.notWorn')}</>
                            ) : (
                                <><FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />{t('liveEeg.signalNoisy')}</>
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
                                    <p className="info-subtitle">{t('liveEeg.infoDisconnected')}</p>
                                </div>
                            </div></>
                    )}

                    {isConnected && (
                        <>
                            <div className="info-box">
                                <div className="info-content">
                                    <p className="info-subtitle">{t('liveEeg.infoConnected')}</p>
                                </div>
                            </div>
                        </>
                    )}

                </div>
            </main>
            <div className="nav-sub-footer">
                <button
                    className="btn-next-eeg"
                    onClick={() => navigate('/baselineCalibration1')}
                    disabled={!isGoodSignal}
                    title={!isGoodSignal ? t('liveEeg.waitForGoodSignal') : ''}
                >
                    {t('nav.next')} <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 6 }} />
                </button>
            </div>
            <Footer />
        </div>
    );
};

export default LiveEegReading;
