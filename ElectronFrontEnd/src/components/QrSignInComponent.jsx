import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import QRCode from 'qrcode';
import devicePairingService from '../service/devicePairingService';
import wsEegService from '../service/wsEegService';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faSpinner, faTriangleExclamation, faRotateRight, faArrowLeft } from '@fortawesome/free-solid-svg-icons';

const { POLL_STATUS } = devicePairingService;

const QrSignInComponent = ({ onLoginSuccess, onCancel }) => {
    const { t } = useTranslation();
    const [pairing, setPairing] = useState(null);
    const [secondsLeft, setSecondsLeft] = useState(0);
    const [error, setError] = useState('');
    const [expired, setExpired] = useState(false);
    const [starting, setStarting] = useState(true);

    const canvasRef = useRef(null);
    const pollTimer = useRef(null);
    const countdownTimer = useRef(null);
    // Guards against a poll resolving after the component has gone away.
    const cancelled = useRef(false);

    const clearTimers = () => {
        if (pollTimer.current) { clearInterval(pollTimer.current); pollTimer.current = null; }
        if (countdownTimer.current) { clearInterval(countdownTimer.current); countdownTimer.current = null; }
    };

    const beginPairing = useCallback(async () => {
        clearTimers();
        setError('');
        setExpired(false);
        setStarting(true);
        setPairing(null);

        const region = sessionStorage.getItem('region') || 'en';

        try {
            const result = await devicePairingService.startPairing(region);
            if (cancelled.current) return;
            setPairing(result);
            setSecondsLeft(result.expiresIn);
        } catch (err) {
            if (cancelled.current) return;
            setError(err.message);
        } finally {
            if (!cancelled.current) setStarting(false);
        }
    }, []);

    useEffect(() => {
        cancelled.current = false;
        beginPairing();
        return () => {
            cancelled.current = true;
            clearTimers();
        };
    }, [beginPairing]);

    // Draw the QR once we have a pairing and the canvas is mounted.
    useEffect(() => {
        if (!pairing || !canvasRef.current) return;
        QRCode.toCanvas(canvasRef.current, pairing.verificationUrl, {
            width: 232,
            margin: 1,
            errorCorrectionLevel: 'M',
        }).catch(() => {
            setError(t('errors.qrRenderFailed'));
        });
    }, [pairing, t]);

    // Poll + countdown, torn down together.
    useEffect(() => {
        if (!pairing) return;

        const region = sessionStorage.getItem('region') || 'en';

        countdownTimer.current = setInterval(() => {
            setSecondsLeft((prev) => (prev > 0 ? prev - 1 : 0));
        }, 1000);

        pollTimer.current = setInterval(async () => {
            const result = await devicePairingService.pollPairing(
                pairing.code, pairing.deviceSecret, region
            );
            if (cancelled.current) return;

            if (result.status === POLL_STATUS.APPROVED) {
                clearTimers();
                wsEegService.init();
                onLoginSuccess(result.email);
                return;
            }

            if (result.status === POLL_STATUS.EXPIRED || result.status === POLL_STATUS.NOT_FOUND) {
                clearTimers();
                setExpired(true);
                return;
            }

            if (result.status === POLL_STATUS.INVALID) {
                clearTimers();
                setError(t('errors.qrNoLongerValid'));
                return;
            }
            // 'pending' and transient errors: keep waiting.
        }, pairing.interval * 1000);

        return clearTimers;
    }, [pairing, onLoginSuccess, t]);

    // Countdown reaching zero mirrors the server-side TTL.
    useEffect(() => {
        if (pairing && secondsLeft === 0 && !expired) {
            clearTimers();
            setExpired(true);
        }
    }, [secondsLeft, pairing, expired]);

    const mmss = `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')}`;

    return (
        <div className="login-card">
            <div className="qr-signin">
                <p className="qr-instructions">{t('qrSignIn.instructions')}</p>

                {starting && (
                    <div className="qr-loading">
                        <FontAwesomeIcon icon={faSpinner} spin style={{ marginRight: 8 }} />
                        {t('qrSignIn.preparing')}
                    </div>
                )}

                {!starting && error && (
                    <div className="error-message">
                        <span className="error-icon"><FontAwesomeIcon icon={faTriangleExclamation} /></span>
                        <span>{error}</span>
                    </div>
                )}

                {!starting && expired && (
                    <div className="qr-expired">
                        <p>{t('qrSignIn.expired')}</p>
                        <button type="button" className="submit-btn" onClick={beginPairing}>
                            <FontAwesomeIcon icon={faRotateRight} style={{ marginRight: 8 }} />
                            {t('qrSignIn.newCode')}
                        </button>
                    </div>
                )}

                {!starting && pairing && !expired && (
                    <>
                        <div className="qr-canvas-wrap">
                            <canvas ref={canvasRef} />
                        </div>

                        <p className="qr-timer">
                            {t('qrSignIn.expiresIn')} <strong>{mmss}</strong>
                        </p>

                        <div className="qr-waiting">
                            <FontAwesomeIcon icon={faSpinner} spin style={{ marginRight: 8 }} />
                            {t('qrSignIn.waiting')}
                        </div>

                        <details className="qr-fallback">
                            <summary>{t('qrSignIn.cantScan')}</summary>
                            <p className="qr-fallback-text">{t('qrSignIn.openAddress')}</p>
                            <code className="qr-fallback-url">{pairing.verificationUrl}</code>
                        </details>
                    </>
                )}

                <button type="button" className="btn-back qr-back" onClick={onCancel}>
                    <FontAwesomeIcon icon={faArrowLeft} style={{ marginRight: 6 }} />
                    {t('qrSignIn.usePasswordInstead')}
                </button>
            </div>
        </div>
    );
};

export default QrSignInComponent;
