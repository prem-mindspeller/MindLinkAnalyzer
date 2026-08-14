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

// How long to keep trying before stopping and handing control back to the user.
// The backend enforces the same budget independently (EEG_CONNECT_TIMEOUT_S),
// so a hung reader thread cannot outlast it even if this page is not watching.
const CONNECT_BUDGET_MS = 60000;
const RETRY_DELAY_MS = 1200;

const LiveEegReading = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();

    const [status, setStatus] = useState(eegConnectService.getStatus());
    const [poorSignal, setPoorSignal] = useState(eegConnectService.getPoorSignal());
    const [scanMessage, setScanMessage] = useState('');
    const [connectError, setConnectError] = useState('');
    // Set once the attempt budget runs out. The backend can still report
    // "connecting" at that point, so this — not the raw status — decides
    // whether the spinner or the Reconnect button is on screen.
    const [gaveUp, setGaveUp] = useState(false);
    // Raised only when the full budget elapses — not when no device was found,
    // which already has its own inline message.
    const [showTroubleModal, setShowTroubleModal] = useState(false);

    // Cancels an in-flight attempt loop when the page unmounts, so a run
    // started here does not outlive the page by up to a minute.
    const abandonedRef = useRef(false);

    const isConnected = status === CONNECTION_STATUS.CONNECTED;
    const isScanning = !gaveUp
        && (status === CONNECTION_STATUS.SEARCHING || status === CONNECTION_STATUS.CONNECTING);
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

    // Retry until the budget is spent rather than for a fixed number of tries,
    // so a slow-but-working device still gets its full minute.
    const connectWithRetry = async (portPath, budgetMs = CONNECT_BUDGET_MS) => {
        const deadline = Date.now() + budgetMs;
        let lastError = '';

        while (Date.now() < deadline && !abandonedRef.current) {
            const result = await eegConnectService.connect(portPath);
            if (abandonedRef.current) return { success: false, error: '' };

            if (!result.success) {
                lastError = result.error || t('errors.connectionFailed');
            } else {
                const remaining = Math.max(0, deadline - Date.now());
                if (await waitForConnectedStatus(Math.min(3500, remaining))) {
                    return { success: true };
                }
                lastError = t('errors.connectionFailed');
            }

            if (abandonedRef.current) return { success: false, error: '' };
            if (Date.now() + RETRY_DELAY_MS >= deadline) break;
            await wait(RETRY_DELAY_MS);
        }

        return {
            success: false,
            timedOut: true,
            error: lastError || t('errors.connectionFailed'),
        };
    };

    const scanAndConnect = async () => {
        setScanMessage('');
        setConnectError('');
        setGaveUp(false);
        setShowTroubleModal(false);

        const hwids = await eegConnectService.fetchAllowedHwids();
        const found = await eegConnectService.autoDetect(hwids);
        if (abandonedRef.current) return;

        if (!found) {
            setScanMessage(t('liveEeg.noDeviceDetected'));
            setGaveUp(true);
            return;
        }

        const result = await connectWithRetry(found.path);
        if (abandonedRef.current || result.success) return;

        // Release the device so the next attempt starts clean, and so a stale
        // backend "connecting" cannot keep driving the spinner.
        await eegConnectService.disconnect();
        if (abandonedRef.current) return;

        setConnectError(
            result.timedOut
                ? t('errors.connectionTimedOut', { seconds: CONNECT_BUDGET_MS / 1000 })
                : (result.error || t('errors.connectionFailed'))
        );
        setGaveUp(true);
        if (result.timedOut) setShowTroubleModal(true);
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
        abandonedRef.current = false;
        const init = async () => {
            await eegConnectService.fetchStatus();
            if (abandonedRef.current) return;
            if (eegConnectService.getStatus() === CONNECTION_STATUS.CONNECTED) return;
            await scanAndConnect();
        };
        init().catch((error) => {
            if (abandonedRef.current) return;
            setConnectError(error?.message || t('errors.connectionFailed'));
            setGaveUp(true);
        });
        return () => { abandonedRef.current = true; };
    }, [t]);

    // Escape closes the dialog, matching the click-outside affordance.
    useEffect(() => {
        if (!showTroubleModal) return;
        const onKeyDown = (e) => { if (e.key === 'Escape') setShowTroubleModal(false); };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [showTroubleModal]);

    const handleRescan = async () => {
        abandonedRef.current = false;
        try {
            await scanAndConnect();
        } catch (error) {
            if (abandonedRef.current) return;
            setConnectError(error?.message || t('errors.connectionFailed'));
            setGaveUp(true);
        }
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

            {showTroubleModal && (
                <div
                    className="step-info-overlay"
                    onClick={() => setShowTroubleModal(false)}
                >
                    <div
                        className="step-info-modal trouble-modal"
                        role="alertdialog"
                        aria-modal="true"
                        aria-labelledby="trouble-modal-title"
                        onClick={e => e.stopPropagation()}
                    >
                        <button
                            className="step-info-close"
                            onClick={() => setShowTroubleModal(false)}
                            aria-label={t('liveEeg.troubleCloseAriaLabel')}
                        >
                            &#x2715;
                        </button>

                        <div className="trouble-modal-icon">
                            <FontAwesomeIcon icon={faTriangleExclamation} />
                        </div>

                        <h2 className="step-info-title" id="trouble-modal-title">
                            {t('liveEeg.troubleTitle')}
                        </h2>
                        <p className="step-info-body">{t('liveEeg.troubleBody')}</p>

                        <div className="trouble-modal-actions">
                            <button
                                className="trouble-btn-primary"
                                onClick={() => { setShowTroubleModal(false); handleRescan(); }}
                            >
                                <FontAwesomeIcon icon={faRotate} style={{ marginRight: 8 }} />
                                {t('liveEeg.troubleRetry')}
                            </button>
                            <button
                                className="trouble-btn-secondary"
                                onClick={() => setShowTroubleModal(false)}
                            >
                                {t('liveEeg.troubleDismiss')}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default LiveEegReading;
