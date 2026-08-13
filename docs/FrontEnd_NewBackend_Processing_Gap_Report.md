# FrontEnd `newBackend` vs Enhanced Single-Channel Processing Layer

## Scope

This document compares only the **processing layer** for single-channel EEG analysis:

- Canonical/reference pipeline: `new-branch-from-6914fa0` via `EnhancedFeatureAnalysisEngine`
- Ported frontend backend: `origin/frontEnd:newBackend/main.py`

This intentionally excludes:

- UI trigger flow
- transport / API layer
- storage / in-memory data source differences
- output envelope / report formatting differences

The question answered here is:

> Is the actual EEG processing after "Analyze All Tasks" the same?

Short answer:

**No. The frontend backend is a partial port of the enhanced methodology, but the processing layer is not identical.**


## Recommendation

### Recommended canonical pipeline

Use **`new-branch-from-6914fa0`** as the reference implementation for single-channel analysis.

Reason:

- it processes **raw EEG more directly**
- it uses the real enhanced engine rather than a reduced/stateless reconstruction
- it has stronger **baseline quality control**
- it preserves more of the original signal-analysis assumptions

### Recommended deployment choice

If the goal is **analysis correctness**, prefer **`new-branch-from-6914fa0`**.

If the goal is **Electron/backend deployment convenience**, `frontEnd/newBackend/main.py` is operationally simpler, but it should be treated as a **non-equivalent port**, not the canonical analysis engine.


## Processing-Layer Verdict

### What is similar

The frontend backend does preserve much of the higher-level statistical logic:

- eyes-closed baseline preference
- block aggregation
- block equalization
- correlation guard
- Welch t-tests
- BH FDR
- directional expectations
- effect-size and percent-change fallback rules
- Fisher/Kost-McDermott summary
- SumP
- cosine similarity

### What is materially different

The frontend backend diverges in the part that matters most:

- **window construction**
- **feature extraction substrate**
- **baseline QC**

These differences are large enough that final p-values, effect sizes, and significant features can differ even when the later statistical rules are similar.


## Highest-Impact Gaps

### 1. Feature extraction substrate is different

**Enhanced pipeline**

- Works directly from raw EEG feature windows inside the enhanced engine.
- Reference areas:
  - [BrainLinkAnalyzer_GUI_Enhanced.py](../BrainLinkAnalyzer_GUI_Enhanced.py#L2025)
  - [BrainLinkAnalyzer_GUI_Enhanced.py](../BrainLinkAnalyzer_GUI_Enhanced.py#L1321)

**Frontend backend**

- First converts raw EEG into TGAM-style band-power windows in `_raw_to_bp_windows()`.
- Then reconstructs higher-level features from those band powers in `_extract_features()`.
- Reference areas:
  - `newBackend/main.py` lines `425-560`
  - `newBackend/main.py` lines `595-676`

**Impact**

This is the largest methodological divergence. The frontend backend is not analyzing the same intermediate signal representation as the enhanced engine.

### Recommendation

If alignment is the goal, the frontend backend should stop treating TGAM-style band-power windows as the primary feature substrate and instead port the enhanced engine's raw-window feature extraction more directly.


### 2. Window length is different

**Enhanced pipeline**

- Forces **2.0 second** windows:
  - [BrainLinkAnalyzer_GUI_Enhanced.py](../BrainLinkAnalyzer_GUI_Enhanced.py#L497)
  - [BrainLinkAnalyzer_GUI_Enhanced.py](../BrainLinkAnalyzer_GUI_Enhanced.py#L502)

**Frontend backend**

- Uses **256 samples at 512 Hz = 0.5 seconds**:
  - `newBackend/main.py` lines `403-405`

**Impact**

Even if both later aggregate into 8-second blocks, the underlying feature estimates are built from different temporal windows. That changes:

- PSD characteristics
- entropy values
- peak values
- band-power stability
- per-feature variance
- downstream test statistics

### Recommendation

Change the frontend backend to use the same effective window duration as the enhanced engine:

- move from `0.5 s` raw windows to `2.0 s`
- ensure the same overlap / step assumptions are used
- recompute block duration based on the aligned window duration


### 3. Baseline QC is weaker in the frontend backend

**Enhanced pipeline**

- Rejects extreme eyes-closed baseline windows during accumulation:
  - [BrainLinkAnalyzer_GUI_Enhanced.py](../BrainLinkAnalyzer_GUI_Enhanced.py#L1321)
  - [BrainLinkAnalyzer_GUI_Enhanced.py](../BrainLinkAnalyzer_GUI_Enhanced.py#L1346)

**Frontend backend**

- Does not reproduce equivalent baseline-window rejection logic
- Returns rejection counters as zero:
  - `newBackend/main.py` lines `1606-1609`

**Impact**

The frontend backend can analyze noisier baseline sets than the enhanced engine would allow. That changes:

- baseline mean / variance
- z-scores
- effect sizes
- significance thresholds via variance-sensitive tests

### Recommendation

Port the enhanced baseline QC into the frontend backend before baseline statistics are finalized:

- compute per-window robust median / MAD
- detect extreme artifact windows
- reject invalid EC baseline windows before statistics
- report real rejection counts instead of hard-coded zeros


## Medium-Impact Gaps

### 4. Blocking concept is similar, but not equivalent

**Enhanced pipeline**

- Uses `_build_blocks()` and time-aware aggregation:
  - [BrainLinkAnalyzer_GUI_Enhanced.py](../BrainLinkAnalyzer_GUI_Enhanced.py#L1481)

**Frontend backend**

- Uses `_build_blocks()` with fixed `windows_per_block` from a `0.5 s` window assumption:
  - `newBackend/main.py` lines `1108-1136`
  - `newBackend/main.py` lines `567-572`

**Impact**

The blocking layer is structurally similar, but since the frontend backend starts from different windows, the blocks do not represent the same underlying measurement units.

### Recommendation

Do not change only the block size. First align the raw feature-window definition, then recalculate blocks.


### 5. Across-task correction is weaker in the frontend backend

**Enhanced pipeline**

- Adds `cross_task_correction` using Holm-Bonferroni:
  - [BrainLinkAnalyzer_GUI_Enhanced.py](../BrainLinkAnalyzer_GUI_Enhanced.py#L2839)

**Frontend backend**

- Performs across-task omnibus ranking / significance but does not reproduce the same cross-task correction block.

**Impact**

This is less important than the feature-extraction mismatch, but it still means the frontend backend is not fully equivalent at the inferential layer.

### Recommendation

Add the same cross-task family-wise correction strategy after per-task omnibus results are computed.


## Low-Impact or Mostly-Aligned Areas

These areas are reasonably well aligned and are not the primary source of mismatch:

- `_equalize_blocks()` vs `_equalize_windows()`
- correlation guard logic
- expected direction rules
- Fisher/KM style combined evidence
- SumP
- cosine similarity

These should be kept, but they do not compensate for the earlier signal-processing differences.


## What To Change In `frontEnd/newBackend/main.py`

Priority order:

1. **Replace the current raw-to-band-power-first pipeline**
   - Rework `_raw_to_bp_windows()` / `_extract_features()` so features are computed from raw windows in the same way as the enhanced engine.

2. **Align window duration with enhanced**
   - Replace:
     - `_RAW_WINDOW = 256`
   - With a window model equivalent to the enhanced engine's 2-second processing windows.

3. **Port baseline QC**
   - Add eyes-closed artifact rejection before baseline statistics are computed.
   - Replace hard-coded zero rejection counts with real counters.

4. **Recompute block assumptions after window alignment**
   - Update `_WINDOW_DURATION_SEC`
   - Update `_WINDOWS_PER_BLOCK`
   - Verify block aggregation now reflects the same effective unit as enhanced.

5. **Add cross-task Holm-Bonferroni correction**
   - Bring the frontend backend's multi-task post-processing in line with enhanced.


## Suggested Developer Plan

### Phase 1: Make the frontend backend methodologically honest

If full alignment cannot happen immediately:

- document `newBackend/main.py` as a **simplified/stateless analysis port**
- do not describe it as equivalent to the enhanced engine
- avoid claiming report parity with the enhanced GUI

### Phase 2: Align the raw processing layer

Port these parts first:

- raw-window feature extraction
- 2-second window model
- baseline QC

This will remove the biggest sources of divergence.

### Phase 3: Align the inferential layer fully

Then port:

- cross-task Holm-Bonferroni correction
- any remaining metadata / QC summaries required for parity


## Final Recommendation

### Best processing pipeline

**Recommended:** `new-branch-from-6914fa0`

### Why

Because it is the stronger and more faithful single-channel processing implementation:

- better signal fidelity
- better baseline handling
- fewer approximations
- closer to the intended enhanced methodology

### Status of `frontEnd/newBackend/main.py`

`frontEnd/newBackend/main.py` is **not wrong**, but it is best understood as:

> a practical backend port of the enhanced statistical ideas, not the same processing pipeline

If parity is required, it should be brought closer to the enhanced engine starting with the raw-window and baseline-QC layers.
