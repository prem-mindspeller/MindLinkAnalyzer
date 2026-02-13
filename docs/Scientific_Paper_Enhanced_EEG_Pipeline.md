# Multi-Channel EEG Analysis Pipeline: From Acquisition to Statistical Inference

**Authors**: BrainLink Companion Development Team  
**Affiliation**: MindLink Research Laboratory  
**Date**: February 2026  
**Version**: 2.0  

---

## Abstract

**Background**: Multi-Channel Analysis pipeline for Neuroprofiling.

**Methods**: We describe the full end-to-end multi-channel EEG analysis pipeline implemented in the BrainLink Companion platform. The system is built around three integrated engines: (1) a **Live Feature Extraction Engine** (`Enhanced64ChannelEngine`) for real-time 64-channel feature computation during streaming, (2) an **Offline Recording and Analysis Engine** (`OfflineMultichannelEngine`) that adds raw-data persistence, phase-marker management, artifact detection, artifact removal, and offline re-analysis, and (3) a **Statistical Analysis Engine** (`EnhancedFeatureAnalysisEngine`) that provides block-level aggregation, per-feature Welch's t-tests with Hedges' g effect sizes and bootstrap confidence intervals, Benjamini–Hochberg false discovery rate (FDR) correction, Fisher's combined probability with Kost–McDermott correlation correction, block-level SumP permutation testing, multi-task comparison via Friedman/Wilcoxon tests, and cross-task familywise error rate (FWER) control via Holm–Bonferroni step-down. Quality assurance includes automated garbage/not-worn detection and expectation-alignment grading. A dedicated report generator (`Enhanced64ChannelReportGenerator`) produces interpretive summaries with regional, asymmetry, coherence, and topographic analyses.

**Results (Current Validation Status)**: We have run **three "cap not worn" datasets** through the pipeline; all three were correctly flagged as **garbage/not worn** by the automated quality detector. No large-scale sensitivity, specificity, or false-positive rate benchmarking has been performed.

**Conclusions**: The pipeline provides a complete, configurable framework for multi-channel EEG analysis spanning preprocessing, feature extraction (~1,500–2,000 features per window), multi-level statistical testing with multiple-comparison correction, and automated quality checks. Further validation with diverse populations and artifact conditions is planned as future work.

**Keywords**: EEG, 64-channel, ANT Neuro, Welch PSD, block aggregation, Welch's t-test, bootstrap confidence interval, Hedges' g, Benjamini–Hochberg FDR, Fisher's combined probability, Kost–McDermott correction, SumP permutation test, Holm–Bonferroni, Friedman test, garbage detection, report generation

---

## 1. Introduction and Scope

### 1.1 Motivation

Dense-array EEG systems (≥64 channels) generate high-dimensional data streams that require systematic preprocessing, feature extraction, and statistical testing before physiologically meaningful conclusions can be drawn. Consumer and research applications demand pipelines that are both computationally efficient (for real-time feedback) and statistically rigorous (for offline analysis and reporting).

### 1.2 System Architecture

The BrainLink Companion multi-channel analysis pipeline is organized into three cooperating engine classes plus a report generator:

| Component | Class | Source File |
|-----------|-------|-------------|
| Live Feature Extraction | `Enhanced64ChannelEngine` | `antNeuro/enhanced_multichannel_analysis.py` |
| Offline Recording & Analysis | `OfflineMultichannelEngine` | `antNeuro/offline_multichannel_analysis.py` |
| Statistical Analysis (base) | `EnhancedFeatureAnalysisEngine` | `BrainLinkAnalyzer_GUI_Enhanced.py` |
| Report Generation | `Enhanced64ChannelReportGenerator` | `utils/enhanced_report_generator.py` |

`Enhanced64ChannelEngine` inherits from `EnhancedFeatureAnalysisEngine`, so the live engine automatically gains access to all statistical methods. `OfflineMultichannelEngine` inherits from `Enhanced64ChannelEngine`, adding raw-data persistence and artifact handling on top of the full feature-extraction and statistical stack.

### 1.3 Hardware Target

The pipeline targets the **ANT Neuro eego™ mylab** system:
- 64 EEG channels in the **NA-265 (10-20 extended)** layout
- Sampling rate: **500 Hz**
- Channel names: Fp1, Fp2, AF3, AF4, AF7, AF8, F1–F8, Fz, FT7, FT8, FC1–FC6, T7, T8, C1–C6, Cz, TP7, TP8, CP1–CP6, CPz, P1–P8, Pz, PO3, PO4, PO7, PO8, O1, O2, Oz

---

## 2. Data Acquisition and Session Management

### 2.1 Live Streaming Path

During live recording, samples arrive as $(64 \times 1)$ vectors at 500 Hz. The `Enhanced64ChannelEngine` maintains a circular ring buffer per channel (default capacity: 5 seconds = 2,500 samples). Feature extraction is triggered every **2-second window** with **50% overlap** (1-second stride), throttled to a maximum rate of ~2 Hz to avoid redundant computation.

### 2.2 Offline Recording Path

The `OfflineMultichannelEngine` extends the live path by simultaneously writing every incoming sample to a **CSV file** in real time:

```
timestamp, CH1, CH2, ..., CH64
1706100000.123, -12.5, 8.3, ..., 3.1
```

Each session generates:
- `raw_data_{session_id}_{email}.csv` — raw EEG samples with Unix timestamps
- `phase_markers_{session_id}_{email}.json` — phase start/stop times, types, and metadata

### 2.3 Phase Marker System

The session protocol is organized into sequential **phases**, each marked with a type and optional metadata:

| Phase Type | Purpose | `record` Flag |
|------------|---------|---------------|
| `eyes_closed` | Resting-state baseline (eyes closed) | `True` |
| `eyes_open` | Resting-state baseline (eyes open) | `True` / `False` |
| `task` | Active cognitive task | `True` |
| `countdown` | Pre-task countdown period | `False` |

Only phases with `record=True` contribute feature windows to analysis. Each phase records its start time, end time, and metadata (task label, subtask type) in the JSON markers file. During offline re-analysis, these markers are used to slice the raw CSV into condition-specific epochs.

### 2.4 Session Metadata

Each session stores subject metadata (ID, age, email) and hardware configuration (sample rate, channel count, channel names) for provenance tracking. The email identifier is embedded in filenames to enable multi-subject file management.

---

## 3. Preprocessing

All preprocessing is applied per-channel before feature extraction.

### 3.1 DC Offset Removal

The mean of the entire window is subtracted from each channel independently:

$$x'_c[n] = x_c[n] - \frac{1}{N}\sum_{k=1}^{N} x_c[k]$$

where $x_c[n]$ is the raw signal for channel $c$ and $N$ is the window length.

### 3.2 Line Noise Removal

A **60 Hz IIR notch filter** (Q = 30) is applied via zero-phase filtering (`scipy.signal.filtfilt`) to suppress powerline interference without introducing phase distortion:

$$H(z) = \frac{1 - 2\cos(2\pi f_0 / f_s)z^{-1} + z^{-2}}{1 - 2r\cos(2\pi f_0 / f_s)z^{-1} + r^2 z^{-2}}$$

where $f_0 = 60$ Hz and $r$ is determined by the quality factor $Q = 30$. The configurable parameter `line_noise_freq` defaults to 60 Hz (North American standard) but can be set to 50 Hz for European deployments.

### 3.3 Extended Preprocessing (Single-Channel Path)

When operating in single-channel mode (e.g., BrainLink headband), the `EnhancedFeatureAnalysisEngine` applies additional harmonic notch filters at 120 Hz and 180 Hz (2nd and 3rd harmonics of 60 Hz) for deeper line-noise suppression. The 64-channel engine uses only the fundamental notch to reduce computational overhead.

### 3.4 Artifact Detection (Offline Engine)

The `OfflineMultichannelEngine` implements automated artifact detection during offline re-analysis using three criteria:

1. **Flat channels**: Channels with standard deviation < 0.1 µV across the entire recording are flagged as electrically dead or disconnected.

2. **Noisy channels**: Channels with standard deviation > 200 µV are flagged as excessively noisy (likely due to poor electrode contact or environmental noise).

3. **High-amplitude windows**: Sliding windows in which the peak-to-peak amplitude exceeds a configurable threshold are marked as artifact segments (e.g., movement artifacts, eye blinks, muscle bursts).

```
Artifact Detection Summary:
  bad_channels: [list of flat or noisy channel indices]
  artifact_windows: [(start_sample, end_sample), ...]
  channel_quality: {channel_idx: quality_score}  # 0.0 to 1.0
```

### 3.5 Artifact Removal (Offline Engine)

Artifacts identified in §3.4 are removed through two mechanisms:

- **Bad channel interpolation**: Channels flagged as flat or noisy are replaced by the **mean of their immediate spatial neighbors** (based on the 10-20 extended layout adjacency map). This is a nearest-neighbor spherical interpolation approximation.

- **Artifact window interpolation**: Time segments flagged as high-amplitude artifacts are replaced by **linear interpolation** between the clean samples immediately before and after the artifact window. This preserves temporal continuity without introducing spectral artifacts.

Both operations are applied in-place to the raw data matrix before feature extraction proceeds.

---

## 4. Feature Extraction

### 4.1 Spectral Estimation

Power spectral density (PSD) is estimated using **Welch's method** (`scipy.signal.welch`):

- `nperseg` = min(sample count, 256) — segment length
- `noverlap` = `nperseg // 2` — 50% segment overlap
- Window function: Hann (default)
- Detrending: constant

This yields a frequency-resolution of approximately $f_s / \text{nperseg} \approx 2$ Hz for the default segment length.

For the single-channel path, the `EnhancedFeatureAnalysisEngine` uses **multitaper PSD estimation** with DPSS (Discrete Prolate Spheroidal Sequence) tapers (NW = 4, K = 7) for improved spectral leakage control. The 64-channel path uses Welch's method for computational efficiency (~64× fewer PSDs to compute).

### 4.2 Canonical Frequency Bands

Five canonical frequency bands are defined:

| Band | Range (Hz) | Neural Correlate |
|------|-----------|-----------------|
| Delta | 0.5 – 4 | Deep sleep, pathology |
| Theta | 4 – 8 | Memory, drowsiness |
| Alpha | 8 – 13 | Relaxed wakefulness, inhibition |
| Beta | 13 – 30 | Active thinking, focus |
| Gamma | 30 – 45 | Higher cognition, binding |

The single-channel engine additionally computes **sub-bands**: theta1 (4–6 Hz), theta2 (6–8 Hz), beta1 (13–20 Hz), beta2 (20–30 Hz).

Band power is computed by integrating the PSD across the band limits using `numpy.trapz` (trapezoidal integration over frequency bins within the band).

### 4.3 Per-Channel Features (~17 features × 64 channels)

For each of the 64 channels, the following features are computed:

| Feature | Formula / Description |
|---------|----------------------|
| `{ch}_delta_power` … `{ch}_gamma_power` | Absolute band power (µV²/Hz) |
| `{ch}_delta_relative` … `{ch}_gamma_relative` | Relative power: $P_{band} / P_{total}$ |
| `{ch}_peak_freq` | Frequency of maximum PSD amplitude (Hz) |
| `{ch}_alpha_theta_ratio` | $P_{\alpha} / P_{\theta}$ — alertness marker |
| `{ch}_beta_alpha_ratio` | $P_{\beta} / P_{\alpha}$ — engagement marker |
| `{ch}_total_power` | Total power across 0.5–45 Hz |

This yields approximately **1,088 per-channel features** (17 × 64).

### 4.4 Regional Aggregate Features

Channels are grouped into five anatomical regions:

| Region | Channels |
|--------|----------|
| Frontal | Fp1, Fp2, AF3, AF4, AF7, AF8, F1–F8, Fz, FC1–FC6 |
| Central | C1–C6, Cz, CP1–CP6 |
| Temporal | T7, T8, FT7, FT8, TP7, TP8 |
| Parietal | P1–P8, Pz, PO3, PO4, PO7, PO8 |
| Occipital | O1, O2, Oz |

For each region, the mean across member channels is computed for all band powers, relative powers, peak frequency, alpha/theta ratio, beta/alpha ratio, and total power — yielding approximately **85 regional features** (17 × 5).

### 4.5 Hemispheric Asymmetry Features

Asymmetry is computed for **27 homologous left-right channel pairs** (e.g., Fp1/Fp2, F3/F4, C3/C4, P3/P4, O1/O2, T7/T8, etc.):

$$A_{pair,band} = \ln(P_{right,band}) - \ln(P_{left,band})$$

This log-ratio formulation follows the convention used in frontal alpha asymmetry (FAA) research (Allen et al., 2004). For each pair, asymmetry is computed across all 5 bands, yielding **135 asymmetry features** (27 pairs × 5 bands). Additionally, a dedicated **frontal alpha asymmetry (FAA)** feature is computed from the F4/F3 pair.

### 4.6 Inter-Regional Coherence Features

Magnitude-squared coherence is computed between **representative channels** from five region pairs:

| Region Pair | Left Channel | Right Channel |
|-------------|-------------|---------------|
| Frontal–Parietal | F3 | P3 |
| Frontal–Occipital | F3 | O1 |
| Frontal–Temporal | F3 | T7 |
| Parietal–Occipital | P3 | O1 |
| Temporal–Parietal | T7 | P3 |

Coherence is computed using `scipy.signal.coherence` with `nperseg = min(n_samples, 256)` and averaged across frequency bins within each canonical band. This yields **25 coherence features** (5 pairs × 5 bands) that index functional connectivity between brain regions.

### 4.7 Global Field Power (GFP)

Global Field Power quantifies the overall spatial variance of the EEG at each time point:

$$\text{GFP}[n] = \sqrt{\frac{1}{K}\sum_{c=1}^{K}\left(x_c[n] - \bar{x}[n]\right)^2}$$

where $K$ is the number of channels and $\bar{x}[n]$ is the cross-channel mean at time $n$. Three summary statistics are extracted: `gfp_mean`, `gfp_std`, and `gfp_max`.

### 4.8 Global Summary Features

Additional summary features aggregate across all channels:
- `mean_total_power`: Global mean of per-channel total power
- `mean_alpha_theta_ratio`: Global mean alpha/theta ratio (arousal index)

### 4.9 EMG Contamination Guard (Single-Channel Path)

The single-channel engine (`EnhancedFeatureAnalysisEngine.extract_features`) implements an EMG (electromyographic) contamination guard to prevent muscle artifact from inflating gamma-band features:

1. **HF/MF Ratio**: Compute the ratio of high-frequency power (35–45 Hz) to mid-frequency power (20–30 Hz).
2. **Spectral Slope**: Fit a linear slope to the PSD between 20–45 Hz. A positive or near-zero slope (rather than the expected negative slope of neural signals) indicates EMG contamination.
3. **Adaptive Threshold**: During baseline (eyes-closed), the distribution of HF/MF ratios is recorded. The EMG threshold is set to $\mu_{baseline} + 2\sigma_{baseline}$. If fewer than 10 baseline windows are available, a fixed fallback threshold of 1.5 is used.
4. **Feature Gating**: If a window is flagged as EMG-contaminated, its gamma-band features are **removed** (set to `None` or excluded) from statistical analysis, preventing muscle activity from being mistaken for cortical gamma oscillations.

### 4.10 Feature Count Summary

| Category | Feature Count (approximate) |
|----------|---------------------------|
| Per-channel (64 channels × 17 features) | 1,088 |
| Regional (5 regions × 17 features) | 85 |
| Hemispheric asymmetry (27 pairs × 5 bands + FAA) | 136 |
| Inter-regional coherence (5 pairs × 5 bands) | 25 |
| Global Field Power (3 statistics) | 3 |
| Global summaries | 2 |
| **Total per window** | **~1,339** |

The exact count varies slightly depending on channel quality (artifact-excluded channels contribute no features) and EMG gating (EMG-contaminated windows have gamma features removed).

---

## 5. Baseline Calibration

### 5.1 Eyes-Closed Baseline

The resting-state eyes-closed phase serves as the reference condition for all subsequent statistical comparisons. During this phase, feature windows are accumulated and per-feature descriptive statistics are computed:

$$\mu_{feat} = \frac{1}{W}\sum_{w=1}^{W} x_{feat}^{(w)}, \quad \sigma_{feat} = \sqrt{\frac{1}{W-1}\sum_{w=1}^{W}\left(x_{feat}^{(w)} - \mu_{feat}\right)^2}$$

where $W$ is the number of baseline windows and $x_{feat}^{(w)}$ is the value of a given feature in window $w$.

### 5.2 EMG Baseline Statistics

For single-channel analysis, the eyes-closed phase also establishes the adaptive EMG threshold:

$$\text{EMG}_{threshold} = \mu_{HF/MF} + 2 \cdot \sigma_{HF/MF}$$

This threshold is used for all subsequent task windows. If the baseline has insufficient windows (< 10), the fallback threshold of 1.5 is used.

---

## 6. Block-Level Aggregation

### 6.1 Rationale

Individual 2-second feature windows exhibit considerable temporal autocorrelation. Using windows as the statistical unit inflates the effective sample size and leads to anti-conservative p-values. To mitigate this, features are aggregated into **non-overlapping blocks** before statistical testing.

### 6.2 Block Construction

The `_build_blocks()` method partitions the sequence of feature windows into non-overlapping blocks of configurable duration (default: **4 seconds** = 2 consecutive windows at 2s/window):

$$B_j = \frac{1}{|W_j|}\sum_{w \in W_j} x_{feat}^{(w)}$$

where $W_j$ is the set of windows belonging to block $j$ and $|W_j|$ is the number of windows per block. Each block produces a single mean feature value, and the block becomes the unit of statistical analysis.

### 6.3 Block Equalization

To prevent unequal sample sizes from biasing statistical tests, the `_equalize_blocks()` method downsamples the larger condition (baseline or task) to match the smaller:

- If $n_{baseline\_blocks} > n_{task\_blocks}$: randomly select $n_{task\_blocks}$ baseline blocks.
- If $n_{task\_blocks} > n_{baseline\_blocks}$: randomly select $n_{baseline\_blocks}$ task blocks.

The minimum number of blocks per condition required for analysis to proceed is **8** (configurable via `min_blocks_per_condition`).

---

## 7. Per-Feature Statistical Testing

### 7.1 Welch's Two-Sample t-Test

For each feature $f$, the null hypothesis $H_0: \mu_{task,f} = \mu_{baseline,f}$ is tested using Welch's t-test (unequal variances):

$$t = \frac{\bar{x}_{task} - \bar{x}_{baseline}}{\sqrt{\frac{s_{task}^2}{n_{task}} + \frac{s_{baseline}^2}{n_{baseline}}}}$$

Degrees of freedom are estimated via the Welch–Satterthwaite equation. This test does not assume equal variance between conditions, making it robust to the heteroscedasticity commonly observed in EEG power measures.

The implementation uses a custom `_welch_ttest()` that computes the t-statistic, degrees of freedom, and two-tailed p-value without depending on SciPy's `ttest_ind` (enabling a minimal-dependency deployment).

### 7.2 Effect Size: Hedges' g with Bootstrap Confidence Interval

For each feature, the standardized effect size is computed as **Hedges' g** (bias-corrected Cohen's d):

$$g = \left(\frac{\bar{x}_{task} - \bar{x}_{baseline}}{s_{pooled}}\right) \cdot J$$

where $s_{pooled}$ is the pooled standard deviation and $J = 1 - \frac{3}{4(n_1 + n_2) - 9}$ is the Hedges small-sample correction factor.

In the offline engine (`OfflineMultichannelEngine`), the denominator uses the **baseline SD** alone (Glass's $\Delta$ formulation) rather than a pooled SD, as the baseline condition is typically more stable and serves as the reference distribution. The correction factor $J$ is still applied.

A **95% bootstrap confidence interval** is computed around Hedges' g using the **percentile method**:

1. Draw $B = 1000$ bootstrap resamples (with replacement) from both task and baseline block distributions.
2. For each resample, compute Hedges' g.
3. The CI bounds are the $2.5^{th}$ and $97.5^{th}$ percentiles of the bootstrap distribution.

A CI that excludes zero provides additional evidence for a genuine effect, independent of p-value significance.

### 7.3 Percent Change

The relative change from baseline is computed for interpretability:

$$\Delta\% = \frac{\bar{x}_{task} - \bar{x}_{baseline}}{\bar{x}_{baseline}} \times 100$$

---

## 8. Multiple Comparison Correction

With ~1,300 features tested simultaneously, false discovery control is critical.

### 8.1 Benjamini–Hochberg False Discovery Rate (FDR)

The primary correction uses the **Benjamini–Hochberg (BH) procedure** (Benjamini & Hochberg, 1995):

1. Sort the $m$ raw p-values: $p_{(1)} \leq p_{(2)} \leq \ldots \leq p_{(m)}$.
2. Find the largest $k$ such that $p_{(k)} \leq \frac{k}{m} \cdot \alpha$.
3. Reject all hypotheses $H_{(1)}, \ldots, H_{(k)}$.

Equivalently, the adjusted p-value (q-value) for each feature is:

$$q_{(i)} = \min\left(\frac{p_{(i)} \cdot m}{i},\ q_{(i+1)}\right)$$

enforcing monotonicity from the largest rank downward. The default FDR level is $\alpha = 0.05$.

### 8.2 Significance Decision Logic

A feature is declared **significant** if it meets **any** of the following criteria:

| Criterion | Threshold |
|-----------|-----------|
| Adjusted p-value (q-value) | $q < 0.05$ |
| Effect size magnitude | $|g| > 0.5$ (medium effect) |
| Percent change magnitude | $|\Delta\%| > 15\%$ |

This multi-gate approach prevents the system from missing practically meaningful effects that may not reach statistical significance with limited sample sizes, while the FDR gate controls the false discovery rate for the p-value channel.

### 8.3 Directional Priors (Expected Direction)

For known task types, the system applies **directional priors** — expected directions of change — to supplement the significance decision. For example:

| Task Type | Expected Feature Change |
|-----------|------------------------|
| `meditation` | Alpha increase, beta decrease |
| `focus` / `concentration` | Beta increase, theta decrease |
| `relaxation` | Alpha increase, theta increase |
| `memory` | Theta increase |
| `40hz_stimulation` | Gamma increase (specifically 38–42 Hz) |

Directional priors do not modify p-values. Instead, they are used (1) for the **expectation alignment grading** (§10.3) and (2) to select the `expected_direction` field in the significance decision, enabling directional reporting ("alpha increased as expected during meditation").

---

## 9. Omnibus Tests

Per-feature tests establish which individual features differ between conditions. Omnibus tests address the global question: **does the task condition differ from baseline at all?**

### 9.1 Fisher's Combined Probability Test with Kost–McDermott Correction

Fisher's method combines $m$ independent p-values into a single test statistic:

$$X^2 = -2\sum_{i=1}^{m} \ln(p_i)$$

Under the null hypothesis (all $H_0$ true), $X^2 \sim \chi^2_{2m}$ if the tests are independent.

EEG features are typically correlated (e.g., alpha power at neighboring channels), which violates the independence assumption and inflates the combined statistic. The **Kost–McDermott (KM) correction** adjusts the degrees of freedom by estimating the effective number of independent tests:

1. Compute the Spearman rank correlation matrix $\mathbf{R}$ across features using block-level data.
2. Calculate $c = \text{var}(X^2) / \text{var}(\chi^2_{2m})$ — the variance inflation factor due to correlation.
3. Adjust the chi-squared test to use scaled degrees of freedom: $X^2 / c \sim \chi^2_{2m/c}$.

The implementation (`_fishers_method` and `_km_from_corr`) computes the Spearman correlation from the discretized feature ranks (to improve robustness), then derives the adjusted p-value. Features with missing or constant values are excluded from the correlation computation.

### 9.2 Block-Level SumP Permutation Test

The SumP permutation test provides a non-parametric omnibus p-value that makes no distributional assumptions:

1. Compute the observed sum of $-\log_{10}(p_i)$ across all features: $T_{obs} = \sum_i -\log_{10}(p_i)$.
2. For each of $B$ permutations (default: 1,000 in standard mode, 100 in fast mode):
   a. Randomly shuffle condition labels (baseline vs. task) **at the block level**, preserving the temporal structure within blocks.
   b. Re-run the per-feature Welch's t-tests on the permuted data.
   c. Compute the permuted sum $T_{\pi}$.
3. The permutation p-value is:

$$p_{perm} = \frac{|\{T_{\pi} \geq T_{obs}\}| + 1}{B + 1}$$

The block-level permutation (implemented in `_permutation_sum_p_blocks`) respects the temporal autocorrelation structure that window-level permutation would destroy. The $+1$ in numerator and denominator follows the Phipson & Smyth (2010) correction for exact permutation p-values.

### 9.3 Omnibus in the Offline Engine

The `OfflineMultichannelEngine` uses a distinct omnibus approach: a **permutation-based Friedman test**. For each permutation, condition labels are shuffled and the sum of absolute variance differences across all features is computed. The p-value is the proportion of permuted statistics that exceed the observed statistic. This provides a non-parametric global test suitable for the offline analysis context.

---

## 10. Quality Assurance

### 10.1 Pre-Analysis Data Quality Checks

Before statistical testing begins, the `analyze_task_data()` method verifies:

1. **Minimum window count**: At least 3 windows must exist in both baseline and task conditions.
2. **Minimum block count**: At least 8 blocks per condition after block construction (configurable via `min_blocks_per_condition`).
3. **Feature variance**: Features with zero or near-zero variance across blocks (SD < $10^{-10}$) are excluded from testing.
4. **Spectral sanity**: Checks for flat signals (zero variance in raw data) and noise-dominated spectra.

If these checks fail, analysis is aborted with a diagnostic message rather than producing unreliable results.

### 10.2 Post-Analysis Garbage Detection

After per-feature testing, the pipeline checks for implausible results that suggest the recording is not from a worn device:

- **CRITICAL (garbage/not worn)**: If > 70% of tested features are flagged as "significant," the recording is almost certainly artifact or noise. Worn EEG from a genuine cognitive task should not produce simultaneous changes across the vast majority of unrelated features. The result is flagged as `quality = 'CRITICAL'` with a warning that the data likely represents a not-worn or heavily artifacted recording.

- **WARNING**: If > 50% (but ≤ 70%) of features are significant, a warning is issued suggesting data quality review.

This heuristic is based on the reasoning that genuine cognitive tasks produce focal or regionally specific neural changes, not global changes across all channels, bands, and feature types simultaneously.

### 10.3 Expectation Alignment Grading

For tasks with known directional priors (§8.3), the system grades how well the observed results align with neuroscientific expectations:

| Grade | Interpretation | Criterion |
|-------|---------------|-----------|
| A | Strong alignment | ≥ 75% of expected-direction features match |
| B | Moderate alignment | ≥ 50% match |
| C | Weak alignment | ≥ 25% match |
| D | No alignment | < 25% match |

The grade is reported alongside the statistical results to provide an interpretive layer. A "D" grade on a known task type may suggest experimental confounds (e.g., participant non-compliance, wrong task performed) even if the statistical test shows significant results.

---

## 11. Multi-Task Analysis

### 11.1 Per-Task Analysis

When multiple tasks are recorded in a single session, each task is analyzed independently against the shared eyes-closed baseline using the full pipeline described in §§6–10. Each task produces its own set of per-feature results, omnibus p-values, composite scores, and quality assessments.

### 11.2 Combined Aggregate Analysis

All task windows from all tasks are pooled and analyzed as a single combined condition against baseline. This provides an overall "any task vs. rest" assessment and increases statistical power when individual tasks have few windows.

### 11.3 Across-Task Comparison (Friedman and Wilcoxon)

To test whether different tasks produce different neural signatures, the `_analyze_across_tasks()` method:

1. Constructs a feature matrix with tasks as conditions and features as variables.
2. Applies the **Friedman test** per feature to test for omnibus differences across tasks ($H_0$: all tasks produce the same distribution for feature $f$).
3. For features with a significant Friedman result, **pairwise Wilcoxon signed-rank tests** identify which specific task pairs differ.
4. FDR correction (BH) is applied across all Friedman p-values.

### 11.4 Cross-Task FWER Correction (Holm–Bonferroni)

When reporting multiple tasks from the same session, each per-task omnibus p-value is subject to familywise error rate inflation. The **Holm–Bonferroni step-down procedure** corrects for this:

1. Sort the $k$ per-task omnibus p-values: $p_{(1)} \leq p_{(2)} \leq \ldots \leq p_{(k)}$.
2. For rank $i$, the adjusted p-value is: $p_{adj,(i)} = p_{(i)} \times (k - i + 1)$.
3. Enforce monotonicity: $p_{adj,(i)} = \max(p_{adj,(i)},\ p_{adj,(i-1)})$.

Holm–Bonferroni is uniformly more powerful than the classical Bonferroni correction while maintaining strong FWER control.

### 11.5 Composite Score

For each task, a composite score summarizes the overall strength of evidence:

$$S = \sum_{i=1}^{m} -\log_{10}(q_i)$$

where $q_i$ is the BH-adjusted p-value for feature $i$. Features with $q_i \geq 1$ contribute zero. A higher composite score indicates more features with smaller adjusted p-values. This metric is used for cross-task ranking within the report.

---

## 12. Report Generation

The `Enhanced64ChannelReportGenerator` produces structured text reports that synthesize all analysis outputs. The report is organized into the following sections:

### 12.1 Header and Metadata

Subject demographics (ID, age, email), session ID, hardware configuration, and analysis timestamp.

### 12.2 Data Quality Validation

- Channel quality assessment: good (≥ 70%), fair (40–69%), poor (< 40%) per channel
- Regional coverage: percentage of good channels per anatomical region (frontal, central, parietal, temporal, occipital), with `[OK]`, `[!]`, or `[X]` status indicators
- Critical quality banners for garbage-detected or low-coverage recordings
- Bad channel list (excluded from analysis)

### 12.3 Per-Task Summaries

For each task analyzed:
- Task type, duration, number of windows and blocks
- Kost–McDermott adjusted Fisher statistic and p-value
- SumP permutation p-value
- Composite score
- Expectation alignment grade (if directional priors exist)
- Top 10 features by effect size with Hedges' g, 95% CI, and adjusted p-values

### 12.4 Cross-Task FWER Table

A table listing each task's omnibus p-value, the Holm–Bonferroni adjusted p-value, and the corrected significance determination. This section only appears when multiple tasks are analyzed.

### 12.5 64-Channel Spatial Analysis

- **Regional Activity Summary**: Count of significant features per band per region with effect size statistics and directional indicators (↑/↓)
- **Hemispheric Asymmetry Analysis**: Left vs. right hemisphere significant feature counts and average effect sizes per band, with an asymmetry index and dominance classification
- **Inter-Channel Coherence and Connectivity**: Significant coherence changes ranked by effect size with directional interpretation (increased integration vs. segregation)
- **Channel Quality and Spatial Coverage**: Per-region channel quality with coverage percentages
- **Topographic Distribution Summary**: Anterior/central/posterior distribution of significant features with topographic pattern classification

### 12.6 Configuration and Provenance

Full documentation of all analysis parameters:
- Preprocessing: notch frequency, Q factor
- Block aggregation: block duration, minimum blocks per condition
- Statistical testing: alpha level, FDR method, CI level, bootstrap samples
- Permutation testing: number of permutations, fast mode flag
- EMG guard: adaptive threshold, fallback threshold

### 12.7 Glossary

Definitions of key statistical terms (alpha, Hedges' g, BH FDR, compositeScore, SumP permutation, FWER) for non-specialist readers.

---

## 13. Configurable Parameters

All pipeline parameters are centralized in the `EnhancedAnalyzerConfig` dataclass:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `alpha` | 0.05 | Global significance threshold |
| `block_seconds` | 4.0 | Non-overlapping block duration (seconds) |
| `n_perm` | 1000 | Number of permutations (standard mode) |
| `n_perm_fast` | 100 | Number of permutations (fast mode) |
| `bootstrap_ci_samples` | 1000 | Bootstrap resamples for CI |
| `ci_level` | 0.95 | Confidence interval level |
| `line_noise_freq` | 60.0 | Powerline frequency (Hz) |
| `notch_q` | 30.0 | Notch filter quality factor |
| `effect_size_threshold` | 0.5 | Minimum |g| for significance (medium effect) |
| `pct_change_threshold` | 15.0 | Minimum |Δ%| for significance |
| `garbage_pct_critical` | 0.70 | Fraction of significant features → CRITICAL |
| `garbage_pct_warning` | 0.50 | Fraction of significant features → WARNING |
| `min_blocks_per_condition` | 8 | Minimum blocks required for analysis |
| `emg_adaptive_threshold` | True | Use adaptive EMG threshold from baseline |
| `fast_mode` | True | Use `n_perm_fast` instead of `n_perm` |

---

## 14. Computational Considerations

### 14.1 Live Streaming Performance

The `Enhanced64ChannelEngine` is optimized for real-time operation:
- **Vectorized PSD computation**: All 64 channels are processed through array operations rather than sequential loops.
- **Extraction throttle**: Feature extraction is throttled to ≤ 2 Hz (one extraction per ~0.5s) to prevent CPU saturation during continuous streaming.
- **Ring buffer**: Circular buffers avoid memory allocation and array copying.
- **Window reuse**: The 50% overlap means half the data in each window was already in the previous window's buffer, avoiding redundant I/O.

### 14.2 Offline Analysis Performance

The `OfflineMultichannelEngine` preprocesses the entire recording at once (artifact detection and removal on the full data matrix), then extracts features in a single windowed pass. This is more efficient than the live engine's incremental approach but requires holding the full recording in memory.

### 14.3 Permutation Testing Scalability

Each permutation requires re-running all per-feature Welch t-tests. With ~1,300 features and 1,000 permutations, this involves ~1.3 million t-tests. The `fast_mode` option (100 permutations) reduces this 10-fold for interactive use. Progress callbacks are supported to enable UI progress bars during long-running permutation tests.

---

## 15. Validation Status

### 15.1 Not-Worn Detection

We tested the pipeline with **three "cap not worn"** datasets — recordings made with the headset placed on a table rather than on a participant's head. In all three cases, the garbage detection heuristic (§10.2) correctly flagged the recording as **CRITICAL (garbage/not worn)**, indicating that the > 70% significant-features threshold successfully discriminates non-neural signal from genuine recordings.

### 15.2 Limitations

- **No large-scale benchmarking**: We have not conducted systematic sensitivity/specificity testing across a range of artifact types (e.g., eye blinks only, jaw clenching only, loose electrodes, intermittent contact).
- **No cross-device validation**: The pipeline has been tested on ANT Neuro eego mylab only. Generalization to other 64-channel systems (e.g., BioSemi, EGI) has not been verified.
- **No clinical validation**: The pipeline is not intended for clinical diagnosis. All interpretive outputs (expectation alignment grades, topographic pattern labels) are research tools, not diagnostic instruments.
- **Interpolation assumptions**: The nearest-neighbor bad-channel interpolation is an approximation of spherical spline interpolation and may introduce bias in regional features near excluded channels.

### 15.3 Planned Validation

Future work includes:
- Testing with deliberately introduced artifact types (controlled muscle, eye movement, electrode pop)
- Comparison of garbage detection sensitivity/specificity across recording durations
- Cross-validation of the 70% threshold using receiver operating characteristic (ROC) analysis
- Multi-site data collection with diverse headset conditions (tight fit, loose fit, partial coverage)

---

## 16. Discussion

### 16.1 Pipeline Design Philosophy

The pipeline balances statistical rigor with practical usability. The multi-gate significance decision (§8.2) — accepting features via p-value, effect size, or percent change — departs from strict null-hypothesis significance testing (NHST) in order to capture effects that are practically meaningful even if they do not survive conservative FDR correction with small sample sizes. This reflects the exploratory nature of consumer EEG analysis, where the goal is often to identify candidate features for further investigation rather than to confirm pre-registered hypotheses.

### 16.2 Block-Level Aggregation

The 4-second block aggregation (§6) is a pragmatic compromise between independence and sample size. Longer blocks (e.g., 10 seconds) would reduce autocorrelation further but would also reduce the number of blocks available for testing, potentially falling below the minimum block threshold. The choice of 4 seconds corresponds to two 2-second windows and is configurable via the `block_seconds` parameter.

### 16.3 Correlation-Corrected Omnibus Testing

The Kost–McDermott correction (§9.1) addresses a well-known limitation of Fisher's method: when features are correlated, the uncorrected combined statistic is anti-conservative. By estimating the variance inflation due to inter-feature correlations and adjusting the degrees of freedom accordingly, the corrected test maintains approximately valid Type I error control. The Spearman rank correlation is used instead of Pearson to reduce sensitivity to outliers in EEG power distributions.

### 16.4 Quality Assurance and Garbage Detection

The > 70% threshold for garbage detection (§10.2) is a conservative heuristic based on the observation that genuine cognitive tasks produce spatially and spectrally focal changes. A not-worn headset produces noise across all channels that, when compared to a genuine baseline, yields universally "significant" differences. This pattern is highly distinctive and has correctly identified all three not-worn test cases. However, the threshold has not been optimized against a labeled dataset of artifact types, and edge cases (e.g., severe but genuine movement artifacts) may produce false positives.

---

## 17. Conclusions

We have described the complete multi-channel EEG analysis pipeline implemented in the BrainLink Companion platform, spanning:

1. **Data acquisition**: Live streaming and offline CSV recording with phase markers
2. **Preprocessing**: DC offset removal, 60 Hz notch filtering, artifact detection and interpolation
3. **Feature extraction**: ~1,300 features per window covering per-channel, regional, asymmetry, coherence, and global field power metrics
4. **Block-level aggregation**: 4-second non-overlapping blocks as units of statistical analysis
5. **Per-feature testing**: Welch's t-test with Hedges' g and bootstrap confidence intervals
6. **Multiple comparison correction**: Benjamini–Hochberg FDR
7. **Omnibus testing**: Fisher's combined probability with Kost–McDermott correction and block-level SumP permutation
8. **Multi-task analysis**: Independent per-task analysis, combined aggregate, Friedman/Wilcoxon across-task comparison, and Holm–Bonferroni cross-task FWER correction
9. **Quality assurance**: Pre-analysis data quality checks, garbage/not-worn detection, and expectation alignment grading
10. **Report generation**: Structured reports with regional, asymmetry, coherence, topographic, and quality analyses

The pipeline is fully configurable, supports both real-time and offline workflows, and has demonstrated correct garbage detection in three not-worn recordings. Systematic validation across a broader range of conditions and populations is planned as future work.

---

## References

1. Allen, J. J. B., Coan, J. A., & Nazarian, M. (2004). Issues and assumptions on the road from raw signals to metrics of frontal EEG asymmetry in emotion. *Biological Psychology*, 67(1–2), 183–218.
2. Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: A practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B*, 57(1), 289–300.
3. Fisher, R. A. (1932). *Statistical Methods for Research Workers* (4th ed.). Oliver and Boyd.
4. Hedges, L. V. (1981). Distribution theory for Glass's estimator of effect size and related estimators. *Journal of Educational Statistics*, 6(2), 107–128.
5. Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70.
6. Kost, J. T., & McDermott, M. P. (2002). Combining dependent p-values. *Statistics & Probability Letters*, 60(2), 183–190.
7. Pesarin, F. (2001). *Multivariate Permutation Tests: With Applications in Biostatistics*. Wiley.
8. Phipson, B., & Smyth, G. K. (2010). Permutation p-values should never be zero: Calculating exact p-values when permutations are randomly drawn. *Statistical Applications in Genetics and Molecular Biology*, 9(1), Article 39.
9. Welch, B. L. (1947). The generalization of Student's problem when several different population variances are involved. *Biometrika*, 34(1–2), 28–35.

---

## Supplementary Material

### S1. Channel Layout Reference (NA-265, 64 channels)

```
                     Fp1  Fp2
                 AF7  AF3  AF4  AF8
            F7   F5   F3   F1  Fz  F2   F4   F6   F8
           FT7  FC5  FC3  FC1      FC2  FC4  FC6  FT8
            T7   C5   C3   C1  Cz  C2   C4   C6   T8
           TP7  CP5  CP3  CP1 CPz  CP2  CP4  CP6  TP8
                 P7   P5   P3  Pz  P4   P6   P8
                     PO7  PO3      PO4  PO8
                          O1   Oz   O2
```

### S2. Regional Channel Assignments

| Region | Channels |
|--------|----------|
| Frontal | Fp1, Fp2, AF3, AF4, AF7, AF8, F1, F2, F3, F4, F5, F6, F7, F8, Fz, FC1, FC2, FC3, FC4, FC5, FC6 |
| Central | C1, C2, C3, C4, C5, C6, Cz, CP1, CP2, CP3, CP4, CP5, CP6 |
| Temporal | T7, T8, FT7, FT8, TP7, TP8 |
| Parietal | P1, P2, P3, P4, P5, P6, P7, P8, Pz, PO3, PO4, PO7, PO8 |
| Occipital | O1, O2, Oz |

### S3. Asymmetry Pairs (27 pairs)

Fp1–Fp2, AF3–AF4, AF7–AF8, F1–F2, F3–F4, F5–F6, F7–F8, FC1–FC2, FC3–FC4, FC5–FC6, C1–C2, C3–C4, C5–C6, T7–T8, FT7–FT8, TP7–TP8, CP1–CP2, CP3–CP4, CP5–CP6, P1–P2, P3–P4, P5–P6, P7–P8, PO3–PO4, PO7–PO8, O1–O2

### S4. Coherence Region Pairs

| Pair | Representative Channels |
|------|------------------------|
| Frontal–Parietal | F3 ↔ P3 |
| Frontal–Occipital | F3 ↔ O1 |
| Frontal–Temporal | F3 ↔ T7 |
| Parietal–Occipital | P3 ↔ O1 |
| Temporal–Parietal | T7 ↔ P3 |

### S5. Pipeline Flow Diagram

```
Raw EEG (64ch × 500Hz)
        │
        ▼
┌─────────────────────┐
│  DC Offset Removal  │  (per-channel mean subtraction)
│  60 Hz Notch Filter │  (IIR, Q=30, zero-phase)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Artifact Detection │  (offline only: flat/noisy channels, high-amplitude windows)
│  Artifact Removal   │  (neighbor interpolation, linear interpolation)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Windowed Feature   │  (2s windows, 50% overlap)
│  Extraction         │  (~1,300 features per window)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Baseline           │  (eyes-closed statistics, EMG threshold)
│  Calibration        │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Block Aggregation  │  (4s non-overlapping blocks, equalization)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Per-Feature Tests  │  (Welch t-test, Hedges' g, bootstrap CI)
│  FDR Correction     │  (Benjamini–Hochberg)
│  Significance Gate  │  (p OR effect_size OR pct_change)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Omnibus Tests      │  (Fisher KM, SumP permutation)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Quality Assurance  │  (garbage detection, expectation alignment)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Multi-Task         │  (per-task, combined, across-task Friedman/Wilcoxon)
│  Analysis           │  (Holm–Bonferroni cross-task FWER)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Report Generation  │  (regional, asymmetry, coherence, topographic)
└─────────────────────┘
```

