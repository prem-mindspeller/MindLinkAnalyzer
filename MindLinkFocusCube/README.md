# MindLink Focus Cube

Separate browser test app for BrainLink raw EEG neurofeedback.

The backend uses `BrainLinkParser` only to parse serial packets and receive raw EEG callbacks. It does not use the parser-provided `attention` or `meditation` values for gameplay or visualization. Alpha, beta, and gamma values are calculated locally from raw samples using live feature extraction.

BrainLink/Macrotellect is treated as a single-channel time-series device. The brain graphic is not ERP source localization or anatomical activation mapping. The pink "prefrontal" activity is a sensor-region visual anchor for the frontal headset position.

## Setup

```powershell
cd M:\CODEBASE\MindLinkAnalyzer\MindLinkFocusCube
C:\Users\conta\anaconda3\envs\brainlink\python.exe -m pip install -r backend\requirements.txt
npm install
npm --prefix frontend install
npm --prefix frontend exec playwright install chromium
```

## Demo Mode

Runs without a headset:

```powershell
npm run dev
```

Open `http://127.0.0.1:5174`.

Standalone cyberpunk brain demo:

```text
http://127.0.0.1:5174/brain-cyberpunk-demo.html
```

That file is a complete single-file HTML/JavaScript demo using Three.js from a CDN and mock `window.currentAlpha` / `window.currentBeta` values.

## Device Mode

Runs against the BrainLink headset and falls back to demo if no device is found:

```powershell
npm run dev:backend:device
npm run dev:frontend
```

Use two terminals for device mode. The backend streams JSON frames at `ws://127.0.0.1:8765`.

Strict device mode fails instead of falling back to demo:

```powershell
npm run dev:backend:device:strict
```

Native parser requirement:

```powershell
C:\Users\conta\anaconda3\envs\brainlink\python.exe -c "import sys; sys.path.insert(0, r'M:\CODEBASE\MindLinkAnalyzer'); import BrainLinkParser.BrainLinkParser; print('native parser ok')"
```

If that import fails, the active Python environment cannot load `BrainLinkParser.pyd`. In that case, switch to the `brainlink` conda environment or rebuild/install the native parser for the active Python version. Protocol-only fallback is available for debugging, but native parser mode is the intended device path:

```powershell
npm run dev:backend:device:pure
```

When the backend is working you should see startup lines like:

```text
[FocusCube] Starting MindLink Focus Cube backend.
[FocusCube] Attention source: alpha
[FocusCube] WebSocket server listening on ws://127.0.0.1:8765
[FocusCube] Searching for BrainLink serial device...
```

If the frontend shows `device_warming`, the backend has opened the device and is waiting for enough raw samples to calculate bands. If it shows `demo`, the backend is using synthetic data because you started demo mode or device detection fell back.

## Attention Mapping

Default behavior matches the test requirement:

- Higher normalized alpha lifts the cube.
- Lower normalized alpha drops the cube.

Alternative mappings are available from the backend CLI:

```powershell
C:\Users\conta\anaconda3\envs\brainlink\python.exe -m backend.focuscube.server --attention-source inverse_alpha
C:\Users\conta\anaconda3\envs\brainlink\python.exe -m backend.focuscube.server --attention-source beta_alpha_ratio
```

## Cortex Model

The frontend tries to load:

```text
frontend/public/models/cortex.glb
```

If that file is missing, the app renders a procedural cortex-like fallback so the test app still works immediately.

## Verification

```powershell
C:\Users\conta\anaconda3\envs\brainlink\python.exe -m pytest backend\tests -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run verify:canvas
```

`verify:canvas` expects the dev app to be running at `http://127.0.0.1:5174`.
