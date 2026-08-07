# MindRove 4-Channel Integration Evaluation Notes

Date: 2026-05-26

This document summarizes the MindRove integration changes made to replace the
BrainLink-first single-channel acquisition path with a MindRove 4-channel raw
EEG path for FP1, FP2, O1, and O2, while preserving the existing EEG report
generation strategy and feature schema.

## Scope

The change updates the active Electron plus FastAPI flow:

- Backend: `newBackend/main.py`
- MindRove adapter: `newBackend/mindrove_device.py`
- Backend dependencies: `newBackend/requirements.txt`
- Frontend WebSocket service: `ElectronFrontEnd/src/service/wsEegService.js`
- Baseline recording: `ElectronFrontEnd/src/pages/BaselineCalibration1.jsx`
- Task recording: `ElectronFrontEnd/src/hooks/useTaskRunner.js`
- Live waveform display: `ElectronFrontEnd/src/components/EegWaveform.jsx`
- Regression tests: `tests/test_newbackend_analysis_fixes.py`
- MindRove adapter tests: `tests/test_mindrove_device.py`
- Standalone capture tests: `tests/test_mindrove_terminal_capture.py`

## MindRove SDK Acquisition

Added `newBackend/mindrove_device.py` as a small adapter around the official
MindRove SDK.

The adapter:

- Imports `BoardShim`, `MindRoveInputParams`, `BoardIds`, and
  `MindroveConfigMode` from `mindrove.board_shim`.
- Uses `BoardIds.MINDROVE_WIFI_BOARD`.
- Constructs the SDK `BoardShim` with the configured MindRove input parameters
  before resolving board metadata. This mirrors the standalone capture script
  and avoids the SDK performing a premature board-info initialization before
  the real Wi-Fi session is opened.
- Resolves `BoardShim.get_battery_channel()` and updates the backend battery
  state from the last finite value in that SDK data row.
- Prepares and starts a BoardShim session.
- Switches the board into EEG mode with `MindroveConfigMode.EEG_MODE`.
- Reads board data through the SDK buffer.
- Resolves the EEG rows for FP1, FP2, O1, and O2 by channel name when
  available. If the SDK descriptor does not provide usable names, the backend
  starts from the first four SDK EEG rows and then auto-selects the first four
  active rows by per-row signal variance. This matches the standalone hardware
  test where rows `0,1,2,3` carried the four live EEG signals and rows
  `4,5,6,7` were all-zero inactive rows.
- Converts SDK matrix output into per-sample dictionaries:

```json
{ "fp1": 0.0, "fp2": 0.0, "o1": 0.0, "o2": 0.0 }
```

The adapter also supports optional environment overrides:

```powershell
$env:MINDROVE_IP_ADDRESS = "192.168.x.x"
$env:MINDROVE_IP_PORT = "12345"
$env:MINDROVE_TIMEOUT = "15"
$env:MINDROVE_SERIAL_PORT = "COM9"
$env:MINDROVE_EEG_ROWS = "0,1,2,3"
```

If these are not set, the adapter uses the same defaults as
`MindLinkFocusCube`: `192.168.4.1:4210` with a 10 second SDK timeout.
`MINDROVE_EEG_ROWS` is optional. Leave it unset, or set it to `auto`, to use
active-row detection. Set it only when a specific MindRove unit or SDK version
requires a fixed row map such as `0,1,4,5`.

## Backend Device Flow

`newBackend/main.py` now exposes MindRove as the default EEG device.

Important behavior:

- `GET /ports` always includes a MindRove virtual device:

```json
{
  "path": "mindrove://wifi",
  "pnpId": "MINDROVE_WIFI",
  "manufacturer": "MindRove",
  "description": "MindRove Wi-Fi EEG (FP1, FP2, O1, O2)",
  "deviceType": "mindrove",
  "available": true,
  "channels": ["fp1", "fp2", "o1", "o2"],
  "samplingRate": 500
}
```

- `POST /connect` defaults to `mindrove://wifi` when no port is supplied.
- `POST /connect` with `{"port":"mindrove://wifi"}` starts the MindRove
  reader thread.
- Passing a serial port such as `{"port":"COM3"}` still uses the legacy serial
  path.
- The legacy BrainLink SDK import is now lazy, so importing the backend module
  does not print startup noise during tests.

The MindRove reader broadcasts two streams:

- `raw_multi_batch`: four-channel samples for recording and analysis.
- `raw_batch`: scalar aggregate samples for the existing waveform display.

This keeps the UI waveform simple while ensuring recordings contain the real
four-channel data.

The reader now drains the MindRove SDK buffer on each loop instead of reading a
small fixed slice. If the adapter changes the selected EEG rows after active-row
detection, the backend emits a fresh `device_info` message and resets the live
filters so filter state from the old row mapping does not contaminate the new
mapping. Signal quality windows are sized from the actual sample rate rather
than the legacy fixed `1000` sample constant.

`POST /connect` is also idempotent while an existing reader is already
connecting or connected to the same MindRove target. This prevents frontend
retries from creating a second `MindroveWifi` SDK instance in the same backend
process.

Backend terminal diagnostics are enabled by default. Set
`EEG_DEBUG_LOGS=0` to silence them, or `EEG_ANALYSIS_VERBOSE=1` to include
lower-level statistical diagnostic messages. The normal logs include:

- `/connect` request target and idempotent reconnect handling.
- MindRove sample rate, selected SDK rows, and stream sample counts.
- Per-second stream health and raw QC status.
- `/analyze` baseline/task raw sample counts and sample shape.
- Feature-row counts, QC counters, montage usage, and neuroprofile export keys.

Live MindRove worn/not-worn status now uses the same raw EEG variance gate as
the standalone capture tool. The backend requires four active selected EEG rows
by default before reporting a good signal, then applies the older spectral QC
only as secondary artifact/noise context. This prevents a floating aggregate
signal from flipping the UI to Good while the headset is not worn.

## Analysis Pipeline Changes

The previous raw path expected one scalar time series. The new raw path accepts
MindRove samples shaped as dictionaries with FP1, FP2, O1, and O2.

The reporting algorithms were not replaced. The change only adapts the input
conversion layer so the existing report logic still receives the same feature
dict shape.

Key details:

- The default MindRove sample rate is `500 Hz`, but analysis windows are now
  derived as `round(2 * fs)`. This keeps the validated two-second window design
  without assuming a fixed sample count when the device reports a different
  sample rate.
- Each channel is converted through the existing raw EEG feature extractor.
- Channel-level feature rows are projected through a sparse-montage layer:
  - frontal region: `Fp1/Fp2`
  - occipital region: `O1/O2`
- Task-specific regional weighting is applied before the existing statistics:
  - visual/imagery/colour/shape tasks emphasize occipital evidence
  - attention/load/executive tasks emphasize frontal evidence
  - emotion/reappraisal/curiosity tasks use a mixed frontal-occipital profile
  - other tasks use a balanced profile
- The public output feature schema remains unchanged.
- No channel-prefixed features such as `fp1_alpha_power`, and no public
  region-prefixed features such as `occipital_alpha_power`, are sent into the
  existing statistical report path.
- Existing report-level statistics, feature selection, task comparison,
  baseline comparison, and neuroprofile export logic remain intact.

Baseline QC behavior:

- A baseline window is accepted if at least one channel passes QC.
- Flat or noisy channels inside an otherwise usable four-channel window are
  ignored for that window.
- A baseline window is rejected only when all channels fail QC.
- If all four channels are flat, the window is counted as `flatline`.

Task samples are converted to the same feature schema using the task's montage
profile. For a visual task, both task and baseline windows are converted through
the occipital-heavy profile. For an attention task, both task and baseline
windows are converted through the frontal-heavy profile. This prevents a task
from being compared against a baseline computed with a different regional
assumption.

The feature pipeline now keeps the neuroprofile export structure intact while
making the upstream evidence more montage-aware:

- Visual/imagery/colour/shape windows require usable occipital evidence.
- Attention/load/executive windows require usable frontal evidence.
- Mixed tasks require at least one frontal and one occipital channel.
- When both channels in the task-primary pair are available, their raw-window
  agreement is checked before the row is allowed into task evidence. For
  example, visual imagery can use one clean occipital channel if the paired
  channel fails QC, but if both O1 and O2 are present and strongly disagree,
  that window is rejected as montage artifact.
- Feature rows carry underscore-prefixed internal agreement/confidence fields
  such as `_frontal_channel_agreement`, `_occipital_channel_agreement`,
  `_primary_channel_agreement`, and `_primary_region_confidence`. These fields
  are not selected as public inference features, but they allow QC and
  traceability code to know whether the evidence came from a reliable regional
  pair.
- Spatial contrast features are computed as normal feature metrics:
  `posterior_anterior_alpha`, `posterior_anterior_beta`,
  `occipital_alpha_advantage`, `frontal_attention_advantage`,
  `front_occipital_alpha_ratio`, and `front_occipital_beta_ratio`.
- Duplicate raw/derived power variants are grouped before inference so
  `*_power_raw` and `*_peak_amp` do not independently inflate the same
  physiological band change when `*_power` is already present.
- Effect-size and percent-change fallbacks remain visible as observations, but
  no longer set `significant_change` by themselves. Neuroprofile support now
  requires the statistical gate rather than treating fallback effects as the
  same class of evidence.
- Gamma features remain visible, but sparse-montage gamma is conservative:
  even when a gamma row passes the statistical gate, it is demoted from
  `significant_change` unless the EMG/high-frequency guard is clean, the
  task-primary regional pair has good agreement, and at least one non-gamma
  feature also supports the task.

The neuroprofile export is also enriched additively with montage metadata:

```json
{
  "montage": {
    "device": "MindRove",
    "channels": ["Fp1", "Fp2", "O1", "O2"],
    "regions": {
      "frontal": ["Fp1", "Fp2"],
      "occipital": ["O1", "O2"]
    }
  },
  "channel_quality": {},
  "regional_reliability": {},
  "primary_evidence_region": "task_specific",
  "multi_channel_gain": {
    "used_frontal_consensus": true,
    "used_occipital_evidence": true,
    "used_spatial_contrast": true,
    "fallback_to_single_channel": false
  }
}
```

These fields do not change the top-level report structure. They add traceability
for where the evidence came from.

## Frontend Recording Changes

`wsEegService.js` now understands:

- `raw_multi_batch`
- `device_info`
- `raw_batch`

The service keeps:

- `getRawBuffer()` for scalar display samples.
- `getRawMultiBuffer()` for FP1/FP2/O1/O2 samples.
- `getDeviceInfo()` for live device metadata.

Auto-detect now prefers the MindRove virtual device when it is available.

Baseline calibration and task recording now subscribe to `rawMulti` first. If
no four-channel stream is active, they fall back to scalar `raw`. This preserves
compatibility with old serial streams but uses four-channel MindRove samples
when MindRove is connected.

The live EEG page now waits for the backend WebSocket status to become
`connected` after posting `/connect`. If the backend accepts the request but the
reader falls back to `disconnected`, the page retries the same detected MindRove
target automatically instead of requiring the user to press Reconnect.

## How To Run Tests

Run commands from the repository root:

```powershell
cd M:\CODEBASE\MindLinkAnalyzer
```

### Backend regression tests

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
pytest tests\test_newbackend_analysis_fixes.py -q
```

Expected result:

```text
all tests passed
```

### MindRove adapter and standalone capture tests

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
pytest tests\test_mindrove_device.py tests\test_mindrove_terminal_capture.py -q
```

These tests cover SDK descriptor handling, active EEG row auto-selection,
explicit row override with `MINDROVE_EEG_ROWS`, full-buffer reads, terminal
contact-state logic, and live-plot data preparation.

### Neuroprofile/report traceability tests

Most traceability tests can be run with:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
pytest tests\test_neuroprofile_traceability.py -q -k "not analyze_existing_keys_preserved"
```

Expected result:

```text
44 passed, 1 deselected
```

The deselected test uses `fastapi.testclient`, which requires `httpx` in the
current environment. To run the full file:

```powershell
python -m pip install httpx
$env:PYTHONDONTWRITEBYTECODE = "1"
pytest tests\test_neuroprofile_traceability.py -q
```

### Backend syntax check

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -c "import ast, pathlib; files=['newBackend/main.py','newBackend/mindrove_device.py']; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8'), filename=f) for f in files]; print('python ast ok')"
```

### Frontend syntax check

```powershell
cd ElectronFrontEnd
node -e "const fs=require('fs'); const babel=require('@babel/core'); const files=['src/service/wsEegService.js','src/pages/BaselineCalibration1.jsx','src/hooks/useTaskRunner.js','src/components/EegWaveform.jsx']; for (const f of files) { const src=fs.readFileSync(f,'utf8'); babel.parseSync(src,{filename:f,sourceType:'module',presets:['@babel/preset-env','@babel/preset-react']}); } console.log('babel parse ok');"
cd ..
```

### Whitespace check

```powershell
git diff --check
```

## How To Run In Real MindRove Mode

There is no separate simulation flag in the active Electron plus FastAPI flow.
Real MindRove mode is selected by connecting to `mindrove://wifi`. The frontend
will prefer that device automatically when the MindRove SDK is available.

### 1. Install backend dependencies

```powershell
cd M:\CODEBASE\MindLinkAnalyzer\newBackend
python -m pip install -r requirements.txt
```

This installs the normal backend dependencies plus `mindrove`.

### 2. Confirm the SDK is importable

```powershell
cd M:\CODEBASE\MindLinkAnalyzer
python -c "import sys; sys.path.insert(0, 'newBackend'); import mindrove_device; print(mindrove_device.MINDROVE_SDK_AVAILABLE)"
```

Expected output:

```text
True
```

If it prints `False`, install or repair the MindRove SDK in the Python
environment used to run the backend:

```powershell
python -m pip install mindrove
```

### 3. Prepare the MindRove device

Use the normal MindRove Wi-Fi setup for the device. The backend uses the SDK
defaults unless these optional overrides are set:

```powershell
$env:MINDROVE_IP_ADDRESS = "192.168.x.x"
$env:MINDROVE_IP_PORT = "12345"
$env:MINDROVE_TIMEOUT = "15"
```

Only set these when the default SDK discovery does not match your device or
network setup.

The EEG row selection also has an optional override:

```powershell
# Recommended default: auto-detect active SDK EEG rows.
Remove-Item Env:\MINDROVE_EEG_ROWS -ErrorAction SilentlyContinue

# Force the row map if a device/SDK exposes a known fixed layout.
$env:MINDROVE_EEG_ROWS = "0,1,2,3"
```

Use `0,1,2,3` for the device behavior validated with the standalone plotter.
Use `0,1,4,5` only if a specific MindRove configuration exposes O1/O2 on rows
4 and 5.

## Standalone Terminal MindRove Capture

For hardware debugging before using the FastAPI backend, run the terminal-only
recorder:

```powershell
cd M:\CODEBASE\MindLinkAnalyzer
python newBackend\mindrove_terminal_capture.py --duration-seconds 300 --output captures\mindrove_5min.csv
```

The script logs SDK import, MindRove input parameters, board metadata, selected
EEG rows, sample rate, resistance rows, battery row, stream startup, per-second
sample flow, worn/contact status, resistance values, EEG row standard
deviations, and rows written. It waits until samples are flowing and the headset
is classified as worn, then records five minutes by default.

When resistance/impedance rows are unavailable, the EEG-variance fallback now
requires all four selected rows to be active by default. This prevents floating
Fp1/Fp2 noise from being treated as a worn four-channel headset while O1/O2 are
flat zero. The recorder logs absolute mean offsets, but the absolute-mean
rejection guard is opt-in because valid MindRove raw streams can retain large
DC offsets even when the headset is worn.

The recorder defaults to active-row auto detection because the MindRove SDK can
expose inactive all-zero EEG rows depending on electrode configuration. It
scans all SDK EEG rows from `BoardShim.get_eeg_channels()`, logs each row's
standard deviation, and selects the first four active rows as `fp1`, `fp2`,
`o1`, and `o2` for the CSV.

The Focus Cube row mapping can still be forced when needed:

```text
--eeg-rows 0,1,4,5
```

Useful diagnostic options:

```powershell
python newBackend\mindrove_terminal_capture.py --print-raw
python newBackend\mindrove_terminal_capture.py --contact-mode eeg
python newBackend\mindrove_terminal_capture.py --contact-mode resistance
python newBackend\mindrove_terminal_capture.py --disable-worn-gate
python newBackend\mindrove_terminal_capture.py --eeg-rows auto
python newBackend\mindrove_terminal_capture.py --eeg-rows 0,1,4,5
python newBackend\mindrove_terminal_capture.py --worn-min-active-eeg-rows 4
python newBackend\mindrove_terminal_capture.py --worn-max-abs-mean 10000
python newBackend\mindrove_terminal_capture.py --mindrove-ip 192.168.4.1 --mindrove-port 4210
python newBackend\mindrove_terminal_capture.py --mindrove-serial-port COM9
```

The CSV includes `timestamp`, `sample_index`, `fp1`, `fp2`, `o1`, `o2`,
`worn`, `contact_quality`, `contact_reason`, `battery`, any detected
`resistance_<row>` columns, `eeg_std_<row>` columns, and
`eeg_abs_mean_<row>` columns.

To stop recording and visualize the live stream instead, use plot mode:

```powershell
python newBackend\mindrove_terminal_capture.py --plot --print-raw
```

Plot mode keeps the same terminal status output, does not write CSV, and opens
a live scrolling Matplotlib window with five traces:

```text
Fp1, Fp2, O1, O2, aggregate mean
```

By default, plot mode displays each trace after subtracting its visible-window
mean. This removes raw DC offset and slow baseline drift from the display only;
acquisition, terminal logs, QC, and CSV mode remain raw.

Useful plot options:

```powershell
python newBackend\mindrove_terminal_capture.py --plot --plot-window-seconds 20
python newBackend\mindrove_terminal_capture.py --plot --plot-backend TkAgg
python newBackend\mindrove_terminal_capture.py --plot --plot-mode raw
python newBackend\mindrove_terminal_capture.py --plot --eeg-rows 0,1,2,3
python newBackend\mindrove_terminal_capture.py --plot --duration-seconds 0
```

Use `--duration-seconds 0` to keep plotting until the plot window is closed or
the terminal is interrupted.

### 4. Start the backend

From the repository root:

```powershell
cd M:\CODEBASE\MindLinkAnalyzer
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir newBackend
```

Development reload mode:

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir newBackend --reload
```

Optional log controls:

```powershell
# Default: concise connection, stream, QC, and analysis logs.
$env:EEG_DEBUG_LOGS = "1"

# Add lower-level statistical diagnostics.
$env:EEG_ANALYSIS_VERBOSE = "1"

# Silence backend EEG diagnostics.
$env:EEG_DEBUG_LOGS = "0"

# Optional MindRove contact gate tuning; defaults match the terminal capture.
$env:MINDROVE_WORN_MIN_ACTIVE_EEG_ROWS = "4"
$env:MINDROVE_WORN_MIN_EEG_STD = "0.5"
$env:MINDROVE_WORN_MAX_EEG_STD = "50000"
```

### 5. Check ports

In another terminal:

```powershell
Invoke-RestMethod http://localhost:8000/ports
```

Confirm the response includes `mindrove://wifi` and `"available": true`.

### 6. Connect explicitly to MindRove

```powershell
Invoke-RestMethod `
  -Uri http://localhost:8000/connect `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"port":"mindrove://wifi"}'
```

Then check:

```powershell
Invoke-RestMethod http://localhost:8000/status
```

Expected status after a successful connection:

```json
{ "status": "connected", "battery": 66 }
```

Battery may be `null` for the first few moments after connection, before the
first SDK data frame containing the battery row has been read. Once available,
the backend also broadcasts a `battery` WebSocket message and includes the same
value in `eeg_data.battery`.

### 7. Start the frontend

```powershell
cd M:\CODEBASE\MindLinkAnalyzer\ElectronFrontEnd
npm install
npm run dev
```

The frontend calls `GET /ports`, prefers the available MindRove device, and
connects through the backend. Baseline and task sessions store four-channel
sample objects in the run-scoped IndexedDB recording store.

## How To Switch Back To Legacy BrainLink Serial

MindRove is now the default. To use the legacy serial path manually, call
`/connect` with a real serial port:

```powershell
Invoke-RestMethod `
  -Uri http://localhost:8000/connect `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"port":"COM3"}'
```

Replace `COM3` with the actual port from:

```powershell
Invoke-RestMethod http://localhost:8000/ports
```

## Evaluation Checklist

Use this checklist during review:

- `GET /ports` returns MindRove virtual device with FP1, FP2, O1, O2.
- `POST /connect` with no body or `mindrove://wifi` starts the MindRove reader.
- WebSocket emits `device_info` with device `mindrove`.
- `device_info.channels` shows the selected SDK rows for FP1, FP2, O1, and O2.
- WebSocket emits `battery` once the MindRove SDK battery row is available.
- WebSocket emits `raw_multi_batch` samples shaped as FP1/FP2/O1/O2 objects.
- WebSocket still emits `raw_batch` so the existing waveform renders.
- IndexedDB baseline records contain four-channel objects, not just numbers;
  Web Storage retains only the compact baseline manifest.
- IndexedDB task records contain four-channel objects, not just numbers.
- `/analyze` accepts those four-channel objects and produces the existing
  feature/report schema.
- Regression tests pass.
- Report/neuroprofile traceability tests pass, except the known local `httpx`
  dependency gap if `httpx` has not been installed.

## Known Limitations

- Standalone hardware streaming and plotting were validated by local terminal
  runs; the FastAPI endpoint should be rechecked against the same device after
  restart.
- The full endpoint test in `tests/test_neuroprofile_traceability.py` requires
  `httpx` to be installed.
- The live waveform displays a scalar aggregate of the four channels. The
  recorded data still stores the four-channel samples.
