const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')

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
    console.warn('[EEG] serialport not available:', e.message)
}

// ─── TGAM Protocol Parser ─────────────────────────────────────────────────────
// NeuroSky / BrainLink byte codes
const CODE_POOR_SIGNAL = 0x02
const CODE_ATTENTION = 0x04
const CODE_MEDITATION = 0x05
const CODE_RAW_EEG = 0x81  // 2-byte int16 big-endian raw ADC
const CODE_EEG_POWER = 0x83  // 24-byte band powers (8 × uint24 big-endian)
const CODE_EXTENDED = 0x85  // BrainLink proprietary: byte[0]=battery%, byte[1-2]=fw version

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
                result.eegPower = []
                for (let b = 0; b < 8; b++) {
                    result.eegPower.push(
                        (payload[i + b * 3] << 16) | (payload[i + b * 3 + 1] << 8) | payload[i + b * 3 + 2]
                    )
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

// ─── Electron App ─────────────────────────────────────────────────────────────
let mainWin = null
let activePort = null

const createWindow = () => {
    mainWin = new BrowserWindow({
        width: 1200,
        height: 800,
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

app.whenReady().then(() => {
    createWindow()
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

        const parseByte = createTGAMParser((payloadBytes) => {
            const data = parsePayload(payloadBytes)
            if (data.raw !== undefined) {
                mainWin.webContents.send('eeg:raw-data', data.raw)
            }
            if (data.poorSignal !== undefined || data.attention !== undefined) {
                mainWin.webContents.send('eeg:eeg-data', {
                    poorSignal: data.poorSignal ?? 200,
                    attention: data.attention ?? 0,
                    meditation: data.meditation ?? 0,
                    eegPower: data.eegPower ?? null,
                    battery: data.battery ?? null   // include battery whenever it arrives in the same packet
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
                    mainWin.webContents.send('eeg:connection-status', 'disconnected')
                    if (activePort && activePort.isOpen) activePort.close(() => { })
                    activePort = null
                }
            }, 1000)
            mainWin.webContents.send('eeg:connection-status', 'connected')
        })
        activePort.on('close', () => {
            clearInterval(silenceTimer)
            mainWin.webContents.send('eeg:connection-status', 'disconnected')
            activePort = null
        })
        activePort.on('error', (err) => {
            clearInterval(silenceTimer)
            console.error('[EEG] serial error:', err.message)
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