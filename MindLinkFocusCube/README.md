# MindLink Focus Cube

Separate browser test app for MindRove Bright raw EEG neurofeedback.

The backend uses the official `mindrove` Python SDK for acquisition and keeps feature extraction local to this app. Alpha, beta, gamma, and the cube-control focus index are calculated from raw EEG time-series samples; no vendor-provided attention score is used for cube control.

MindRove Bright provides multiple EEG rows through the SDK. Focus Cube keeps the Bright layout channel-wise: frontal `Fp1/Fp2` and occipital `O1/O2`. The brain graphic is a visualization anchor, not clinical source localization.

## Setup

```powershell
cd M:\CODEBASE\MindLinkAnalyzer\MindLinkFocusCube
python -m pip install -r backend\requirements.txt
npm install
npm --prefix frontend install
npm --prefix frontend exec playwright install chromium
```

If your terminal auto-activates the wrong virtual environment, activate the Python environment where `mindrove` is installed first, then run the commands above.

Quick SDK check:

```powershell
python -c "from mindrove.board_shim import BoardShim, BoardIds; print(BoardShim.get_sampling_rate(BoardIds.MINDROVE_WIFI_BOARD))"
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

## Device Mode

Connect your machine to the MindRove Bright WiFi network, then run the backend and frontend in two terminals:

```powershell
npm run dev:backend:device
npm run dev:frontend
```

The backend streams JSON frames at `ws://127.0.0.1:8765`. By default it connects to the MindRove SDK WiFi endpoint `192.168.4.1:4210`.

The app now defaults to `--eeg-rows auto`, matching `newBackend\mindrove_terminal_capture.py`: it asks the MindRove SDK for EEG rows, scans for the first four active rows, and maps them positionally:

```text
selected row 1 = Fp1, selected row 2 = Fp2, selected row 3 = O1, selected row 4 = O2
```

This matters because some SDK configurations expose Bright as `0,1,2,3`, while others use `0,1,4,5`. If you know your exact mapping, lock it with `--eeg-rows 0,1,4,5` or `--eeg-rows 0,1,2,3`.

The MindRove SDK also exposes resistance/impedance rows. Focus Cube uses those rows as a worn/contact gate. If contact is not good enough, the backend emits `device_not_worn`, clears the EEG feature buffer, and sends `attention=0.0` so floating off-head electrode noise cannot lift the cube.

By default, contact mode is `auto`: it trusts resistance/impedance when it is clearly good, but falls back to plausible active EEG row variance when the SDK resistance values are missing or not useful for the Bright headset. Focus Cube also requires three consecutive worn/contact frames before it accepts samples for calibration or cube control. Until then the UI shows `stabilizing`, and the backend remains in `device_not_worn`.

If the terminal says `not_worn`, inspect the printed `reason`, `stable_frames`, `resistance_ohms`, and `eeg_std` values.

Tune or bypass the gate when testing:

```powershell
python -m backend.focuscube.server --worn-resistance-threshold 5000000 --worn-min-good-resistance-pairs 2 --require-device
python -m backend.focuscube.server --contact-mode eeg --require-device
python -m backend.focuscube.server --contact-mode auto --worn-min-eeg-std 0.2 --worn-max-eeg-std 100000 --require-device
python -m backend.focuscube.server --worn-stable-frames 5 --require-device
python -m backend.focuscube.server --disable-worn-gate --require-device
```

Use `--disable-worn-gate` only for debugging, because off-head floating EEG can look random but still produce band powers.

Strict device mode fails instead of falling back to demo:

```powershell
npm run dev:backend:device:strict
```

Print raw channel-wise SDK EEG rows before feature extraction:

```powershell
python -m backend.focuscube.server --print-raw --require-device
python -m backend.focuscube.server --print-raw --raw-print-rows 6 --raw-print-samples 12 --require-device
```

The raw line is throttled by default and looks like:

```text
[FocusCube] raw_sdk shape=39x125 eeg_rows=[0, 1, 2, 3, 4, 5, 6, 7] row0=[...] row1=[...]
```

`shape` is the full SDK board matrix: rows are board channels and columns are samples returned by that drain cycle. `row0`, `row1`, etc. are the EEG rows before we average active rows into the feature pipeline.

Override connection settings if needed:

```powershell
python -m backend.focuscube.server --mindrove-ip 192.168.4.1 --mindrove-port 4210 --require-device
python -m backend.focuscube.server --mindrove-serial-port COM9 --require-device
```

When the backend is working you should see startup lines like:

```text
[FocusCube] Starting MindLink Focus Cube backend.
[FocusCube] Attention source: alpha
[FocusCube] WebSocket server listening on ws://127.0.0.1:8765
[FocusCube] Starting MindRove Bright stream ip=192.168.4.1 port=4210...
```

If the frontend shows `device_warming`, the backend has opened the device and is waiting for enough raw samples to calculate bands. If it shows `demo`, the backend is using synthetic data because you started demo mode or device detection fell back.

## Attention Mapping

Default live-device behavior uses a calibrated focus index rather than raw alpha:

- First, the backend collects baseline windows in `device_calibrating` mode.
- Then it scores frontal engagement: `frontal_beta / (frontal_alpha + frontal_theta)`.
- It also scores alpha suppression in the occipital and frontal rows relative to baseline.
- It applies an artifact penalty from high-frequency and line-noise ratios.
- The cube follows the smoothed focus index, not instantaneous band power.

This is intentionally conservative. Stable baseline-like windows should keep the cube low, while sustained frontal beta engagement plus posterior alpha suppression should lift it.

The backend still streams alpha/beta/gamma bands for the particle visualization.

Calibration and scoring knobs:

```powershell
python -m backend.focuscube.server --require-device
python -m backend.focuscube.server --eeg-rows auto --require-device
python -m backend.focuscube.server --eeg-rows 0,1,4,5 --require-device
python -m backend.focuscube.server --focus-deadband 0.02 --focus-full-scale 0.18 --require-device
```

The older mappings remain mainly for experiments and demo comparisons:

Alternative mappings are available from the backend CLI:

```powershell
python -m backend.focuscube.server --attention-source inverse_alpha --demo
python -m backend.focuscube.server --attention-source beta_alpha_ratio --demo
```

## Cortex Model

The frontend tries to load:

```text
frontend/public/models/cortex.glb
```

If that file is missing, the app renders a procedural cortex-like fallback so the test app still works immediately.

## Verification

```powershell
python -m pytest backend\tests -q -p no:cacheprovider
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run verify:canvas
```

`verify:canvas` expects the dev app to be running at `http://127.0.0.1:5174`.
