# MindLink Analyzer

A desktop EEG cognitive-assessment application built with **Electron + React** and a **Python FastAPI** backend.

The app connects to a NeuroSky/BrainLink EEG headset, guides the user through a standardised session of cognitive tasks, and seeds the resulting brain-wave report to the Mindspeller API.

---

## Project Structure

```
MindLinkAnalyzer/
├── newBackend/          # Python FastAPI backend — serial parsing, signal processing, WebSocket
└── ElectronFrontEnd/    # Electron + React frontend — UI, session flow, API integration
```

## Main Applications

### BrainLink Analyzer (1-Channel)
**File**: `BrainLinkAnalyzer_GUI_Sequential_Integrated.py`

Features:
- Single-channel BrainLink headset support
- Real-time EEG streaming via Bluetooth
- Sequential protocol analysis (Eyes Open/Closed, Music, etc.)
- Feature extraction (band powers, ratios, statistics)
- Data export and visualization

**Usage**:
```powershell
python BrainLinkAnalyzer_GUI_Sequential_Integrated.py
```

### ANT Neuro Analyzer (64-Channel) [In Development]
**Location**: `antNeuro/`

Features:
- 64-channel EEG support
- High sampling rates (500Hz-2000Hz)
- Multi-channel visualization
- Advanced spatial analysis
- Professional-grade data acquisition

**Status**: SDK integrated, GUI development pending hardware availability

See `antNeuro/README.md` for details.

## Quick Start

### For BrainLink (1-Channel)
1. Pair BrainLink headset via Bluetooth
2. Run the main application:
   ```powershell
   python BrainLinkAnalyzer_GUI_Sequential_Integrated.py
   ```
3. Follow on-screen instructions

### For ANT Neuro (64-Channel)
1. Follow setup guide: `antNeuro/ANT_Neuro_SDK_Developer_Setup_Guide.md`
2. Ensure Python 3.13 is installed
3. Set environment variables (see guide)
4. Test SDK:
   ```powershell
   cd antNeuro
   C:\Python313\python.exe test_antneuro_eego.py
   ```

## Requirements

### Python Version
- **BrainLink**: Python 3.9+ (currently using 3.12)
- **ANT Neuro**: Python 3.13+ (required for SDK)

### Dependencies
```powershell
pip install -r config/requirements.txt
```

Key packages:
- `numpy` - Numerical computations
- `scipy` - Signal processing
- `matplotlib` / `pyqtgraph` - Visualization
- `PyQt5` - GUI framework
- `pyserial` - Serial communication

### Platform Support
- **Windows**: Full support (primary platform)
- **macOS**: Supported (see `docs/macOS_*` files)
- **Linux**: Experimental

## Building Executables

### Windows
```powershell
cd build_scripts
.\build_exe.ps1
```

### macOS
```bash
cd build_scripts
./build_macos_analyzer.sh
```

Output: Standalone `.exe` (Windows) or `.app` (macOS) files

## Documentation

### Analysis & Reporting
- **[Enhanced Report Generation Guide](docs/Enhanced_Report_Generation_Guide.md)** - Comprehensive 64-channel analysis reporting with statistical metrics, data quality validation, expectation-alignment analysis, and spatial insights
- **[Offline Analyzer Guide](docs/Offline_Analyzer_Guide.md)** - Standalone command-line tool for batch processing CSV files with production-ready reporting
- **[Statistical Methodology Review](docs/Statistical_Methodology_Review.md)** - Peer review-compliant statistical methods including sample size, artifact handling, confidence intervals, and cross-task correction

### Technical Documentation
- **[EEG Feature Extraction Formulas](docs/EEG_Feature_Extraction_Formulas.md)** - Mathematical formulas used
- **[BrainLink Implementation Report](docs/BrainLink_Python_Implementation_Report.md)** - Technical details
- **[Processing Architecture](docs/BrainLink_Processing_Architecture.md)** - System architecture

### Setup & Installation
- **[ANT Neuro Setup Guide](antNeuro/ANT_Neuro_SDK_Developer_Setup_Guide.md)** - Complete setup for 64-channel
- **[macOS Porting Guide](docs/macOS_Porting_Guide.md)** - Cross-platform notes
- **[Installation Summary](docs/INSTALLATION_SUMMARY.md)** - General installation

### Troubleshooting
- **[macOS Troubleshooting](docs/MacOS_TroubleshootingGuide.md)**
- **[Login Troubleshooting](docs/LoginTroubleshooting.md)**

## Development

### Running Tests
```powershell
cd tests
python test_algorithm.py
python test_brainlink_direct.py
```

### Debug Mode
```powershell
python tests/debug_data_flow.py
```

### Code Structure
- Main GUI applications in root directory
- Hardware-specific code in dedicated folders (`antNeuro/`)
- Shared utilities in `utils/`
- Platform-specific code documented in `docs/`

## Features

### Signal Processing
- FFT-based frequency analysis
- Band power extraction (Delta, Theta, Alpha, Beta, Gamma)
- Alpha peak detection
- Relative power calculations
- Statistical measures (mean, std, skewness, kurtosis)

### Analysis Protocols
- Baseline (Eyes Closed)
- Eyes Open comparison
- Meditation states
- Music response
- Custom protocols

### Data Export
- CSV format for raw data
- JSON for processed features
- Matplotlib plots
- Real-time visualization

## Environment Variables

### For ANT Neuro
```
PYTHONPATH=M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox
PATH+=C:\msys64\ucrt64\bin
```

## Support

- Check `docs/` folder for detailed documentation
- See `antNeuro/` for 64-channel specific help
- Review `tests/` for example usage

## Version History

- **v3.0** - ANT Neuro 64-channel integration (in progress)
- **v2.0** - Sequential protocol implementation
- **v1.0** - Initial BrainLink GUI analyzer

## License

[Add license information]

## Contributors

[Add contributor information]

---

## Documentation

| Component | File | Description |
|---|---|---|
| Python backend | [newBackend/STARTUP.md](newBackend/STARTUP.md) | Environment setup, dependency installation, and how to start the backend server |
| Electron frontend | [ElectronFrontEnd/DOCUMENTATION.md](ElectronFrontEnd/DOCUMENTATION.md) | Full architecture reference, module guide, data-flow diagrams, and build instructions |

---

## Quick Start

Both the backend and the frontend must be running at the same time.

### 1. Start the Python backend

```powershell
cd newBackend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. Start the Electron frontend

```powershell
cd ElectronFrontEnd
npm install
npm run dev
```
### . Build Instruction

Step 1 — build the backend (from workspace root, using conda Python):

cd m:\CODEBASE\MindLinkAnalyzer
C:\Users\conta\anaconda3\envs\brainlink\python.exe -m PyInstaller MindLinkBackend.spec --distpath newBackend/dist

Step 2 — package the Electron app (electron-builder picks up the backend folder automatically via extraResources):

cd ElectronFrontEnd
npm run package

# Equivalent: npx electron-builder
# The Electron Builder beforePack hook runs the webpack production build and
# verifies dist/index.html and dist/bundle.js before packaging.


See the linked documentation files above for full details, troubleshooting, and build instructions.
