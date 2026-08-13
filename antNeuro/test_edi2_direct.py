#!/usr/bin/env python3
"""
Test ANT Neuro EDI2 using pythonnet (direct DLL access).
Alternative to gRPC if .NET 8 runtime is not available.
"""
import sys
import os

print("Installing pythonnet if needed...")
try:
    import clr
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pythonnet", "--quiet"])
    import clr

# Add EDI DLL paths
edi_interface_path = r"M:\CODEBASE\BrainLinkCompanion\antNeuro\edi_dlls\lib\netstandard2.0"
edi_impl_path = r"M:\CODEBASE\BrainLinkCompanion\antNeuro\edi_dlls_impl\lib\netstandard2.0"

sys.path.append(edi_interface_path)
sys.path.append(edi_impl_path)

print("="*70)
print("EDI2 Direct DLL Test (pythonnet)")
print("="*70)

try:
    # Load EDI DLLs
    print("\nLoading EDI DLLs...")
    clr.AddReference("System")
    clr.AddReference(os.path.join(edi_interface_path, "ES.EdiInterface"))
    clr.AddReference(os.path.join(edi_impl_path, "ES.EdiImpl"))
    clr.AddReference(os.path.join(edi_impl_path, "Edi.Windows"))
    
    print("DLLs loaded successfully!")
    
    # Import EDI types
    from ES.EdiInterface import IEdiController, IDeviceManager, IAmplifier
    from ES.EdiImpl import EdiController
    
    print("\n--- Creating EDI Controller ---")
    controller = EdiController()
    print(f"Controller created: {controller}")
    
    print("\n--- Getting Device Manager ---")
    device_manager = controller.GetDeviceManager()
    print(f"Device Manager: {device_manager}")
    
    print("\n--- Getting Devices ---")
    devices = device_manager.GetDevices()
    print(f"Found {len(devices)} device(s)")
    
    if not devices:
        print("\nNo devices found!")
        print("Make sure your EE225 is connected via USB.")
        sys.exit(1)
    
    for dev in devices:
        print(f"  Device: {dev.Serial}")
    
    print("\n--- Creating Amplifier ---")
    amplifier = controller.CreateDevice([devices[0]])
    print(f"Amplifier created: {amplifier}")
    
    print("\n--- Getting Amplifier Info ---")
    info = amplifier.GetDeviceInformation()
    for i in info:
        print(f"  Serial: {i.Serial}")
    
    print("\n--- Getting Channels ---")
    channels = amplifier.GetChannelsAvailable()
    print(f"Available channels: {len(channels)}")
    for i, ch in enumerate(channels[:10]):
        print(f"  Ch{i}: {ch.Name}")
    
    print("\n--- Getting Sampling Rates ---")
    rates = amplifier.GetSamplingRatesAvailable()
    print(f"Available rates: {list(rates)}")
    
    print("\n--- Getting Power State ---")
    power = amplifier.GetPower()
    for pwr in power:
        print(f"  Battery Level: {pwr.BatteryLevel}%")
        print(f"  Is Charging: {pwr.isBatteryCharging}")
        print(f"  Is Power On: {pwr.isPowerOn}")
    
    print("\n" + "="*70)
    print("SUCCESS! EDI2 DLLs work via pythonnet!")
    print("="*70)
    print("""
Next step: Implement streaming by:
1. Setting mode to EEG
2. Reading frames in a loop
3. Processing the data

The EDI2 API does NOT have the power state blocking issue!
    """)
    
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
    print("\n" + "="*70)
    print("pythonnet approach failed.")
    print("Please install .NET 8 runtime and use the gRPC method instead.")
    print("See EDI2_SETUP_GUIDE.md for instructions.")
    print("="*70)
