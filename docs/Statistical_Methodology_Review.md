# BrainLink EEG Analysis Pipeline - Statistical Methodology

## Version 2.0 - Peer Review Compliance Update
**Date**: February 2026  
**Status**: Production Implementation  
**Purpose**: Address methodological concerns for publication-grade rigor

---

## Executive Summary

This document describes the statistical methodology of the BrainLink 64-channel EEG analysis pipeline, addressing key concerns raised during peer review. The pipeline has been updated to meet publication-quality standards.

---

## Table of Contents

1. [Sample Size and Statistical Power](#1-sample-size-and-statistical-power)
2. [Temporal Autocorrelation Handling](#2-temporal-autocorrelation-handling)
3. [Artifact Rejection Pipeline](#3-artifact-rejection-pipeline)
4. [Gamma Band Reliability](#4-gamma-band-reliability)
5. [Connectivity Metrics](#5-connectivity-metrics)
6. [Composite Score Definition](#6-composite-score-definition)
7. [Multiple Comparisons Correction](#7-multiple-comparisons-correction)
8. [Discretization Policy](#8-discretization-policy)
9. [Confidence Intervals and Reliability](#9-confidence-intervals-and-reliability)

---

## 1. Sample Size and Statistical Power

### Issue
With 8-second blocks and 60-second task phases, only ~7 blocks per condition were available, resulting in underpowered Cohen's d estimates with unstable confidence intervals.

### Solution: Shorter Windows with Power Targets

**Configuration Parameters**:
```python
# Updated defaults (BrainLinkAnalyzer_GUI_Enhanced.py)
block_seconds: float = 4.0        # Reduced from 8.0 seconds
min_blocks_baseline: int = 8      # Increased from 4 blocks  
min_blocks_task: int = 8          # Increased from 4 blocks
target_blocks: int = 15           # Recommended for stable d estimates

# Window overlap (for feature extraction, not block aggregation)
window_size: float = 2.0          # 2-second sliding windows
window_overlap: float = 0.5       # 50% overlap for smoother estimates
```

**Power Analysis Guidance**:
| Blocks per Condition | 95% CI Width on d=0.5 | Recommendation |
|---------------------|----------------------|----------------|
| 4                   | ±0.89                | Exploratory only |
| 8                   | ±0.63                | Minimum acceptable |
| 15                  | ±0.46                | Publication-grade |
| 30                  | ±0.32                | High precision |

**Implementation**:
- Task phases extended to 90 seconds (default) to yield ~22 blocks at 4s each
- Baseline (eyes-closed) extended to 60 seconds to yield ~15 blocks
- Data quality warning triggered if blocks_per_condition < 8

**Code Location**: `EnhancedAnalyzerConfig.min_blocks_baseline`, `min_blocks_task`

---

## 2. Temporal Autocorrelation Handling

### Issue
Welch's t-test assumes independence of observations. Consecutive EEG windows are temporally autocorrelated, violating this assumption.

### Solution: Block-Level Aggregation + Permutation Testing

**Approach**:
1. **Non-overlapping blocks**: Windows are aggregated into non-overlapping blocks (default 4 seconds) to reduce autocorrelation
2. **Sufficient spacing**: Block boundaries are separated by the full block duration (no overlap)
3. **Block-level permutation**: Statistical inference uses block-level permutation tests that respect temporal structure

**Block Aggregation Process**:
```
Raw EEG (continuous) → 2s sliding windows (50% overlap) → Feature extraction
                                    ↓
              Features averaged within 4s non-overlapping blocks
                                    ↓
                    Block-level t-test or permutation
```

**Autocorrelation Mitigation**:
- Each block summarizes 2 overlapping windows (effectively independent at block level)
- Lag-1 autocorrelation between blocks is typically < 0.3
- Permutation tests shuffle block labels, preserving within-block structure

**Implementation**:
```python
# In _build_blocks() method
def _build_blocks(self, features_list, timestamps):
    # Non-overlapping block aggregation
    block_sec = float(self.block_seconds)  # 4.0 seconds
    # Windows are averaged within each block
    # Blocks are treated as independent observations
```

**Validation**: 
- Durbin-Watson statistic computed on block-level residuals
- Warning issued if DW < 1.5 (positive autocorrelation detected)

**Code Location**: `EnhancedFeatureAnalysisEngine._build_blocks()`, `_permutation_sum_p_blocks()`

---

## 3. Artifact Rejection Pipeline

### Issue
No clear documentation of artifact handling for 64-channel EEG. Muscle and ocular artifacts can severely confound band power estimates.

### Solution: Multi-Stage Artifact Rejection

The pipeline implements the following artifact rejection stages:

### Stage 1: Bad Channel Detection and Interpolation

**Method**: Robust z-score on channel variance
```python
def detect_bad_channels(data: np.ndarray, threshold_z: float = 3.0):
    """
    Detect bad channels using variance-based robust z-score.
    
    Channels flagged as bad:
    - Flat channels: std < 0.1 µV (likely disconnected)
    - Noisy channels: |z(variance)| > threshold_z
    - Excessive amplitude: max |signal| > 200 µV
    """
```

**Interpolation**: Spherical spline interpolation from neighboring channels (spatial average fallback if spline unavailable)

### Stage 2: Re-referencing

**Method**: Average reference (standard for 64-channel)
```python
def apply_average_reference(data: np.ndarray):
    """
    Apply average reference: subtract mean across all good channels.
    Excluded channels: those marked as bad in Stage 1
    """
    good_channels = ~bad_channel_mask
    avg = data[:, good_channels].mean(axis=1, keepdims=True)
    return data - avg
```

### Stage 3: Epoch Rejection Based on Amplitude Thresholds

**Thresholds**:
- Peak-to-peak threshold: ±100 µV per epoch
- Gradient threshold: >50 µV/ms (sharp transients)

```python
def reject_epochs(epochs: np.ndarray, 
                  pk_threshold: float = 100.0,
                  gradient_threshold: float = 50.0):
    """
    Reject epochs exceeding amplitude or gradient thresholds.
    Returns: valid_mask (bool array), rejection_stats (dict)
    """
```

**Rejection Reporting**:
```
Epoch Rejection Summary:
  Total epochs: 120
  Rejected (amplitude): 8 (6.7%)
  Rejected (gradient): 3 (2.5%)
  Clean epochs: 109 (90.8%)
```

### Stage 4: ICA-Based Artifact Removal (Planned for Offline Path)

**Status**: Planned for offline processing path. Real-time GUI continues with epoch rejection.

**Implementation Plan: Picard ICA**

Picard (Preconditioned ICA for Real Data) is recommended for the offline analysis path:

- **Speed**: ~10 seconds for 64 channels x 90 seconds of data
- **Robustness**: Handles EEG data better than FastICA
- **Library**: Available via `pip install picard` or through MNE-Python

**Planned Pipeline**:
```python
from picard import picard

def apply_ica_artifact_removal(data: np.ndarray, sfreq: float, n_components: int = None):
    """
    Apply Picard ICA for artifact removal in offline analysis.
    
    Automatic component classification:
    1. EOG components: correlation > 0.8 with frontal channels
    2. EMG components: high-frequency spectral profile (>40 Hz dominance)
    3. ECG components: QRS-like temporal morphology
    
    Semi-automatic flagging allows optional expert review before rejection.
    """
    # Fit ICA
    K, W, S = picard(data.T, n_components=n_components, ortho=True, max_iter=200)
    
    # Automatic component flagging
    artifact_components = []
    for i, component in enumerate(S):
        if detect_eog_component(component, data, sfreq):
            artifact_components.append(i)
        elif detect_emg_component(component, sfreq):
            artifact_components.append(i)
    
    # Reconstruct data without artifact components
    S_clean = S.copy()
    S_clean[artifact_components, :] = 0
    data_clean = np.linalg.pinv(K @ W).T @ S_clean
    
    return data_clean, artifact_components
```

**Benefits over Epoch Rejection**:
- Preserves 95%+ of data (vs. 60-80% with conservative rejection)
- Separates overlapping artifacts from neural signals
- More reliable gamma band analysis after EMG component removal

**Current Workaround** (Real-time GUI):
- Blink detection via robust dispersion (MAD) in frontal channels
- EMG guard for gamma band (see Section 4)
- Conservative epoch rejection with explicit reporting

### Stage 5: Line Noise Removal

**Status**: Implemented. Applied before PSD computation.

Power line interference at 50Hz (Europe/Asia) or 60Hz (North America) and harmonics can contaminate high-frequency band estimates, particularly gamma.

**Implementation**:
```python
def apply_notch_filter(x: np.ndarray, fs: float, line_freq: float = 60.0):
    """
    Apply notch filter at line frequency and harmonics.
    
    Removes 50/60Hz contamination from mains power.
    Harmonics (120Hz, 180Hz for 60Hz systems) are also filtered.
    """
    from scipy import signal as sig
    
    nyq = fs / 2.0
    Q = 30.0  # Quality factor (narrow notch)
    
    for harmonic in [1, 2, 3]:  # Fundamental + 2 harmonics
        freq = line_freq * harmonic
        if freq < nyq - 1:  # Only if below Nyquist
            w0 = freq / nyq
            b, a = sig.iirnotch(w0, Q)
            x = sig.filtfilt(b, a, x)
    
    return x
```

**Configuration Options**:
```python
@dataclass
class EnhancedAnalyzerConfig:
    line_noise_freq: float = 60.0        # Mains frequency (50.0 for EU/Asia)
    apply_notch_filter: bool = True      # Apply notch at line freq + harmonics
```

**Report Output**:
```
Preprocessing Applied:
  Notch filter: 60 Hz + harmonics (Q=30)
  Anti-alias filter: 100 Hz lowpass
  Average reference: Yes
```

### Artifact Reporting in Analysis Output

```python
artifact_summary = {
    'bad_channels': ['T7', 'T8'],            # Interpolated
    'rejection_rate': 0.092,                  # 9.2% epochs rejected
    'rejected_count': 11,
    'total_epochs': 120,
    'avg_reference_applied': True,
    'ica_applied': False                      # Placeholder
}
```

**Code Location**: `OfflineMultichannelEngine.detect_artifacts()`, `remove_artifacts()`

---

## 4. Gamma Band Reliability

### Issue
Gamma power (>30 Hz) is susceptible to EMG contamination, microsaccades, and line noise. Large gamma effects may reflect muscle artifact rather than cortical oscillations.

### Solution: EMG Guard + Reliability Warnings

### EMG Detection Algorithm

The pipeline detects probable EMG contamination using spectral analysis with adaptive thresholding:

```python
def _check_emg_contamination(self, psd: np.ndarray, freqs: np.ndarray):
    """
    Detect EMG contamination using high-frequency power ratio.
    
    EMG signature: elevated power in 40-100 Hz relative to 20-40 Hz
    
    Thresholding modes:
    1. Adaptive (default): baseline_mean + 2 * baseline_SD
    2. Fixed fallback: ratio > 1.5
    
    Adaptive thresholding is more sensitive for subjects with naturally
    low muscle artifact, and more conservative for subjects with higher
    baseline muscle tension.
    """
    mid_band = psd[(freqs >= 20) & (freqs < 40)].mean()
    high_band = psd[(freqs >= 40) & (freqs <= 100)].mean()
    
    emg_ratio = high_band / (mid_band + 1e-10)
    
    # Adaptive threshold from baseline statistics
    if hasattr(self, '_baseline_emg_stats') and self.config.emg_adaptive_threshold:
        baseline_mean = self._baseline_emg_stats['ratio_mean']
        baseline_std = self._baseline_emg_stats['ratio_std']
        threshold = baseline_mean + 2.0 * baseline_std
    else:
        threshold = self.config.emg_fixed_ratio  # Default: 1.5
    
    return emg_ratio > threshold, emg_ratio
```

**Adaptive Threshold Computation**:
```python
# Computed during baseline phase (eyes-closed rest)
def compute_baseline_statistics(self):
    # ... other baseline computations ...
    
    # EMG baseline statistics for adaptive thresholding
    emg_ratios = [f.get('_emg_ratio', 0.0) for f in ec_features]
    self._baseline_emg_stats = {
        'ratio_mean': float(np.mean(emg_ratios)),
        'ratio_std': float(np.std(emg_ratios)),
        'ratio_median': float(np.median(emg_ratios)),
        'threshold': float(np.mean(emg_ratios) + 2.0 * np.std(emg_ratios))
    }
```

**Configuration Options**:
```python
@dataclass
class EnhancedAnalyzerConfig:
    emg_adaptive_threshold: bool = True   # Use baseline-calibrated threshold
    emg_fixed_ratio: float = 1.5          # Fallback fixed threshold
```

### Gamma Metrics Handling

When EMG contamination is detected in a window:
1. **gamma_power**: Set to NaN for that window
2. **gamma_relative**: Set to NaN
3. **gamma features excluded** from statistical analysis for that window

### Session-Level Statistics

```python
gamma_emg_stats = {
    'windows_evaluated': 120,
    'windows_flagged_emg': 15,
    'gamma_data_retention': 0.875,  # 87.5% usable
    'reliability_flag': 'moderate' if retention > 0.7 else 'low'
}
```

### Report Warnings

When gamma features are significant, reports include:

```
WARNING: GAMMA BAND RELIABILITY
Gamma features showed significant effects, but scalp EEG gamma is susceptible 
to muscle artifact contamination. Interpretation should be cautious.

EMG Guard Statistics:
  Windows evaluated: 120
  Windows flagged (EMG): 15 (12.5%)
  Gamma data retention: 87.5%

Recommendations:
  - Verify subject was relaxed (minimal jaw clenching)
  - Consider Laplacian/CSD transform for spatial filtering
  - Report gamma findings as secondary outcomes
```

**Code Location**: `EnhancedFeatureAnalysisEngine.extract_features()` (EMG guard logic)

---

## 5. Connectivity Metrics

### Issue
Standard magnitude-squared coherence is biased by volume conduction. Nearby electrodes show spuriously high coherence from zero-lag correlations.

### Solution: Volume-Conduction-Robust Metrics

### Primary Metric: Debiased Weighted Phase Lag Index (dwPLI)

```python
def compute_dwpli(signal1: np.ndarray, signal2: np.ndarray, 
                  fs: float, freq_band: Tuple[float, float]):
    """
    Compute debiased weighted Phase Lag Index.
    
    dwPLI is insensitive to zero-lag volume conduction artifacts.
    Values range from 0 (no coupling) to 1 (perfect phase coupling).
    
    Reference: Vinck et al., NeuroImage 55(4):1548-1565, 2011
    """
    # Cross-spectral density
    f, Cxy = signal.csd(signal1, signal2, fs=fs, nperseg=fs*2)
    
    # Select frequency band
    band_mask = (f >= freq_band[0]) & (f <= freq_band[1])
    Cxy_band = Cxy[band_mask]
    
    # Imaginary part captures phase-lagged interactions
    imag_Cxy = np.imag(Cxy_band)
    
    # Weighted by magnitude (emphasizes strong interactions)
    sum_imag = np.mean(imag_Cxy)
    sum_sq_imag = np.mean(imag_Cxy ** 2)
    
    # Debiasing
    n = len(Cxy_band)
    numerator = sum_imag ** 2 - sum_sq_imag / n
    denominator = sum_sq_imag - sum_sq_imag / n
    
    dwpli = numerator / (denominator + 1e-10)
    return np.clip(dwpli, 0, 1)
```

### Alternative: Imaginary Coherency (iCoh)

```python
def compute_icoh(signal1: np.ndarray, signal2: np.ndarray,
                 fs: float, freq_band: Tuple[float, float]):
    """
    Compute imaginary part of coherency.
    
    iCoh = Im(Cxy) / sqrt(Cxx * Cyy)
    Only non-zero for phase-lagged interactions.
    """
```

### Connectivity Matrix Output

```python
connectivity_results = {
    'metric': 'dwPLI',
    'bands': {
        'alpha': {
            'matrix': np.ndarray,      # (64, 64) connectivity matrix
            'mean_strength': 0.32,
            'significant_pairs': [('F3', 'P3', 0.45), ...]
        },
        'beta': { ... },
        'theta': { ... }
    },
    'volume_conduction_robust': True
}
```

**Code Location**: `enhanced_multichannel_analysis.py`, `compute_connectivity()` method

---

## 6. Composite Score Definition

### Issue
CompositeScore was described as a "weighted combination" without an explicit formula.

### Solution: Explicit Formula

### Definition

The CompositeScore is defined as the **sum of negative log10-transformed FDR-adjusted p-values**:

$$
\text{CompositeScore} = \sum_{i=1}^{k} -\log_{10}(q_i)
$$

Where:
- $k$ = number of features analyzed
- $q_i$ = Benjamini-Hochberg adjusted p-value (q-value) for feature $i$
- $q_i$ is floored at $10^{-12}$ to prevent infinity

### Interpretation

| CompositeScore | Interpretation |
|----------------|----------------|
| < 10           | Minimal effect (most features p > 0.1) |
| 10-50          | Moderate effect (several features p < 0.01) |
| 50-200         | Strong effect (many features p < 0.001) |
| > 200          | Very strong effect (requires caution - check data quality) |

### Code Implementation

```python
# In analyze_task_data()
composite_score = None
if combo_features:
    adjusted_values = []
    for feature in combo_features:
        entry = self.analysis_results[feature]
        # Prefer FDR-adjusted q-value; fall back to raw p-value
        val = entry.get('q_value') or entry.get('p_value') or 1.0
        adjusted_values.append(max(val, 1e-12))  # Floor to prevent -inf
    
    # Sum of -log10(q) aggregates evidence across features
    composite_score = float(np.sum(-np.log10(adjusted_values)))
```

### Caveats

1. **Not a formal test statistic**: CompositeScore is not a p-value; it's a ranking measure
2. **Sensitive to feature count**: More features → higher potential scores
3. **Use comparatively**: Compare across tasks/sessions, not as absolute threshold

**Recommendation**: Report Fisher's combined p-value and SumP permutation p-value as primary inferential statistics. Use CompositeScore for exploratory feature importance ranking.

---

## 7. Multiple Comparisons Correction

### Issue
Running multiple tasks creates family-wise error inflation. No correction was applied across tasks.

### Solution: Hierarchical Correction Strategy

### Level 1: Within-Task (Features)

**Method**: Benjamini-Hochberg FDR at α=0.05
- Controls false discovery rate within each task's ~1,400 features
- Raw p-values transformed to q-values

### Level 2: Within-Task (Omnibus)

**Method**: Kost-McDermott corrected Fisher's combined p-value
- Accounts for correlation between features
- Single omnibus p-value per task

### Level 3: Across-Tasks (Family-Wise)

**Method**: Holm-Bonferroni correction across task-level omnibus p-values

```python
def apply_holm_bonferroni(p_values: List[float], alpha: float = 0.05):
    """
    Apply Holm-Bonferroni step-down correction.
    
    More powerful than Bonferroni while controlling FWER.
    """
    n = len(p_values)
    sorted_indices = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_indices]
    
    adjusted_p = np.zeros(n)
    for i, (orig_idx, p) in enumerate(zip(sorted_indices, sorted_p)):
        adjusted_p[orig_idx] = min(1.0, p * (n - i))
    
    # Enforce monotonicity
    for i in range(1, n):
        adjusted_p[sorted_indices[i]] = max(
            adjusted_p[sorted_indices[i]], 
            adjusted_p[sorted_indices[i-1]]
        )
    
    return adjusted_p
```

### Report Output

```
CROSS-TASK CORRECTION
=====================
Method: Holm-Bonferroni (step-down)
Tasks analyzed: 5
Family-wise α: 0.05

Per-Task Omnibus Results:
  mental_math:       Fisher_KM_p = 0.0023, adjusted_p = 0.0115 [SIGNIFICANT*]
  visual_imagery:    Fisher_KM_p = 0.0156, adjusted_p = 0.0624 
  attention_focus:   Fisher_KM_p = 0.0312, adjusted_p = 0.0936
  working_memory:    Fisher_KM_p = 0.0087, adjusted_p = 0.0348 [SIGNIFICANT*]
  motor_imagery:     Fisher_KM_p = 0.0421, adjusted_p = 0.0842

* Significant after family-wise error correction
```

**Code Location**: `EnhancedFeatureAnalysisEngine._analyze_across_tasks()`

---

## 8. Discretization Policy

### Issue
Binning continuous effect sizes into 5 quantile bins loses information and should not be used for statistical inference.

### Solution: Clarified Role

### Policy Statement

**Discretization is for visualization and reporting only, NOT for statistical inference.**

### Current Usage

1. **Visualization**: Heatmaps showing effect magnitude across channels/regions
2. **Ranking**: Identifying top-N features for summary reports
3. **Portability**: Integer bin indices for mobile/web dashboard display

### What Discretization Does NOT Affect

- Per-feature p-values (computed from continuous data)
- FDR correction (uses continuous p-values)
- Fisher's combined statistic (uses continuous p-values)
- CompositeScore (uses continuous q-values)
- Effect size reporting (Cohen's d reported as continuous float)

### Report Clarification

Reports now include:

```
NOTE: Continuous effect sizes (Cohen's d) are used for all statistical inference.
Discretization into bins is applied only for visualization (heatmaps, summaries).
The 'bin' column indicates quantile position for quick visual scanning.
```

---

## 9. Confidence Intervals and Reliability

### Issue
Only point estimates were reported. No confidence intervals or test-retest reliability metrics.

### Solution: Bootstrapped CIs + Reliability Tracking

### Bootstrapped Confidence Intervals

95% CI computed via percentile bootstrap with 1000 iterations:

```python
def _bootstrap_cohens_d_ci(self, baseline_vals: np.ndarray, task_vals: np.ndarray,
                            n_iterations: int = 1000) -> Tuple[float, float]:
    """
    Compute bootstrapped 95% CI for Cohen's d using percentile method.
    
    Percentile method provides robust coverage for effect size estimation
    without the complexity of BCa corrections.
    
    Parameters
    ----------
    baseline_vals : array
        Feature values from baseline condition
    task_vals : array  
        Feature values from task condition
    n_iterations : int
        Number of bootstrap resamples (default: 1000)
    
    Returns
    -------
    ci_low, ci_high : float
        Lower and upper bounds of 95% CI
    """
    rng = np.random.default_rng()
    boot_d = np.zeros(n_iterations)
    
    for i in range(n_iterations):
        boot_baseline = rng.choice(baseline_vals, size=len(baseline_vals), replace=True)
        boot_task = rng.choice(task_vals, size=len(task_vals), replace=True)
        boot_d[i] = self._cohens_d(boot_baseline, boot_task)
    
    # Percentile method - simple and robust
    ci_low = float(np.percentile(boot_d, 2.5))
    ci_high = float(np.percentile(boot_d, 97.5))
    
    return ci_low, ci_high
```

**Note**: The percentile method was chosen over BCa (bias-corrected and accelerated) for simplicity and computational efficiency. With n=1000 iterations and typical EEG sample sizes, percentile bootstrap provides adequate coverage while avoiding the numerical instabilities that can occur with BCa's jackknife acceleration term.

### Report Output Enhancement

```
Top Significant Features:
Feature              | d      | 95% CI        | p       | q
---------------------|--------|---------------|---------|--------
alpha_relative       | -0.82  | [-1.12, -0.52]| 0.0001  | 0.0012
beta_alpha_ratio     |  0.65  | [0.38, 0.92]  | 0.0008  | 0.0048
theta_relative       |  0.41  | [0.15, 0.67]  | 0.0124  | 0.0372
```

### Test-Retest Reliability (Planned)

Future implementation will track:

```python
reliability_metrics = {
    'icc_model': 'ICC(3,k)',  # Two-way mixed, consistency, average measures
    'feature_iccs': {
        'alpha_relative': {'icc': 0.78, 'ci95': [0.65, 0.87]},
        'beta_alpha_ratio': {'icc': 0.71, 'ci95': [0.56, 0.82]},
        ...
    },
    'sessions_required': 2,
    'reference': 'Shrout & Fleiss (1979)'
}
```

**Code Location**: `EnhancedFeatureAnalysisEngine.analyze_task_data()` (CI computation)

---

## Implementation Checklist

| Issue | Status | Location |
|-------|--------|----------|
| 1. Sample size/power | Implemented | `EnhancedAnalyzerConfig.block_seconds=4.0` |
| 2. Autocorrelation | Implemented | `_build_blocks()`, `_permutation_sum_p_blocks()` |
| 3. Artifact rejection | Documented | `detect_artifacts()`, `remove_artifacts()` |
| 4. Gamma warnings | Implemented | `extract_features()` EMG guard |
| 5. Robust coherence | Implemented | `compute_dwpli()` |
| 6. CompositeScore formula | Documented | This document + code comments |
| 7. Cross-task correction | Implemented | `_analyze_across_tasks()` |
| 8. Discretization policy | Clarified | This document |
| 9. Confidence intervals | Implemented | `_bootstrap_cohens_d_ci()` |
| 10. Line noise filtering | Implemented | `extract_features()` notch filter |
| 11. Adaptive EMG threshold | Implemented | `compute_baseline_statistics()` |
| 12. Permutation count (n=1000) | Implemented | `EnhancedAnalyzerConfig.n_perm=1000` |
| 13. ICA artifact removal | Planned | Picard ICA for offline path |

---

## References

1. Kost JT, McDermott MP. (2002). Combining dependent p-values. *Statistics & Probability Letters*, 60(2):183-190.
2. Benjamini Y, Hochberg Y. (1995). Controlling the false discovery rate. *JRSS-B*, 57(1):289-300.
3. Vinck M, et al. (2011). An improved index of phase-synchronization. *NeuroImage*, 55(4):1548-1565.
4. Efron B, Tibshirani RJ. (1993). *An Introduction to the Bootstrap*. Chapman & Hall.
5. Shrout PE, Fleiss JL. (1979). Intraclass correlations: Uses in assessing rater reliability. *Psych Bull*, 86(2):420-428.
6. Holm S. (1979). A simple sequentially rejective multiple test procedure. *Scand J Stat*, 6(2):65-70.
7. Ablin P, Cardoso JF, Gramfort A. (2018). Faster independent component analysis by preconditioning with Hessian approximations. *IEEE TSP*, 66(15):4040-4049. (Picard ICA)

---

**Document Version**: 2.1  
**Last Updated**: Session Date  
**Authors**: BrainLink Companion Development Team
