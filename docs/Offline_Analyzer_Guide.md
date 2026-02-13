# BrainLink Offline Analyzer - User Guide

## Overview

The **BrainLink Offline Analyzer** is a standalone, production-grade application for analyzing 64-channel EEG data recorded during BrainLink sessions. It processes raw CSV files and generates comprehensive analysis reports without requiring the full GUI application.

### Key Features

- **Standalone**: No GUI required - runs from command line
- **Flexible Modes**: Fast mode (~30 seconds) or Full mode (10-20 minutes)
- **Comprehensive Reports**: Detailed analysis with statistical significance testing
- **Artifact Detection**: Automatic detection and removal of bad channels/segments
- **Multi-Format Output**: Text, HTML, or PDF reports
- **Production Ready**: Robust error handling, logging, and validation

---

## Installation

### Prerequisites

1. **Python 3.8+** installed
2. **Required packages** (install via pip):

```bash
pip install numpy pandas scipy
```

3. **Optional for PDF reports**:

```bash
pip install reportlab
```

### Setup

The analyzer is part of the BrainLinkCompanion codebase. Ensure you have:

- `BrainLink_Offline_Analyzer.py`
- `antNeuro/offline_multichannel_analysis.py`
- `BrainLinkAnalyzer_GUI_Enhanced.py`

All in the same directory structure.

---

## Quick Start

### Basic Usage (Fast Mode)

```bash
python BrainLink_Offline_Analyzer.py session_20260206_150540_user_email_com.csv
```

This will:
- Analyze the CSV file in **fast mode** (~30 seconds)
- Auto-detect markers file if available
- Generate a text report: `analysis_report_fast_YYYYMMDD_HHMMSS.txt`

### With Markers File

```bash
python BrainLink_Offline_Analyzer.py session_data.csv --markers markers_data.json
```

### Full Mode (Permutation Testing)

```bash
python BrainLink_Offline_Analyzer.py session_data.csv --full --permutations 500
```

This will:
- Use **full permutation testing** (~10-15 minutes for 500 permutations)
- Provide publication-grade statistical rigor
- Generate report: `analysis_report_full_YYYYMMDD_HHMMSS.txt`

### HTML Output

```bash
python BrainLink_Offline_Analyzer.py session_data.csv --format html
```

---

## Command-Line Options

```
usage: BrainLink_Offline_Analyzer.py [-h] [--markers MARKERS] [--fast] [--full]
                                      [--output OUTPUT] [--format {txt,html,pdf}]
                                      [--permutations PERMUTATIONS] [--version]
                                      csv_file

positional arguments:
  csv_file                    Path to CSV file with raw EEG data

optional arguments:
  -h, --help                  Show help message
  --markers MARKERS           Path to phase markers JSON file
  --fast                      Use fast mode (parametric tests, ~30s) [DEFAULT]
  --full                      Use full mode (permutation tests, ~10-20min)
  --output OUTPUT             Output report file path (auto-generated if omitted)
  --format {txt,html,pdf}     Output format (default: txt)
  --permutations PERMUTATIONS Number of permutations for full mode (default: 200)
  --version                   Show version number
```

---

## Input File Format

### CSV File Structure

The CSV file should contain:

```csv
timestamp,sample_index,Fp1,Fp2,F7,F3,Fz,F4,F8,...
0.000,0,-2.45,1.32,-0.98,...
0.002,1,-2.52,1.28,-1.02,...
0.004,2,-2.48,1.35,-0.95,...
```

**Required columns:**
- `timestamp`: Time in seconds (relative to recording start)
- `sample_index`: Sequential sample number

**Channel columns:**
- All remaining columns are treated as EEG channels
- Standard 64-channel montage expected (10-20 system)

### Markers File (JSON)

Optional JSON file with task phase markers:

```json
{
  "session_id": "session_20260206_150540",
  "user_email": "user@email.com",
  "sample_rate": 500,
  "channel_count": 64,
  "channel_names": ["Fp1", "Fp2", "F7", ...],
  "phase_markers": [
    {
      "phase": "baseline",
      "task": null,
      "start": 0.0,
      "end": 60.0
    },
    {
      "phase": "task",
      "task": "focus_task",
      "start": 60.0,
      "end": 120.0
    }
  ]
}
```

If no markers file is provided, the analyzer will:
1. Look for `markers_<csv_stem>.json` in the same directory
2. If not found, analyze the entire recording as one segment

---

## Analysis Modes

### Fast Mode (Default)

**Duration:** ~30 seconds  
**Statistical Method:** Parametric tests with chi-square approximation

**Workflow:**
1. Feature extraction (~10s)
2. Welch's t-test for each feature (~5s)
3. Fisher's method with χ² approximation (~1s)
4. FDR multiple comparison correction (~1s)
5. Report generation (~5s)

**Use when:**
- Quick exploratory analysis needed
- Preliminary screening before full analysis
- Real-time feedback required
- Large number of sessions to process

**Accuracy:** Chi-square approximation is excellent for k > 20 features (error < 1%). With 1,400+ features, error is negligible (< 0.1%).

### Full Mode

**Duration:** 10-20 minutes (depending on permutations)  
**Statistical Method:** Block permutation testing with Kost-McDermott correction

**Workflow:**
1. Feature extraction (~10s)
2. Permutation testing (50-1000 iterations, ~2-20min)
   - Shuffle task/baseline labels
   - Recompute statistics
   - Build null distribution
3. Multiple comparison correction (~10s)
4. Report generation (~10s)

**Permutation Presets:**
- `--permutations 50`: Ultrafast (~2 min)
- `--permutations 100`: Fast (~3 min)
- `--permutations 200`: Default (~5 min)
- `--permutations 500`: Strict (~10 min)
- `--permutations 1000`: Research grade (~20 min)

**Use when:**
- Publication-quality analysis required
- Conservative significance testing needed
- No assumption about data distribution
- Final confirmatory analysis

---

## Report Contents

> **Note**: As of February 2026, the offline analyzer uses the **Enhanced 64-Channel Report Generator** which provides significantly more detailed analysis than documented here. For comprehensive information about report structure, statistical metrics, data quality validation, expectation-alignment analysis, and 64-channel spatial insights, see the [Enhanced Report Generation Guide](Enhanced_Report_Generation_Guide.md).

### 1. Session Information
- Session ID
- User email
- Recording duration
- Sample count
- Channel count
- Sample rate

### 2. Artifact Detection Summary
- Bad channels detected
- Flat channels (< 0.1 µV std)
- Noisy channels (> 200 µV amplitude)
- Artifact windows removed
- Average channel quality score

### 3. Feature Extraction Summary
- **Per-Channel Features** (1,088 total)
  - Band powers: delta, theta, alpha, beta, gamma
  - Relative powers
  - Peak frequencies
  - Cross-band ratios (alpha/theta, beta/alpha)

- **Regional Features** (60 total)
  - 5 regions: Frontal, Central, Temporal, Parietal, Occipital
  - Aggregated band powers per region

- **Spatial Features** (~140 total)
  - Hemispheric asymmetry (27 pairs × 5 bands)
  - Frontal alpha asymmetry (FAA)
  - Inter-regional coherence
  - Global field power (GFP)

### 4. Task Analysis Results

For each task:
- **Fisher KM p-value**: Overall task significance
- **SumP p-value**: Combined feature significance
- **Significant features count**: Number of features showing significant change
- **Top 10 significant features**: Ranked by effect size
  - Feature name
  - Delta (Δ): Change from baseline
  - P-value: Statistical significance
  - Cohen's d: Effect size

---

## Output Files

### Text Report (`.txt`)

Plain text format, human-readable:

```
================================================================================
BRAINLINK OFFLINE 64-CHANNEL EEG ANALYSIS REPORT
================================================================================

Generated: 2026-02-06 15:30:45
Analysis Mode: FAST (Parametric Tests)

SESSION INFORMATION
----------------------------------------
Session ID: session_20260206_150540
User: user@email.com
Recording Duration: 180.0 seconds
Samples: 90,000
Channels: 64
Sample Rate: 500 Hz

ARTIFACT DETECTION SUMMARY
----------------------------------------
Bad channels detected: 2
Flat channels: 1
Noisy channels: 1
Artifact windows removed: 5
Average channel quality: 0.87
Good channels (quality ≥ 0.7): 62/64

...
```

### HTML Report (`.html`)

Web-formatted report with styling:
- Color-coded sections
- Responsive layout
- Can be opened in any web browser
- Includes embedded CSS styling

### PDF Report (`.pdf`)

Professional PDF document:
- Requires `reportlab` package
- Paginated layout
- Suitable for archiving

---

## Examples

### Example 1: Quick Analysis

```bash
# Analyze a session file quickly
python BrainLink_Offline_Analyzer.py data/session_20260206.csv
```

**Output:**
```
2026-02-06 15:30:20 - INFO - Initialized analyzer for: session_20260206.csv
2026-02-06 15:30:20 - INFO - Mode: FAST (200 permutations)
2026-02-06 15:30:20 - INFO - Loading CSV data...
2026-02-06 15:30:22 - INFO - Loaded 90000 samples
2026-02-06 15:30:22 - INFO - Detected 64 EEG channels
2026-02-06 15:30:23 - INFO - Auto-detected markers file: markers_20260206.json
2026-02-06 15:30:23 - INFO - Starting Offline EEG Analysis
2026-02-06 15:30:25 - INFO - Extracting features from raw data...
2026-02-06 15:30:30 - INFO - Feature extraction progress: 50%
2026-02-06 15:30:40 - INFO - Feature extraction progress: 100%
2026-02-06 15:30:42 - INFO - Running statistical analysis...
2026-02-06 15:30:45 - INFO - Analysis Complete!
2026-02-06 15:30:46 - INFO - Generating TXT report: analysis_report_fast_20260206_153046.txt
2026-02-06 15:30:46 - INFO - SUCCESS!
2026-02-06 15:30:46 - INFO - Report available at: M:\CODEBASE\BrainLinkCompanion\analysis_report_fast_20260206_153046.txt
```

### Example 2: Full Mode with Custom Settings

```bash
# Research-grade analysis with 1000 permutations and HTML output
python BrainLink_Offline_Analyzer.py session_data.csv \
  --full \
  --permutations 1000 \
  --markers markers.json \
  --format html \
  --output final_analysis_report.html
```

### Example 3: Batch Processing

```bash
# Analyze multiple sessions in a loop (Windows PowerShell)
Get-ChildItem *.csv | ForEach-Object {
    python BrainLink_Offline_Analyzer.py $_.FullName --fast
}
```

---

## Troubleshooting

### Error: "CSV file not found"

**Solution:** Check file path is correct and file exists.

```bash
# Use absolute path
python BrainLink_Offline_Analyzer.py "C:\Users\Data\session.csv"
```

### Error: "CSV must contain 'timestamp' and 'sample_index' columns"

**Solution:** Verify CSV has required columns. Check header row.

### Warning: "No markers file found"

**Info:** This is not an error. The analyzer will process the entire recording as one segment.

**To fix:** Provide markers file with `--markers` option or ensure auto-detection works.

### Analysis Very Slow

**Symptoms:** Full mode taking > 30 minutes

**Solutions:**
- Reduce permutations: `--permutations 100`
- Switch to fast mode: `--fast`
- Check system resources (CPU, RAM)

### Low Channel Quality

**Symptom:** Many channels flagged as bad in artifact summary

**Check:**
- Recording quality during session
- Electrode contact impedance
- Environmental noise
- Bad channels are automatically interpolated

---

## Performance Benchmarks

**Test System:** Intel i7-9700K, 16GB RAM, Windows 11

| Mode | Permutations | Duration | Use Case |
|------|-------------|----------|----------|
| Fast | N/A | ~30s | Exploratory, quick feedback |
| Full (ultrafast) | 50 | ~2 min | Initial screening |
| Full (fast) | 100 | ~3 min | Standard analysis |
| Full (default) | 200 | ~5 min | Balanced rigor/speed |
| Full (strict) | 500 | ~10 min | Conservative testing |
| Full (research) | 1000 | ~20 min | Publication quality |

**Note:** Times may vary based on:
- Number of task phases
- Recording duration
- System performance
- Number of features extracted

---

## Integration with Main Application

This standalone analyzer is designed to work seamlessly with data exported from the main BrainLinkAnalyzer GUI application.

**Workflow:**
1. Record session in main GUI (creates CSV + markers JSON)
2. Files saved to: `C:\Users\<user>\BrainLink_Recordings\`
3. Run offline analyzer on saved files
4. Generate reports for archiving or sharing

**File naming convention:**
- CSV: `session_YYYYMMDD_HHMMSS_user_email_com.csv`
- Markers: `markers_YYYYMMDD_HHMMSS.json`

The analyzer automatically pairs CSV with markers if they share the same timestamp.

---

## API Usage (Python Integration)

You can also use the analyzer programmatically in your own Python scripts:

```python
from BrainLink_Offline_Analyzer import OfflineEEGAnalyzer

# Create analyzer
analyzer = OfflineEEGAnalyzer(
    csv_file='session_data.csv',
    markers_file='markers_data.json',
    fast_mode=True,  # or False for full mode
    n_permutations=200
)

# Run analysis
results = analyzer.analyze()

# Generate report
report_path = analyzer.generate_report(
    output_file='my_report.html',
    format='html'
)

# Access results programmatically
session_info = results['session_info']
multi_task = results['multi_task_results']
artifact_summary = results['artifact_summary']
```

---

## Technical Details

### Statistical Methods

**Fast Mode:**
- Per-feature: Welch's t-test (unequal variances)
- Combined: Fisher's method with chi-square approximation
- Multiple comparisons: Benjamini-Hochberg FDR correction

**Full Mode:**
- Per-feature: Welch's t-test (unequal variances)
- Combined: Block permutation testing (maintains temporal structure)
- Multiple comparisons: Kost-McDermott correction

### Artifact Removal

**Detection criteria:**
- Flat channels: std < 0.1 µV
- Noisy channels: peak-to-peak > 200 µV
- Artifact windows: amplitude > 150 µV

**Removal method:**
- Bad channels: Spherical spline interpolation from neighbors
- Artifact windows: Linear interpolation across time

### Channel Quality Score

$$Q_i = \left(1 - \frac{\text{artifacts}_i}{\text{total\_windows}}\right) \times \left(1 - \text{is\_bad}_i\right)$$

Where:
- $Q_i \in [0, 1]$: Quality score for channel $i$
- $\text{artifacts}_i$: Number of artifact windows in channel $i$
- $\text{is\_bad}_i \in \{0, 1\}$: Whether channel is bad (flat or noisy)

---

## Version History

### Version 1.0.0 (February 2026)
- Initial release
- Fast mode and full mode support
- Multi-format reporting (txt, html, pdf)
- Automatic artifact detection and removal
- Comprehensive statistical analysis
- Production-grade error handling

---

## Support

For issues, questions, or feature requests:
1. Check this guide and troubleshooting section
2. Review the main application documentation
3. Contact the BrainLinkCompanion development team

---

## License

Part of the BrainLinkCompanion suite.  
© 2026 BrainLink Companion Team
