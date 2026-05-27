/**
 * wsEegService.js — WebSocket-based EEG data service.
 *
 * Drop-in replacement for EegConnectService.js.  Instead of using Electron IPC
 * to talk directly to the serial port, this service delegates everything to the
 * Python FastAPI backend running at http://localhost:8000.
 *
 * The Python backend owns the serial port, parses the TGAM stream, applies the
 * 1–45 Hz bandpass + 50 Hz notch filter chain, and broadcasts messages over a
 * WebSocket at ws://localhost:8000/ws.
 *
 * Interface (identical to EegConnectService.js)
 * ─────────────────────────────────────────────
 * on(event, cb)        subscribe; returns () => void unsubscribe
 * off(event, cb)
 * getStatus()          'disconnected' | 'searching' | 'connecting' | 'connected'
 * getBattery()         0–100 | null
 * getPoorSignal()      0–200  (200 = not worn)
 * getAttention()       0–100
 * getMeditation()      0–100
 * getBandPowers()      { delta, theta, lowAlpha, highAlpha,
 *                        lowBeta, highBeta, lowGamma, midGamma } | null
 * getRawBuffer()       number[]  (last ≤6144 filtered raw samples)
 * isConnected()        boolean
 * isWorn()             boolean  (poorSignal < 200)
 * isGoodSignal()       boolean  (poorSignal < 25)
 *
 * fetchAllowedHwids()  → string[]   calls Mindspeller API
 * autoDetect(hwids)    → port | null  calls GET /ports on Python backend
 * connect(portPath)    → { success, error? }
 * disconnect()         → void
 *
 * In-bound WebSocket messages from the Python backend
 * ────────────────────────────────────────────────────
 * { type: 'status',    value: 'connected'|'disconnected'|'connecting' }
 * { type: 'raw_batch', samples: number[] }
 * { type: 'raw_multi_batch', samples: Array<{ fp1, fp2, o1, o2 }> }
 * { type: 'device_info', device, sampleRate, channels }
 * { type: 'eeg_data',  poorSignal, attention, meditation, bandPower, battery }
 * { type: 'battery',   level: number }
 * { type: 'error',     message: string }
 */

import loginService from './loginService';

const BACKEND_HTTP = 'http://localhost:8000';
const BACKEND_WS = 'ws://localhost:8000/ws';

const API_ENDPOINTS = {
    en: 'https://en.mindspeller.com',
    nl: 'https://nl.mindspeller.com'
};

const KNOWN_HWIDS = ["5C361634682F", "5C3616327E59", "5C3616346938", "5C3616346838", "5C36163468D3", "5C3616327C21", "5C36163468D3", "90E2FC2C5F37", '90E2FC2C627C','90E2FC2C6378','90E2FC2C5E7D','90E2FC2C5FAA','90E2FC2C614B'];
const KNOWN_NAMES = ['brainlink', 'neurosky', 'ftdi', 'silabs', 'ch340'];

export const CONNECTION_STATUS = {
    DISCONNECTED: 'disconnected',
    SEARCHING: 'searching',
    CONNECTING: 'connecting',
    CONNECTED: 'connected',
};

class WsEegServiceClass {
    constructor() {
        this._status = CONNECTION_STATUS.DISCONNECTED;
        this._battery = null;
        this._poorSignal = 200;
        this._attention = 0;
        this._meditation = 0;
        this._bandPowers = null;
        this._rawBuffer = [];
        this._rawMultiBuffer = [];
        this._deviceInfo = null;
        this._listeners = {};

        this._ws = null;
        this._reconnectTimer = null;
        this._batteryPollTimer = null;
        this._connectPromise = null;
        this._connectPort = null;

        // Open the WebSocket after the current JS tick so the browser
        // context (window.WebSocket) is fully available before connecting.
        setTimeout(() => this._openWs(), 0);
    }

    /** No-op — kept for backward compatibility; WebSocket opens automatically. */
    init() { }


    _openWs() {
        if (this._ws && this._ws.readyState < 2) return; // CONNECTING or OPEN

        try {
            this._ws = new WebSocket(BACKEND_WS);
        } catch (e) {
            this._scheduleReconnect();
            return;
        }

        this._ws.onopen = () => {
            if (this._reconnectTimer) {
                clearTimeout(this._reconnectTimer);
                this._reconnectTimer = null;
            }
        };

        this._ws.onmessage = (event) => {
            let msg;
            try { msg = JSON.parse(event.data); } catch { return; }
            this._handleMessage(msg);
        };

        this._ws.onclose = () => this._scheduleReconnect();
        this._ws.onerror = () => { };
    }

    _scheduleReconnect(delayMs = 2000) {
        if (this._reconnectTimer) return;
        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this._openWs();
        }, delayMs);
    }

    _handleMessage(msg) {
        switch (msg.type) {
            case 'status':
                this._status = msg.value;
                if (msg.value === 'disconnected') {
                    this._stopBatteryPolling();
                    this._poorSignal = 200;
                    this._attention = 0;
                    this._meditation = 0;
                    this._bandPowers = null;
                    this._rawBuffer = [];
                    this._rawMultiBuffer = [];
                    this._deviceInfo = null;
                } else if (msg.value === 'connected') {
                    this.fetchStatus();
                    this._startBatteryPolling();
                }
                this._notify('status', msg.value);
                break;

            case 'raw_batch':
                if (Array.isArray(msg.samples)) {
                    for (const s of msg.samples) {
                        this._rawBuffer.push(s);
                        this._notify('raw', s);   // fire for every sample, not just the last
                    }
                    if (this._rawBuffer.length > 6144)
                        this._rawBuffer = this._rawBuffer.slice(-6144);
                }
                break;

            case 'raw_multi_batch':
                if (Array.isArray(msg.samples)) {
                    for (const sample of msg.samples) {
                        this._rawMultiBuffer.push(sample);
                        this._notify('rawMulti', sample);
                    }
                    if (this._rawMultiBuffer.length > 6144)
                        this._rawMultiBuffer = this._rawMultiBuffer.slice(-6144);
                }
                break;

            case 'device_info':
                this._deviceInfo = { ...msg };
                this._notify('deviceInfo', this._deviceInfo);
                break;

            case 'eeg_data':
                this._poorSignal = msg.poorSignal ?? this._poorSignal;
                this._attention = msg.attention ?? this._attention;
                this._meditation = msg.meditation ?? this._meditation;
                if (msg.bandPower != null) {
                    this._bandPowers = msg.bandPower;
                    this._notify('bandPower', msg.bandPower);
                }
                if (msg.battery != null) {
                    this._battery = msg.battery;
                    this._notify('battery', msg.battery);
                }
                this._notify('eegData', msg);
                break;

            case 'battery':
                this._battery = msg.level;
                this._notify('battery', msg.level);
                break;

            case 'error':
                break;

            default:
                break;
        }
    }

    // ── Pub / Sub ──────────────────────────────────────────────────────────

    on(event, cb) {
        if (!this._listeners[event]) this._listeners[event] = new Set();
        this._listeners[event].add(cb);
        return () => this.off(event, cb);
    }
    off(event, cb) { this._listeners[event]?.delete(cb); }
    _notify(event, data) { this._listeners[event]?.forEach(cb => cb(data)); }

    // ── State getters ──────────────────────────────────────────────────────

    getStatus() { return this._status; }
    getBattery() { return this._battery; }
    getPoorSignal() { return this._poorSignal; }
    getAttention() { return this._attention; }
    getMeditation() { return this._meditation; }
    getBandPowers() { return this._bandPowers ? { ...this._bandPowers } : null; }
    getRawBuffer() { return [...this._rawBuffer]; }
    getRawMultiBuffer() { return this._rawMultiBuffer.map(sample => ({ ...sample })); }
    getDeviceInfo() { return this._deviceInfo ? { ...this._deviceInfo } : null; }
    isConnected() { return this._status === CONNECTION_STATUS.CONNECTED; }
    isWorn() { return this._poorSignal < 200; }
    isGoodSignal() { return this._poorSignal < 25; }

    _startBatteryPolling() {
        this._stopBatteryPolling();
        // Poll aggressively (1 s) while battery is unknown, then settle to 5 s.
        const tick = () => {
            if (this._status !== CONNECTION_STATUS.CONNECTED) {
                this._stopBatteryPolling();
                return;
            }
            this.fetchStatus();
            const interval = this._battery == null ? 1000 : 5000;
            this._batteryPollTimer = setTimeout(tick, interval);
        };
        this._batteryPollTimer = setTimeout(tick, 500); // first check after 500 ms
    }

    _stopBatteryPolling() {
        if (this._batteryPollTimer) {
            clearTimeout(this._batteryPollTimer);
            this._batteryPollTimer = null;
        }
    }

    _stopBatteryPolling() {
        if (this._batteryPollTimer) {
            clearInterval(this._batteryPollTimer);
            this._batteryPollTimer = null;
        }
    }

    // ── Fetch user-specific allowed HWIDs from Mindspeller API ────────────

    async fetchAllowedHwids() {
        const token = loginService.getToken();
        const region = loginService.getRegion();
        const baseUrl = API_ENDPOINTS[region];
        if (!token || !baseUrl) return [];
        try {
            const res = await fetch(`${baseUrl}/api/cas/users/hwids`, {
                headers: { 'X-Authorization': `Bearer ${token}` },
            });
            if (!res.ok) return [];   // endpoint may not exist on all regions — silently ignore
            const data = await res.json();
            const raw = data.brainlink_hwid || [];
            return typeof raw === 'string' ? [raw] : raw;
        } catch {
            return [];
        }
    }

    // ── List ports via Python backend ──────────────────────────────────────

    async listPorts() {
        try {
            const res = await fetch(`${BACKEND_HTTP}/ports`);
            const data = await res.json();
            return data.ports || [];
        } catch {
            return [];
        }
    }

    // ── Auto-detect BrainLink ──────────────────────────────────────────────

    async autoDetect(allowedHwids = []) {
        this._status = CONNECTION_STATUS.SEARCHING;
        this._notify('status', CONNECTION_STATUS.SEARCHING);

        const ports = await this.listPorts();

        // 1. Prefer the MindRove Wi-Fi adapter exposed by the Python backend.
        const byMindRove = ports.find(p =>
            p.available !== false &&
            (
                p.deviceType === 'mindrove' ||
                (p.description || '').toLowerCase().includes('mindrove') ||
                (p.path || '').startsWith('mindrove://')
            )
        );
        if (byMindRove) return byMindRove;

        // 2. User-specific BrainLink HWIDs from the Mindspeller API
        if (allowedHwids.length > 0) {
            const match = ports.find(p => allowedHwids.some(hw => p.pnpId.includes(hw)));
            if (match) return match;
        }

        // 3. Default BrainLink HWID (Windows)
        const byHwid = ports.find(p => KNOWN_HWIDS.some(hw => p.pnpId.includes(hw)));
        if (byHwid) return byHwid;

        // 4. Name / path fallback (macOS / Linux)
        const byName = ports.find(p =>
            KNOWN_NAMES.some(n => (p.description || '').toLowerCase().includes(n)) ||
            p.path.startsWith('/dev/tty.usbserial') ||
            p.path.startsWith('/dev/tty.usbmodem')
        );
        if (byName) return byName;

        this._status = CONNECTION_STATUS.DISCONNECTED;
        this._notify('status', CONNECTION_STATUS.DISCONNECTED);
        return null;
    }

    async connect(portPath) {
        if (this._connectPromise && this._connectPort === portPath) {
            return this._connectPromise;
        }

        this._connectPort = portPath;
        this._connectPromise = (async () => {
            try {
                const res = await fetch(`${BACKEND_HTTP}/connect`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ port: portPath }),
                });
                return res.json();
            } catch (e) {
                return { success: false, error: e.message };
            } finally {
                this._connectPromise = null;
                this._connectPort = null;
            }
        })();

        return this._connectPromise;
    }

    // ── Disconnect ─────────────────────────────────────────────────────────

    async disconnect() {
        try {
            await fetch(`${BACKEND_HTTP}/disconnect`, { method: 'POST' });
        } catch { /* ignore */ }
        this._stopBatteryPolling();
        // State will be updated when the backend sends a 'status: disconnected' message
    }

    // ── Fetch current status + battery from backend (REST) ─────────────────

    async fetchStatus() {
        try {
            const res = await fetch(`${BACKEND_HTTP}/status`);
            if (!res.ok) return;
            const data = await res.json();
            if (data.battery != null && data.battery !== this._battery) {
                this._battery = data.battery;
                this._notify('battery', data.battery);
            }
            if (data.status && data.status !== this._status) {
                this._status = data.status;
                this._notify('status', data.status);
            }
        } catch { /* backend not running */ }
    }
}

const wsEegService = new WsEegServiceClass();
export default wsEegService;
