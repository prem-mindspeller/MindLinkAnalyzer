# EDI2 SDK Deep Dive - API Reference and Findings

## Overview

This document summarizes the investigation of the ANT Neuro EDI2 gRPC SDK v2.0.2.1355
for impedance measurement and EEG streaming capabilities.

## SDK Location

- **gRPC Server**: `M:\CODEBASE\EDI_Distributables\EDI_Distributables\DDE-OP-3754ver2.0.2.1355 EdigRPCApp-net8.0-windows10.0.19041.0\EdigRPCApp.exe`
- **Proto File**: `M:\CODEBASE\EDI_Distributables\EDI_Distributables\DDE-OP-3755ver2.0.2.1355 Edi-grpx-proto\EdigRPC.proto`
- **API Documentation**: `M:\CODEBASE\EDI_Distributables\EDI_Distributables\UDO-SM-1206rev2.0 EDI 2.0.2.1355  API Documentation`
- **Example Application**: `M:\CODEBASE\EDI_Distributables\EDI_Distributables\DDE-OP-0591ver2.0.2.1355 EDI Example Application Source`

## Key Data Structures

### AmplifierMode Enum
```protobuf
enum AmplifierMode {
    AmplifierMode_Disconnect = 0;
    AmplifierMode_PowerOff = 1;
    AmplifierMode_Eeg = 2;
    AmplifierMode_Impedance = 3;
    AmplifierMode_OpenLine = 4;
    AmplifierMode_Idle = 5;
}
```

### AmplifierFrameType Enum
```protobuf
enum AmplifierFrameType {
    AmplifierFrameType_EEG = 0;
    AmplifierFrameType_ImpedanceVoltages = 1;
    AmplifierFrameType_OpenLine = 2;
    AmplifierFrameType_Stimulation = 3;
}
```

### Impedances Message
```protobuf
message Impedances {
    repeated TupleImpledanceChannel Channels = 1;   // Regular EEG channels
    repeated TupleImpledanceChannel Reference = 2;  // Reference channel(s)
    repeated TupleImpledanceChannel Ground = 3;     // Ground
}

message TupleImpledanceChannel {
    uint32 Value = 1;                       // Impedance value in Ohms
    ChannelConnectionState ChannelState = 2; // Connected/Disconnected/Unknown
}
```

### AmplifierFrame Message
```protobuf
message AmplifierFrame {
    AmplifierFrameType FrameType = 1;       // Type of data in frame
    Impedances Impedance = 2;               // Impedance values (if applicable)
    DateTimeOffset Start = 3;               // Amplifier clock time
    DateTimeOffset StartPcTime = 4;         // PC clock time
    repeated TimeMarker TimeMarkers = 5;    // Event markers
    DoubleMatrix Values = 6;                // EEG data matrix (channels × samples)
    int64 BufferLoadCapacity = 7;           // Buffer fill percentage
}
```

### StreamParams Message
```protobuf
message StreamParams {
    repeated uint32 ActiveChannels = 1;     // List of active channel indices
    map<int32, double> Ranges = 2;          // ChannelPolarity -> range in Volts
    double SamplingRate = 3;                // Sample rate in Hz
    int32 BufferSize = 4;                   // Buffer size in samples
    int32 DataReadyPercentage = 5;          // When to notify data ready (%)
}
```

## Key gRPC Methods

### DeviceManager
- `DeviceManager_GetDevices()` - Get list of connected devices

### Controller
- `Controller_CreateDevice(DeviceInfoList)` - Create amplifier from device list
- `Controller_GetHandle()` - Get current amplifier handle

### Amplifier
- `Amplifier_SetMode(AmplifierHandle, Mode, StreamParams)` - Set operating mode
- `Amplifier_GetMode(AmplifierHandle)` - Get current mode
- `Amplifier_GetModesAvailable(AmplifierHandle)` - Get supported modes
- `Amplifier_GetFrame(AmplifierHandle)` - Get data frame(s)
- `Amplifier_GetChannelsAvailable(AmplifierHandle)` - Get channel list
- `Amplifier_GetDeviceInformation(AmplifierHandle)` - Get device info
- `Amplifier_GetRangesAvailable(AmplifierHandle)` - Get supported voltage ranges
- `Amplifier_GetSamplingRatesAvailable(AmplifierHandle)` - Get supported sample rates
- `Amplifier_GetPower(AmplifierHandle)` - Get power state

## Impedance Measurement Workflow (from C# Example)

The C# example application (`MainViewModel.cs`, `RecordingService.cs`, `HardwareService.cs`)
shows the correct workflow:

### 1. State Transition Sequence
```csharp
// Step 1: Set to IDLE first
await SetAmpParameters(AmplifierMode.Idle);

// Step 2: Stage impedance mode (set internal state)
_lastConnectedAmplifier.Mode = AmplifierMode.Impedance;

// Step 3: Actually set impedance mode with parameters
Amplifier.SetMode(AmplifierMode.Impedance, streamParams);

// Step 4: Loop reading frames
while (!token.IsCancellationRequested) {
    ReadOnlyCollection<AmplifierFrame> outData = HardwareService.OnReadData();
    if (outData != null) {
        FireNewDataEvent(outData);
    }
}
```

### 2. Frame Validation (from HardwareService.OnReadData)
```csharp
// Check for impedance data in frame
if (outDataList.First().FrameType == AmplifierFrameType.ImpedanceVoltages
    && outDataList.First().Impedance == null)
    // Empty impedance frame - return null and retry
    return null;
```

### 3. StreamParams Configuration
```csharp
StreamParams = new StreamParams() {
    ActiveChannels = ChannelDefinitions.GetChannelIndices(Amplifier.GetChannelsAvailable()),
    Ranges = new Dictionary<ChannelPolarity, double>() {
        { ChannelPolarity.Referential, 1.0 },  // 1.0V for EE_411
        { ChannelPolarity.Bipolar, 2.5 }       // Only for EE_511
    },
    SamplingRate = 512,
    DataReadyPercentage = 1,
    BufferSize = (int)(SamplingRate * 5)  // 5 seconds buffer
};
```

## Test Results Summary

### What Works:
- ✅ EEG streaming mode (Mode = 2) works correctly via gRPC
- ✅ GetFrame() returns valid EEG data with Values matrix
- ✅ Channel count, sample rate, and data format are correct

### What Doesn't Work:
- ❌ Impedance mode (Mode = 3) returns error: "Wrong Amplifier state: Index was outside the bounds of the array"
- ❌ GetFrame() in impedance mode returns empty FrameList or errors
- ❌ Setting impedance mode sometimes succeeds but GetFrame fails

### Possible Causes:
1. **Hardware Limitation**: The EE225 device may not support impedance measurement via the gRPC interface (only via direct USB?)
2. **Firmware Issue**: The SDK version or device firmware may have a bug
3. **Channel Configuration**: The StreamParams ActiveChannels list might need specific configuration for impedance mode
4. **Missing Calibration**: Impedance mode may require specific hardware calibration first

## Recommended Solution: Variance-Based Quality Estimation

Since SDK impedance measurement is unreliable via gRPC, use a variance-based approach:

```python
def estimate_signal_quality(data: np.ndarray, sample_rate: float = 512) -> Dict[str, float]:
    """
    Estimate signal quality from EEG data variance.
    
    Good electrode contact shows:
    - Low variance (stable signal)
    - Low DC offset
    - Normal amplitude range
    
    Poor contact shows:
    - High variance (noisy signal)
    - High DC offset (stuck electrode)
    - Flat line (disconnected)
    """
    quality = {}
    for ch_idx in range(data.shape[0]):
        ch_data = data[ch_idx]
        
        # Calculate metrics
        variance = np.var(ch_data)
        std = np.std(ch_data)
        dc_offset = abs(np.mean(ch_data))
        amplitude = np.max(ch_data) - np.min(ch_data)
        
        # Quality score based on variance (lower is better for EEG)
        # Typical good EEG variance: 100-1000 µV²
        # High variance (>10000): poor contact
        # Very low variance (<10): flat line/disconnected
        
        if variance < 10:
            quality[f"Ch{ch_idx+1}"] = 0.0  # Disconnected
        elif variance > 10000:
            quality[f"Ch{ch_idx+1}"] = 0.3  # Poor contact
        elif variance > 5000:
            quality[f"Ch{ch_idx+1}"] = 0.5  # Marginal
        elif variance > 1000:
            quality[f"Ch{ch_idx+1}"] = 0.7  # Acceptable
        else:
            quality[f"Ch{ch_idx+1}"] = 1.0  # Good
    
    return quality
```

## Files to Update

1. **edi2_client.py** - Keep impedance methods for future SDK fixes, but add variance-based fallback
2. **BrainLinkAnalyzer_GUI_Sequential_Integrated.py** - Use variance-based quality by default
3. **AntNeuroAnalyzer_GUI_Sequential_Integrated.py** - Same updates for ANT Neuro GUI

## Future Investigation

1. Contact ANT Neuro support about impedance mode via gRPC
2. Test with different EE225 firmware versions
3. Test with EE411/EE511 devices which may have better support
4. Monitor EDI2 SDK updates for bug fixes
