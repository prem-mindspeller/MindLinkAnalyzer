import loginService from './loginService';
const { ipcRenderer } = require('electron');

const API_ENDPOINTS = {
    en: 'https://stg-en.mindspell.be',
    nl: 'https://stg-nl.mindspell.be',
    local: 'http://127.0.0.1:5000'
};

const KNOWN_HWIDS = ['5C3616346838'];
const KNOWN_NAMES = ['brainlink', 'neurosky', 'ftdi', 'silabs', 'ch340'];

export const CONNECTION_STATUS = {
    DISCONNECTED: 'disconnected',
    SEARCHING: 'searching',
    CONNECTING: 'connecting',
    CONNECTED: 'connected'
};

class EegConnectServiceClass {
    constructor() {
        this._status = CONNECTION_STATUS.DISCONNECTED;
        this._battery = null;
        this._poorSignal = 200;
        this._rawBuffer = [];
        this._listeners = {};

        ipcRenderer.on('eeg:connection-status', (_, status) => {
            this._status = status;
            this._notify('status', status);
        });

        ipcRenderer.on('eeg:raw-data', (_, raw) => {
            this._rawBuffer.push(raw);
            if (this._rawBuffer.length > 2560) this._rawBuffer = this._rawBuffer.slice(-2560);
            this._notify('raw', raw);
        });

        ipcRenderer.on('eeg:eeg-data', (_, data) => {
            this._poorSignal = data.poorSignal;
            if (data.battery != null) {
                this._battery = data.battery;
                this._notify('battery', data.battery);
            }
            this._notify('eegData', data);
        });

        ipcRenderer.on('eeg:extend-data', (_, data) => {
            if (data.battery != null) {
                this._battery = data.battery;
                this._notify('battery', data.battery);
            }
        });
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
    getRawBuffer() { return [...this._rawBuffer]; }
    isConnected() { return this._status === CONNECTION_STATUS.CONNECTED; }
    isWorn() { return this._poorSignal < 200; }
    isGoodSignal() { return this._poorSignal < 25; }

    // ── Fetch user-specific allowed HWIDs from API ─────────────────────────
    async fetchAllowedHwids() {
        const token = loginService.getToken();
        const region = loginService.getRegion();
        const baseUrl = API_ENDPOINTS[region];
        try {
            const res = await fetch(`${baseUrl}/api/cas/users/hwids`, {
                headers: { 'X-Authorization': `Bearer ${token}` }
            });
            if (!res.ok) return [];
            const data = await res.json();
            const raw = data.brainlink_hwid || [];
            return typeof raw === 'string' ? [raw] : raw;
        } catch {
            return [];
        }
    }

    // ── List all available serial ports ───────────────────────────────────
    async listPorts() {
        const result = await ipcRenderer.invoke('eeg:list-ports');
        return result.ports || [];
    }

    // ── Auto-detect BrainLink: returns matched port object or null ─────────
    async autoDetect(allowedHwids = []) {
        this._status = CONNECTION_STATUS.SEARCHING;
        this._notify('status', CONNECTION_STATUS.SEARCHING);

        const ports = await this.listPorts();

        // 1. User-specific HWIDs from the API
        if (allowedHwids.length > 0) {
            const match = ports.find(p => allowedHwids.some(hw => p.pnpId.includes(hw)));
            if (match) return match;
        }

        // 2. Default BrainLink HWID (Windows)
        const byHwid = ports.find(p => KNOWN_HWIDS.some(hw => p.pnpId.includes(hw)));
        if (byHwid) return byHwid;

        // 3. Name / path fallback (macOS / Linux)
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

    // ── Connect to a specific port path ───────────────────────────────────
    async connect(portPath) {
        return ipcRenderer.invoke('eeg:connect', portPath);
    }

    // ── Disconnect ────────────────────────────────────────────────────────
    async disconnect() {
        await ipcRenderer.invoke('eeg:disconnect');
        this._status = CONNECTION_STATUS.DISCONNECTED;
        this._battery = null;
        this._poorSignal = 200;
        this._rawBuffer = [];
        this._notify('status', CONNECTION_STATUS.DISCONNECTED);
    }
}

// Singleton — all components share the same state
const eegConnectService = new EegConnectServiceClass();
export default eegConnectService;
