"""
ANT Neuro eego 64-Channel EEG Data Acquisition Module
------------------------------------------------------
This module handles connection and data streaming from ANT Neuro eego amplifiers.

Compatible with: eego-SDK (64-channel amplifiers)
Python Version: 3.13+
"""

import sys
import time
import numpy as np
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

# Add SDK path
sys.path.insert(0, 'M:/CODEBASE/BrainLinkCompanion/eego_sdk_toolbox')

try:
    import eego_sdk
    SDK_AVAILABLE = True
except ImportError as e:
    SDK_AVAILABLE = False
    print(f"Warning: eego_sdk not available: {e}")


@dataclass
class ChannelInfo:
    """Information about a single EEG channel"""
    index: int
    label: str
    type: str  # 'EEG', 'Reference', 'Ground', etc.
    unit: str
    sampling_rate: float


@dataclass
class AmplifierInfo:
    """Information about a connected amplifier"""
    serial: str
    type: str
    channel_count: int
    firmware_version: Optional[str] = None


class AntNeuroDevice:
    """
    Interface for ANT Neuro eego 64-channel EEG amplifier
    
    Usage:
        device = AntNeuroDevice()
        amplifiers = device.discover_amplifiers()
        device.connect(amplifiers[0].serial)
        device.start_streaming(sample_rate=500)
        
        while streaming:
            data = device.read_samples(250)  # Read 0.5 seconds at 500Hz
            # Process data...
            
        device.stop_streaming()
    """
    
    def __init__(self):
        """Initialize the ANT Neuro device interface"""
        if not SDK_AVAILABLE:
            raise RuntimeError("eego_sdk not available. Check installation.")
        
        self.factory = None
        self.amplifier = None
        self.amplifier_objects = []  # Cache of discovered amplifier objects
        self.stream = None
        self.channels: List[ChannelInfo] = []
        self.sampling_rate = 0
        self.is_streaming = False
        
        # Initialize factory
        try:
            self.factory = eego_sdk.factory()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize eego_sdk factory: {e}")
    
    def discover_amplifiers(self) -> List[AmplifierInfo]:
        """
        Discover all connected ANT Neuro amplifiers
        
        Returns:
            List of AmplifierInfo objects for each discovered amplifier
            
        Raises:
            RuntimeError: If discovery fails
        """
        if not self.factory:
            raise RuntimeError("Factory not initialized")
        
        try:
            amplifiers = self.factory.getAmplifiers()
            
            # Convert to list first to avoid iterator issues
            amp_list = list(amplifiers)
            print(f"getAmplifiers returned {len(amp_list)} items")
            
            # Store the amplifier objects and build info list
            self.amplifier_objects = []
            amp_info_list = []
            
            for amp in amp_list:
                # Store the amplifier object
                self.amplifier_objects.append(amp)
                
                # Get channel count from channel list
                channels = amp.getChannelList()
                
                info = AmplifierInfo(
                    serial=amp.getSerialNumber(),
                    type=amp.getType(),
                    channel_count=len(channels),
                    firmware_version=amp.getFirmwareVersion()
                )
                amp_info_list.append(info)
            
            print(f"Discovered {len(amp_info_list)} amplifier(s)")
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
            amplifiers = self.discover_amplifiers()
            
            if not amplifiers:
                raise RuntimeError("No amplifiers found. Check device connection.")
            
            print(f"Found {len(amplifiers)} amplifier(s), {len(self.amplifier_objects)} objects cached")
            
            # Select amplifier
            if amplifier_serial:
                selected_idx = next((i for i, a in enumerate(amplifiers) if a.serial == amplifier_serial), None)
                if selected_idx is None:
                    raise RuntimeError(f"Amplifier with serial {amplifier_serial} not found")
                selected = amplifiers[selected_idx]
            else:
                selected_idx = 0
                selected = amplifiers[0]
            
            # Use the cached amplifier object
            if selected_idx >= len(self.amplifier_objects):
                raise RuntimeError(f"Amplifier object cache mismatch")
            
            self.amplifier = self.amplifier_objects[selected_idx]
            
            print(f"Connected to amplifier: {selected.serial}")
            print(f"  Type: {selected.type}")
            print(f"  Channels: {selected.channel_count}")
            
            return selected
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Failed to connect: {e}")
    
    def start_streaming(self, sample_rate: int = 500) -> None:
        """
        Start EEG data streaming
        
        Args:
            sample_rate: Sampling rate in Hz (e.g., 500, 1000, 2000)
            
        Raises:
            RuntimeError: If streaming cannot be started
        """
        if not self.amplifier:
            raise RuntimeError("No amplifier connected. Call connect() first.")
        
        if self.is_streaming:
            raise RuntimeError("Already streaming. Stop current stream first.")
        
        try:
            # Ensure any previous stream is closed
            if self.stream is not None:
                try:
                    self.stream = None
                    print("Closed previous stream")
                except:
                    pass
            
            # Check and wait for power state to be ready
            import time
            try:
                max_retries = 20
                for i in range(max_retries):
                    power_state = self.amplifier.getPowerState()
                    print(f"Power state check {i+1}/{max_retries}: {power_state}")
                    if power_state:  # True means powered on
                        print(f"✓ Amplifier powered on")
                        # Wait additional time for amplifier to stabilize
                        print("Waiting 2 seconds for amplifier to stabilize...")
                        time.sleep(2.0)
                        break
                    print(f"  Waiting for amplifier to power on...")
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Amplifier did not power on within timeout period")
                    
            except Exception as e:
                print(f"Power state check error: {e}")
                raise RuntimeError(f"Cannot verify amplifier power state: {e}")
            
            # Get available sampling rates
            available_rates = self.amplifier.getSamplingRatesAvailable()
            print(f"Available sampling rates: {available_rates}")
            if sample_rate not in available_rates:
                print(f"Warning: {sample_rate} Hz not available. Using {available_rates[0]} Hz")
                sample_rate = available_rates[0]
            
            # Get available voltage ranges
            ref_ranges = self.amplifier.getReferenceRangesAvailable()
            bipolar_ranges = self.amplifier.getBipolarRangesAvailable()
            
            print(f"Available reference ranges: {ref_ranges}")
            print(f"Available bipolar ranges: {bipolar_ranges}")
            
            # Use first available range (typically the default)
            ref_range = ref_ranges[0] if ref_ranges else 1.0
            bipolar_range = bipolar_ranges[0] if bipolar_ranges else 1.0
            
            print(f"Attempting to open stream...")
            print(f"  Sample rate: {sample_rate} Hz")
            print(f"  Reference range: {ref_range}")
            print(f"  Bipolar range: {bipolar_range}")
            
            # Open EEG stream with all required parameters
            # OpenEegStream(sample_rate, reference_range, bipolar_range)
            self.stream = self.amplifier.OpenEegStream(sample_rate, ref_range, bipolar_range)
            self.sampling_rate = sample_rate
            print("✓ Stream opened successfully!")
            
            # Get channel information from stream
            channel_list = self.stream.getChannelList()
            self.channels = []
            
            for idx, ch in enumerate(channel_list):
                ch_info = ChannelInfo(
                    index=idx,
                    label=f"Ch{idx+1}",  # Default label
                    type='EEG',
                    unit='μV',  # Standard unit for EEG
                    sampling_rate=sample_rate
                )
                self.channels.append(ch_info)
            
            self.is_streaming = True
            print(f"Streaming started at {sample_rate} Hz")
            print(f"Channels available: {len(self.channels)}")
            
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
            Returns None if no data available
            
        Raises:
            RuntimeError: If not streaming
        """
        if not self.is_streaming:
            raise RuntimeError("Not streaming. Call start_streaming() first.")
        
        try:
            # Get data from stream - returns a buffer object
            buffer = self.stream.getData()
            
            if buffer is None:
                return None
            
            # Get the data as a flat list/array
            # The SDK returns data in channel-major format:
            # [ch0_sample0, ch0_sample1, ..., ch1_sample0, ch1_sample1, ...]
            num_channels = len(self.channels)
            
            # Try to get the size and samples
            try:
                size = buffer.size()
                if size == 0:
                    return None
                
                # Extract samples from buffer
                # buffer.getSample(channel_idx) returns all samples for that channel
                channel_data = []
                for ch_idx in range(num_channels):
                    ch_samples = buffer.getSample(ch_idx)
                    # Convert to list if it's not already
                    if hasattr(ch_samples, '__iter__'):
                        channel_data.append(list(ch_samples))
                    else:
                        channel_data.append([ch_samples])
                
                # Transpose to get (samples, channels) format
                max_samples = max(len(ch) for ch in channel_data)
                data_array = np.zeros((max_samples, num_channels))
                
                for ch_idx, ch_samples in enumerate(channel_data):
                    data_array[:len(ch_samples), ch_idx] = ch_samples
                
                # Return requested number of samples
                if data_array.shape[0] >= num_samples:
                    return data_array[:num_samples, :]
                else:
                    return data_array
                    
            except AttributeError:
                # Alternative: buffer might be a simple array
                # Try to reshape directly
                data_flat = np.array(buffer)
                if len(data_flat) == 0:
                    return None
                
                # Assume channel-major format
                samples_per_channel = len(data_flat) // num_channels
                data_array = data_flat.reshape(num_channels, samples_per_channel).T
                
                if data_array.shape[0] >= num_samples:
                    return data_array[:num_samples, :]
                else:
                    return data_array
            
        except Exception as e:
            print(f"Error reading samples: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
    
    def stop_streaming(self) -> None:
        """Stop EEG data streaming and cleanup"""
        if self.is_streaming:
            try:
                if self.stream:
                    # Close stream
                    self.stream = None
                self.is_streaming = False
                print("Streaming stopped")
            except Exception as e:
                print(f"Error stopping stream: {e}")
        
        self.sampling_rate = 0
        self.channels = []
    
    def disconnect(self) -> None:
        """Disconnect from amplifier"""
        self.stop_streaming()
        self.amplifier = None
        print("Disconnected from amplifier")
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.disconnect()
        except:
            pass


# Test function
def test_device():
    """Test the ANT Neuro device connection"""
    print("="*60)
    print("ANT NEURO DEVICE TEST")
    print("="*60)
    
    try:
        device = AntNeuroDevice()
        print("✓ Device interface initialized")
        
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
        
        # Start streaming
        print("\nStarting data stream at 500 Hz...")
        device.start_streaming(sample_rate=500)
        print("✓ Streaming started")
        
        # Read some samples
        print("\nReading test samples...")
        for i in range(3):
            time.sleep(0.5)  # Wait 0.5 seconds
            data = device.read_samples(250)  # Read 250 samples (0.5 sec at 500Hz)
            
            if data is not None:
                print(f"  Read {data.shape[0]} samples x {data.shape[1]} channels")
                print(f"    Data range: {data.min():.2f} to {data.max():.2f} μV")
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
        print("TEST COMPLETE - Device is working correctly!")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_device()
