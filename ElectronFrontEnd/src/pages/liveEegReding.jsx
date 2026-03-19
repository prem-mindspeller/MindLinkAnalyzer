import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Footer from '../components/footer';
import LoggedInHeader from '../components/LoggedInHeader';
import eegConnectService, { CONNECTION_STATUS } from '../service/EegConnectService';
import '../styles/liveEegReading.css';

const DISPLAY_SAMPLES = 512;  // visible window (~1 s at 512 Hz) — scrolls smoothly
const FS = 512; // samples per second

const LiveEegReading = () => {
    const navigate = useNavigate();
    const canvasRef = useRef(null);
    const rafRef = useRef(null);

    const [status, setStatus] = useState(eegConnectService.getStatus());
    const [poorSignal, setPoorSignal] = useState(eegConnectService.getPoorSignal());
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

        // Layout margins
        const ML = 58;  // left  — room for Y-axis labels + "Amplitude (µV)"
        const MR = 16;  // right
        const MT = 36;  // top   — room for chart title
        const MB = 44;  // bottom — room for X-axis ticks + "Time (samples)"
        const PW = W - ML - MR;  // plot width
        const PH = H - MT - MB;  // plot height

        const samples = eegConnectService.getRawBuffer().slice(-DISPLAY_SAMPLES);

        // ── Background ──────────────────────────────────────────────────────
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, W, H);

        // Inner plot background (slightly lighter)
        ctx.fillStyle = '#0f0f1e';
        ctx.fillRect(ML, MT, PW, PH);

        // ── Y scale: auto-fit to data, rounded to nearest 100 ───────────────
        let yMax = 400, yMin = -400;
        if (samples.length > 1) {
            const dataMax = Math.max(...samples);
            const dataMin = Math.min(...samples);
            const pad = Math.max((dataMax - dataMin) * 0.15, 50);
            yMax = Math.ceil((dataMax + pad) / 100) * 100;
            yMin = Math.floor((dataMin - pad) / 100) * 100;
        }
        const yRange = yMax - yMin;

        // ── Grid & Y-axis ticks ──────────────────────────────────────────────
        const yStep = yRange <= 400 ? 100 : yRange <= 800 ? 200 : 400;
        const firstTick = Math.ceil(yMin / yStep) * yStep;
        ctx.lineWidth = 1;
        ctx.font = '11px monospace';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        for (let v = firstTick; v <= yMax; v += yStep) {
            const yp = MT + PH - ((v - yMin) / yRange) * PH;
            // Grid line
            ctx.strokeStyle = v === 0 ? '#2a3a5a' : '#1e2a3a';
            ctx.beginPath(); ctx.moveTo(ML, yp); ctx.lineTo(ML + PW, yp); ctx.stroke();
            // Tick label
            ctx.fillStyle = '#8899bb';
            ctx.fillText(v, ML - 6, yp);
        }

        // ── X-axis ticks & "Time (samples)" label ────────────────────────────
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        const xTickStep = 100;
        for (let s = 0; s <= DISPLAY_SAMPLES; s += xTickStep) {
            const xp = ML + (s / DISPLAY_SAMPLES) * PW;
            ctx.strokeStyle = '#1e2a3a';
            ctx.beginPath(); ctx.moveTo(xp, MT); ctx.lineTo(xp, MT + PH); ctx.stroke();
            ctx.fillStyle = '#8899bb';
            ctx.fillText(s, xp, MT + PH + 6);
        }
        ctx.fillStyle = '#aabbcc';
        ctx.font = '12px sans-serif';
        ctx.fillText('Time (samples)', ML + PW / 2, MT + PH + 24);

        // ── Y-axis label (rotated) ───────────────────────────────────────────
        ctx.save();
        ctx.translate(13, MT + PH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = '#aabbcc';
        ctx.font = '12px sans-serif';
        ctx.fillText('Amplitude (µV)', 0, 0);
        ctx.restore();

        // ── Axes borders ─────────────────────────────────────────────────────
        ctx.strokeStyle = '#334466';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(ML, MT, PW, PH);

        // ── Chart title ───────────────────────────────────────────────────────
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = '#cce0ff';
        ctx.font = 'bold 13px sans-serif';
        ctx.fillText('Raw EEG Signal (filtered 1–45 Hz)', ML + PW / 2, MT / 2);

        // ── "No data" placeholder ─────────────────────────────────────────────
        if (samples.length < 2) {
            ctx.fillStyle = '#5588aa';
            ctx.font = '14px monospace';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('Waiting for EEG data…', ML + PW / 2, MT + PH / 2);
            return;
        }

        // ── Waveform ────────────────────────────────────────────────────────
        ctx.save();
        ctx.beginPath();
        ctx.rect(ML, MT, PW, PH);  // clip to plot area
        ctx.clip();

        ctx.strokeStyle = '#4d9de0';
        ctx.lineWidth = 1.8;
        ctx.lineJoin = 'round';
        ctx.beginPath();
        samples.forEach((val, i) => {
            const x = ML + (i / (DISPLAY_SAMPLES - 1)) * PW;
            const y = MT + PH - ((val - yMin) / yRange) * PH;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.restore();
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
                                <div className="chart-area" style={{ padding: 0, height: '360px' }}>
                                    <canvas
                                        ref={canvasRef}
                                        width={900}
                                        height={360}
                                        style={{ width: '100%', height: '100%' }}
                                    />
                                </div>
                            </div>

                            <div className={`signal-quality-line ${isGoodSignal ? 'sig-good' : 'sig-warn'}`}>
                                {isGoodSignal
                                    ? '✓ Signal quality: Good\u2002|\u2002Data flowing normally'
                                    : poorSignal >= 200
                                        ? '⚠ Headset not worn — place it firmly against your forehead'
                                        : '⚠ Signal quality: Poor — hold still and press the headset against your forehead'}
                            </div>

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