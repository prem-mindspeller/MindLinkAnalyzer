# ANT Neuro eego 64-Channel EEG Integration

This folder contains all files related to the ANT Neuro eego 64-channel EEG headset integration.

## Three-Layer Architecture

The ANT Neuro analyzer follows the same three-layer inheritance pattern as the BrainLink analyzer:

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: AntNeuroAnalyzer_GUI_Sequential.py  (RUN THIS)     │
│  - Guided workflow wizard                                     │
│  - Session management                                         │
│  - Task recording                                             │
│  - Comprehensive export                                       │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: AntNeuroAnalyzer_GUI_Enhanced.py                   │
│  - Multi-channel feature extraction                           │
│  - Spatial features (coherence, PLI, asymmetry)              │
│  - ROI-based analysis                                         │
│  - Statistical testing (Kost-McDermott FDR)                  │
│  - Topographic visualization                                  │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: AntNeuroAnalyzer_GUI.py  (Base)                    │
│  - eego SDK connection                                        │
│  - MindSpeller authentication                                 │
│  - Basic streaming & visualization                            │
│  - Signal processing utilities                                │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

**IMPORTANT:** Use Python 3.13 (SDK rebuilt February 2026)

```powershell
# Option 1: Interactive test launcher
cd M:\CODEBASE\BrainLinkCompanion
.\antNeuro\run_tests.ps1

# Option 2: Direct test with Python 3.13
C:\Python313\python.exe antNeuro\test_antneuro_eego.py
C:\Python313\python.exe antNeuro\check_device_state.py

# Option 3: Use the batch file launcher
antNeuro\run_test.bat antNeuro\test_antneuro_eego.py
```

**Python Version Check:** All scripts now verify Python 3.13+ is being used and provide clear error messages if not.

**SDK Status:** Built for Python 3.13.5 from GitLab source (February 4, 2026)
- SDK Version: 1.3.29.57168
- Location: `eego_sdk_toolbox/eego_sdk.pyd`
- ⚠️ Known issue: Power detection doesn't work for USB-C powered EE225 models
- See [POWER_STATE_ISSUE.md](POWER_STATE_ISSUE.md) for details

## Files

### Application Scripts (Three-Layer Stack)
- **`AntNeuroAnalyzer_GUI.py`** - Base/Parent class
  - Core device connection with eego SDK
  - Authentication system
  - Basic EEG streaming and 64-channel visualization
  - Signal processing utilities (bandpass, notch, PSD)
  - Demo mode for testing without hardware

- **`AntNeuroAnalyzer_GUI_Enhanced.py`** - Enhanced child class
  - Inherits all base functionality
  - `EnhancedFeatureEngine` - Multi-channel feature extraction
  - `StatisticalEngine` - Kost-McDermott FDR, cluster correction
  - `TopographicWidget` - Scalp topography visualization
  - Spatial features: coherence, PLI, asymmetry

- **`AntNeuroAnalyzer_GUI_Sequential.py`** - Main application (RUN THIS)
  - Inherits all enhanced functionality
  - Session wizard for guided workflow
  - Task recording with configurable tasks
  - Comprehensive session export (CSV + JSON)

### Utility Scripts
- **`antneuro_data_acquisition.py`** - Standalone data acquisition module
  - Class: `AntNeuroDevice` - Low-level device interface
  - Can be used independently of GUI

- **`test_antneuro_eego.py`** - SDK test script
  - Tests SDK import
  - Discovers connected amplifiers
  - Verifies basic functionality

### Documentation
- **`ANT_Neuro_Integration_Plan.md`** - Complete integration plan and architecture
- **`ANT_Neuro_SDK_Developer_Setup_Guide.md`** - Step-by-step setup guide

## SDK Location

The compiled SDK toolbox is located at:
```
M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox\
```

Contains:
- `eego_sdk.pyd` - Python module
- `eego-SDK.dll` - ANT Neuro SDK library
- Runtime DLLs (libgcc, libstdc++, libwinpthread)

## Usage

### Quick Test
```powershell
cd M:\CODEBASE\BrainLinkCompanion\antNeuro
C:\Python313\python.exe test_antneuro_eego.py
```

### Import in Your Code
```python
import sys
sys.path.insert(0, '../antNeuro')
from antneuro_data_acquisition import AntNeuroDevice

device = AntNeuroDevice()
amplifiers = device.discover_amplifiers()
device.connect()
device.start_streaming(sample_rate=500)
```

## Requirements

- **Python**: 3.13+ (compiled for Python 3.13)
- **OS**: Windows 10/11 (64-bit)
- **Hardware**: ANT Neuro eego 64-channel amplifier
- **Dependencies**: numpy (for data processing)

## Environment Variables

Ensure these are set:
- `PYTHONPATH` = `M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox`
- `PATH` includes `C:\msys64\ucrt64\bin`

## Next Steps

1. Connect ANT Neuro headset hardware
2. Test device detection
3. Create GUI application for 64-channel visualization
4. Integrate with existing BrainLink analysis pipeline
5. Build standalone executable

## Related Files

- SDK source: `M:\CODEBASE\antneuroSDK\eego-sdk-pybind11-master`
- Build files: `M:\CODEBASE\antneuroSDK\eego-sdk-pybind11-master\BUILD`
- Toolbox: `M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox`
