#!/usr/bin/env python3
"""
ANT Neuro EDI2 64-Channel EEG Data Acquisition Module
------------------------------------------------------
This module provides the same interface as antneuro_data_acquisition.py but uses
the EDI2 gRPC API instead of the old eego SDK.

Key differences from eego SDK:
- No power state blocking issues
- Works with modern USB controllers
- Uses gRPC client-server architecture

Compatible with: EDI2 v2.0.2 (EdigRPCApp)
Python Version: 3.13+
"""

import sys
import time
import numpy as np
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
from collections import deque
import threading

# Import EDI2 client
try:
    from edi2_client import EDI2Client, DeviceInfo, ChannelInfo as EDI2ChannelInfo
    EDI2_AVAILABLE = True
except ImportError as e:
    EDI2_AVAILABLE = False
    print(f"Warning: EDI2 client not available: {e}")


@dataclass
class ChannelInfo:
    """Information about a single EEG channel (compatible with old interface)"""
    index: int
    label: str
    type: str  # 'EEG', 'Reference', 'Bipolar', etc.
    unit: str
    sampling_rate: float


@dataclass
class AmplifierInfo:
    """Information about a connected amplifier (compatible with old interface)"""
    serial: str
    type: str
    channel_count: int
    firmware_version: Optional[str] = None


class AntNeuroEDI2Device:
    """
    Interface for ANT Neuro EEG amplifiers using EDI2 gRPC API
    
    This class provides the same interface as the old AntNeuroDevice class
    but uses the EDI2 API which doesn't have power state blocking issues.
    
    Usage:
        device = AntNeuroEDI2Device()
        amplifiers = device.discover_amplifiers()
        device.connect(amplifiers[0].serial)
        device.start_streaming(sample_rate=512)
        
        while streaming:
            data = device.read_samples(256)  # Read 0.5 seconds at 512Hz
            # Process data...
            
        device.stop_streaming()
    """
    
    def __init__(self, grpc_server_path: str = None):
        """
        Initialize the ANT Neuro EDI2 device interface
        
        Args:
            grpc_server_path: Optional custom path to EdigRPCApp.exe
        """
        if not EDI2_AVAILABLE:
            raise RuntimeError("EDI2 client not available. Check edi2_client.py import.")
        
        self.client = EDI2Client(grpc_server_path=grpc_server_path)
        
        # Interface compatibility
        self.channels: List[ChannelInfo] = []
        self.sampling_rate: int = 0
        self.is_streaming: bool = False
        
        # Internal buffer for read_samples compatibility
        self._internal_buffer = deque(maxlen=65536)
        self._buffer_lock = threading.Lock()
    
    def discover_amplifiers(self) -> List[AmplifierInfo]:
        """
        Discover all connected ANT Neuro amplifiers
        
        Returns:
            List of AmplifierInfo objects for each discovered amplifier
            
        Raises:
            RuntimeError: If discovery fails
        """
        try:
            devices = self.client.discover_devices()
            
            amp_info_list = []
            for dev in devices:
                # Parse serial for type info
                serial = dev['serial']
                dev_type = 'EEgo'
                if 'EE225' in serial:
                    dev_type = 'EE225'
                elif 'EE411' in serial:
                    dev_type = 'EE411'
                
                info = AmplifierInfo(
                    serial=serial,
                    type=dev_type,
                    channel_count=88,  # Will be updated on connect
                    firmware_version=''
                )
                amp_info_list.append(info)
            
            print(f"[EDI2] Discovered {len(amp_info_list)} amplifier(s)")
            return amp_info_list
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Failed to discover amplifiers: {e}")
    
    def connect(self, amplifier_serial: Optional[str] = None) -> AmplifierInfo:
        """
        Connect to a specific amplifier (or the first one found)
        
        Args:
            amplifier_serial: Serial number of amplifier. If None, connects to first available.
            
        Returns:
            AmplifierInfo object for the connected amplifier
            
        Raises:
            RuntimeError: If connection fails
        """
        try:
            if not self.client.connect(amplifier_serial):
                raise RuntimeError(f"Failed to connect to amplifier: {amplifier_serial}")
            
            # Update channel info
            self.channels = []
            for ch in self.client.channels:
                ch_type = 'Reference' if ch.channel_type == 0 else 'Bipolar'
                self.channels.append(ChannelInfo(
                    index=ch.index,
                    label=ch.name if ch.name else f"Ch{ch.index+1}",
                    type=ch_type,
                    unit='μV',
                    sampling_rate=512  # Will be updated when streaming starts
                ))
            
            # Get device info
            info = AmplifierInfo(
                serial=self.client.device_info.serial,
                type='EEgo',
                channel_count=self.client.device_info.channel_count,
                firmware_version=self.client.device_info.firmware_version
            )
            
            print(f"[EDI2] Connected to amplifier: {info.serial}")
            print(f"[EDI2]   Type: {info.type}")
            print(f"[EDI2]   Channels: {info.channel_count}")
            
            return info
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Failed to connect: {e}")
    
    def _on_data_received(self, data: np.ndarray):
        """Internal callback to buffer incoming data"""
        with self._buffer_lock:
            for sample in data:
                self._internal_buffer.append(sample)
    
    def start_streaming(self, sample_rate: int = 512) -> None:
        """
        Start EEG data streaming
        
        Args:
            sample_rate: Sampling rate in Hz (default 512, supports up to 32768)
            
        Raises:
            RuntimeError: If streaming cannot be started
        """
        if not self.client.is_connected:
            raise RuntimeError("No amplifier connected. Call connect() first.")
        
        if self.is_streaming:
            raise RuntimeError("Already streaming. Stop current stream first.")
        
        try:
            # Clear internal buffer
            with self._buffer_lock:
                self._internal_buffer.clear()
            
            # Set data callback
            self.client.set_data_callback(self._on_data_received)
            
            # Get power state (for info - EDI2 doesn't block on power)
            power = self.client.get_power_state()
            print(f"[EDI2] Power state: Battery={power.get('battery_level', 'N/A')}%, "
                  f"Charging={power.get('is_charging', 'N/A')}, "
                  f"PowerOn={power.get('is_power_on', 'N/A')}")
            
            # Start streaming
            if not self.client.start_streaming(sample_rate=float(sample_rate)):
                raise RuntimeError("Failed to start streaming")
            
            self.sampling_rate = sample_rate
            self.is_streaming = True
            
            # Update channel sampling rates
            for ch in self.channels:
                ch.sampling_rate = sample_rate
            
            print(f"[EDI2] Streaming started at {sample_rate} Hz")
            print(f"[EDI2] Channels available: {len(self.channels)}")
            
        except Exception as e:
            raise RuntimeError(f"Failed to start streaming: {e}")
    
    def read_samples(self, num_samples: int) -> Optional[np.ndarray]:
        """
        Read EEG samples from the stream
        
        Args:
            num_samples: Number of samples to read per channel
            
        Returns:
            numpy array of shape (num_samples, num_channels)
            Each row is a time point, each column is a channel
            Returns None if insufficient data available
            
        Raises:
            RuntimeError: If not streaming
        """
        if not self.is_streaming:
            raise RuntimeError("Not streaming. Call start_streaming() first.")
        
        # Wait for enough data with timeout
        timeout = 5.0  # seconds
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._buffer_lock:
                if len(self._internal_buffer) >= num_samples:
                    # Extract requested samples
                    data = np.array([self._internal_buffer.popleft() 
                                    for _ in range(num_samples)])
                    return data
            time.sleep(0.01)
        
        # Return whatever is available
        with self._buffer_lock:
            if self._internal_buffer:
                available = len(self._internal_buffer)
                data = np.array([self._internal_buffer.popleft() 
                                for _ in range(available)])
                return data
        
        return None
    
    def read_all_available(self) -> Optional[np.ndarray]:
        """
        Read all available samples from the buffer
        
        Returns:
            numpy array of shape (samples, channels) or None
        """
        with self._buffer_lock:
            if not self._internal_buffer:
                return None
            data = np.array(list(self._internal_buffer))
            self._internal_buffer.clear()
            return data
    
    def get_channel_info(self) -> List[ChannelInfo]:
        """
        Get information about all channels
        
        Returns:
            List of ChannelInfo objects
        """
        return self.channels
    
    def get_sampling_rate(self) -> int:
        """Get current sampling rate"""
        return self.sampling_rate
    
    def get_power_state(self) -> Dict:
        """Get device power state"""
        return self.client.get_power_state()
    
    def stop_streaming(self) -> None:
        """Stop EEG data streaming and cleanup"""
        if self.is_streaming:
            self.client.stop_streaming()
            self.is_streaming = False
            print("[EDI2] Streaming stopped")
        
        self.sampling_rate = 0
    
    def disconnect(self) -> None:
        """Disconnect from amplifier"""
        self.stop_streaming()
        self.client.disconnect()
        self.channels = []
        print("[EDI2] Disconnected from amplifier")
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.disconnect()
        except:
            pass


# =============================================================================
# Test function
# =============================================================================

def test_edi2_device():
    """Test the ANT Neuro EDI2 device connection"""
    print("="*60)
    print("ANT NEURO EDI2 DEVICE TEST")
    print("="*60)
    
    try:
        device = AntNeuroEDI2Device()
        print("✓ EDI2 device interface initialized")
        
        # Discover amplifiers
        print("\nDiscovering amplifiers...")
        amplifiers = device.discover_amplifiers()
        
        if not amplifiers:
            print("⚠ No amplifiers found (device not connected)")
            print("  Connect the ANT Neuro headset and try again.")
            return
        
        print(f"✓ Found {len(amplifiers)} amplifier(s)")
        for amp in amplifiers:
            print(f"  - {amp.serial}: {amp.type} ({amp.channel_count} channels)")
        
        # Connect to first amplifier
        print("\nConnecting to amplifier...")
        amp_info = device.connect()
        print("✓ Connected successfully")
        
        # Check power state
        print("\nChecking power state...")
        power = device.get_power_state()
        print(f"  Battery: {power.get('battery_level', 'N/A')}%")
        print(f"  Charging: {power.get('is_charging', 'N/A')}")
        print(f"  Power On: {power.get('is_power_on', 'N/A')}")
        
        # Start streaming
        print("\nStarting data stream at 512 Hz...")
        device.start_streaming(sample_rate=512)
        print("✓ Streaming started")
        
        # Read some samples
        print("\nReading test samples...")
        for i in range(3):
            time.sleep(0.5)  # Wait 0.5 seconds
            data = device.read_samples(256)  # Read 256 samples (0.5 sec at 512Hz)
            
            if data is not None:
                print(f"  Read {data.shape[0]} samples x {data.shape[1]} channels")
                print(f"    Data range: {data.min():.4f} to {data.max():.4f}")
                print(f"    Mean: {data.mean():.4f}, Std: {data.std():.4f}")
            else:
                print("  No data available yet")
        
        # Stop streaming
        print("\nStopping stream...")
        device.stop_streaming()
        print("✓ Stream stopped")
        
        # Disconnect
        device.disconnect()
        print("✓ Disconnected")
        
        print("\n" + "="*60)
        print("TEST COMPLETE - EDI2 Device is working correctly!")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_edi2_device()
