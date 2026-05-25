# Focus Cube MindRove Bright Implementation Plan

## Goal

Build and maintain a separate MindRove Bright raw-EEG browser test app where a locally calculated calibrated focus index lifts a cube and alpha/beta/gamma powers animate a neural visualization.

## Architecture

A Python backend owns MindRove SDK acquisition, raw EEG buffering, feature extraction, normalization, demo generation, and WebSocket broadcasting. A Vite/Three.js frontend owns rendering, interpolation, and responsive split-screen presentation. Existing MindLinkAnalyzer runtime scripts are not modified.

## Tech Stack

Python 3.11, `mindrove`, NumPy, SciPy, websockets, pytest, Vite, Three.js, Vitest.

## Backend Tasks

1. Keep `focuscube.features` as the source of truth for local raw-sample band extraction, channel-wise Bright region features, baseline calibration, and focus-index scoring.
2. Use `focuscube.mindrove_source.MindRoveRawSource` for SDK setup, stream draining, battery metadata, and device status.
3. Keep `focuscube.server` responsible for CLI options, device/demo mode, WebSocket frames, and feature logging.
4. Maintain tests for feature extraction, calibrated focus-index behavior, demo/warming frames, and MindRove board-data conversion.

## Frontend Tasks

1. Keep the split-screen cube and neural visualization as the first viewport.
2. Show real device, warming, demo, and disconnected states in the badge.
3. Show battery, endpoint, and sample count from backend device metadata.
4. Drive cube animation from backend `attention`, which is the live-device smoothed focus index. Drive particles from normalized band-power values.

## Verification

```powershell
python -m pytest backend\tests -q -p no:cacheprovider
npm --prefix frontend test -- --run
npm --prefix frontend run build
```
