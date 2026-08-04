# MindLink Analyzer — Electron Frontend

**Version:** 1.0.0  
**Author:** Augustine Asimhi  
**License:** ISC  
**Platform:** Windows (desktop application via Electron)

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Requirements](#2-system-requirements)
3. [Repository Structure](#3-repository-structure)
4. [Getting Started](#4-getting-started)
   - 4.1 [Prerequisites](#41-prerequisites)
   - 4.2 [Installation](#42-installation)
   - 4.3 [Running in Development Mode](#43-running-in-development-mode)
   - 4.4 [Running in Production Mode](#44-running-in-production-mode)
   - 4.5 [Building a Distributable](#45-building-a-distributable)
5. [Architecture](#5-architecture)
   - 5.1 [Technology Stack](#51-technology-stack)
   - 5.2 [Process Model](#52-process-model)
   - 5.3 [Application Flow (7-Step Session)](#53-application-flow-7-step-session)
6. [Module Reference](#6-module-reference)
   - 6.1 [Main Process (main.js)](#61-main-process-mainjs)
   - 6.2 [Services](#62-services)
   - 6.3 [Pages](#63-pages)
   - 6.4 [Components](#64-components)
   - 6.5 [Hooks](#65-hooks)
7. [Data Flow](#7-data-flow)
   - 7.1 [EEG Signal Pipeline](#71-eeg-signal-pipeline)
   - 7.2 [Session Storage Schema](#72-session-storage-schema)
   - 7.3 [Backend API Contract](#73-backend-api-contract)
   - 7.4 [Mindspeller REST API](#74-mindspeller-rest-api)
8. [Cognitive Tasks](#8-cognitive-tasks)
9. [Internationalisation](#9-internationalisation)
10. [Routing](#10-routing)
11. [Styling](#11-styling)
12. [Build Configuration](#12-build-configuration)
13. [Known Limitations](#13-known-limitations)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Overview

MindLink Analyzer is an **Electron + React desktop application** that guides a user through a standardised EEG cognitive-assessment session using a NeuroSky/BrainLink consumer-grade EEG headset.

The application:

- Discovers and connects to the EEG headset via a **local Python FastAPI backend** (`MindlinkBackend.exe`).
- Guides the user through **baseline calibration** (eyes-closed / eyes-open).
- Runs up to **13 cognitive tasks** across four neurological pathways.
- Sends the collected band-power samples to the Python backend for **statistical analysis**.
- Seeds the resulting report to the **Mindspeller REST API** for long-term storage and visualisation.

---

## 2. System Requirements

| Requirement | Minimum |
|---|---|
| OS | Windows 10 64-bit |
| Node.js | v18 LTS or later |
| npm | v9 or later |
| Python backend | `MindlinkBackend.exe` running on port 8000 |
| EEG Device | NeuroSky TGAM or BrainLink (Bluetooth/USB) |
| RAM | 4 GB |
| Display | 1280 × 720 |

> **Note:** The Python backend (`MindlinkBackend.exe`) must be built separately from the `newBackend/` sibling directory. In development mode the frontend expects the executable at `../newBackend/dist/MindlinkBackend/MindlinkBackend.exe` relative to this folder.

> **Spoken stimuli require Windows.** Tasks 1, 2, 4, 7 and 11 deliver their
> stimuli through the Web Speech API, which has no voices under Electron on
> Linux. See [Known Limitations](#13-known-limitations).

---

## 3. Repository Structure

```
ElectronFrontEnd/
├── main.js                        # Electron main process — app lifecycle, serial port, IIR filter, backend spawn
├── webpack.config.js              # Webpack 5 build config (target: electron-renderer)
├── package.json                   # npm manifest, scripts, electron-builder config
├── index.html                     # Electron loader template (points to dist/)
├── DOCUMENTATION.md               # This file
├── src/
│   ├── index.js                   # React entry point (ReactDOM.render)
│   ├── index.html                 # Webpack HTML template
│   ├── App.jsx                    # Root component — HashRouter + route definitions
│   ├── i18n.js                    # i18next initialisation (EN / NL)
│   ├── assets/                    # Static images and icons
│   ├── service/
│   │   ├── wsEegService.js        # WebSocket EEG client — state, events, auto-reconnect
│   │   ├── loginService.js        # JWT auth, token refresh, partner booking check
│   │   ├── analysisService.js     # POST /analyze + report seeding to Mindspeller API
│   │   └── authService.js        # (Legacy — currently unused)
│   ├── hooks/
│   │   └── useTaskRunner.js       # Task-execution state machine (countdown → phases → done)
│   ├── pages/
│   │   ├── home.jsx               # Landing page
│   │   ├── region.jsx             # Step 1 — server/data-region selection
│   │   ├── login.jsx              # Steps 2–3 — credentials + partner ID
│   │   ├── liveEegReding.jsx      # Step 4 — device discovery & connection
│   │   ├── BaselineCalibration1.jsx # Step 5 — 30 s eyes-closed + 30 s eyes-open
│   │   ├── TaskSelection.jsx      # Step 6 — task list + in-page task execution
│   │   ├── upload.jsx             # Step 7 — analysis trigger + report seeding
│   │   └── help.jsx               # Help accordion (accessible from any step)
│   ├── components/
│   │   ├── header.jsx             # Pre-login header (logo + language toggle)
│   │   ├── LoggedInHeader.jsx     # Post-login header (battery, signal, username)
│   │   ├── footer.jsx             # Copyright footer
│   │   ├── loginFormComponent.jsx # Email/password form
│   │   ├── partnerIdComponent.jsx # Partner ID input + booking verification
│   │   ├── StepInfoPopup.jsx      # Contextual step explanation overlay
│   │   ├── EegWaveform.jsx        # Canvas-based real-time EEG waveform
│   │   ├── AnalysisResultsPanel.jsx # Results visualisation (reserved)
│   │   ├── region/
│   │   │   ├── regionselectionCard.jsx  # Region picker UI
│   │   │   ├── stepsComponent.jsx       # 7-step progress indicator
│   │   │   └── warningComponent.jsx     # Pre-connection headset checklist
│   │   └── tasks/
│   │       ├── TaskRunner.jsx           # Shared task-execution UI wrapper
│   │       ├── AttentionFocusTask.jsx
│   │       ├── CognitiveLoadTask.jsx
│   │       ├── CuriosityTask.jsx
│   │       ├── DiverseThinkingTask.jsx
│   │       ├── EmotionFaceTask.jsx
│   │       ├── LanguageProcessingTask.jsx
│   │       ├── MentalMathTask.jsx
│   │       ├── MotorImageryTask.jsx
│   │       ├── NumFormTask.jsx
│   │       ├── OrderSurpriseTask.jsx
│   │       ├── ReappraisalTask.jsx
│   │       ├── VisualImageryTask.jsx
│   │       └── WorkingMemoryTask.jsx
│   ├── locales/
│   │   ├── en.json                # English translations
│   │   └── nl.json                # Dutch translations
│   └── styles/
│       ├── main.css               # Global styles, header, footer, steps
│       ├── home.css
│       ├── loginpage.css
│       ├── regionpage.css
│       ├── baselineCalibration.css
│       ├── liveEegReading.css
│       ├── taskSelection.css
│       ├── upload.css
│       ├── help.css
│       └── pathway.css
└── dist/                          # Generated by Webpack — do not edit manually
```

---

## 4. Getting Started

### 4.1 Prerequisites

1. **Node.js ≥ 18** — Download from [nodejs.org](https://nodejs.org).
2. **Python backend executable** — Build or obtain `MindlinkBackend.exe` and place it at:
   ```
   ../newBackend/dist/MindlinkBackend/MindlinkBackend.exe
   ```
   relative to this `ElectronFrontEnd/` folder. The backend must expose:
   - `GET  http://localhost:8000/health`
   - `GET  http://localhost:8000/ports`
   - `POST http://localhost:8000/connect`
   - `POST http://localhost:8000/disconnect`
   - `POST http://localhost:8000/analyze`
   - `WS   ws://localhost:8000/ws`

3. **EEG Headset** — A NeuroSky TGAM-based or BrainLink device paired via Bluetooth or connected over USB-serial.

---

### 4.2 Installation

```bash
# Clone or download the repository, then navigate to this folder
cd ElectronFrontEnd

# Install all npm dependencies
npm install
```

> If native modules fail to compile (e.g. `serialport`), rebuild them for Electron:
> ```bash
> npx electron-rebuild
> ```

---

### 4.3 Running in Development Mode

Development mode enables **hot reload** for the React renderer and opens Chrome DevTools automatically.

```bash
# Step 1 — Build the renderer bundle (watch mode) AND launch Electron simultaneously
npm run dev
```

This single command uses `concurrently` to:
1. Run `webpack --mode development --watch` to produce `dist/bundle.js`.
2. Wait for `dist/bundle.js` to exist (`wait-on`), then start Electron with `NODE_ENV=development`.

The Electron main process will:
- Spawn `MindlinkBackend.exe` and poll `http://localhost:8000/health` until it responds (up to 20 s).
- Open the browser window pointing at `dist/index.html`.
- Open Chrome DevTools in the renderer.

---

### 4.4 Running in Production Mode

Production mode uses a minified bundle and does not open DevTools.

```bash
# Step 1 — Build the renderer bundle (one-time, optimised)
npm run build

# Step 2 — Launch Electron
npm start
```

> Always run `npm run build` after pulling code changes before running `npm start`.

---

### 4.5 Building a Distributable

Creates a Windows NSIS installer under `dist/` using `electron-builder`.

```bash
npm run build          # Compile renderer
npx electron-builder   # Package into installer
```

The installer is configured in `package.json` under the `"build"` key:

| Setting | Value |
|---|---|
| App ID | `com.mindspeller.Mindlink` |
| Product name | `Mindlink Analyzer` |
| Windows target | NSIS installer |
| Icon | `icon.ico` |
| Extra resource | Python backend bundled into `resources/backend/` |

---

## 5. Architecture

### 5.1 Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Desktop shell | Electron | 40.7.0 |
| UI framework | React | 18.2.0 |
| Routing | React Router (HashRouter) | 7.x |
| Internationalisation | i18next + react-i18next | 26.x / 17.x |
| Build tool | Webpack | 5.88.0 |
| Transpiler | Babel (env + react presets) | 7.23.0 |
| Serial comms | SerialPort | 12.0.0 |
| Icons | FontAwesome (SVG core) | 7.2.0 |
| Packaging | electron-builder | 26.8.1 |

---

### 5.2 Process Model

```
┌─────────────────────────────────────────────────────────────────────┐
│  Electron Main Process (main.js — Node.js)                          │
│                                                                      │
│  ┌──────────────────┐   IPC (ipcMain/ipcRenderer)                  │
│  │  Serial Port     │◄──────────────────────────────┐              │
│  │  (SerialPort)    │                                │              │
│  └────────┬─────────┘                                │              │
│           │ TGAM byte stream                         │              │
│           ▼                                          │              │
│  ┌──────────────────┐                                │              │
│  │  IIR Filter      │  1–45 Hz bandpass              │              │
│  │  + TGAM Parser   │  50 Hz notch                   │              │
│  └────────┬─────────┘                                │              │
│           │ eeg:raw-data-batch / eeg:eeg-data         │              │
│           ▼                                          │              │
│  ┌─────────────────────────────────────────────────┐│              │
│  │  Python Backend  (MindlinkBackend.exe)           ││              │
│  │  http://localhost:8000   ws://localhost:8000/ws  ││              │
│  └──────────────────────────────────────────────────┘│              │
└─────────────────────────────────────────────────────│──────────────┘
                                                       │
┌─────────────────────────────────────────────────────▼──────────────┐
│  Electron Renderer Process (React — Webpack bundle)                 │
│                                                                      │
│  App.jsx (HashRouter)                                               │
│    ├── wsEegService.js  ◄── WebSocket ws://localhost:8000/ws        │
│    ├── loginService.js  ◄── Mindspeller REST API (JWT)              │
│    └── analysisService.js ► POST /analyze  ► Mindspeller seed API   │
└─────────────────────────────────────────────────────────────────────┘
```

- The **Main Process** owns native resources (serial port, child process).
- The **Renderer Process** is a standard React SPA that communicates with the Python backend exclusively over **WebSocket** (`wsEegService.js`) — not over Electron IPC — to decouple the signal pipeline from Electron.
- `nodeIntegration: true` / `contextIsolation: false` are set on the renderer to allow `require()` inside React (legacy pattern; no external content is loaded).

---

### 5.3 Application Flow (7-Step Session)

```
Home (/homePage)
  └─► Region Selection (/region)          ← Step 1
        └─► Login + Partner ID (/login)   ← Steps 2–3
              └─► Device Discovery        ← Step 4
                  (/liveReading)
                    └─► Baseline          ← Step 5
                        Calibration
                        (/baselineCalibration1)
                          └─► Task        ← Step 6
                              Selection
                              (/taskSelection)
                                └─► Analysis & ← Step 7
                                    Upload
                                    (/upload)
```

The `/help` route is always accessible via the header button regardless of the current step.

---

## 6. Module Reference

### 6.1 Main Process (`main.js`)

Responsibilities:

| Concern | Implementation |
|---|---|
| Backend spawn | `startBackend()` — spawns `MindlinkBackend.exe`, pipes stdout/stderr |
| Backend health | `waitForBackend(retries, delayMs)` — polls `GET /health` with retry |
| Window creation | `createWindow()` — 1200 × 800, auto-hide menu bar |
| Hot reload (dev) | `electron-reload` watches `__dirname` |
| Serial port list | IPC handler `eeg:list-ports` → `SerialPort.list()` |
| Serial connect | IPC handler `eeg:connect` → opens port at 115200 baud, creates filter |
| Serial disconnect | IPC handler `eeg:disconnect` |
| IIR filtering | `createEEGFilter(fs=512)` — cascaded biquad (HPF 1 Hz → LPF 45 Hz → notch 50 Hz) |
| TGAM parsing | `createTGAMParser(onPacket)` — byte-level state machine |
| Raw batching | Collects raw samples, flushes every 16 ms via `eeg:raw-data-batch` |
| App quit | Kills backend process on `will-quit` |

**IPC Channels**

| Channel | Direction | Payload |
|---|---|---|
| `eeg:list-ports` | Renderer → Main (invoke) | — |
| `eeg:connect` | Renderer → Main (invoke) | `portPath: string` |
| `eeg:disconnect` | Renderer → Main (invoke) | — |
| `eeg:connection-status` | Main → Renderer (send) | `'disconnected' \| 'connecting' \| 'connected'` |
| `eeg:raw-data-batch` | Main → Renderer (send) | `number[]` |
| `eeg:eeg-data` | Main → Renderer (send) | `{ poorSignal, attention, meditation, bandPower, battery }` |
| `eeg:extend-data` | Main → Renderer (send) | Additional parsed fields |

---

### 6.2 Services

#### `wsEegService.js`

Singleton class (`WsEegService`) that maintains a persistent WebSocket connection to the Python backend.

**Public API**

| Method | Returns | Description |
|---|---|---|
| `on(event, cb)` | `() => void` | Subscribe to an event; returns an unsubscribe function |
| `off(event, cb)` | `void` | Unsubscribe |
| `getStatus()` | `string` | `'disconnected' \| 'searching' \| 'connecting' \| 'connected'` |
| `getBattery()` | `number \| null` | Battery level 0–100 |
| `getPoorSignal()` | `number` | 0–200; 200 = headset not worn |
| `getAttention()` | `number` | eSense attention 0–100 |
| `getMeditation()` | `number` | eSense meditation 0–100 |
| `getBandPowers()` | `object \| null` | `{ delta, theta, lowAlpha, highAlpha, lowBeta, highBeta, lowGamma, midGamma }` |
| `getRawBuffer()` | `number[]` | Up to last 6144 filtered raw samples |
| `isConnected()` | `boolean` | `status === 'connected'` |
| `isWorn()` | `boolean` | `poorSignal < 200` |
| `isGoodSignal()` | `boolean` | `poorSignal < 25` |
| `fetchAllowedHwids()` | `Promise<string[]>` | Fetches approved device MAC addresses from Mindspeller API |
| `autoDetect(hwids)` | `Promise<string \| null>` | Calls `GET /ports` on backend to find matching device |
| `connect(portPath)` | `Promise<{ success, error? }>` | Tells backend to open the serial port |
| `disconnect()` | `void` | Tells backend to close the serial port |

**Events**

| Event | Payload | Fired when |
|---|---|---|
| `status` | `string` | Connection state changes |
| `raw` | `number` | Each raw EEG sample arrives |
| `eegData` | `object` | Full `eeg_data` packet received |
| `battery` | `number` | Battery level update |
| `bandPower` | `object` | Band powers updated |

**Reconnect behaviour:** On WebSocket close, the service schedules a reconnect after 2 seconds automatically.

---

#### `loginService.js`

Handles JWT-based authentication against the Mindspeller CAS REST API.

| Function / Method | Description |
|---|---|
| `loginUser(email, password, region)` | POST `/api/cas/token/login`; stores `jwtToken`, `jwtRefreshToken`, `loggedInUser`, `region` in `sessionStorage`; starts auto-refresh interval |
| `logout()` | Clears `sessionStorage`; stops refresh interval |
| `getToken()` | Returns current JWT access token |
| `getRegion()` | Returns `'en'` or `'nl'` |
| `refreshToken()` | POST `/api/cas/token/refresh`; updates stored token |
| `checkPartnerBooking(partnerId)` | GET `/api/cas/partners/bookings`; returns `{ hasBooking, pathwayType }` |

Token auto-refresh runs every **10 minutes**. On a 401 response anywhere in the app, the service logs the user out and redirects to the sign-up page.

---

#### `analysisService.js`

Orchestrates the final analysis and report submission.

| Export | Description |
|---|---|
| `runAnalysis()` | Loads baseline and task recordings from the durable IndexedDB store (`recordingStore.mjs`, which migrates legacy `calibrationData_*` / `taskData_*` Web Storage arrays); validates baseline presence, battery version and task completeness; POSTs baseline + tasks + `protocol_profile` + per-task metadata to `POST http://localhost:8000/analyze`; returns enriched per-task results |
| `runSingleTaskQualityCheck(taskId, samples, opts)` | Re-uses `POST /analyze` for one just-completed task to drive the post-task quality popup. Does not write report data and does not affect the upload envelope |
| `seedReport(email, protocolType, analysisResults)` | Serializes the backend's `neuroprofile_feature_export` (`reportDocument.mjs`), compresses it into the envelope described in `docs/report_compression_contract.md` (`reportEnvelope.mjs`), and POSTs it to `POST /api/cas/eeg-reports/seed` with the sha256 and size metadata; retries once on 401 after token refresh |

---

### 6.3 Pages

| Route | Component | Purpose |
|---|---|---|
| `/homePage` | `home.jsx` | Hero landing page with feature list |
| `/region` | `region.jsx` | Server/data-jurisdiction selector (Step 1) |
| `/login` | `login.jsx` | Login form + partner ID (Steps 2–3) |
| `/liveReading` | `liveEegReding.jsx` | Device auto-detection + waveform preview (Step 4) |
| `/baselineCalibration1` | `BaselineCalibration1.jsx` | 30 s EC + 30 s EO recording with modal countdown (Step 5) |
| `/taskSelection` | `TaskSelection.jsx` | Task list filtered by pathway; in-page task execution (Step 6) |
| `/upload` | `upload.jsx` | Runs analysis, displays results, seeds report (Step 7) |
| `/help` | `help.jsx` | Accordion FAQ and hardware setup guide |

---

### 6.4 Components

| Component | Description |
|---|---|
| `header.jsx` | Pre-login header — logo, language toggle (EN/NL), help button |
| `LoggedInHeader.jsx` | Post-login header — battery %, signal quality indicator, username, logout |
| `footer.jsx` | Copyright footer |
| `loginFormComponent.jsx` | Controlled email + password form with validation feedback |
| `partnerIdComponent.jsx` | Partner ID input; calls `loginService.checkPartnerBooking()` |
| `StepInfoPopup.jsx` | Modal overlay explaining the current step |
| `EegWaveform.jsx` | `<canvas>`-based waveform; subscribes to `wsEegService` raw events; renders last 2048 samples at ≈ 60 fps |
| `AnalysisResultsPanel.jsx` | Reserved visualisation panel (not yet wired into upload page) |
| `region/regionselectionCard.jsx` | Clickable region card |
| `region/stepsComponent.jsx` | 7-step progress bar (completed / active / upcoming states) |
| `region/warningComponent.jsx` | Pre-connection headset preparation checklist |
| `tasks/TaskRunner.jsx` | Shared task shell: progress bar, instruction text, phase-based layout |
| `tasks/*.jsx` | Individual task components — define phase sequences consumed by `useTaskRunner` |

---

### 6.5 Hooks

#### `useTaskRunner(taskConfig)`

State machine hook that drives any cognitive task.

**Phases** are defined per task as an array of objects:

```js
{
  type: 'cue' | 'task' | 'viewing' | 'thinking' | 'get_ready' | 'wait' | 'video' | 'rest',
  duration: number,       // seconds
  record: boolean,        // whether to collect raw EEG samples during this phase
  label?: string,         // display text
}
```

**Hook Return Value**

| Field | Type | Description |
|---|---|---|
| `phase` | `string` | Current phase type |
| `phaseIndex` | `number` | Index into the phases array |
| `elapsed` | `number` | Seconds elapsed in current phase |
| `progress` | `number` | 0–1 fraction of current phase completed |
| `isRecording` | `boolean` | Whether samples are being collected |
| `isDone` | `boolean` | All phases completed |
| `start()` | `function` | Begins the 5-second countdown then runs phases |
| `samples` | `number[]` | Collected raw EEG samples for recording phases |

Audio cues:
- **Countdown:** 800 Hz beep each second.
- **Phase completion / task done:** 1000 Hz beep.

---

## 7. Data Flow

### 7.1 EEG Signal Pipeline

```
BrainLink/NeuroSky headset
      │ Bluetooth or USB-serial (115200 baud)
      ▼
Python Backend (serial port owner)
      │ TGAM byte stream parsed
      │ IIR filter applied (1–45 Hz BP + 50 Hz notch, fs = 512 Hz)
      ▼
WebSocket  ws://localhost:8000/ws
      │ JSON messages: raw_batch, eeg_data, status, battery, error
      ▼
wsEegService.js (renderer process)
      │ _rawBuffer  (ring buffer, max 6144 samples ≈ 12 s at 512 Hz)
      │ event listeners notified
      ▼
React components / useTaskRunner hook
      │ Samples accumulated in task recording phases
      ▼
IndexedDB  (run-scoped task and EC/EO baseline recordings)
sessionStorage  (small run ID, completion and baseline manifest only)
      ▼
analysisService.runAnalysis()  →  POST http://localhost:8000/analyze
      ▼
analysisService.seedReport()   →  POST https://<region>.mindspeller.com/api/cas/eeg-reports/seed
```

**IIR Filter Design** (fs = 512 Hz, Direct-Form I biquads):

| Stage | Type | Frequency | Purpose |
|---|---|---|---|
| HPF | 2nd-order Butterworth | 1 Hz | Remove DC offset and slow drift |
| LPF | 2nd-order Butterworth | 45 Hz | Remove EMG and high-frequency noise |
| Notch | IIR Notch (Q = 35) | 50 Hz | Remove power-line interference |

---

### 7.2 Recording and Session Storage Schema

Large raw EEG recordings live in IndexedDB under a run-scoped identifier. Only
small authentication, routing and completion values remain in
`window.sessionStorage`. Legacy raw Web Storage values are migrated lazily and
removed only after their durable copy commits.

| Key | Type | Set by | Used by |
|---|---|---|---|
| `jwtToken` | `string` | `loginService` | All API calls |
| `jwtRefreshToken` | `string` | `loginService` | `loginService.refreshToken()` |
| `loggedInUser` | `string` (email) | `loginService` | `upload.jsx`, `seedReport` |
| `region` | `'en' \| 'nl'` | `loginService` | All API base URLs |
| `language` | `'en' \| 'nl'` | `header.jsx` | `i18n.js` |
| `partnerId` | `string` | `partnerIdComponent` | `seedReport` |
| `pathwayType` | `string` | `login.jsx` | `TaskSelection.jsx` |
| `recordingStoreSessionId` | `string` | `recordingStore` | Namespaces task and baseline recordings |
| `baselineCalibration` | compact JSON metadata | `BaselineCalibration1` | Completion/UI compatibility manifest |
| `calibrationData_eyes_closed/open` | legacy JSON arrays | Older releases | Lazily migrated, then removed |
| `completedTasks` | `JSON string[]` | `TaskSelection` | `runAnalysis`, `upload` |
| `taskData_<taskId>` | legacy JSON arrays | Older releases | Lazily migrated, then removed |

IndexedDB database `mindlink-analyzer-recordings`, object store
`taskRecordings`, contains both task records and namespaced
`baseline::eyes_closed` / `baseline::eyes_open` records. Cleanup deletes the
entire active run namespace, including interrupted recordings.

---

### 7.3 Backend API Contract

All calls go to `http://localhost:8000` (Python FastAPI).

| Method | Path | Request | Response |
|---|---|---|---|
| `GET` | `/health` | — | `200 OK` |
| `GET` | `/ports` | — | `{ ports: [{ path, hwid, description }] }` |
| `POST` | `/connect` | `{ port: string }` | `{ success: bool, error?: string }` |
| `POST` | `/disconnect` | — | `{ success: bool }` |
| `POST` | `/analyze` | `{ baseline: { eyes_closed: number[], eyes_open: number[] }, tasks: { [id]: number[] } }` | See analysis result schema below |
| `WS` | `/ws` | — | JSON messages (see wsEegService) |

**Analysis Result Schema**

```jsonc
{
  "baseline_kept": 2000,
  "baseline_rejected": 100,
  "ec_samples_raw": 2100,
  "ec_median_mad": 12.5,
  "per_task": {
    "<taskId>": {
      "sample_count": 1800,
      "summary": {
        "fisher":    { "km_p": 0.03, "significant": true },
        "sum_p":     { "perm_p": 0.04, "significant": true },
        "composite": { "score": 0.72 },
        "effect_size_mean": 0.45
      },
      "analysis": {
        "delta":    { "task_mean": 12000 },
        "theta":    { "task_mean": 8000 },
        "lowAlpha": { "task_mean": 5000 }
        // … highAlpha, lowBeta, highBeta, lowGamma, midGamma
      }
    }
  }
}
```

---

### 7.4 Mindspeller REST API

Base URLs:
- English region: `https://en.mindspeller.com`
- Dutch region: `https://nl.mindspeller.com`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/cas/token/login` | None | Obtain JWT tokens |
| `POST` | `/api/cas/token/refresh` | Bearer (refresh token) | Refresh access token |
| `GET` | `/api/cas/partners/bookings` | Bearer (access token) | Check partner booking / pathway |
| `POST` | `/api/cas/eeg-reports/seed` | `X-Authorization: Bearer <token>` | Upload EEG report |

---

## 8. Cognitive Tasks

The app runs the 12-task **optimized battery** (`task_battery_optimization_2.0.0-candidate.1`).
The pathway-specific task sets described in earlier revisions of this document
no longer exist — tasks are now gated by *session depth*, not partner pathway.

Task identity, durations, phase plans, stimulus forms, rubrics and thresholds
are data in the versioned protocol profile rather than constants in the runner:

| Concern | Source of truth |
|---|---|
| Task ids, phases, durations, thresholds | [optimizedBatteryProfile.mjs](src/components/tasks/optimizedBatteryProfile.mjs) |
| Stimulus forms and scheduling | [optimizedBatteryConfig.mjs](src/components/tasks/optimizedBatteryConfig.mjs) |
| Per-task UI | [src/components/tasks/optimized/](src/components/tasks/optimized/) |
| Rationale for every duration deviation | [docs/Task_Battery_Optimization_Implementation.md](../docs/Task_Battery_Optimization_Implementation.md) |
| Per-task evidence and ability claims | [docs/Optimized_Task_Battery_Traceability_Reference.md](../docs/Optimized_Task_Battery_Traceability_Reference.md) |

Durations are deliberately **not** duplicated here: the frontend profile and the
backend's `TASK_RECORDING_DURATIONS_SECONDS` must already agree exactly (a
mismatch makes the backend reject the whole `protocol_profile`), and a third
copy in prose is the one that silently goes stale.

Sessions are cumulative — session 1 runs tasks 3, 2, 1, 4; session 2 adds 6, 7
and the eyes-open block (9, 5, 8); session 3 adds 11, 10 and 12. The eyes-open
fixation baseline is required before any eyes-open task.

---

## 9. Internationalisation

The app supports **ten languages** via `i18next`: English (`en`), Dutch (`nl`),
German (`de`), French (`fr`), Spanish (`es`), Italian (`it`), Portuguese (`pt`),
Hindi (`hi`), Arabic (`ar`) and Japanese (`ja`).

- Configuration: [src/i18n.js](src/i18n.js)
- Translations: one file per language in [src/locales/](src/locales/)
- Language is stored in `sessionStorage.language` and applied on app startup.
- The header language toggle switches the active language at runtime via `i18n.changeLanguage()`.

Translation key namespaces: `header`, `home`, `region`, `login`, `baseline`, `tasks`, `upload`, `help`.

Dynamic keys follow the pattern:
- `taskMeta.<taskId>.name` — Display name
- `taskMeta.<taskId>.description` — Short description
- `taskContent.<taskId>.intro*` — In-task instruction lines

---

## 10. Routing

React Router v7 (`HashRouter`) is used. Hash-based routing is required because Electron loads `file://` URLs and a standard `BrowserRouter` would not handle page reloads correctly.

| Path | Component | Notes |
|---|---|---|
| `/` | Redirect | Redirects to `/homePage` |
| `/homePage` | `HomePage` | |
| `/region` | `RegionPage` | |
| `/login` | `LoginPage` | |
| `/liveReading` | `LiveEegReading` | |
| `/baselineCalibration1` | `BaselineCalibration1` | |
| `/taskSelection` | `TaskSelection` | |
| `/upload` | `UploadPage` | |
| `/help` | `HelpPage` | |

---

## 11. Styling

Global design tokens (defined in `src/styles/main.css`):

| Token | Value | Usage |
|---|---|---|
| Primary | `#3b5bdb` (indigo) | Buttons, links, active states |
| Accent | `#6c63ff` (purple) | Gradients, highlights |
| Success | `#059669` (emerald) | Connected / good signal indicators |
| Warning | `#d97706` (amber) | Caution states |
| Neutral | `#e2e8f0` → `#64748b` | Backgrounds, borders, muted text |

Component design conventions:
- Cards use 10–16 px border radius with box shadows.
- Buttons use gradient backgrounds with hover lift (`transform: translateY(-1px)`).
- Step indicators use icon badges (checkmark / number / lock).
- Typography: Segoe UI, 14–26 px headings.

---

## 12. Build Configuration

### Webpack (`webpack.config.js`)

| Setting | Value |
|---|---|
| Entry | `./src/index.js` |
| Output | `./dist/bundle.js` |
| Target | `electron-renderer` |
| Loaders | `babel-loader` (JS/JSX), `style-loader + css-loader` (CSS), `asset/resource` (images) |
| Plugins | `HtmlWebpackPlugin` (template: `src/index.html`, output: `dist/index.html`) |
| Source maps | `source-map` |

### npm Scripts

| Script | Command | Purpose |
|---|---|---|
| `start` | `electron .` | Launch packaged/built app |
| `dev` | `concurrently webpack-watch + electron` | Development with hot reload |
| `build` | `webpack --mode production` | Optimised one-time build |
| `test` | *(not implemented)* | Placeholder |

---

## 13. Known Limitations

- **Windows only** — The Python backend is packaged as a `.exe`. macOS/Linux builds are not supported without modifying the `extraResources` path and build target.
- **Spoken stimuli are silent under Electron on Linux** — Electron does not ship
  Chromium's speech-dispatcher integration, so the Web Speech API exists but has
  no voices. Verified on Electron 40.10.6: `window.speechSynthesis` and
  `SpeechSynthesisUtterance` are present, `getVoices()` returns `0`, and
  `speak()` fires `onerror` with `synthesis-failed`. This does not depend on the
  host — a working system speech stack (`speech-dispatcher` + `espeak-ng`, with
  `spd-say` producing audio) does not change it, and neither does the
  `--enable-speech-dispatcher` Chromium switch. Windows is unaffected because
  Chromium uses SAPI there.
  - *Affected tasks:* 1, 2, 4, 7 (the "Update"/"Switch" cues) and 11 (the
    passage). Task 3 is tones-only and unaffected.
  - *Expected signature:* countdown and tone stimuli still play, because those
    are WebAudio oscillators on a separate code path. Hearing beeps but no voice
    is this limitation, not a broken audio device.
  - *No invalid data results.* The failed utterance enters the audio delivery
    audit, forcing `protocol_complete: false`, so the backend marks the attempt
    protocol-invalid and unscorable rather than scoring undelivered stimuli.
  - *Remedy, when required:* the audio profile already supports a
    `premixed_audio_asset` source mode, and `speak()` resolves assets globally,
    per form or per stimulus key. Pre-rendered audio files therefore fix Linux
    through profile data alone, with no task-engine change — the same step the
    battery needs for calibrated production audio (see
    `docs/Task_Battery_Optimization_Implementation.md`).
- **Single language server regions** — Only the English (`en`) region is selectable in the UI; the Dutch region card is visible but locked.
- **Test script wiring** — Automated `.test.mjs` contract/unit tests exist, but
  the package-level `npm test` script is still a placeholder; run them with
  Node's test runner until that script is wired up.
- **`nodeIntegration: true`** — The renderer has full Node.js access. This is acceptable for a local desktop app with no external content but would be a security concern in a web context.
- **Run recovery after full window close** — Raw EEG is durable in IndexedDB,
  but the active run identifier is session-scoped. Reloading the current window
  is supported; recovering a run after fully closing the Electron window is not
  yet implemented.
- **`AnalysisResultsPanel` unused** — The component is implemented but not wired into the upload page.
- **`authService.js` unused** — Imported but not consumed anywhere; kept for future use.

---

## 14. Troubleshooting

### App opens but shows "Backend not available" or connection errors

- Ensure `MindlinkBackend.exe` is present at `../newBackend/dist/MindlinkBackend/MindlinkBackend.exe`.
- Confirm port 8000 is not already in use: `netstat -ano | findstr :8000`.
- Check the Electron console (`Ctrl+Shift+I` in dev mode) for `[Backend]` log lines.

### EEG device not found during auto-detection

- Pair the BrainLink device in Windows Bluetooth settings before launching the app.
- Check that the device's MAC address appears in `KNOWN_HWIDS` in `wsEegService.js` or matches a name in `KNOWN_NAMES`.
- Try connecting manually: select the COM port from the device list.

### `serialport` fails to load / native module error

```bash
npx electron-rebuild
```

Run this after `npm install` whenever Electron or Node.js versions change.

### Webpack build fails with Babel errors

Ensure you are using **Node.js ≥ 18**. Delete `node_modules/` and run `npm install` again.

### Login returns "Incorrect email or password"

- Verify you have a valid Mindspeller account at `https://en.mindspeller.com`.
- Confirm the region selector matches your account's data region.

### Analysis returns "No baseline data found"

The required matched baseline must be completed in the active battery run.
Reloading the same Electron window retains its session identifier and can load
the durable IndexedDB baseline; fully closing the window retires that active
run context.

---
