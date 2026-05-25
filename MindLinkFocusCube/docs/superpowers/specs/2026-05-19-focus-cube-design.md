# Focus Cube MindRove Bright Test App Design

## Goal

Build a separate browser-based test application that uses live raw MindRove Bright EEG samples to drive a small neurofeedback game. The user sees a split screen: a focus-controlled cube on the left and a live neural activity visualization on the right. The app is isolated from the existing MindLinkAnalyzer runtime code.

## Scope

The app lives under `MindLinkFocusCube/`. It uses the official `mindrove` Python SDK for device acquisition, buffers raw EEG rows, converts active EEG rows into one live feature stream, computes alpha/beta/gamma band powers locally, and broadcasts compact WebSocket frames to the browser.

No vendor-provided attention score is used for control. The cube is driven by a locally calculated, baseline-normalized focus index; particles are driven by locally calculated band-power features.

## Architecture

`MindLinkFocusCube/backend` contains the Python backend:

- `focuscube.mindrove_source` owns MindRove SDK setup, stream lifecycle, board-buffer draining, battery metadata, and device status.
- `focuscube.features` owns filtering, Welch PSD band powers, channel-wise Bright regions, baseline calibration, focus-index scoring, artifact penalties, demo frames, and warming frames.
- `focuscube.server` owns CLI options, fallback to demo mode, WebSocket serving, and once-per-second feature logging.

`MindLinkFocusCube/frontend` contains the Vite/Three.js browser app:

- Left panel: cube height follows the backend `attention` value, which is the smoothed calibrated focus index in live-device mode.
- Right panel: top-down cortex visualization uses cyan alpha particles and magenta beta/gamma particles.
- Top-right badge shows real/demo/warming mode, battery, endpoint, and sample count.

## Data Flow

1. The backend starts a MindRove WiFi board session through `BoardShim`.
2. It drains available board data from the SDK buffer.
3. It keeps Bright rows channel-wise by default: `Fp1`, `Fp2`, `O1`, and `O2`.
4. It reads battery and resistance/impedance rows when available.
5. It runs a short baseline calibration.
6. It computes frontal engagement, occipital alpha suppression, frontal alpha suppression, and artifact penalties.
7. It broadcasts JSON frames over `ws://127.0.0.1:8765`.
8. The browser animates the cube and particles from those frames.

## Device Defaults

The default MindRove WiFi endpoint is:

```text
192.168.4.1:4210
```

CLI overrides:

```powershell
python -m backend.focuscube.server --mindrove-ip 192.168.4.1 --mindrove-port 4210
python -m backend.focuscube.server --mindrove-serial-port COM9
```

## Error Handling

If device startup fails, the backend falls back to demo mode unless `--require-device` is passed. While the stream is open but the feature window is not full yet, frames use `device_warming` mode.

## Testing

Backend tests cover:

- Band-power feature extraction from raw samples.
- Payload shape and omission of parser/vendor attention fields.
- MindRove input parameter construction.
- MindRove board-buffer draining into a single raw sample stream.
- Channel-wise Bright region extraction and calibrated focus-index behavior.

Frontend tests cover cube and particle math.
