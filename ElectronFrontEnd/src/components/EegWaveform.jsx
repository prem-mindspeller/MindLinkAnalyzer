import React, { useEffect, useRef, useCallback } from 'react';
import eegConnectService from '../service/wsEegService';

const DISPLAY_SAMPLES = 2048;   // visible window — ~4 s at 512 Hz
const BUF_SIZE = 8192;   // ring buffer — ~16 s headroom
const FS = 512;


const EegWaveform = ({ status }) => {
    const canvasRef = useRef(null);
    const rafRef = useRef(null);
    const ringBuf = useRef(new Float32Array(BUF_SIZE));
    const ringHead = useRef(0);
    const ringCount = useRef(0);
    const sampleRateRef = useRef(0);
    const statusRef = useRef(status);

    // Keep statusRef in sync with prop so drawChart never reads a stale value
    useEffect(() => { statusRef.current = status; }, [status]);

    const drawChart = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width, H = canvas.height;

        const ML = 52, MR = 16, MT = 36, MB = 44;
        const PW = W - ML - MR;
        const PH = H - MT - MB;

        // Read from ring buffer
        const n = Math.min(ringCount.current, DISPLAY_SAMPLES);
        const samples = new Array(n);
        for (let i = 0; i < n; i++) {
            samples[i] = ringBuf.current[((ringHead.current - n + i) + BUF_SIZE) % BUF_SIZE];
        }

        // Background
        ctx.fillStyle = '#080808';
        ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = '#040404';
        ctx.fillRect(ML, MT, PW, PH);

        // Y scale
        let yMax = 400, yMin = -400;
        if (n > 1) {
            let dMax = samples[0], dMin = samples[0];
            for (const v of samples) { if (v > dMax) dMax = v; if (v < dMin) dMin = v; }
            const pad = Math.max((dMax - dMin) * 0.15, 50);
            yMax = Math.ceil((dMax + pad) / 100) * 100;
            yMin = Math.floor((dMin - pad) / 100) * 100;
        }
        const yRange = yMax - yMin || 1;

        // Grid + Y-axis labels
        const yStep = yRange <= 400 ? 100 : yRange <= 800 ? 200 : 400;
        ctx.font = '11px monospace';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        for (let v = Math.ceil(yMin / yStep) * yStep; v <= yMax; v += yStep) {
            const yp = MT + PH - ((v - yMin) / yRange) * PH;
            ctx.strokeStyle = v === 0 ? '#0f2e0f' : '#0a1a0a';
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(ML, yp); ctx.lineTo(ML + PW, yp); ctx.stroke();
            ctx.fillStyle = '#3a8a3a';
            ctx.fillText(v, ML - 4, yp);
        }

        // X-axis ticks (time in seconds)
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        for (let t = 0; t <= 8; t++) {
            const xp = ML + (t / 8) * PW;
            const sec = ((t / 8) * DISPLAY_SAMPLES / FS).toFixed(1);
            ctx.strokeStyle = '#0a1a0a';
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(xp, MT); ctx.lineTo(xp, MT + PH); ctx.stroke();
            ctx.fillStyle = '#3a8a3a';
            ctx.fillText(`${sec}s`, xp, MT + PH + 6);
        }
        ctx.fillStyle = '#5aaa5a';
        ctx.font = '12px sans-serif';
        ctx.fillText('Time', ML + PW / 2, MT + PH + 26);

        // Y-axis label
        ctx.save();
        ctx.translate(12, MT + PH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = '#5aaa5a';
        ctx.font = '12px sans-serif';
        ctx.fillText('µV', 0, 0);
        ctx.restore();

        // Border
        ctx.strokeStyle = '#143214';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(ML, MT, PW, PH);

        // Title + live Hz indicator
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = '#44cc44';
        ctx.font = 'bold 12px sans-serif';
        ctx.fillText('Raw EEG  ·  1–45 Hz bandpass  ·  50 Hz notch', ML + 4, MT / 2);
        if (sampleRateRef.current > 10) {
            ctx.textAlign = 'right';
            ctx.fillStyle = '#22aa22';
            ctx.font = '11px monospace';
            ctx.fillText(`${Math.round(sampleRateRef.current)} Hz  ●`, ML + PW - 4, MT / 2);
        }

        // Placeholder when buffer is empty
        if (n < 2) {
            const st = statusRef.current;
            const txt = st === 'connected'
                ? 'Waiting for EEG data…'
                : (st === 'searching' || st === 'connecting') ? 'Scanning for device…'
                    : 'No device — click Scan Again';
            ctx.fillStyle = '#2a5a2a';
            ctx.font = '14px monospace';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(txt, ML + PW / 2, MT + PH / 2);
            return;
        }

        // Waveform
        ctx.save();
        ctx.beginPath();
        ctx.rect(ML, MT, PW, PH);
        ctx.clip();
        ctx.strokeStyle = '#00e040';
        ctx.lineWidth = 1.5;
        ctx.lineJoin = 'round';
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
            const x = ML + (i / (DISPLAY_SAMPLES - 1)) * PW;
            const y = MT + PH - ((samples[i] - yMin) / yRange) * PH;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.restore();
    }, []);

    // RAF render loop
    useEffect(() => {
        const loop = () => { drawChart(); rafRef.current = requestAnimationFrame(loop); };
        rafRef.current = requestAnimationFrame(loop);
        return () => cancelAnimationFrame(rafRef.current);
    }, [drawChart]);

    // Subscribe to raw samples — fill ring buffer + measure Hz
    useEffect(() => {
        let hzCount = 0;
        let hzTimestamp = performance.now();

        const unsubRaw = eegConnectService.on('raw', (sample) => {
            ringBuf.current[ringHead.current] = sample;
            ringHead.current = (ringHead.current + 1) % BUF_SIZE;
            if (ringCount.current < BUF_SIZE) ringCount.current++;

            hzCount++;
            if (hzCount >= 256) {
                const now = performance.now();
                const elapsed = (now - hzTimestamp) / 1000;
                sampleRateRef.current = elapsed > 0 ? hzCount / elapsed : 0;
                hzTimestamp = now;
                hzCount = 0;
            }
        });

        return () => unsubRaw();
    }, []);

    return (
        <canvas
            ref={canvasRef}
            width={900}
            height={360}
            style={{ width: '100%', height: '100%' }}
        />
    );
};

export default EegWaveform;
