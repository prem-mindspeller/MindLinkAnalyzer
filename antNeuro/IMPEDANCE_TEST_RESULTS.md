# EDI2 Impedance Measurement Test Results

**Date:** February 6, 2026  
**Device:** EE225-300300-300033  
**SDK Version:** 2.0.2.1355

## Test Summary

Testing impedance measurement via EDI2 gRPC interface following the exact workflow from the official C# example application.

## Results

### ✅ What Works
- Device detection and connection
- Available modes query - **Impedance mode (3) IS supported**
- Setting IDLE mode successfully
- Setting IMPEDANCE mode successfully

### ❌ What Fails
- **Impedance mode causes connection abort**
- After setting impedance mode, gRPC connection is terminated
- Error: `Connection aborted (An established connection was aborted by the software in your host machine)`
- Amplifier handle becomes invalid: `not found: amplifier with id 0`

## Test Output

```
[3] Checking available modes...
    Available modes:
      - Idle (5)
      - Eeg (2)
      - Impedance (3)        ← Mode IS supported

[8] Setting IMPEDANCE mode...
    IMPEDANCE mode set        ← Mode set successfully

[10] Getting impedance frames...
    Attempt 1...
    gRPC Error: StatusCode.UNAVAILABLE: IOCP/Socket: Connection aborted
                                        ↑
                                    Connection lost!
```

## Root Cause Analysis

The impedance mode is **supported by the device** but causes the **gRPC connection to abort**. Possible causes:

1. **gRPC/COM Interaction Issue**: Impedance mode may trigger low-level hardware operations that interfere with the gRPC server's connection handling
2. **Device Firmware Behavior**: The EE225 device may reset its USB connection when entering impedance mode
3. **SDK Bug**: The gRPC wrapper may not properly handle impedance mode state transitions
4. **Power State Issue**: Similar to the old eego SDK blocking issues, impedance mode may trigger USB reenumeration

## Comparison with C# Example

The C# example application (`RecordingService.cs`) shows impedance measurement working in the **native .NET SDK**, but our tests show it **fails via gRPC**. This suggests:

- Impedance works in **direct SDK** (C# native library)
- Impedance **does NOT work via gRPC wrapper** (Python/remote access)

## Recommended Solution

**Use variance-based signal quality estimation** as primary method:

```python
# Already implemented in BrainLinkAnalyzer_GUI_Sequential_Integrated.py
variance = np.var(channel_data)
if variance < 0.5:
    quality = "Poor (low variance)"
elif variance > 100:
    quality = "Poor (excessive noise)"
else:
    quality = "Good"
```

**Advantages:**
- No mode switching required
- No connection disruption
- Real-time calculation during streaming
- Works with any device/SDK

**Disadvantages:**
- Not true impedance (kΩ) values
- Approximate quality only
- Cannot detect specific hardware issues (broken electrode, dry contact, etc.)

## Alternative Approaches

1. **Use native C# SDK directly** - Would require C#/CLR bridge
2. **Pre-measurement impedance check** - Check before main streaming, accept connection reset
3. **Separate impedance tool** - External utility using native SDK
4. **Contact manufacturer** - Report gRPC/impedance incompatibility

## Conclusion

**Impedance measurement via EDI2 gRPC is NOT reliable** for the EE225 device. The variance-based quality estimation already implemented is the recommended approach for real-time signal quality monitoring.

## Test Files

- `test_edi2_impedance_proper.py` - Proper workflow test (this result)
- `test_edi2_impedance_debug.py` - Detailed debugging test
- `test_edi2_impedance.py` - Initial impedance test
