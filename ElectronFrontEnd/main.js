const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const path = require('path')
const { autoUpdater } = require('electron-updater')

if (process.env.NODE_ENV === 'development') {
    require('electron-reload')(__dirname, {
        electron: path.join(__dirname, 'node_modules', '.bin', 'electron'),
        hardResetMethod: 'exit'
    });
}

// ─── Serial port ─────────────────────────────────────────────────────────────
// Install with: npm install serialport  then  npx electron-rebuild
let SerialPort = null
try {
    SerialPort = require('serialport').SerialPort
} catch (e) {
}

// ─── TGAM Protocol Parser ─────────────────────────────────────────────────────
// NeuroSky / BrainLink byte codes
const CODE_POOR_SIGNAL = 0x02
const CODE_ATTENTION = 0x04
const CODE_MEDITATION = 0x05
const CODE_RAW_EEG = 0x81  // 2-byte int16 big-endian raw ADC
const CODE_EEG_POWER = 0x83  // 24-byte band powers (8 × uint24 big-endian)
const CODE_EXTENDED = 0x85  // BrainLink proprietary: byte[0]=battery%, byte[1-2]=fw version

// Band order as defined by NeuroSky TGAM / BrainLink 0x83 packet
const BAND_NAMES = ['delta', 'theta', 'lowAlpha', 'highAlpha', 'lowBeta', 'highBeta', 'lowGamma', 'midGamma']

// ─── Digital EEG Filters ──────────────────────────────────────────────────────
// Direct-Form I biquad: y[n] = b0·x[n] + b1·x[n−1] + b2·x[n−2] − a1·y[n−1] − a2·y[n−2]
function createBiquad(b0, b1, b2, a1, a2) {
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0
    return function (x) {
        const y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1; x1 = x; y2 = y1; y1 = y
        return y
    }
}

/**
 * Cascaded 2nd-order Butterworth band-pass (1–45 Hz) + IIR notch (50 Hz).
 * Designed for fs=512 Hz (NeuroSky TGAM / BrainLink raw EEG rate).
 */
function createEEGFilter(fs = 512) {
    const S2 = Math.SQRT2

    // High-pass at 1 Hz — removes DC offset and slow drift
    const kH = Math.tan(Math.PI * 1 / fs)
    const nH = 1 / (1 + S2 * kH + kH * kH)
    const hpf = createBiquad(
        nH, -2 * nH, nH,
        2 * (kH * kH - 1) * nH,
        (1 - S2 * kH + kH * kH) * nH
    )

    // Low-pass at 45 Hz — removes EMG and high-frequency noise
    const kL = Math.tan(Math.PI * 45 / fs)
    const nL = 1 / (1 + S2 * kL + kL * kL)
    const lpf = createBiquad(
        kL * kL * nL, 2 * kL * kL * nL, kL * kL * nL,
        2 * (kL * kL - 1) * nL,
        (1 - S2 * kL + kL * kL) * nL
    )

    // IIR notch at 50 Hz (Q=35, narrow band) — removes power-line interference
    const w0 = 2 * Math.PI * 50 / fs
    const cosW0 = Math.cos(w0)
    const alpha = Math.sin(w0) / (2 * 35)
    const a0n = 1 + alpha
    const notch = createBiquad(
        1 / a0n, -2 * cosW0 / a0n, 1 / a0n,
        -2 * cosW0 / a0n,
        (1 - alpha) / a0n
    )

    // Return the cascaded filter as a single function
    return (x) => notch(lpf(hpf(x)))
}

/** Returns a stateful byte-stream parser; calls onPacket(payloadBytes[]) for each valid packet. */
function createTGAMParser(onPacket) {
    let state = 'SYNC1', payloadLen = 0, payload = []
    return function (byte) {
        switch (state) {
            case 'SYNC1':
                if (byte === 0xAA) state = 'SYNC2'
                break
            case 'SYNC2':
                state = byte === 0xAA ? 'LENGTH' : 'SYNC1'
                break
            case 'LENGTH':
                if (byte === 0xAA) break // still syncing
                payloadLen = byte
                payload = []
                state = payloadLen === 0 ? 'CHECKSUM' : 'PAYLOAD'
                break
            case 'PAYLOAD':
                payload.push(byte)
                if (payload.length === payloadLen) state = 'CHECKSUM'
                break
            case 'CHECKSUM': {
                const expected = (~(payload.reduce((a, b) => a + b, 0) & 0xFF)) & 0xFF
                if (expected === byte) onPacket(payload)
                state = 'SYNC1'
                break
            }
        }
    }
}

/** Parses a validated TGAM payload into a data object with named fields. */
function parsePayload(payload) {
    const result = {}
    let i = 0
    while (i < payload.length) {
        const code = payload[i++]
        if (code >= 0x80) {
            if (i >= payload.length) break
            const len = payload[i++]
            if (i + len > payload.length) break
            if (code === CODE_RAW_EEG && len === 2) {
                let raw = (payload[i] << 8) | payload[i + 1]
                if (raw > 32767) raw -= 65536
                result.raw = raw
            } else if (code === CODE_EEG_POWER && len === 24) {
                // Build a named object so consumers don't need to know array indices
                result.bandPower = {}
                for (let b = 0; b < 8; b++) {
                    result.bandPower[BAND_NAMES[b]] =
                        (payload[i + b * 3] << 16) | (payload[i + b * 3 + 1] << 8) | payload[i + b * 3 + 2]
                }
            } else if (code === CODE_EXTENDED && len >= 1) {
                result.battery = payload[i]
                if (len >= 3) result.version = `${payload[i + 1]}.${payload[i + 2]}`
            }
            i += len
        } else {
            switch (code) {
                case CODE_POOR_SIGNAL: result.poorSignal = payload[i++]; break
                case CODE_ATTENTION: result.attention = payload[i++]; break
                case CODE_MEDITATION: result.meditation = payload[i++]; break
                default: i++; break
            }
        }
    }
    return result
}


const { spawn } = require('child_process')
const http = require('http')

const backendPath = app.isPackaged
    ? path.join(process.resourcesPath, 'backend', 'MindlinkBackend.exe')
    : path.join(__dirname, '..', 'newBackend', 'dist', 'MindlinkBackend', 'MindlinkBackend.exe')

let backendProcess = null

function startBackend() {
    backendProcess = spawn(backendPath, [], {
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
    })
    backendProcess.stdout.on('data', () => { })
    backendProcess.stderr.on('data', () => { })
    backendProcess.on('exit', () => { })
}

function waitForBackend(retries = 30, delayMs = 500) {
    return new Promise((resolve, reject) => {
        let attempts = 0
        const check = () => {
            http.get('http://localhost:8000/health', (res) => {
                if (res.statusCode < 500) { resolve(); return }
                retry()
            }).on('error', retry)
        }
        function retry() {
            attempts++
            if (attempts >= retries) { reject(new Error('Backend did not start in time')); return }
            setTimeout(check, delayMs)
        }
        check()
    })
}

app.on('will-quit', () => {
    if (backendProcess) backendProcess.kill()
})

// ─── Electron App ─────────────────────────────────────────────────────────────
let mainWin = null
let activePort = null

const createWindow = () => {
    mainWin = new BrowserWindow({
        width: 1200,
        height: 800,
        // Windows taskbar requires .ico; other platforms use the PNG
        icon: process.platform === 'win32'
            ? path.join(__dirname, 'icon.ico')
            : path.join(__dirname, 'src', 'assets', 'logo-no-text.png'),
        autoHideMenuBar: true,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            enableRemoteModule: true
        }
    })
    mainWin.loadFile(path.join(__dirname, 'dist', 'index.html'))
    // Tell a fresh renderer it starts disconnected (prevents stale status from previous sessions)
    mainWin.webContents.on('did-finish-load', () => {
        mainWin.webContents.send('eeg:connection-status', 'disconnected')
    })
    if (process.env.NODE_ENV === 'development') {
        mainWin.webContents.openDevTools()
    }
    return mainWin
}

// ─── Auto Updater ────────────────────────────────────────────────────────────
// Reads update metadata directly from the public GitHub releases repo.
// electron-builder publishes a latest.yml there automatically on each release.

function setupAutoUpdater() {
    if (!app.isPackaged) return   // skip in dev

    // No extra server needed — electron-updater fetches latest.yml from GitHub releases
    autoUpdater.setFeedURL({
        provider: 'github',
        owner: 'Mindspeller',
        repo: 'MindLink-Releases'
    })
    autoUpdater.autoDownload = true
    autoUpdater.autoInstallOnAppQuit = true

    autoUpdater.on('update-downloaded', () => {
        dialog.showMessageBox(mainWin, {
            type: 'info',
            title: 'Update Ready',
            message: 'A new version of Mindlink Analyzer has been downloaded.',
            detail: 'The update will be installed when you restart the application.',
            buttons: ['Restart Now', 'Later'],
            defaultId: 0
        }).then(({ response }) => {
            if (response === 0) autoUpdater.quitAndInstall(false, true)
        })
    })

    autoUpdater.on('error', () => { /* silent — update errors should not crash the app */ })

    // Check on launch, then every 4 hours
    autoUpdater.checkForUpdates()
    setInterval(() => autoUpdater.checkForUpdates(), 4 * 60 * 60 * 1000)
}

app.whenReady().then(async () => {
    startBackend()
    try {
        await waitForBackend(40, 500)
    } catch (e) {
        // Open anyway — user sees connection errors but app is usable
    }
    createWindow()
    setupAutoUpdater()
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
})

app.on('window-all-closed', () => {
    if (activePort && activePort.isOpen) activePort.close()
    if (process.platform !== 'darwin') app.quit()
})

// ─── IPC: list serial ports ───────────────────────────────────────────────────
ipcMain.handle('eeg:list-ports', async () => {
    if (!SerialPort) return { ports: [], error: 'serialport module not installed — run: npm install serialport && npx electron-rebuild' }
    try {
        const list = await SerialPort.list()
        return {
            ports: list.map(p => ({
                path: p.path,
                pnpId: p.pnpId || '',
                manufacturer: p.manufacturer || '',
                description: p.friendlyName || p.manufacturer || p.path || ''
            }))
        }
    } catch (err) {
        return { ports: [], error: err.message }
    }
})

// ─── IPC: connect to a port ───────────────────────────────────────────────────
ipcMain.handle('eeg:connect', async (event, portPath) => {
    if (!SerialPort) return { success: false, error: 'serialport module not installed' }
    if (activePort && activePort.isOpen) {
        await new Promise(resolve => activePort.close(() => resolve()))
    }
    try {
        mainWin.webContents.send('eeg:connection-status', 'connecting')
        let lastDataMs = Date.now()
        let silenceTimer = null
        activePort = new SerialPort({ path: portPath, baudRate: 115200, autoOpen: false })

        // Fresh filter state for each new connection (prevents transient bleed-over)
        const eegFilter = createEEGFilter()

        // Batch raw samples: collect and flush every 16 ms (~60 fps) instead of one IPC per sample.
        // Electron IPC can't sustain 512 individual sends/second without dropping.
        let rawBatch = []
        let batchTimer = setInterval(() => {
            if (rawBatch.length > 0 && mainWin && !mainWin.isDestroyed()) {
                mainWin.webContents.send('eeg:raw-data-batch', rawBatch)
                rawBatch = []
            }
        }, 16)

        const parseByte = createTGAMParser((payloadBytes) => {
            const data = parsePayload(payloadBytes)
            if (data.raw !== undefined) {
                // Apply bandpass (1–45 Hz) + notch (50 Hz) then batch
                rawBatch.push(Math.round(eegFilter(data.raw)))
            }
            if (data.poorSignal !== undefined || data.attention !== undefined) {
                mainWin.webContents.send('eeg:eeg-data', {
                    poorSignal: data.poorSignal ?? 200,
                    attention: data.attention ?? 0,
                    meditation: data.meditation ?? 0,
                    bandPower: data.bandPower ?? null,
                    battery: data.battery ?? null
                })
            }
            if (data.battery !== undefined) {
                mainWin.webContents.send('eeg:extend-data', {
                    battery: data.battery,
                    version: data.version || null
                })
            }
        })

        activePort.on('data', (chunk) => {
            lastDataMs = Date.now()
            for (const byte of chunk) parseByte(byte)
        })
        activePort.on('open', () => {
            lastDataMs = Date.now()
            // Watchdog: if no bytes received for 3 s, device has gone silent — treat as disconnected
            silenceTimer = setInterval(() => {
                if (Date.now() - lastDataMs > 3000) {
                    clearInterval(silenceTimer)
                    clearInterval(batchTimer)
                    mainWin.webContents.send('eeg:connection-status', 'disconnected')
                    if (activePort && activePort.isOpen) activePort.close(() => { })
                    activePort = null
                }
            }, 1000)
            mainWin.webContents.send('eeg:connection-status', 'connected')
        })
        activePort.on('close', () => {
            clearInterval(silenceTimer)
            clearInterval(batchTimer)
            mainWin.webContents.send('eeg:connection-status', 'disconnected')
            activePort = null
        })
        activePort.on('error', (err) => {
            clearInterval(silenceTimer)
            clearInterval(batchTimer)
            mainWin.webContents.send('eeg:connection-status', 'disconnected')
            activePort = null
        })

        await new Promise((resolve, reject) => activePort.open(err => err ? reject(err) : resolve()))
        return { success: true }
    } catch (err) {
        mainWin.webContents.send('eeg:connection-status', 'disconnected')
        activePort = null
        return { success: false, error: err.message }
    }
})

// ─── IPC: disconnect ──────────────────────────────────────────────────────────
ipcMain.handle('eeg:disconnect', async () => {
    if (activePort && activePort.isOpen) {
        await new Promise(resolve => activePort.close(() => resolve()))
    }
    // Explicitly tell the renderer it is disconnected (close event may not fire on manual disconnect)
    if (mainWin && !mainWin.isDestroyed()) {
        mainWin.webContents.send('eeg:connection-status', 'disconnected')
    }
    activePort = null
    return { success: true }
})
