# Focus Cube BrainLink Test App Design

## Goal

Build a separate browser-based test application that uses the existing BrainLink headset pipeline to drive a small neurofeedback game. The user sees a split screen: a focus-controlled cube on the left and a live neural activity visualization on the right. The app is isolated from the existing MindLinkAnalyzer application code.

## Scope

The new app lives under `MindLinkFocusCube/` and does not modify existing MindLinkAnalyzer runtime scripts. It may import or copy small, clearly attributed pipeline concepts from the current BrainLink parser and feature extraction code, but runtime code for this app is owned by the new folder.

The first version supports:

- BrainLink serial input through Python.
- A demo mode that emits realistic synthetic band powers when no headset is connected.
- Local WebSocket streaming from backend to browser.
- Split-screen Three.js rendering.
- Alpha-driven cube motion, with configurable mapping direction.
- Blue particles driven by alpha power.
- Pink particles driven by combined beta and gamma power.
- A local fallback cortex-like mesh if no GLTF cortex asset is installed yet.

OSC is out of scope for the first version because WebSocket is simpler, lower-friction in a browser, and adequate for localhost latency. The backend can expose an OSC adapter later without changing the game state model.

## Architecture

`MindLinkFocusCube/backend` contains the Python backend. It connects to BrainLink using the existing `BrainLinkParser` package when available, buffers raw EEG samples, runs the feature extraction pipeline, normalizes band powers, and broadcasts compact JSON frames over WebSocket.

`MindLinkFocusCube/frontend` contains a lightweight browser app using Vite and Three.js. It connects to the backend WebSocket, smooths incoming control values for rendering, and updates the cube and neural visualization every animation frame.

The backend owns signal processing and normalization. The frontend owns presentation, interpolation, and visual effects.

## Data Flow

1. BrainLink serial bytes are read by the backend.
2. `BrainLinkParser` invokes raw EEG callbacks.
3. Raw samples enter a fixed-size rolling buffer.
4. Once enough samples exist, the backend applies the same broad pipeline used in the existing analyzer: notch filtering, 1-45 Hz bandpass filtering, Welch PSD, Simpson band-power integration.
5. The backend computes absolute and relative delta, theta, alpha, beta, and gamma values.
6. The backend normalizes alpha, beta, and gamma to stable 0-1 control signals using an adaptive rolling range.
7. A WebSocket frame is broadcast:

```json
{
  "timestamp": 1779187200.0,
  "mode": "device",
  "quality": 0.91,
  "attention": 0.64,
  "bands": {
    "alpha": 12.4,
    "beta": 8.2,
    "gamma": 2.1
  },
  "relative": {
    "alpha": 0.31,
    "beta": 0.21,
    "gamma": 0.05
  },
  "normalized": {
    "alpha": 0.71,
    "beta": 0.52,
    "gamma": 0.28,
    "betaGamma": 0.43
  }
}
```

## Attention Mapping

The requested default is alpha-driven cube lift:

- Higher normalized alpha means the cube rises.
- Lower normalized alpha means the cube drops.

Because alpha can also indicate relaxed or eyes-closed states, this mapping is configurable in `backend/config.json` or an equivalent app config:

- `attention_source`: `alpha`, `inverse_alpha`, or `beta_alpha_ratio`.
- `lift_smoothing`: render-side smoothing amount.
- `lift_threshold`: optional threshold for "focused" UI state.

The first build defaults to `alpha` so it matches the requested behavior.

## Frontend Experience

The first viewport is the application itself, not a landing page.

Left panel:

- A cube in a 3D space.
- A floor/reference plane that makes lift/drop obvious.
- A compact status strip for connection state, attention value, and mode.

Right panel:

- A 3D cortex visualization.
- Blue particles are positioned around the cortex and scale brightness/density with alpha.
- Pink particles are positioned around the cortex and scale brightness/density with beta/gamma.
- The scene gently rotates to reveal spatial depth.

The design uses restrained controls and avoids decorative cards. The split screen is stable on desktop and stacks vertically on narrow screens.

## GLTF Asset Strategy

The app checks for a local cortex model at `frontend/public/models/cortex.glb`. If it exists, Three.js loads it. If it does not exist, the app renders a procedural cortex-like fallback mesh so the test app works immediately.

The README will document where to place a free GLTF cortex model. The repository will not depend on downloading a third-party model during startup.

## Error Handling

If BrainLink is unavailable, the backend starts in demo mode unless `--require-device` is passed.

If signal quality is poor or the buffer is too small, the backend keeps streaming frames with `quality` below threshold and marks values as estimated or demo-like where appropriate.

If the WebSocket disconnects, the frontend displays disconnected state and smoothly returns the cube toward neutral instead of freezing at the last value.

## Testing

Backend tests cover:

- Band power normalization from known numeric inputs.
- Attention mapping for `alpha`, `inverse_alpha`, and `beta_alpha_ratio`.
- WebSocket payload shape.
- Demo generator emits bounded values.

Frontend tests are limited to deterministic pure functions where practical:

- Mapping attention to cube height.
- Mapping normalized bands to particle opacity/count parameters.

Manual verification covers:

- Running in demo mode.
- Opening the browser app.
- Seeing the cube rise/drop as synthetic alpha changes.
- Seeing blue and pink particles respond to incoming frames.

## Run Commands

Expected developer flow:

```powershell
cd MindLinkAnalyzer\MindLinkFocusCube
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
npm install
npm run dev
```

The frontend dev server and backend can be launched together through one npm script if dependencies are present.

## Non-Goals

- No changes to existing MindLinkAnalyzer GUI, backend, report generation, or React/Electron app.
- No production packaging in the first version.
- No Blender integration in the first version.
- No clinical or diagnostic attention claims.
- No remote server dependency for live rendering.
