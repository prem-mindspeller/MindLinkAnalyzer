# New Backend EEG Processing and Feature Extraction

This document describes the EEG processing path in `newBackend/main.py`, focused on the `/analyze` endpoint used after the frontend sends baseline and task recordings.

## Input Shape

The backend accepts:

```json
{
  "baseline": {
    "eyes_closed": [],
    "eyes_open": []
  },
  "tasks": {
    "task_id": []
  },
  "block_seconds": 8.0
}
```

The sample arrays can contain either:

- raw EEG numbers sampled at 512 Hz
- TGAM-style band-power dictionaries with `delta`, `theta`, `lowAlpha`, `highAlpha`, `lowBeta`, `highBeta`, `lowGamma`, and `midGamma`

Raw numeric EEG is the preferred analysis path because it preserves the signal window and PSD assumptions more directly.

## Raw EEG Windowing

Raw EEG is processed as fixed 2-second windows:

- sample rate: `512 Hz`
- window length: `1024 samples`
- raw step: `1024 samples`
- overlap: none in the offline `/analyze` path

The default statistical block is 8 seconds, so each block contains:

- `4` feature windows
- `4 * 2.0 s = 8.0 s`

Blocks are used before statistical testing so adjacent EEG windows are not treated as independent samples.

## Raw Feature Extraction

For each 2-second raw window, the backend:

1. Converts samples to `float64`.
2. Removes the window mean.
3. Computes a PSD using DPSS multitaper when available.
4. Falls back to a Hann-window FFT if DPSS is unavailable.
5. Estimates a 10th-percentile PSD noise floor.
6. Builds an SNR-adjusted PSD by subtracting the noise floor and clamping at zero.
7. Computes band powers, peak descriptors, relative powers, entropy, ratios, total power, and EMG guard flags.

The raw frequency bands are:

| Band | Range |
| --- | --- |
| `delta` | 0.5-4 Hz |
| `theta` | 4-8 Hz |
| `alpha` | 8-13 Hz |
| `beta` | 13-30 Hz |
| `gamma` | 30-45 Hz |
| `theta1` | 4-6 Hz |
| `theta2` | 6-8 Hz |
| `beta1` | 13-20 Hz |
| `beta2` | 20-30 Hz |

For each band, the backend emits:

- `{band}_power`: SNR-adjusted band power
- `{band}_power_raw`: raw PSD band power
- `{band}_relative`: SNR-adjusted band power divided by total SNR power
- `{band}_peak_freq`: peak frequency inside the band
- `{band}_peak_amp`: raw PSD amplitude at the peak frequency
- `{band}_peak_rel_amp`: peak prominence relative to the normalized band mean
- `{band}_entropy`: spectral entropy inside the band

The backend also emits:

- `alpha_theta_ratio`
- `beta_alpha_ratio`
- `beta2_beta1_ratio`
- `theta2_theta1_ratio`
- `total_power`
- `_emg_guard`
- `_gamma_evaluated`

## Gamma EMG Guard

The backend checks for possible high-frequency muscle contamination before trusting gamma features.

It compares:

- high-frequency power from 35-45 Hz
- mid-frequency power from 20-30 Hz
- the spectral slope from 20-45 Hz

Gamma is guarded when:

- the 35-45 Hz / 20-30 Hz power ratio is greater than `1.2`, or
- the 20-45 Hz spectral slope is flatter than `-0.6`

When the guard fires:

- gamma features are zeroed
- `_emg_guard` is `1`
- `_gamma_evaluated` is `0`

## Eyes-Closed Baseline QC

The backend uses eyes-closed baseline as the primary baseline source. Raw eyes-closed windows are quality-checked before baseline statistics are computed.

Each raw baseline window is checked for:

- flatline or disconnected signal
- probable not-worn headset
- extreme artifact windows

The robust amplitude scale is:

```text
scale = 1.4826 * median(abs(x - median(x)))
```

A window is rejected as:

- `flatline` when scale is below `0.5`
- `not_worn` when low-frequency neural power is too weak, high-frequency power dominates, or the spectrum is too flat
- `artifact` when too many samples are extreme outliers relative to the robust scale

The `/analyze` response reports:

- `baseline_kept`
- `baseline_rejected`
- `baseline_rejected_not_worn`
- `baseline_rejected_artifact`
- `baseline_rejected_flatline`

If all baseline windows are rejected, analysis stops with:

```json
{"error": "No usable baseline data after quality control"}
```

## TGAM Band-Power Input Path

If the frontend sends TGAM-style band-power dictionaries instead of raw EEG, the backend uses `_extract_features()`.

TGAM input contains these source bands:

- `delta`
- `theta`
- `lowAlpha`
- `highAlpha`
- `lowBeta`
- `highBeta`
- `lowGamma`
- `midGamma`

The backend derives:

- `delta`
- `theta`
- `theta1`
- `theta2`
- `alpha`
- `beta`
- `beta1`
- `beta2`
- `gamma`

For TGAM data, `theta1` and `theta2` are approximated from `theta`, while `alpha`, `beta`, and `gamma` are composed from their low/high source bands.

This path is retained for compatibility, but it is less faithful than raw-window feature extraction because it starts from already-compressed band-power summaries.

## Block Aggregation

Feature rows are grouped into non-overlapping blocks before statistical testing.

Default:

- `block_seconds = 8.0`
- `window_duration = 2.0`
- `windows_per_block = 4`

Each block stores the mean value for every feature across the windows in that block.

If one group has more blocks than another, the backend down-samples the larger group to match the smaller group before testing.

## Per-Task Statistical Analysis

For each task, the backend compares task blocks against baseline blocks.

For each feature, it computes:

- task mean and baseline mean
- delta
- Welch t-test p-value
- Cohen's d
- percent change
- z-score
- baseline/task ratio
- log2 ratio
- BH FDR q-value
- one-sided p-value when a task-specific expected direction exists
- significance flags and thresholds

Significance can be assigned by:

- directional p-value passing alpha
- effect size fallback
- percent-change fallback

The backend also computes task-level summaries:

- Kost-McDermott adjusted Fisher combined evidence
- SumP permutation evidence
- composite score from adjusted p/q evidence
- mean absolute effect size
- cosine similarity between baseline and task feature vectors
- effective sample size metadata
- feature-selection metadata
- expectation-alignment summary when a known task id is provided

## Across-Task Analysis

When multiple tasks are present, the backend builds an across-task section.

It computes per-feature task rankings using task effect sizes, and when possible runs a Kruskal-Wallis omnibus test per feature with BH FDR correction.

It also adds a cross-task family-wise correction block:

```json
{
  "method": "holm_bonferroni",
  "alpha": 0.05,
  "tasks": [],
  "n_tests": 0,
  "n_rejected": 0,
  "results": []
}
```

This Holm-Bonferroni correction is applied over the per-task combined `km_p` values.

## Output Overview

The `/analyze` response contains:

- `per_task`: per-task summary and per-feature analysis
- `combined`: all task rows pooled against baseline
- `across_task`: cross-task rankings, omnibus tests, and Holm correction
- baseline QC counters
- raw baseline sample counts
- eyes-open window count
- runtime config metadata

## Important Notes

- The raw EEG path is the preferred method for analysis correctness.
- The TGAM path exists for compatibility with precomputed band-power samples.
- Baseline QC currently applies to raw eyes-closed baseline windows.
- The live serial parser and filtering in `eeg_processor.py` are separate from this offline `/analyze` feature pipeline.
