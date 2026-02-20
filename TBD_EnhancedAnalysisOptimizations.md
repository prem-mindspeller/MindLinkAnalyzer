# Single-Channel EEG Analysis Optimizations

**Original Date**: February 3, 2026  
**Last Updated**: February 18, 2026  
**Version**: 2.1 (Status Reconciled Against Live Codebase)

---

## ⚠️ Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ **IMPLEMENTED** | Live in codebase — do not duplicate |
| 🔄 **PARTIAL** | Partially implemented — gap noted |
| ❌ **NOT YET DONE** | Planned but not implemented |
| 🗑️ **SUPERSEDED** | Approach changed; original plan obsolete |

---

## Summary of Changes

This document tracks planned and completed optimizations to the BrainLink analysis pipeline for single-channel consumer EEG devices. Items marked ✅ are live; items marked ❌ are still pending.

---

## 🎯 Key Optimizations

### 1. Reduced Feature Set (40+ → 8 Core Features) — ❌ NOT YET DONE

**Problem**: With ~7-15 samples per condition, testing 40+ features creates severe overfitting risk.

**Planned solution**:
```python
CORE_SINGLE_CHANNEL_FEATURES = [
    'alpha_relative',      # Primary cognitive marker
    'theta_relative',      # Drowsiness/focus marker
    'beta_relative',       # Alertness/arousal marker
    'alpha_theta_ratio',   # Engagement index
    'beta_alpha_ratio',    # Arousal index
    'total_power',         # Signal strength (QC)
    'spectral_entropy',    # Complexity measure
    'peak_alpha_freq',     # Individual alpha frequency
]
```

**Current reality**: `EnhancedFeatureAnalysisEngine` still uses the full feature set. The `CORE_SINGLE_CHANNEL_FEATURES` list, `EXCLUDED_SINGLE_CHANNEL_FEATURES`, and `SINGLE_CHANNEL_BANDS` constants from this document do **not yet exist** in the codebase. The `EnhancedAnalyzerConfig` class (in `BrainLinkAnalyzer_GUI_Enhanced.py`) has no `single_channel_mode`, `use_core_features_only`, `exclude_split_bands`, or `use_iaf_adaptive_bands` fields.

---

### 2. Gamma Band — 🔄 PARTIAL (EMG guard exists, exclusion not yet enforced)

**Problem**: Gamma (30-45 Hz) is dominated by EMG artifacts from facial muscles in single-channel frontal EEG.

**Current state**: An EMG guard is already tracking gamma windows:
```python
# In EnhancedFeatureAnalysisEngine.__init__:
self.gamma_windows_total = 0
self.gamma_windows_kept = 0
```
The analysis engine notes `'Gamma evaluation guarded by EMG flag in some windows'` in results. However, gamma is still **included** in task thresholds (e.g. `mental_math`, `attention_focus`, `visual_imagery`) and the feature pipeline does not have a hard `exclude_gamma = True` flag. Grade-A scoring for `mental_math` still requires `gamma_up`.

**Remaining work**: Add `exclude_gamma: bool = True` to `EnhancedAnalyzerConfig` and gate all gamma feature extraction and scoring behind it.

---

### 3. Split Bands Removed — ❌ NOT YET DONE

**Problem**: Sub-band distinctions (theta1/theta2, beta1/beta2) require high SNR that consumer devices lack.

**Current state**: Not implemented. `EnhancedAnalyzerConfig` has no `exclude_split_bands` field.

---

### 4. Individual Alpha Frequency (IAF) Adaptive Bands — ❌ NOT YET DONE

**Current state**: Fixed frequency bands are still used. No `use_iaf_adaptive_bands` flag or `get_iaf_adaptive_bands()` method exists.

---

### 5. Two-Sided Tests Only — 🔄 PARTIAL

**Current state**: `EnhancedAnalyzerConfig` has `use_directional_priors: bool` field — **not yet added**. Directional priors logic in `assess_significance` has not been toggled. The `use_two_sided_tests` field from this document does not exist in the config.

---

### 6. Bonferroni Correction — 🗑️ SUPERSEDED

**Original plan**: Replace Kost-McDermott with Bonferroni for small n.

**Current state**: `EnhancedAnalyzerConfig` uses `dependence_correction: str = "Kost-McDermott"` and `use_permutation_for_sumP: bool = True`. There is no `use_bonferroni` nor `use_kost_mcdermott` boolean flag. The correction method is selected via the string field `dependence_correction` which accepts choices from `DEPENDENCE_CORRECTION_CHOICES`.

**Updated approach**: To switch to simpler correction, set `dependence_correction = "Bonferroni"` (if that choice exists in `DEPENDENCE_CORRECTION_CHOICES`) or extend the choices list. Do not add separate boolean flags — use the existing string field.

---

### 7. Reduced Permutation Count — ✅ IMPLEMENTED (partially)

**Current state**: `n_perm` defaults to `1000` (already reduced from the original 5000). The config docstring notes:
> Performance: ~1000 permutations/second for 50 features

The `runtime_preset` mechanism allows further reduction via `PERM_PRESETS`. The planned default of `500` from this document has **not** been applied — the current default is `1000`.

**Remaining**: If 500 is desired for small-n sessions, set `n_perm = 500` as the default or add a `small_n_mode` preset.

---

### 8. Unified Significance Thresholds — ✅ IMPLEMENTED

**Current state**: Live in `EnhancedAnalyzerConfig`:
```python
min_effect_size: float = 0.5      # Cohen's d — medium effect (matches plan)
min_percent_change: float = 10.0  # Practical significance (plan said 15.0 — slight gap)
p_value_threshold: float = 0.05   # Standard alpha (via fdr_alpha field)
```
The `min_percent_change` default is `10.0`, not `15.0` as planned. Adjust if stricter practical significance is desired.

---

### 9. Honest Confidence Reporting — ❌ NOT YET DONE

**Current state**: The `AnalysisConfidence` dataclass and `interpret_analysis_confidence()` function from this document do **not exist** in the codebase. The `show_confidence_levels` and `show_limitations_warnings` config fields are not present in `EnhancedAnalyzerConfig`.

---

## ✅ Changes Implemented Since This Document Was Written

These are real improvements made to the pipeline that were **not in the original plan**:

### A. EC Baseline Not-Worn Rejection ✅
Window-level rejection now runs during eyes-closed calibration using a robust MAD-scale gate:
```python
# In EnhancedFeatureAnalysisEngine (BrainLinkAnalyzer_GUI_Enhanced.py):
scale = 1.4826 * mad   # Robust std estimate (µV)
is_not_worn = scale > 250.0          # Headset off — broadband noise
is_extreme_artifact = (not is_not_worn) and np.sum(outliers) > (len(x) * 0.05)
is_flatline = scale < 0.5            # Disconnected lead

# Per-reason rejection counters tracked:
self.baseline_rejected_not_worn    # Windows rejected because headset was off
self.baseline_rejected_artifact    # Extreme blink/motion
self.baseline_rejected_flatline    # Disconnected lead
self._ec_accepted_scales           # MAD-scale of every accepted window
```
Valid window: `0.5 µV ≤ scale ≤ 250 µV` and no extreme outliers (`>20×scale` in >5% of samples).

### B. Data Quality Assessment Section in Report ✅
The generated report includes a 4-tier Data Quality Assessment block surfacing calibration statistics:
- **OK** — all windows accepted, noise within normal range
- **WARNING** — some windows rejected or borderline noise
- **HIGH NOISE FLOOR** — median accepted-window MAD-scale > 150 µV
- **CRITICAL** — majority of windows rejected or headset likely not worn during calibration

### C. Signal Quality Indicator — Live Assessment (assess_eeg_signal_quality) ✅
A spectral-analysis-based signal quality function `assess_eeg_signal_quality()` runs continuously at 500ms in the UI (header, calibration dialog, live EEG dialog, prep dialogs). It uses:
- Low-frequency dominance (delta+theta must be >30% of total power)
- Spectral slope (must be < −0.3; real EEG is 1/f)
- High-frequency ratio (must be <50%)

Status values: `not_worn`, `good`, `acceptable`, `poor`, `severe_artifacts`, `motion_artifacts`.

**Hysteresis**: Status only flips to "Noisy" after 3 continuous seconds of `not_worn`. On first detection the clock is pre-aged by 3s so a headset already off when a dialog opens shows Noisy immediately.

### D. Task Description Auto-Select and Advanced Task Booking Gate ✅
- Task description field auto-populates on `task_combo` change
- Advanced tasks gated behind `has_advanced_booking` check via `_fetch_partner_bookings()`

---

## 📊 Before vs After Comparison (Updated)

| Aspect | Planned (Feb 3) | Current State | Status |
|--------|----------------|---------------|--------|
| Features tested | 8 core | 40+ (unchanged) | ❌ |
| Gamma included | Excluded | Guarded but included | 🔄 |
| Split bands | Excluded | Still included | ❌ |
| IAF adaptive bands | Yes | No | ❌ |
| Directional priors | Disabled | Still enabled | 🔄 |
| Correction method | Bonferroni | Kost-McDermott (string field) | 🗑️ superseded |
| Permutations | 500 | 1000 default | 🔄 |
| Effect threshold | Cohen's d 0.5 | 0.5 ✅ | ✅ |
| Min % change | 15% | 10% | 🔄 |
| Confidence reporting | AnalysisConfidence dataclass | Not implemented | ❌ |
| EC window rejection | (not planned) | MAD-scale gate, 250 µV ✅ | ✅ new |
| Data quality in report | (not planned) | 4-tier quality block ✅ | ✅ new |
| Live signal quality | (not planned) | Spectral assess + 3s hysteresis ✅ | ✅ new |

---

## 🔧 Configuration — Current Actual Fields

The real `EnhancedAnalyzerConfig` in `BrainLinkAnalyzer_GUI_Enhanced.py` (as of Feb 18 2026):

```python
@dataclass
class EnhancedAnalyzerConfig:
    alpha: float = 0.05
    mode: str = "aggregate_only"
    dependence_correction: str = "Kost-McDermott"
    use_permutation_for_sumP: bool = True
    n_perm: int = 1000
    discretization_bins: int = 5
    export_profile: str = "full"
    effect_measure: str = "delta"
    omnibus: str = "Friedman"
    posthoc: str = "Wilcoxon"
    fdr_alpha: float = 0.05
    seed: Optional[int] = None
    runtime_preset: Optional[str] = None
    min_effect_size: float = 0.5
    min_percent_change: float = 10.0
    correlation_guard: bool = True
    block_seconds: float = 8.0
    mt_tapers: int = 3
    nmin_sessions: int = 2
```

The following fields from this document's original plan **do not yet exist** and need to be added when implementing the remaining items:
- `single_channel_mode: bool`
- `use_core_features_only: bool`
- `exclude_gamma: bool`
- `exclude_split_bands: bool`
- `use_iaf_adaptive_bands: bool`
- `use_directional_priors: bool`
- `use_bonferroni: bool` ← or use the existing `dependence_correction` string instead
- `use_kost_mcdermott: bool` ← same
- `show_confidence_levels: bool`
- `show_limitations_warnings: bool`

---

## 🚀 Remaining Implementation Order (Suggested)

Priority order based on impact vs effort:

1. **`exclude_gamma` flag** — easiest win, already partially guarded; just needs a config field and filter in feature extraction + scoring
2. **`n_perm = 500` default** — one-line change if small-n mode is desired
3. **`min_percent_change = 15.0`** — tighten practical significance threshold
4. **`use_directional_priors = False`** — requires identifying where priors are applied in `assess_significance` and gating them
5. **`exclude_split_bands`** — remove theta1/theta2/beta1/beta2 from feature extraction
6. **`use_core_features_only`** — filter feature list to `CORE_SINGLE_CHANNEL_FEATURES` before statistical testing
7. **`AnalysisConfidence` + `interpret_analysis_confidence()`** — add dataclass and wire into report output
8. **`use_iaf_adaptive_bands`** — most complex; requires per-session IAF estimation pass

---

## 🔬 Scientific Justification (Unchanged)

### Why 8 Features?
The selected features are validated in single-channel EEG research, robust to noise, sufficiently independent to avoid redundancy, and interpretable for end users.

### Why No Gamma?
```
Gamma band (30-45 Hz):
- Scalp amplitude: ~1-2 µV (extremely weak)
- Consumer device noise floor: 10-50 µV
- Signal-to-noise ratio: <0.1 (unusable)
- EMG contamination: Dominant in frontal electrodes
```

### Why Relative Power?
Absolute power varies with electrode impedance, scalp thickness, hair density, and device placement. Relative power normalizes these factors, making cross-session and cross-subject comparisons valid.

### Why MAD-Scale for Baseline Rejection?
MAD (Median Absolute Deviation) is resistant to the extreme outliers that corrupt the mean and standard deviation during blink and motion artifacts. The 1.4826 scaling factor makes it a consistent estimator of standard deviation under Gaussian noise.

---

## 🔗 For ANT Neuro 64-channel Integration

When integrated (see `antNeuro/` folder):
- Use full feature set (`single_channel_mode=False`, all 40+ features)
- Enable gamma band (64-channel has better EMG rejection via spatial filtering)
- Add spatial features: coherence, asymmetry, source localization
- Use Kost-McDermott correction (sufficient samples from high-density array)
- Consider IAF estimation from occipital channels (more reliable than frontal)

---

**Document Version**: 2.1  
**Last Updated**: February 18, 2026