import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Footer from '../components/footer';
import LoggedInHeader from '../components/LoggedInHeader';
import eegConnectService, { CONNECTION_STATUS } from '../service/EegConnectService';
import '../styles/liveEegReading.css';

const DISPLAY_SAMPLES = 512; // ~2 s at 256 Hz

const LiveEegReading = () => {
    const navigate = useNavigate();
    const canvasRef = useRef(null);
    const rafRef = useRef(null);

    const [status, setStatus] = useState(eegConnectService.getStatus());
    const [poorSignal, setPoorSignal] = useState(eegConnectService.getPoorSignal());
    const [ports, setPorts] = useState([]);
    const [scanMessage, setScanMessage] = useState('');
    const [connectError, setConnectError] = useState('');

    const isConnected = status === CONNECTION_STATUS.CONNECTED;
    const isScanning = status === CONNECTION_STATUS.SEARCHING || status === CONNECTION_STATUS.CONNECTING;
    const isGoodSignal = isConnected && poorSignal < 25;

    // ── Canvas draw loop ──────────────────────────────────────────────────────
    const drawChart = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width, H = canvas.height;
        const samples = eegConnectService.getRawBuffer().slice(-DISPLAY_SAMPLES);

        ctx.fillStyle = '#001010';
        ctx.fillRect(0, 0, W, H);

        ctx.strokeStyle = '#0a2a2a';
        ctx.lineWidth = 1;
        for (let i = 1; i < 10; i++) {
            ctx.beginPath(); ctx.moveTo((i / 10) * W, 0); ctx.lineTo((i / 10) * W, H); ctx.stroke();
        }
        for (let i = 1; i < 5; i++) {
            ctx.beginPath(); ctx.moveTo(0, (i / 5) * H); ctx.lineTo(W, (i / 5) * H); ctx.stroke();
        }
        ctx.strokeStyle = '#0f3f3f';
        ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.stroke();

        if (samples.length < 2) {
            ctx.fillStyle = '#00ff88';
            ctx.font = '14px monospace';
            ctx.textAlign = 'center';
            ctx.fillText('Waiting for EEG data\u2026', W / 2, H / 2);
            return;
        }

        const SCALE = 600;
        ctx.strokeStyle = '#00ff88';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        samples.forEach((val, i) => {
            const x = (i / (DISPLAY_SAMPLES - 1)) * W;
            const y = H / 2 - (val / SCALE) * (H / 2) * 0.85;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();
    }, []);

    useEffect(() => {
        const loop = () => { drawChart(); rafRef.current = requestAnimationFrame(loop); };
        rafRef.current = requestAnimationFrame(loop);
        return () => cancelAnimationFrame(rafRef.current);
    }, [drawChart]);

    // ── Subscribe to service events ───────────────────────────────────────────
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
                setScanMessage('No BrainLink device detected. Make sure the device is switched on and try again.');
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
            setScanMessage('No BrainLink device detected. Make sure the device is switched on and try again.');
        }
    };

    const handleDisconnect = () => eegConnectService.disconnect();

    const signalText = !isConnected ? '\u2014'
        : poorSignal >= 200 ? 'Not Worn'
            : poorSignal < 25 ? 'Good \u2705'
                : 'Poor \u26a0\ufe0f';

    const warningText = !isConnected ? null
        : poorSignal >= 200 ? 'Headset not worn \u2014 place the headset firmly against your forehead.'
            : poorSignal >= 25 ? 'Signal quality is poor \u2014 hold still and press the headset against your forehead.'
                : null;

    return (
        <div className="app-container">
            <LoggedInHeader />
            <main className="app-main" style={{ alignItems: 'flex-start' }}>
                <div className="eeg-page" style={{ paddingTop: '20px' }}>

                    {/* ── Scanning / not-connected section ── */}
                    {!isConnected && (
                        <div className="device-scan-section">
                            {isScanning ? (
                                <div className="scan-status scanning">
                                    <span className="scan-spinner">&#x27F3;</span>
                                    <span>
                                        {status === CONNECTION_STATUS.CONNECTING
                                            ? 'Connecting to device\u2026'
                                            : 'Scanning for BrainLink device\u2026'}
                                    </span>
                                </div>
                            ) : (
                                <>
                                    {scanMessage && (
                                        <div className="scan-status warn">
                                            <span>&#x26A0;&#xFE0F; &nbsp;{scanMessage}</span>
                                        </div>
                                    )}
                                    {connectError && (
                                        <div className="scan-status error">
                                            <span>&#x274C; &nbsp;{connectError}</span>
                                        </div>
                                    )}
                                    <button className="rescan-btn" onClick={handleRescan}>
                                        &#x1F504; &nbsp;Scan Again
                                    </button>
                                </>
                            )}
                        </div>
                    )}

                    {/* ── Connected: live EEG ── */}
                    {isConnected && (
                        <>
                            <div className="info-box">
                                <div className="info-content">
                                    <p className="info-title">IMPORTANT: Please wait 20–30 seconds for the signal to stabilise after wearing the headset.</p>
                                    <p className="info-subtitle">Do NOT proceed until you see <strong>Signal quality: Good ✅</strong> in the header above.</p>
                                </div>
                            </div>

                            <div className="eeg-chart-container">
                                <div className="chart-header">
                                    Raw EEG Signal &nbsp;|&nbsp; Signal quality: <strong>{signalText}</strong>
                                </div>
                                <div className="chart-area" style={{ padding: 0, height: '300px' }}>
                                    <canvas
                                        ref={canvasRef}
                                        width={860}
                                        height={280}
                                        style={{ width: '100%', height: '100%' }}
                                    />
                                </div>
                            </div>

                            {warningText && (
                                <div className="warning-box">
                                    <span className="warning-message">⚠ &nbsp;{warningText}</span>
                                </div>
                            )}

                            <button className="device-disconnect-btn" onClick={handleDisconnect}>
                                🔌 &nbsp;Disconnect Device
                            </button>
                        </>
                    )}

                    <div className="navigation-buttons-eeg">
                        <button className="btn-back-eeg" onClick={() => navigate(-1)}>
                            ← Back
                        </button>
                        <button
                            className="btn-next-eeg"
                            onClick={() => navigate('/pathway')}
                            disabled={!isGoodSignal}
                            title={!isGoodSignal ? 'Wait for good signal quality before proceeding' : ''}
                        >
                            Next →
                        </button>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default LiveEegReading;