# MindLink EEG Backend — Startup Guide

The Python backend owns the BrainLink serial connection, parses the TGAM
byte stream, filters the signal, and streams data to the Electron frontend
over a WebSocket.  Both pieces must be running at the same time.

---

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | ≥ 3.10 | `python --version` |
| pip | any recent | `pip --version` |
| Node.js | ≥ 18 | `node --version` |
| npm | ≥ 9 | `npm --version` |
| BrainLink device | — | plugged-in via USB or paired via Bluetooth |

---

## One-time setup

Open **two** terminals.  Do this once before the first run.

### Terminal 1 — Python backend

```powershell
cd newBackend

# Create a virtual environment (keeps dependencies isolated)
python -m venv .venv

# Activate it
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate          # macOS / Linux

# Install dependencies
pip install -r requirements.txt
```

### Terminal 2 — Electron frontend

```powershell
cd ElectronFrontEnd
npm install
```

---

## Starting the app (every run)

Always start the **backend first** so the WebSocket is ready before the
frontend loads.

### Step 1 — start the Python backend (Terminal 1)

```powershell
cd newBackend
.venv\Scripts\Activate.ps1          # skip if already active

uvicorn main:app --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> Add `--reload` during development to auto-restart on file changes:
> `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

### Step 2 — start the Electron frontend (Terminal 2)

```powershell
cd ElectronFrontEnd
npm run dev
```

The Electron window will open.  Navigate to the **Live EEG** page — the
chart will connect to `ws://localhost:8000/ws` automatically.

---

## REST API quick reference

The backend exposes these HTTP endpoints (useful for testing):

| Method | URL | Body | Description |
|---|---|---|---|
| `GET` | `/ports` | — | List detected serial ports |
| `POST` | `/connect` | `{"port": "COM3"}` | Open the BrainLink port |
| `POST` | `/disconnect` | — | Close the active port |
| `GET` | `/status` | — | Current connection status |

Test with curl:
```powershell
curl http://localhost:8000/ports
curl http://localhost:8000/status
curl -X POST http://localhost:8000/connect -H "Content-Type: application/json" -d '{"port":"COM3"}'
```

Or open the interactive docs in a browser: **http://localhost:8000/docs**

---

## WebSocket message format

All messages are JSON.  The frontend (`wsEegService.js`) handles these
automatically — this table is for debugging.

| `type` | Fields | Notes |
|---|---|---|
| `status` | `value`: `"connected"` \| `"disconnected"` \| `"connecting"` | Sent on every state change and to each new client on connect |
| `raw_batch` | `samples`: `number[]` | Filtered raw ADC values, flushed ~60 times/s |
| `eeg_data` | `poorSignal`, `attention`, `meditation`, `bandPower`, `battery` | Parsed TGAM scalar packet |
| `battery` | `level`: `0–100` | From BrainLink extended packet |
| `error` | `message`: string | Serial or device error |

---

## Port detection

The backend uses the same detection logic as the Python GUI:

1. **Windows** — matches by PnP hardware ID against known BrainLink serial numbers (`5C361634682F`, `5C3616346938`, `5C3616346838`, `5C3616327E59`)
2. **macOS / Linux** — matches by description keyword (`brainlink`, `neurosky`, `ftdi`, `silabs`, `ch340`) or device path (`/dev/tty.usbserial*`)

The frontend calls `GET /ports` and picks the best match automatically.
If auto-detection fails, check:
- The device is switched on and the LED is blinking
- On Windows: Device Manager → Ports (COM & LPT) shows the device
- On macOS: `ls /dev/tty.usb*` shows the device

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Address already in use` | Port 8000 is taken | `--port 8001` and update `BACKEND_HTTP` / `BACKEND_WS` in `wsEegService.js` |
| `serialport module not installed` | Old Electron path still active | Make sure the frontend is using `wsEegService.js`, not `EegConnectService.js` |
| Chart shows "No device connected" | Backend not running | Start `uvicorn` first, then reload the Electron app |
| Chart shows "Waiting for EEG data…" | Device not yet opened | Click **Scan Again** on the Live EEG page |
| `Permission denied` on serial port (Linux/macOS) | User not in `dialout` group | `sudo usermod -aG dialout $USER` then log out and back in |
| `pip install` fails on `uvicorn[standard]` | Missing C build tools | `pip install uvicorn` (without `[standard]`) — websocket support is still included |
