/**
 * serialService.js — Electron IPC transport layer
 *
 * This module is the ONLY place in the renderer that knows about ipcRenderer.
 * It provides:
 *   - invoke methods  (renderer → main, returns a Promise)
 *   - subscribe methods (main → renderer push, returns an unsubscribe function)
 *
 * Business logic belongs in EegConnectService.js, not here.
 *
 * IPC channels exposed by main.js
 * ────────────────────────────────────────────────────────
 * INVOKE (renderer → main)
 *   eeg:list-ports   → { ports: [{path,pnpId,manufacturer,description}], error? }
 *   eeg:connect      → { success: bool, error? }
 *   eeg:disconnect   → { success: bool }
 *
 * PUSH (main → renderer)
 *   eeg:connection-status  → string  ('disconnected' | 'searching' | 'connecting' | 'connected')
 *   eeg:raw-data-batch     → number[]  filtered raw EEG samples (≈8 per frame at 512 Hz / 60 fps)
 *   eeg:eeg-data           → { poorSignal, attention, meditation, bandPower, battery }
 *   eeg:extend-data        → { battery, version }
 */

const { ipcRenderer } = require('electron');

/**
 * Creates a subscribe function for a named IPC channel.
 * The returned subscribe function accepts a callback and returns an unsubscribe function.
 */
function makeSubscription(channel) {
    return (cb) => {
        const handler = (_, payload) => cb(payload);
        ipcRenderer.on(channel, handler);
        return () => ipcRenderer.removeListener(channel, handler);
    };
}

const serialService = {
    // ── Renderer → Main (request / response) ─────────────────────────────────

    /** List all available serial ports. */
    listPorts: () => ipcRenderer.invoke('eeg:list-ports'),

    /** Open a serial connection to the given port path. */
    connect: (portPath) => ipcRenderer.invoke('eeg:connect', portPath),

    /** Close the active serial connection. */
    disconnect: () => ipcRenderer.invoke('eeg:disconnect'),

    // ── Main → Renderer (push subscriptions) ─────────────────────────────────
    // Each method accepts a callback and returns an () => void unsubscribe function.

    /** Connection lifecycle: 'disconnected' | 'searching' | 'connecting' | 'connected' */
    onStatus: makeSubscription('eeg:connection-status'),

    /**
     * Batched filtered raw EEG samples (number[]).
     * Flushed every ~16 ms (~60 fps) by main.js to avoid IPC flooding at 512 Hz.
     */
    onRawBatch: makeSubscription('eeg:raw-data-batch'),

    /**
     * Parsed EEG scalar packet:
     *   poorSignal  0–200 (0 = perfect, 200 = not worn)
     *   attention   0–100
     *   meditation  0–100
     *   bandPower   { delta, theta, lowAlpha, highAlpha, lowBeta, highBeta, lowGamma, midGamma } | null
     *   battery     0–100 | null
     */
    onEegData: makeSubscription('eeg:eeg-data'),

    /**
     * BrainLink extended packet (battery + firmware version).
     *   battery  0–100
     *   version  string | null
     */
    onExtendData: makeSubscription('eeg:extend-data'),
};

export default serialService;
