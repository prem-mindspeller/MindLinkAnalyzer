# EDI2 Setup Guide - Solution to Power State Issue

## The Solution
ANT Neuro support provided **EDI2** (eemagine Device Interface v2.0.2.1355) - a modern API that **does NOT have the power state blocking issue** of the old eego SDK.

## Option 1: Using EDI gRPC Server (Recommended)

This is the official approach and works reliably.

### Step 1: Install .NET 8.0 Runtime
1. Download from: https://dotnet.microsoft.com/download/dotnet/8.0
2. Install: **"Download .NET Runtime 8.0" (Windows x64)**
3. You need both:
   - .NET Runtime 8.0
   - .NET Desktop Runtime 8.0

Or run this PowerShell command (as Administrator):
```powershell
winget install Microsoft.DotNet.Runtime.8
winget install Microsoft.DotNet.DesktopRuntime.8
```

### Step 2: Test EDI gRPC Server
```powershell
cd "M:\CODEBASE\EDI_Distributables\EDI_Distributables\DDE-OP-3754ver2.0.2.1355 EdigRPCApp-net8.0-windows10.0.19041.0"
.\EdigRPCApp.exe
```

The server should start and print something like:
```
EDI gRPC Server running on port 50051
```

### Step 3: Run Python Test
```powershell
cd M:\CODEBASE\BrainLinkCompanion\antNeuro
C:\Python313\python.exe test_edi2_grpc.py
```

This should:
- Detect your EE225 amplifier
- Get all channel information
- Start EEG streaming
- Get data frames
- **No power state issues!**

## Option 2: Using pythonnet (Direct DLL Access)

If you can't install .NET 8, you can try using pythonnet to call the EDI DLLs directly.

### Install pythonnet
```powershell
C:\Python313\python.exe -m pip install pythonnet
```

### Test Script
Run: `C:\Python313\python.exe test_edi2_direct.py`

## Why EDI2 Fixes the Power Issue

The old eego SDK (v1.3.29) has a hard-coded power state check:
- Checks `is_powered` flag
- If `is_powered == 0`, blocks all streaming
- This flag depends on specific USB power delivery behavior

EDI2 uses a different approach:
- Modern device management
- Mode-based operation (Idle → EEG → streaming)
- **No power state blocking** - just checks if device is present
- Better USB compatibility

## Files Created
- `antNeuro/test_edi2_grpc.py` - gRPC client test
- `antNeuro/EdigRPC_pb2.py` - Generated gRPC protobuf code
- `antNeuro/EdigRPC_pb2_grpc.py` - Generated gRPC client stubs
- `antNeuro/edi_dlls/` - Extracted EDI interface DLLs
- `antNeuro/edi_dlls_impl/` - Extracted EDI implementation DLLs

## Next Steps After Testing

Once you confirm EDI2 works:
1. Create a Python wrapper class for EDI gRPC client
2. Update your GUI to use EDI2 instead of eego SDK
3. Enjoy streaming without power state issues!

## References
- EDI Documentation: `M:\CODEBASE\EDI_Distributables\EDI_Distributables\UDO-SM-1206rev2.0 EDI 2.0.2.1355  API Documentation`
- Example App: `M:\CODEBASE\EDI_Distributables\EDI_Distributables\DDE-OP-0591ver2.0.2.1355 EDI Example Application Source`
