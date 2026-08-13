# ANT Neuro eego 64-Channel EEG Integration Plan

## Setup Complete ✓

### 1. SDK Build and Configuration
- ✅ **user.cmake** created and configured
- ✅ **CMake build** completed successfully using MinGW Makefiles
- ✅ **Python bindings** compiled: `eego_sdk.pyd`
- ✅ **Required DLLs** copied to toolbox folder

### 2. Toolbox Folder Setup
**Location:** `M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox`

**Contents:**
- `eego_sdk.pyd` - Python module (664 KB)
- `eego-SDK.dll` - ANT Neuro SDK library (683 KB)
- `eego-SDK.lib` - Import library (9 KB)
- `libgcc_s_seh-1.dll` - GCC runtime
- `libstdc++-6.dll` - C++ standard library
- `libwinpthread-1.dll` - pthread library
- `stream.py` - Example/test script from SDK

AFTER CONNECTING AMPLIFIER RUN THIS IN THE POWERSHELL AS ADMINISTRATOR: 'pnputil /add-driver "M:\CODEBASE\antneuroSDK\eego-sdk-pybind11-master\BUILD311\_deps\eego_sdk-src\windows\driver\win8\x64\cyusb3.inf" /install'

### 3. Environment Variables Configured ✓

#### PYTHONPATH
```
M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox
```

#### PATH (Added)
```
C:\msys64\ucrt64\bin
M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox
```

**How to Verify Environment Variables:**
1. Press `Windows + R`
2. Type `sysdm.cpl` and press Enter
3. Click "Advanced" tab → "Environment Variables"
4. Check **User variables**:
   - `PYTHONPATH` = `M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox`
   - `Path` should include both:
     - `C:\msys64\ucrt64\bin`
     - `M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox`

### 4. Python Version Requirement
**⚠ IMPORTANT:** The SDK was compiled for **Python 3.13.5**

- Use: `C:\Python313\python.exe`
- Do NOT use: MSYS2 Python (3.12) - will cause import errors

---

## Integration Architecture

### Current Implementation (BrainLink SDK)
The existing BrainLinkCompanion supports a single-channel BrainLink headset:
- File: `BrainLinkAnalyzer_GUI_Sequential_Integrated.py`
- Protocol: Bluetooth connection via `machinaris.py`
- Data: Single EEG channel
- Executable: BrainLinkAnalyzer (PyInstaller)

### New Implementation (ANT Neuro eego 64-Channel)

#### Design Approach: Separate Executable
**Rationale:**
1. Different hardware requirements (USB/network vs Bluetooth)
2. Different channel counts (64 vs 1)
3. Different sampling rates
4. Independent device management
5. Keeps original BrainLink implementation intact

#### Proposed Structure
```
BrainLinkCompanion/
├── BrainLinkAnalyzer_GUI_Sequential_Integrated.py  # Existing (1-channel)
├── AntNeuroAnalyzer_GUI.py                          # New (64-channel)
├── eego_sdk_toolbox/                                # ANT Neuro SDK files
├── shared_analysis/                                 # Shared analysis modules
│   ├── eeg_processing.py                           # Common processing
│   ├── feature_extraction.py                       # Shared features
│   └── visualization.py                            # Plotting functions
└── build_scripts/
    ├── build_brainlink.ps1                         # Build BrainLink EXE
    └── build_antneuro.ps1                          # Build ANT Neuro EXE
```

---

## Next Steps for Integration

### Phase 1: Create ANT Neuro Data Acquisition Module
Create: `antneuro_data_acquisition.py`

**Key Functions:**
```python
class AntNeuroDevice:
    def __init__(self):
        """Initialize connection to ANT Neuro amplifier"""
        
    def discover_amplifiers(self):
        """Find connected eego devices"""
        
    def connect(self, amplifier_serial):
        """Connect to specific amplifier"""
        
    def start_streaming(self, sample_rate=500):
        """Start EEG data stream"""
        
    def get_channels(self):
        """Get 64 channel configuration"""
        
    def read_samples(self, num_samples):
        """Read EEG samples from all channels"""
        
    def stop_streaming(self):
        """Stop and cleanup"""
```

### Phase 2: Create ANT Neuro GUI Application
Create: `AntNeuroAnalyzer_GUI.py`

**Features to Implement:**
1. Device discovery and connection UI
2. 64-channel data visualization (grid layout)
3. Real-time streaming display
4. Recording to file (multi-channel format)
5. Feature extraction adapted for 64 channels
6. Analysis protocols (eyes open/closed, etc.)

### Phase 3: Shared Analysis Pipeline
Extract common functionality:
- FFT analysis
- Band power calculations (Delta, Theta, Alpha, Beta, Gamma)
- Statistical measures
- Export formats

### Phase 4: Build System
Create PyInstaller specs for:
1. `AntNeuroAnalyzer.spec` - 64-channel application
2. Include eego_sdk.pyd and DLLs in bundle
3. Separate executable from BrainLink version

---

## Testing Strategy (Without Hardware)

### Current Status
✅ SDK imports successfully
✅ Factory initialization works
⚠ No amplifiers detected (expected without hardware)

### When Hardware Arrives
1. Run `test_antneuro_eego.py` to verify device detection
2. Test basic streaming with `stream.py`
3. Verify all 64 channels are accessible
4. Test sample rates (500 Hz, 1000 Hz, etc.)
5. Validate data quality

---

## Key SDK Components

### eego_sdk Module Classes

#### factory
- `getAmplifiers()` - Returns list of connected amplifiers
- Creates amplifier instances

#### amplifier
- `getSerial()` - Device serial number
- `getType()` - Amplifier model
- `getChannelCount()` - Number of channels (64)
- `OpenStream(sample_rate)` - Start data stream

#### stream
- `getData()` - Get EEG samples
- `getChannelList()` - Channel configuration
- Methods for data retrieval

#### channel
- Channel metadata
- Type (EEG, Reference, Ground, etc.)
- Units and scaling

#### buffer
- Data buffering
- Sample management

---

## Development Checklist

### Setup (Completed ✓)
- [x] Build eego SDK Python bindings
- [x] Create toolbox folder
- [x] Configure environment variables
- [x] Test SDK import
- [x] Create test script

### Integration (Pending Device)
- [ ] Create `antneuro_data_acquisition.py`
- [ ] Test with real hardware
- [ ] Create `AntNeuroAnalyzer_GUI.py`
- [ ] Implement 64-channel visualization
- [ ] Extract shared analysis modules
- [ ] Create PyInstaller build script
- [ ] Test final executable

### Documentation
- [ ] User manual for ANT Neuro version
- [ ] Installation guide
- [ ] Troubleshooting guide

---

## Important Notes

1. **Python Version**: Always use Python 3.13 (`C:\Python313\python.exe`)
2. **Keep Separate**: ANT Neuro implementation separate from BrainLink
3. **SDK Path**: eego_sdk must be imported from toolbox folder
4. **DLL Dependencies**: All DLLs must be in same folder as .pyd file
5. **Device Connection**: Will be USB or network-based (not Bluetooth)

---

## File Locations Reference

| Item | Path |
|------|------|
| SDK Source | `M:\CODEBASE\antneuroSDK\eego-sdk-pybind11-master` |
| SDK Zip | `M:\CODEBASE\antneuroSDK\eego_sdk.zip` |
| Toolbox | `M:\CODEBASE\BrainLinkCompanion\eego_sdk_toolbox` |
| Test Script | `M:\CODEBASE\BrainLinkCompanion\test_antneuro_eego.py` |
| This Plan | `M:\CODEBASE\BrainLinkCompanion\ANT_Neuro_Integration_Plan.md` |
| Build Folder | `M:\CODEBASE\antneuroSDK\eego-sdk-pybind11-master\BUILD` |

---

## Contact & Support

- ANT Neuro Documentation: Check SDK folder for PDFs
- SDK GitHub: (Check LINK.txt in antneuroSDK folder)
- Example Code: `stream.py` in toolbox folder
