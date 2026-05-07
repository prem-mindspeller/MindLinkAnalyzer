# Offline 64-Channel EEG Analysis Pipeline
## Technical Documentation

**System:** MindLink / BrainLink Companion - ANT Neuro Integration  
**Version:** 2.4, offline analysis pipeline  
**Updated:** April 2026  
**Primary files:** `BrainLink_Offline_Analyzer.py`, `antNeuro/offline_multichannel_analysis.py`, `utils/enhanced_report_generator.py`

---

## 1. Purpose

The offline 64-channel analyzer separates EEG recording from analysis. During the experiment, the system records raw 64-channel EEG and phase markers. After the session, the offline pipeline reloads the raw data, segments it by phase, preprocesses it, extracts features, compares task windows against baseline windows, and generates a quality-gated report.

The pipeline is currently suitable for:

- Session-level quality control.
- Exploratory physiological response analysis.
- Method development for 64-channel EEG feature extraction.
- Identifying whether a recording is potentially profile-ready.

The pipeline is not allowed to produce cognitive profiles, trait scores, diagnostic labels, or subject-level conclusions unless the report gate says `PROFILE-READY`.

---

## 2. Current Profile-Safety Principle

The report is intentionally conservative. It separates:

- **Profile-facing sections:** only features that pass artifact filters and are not EMG-excluded gamma.
- **Diagnostic/QC sections:** artifact-suspect features, gamma flood diagnostics, saturation guard details, bad-channel information, and baseline limitations.

When the report says `RESEARCH-ONLY`, lower sections suppress interpretive language such as cognitive, emotional, or trait explanations. Spatial and connectivity distributions may still be shown for QC review, but not for profile inference.

Example current gate from `analysis_report_fast_20260427_165750.txt`:

```text
PROFILE SUITABILITY: RESEARCH-ONLY

Blocking reasons:
  - Gamma EMG flood in 4 task(s)
  - Artifact-suspect features: 243 unique feature names / 332 task-feature instances with |d| > 10
  - High-frequency saturation guard activated in 20 phase(s): 574 candidate windows left in place to avoid biased tiny-sample analysis
```

Interpretation for that report: the session can be discussed as a contaminated physiological/QC example, but it should not be used to create a user profile.

---

## 3. High-Level Flow

```text
Raw 64-channel EEG CSV
        +
Phase marker JSON
        |
        v
Load and align timestamps
        |
        v
Segment into eyes-closed, eyes-open, and task phases
        |
        v
Per-phase artifact detection and bad-channel handling
        |
        v
High-frequency artifact gate before feature extraction
        |
        v
Notch filtering, average reference, PSD computation
        |
        v
Window-level feature extraction
        |
        v
Task-vs-baseline statistics
        |
        v
Artifact/gamma/profile-suitability guards
        |
        v
Report generation
```

---

## 4. Recording Inputs

### 4.1 EEG Data

- Hardware target: ANT Neuro eego / 64-channel cap.
- Sampling rate: 500 Hz.
- Expected data shape after loading: `n_samples x 64`.
- CSV columns: timestamp, sample index, and channel voltages.
- Channel montage: extended 10-20 / 10-10 style labels such as `Fp1`, `Fp2`, `F3`, `F4`, `C3`, `Pz`, `O1`, `POz`.

### 4.2 Phase Markers

The analyzer uses a marker JSON to map time ranges to recording phases. Typical phases:

- `eyes_closed`: resting baseline currently used as the main statistical reference.
- `eyes_open`: retained for reference and provenance, but not pooled with eyes-closed baseline.
- `task`: task-specific segments, for example `attention_focus`, `mental_math`, `visual_imagery`, `emotion_face`.
- Protocol/data-collection tasks such as 40 Hz stimulation may be recorded but excluded from multi-task statistical comparison.

The report now distinguishes:

```text
Tasks executed: 5
Tasks analyzed statistically: 4
Excluded from statistical comparison:
  - 1 data collection/protocol task(s), for example 40 Hz stimulation if present in the protocol
```

---

## 5. Windowing

The pipeline extracts features from overlapping windows.

| Parameter | Current value | Reason |
|---|---:|---|
| Window length | 2.0 s | Provides spectral information while keeping task dynamics local. |
| Step size | 1.0 s | 50% overlap improves coverage. |
| Block aggregation | 4.0 s blocks | Reduces dependence between adjacent overlapped windows. |
| Minimum blocks | 8 per condition where possible | Avoids unstable tiny-sample comparisons. |

Effective sample size is reported per task, for example:

```text
ESS: baseline=7, task=12, n_blocks=12
```

This means the statistical test is not pretending every overlapping 2 s window is independent.

---

## 6. Preprocessing and Artifact Handling

### 6.1 Channel Quality and Bad Channels

Each phase is screened for channel quality. The report separates two concepts that should not be confused:

- **Quality bin:** mean per-channel quality across phases.
- **Global exclusion:** channels removed from feature extraction because they were flat or majority-noisy.

Quality bins:

- Good: quality >= 0.70.
- Fair: 0.40 <= quality < 0.70.
- Poor: quality < 0.40.

Global exclusion:

- Flat channels are excluded.
- Noisy channels are excluded only if noisy in the majority of phases.

This is why the number of globally excluded channels can differ from the number of channels in the "poor" bin.

### 6.2 Average Reference

Average reference is applied by default unless disabled by configuration. Bad/invalid channels are handled before feature extraction so they do not dominate spatial summaries.

### 6.3 Notch Filter

Line-noise filtering is applied at the configured line frequency and harmonics. In the current report example:

```text
Notch filter: 50.0 Hz + harmonics (Q=30)
```

### 6.4 High-Frequency Artifact Gate

This is a pre-feature extraction gate for broadband high-frequency contamination, especially muscle artifact.

For each candidate feature window:

- High-frequency band: 30-45 Hz.
- Broadband reference: 1-45 Hz.
- Global metric: 75th percentile HF/broadband ratio across valid channels.
- Frontotemporal metric: 75th percentile HF/broadband ratio across frontal and temporal channels.

Thresholds are robust/adaptive using median/MAD logic with fixed lower floors:

- Global floor: 0.35.
- Frontotemporal floor: 0.30.

If a window exceeds either threshold, it is rejected before features are extracted.

### 6.5 Saturation Guard

If too many windows in a phase would be rejected, the pipeline does not keep only a tiny clean-looking remainder. That would bias the phase and make the task comparison unstable.

Current rule:

- If candidate rejection fraction exceeds `hf_max_reject_fraction` (currently 0.80), the phase is treated as tonically contaminated.
- Epoch rejection is disabled for that phase.
- The number of candidate rejected windows is reported.
- The profile gate treats this as a blocking reason.

Current report example:

```text
High-frequency epoch rejection: 0/574 windows rejected
Saturation guard: 20 phase(s) treated as tonically contaminated;
574 candidate windows were not dropped to avoid biased tiny-sample analysis.
```

Interpretation: the gate detected contamination everywhere. It could not safely "clean" the data by dropping windows because that would over-prune the session.

### 6.6 ICA, CSD, and CCA Hooks

The command-line/configuration layer exposes hooks for:

- ICA-based EMG component removal.
- Surface Laplacian / current source density (CSD).
- CCA-based muscle artifact removal.

The report states whether these were requested and whether they were applied. The pipeline must not imply these methods were applied unless the optional dependencies and implementation path actually ran.

Current report example:

```text
ICA EMG cleaning: not requested
CSD transform: not requested
CCA EMG cleaning: not requested
```

---

## 7. Feature Extraction

The analyzer extracts per-window features from valid channels and regions.

### 7.1 Frequency Bands

| Band | Range |
|---|---|
| Delta | 0.5-4 Hz |
| Theta | 4-8 Hz |
| Alpha | 8-13 Hz |
| Beta | 13-30 Hz |
| Gamma | 30-45 Hz |

Gamma is always treated cautiously because scalp gamma overlaps strongly with EMG.

### 7.2 Feature Families

Main feature families:

- Per-channel absolute band power.
- Per-channel relative band power.
- Per-channel peak frequency.
- Cross-band ratios such as alpha/theta and beta/alpha.
- Regional average powers and ratios.
- Hemispheric asymmetry features.
- Frontal alpha asymmetry.
- Inter-regional coherence features.
- Global field power.
- Global summary features.

The exact feature count can change when channels are excluded or when a feature cannot be computed. Missing features are not zero-filled.

---

## 8. Statistical Analysis

### 8.1 Baseline Policy

Current implementation:

- Eyes-closed baseline is the primary statistical baseline.
- Eyes-open baseline is retained for reference and provenance.
- Eyes-open and eyes-closed are not pooled.

Important limitation:

- For eyes-open cognitive/visual tasks, an eyes-open or task-specific pre-task baseline would be more appropriate for profiling.
- If only eyes-closed is used against eyes-open tasks, task interpretation is lower confidence.

The report states this explicitly:

```text
Baseline: eyes-closed only (eyes-open retained for reference, not pooled).
Profile limitation: eyes-open cognitive/visual tasks should prefer eyes-open or task-specific pre-task baselines.
```

### 8.2 Per-Feature Tests

Current implementation:

- Baseline and task values are aggregated into blocks.
- A feature is tested only when both baseline and task have at least 3 finite values.
- Missing features are not imputed or zero-filled.
- Per-feature task-vs-baseline comparison uses Mann-Whitney U.
- Per-feature p-values are corrected with Benjamini-Hochberg FDR.
- Effect sizes are reported as Hedges' g, with bootstrap confidence intervals when enabled.

### 8.3 Fisher Omnibus

The report shows Fisher combined p-values as an independence approximation:

```text
Fisher_p=... method=independence_approximation
```

This is intentionally not described as Kost-McDermott corrected. EEG features are correlated, so the Fisher omnibus should be interpreted cautiously and mainly as an aggregate signal indicator rather than a publication-ready inferential claim.

### 8.4 SumP

SumP is the sum of raw per-feature p-values. In fast mode it uses a parametric Irwin-Hall approximation; in full/permutation paths it can use permutation-derived nulls where implemented.

### 8.5 Composite Score

CompositeScore is:

```text
sum(-log10(q)) across significant features
```

It is an aggregate strength indicator, not a cognitive score and not a normative profile metric.

### 8.6 Cross-Task Family-Wise Correction

Task-level omnibus p-values are corrected across tasks with Holm-Bonferroni. If no task survives correction, the report states:

```text
No task-level omnibus effects survived Holm-Bonferroni family-wise correction.
No reliable between-task differentiation was detected.
```

For profiling, this matters because a pipeline that cannot reliably separate task signatures should not produce task-specific cognitive interpretations.

### 8.7 Across-Task Omnibus Feature Stability

The across-task feature stability section is QC/exploratory. It now excludes artifact-suspect and EMG-excluded gamma features from profile-facing lists.

If the displayed q-values are mathematically inconsistent with raw p-values, the report suppresses the top-feature omnibus ranking:

```text
Top Feature Omnibus Stats suppressed: omnibus q-values are smaller than their raw p-values...
Treat omnibus output as QC-only until fixed.
```

This prevents invalid-looking omnibus rankings from being treated as meaningful profile features.

---

## 9. Artifact-Suspect Guard

Features with very large effect sizes are flagged:

```text
artifact_suspect = True when |d| > 10
```

Rationale:

- Hedges' g above 10 is generally implausible for scalp EEG task effects.
- Such values usually reflect movement, electrode instability, clipping, or bad-channel contamination.

Behavior:

- Excluded from profile-facing top-feature lists.
- Shown separately in an artifact-suspect diagnostic list.
- Winsorized/capped at 10 for Mean|d| summary.
- Excluded from regional, asymmetry, topographic, connectivity, and across-task interpretive summaries.
- Counted in the profile suitability gate as both unique feature names and task-feature instances.

Example:

```text
Artifact-suspect features: 243 unique feature names / 332 task-feature instances with |d| > 10
```

---

## 10. Gamma EMG Flood Guard

### 10.1 Why This Exists

Scalp gamma, especially 30-45 Hz, is highly vulnerable to muscle activity from jaw, face, neck, and scalp muscles. EMG often appears as broadband high-frequency activity and can create apparently significant gamma changes across many channels at once.

### 10.2 Detection Rule

For each task:

```text
gamma_sig_fraction = significant_gamma_features / total_gamma_features
```

If:

```text
gamma_sig_fraction > 0.25
```

then the task is flagged as an EMG flood.

### 10.3 Behavior When Flood Is Active

When gamma flood is detected:

- All gamma features are marked `emg_excluded`.
- Gamma is removed from Fisher, SumP, CompositeScore, and Mean|d|.
- Gamma is removed from top-feature lists.
- Gamma is removed from regional, asymmetry, topographic, connectivity, and across-task interpretive summaries.
- Gamma remains visible only in an `EMG-excluded gamma diagnostics` section.
- The profile suitability gate marks the session as `RESEARCH-ONLY` when floods affect analyzed tasks.

Example:

```text
EMG FLOOD DETECTED: 65/130 gamma features significant (50% > 25% threshold).
All gamma features EXCLUDED from omnibus statistics.
EMG-excluded gamma diagnostics (not profile-facing; top 5 by p-value):
```

Interpretation: gamma can be inspected as contamination evidence but not interpreted as cortical gamma activation.

---

## 11. Spatial and Connectivity Report Sections

The report includes:

- Regional activity summary.
- Hemispheric asymmetry analysis.
- Inter-channel coherence/connectivity.
- Channel quality and spatial coverage.
- Topographic distribution summary.

Current profile-facing rule:

```text
Artifact-suspect features and EMG-excluded gamma features are excluded from interpretive summaries.
```

When profile suitability is `RESEARCH-ONLY`, interpretive statements are disabled:

```text
Interpretation disabled: session is RESEARCH-ONLY; distribution is shown for QC review only.
```

This avoids saying "do not profile" at the top while implying cognitive meaning later in the report.

---

## 12. Profile Suitability Gate

The profile gate is the most important downstream safeguard.

### 12.1 Possible Status Values

| Status | Meaning |
|---|---|
| `PROFILE-READY` | Minimum safeguards passed; cautious profile-level interpretation may be possible. |
| `RESEARCH-ONLY` | Data can be reviewed for QC/physiology but should not be used for subject profiling. |
| `INVALID` | Recording quality is too poor; results should be discarded/recollected. |

### 12.2 Current Blocking Reasons

The gate can block profiling for:

- Gamma EMG flood across analyzed tasks.
- Artifact-suspect feature burden.
- High-frequency saturation guard activation.
- Expectation-alignment failure when available.
- Across-task feature saturation.
- Poor channel quality or insufficient good-channel coverage.

### 12.3 Interpretation Scope

If `RESEARCH-ONLY`:

- OK: discuss artifact patterns, QC failures, physiological response candidates, and pipeline behavior.
- Not OK: subject profiles, cognitive scores, emotional traits, diagnostic labels, or personality-style inferences.

---

## 13. Current Known Limitations

1. **Baseline limitation**

   Eyes-closed baseline is not ideal for eyes-open cognitive or visual tasks. Future profile-ready reports should compare eyes-open tasks primarily to eyes-open or task-specific baselines.

2. **Fisher independence approximation**

   The Fisher omnibus is useful as an aggregate indicator, but it does not fully model correlation among EEG features.

3. **Gamma cannot be rescued by report filtering**

   Gamma flood exclusion prevents misinterpretation, but it does not clean the original data. Cleaner acquisition and/or validated ICA/CSD/CCA preprocessing are needed.

4. **HF saturation means contamination is tonic**

   If the saturation guard activates, the problem is not a few bad windows. The phase is broadly contaminated.

5. **Current output is not normative**

   The report compares this subject's task windows to their own baseline. It does not compare against age-matched or population norms.

6. **Q-value inconsistency in across-task omnibus rankings**

   If q-values are smaller than raw p-values in that section, the ranking is suppressed and should be treated as QC-only until the omnibus family alignment is fixed.

---

## 14. Recommended Path Toward Profile-Ready Use

To move from research-only exploratory analysis toward profile-compatible analysis:

1. Improve acquisition quality:
   - Lower impedances.
   - Stabilize cap fit.
   - Reduce jaw/face/neck movement.
   - Add explicit participant instructions for relaxed jaw and minimal facial movement.

2. Strengthen baselines:
   - Keep eyes-closed baseline for resting profile.
   - Use eyes-open baseline for eyes-open tasks.
   - Prefer task-specific pre-task baseline when possible.

3. Validate advanced cleaning:
   - Add/test ICA-based EMG component rejection.
   - Add/test surface Laplacian/CSD.
   - Add/test CCA-based muscle artifact suppression.
   - Report exactly which steps were applied.

4. Fix or remove unstable omnibus rankings:
   - Ensure p/q arrays remain aligned.
   - Do not show feature omnibus rankings unless adjusted q-values are mathematically valid.

5. Establish validation data:
   - Repeat clean sessions.
   - Test reliability across sessions.
   - Compare expected task signatures against literature and controlled paradigms.
   - Build normative or within-subject reliability criteria before any profiling claims.

---

## 15. Report Reading Checklist

Before interpreting any report, check:

1. `PROFILE SUITABILITY`.
2. Gamma EMG flood count and affected tasks.
3. Artifact-suspect feature counts.
4. HF saturation guard count.
5. Tasks executed versus tasks analyzed statistically.
6. Cross-task FWER result.
7. Baseline policy warning.
8. Channel quality and globally excluded channels.
9. Whether spatial/connectivity sections say interpretation is disabled.
10. Whether omnibus top-feature stats were suppressed.

If any of the first four items are severe, the report should remain research-only.

---

## 16. Summary

The current offline 64-channel pipeline is scientifically more conservative than earlier versions. It now blocks profiling when high-frequency contamination, gamma EMG flood, extreme effect sizes, or unstable task-level statistics are present. It also structurally prevents artifact-suspect and EMG-excluded gamma features from leaking into profile-facing feature lists or spatial interpretations.

The current example report is therefore not a failed profiling report; it is a correctly gated research-only/QC report showing that the session is too contaminated for profiling.

