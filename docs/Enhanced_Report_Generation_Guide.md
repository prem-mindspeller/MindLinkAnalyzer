# Enhanced 64-Channel Report Generation Guide
## Comprehensive Multi-Task EEG Analysis Reporting

**System**: BrainLink Companion - Enhanced Report Generator  
**Version**: 1.0  
**Date**: February 2026  
**Author**: BrainLink Companion Development Team

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Report Structure](#report-structure)
4. [Data Quality Validation](#data-quality-validation)
5. [Per-Task Statistical Analysis](#per-task-statistical-analysis)
6. [Expectation-Alignment Analysis](#expectation-alignment-analysis)
7. [64-Channel Spatial Analysis](#64-channel-spatial-analysis)
8. [Integration Points](#integration-points)
9. [Usage Examples](#usage-examples)
10. [Report Fields Reference](#report-fields-reference)

---

## Overview

### Purpose

The Enhanced 64-Channel Report Generator provides comprehensive, publication-quality reports for multi-task EEG analysis. It generates identical detailed reports for both:

- **GUI-based analysis** (displayed immediately after analysis, saved when "Generate Report" clicked)
- **Offline analysis** (standalone command-line processing of CSV files)

### Key Features

- **Data Quality Validation**: Automatic detection of garbage data (>70% significant features)
- **Per-Task Analysis**: Task-specific statistical summaries with band-specific effect sizes
- **Expectation-Alignment**: Grades task performance against neurophysiological expectations
- **64-Channel Spatial**: Regional activity, hemispheric asymmetry, and connectivity analysis
- **Statistical Rigor**: Fisher's combined p-value (Kost-McDermott corrected), permutation testing via SumP
- **Publication-Ready**: Formatted for scientific papers and clinical reports

### Report Scale

Each report contains:
- **8 major sections** (session info, per-task, combined, omnibus, spatial, configuration, glossary)
- **Per-task subsections**: 40-50 lines covering all statistical details
- **Total length**: 3,000-5,000 lines (depending on task count)
- **Generation time**: <5 seconds for 64-channel multi-task dataset

---

## Architecture

### Component Overview

```
┌──────────────────────────────────────────────────────────────┐
│          Enhanced64ChannelReportGenerator                     │
├──────────────────────────────────────────────────────────────┤
│  Static Method: generate_text_report()                        │
│  ├─ Input: results dict, fast_mode, n_permutations, config   │
│  └─ Output: List[str] (lines of formatted report)            │
├──────────────────────────────────────────────────────────────┤
│  Private Methods:                                             │
│  ├─ _generate_session_info()                                 │
│  ├─ _generate_glossary()                                     │
│  ├─ _generate_detailed_task_summary()                        │
│  ├─ _generate_combined_summary()                             │
│  ├─ _generate_omnibus_summary()                              │
│  ├─ _generate_multichannel_summary()                         │
│  ├─ _generate_expectation_alignment()                        │
│  └─ _generate_multichannel_summary()                         │
└──────────────────────────────────────────────────────────────┘
```

**New in v2.1**: The `config` parameter is now accepted to display preprocessing settings (line noise filtering, EMG threshold mode, bootstrap CI parameters).

### Data Flow

```
Analysis Engine Results
        ↓
    Multi-task_results {
      'per_task': {
        'task_name': {
          'analysis': {feature: {p, q, d, delta, ...}},
          'summary': {fisher, sum_p, ess, data_quality, expectation, ...}
        }
      },
      'combined': {...},
      'across_task': {...}
    }
        ↓
    Enhanced64ChannelReportGenerator.generate_text_report()
        ↓
    Formatted Report Lines
        ↓
    GUI Display OR File Save
```

---

## Report Structure

### Section 1: Session Information
Displays recording metadata and system configuration:
```
Session ID: user_2026-02-06_150540
User: user@brainlink.com
Recording Duration: 450.5 seconds
Total Samples: 225,250
Channels: 64
Sample Rate: 500 Hz
Baseline EC Windows: 4
Baseline EO Windows: 2
Tasks Executed: 3
```

### Section 2: Per-Task Statistical Summaries

Each task receives a detailed analysis subsection:

#### 2.1 Data Quality Warning (if applicable)
```
[mental_math]

NOTICE: *** DATA QUALITY WARNING ***
  CRITICAL: 88.5% of features marked significant - this exceeds the 70% threshold 
  and strongly suggests the data is noise/garbage, not real EEG. The headset may 
  not have been worn.
  [!] These results should NOT be interpreted as valid EEG analysis.
  *********************************************
```

#### 2.2 Statistical Metrics
```
KM correlation: k=1408, mean_offdiag_r=0.0836439, df_KM/(2k)=0.108006
Fisher_KM_p=0 sig=True df=15.1208
ESS: baseline=4, task=4, n_blocks=4
SumP=28.5573 p=0.00599401 sig=True perm=True
CompositeScore=779.482 Mean|d|=0.430687
Decision thresholds (band-specific): p≤0.012642, q≤0.012642
Correlation guard factor=0.47531 (m_eff=657.84/1408)
```

#### 2.3 Top 5 Significant Features
Displays effect sizes, p-values, and 95% confidence intervals for most impactful features:
```
Significant Features (adjusted thresholds, top 5 shown):
  gamma_power: p=0 q=7e-300 d=-1.24135 95%CI=[-1.45,-1.03] Δ=-0.135191 [GAMMA: EMG caution]
  beta_alpha_ratio: p=1.8e-290 q=2.5e-289 d=+1.32905 95%CI=[+1.08,+1.58] Δ=+0.154266
  alpha_relative: p=3.2e-185 q=4.1e-184 d=-0.89234 95%CI=[-1.12,-0.66] Δ=-0.082451
  ...
```

**New in v2.1**: 95% confidence intervals for Cohen's d are now displayed using percentile bootstrap (1000 iterations). Gamma features include EMG contamination warnings.

#### 2.4 Expectation-Alignment Analysis
Shows how well results match expected neurophysiological patterns:
```
⎯⎯⎯ Expectation-Alignment Analysis ⎯⎯⎯
Grade: A
Passed Features (n=13):
  theta_power (down): Δ%=-23.4051, p_dir=7.06111e-71 | rule=p
  alpha_relative (down): Δ%=-18.2945, p_dir=9.12e-65 | rule=p
  ...
Top Drivers (by |d|):
  gamma_power: |d|=1.24135
  ...
Notes:
  All key features (α↓, β/ratio↑, γ↑) passed
```

### Section 3: Combined Task Aggregate
Omnibus statistics across all tasks combined:
```
Combined Task Aggregate
Fisher_KM_p=7.542193660571726e-54 sig=True df=987.2341
SumP=45.2134 p=0.0049 sig=True perm=True
CompositeScore=1245.923 Mean|d|=0.623451
```

### Section 4: Across-Task Omnibus
Features showing consistent effects across tasks:
```
Across-Task Omnibus (Feature Stability)
Features tested: 1408 | Significant (FDR 0.05): 43
Significant features: alpha_power, alpha_relative, beta_alpha_ratio, gamma_power, ...
Top Feature Omnibus Stats (up to 5):
  gamma_power: stat=82.45 p=0 q=0
  beta_alpha_ratio: stat=71.23 p=1.3e-67 q=1.8e-66
```

### Section 5: 64-Channel Spatial & Connectivity Analysis

#### 5.1 Regional Activity Summary
Activity by brain region and frequency band:
```
Regional Activity Summary
Frontal Region:
  Delta  : 2 sig features ↑ (avg |d|=0.234, max |d|=0.345)
  Theta  : 4 sig features ↓ (avg |d|=0.512, max |d|=0.678)
  Alpha  : 8 sig features ↓ (avg |d|=0.623, max |d|=0.891)
  Beta   : 6 sig features ↑ (avg |d|=0.445, max |d|=0.756)
  Gamma  : 3 sig features ↑ (avg |d|=0.567, max |d|=0.834)
```

#### 5.2 Hemispheric Asymmetry Analysis
Left vs right hemisphere lateralization:
```
Hemispheric Asymmetry Analysis
Delta  : Left sig=1 (avg |d|=0.234) | Right sig=2 (avg |d|=0.345) | Asymmetry=+0.189 (Left)
Theta  : Left sig=3 (avg |d|=0.512) | Right sig=2 (avg |d|=0.401) | Asymmetry=+0.121 (Left)
...
```

#### 5.3 Inter-Channel Coherence & Connectivity
Functional connectivity changes:
```
Inter-Channel Coherence & Connectivity
Significant Coherence Changes: 12 features
Top Connectivity Changes:
  frontal_central_coherence_alpha: increased (d=+0.512, p=3.4e-45)
  temporal_parietal_coherence_beta: increased (d=+0.467, p=1.2e-38)
...
Net Connectivity: 9 increased, 3 decreased
Overall pattern suggests enhanced functional integration
```

### Section 6: Configuration & Provenance
Technical settings, preprocessing details, and processing parameters:
```
Mode=aggregate_only | alpha=0.05 | dependence=Kost-McDermott
Permutation testing: n_perm=1000 (block-level SumP, p-value resolution: 0.0010)
Effect measure: delta | Discretization bins: 5 | FDR alpha: 0.05
Multi-channel: 64-channel EEG (10-20 extended system)
Baseline: eyes-closed only (eyes-open retained for reference, not pooled).

Preprocessing Applied:
  - Notch filter: 60 Hz + harmonics (Q=30)
  - EMG threshold: Adaptive (baseline_mean + 2xSD)
  - Bootstrap 95% CI: 1000 iterations (percentile method)
  - Block aggregation: 4.0s blocks (min 8 per condition)
  - Average reference: Applied

Phase-Based Recording:
  • Only phases marked 'record=True' in task definitions are processed
  • Cognitive tasks (mental_math, etc.): Record only 'task' phase (52s)
  • Protocol tasks (diverse_thinking, reappraisal): Record 'thinking' phases (30s)
  • Visual tasks (curiosity, num_form): Record 'viewing'/'video' phases
```

**New in v2.1**: Preprocessing section now explicitly documents notch filtering, EMG threshold mode (adaptive vs fixed), bootstrap CI settings, and block aggregation parameters.

### Section 7: Glossary
Metric definitions:
```
Fisher_KM: Fisher combined p-value adjusted with Kost–McDermott correlation correction.
           Combines p-values from independent features accounting for correlations.
...
```

---

## Data Quality Validation

### Automatic Detection

The enhanced report generator automatically detects and flags suspicious results:

#### Thresholds
- **>70% significant features**: CRITICAL - Garbage data (headset not worn)
- **>50% significant features**: WARNING - Suspicious, investigate  
- **5-30% significant features**: NORMAL - Real EEG data

#### Why This Works

Real cognitive tasks affect **specific brain regions and pathways**, not the entire brain uniformly. A change of 88.5% of features (1,200+ out of 1,408) indicates:
- Systematic noise (60 Hz interference, motion artifact)
- Missing reference signal
- Equipment malfunction
- Data not properly recorded

#### Example Output

```
⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯
[mental_math]

NOTICE: *** DATA QUALITY WARNING ***
  CRITICAL: 88.5% of features marked significant - this exceeds the 70% threshold 
  and strongly suggests the data is noise/garbage, not real EEG. The headset may 
  not have been worn.
  [!] These results should NOT be interpreted as valid EEG analysis.
  Significant: 1236/1408 (88.5% - expected <30% for real data)
⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯
```

### Reliability Flag

Each task summary includes a `data_quality` object:
```python
{
  'reliable': False,           # Boolean: results trustworthy?
  'warnings': [...],           # List of warning messages
  'sig_prop': 0.885,           # Proportion of significant features
  'sig_count': 1236,           # Number of significant features
  'total_features': 1408       # Total features tested
}
```

---

## Per-Task Statistical Analysis

### Statistics Included

Each task report includes all these metrics:

#### 1. KM Correlation
```
KM correlation: k=1408, mean_offdiag_r=0.0836439, df_KM/(2k)=0.108006
```
- **k**: Number of features tested
- **mean_offdiag_r**: Average off-diagonal correlation
- **df_KM/(2k)**: Kost-McDermott degrees of freedom ratio (correction factor)

#### 2. Fisher's Combined P-value
```
Fisher_KM_p=0 sig=True df=15.1208
```
- **KM_p**: Combined p-value from multiple features (corrected for correlation)
- **sig**: Boolean significance flag
- **df**: Degrees of freedom for F-distribution

#### 3. Effective Sample Size (ESS)
```
ESS: baseline=4, task=4, n_blocks=4
```
- **baseline**: Number of baseline windows/blocks
- **task**: Number of task windows/blocks
- **n_blocks**: Maximum of the two

#### 4. SumP (Sum of P-values)
```
SumP=28.5573 p=0.00599401 sig=True perm=True
```
- **value**: Sum of test statistics across features
- **p**: P-value from permutation distribution (if `perm=true`) or chi-square (if `perm=false`)
- **sig**: Significance after FDR correction
- **perm**: Whether permutation testing was used

#### 5. CompositeScore & Mean|d|
```
CompositeScore=779.482 Mean|d|=0.430687
```
- **CompositeScore**: Weighted combination of Fisher and SumP statistics
- **Mean|d|**: Average absolute effect size magnitude

#### 6. Decision Thresholds
```
Decision thresholds (band-specific): p≤0.012642, q≤0.012642
Effect sizes: α≥0.25, β≥0.35, γ≥0.30, θ≥0.30, ratios≥0.30
Percent change: relative features≥5%, absolute≥10%
```

#### 7. Correlation Guard Factor
```
Correlation guard=0.47531 (m_eff=657.84/1408)
```
Accounts for correlated features reducing degrees of freedom.

#### 8. Top Features
```
Significant Features (adjusted thresholds, top 5 shown):
  gamma_power: p=0 q=7e-300 Δ=-0.135191 d=-1.24135 task_mean=0.260637 base_mean=0.395828 bin=4
```

- **p**: Raw p-value from Welch's t-test
- **q**: FDR-adjusted p-value (Benjamini-Hochberg)
- **Δ**: Absolute difference (task_mean - baseline_mean)
- **d**: Cohen's d effect size
- **task_mean**: Mean value during task
- **base_mean**: Mean value during baseline
- **bin**: Discretization bin (1-5, where 5 = highest effect)

---

## Expectation-Alignment Analysis

### Purpose

Compares observed changes against known neurophysiological patterns for each task type.

### Task-Specific Expectations

#### Mental Math
**Expected Pattern**: α↓, β↑, β/α ratio↑, γ↑
- Reduced alpha (focused attention)
- Increased beta (working memory)
- Increased gamma (cognitive engagement)

Grading Rule: **Grade A** if all key features passed; **Grade B** if core features (α↓, β/ratio↑) passed

#### Attention Focus
**Expected Pattern**: α↓, β↑, β/α ratio↑
Grading Rule: **Grade A** if (α↓) AND (β↑ OR ratio↑)

#### Visual Imagery
**Expected Pattern**: α↑, α/θ ratio↑
Grading Rule: **Grade A** if α↑ OR ratio↑ (visual areas dominant)

#### Working Memory
**Expected Pattern**: θ↑, α↓, β/α ratio↑
Grading Rule: **Grade A** if θ↑ AND (α↓ OR ratio↑)

#### Cognitive Load
**Expected Pattern**: θ↑, α↓
Grading Rule: **Grade A** if θ↑ AND α↓

### Report Output

```
⎯⎯⎯ Expectation-Alignment Analysis ⎯⎯⎯
Grade: A
Passed Features (n=13):
  theta_power (down): Δ%=-23.4051, p_dir=7.06111e-71 | rule=p
  alpha_relative (down): Δ%=-18.2945, p_dir=9.12e-65 | rule=p
  beta_relative (up): Δ%=+34.5612, p_dir=3.21e-78 | rule=p
  ...
Top Drivers (by |d|):
  gamma_power: |d|=1.24135
  beta_relative: |d|=1.18045
Notes:
  All key features (α↓, β/ratio↑, γ↑) passed
```

#### Grade Interpretation
- **Grade A**: All key neurophysiological patterns present (excellent alignment)
- **Grade B**: Core patterns present (good alignment)
- **Grade C**: Some patterns present (partial alignment)
- **Grade D**: Minimal pattern match (poor alignment)
- **Grade N/A**: Insufficient data for grading

#### p_dir Field
One-sided p-value testing directional hypothesis:
- θ expected up: p-value from one-sided t-test (θ > baseline)
- α expected down: p-value from one-sided t-test (α < baseline)

---

## 64-Channel Spatial Analysis

### Regional Activity Summary

Aggregates data across brain regions (5 regions × 5 bands = 25 regional combinations):

```
Frontal Region:
  Delta  : 2 sig features ↑ ...  (↑ = more significant ups than downs)
  Theta  : 4 sig features ↓ ...
  Alpha  : 8 sig features ↓ ...
  Beta   : 6 sig features ↑ ...
  Gamma  : 3 sig features ↑ ...
```

**Interpretation**:
- ↑ indicates net increase in activity
- ↓ indicates net decrease
- Count = number of significant regional features

### Hemispheric Asymmetry
```
Delta  : Left sig=1 (avg |d|=0.234) | Right sig=2 (avg |d|=0.345) | 
         Asymmetry=+0.189 (Left)
```

**Asymmetry Index** = (Left Avg - Right Avg) / (Left Avg + Right Avg)

Range: -1.0 (right dominant) to +1.0 (left dominant)

Interpretation:
- |Index| > 0.1: Clear hemispheric dominance
- |Index| < 0.1: Balanced bilateral activity

### Inter-Channel Coherence & Connectivity

Shows changes in synchronized activity between regions:

```
Coherence Features: 12 significant
Top Connectivity Changes:
  frontal_central_coherence_alpha: increased (d=+0.512, p=3.4e-45)
  temporal_parietal_coherence_beta: decreased (d=-0.289, p=2.1e-32)
...
Net Connectivity: 9 increased, 3 decreased
Overall pattern suggests enhanced functional integration
```

---

## Integration Points

### GUI Integration (BrainLinkAnalyzer_GUI_Sequential_Integrated.py)

#### 1. Results Display (Immediate)
After multi-task analysis completes:
```python
# In _display_results():
config = getattr(engine, 'config', None)
fast_mode = getattr(config, 'fast_mode', True) if config else True
n_perm = getattr(config, 'n_perm', 1000) if config else 1000

report_lines = Enhanced64ChannelReportGenerator.generate_text_report(
    results=results_data,
    fast_mode=fast_mode,
    n_permutations=n_perm,
    config=config  # New: pass config for preprocessing info
)
results_text = "\n".join(report_lines)
self.results_text.setPlainText(results_text)
```

#### 2. Report Generation (User-Triggered)
When user clicks "Generate Report" button:
```python
# In _generate_report_text():
report_lines = Enhanced64ChannelReportGenerator.generate_text_report(
    results=results,
    fast_mode=fast_mode,
    n_permutations=n_perm,
    config=config
)
self.generated_report_text = "\n".join(report_lines)
# Save to file when user selects location
```

### Offline Analyzer Integration (BrainLink_Offline_Analyzer.py)

```python
# In _generate_text_report():
results_for_report = {
    'session_info': {...},
    'analysis_results': {...},
    'multi_task_results': {...},
    'baseline_stats': {...}
}
lines = Enhanced64ChannelReportGenerator.generate_text_report(
    results=results_for_report,
    fast_mode=self.fast_mode,
    n_permutations=self.n_permutations,
    config=self.config  # New: pass config for preprocessing info
)
with open(output_path, 'w') as f:
    f.write('\n'.join(lines))
```

### Data Structures Required

The report generator expects this input structure:

```python
{
    'session_info': {
        'session_id': str,
        'user_email': str,
        'duration': float,
        'n_samples': int,
        'n_channels': int,
        'sample_rate': float,
        'baseline_ec_windows': int,
        'baseline_eo_windows': int,
        'tasks_executed': int
    },
    'artifact_summary': dict,
    'analysis_results': dict,  # {feature_name: {p, q, d, delta, ...}}
    'multi_task_results': {
        'per_task': {
            'task_name': {
                'summary': {
                    'fisher': {km_p, km_df, km_mean_r, k_features, ...},
                    'sum_p': {value, perm_p, significant, permutation_used, ...},
                    'ess': {baseline_blocks, task_blocks, block_seconds, ...},
                    'composite': {score, ranking_only, ...},
                    'feature_selection': {total_features, sig_feature_count, ...},
                    'data_quality': {reliable, warnings, sig_prop, ...},
                    'expectation': {grade, passes, top_drivers, notes, ...},
                    'effect_size_mean': float
                },
                'analysis': {feature_name: {...}}
            }
        },
        'combined': {...},
        'across_task': {...}
    },
    'baseline_stats': dict,
    'artifact_summary': dict
}
```

---

## Usage Examples

### Example 1: GUI Analysis Report

After user records tasks and clicks "Analyze", report immediately appears in results area:

```
==============================================================================
64-CHANNEL MULTI-TASK EEG ANALYSIS REPORT
==============================================================================

SESSION INFORMATION
────────────────────────────────────────
Session ID: session_20260206_150540
User: test.user@brainlink.com
Recording Duration: 425.3 seconds
Total Samples: 212,650
Channels: 64
Sample Rate: 500 Hz
Baseline EC Windows: 4
Baseline EO Windows: 2
Tasks Executed: 2

Per-Task Statistical Summaries
────────────────────────────────────────

[mental_math]

  KM correlation: k=1408, mean_offdiag_r=0.0836, df_KM/(2k)=0.1080
  Fisher_KM_p=0 sig=True df=15.1208
  ESS: baseline=4, task=4, n_blocks=4
  SumP=28.5573 p=0.006 sig=True perm=True
  CompositeScore=779.482 Mean|d|=0.4307
  Decision thresholds (band-specific): p≤0.012642, q≤0.012642
  ...
```

User can:
- Read results directly on screen
- Click "Generate Report" to save detailed version
- Examine specific features and statistics

### Example 2: Offline Analysis Report

Command line:
```bash
python BrainLink_Offline_Analyzer.py "session_data.csv" --fast --output "report.txt"
```

Output file contains same comprehensive report, saved to `report.txt`.

### Example 3: Report Extraction in Code

```python
from utils.enhanced_report_generator import Enhanced64ChannelReportGenerator

results = {
    'session_info': {...},
    'multi_task_results': multi_task_results,
    'analysis_results': analysis_results,
    ...
}

# Create or obtain config object (optional but recommended)
from BrainLinkAnalyzer_GUI_Enhanced import EnhancedAnalyzerConfig
config = EnhancedAnalyzerConfig()  # Or obtain from engine

report_lines = Enhanced64ChannelReportGenerator.generate_text_report(
    results=results,
    fast_mode=True,
    n_permutations=1000,
    config=config  # Optional: enables preprocessing info display
)

# Save to file
with open('analysis_report.txt', 'w') as f:
    f.write('\n'.join(report_lines))

# Or process lines
for line in report_lines:
    if 'significant' in line.lower():
        print(f"KEY FINDING: {line}")
```

---

## Report Fields Reference

### Task Summary Fields

| Field | Type | Description |
|-------|------|-------------|
| fisher.km_p | float | Combined p-value (Kost-McDermott corrected) |
| fisher.km_df | float | Degrees of freedom |
| fisher.km_mean_r | float | Mean off-diagonal correlation |
| fisher.k_features | int | Number of features tested |
| fisher.significant | bool | Significance after correction |
| sum_p.value | float | Sum of test statistics |
| sum_p.perm_p | float | P-value from permutation distribution |
| sum_p.significant | bool | Significance flag |
| ess.baseline_blocks | int | Baseline window count |
| ess.task_blocks | int | Task window count |
| composite.score | float | Composite statistical score |
| feature_selection.total_features | int | Total features tested |
| feature_selection.sig_feature_count | int | Significant features |
| data_quality.reliable | bool | Results trustworthy? |
| data_quality.sig_prop | float | Proportion significant (0-1) |
| expectation.grade | str | A/B/C/D grade |
| expectation.passes | list | Features meeting expectations |

### Feature-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| p_value | float | Raw p-value from Welch's t-test |
| q_value | float | FDR-adjusted p-value |
| delta | float | Task mean - Baseline mean |
| effect_size_d | float | Cohen's d |
| d_ci_lower | float | 95% CI lower bound for Cohen's d (bootstrap) |
| d_ci_upper | float | 95% CI upper bound for Cohen's d (bootstrap) |
| task_mean | float | Mean during task |
| baseline_mean | float | Mean during baseline |
| significant_change | bool | Passed significance criterion |
| bin | int | Discretization bin (1-5) |
| discrete_index | int | Quantile bin |

---

## Summary

The Enhanced 64-Channel Report Generator provides:

✓ **Instant Reporting**: Results displayed in GUI immediately after analysis  
✓ **Publication Quality**: Complete statistical details with proper corrections  
✓ **Data Quality Assurance**: Automatic garbage data detection  
✓ **Comprehensive Analysis**: All statistical metrics in one place  
✓ **Task Validation**: Expectation-alignment shows if results make sense  
✓ **Spatial Insights**: 64-channel specific regional and connectivity analysis  
✓ **Reproducible**: Same format for GUI and offline processing  

---

**For technical support or questions about report interpretation, contact the BrainLink Companion development team.**
