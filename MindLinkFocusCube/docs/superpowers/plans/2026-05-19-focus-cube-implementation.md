# Focus Cube Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate BrainLink raw-EEG browser test app where alpha-derived live features lift a cube and alpha/beta/gamma powers animate a 3D neural visualization.

**Architecture:** A Python backend owns BrainLink serial parsing, raw EEG buffering, feature extraction, normalization, demo generation, and WebSocket broadcasting. A Vite/Three.js frontend owns rendering, interpolation, and responsive split-screen presentation. Existing MindLinkAnalyzer runtime scripts are not modified.

**Tech Stack:** Python 3.11, NumPy, SciPy, pyserial, websockets, pytest, Vite, Three.js, Vitest.

---

## File Structure

- `MindLinkFocusCube/backend/focuscube/config.py`: runtime config and attention mapping options.
- `MindLinkFocusCube/backend/focuscube/features.py`: raw EEG feature extraction, rolling normalization, attention mapping, and demo frames.
- `MindLinkFocusCube/backend/focuscube/brainlink_source.py`: BrainLinkParser serial adapter that ignores built-in attention/meditation for control.
- `MindLinkFocusCube/backend/focuscube/server.py`: WebSocket broadcaster and CLI entrypoint.
- `MindLinkFocusCube/backend/tests/test_features.py`: backend TDD tests for feature math and payload shape.
- `MindLinkFocusCube/backend/requirements.txt`: backend dependencies.
- `MindLinkFocusCube/frontend/src/math.js`: deterministic visual mapping helpers.
- `MindLinkFocusCube/frontend/src/main.js`: Three.js app and WebSocket client.
- `MindLinkFocusCube/frontend/src/styles.css`: split-screen app styling.
- `MindLinkFocusCube/frontend/src/math.test.js`: frontend TDD tests for visual mappings.
- `MindLinkFocusCube/package.json`, `MindLinkFocusCube/frontend/package.json`, `MindLinkFocusCube/frontend/vite.config.js`, `MindLinkFocusCube/frontend/index.html`: app scripts and frontend scaffold.
- `MindLinkFocusCube/README.md`: setup and run instructions.

### Task 1: Backend Feature Core

**Files:**
- Create: `MindLinkFocusCube/backend/focuscube/config.py`
- Create: `MindLinkFocusCube/backend/focuscube/features.py`
- Create: `MindLinkFocusCube/backend/focuscube/__init__.py`
- Test: `MindLinkFocusCube/backend/tests/test_features.py`

- [ ] **Step 1: Write failing backend tests**

```python
import math
import numpy as np

from focuscube.config import FocusCubeConfig
from focuscube.features import (
    AdaptiveNormalizer,
    attention_from_normalized,
    build_payload,
    compute_band_features,
    demo_frame,
)


def sine_wave(freq, fs=256, seconds=3, amplitude=50):
    t = np.arange(0, seconds, 1 / fs)
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_compute_band_features_detects_alpha_from_raw_samples():
    features = compute_band_features(sine_wave(10))
    assert features.bands["alpha"] > features.bands["beta"] * 4
    assert features.relative["alpha"] > 0.55


def test_attention_mapping_uses_normalized_alpha_by_default():
    config = FocusCubeConfig(attention_source="alpha")
    assert attention_from_normalized({"alpha": 0.8, "beta": 0.1, "gamma": 0.1}, config) == 0.8


def test_attention_mapping_can_ignore_alpha_with_ratio_mode():
    config = FocusCubeConfig(attention_source="beta_alpha_ratio")
    value = attention_from_normalized({"alpha": 0.2, "beta": 0.8, "gamma": 0.1}, config)
    assert value > 0.75


def test_adaptive_normalizer_returns_bounded_values():
    normalizer = AdaptiveNormalizer(window=4)
    values = [normalizer.normalize("alpha", value) for value in [10, 20, 30, 40, 50]]
    assert all(0 <= value <= 1 for value in values)
    assert values[-1] == 1


def test_payload_shape_is_raw_feature_derived():
    config = FocusCubeConfig(attention_source="alpha")
    features = compute_band_features(sine_wave(10))
    normalizer = AdaptiveNormalizer(window=8)
    payload = build_payload(features, normalizer, config, mode="device")
    assert payload["mode"] == "device"
    assert "attention" in payload
    assert set(["alpha", "beta", "gamma"]).issubset(payload["bands"])
    assert set(["alpha", "beta", "gamma", "betaGamma"]).issubset(payload["normalized"])
    assert "parserAttention" not in payload
    assert "parserMeditation" not in payload


def test_demo_frame_emits_bounded_payload():
    payload = demo_frame(0.5, FocusCubeConfig())
    assert payload["mode"] == "demo"
    assert 0 <= payload["attention"] <= 1
    assert 0 <= payload["normalized"]["alpha"] <= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Users\conta\anaconda3\envs\brainlink\python.exe -m pytest MindLinkFocusCube/backend/tests/test_features.py -q`
Expected: FAIL because `focuscube` modules do not exist yet.

- [ ] **Step 3: Implement backend feature core**

Create config and feature code implementing the named functions. Use SciPy `welch`, `butter`, `filtfilt`, `iirnotch`, and Simpson integration. Use raw sample arrays only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:\Users\conta\anaconda3\envs\brainlink\python.exe -m pytest MindLinkFocusCube/backend/tests/test_features.py -q`
Expected: 6 passed.

### Task 2: Backend BrainLink Source And WebSocket Server

**Files:**
- Create: `MindLinkFocusCube/backend/focuscube/brainlink_source.py`
- Create: `MindLinkFocusCube/backend/focuscube/server.py`
- Create: `MindLinkFocusCube/backend/requirements.txt`
- Modify: `MindLinkFocusCube/backend/tests/test_features.py`

- [ ] **Step 1: Add failing payload and server import tests**

Append tests that import `focuscube.server.create_frame_stream` and assert the async demo stream yields payloads with no parser attention fields.

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Users\conta\anaconda3\envs\brainlink\python.exe -m pytest MindLinkFocusCube/backend/tests/test_features.py -q`
Expected: FAIL because server/source modules do not exist.

- [ ] **Step 3: Implement source and server**

Implement a `BrainLinkRawSource` that imports `BrainLinkParser` from `../BrainLinkParser` when running inside this repo, uses parser raw callbacks for samples, ignores parser `onEEG` attention/meditation for state, and provides demo fallback. Implement WebSocket JSON broadcasting at `ws://127.0.0.1:8765`.

- [ ] **Step 4: Run backend tests**

Run: `C:\Users\conta\anaconda3\envs\brainlink\python.exe -m pytest MindLinkFocusCube/backend/tests/test_features.py -q`
Expected: all backend tests pass.

### Task 3: Frontend Mapping Helpers

**Files:**
- Create: `MindLinkFocusCube/frontend/src/math.js`
- Create: `MindLinkFocusCube/frontend/src/math.test.js`
- Create: `MindLinkFocusCube/frontend/package.json`
- Create: `MindLinkFocusCube/frontend/vite.config.js`

- [ ] **Step 1: Write failing frontend tests**

```javascript
import { describe, expect, it } from 'vitest';
import { cubeHeightFromAttention, particleParamsFromBands } from './math.js';

describe('cubeHeightFromAttention', () => {
  it('maps low and high attention to drop and lift bounds', () => {
    expect(cubeHeightFromAttention(0)).toBeCloseTo(-1.4);
    expect(cubeHeightFromAttention(1)).toBeCloseTo(2.4);
  });
});

describe('particleParamsFromBands', () => {
  it('binds blue particles to alpha and pink particles to beta/gamma', () => {
    const params = particleParamsFromBands({ alpha: 0.75, betaGamma: 0.25 });
    expect(params.blue.opacity).toBeGreaterThan(params.pink.opacity);
    expect(params.blue.activeCount).toBeGreaterThan(params.pink.activeCount);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd MindLinkFocusCube/frontend; npm test -- --run`
Expected: FAIL because helper files do not exist.

- [ ] **Step 3: Implement mapping helpers**

Implement clamp, cube height mapping, and particle parameter mapping with deterministic output.

- [ ] **Step 4: Run frontend tests**

Run: `cd MindLinkFocusCube/frontend; npm test -- --run`
Expected: tests pass.

### Task 4: Three.js App

**Files:**
- Create: `MindLinkFocusCube/frontend/index.html`
- Create: `MindLinkFocusCube/frontend/src/main.js`
- Create: `MindLinkFocusCube/frontend/src/styles.css`

- [ ] **Step 1: Implement split-screen Three.js app**

Build two canvases or renderers: cube game on the left and neural visualization on the right. Load `public/models/cortex.glb` if available, otherwise use procedural fallback geometry. Connect to WebSocket and update render state from incoming payloads.

- [ ] **Step 2: Run frontend build**

Run: `cd MindLinkFocusCube/frontend; npm run build`
Expected: Vite build exits 0.

### Task 5: App Scripts And Documentation

**Files:**
- Create: `MindLinkFocusCube/package.json`
- Create: `MindLinkFocusCube/README.md`
- Modify: `MindLinkAnalyzer/.gitignore`
- Modify: `MindLinkFocusCube/docs/superpowers/specs/2026-05-19-focus-cube-design.md`

- [ ] **Step 1: Add scripts and README**

Document setup, demo mode, device mode, the raw-data-only rule, GLTF placement, and ports.

- [ ] **Step 2: Run full verification**

Run: `C:\Users\conta\anaconda3\envs\brainlink\python.exe -m pytest MindLinkFocusCube/backend/tests/test_features.py -q`
Run: `cd MindLinkFocusCube/frontend; npm test -- --run`
Run: `cd MindLinkFocusCube/frontend; npm run build`
Expected: all commands exit 0.
