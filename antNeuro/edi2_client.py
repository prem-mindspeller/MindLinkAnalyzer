#!/usr/bin/env python3
"""
ANT Neuro EDI2 gRPC Client - Production Wrapper
================================================

This module provides a clean Python interface to the ANT Neuro EDI2 gRPC API.
It replaces the old eego SDK which had power state blocking issues.

Features:
- Automatic gRPC server lifecycle management
- Threaded data acquisition with buffering
- NumPy array output compatible with existing pipeline
- Graceful error handling and reconnection

Usage:
    from edi2_client import EDI2Client
    
    client = EDI2Client()
    devices = client.discover_devices()
    client.connect(devices[0]['serial'])
    client.start_streaming(sample_rate=512)
    
    while streaming:
        data = client.get_data()  # Returns (samples, channels) numpy array
        # Process data...
    
    client.stop_streaming()
    client.disconnect()

Author: BrainLink Companion Team
Date: February 2026
"""

import os
import sys
import time
import subprocess
import threading
import numpy as np
from typing import List, Dict, Optional, Any, Tuple
from collections import deque
from dataclasses import dataclass

# Add the antNeuro directory to path for gRPC imports
ANTNEURO_DIR = os.path.dirname(os.path.abspath(__file__))
if ANTNEURO_DIR not in sys.path:
    sys.path.insert(0, ANTNEURO_DIR)

try:
    import grpc
    import EdigRPC_pb2 as edi
    import EdigRPC_pb2_grpc as edi_grpc
    GRPC_AVAILABLE = True
except ImportError as e:
    GRPC_AVAILABLE = False
    print(f"Warning: gRPC modules not available: {e}")


@dataclass
class DeviceInfo:
    """Information about a connected ANT Neuro device"""
    serial: str
    device_type: int
    key: str
    channel_count: int = 88
    firmware_version: str = ""


@dataclass
class ChannelInfo:
    """Information about an EEG channel"""
    index: int
    name: str
    polarity: int
    channel_type: int  # 0 = reference, 1 = bipolar


class EDI2Client:
    """
    Python client for ANT Neuro EDI2 gRPC API
    
    This class manages the gRPC server lifecycle and provides a clean interface
    for streaming EEG data from ANT Neuro amplifiers.
    
    Key Features:
    - No power state blocking (unlike old eego SDK)
    - Works with modern USB controllers
    - 88-channel support (64 reference + 24 bipolar)
    - Sampling rates up to 32768 Hz
    """
    
    # Default gRPC server path
    DEFAULT_GRPC_SERVER = r"M:\CODEBASE\EDI_Distributables\EDI_Distributables\DDE-OP-3754ver2.0.2.1355 EdigRPCApp-net8.0-windows10.0.19041.0\EdigRPCApp.exe"
    DEFAULT_PORT = 3390
    
    # Valid voltage ranges per channel type
    REFERENCE_RANGES = [1.0, 0.75, 0.15]  # Volts
    BIPOLAR_RANGES = [4.0, 1.5, 0.7, 0.35]  # Volts
    
    def __init__(self, grpc_server_path: str = None, port: int = None):
        """
        Initialize the EDI2 client
        
        Args:
            grpc_server_path: Path to EdigRPCApp.exe. Uses default if not specified.
            port: gRPC port. Uses 3390 if not specified.
        """
        if not GRPC_AVAILABLE:
            raise RuntimeError("gRPC modules not available. Install grpcio and grpcio-tools.")
        
        self.grpc_server_path = grpc_server_path or self.DEFAULT_GRPC_SERVER
        self.port = port or self.DEFAULT_PORT
        self.address = f"localhost:{self.port}"
        
        # gRPC components
        self.server_process: Optional[subprocess.Popen] = None
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[edi_grpc.EdigRPCStub] = None
        
        # Device state
        self.amplifier_handle: Optional[int] = None
        self.device_info: Optional[DeviceInfo] = None
        self.channels: List[ChannelInfo] = []
        
        # Streaming state
        self.sample_rate: int = 512
        self.is_connected: bool = False
        self.is_streaming: bool = False
        
        # Data buffer
        self.data_buffer = deque(maxlen=32768)  # ~64 seconds at 512 Hz
        self.buffer_lock = threading.Lock()
        
        # Streaming thread
        self.stream_thread: Optional[threading.Thread] = None
        self.stop_thread_flag = threading.Event()
        
        # Callbacks
        self.on_data_callback: Optional[callable] = None
        self.on_error_callback: Optional[callable] = None
        
        # Cached impedance values (updated during impedance check)
        self._cached_impedances: Dict[str, float] = {}
        self._impedance_timestamp: float = 0
        self._impedance_check_thread: Optional[threading.Thread] = None
        
        # Sample counter for time tracking
        self._sample_counter: int = 0
        self._stream_start_time: float = 0
    
    def _start_server(self) -> bool:
        """Start the gRPC server process"""
        if self.server_process and self.server_process.poll() is None:
            print("[EDI2] Server already running")
            return True
        
        # Check if a server is already running on the port (from a previous session)
        # Try to connect before starting a new one
        try:
            test_channel = grpc.insecure_channel(self.address)
            test_stub = edi_grpc.EdigRPCStub(test_channel)
            test_stub.DeviceManager_GetDevices(
                edi.DeviceManager_GetDevicesRequest(),
                timeout=1.0
            )
            test_channel.close()
            print(f"[EDI2] Found existing server on port {self.port}, reusing it")
            return True
        except grpc.RpcError:
            # No server running, need to start one
            pass
        
        if not os.path.exists(self.grpc_server_path):
            raise FileNotFoundError(f"gRPC server not found: {self.grpc_server_path}")
        
        try:
            print(f"[EDI2] Starting gRPC server on port {self.port}...")
            # Use CREATE_NEW_CONSOLE to ensure server has proper I/O handles
            # This matches the working test script behavior
            self.server_process = subprocess.Popen(
                [self.grpc_server_path, f"--port={self.port}"],
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            )
            
            # Wait for server to initialize with retry logic
            max_retries = 10
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                time.sleep(retry_delay)
                
                # Check if process is still alive
                if self.server_process.poll() is not None:
                    raise RuntimeError("Server process terminated unexpectedly")
                
                # Try to connect
                try:
                    test_channel = grpc.insecure_channel(self.address)
                    test_stub = edi_grpc.EdigRPCStub(test_channel)
                    test_stub.DeviceManager_GetDevices(
                        edi.DeviceManager_GetDevicesRequest(),
                        timeout=1.0
                    )
                    test_channel.close()
                    print(f"[EDI2] Server ready (PID: {self.server_process.pid})")
                    return True
                except grpc.RpcError:
                    if attempt < max_retries - 1:
                        print(f"[EDI2] Waiting for server... ({attempt + 1}/{max_retries})")
                    continue
            
            raise RuntimeError("Server did not become ready in time")
            
        except Exception as e:
            print(f"[EDI2] Error starting server: {e}")
            if self.server_process:
                try:
                    self.server_process.terminate()
                except:
                    pass
                self.server_process = None
            return False
    
    def _stop_server(self):
        """Stop the gRPC server process"""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
                print("[EDI2] Server stopped")
            except Exception as e:
                print(f"[EDI2] Error stopping server: {e}")
                try:
                    self.server_process.kill()
                except:
                    pass
            self.server_process = None
    
    def _connect_grpc(self) -> bool:
        """Establish gRPC channel connection"""
        # Reuse existing connection if available
        if self.stub is not None:
            try:
                # Test connection with a simple call
                self.stub.DeviceManager_GetDevices(
                    edi.DeviceManager_GetDevicesRequest(),
                    timeout=1.0
                )
                print("[EDI2] Reusing existing gRPC connection")
                return True
            except:
                # Connection broken, recreate
                self._disconnect_grpc()
        
        try:
            # Create channel with keepalive options to prevent timeout during streaming
            # Windows gRPC may close idle connections after a few seconds without keepalive
            options = [
                ('grpc.keepalive_time_ms', 10000),  # Send keepalive ping every 10 seconds
                ('grpc.keepalive_timeout_ms', 5000),  # Wait 5 seconds for keepalive ack
                ('grpc.keepalive_permit_without_calls', True),  # Allow keepalive pings even when no calls
                ('grpc.http2.max_pings_without_data', 0),  # Unlimited pings without data
                ('grpc.http2.min_time_between_pings_ms', 10000),  # Minimum 10s between pings
            ]
            self.channel = grpc.insecure_channel(self.address, options=options)
            self.stub = edi_grpc.EdigRPCStub(self.channel)
            
            # Verify connection by getting device list
            response = self.stub.DeviceManager_GetDevices(
                edi.DeviceManager_GetDevicesRequest()
            )
            print(f"[EDI2] Connected to server ({len(response.DeviceInfoList)} device(s) available)")
            return True
            
        except grpc.RpcError as e:
            print(f"[EDI2] gRPC connection failed: {e}")
            return False
    
    def _disconnect_grpc(self):
        """Close gRPC channel"""
        if self.channel:
            try:
                self.channel.close()
            except:
                pass
            self.channel = None
            self.stub = None
    
    def discover_devices(self) -> List[Dict[str, Any]]:
        """
        Discover connected ANT Neuro devices
        
        Returns:
            List of device dictionaries with 'serial', 'type', 'key' fields
        """
        # Ensure server is running
        if not self._start_server():
            return []
        
        if not self._connect_grpc():
            return []
        
        try:
            response = self.stub.DeviceManager_GetDevices(
                edi.DeviceManager_GetDevicesRequest()
            )
            
            devices = []
            for dev in response.DeviceInfoList:
                devices.append({
                    'serial': dev.Serial,
                    'type': dev.AmplifierType,
                    'key': dev.Key,
                })
            
            print(f"[EDI2] Found {len(devices)} device(s)")
            for d in devices:
                print(f"  - {d['serial']} (Type: {d['type']}, Key: {d['key']})")
            
            return devices
            
        except grpc.RpcError as e:
            print(f"[EDI2] Error discovering devices: {e}")
            return []
    
    def connect(self, device_serial: str = None) -> bool:
        """
        Connect to an ANT Neuro device
        
        Args:
            device_serial: Serial number of device to connect. Uses first found if None.
            
        Returns:
            True if connected successfully
        """
        # Ensure server is running (don't restart if already running)
        if self.server_process is None or self.server_process.poll() is not None:
            if not self._start_server():
                return False
        
        # Ensure gRPC channel is connected (reuse if already connected)
        if self.stub is None:
            if not self._connect_grpc():
                return False
        
        # Retry logic for "Amplifier in use" errors
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                # IMPORTANT: Dispose old amplifier handle before creating new one
                # This prevents "amplifier with id X not found" errors from stale handles
                if self.amplifier_handle is not None:
                    try:
                        print(f"[EDI2] Disposing old amplifier handle: {self.amplifier_handle}")
                        self.stub.Amplifier_Dispose(
                            edi.Amplifier_DisposeRequest(
                                AmplifierHandle=self.amplifier_handle
                            )
                        )
                    except Exception as e:
                        # Handle may already be disposed - that's OK
                        print(f"[EDI2] Old handle disposal (expected): {e}")
                    self.amplifier_handle = None
                
                # Get devices
                device_resp = self.stub.DeviceManager_GetDevices(
                    edi.DeviceManager_GetDevicesRequest()
                )
                
                if not device_resp.DeviceInfoList:
                    print("[EDI2] No devices found")
                    return False
                
                # Find matching device or use first
                device_info = None
                for dev in device_resp.DeviceInfoList:
                    if device_serial is None or dev.Serial == device_serial:
                        device_info = dev
                        break
                
                if not device_info:
                    print(f"[EDI2] Device {device_serial} not found")
                    return False
                
                # Create amplifier
                create_resp = self.stub.Controller_CreateDevice(
                    edi.Controller_CreateDeviceRequest(
                        DeviceInfoList=[device_info]
                    )
                )
                
                self.amplifier_handle = create_resp.AmplifierHandle
                print(f"[EDI2] Created amplifier (handle: {self.amplifier_handle})")
                
                # Get device info (use correct method name)
                info_resp = self.stub.Amplifier_GetDeviceInformation(
                    edi.Amplifier_GetDeviceInformationRequest(
                        AmplifierHandle=self.amplifier_handle
                    )
                )
                
                # Get channel list (use correct method name)
                ch_resp = self.stub.Amplifier_GetChannelsAvailable(
                    edi.Amplifier_GetChannelsAvailableRequest(
                        AmplifierHandle=self.amplifier_handle
                    )
                )
                
                self.channels = []
                for idx, ch in enumerate(ch_resp.ChannelList):
                    # Note: SDK returns "none" when no electrode layout is configured
                    # We preserve this so the GUI can detect it and use appropriate fallback
                    ch_name = ch.Name if ch.Name and ch.Name.lower() != 'none' else f"Ch{ch.ChannelIndex+1}"
                    self.channels.append(ChannelInfo(
                        index=ch.ChannelIndex,
                        name=ch_name,
                        polarity=ch.ChannelPolarity,
                        channel_type=ch.UnitType
                    ))
                
                # Store device info (DeviceInformation is a nested message)
                dev_info = info_resp.DeviceInformation
                self.device_info = DeviceInfo(
                    serial=dev_info.Serial if hasattr(dev_info, 'Serial') else device_info.Serial,
                    device_type=device_info.AmplifierType,
                    key=device_info.Key,
                    channel_count=len(self.channels),
                    firmware_version=getattr(dev_info, 'FirmwareVersion', '')
                )
                
                self.is_connected = True
                print(f"[EDI2] Connected to {self.device_info.serial}")
                print(f"[EDI2]   Channels: {self.device_info.channel_count}")
                
                return True
                
            except grpc.RpcError as e:
                error_message = str(e)
                print(f"[EDI2] Connection error: {e}")
                
                # Check if it's an "Amplifier in use" error and we haven't retried yet
                if "Amplifier in use" in error_message and attempt < max_retries:
                    print(f"[EDI2] Amplifier in use - restarting gRPC server to clear stale handles...")
                    print(f"[EDI2] Retry attempt {attempt + 1}/{max_retries}")
                    
                    # Stop and restart gRPC server to clear all handles
                    self._stop_server()
                    import time
                    time.sleep(1)  # Give it time to fully stop
                    
                    if not self._start_server():
                        print("[EDI2] Failed to restart server")
                        return False
                    
                    # Reconnect gRPC channel
                    self.stub = None
                    if not self._connect_grpc():
                        print("[EDI2] Failed to reconnect gRPC")
                        return False
                    
                    print("[EDI2] Server restarted, retrying connection...")
                    continue  # Retry the connection
                else:
                    # Not "Amplifier in use" error, or we've already retried
                    return False
        
        # If we exhausted all retries
        return False
    
    def disconnect(self):
        """Disconnect from the device"""
        self.stop_streaming()
        
        if self.amplifier_handle is not None and self.stub:
            try:
                self.stub.Amplifier_Dispose(
                    edi.Amplifier_DisposeRequest(
                        AmplifierHandle=self.amplifier_handle
                    )
                )
            except:
                pass
        
        self.amplifier_handle = None
        self.device_info = None
        self.is_connected = False
        
        self._disconnect_grpc()
        self._stop_server()
        
        print("[EDI2] Disconnected")
    
    def get_available_sample_rates(self) -> List[float]:
        """Get list of available sampling rates"""
        if not self.is_connected or not self.stub:
            return []
        
        try:
            resp = self.stub.Amplifier_GetSampleRatesAvailable(
                edi.Amplifier_GetSampleRatesAvailableRequest(
                    AmplifierHandle=self.amplifier_handle
                )
            )
            return list(resp.RateList)
        except:
            return [250.0, 256.0, 500.0, 512.0, 1000.0, 1024.0, 2000.0, 2048.0]
    
    def get_power_state(self) -> Dict[str, Any]:
        """Get device power state"""
        if not self.is_connected or not self.stub:
            return {}
        
        try:
            resp = self.stub.Amplifier_GetPower(
                edi.Amplifier_GetPowerRequest(
                    AmplifierHandle=self.amplifier_handle
                )
            )
            if resp.PowerList:
                pwr = resp.PowerList[0]
                return {
                    'battery_level': pwr.BatteryLevel,
                    'is_charging': pwr.isBatteryCharging,
                    'is_power_on': pwr.isPowerOn
                }
        except:
            pass
        return {}
    
    def start_streaming(self, sample_rate: float = 512.0, 
                        reference_range: float = 1.0,
                        bipolar_range: float = 1.5) -> bool:
        """
        Start EEG data streaming
        
        Args:
            sample_rate: Sampling rate in Hz (default 512)
            reference_range: Voltage range for reference channels (1.0, 0.75, or 0.15 V)
            bipolar_range: Voltage range for bipolar channels (4.0, 1.5, 0.7, or 0.35 V)
            
        Returns:
            True if streaming started successfully
        """
        if not self.is_connected:
            print("[EDI2] Not connected")
            return False
        
        if self.is_streaming:
            print("[EDI2] Already streaming")
            return True
        
        # Validate ranges
        if reference_range not in self.REFERENCE_RANGES:
            print(f"[EDI2] Invalid reference range {reference_range}, using 1.0V")
            reference_range = 1.0
        
        if bipolar_range not in self.BIPOLAR_RANGES:
            print(f"[EDI2] Invalid bipolar range {bipolar_range}, using 1.5V")
            bipolar_range = 1.5
        
        try:
            self.sample_rate = int(sample_rate)
            
            # Create stream parameters
            stream_params = edi.StreamParams(
                ActiveChannels=list(range(len(self.channels))),
                Ranges={0: reference_range, 1: bipolar_range},
                SamplingRate=float(sample_rate),
                BufferSize=1000,
                DataReadyPercentage=50
            )
            
            print(f"[EDI2] Setting mode to EEG with {len(self.channels)} channels at {sample_rate} Hz...")
            
            # Set mode to EEG
            try:
                self.stub.Amplifier_SetMode(
                    edi.Amplifier_SetModeRequest(
                        AmplifierHandle=self.amplifier_handle,
                        Mode=edi.AmplifierMode.AmplifierMode_Eeg,
                        StreamParams=stream_params
                    )
                )
            except grpc.RpcError as e:
                # Handle stale amplifier handle - try reconnecting
                if "not found" in str(e).lower():
                    print(f"[EDI2] Amplifier handle stale, reconnecting...")
                    if self.device_info and self.connect(self.device_info.serial):
                        # Retry after reconnect
                        self.stub.Amplifier_SetMode(
                            edi.Amplifier_SetModeRequest(
                                AmplifierHandle=self.amplifier_handle,
                                Mode=edi.AmplifierMode.AmplifierMode_Eeg,
                                StreamParams=stream_params
                            )
                        )
                    else:
                        raise e
                else:
                    raise e
            
            print(f"[EDI2] Streaming started at {sample_rate} Hz")
            
            # Start data collection thread
            self.stop_thread_flag.clear()
            self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
            self.stream_thread.start()
            
            self.is_streaming = True
            return True
            
        except grpc.RpcError as e:
            print(f"[EDI2] Error starting stream: {e}")
            return False
    
    def stop_streaming(self):
        """Stop EEG data streaming"""
        if not self.is_streaming:
            return
        
        # Stop stream thread
        self.stop_thread_flag.set()
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=2.0)
        
        # Set mode to idle
        if self.stub and self.amplifier_handle is not None:
            try:
                self.stub.Amplifier_SetMode(
                    edi.Amplifier_SetModeRequest(
                        AmplifierHandle=self.amplifier_handle,
                        Mode=edi.AmplifierMode.AmplifierMode_Idle,
                        StreamParams=edi.StreamParams()
                    )
                )
            except:
                pass
        
        self.is_streaming = False
        print("[EDI2] Streaming stopped")
    
    def _stream_loop(self):
        """Background thread for continuous data acquisition"""
        print("[EDI2] Stream loop started")
        
        frame_count = 0
        zero_frame_count = 0
        # Store the last sample from previous frame for differentiation
        # EDI2 gRPC returns cumulative/integrated values, we need to differentiate
        self._last_sample = None
        
        while not self.stop_thread_flag.is_set():
            try:
                # Get frame from amplifier
                frame_resp = self.stub.Amplifier_GetFrame(
                    edi.Amplifier_GetFrameRequest(
                        AmplifierHandle=self.amplifier_handle
                    )
                )
                
                if not frame_resp.FrameList:
                    # No frames available - skip this iteration
                    time.sleep(0.001)
                    continue
                
                for frame in frame_resp.FrameList:
                    # Extract data matrix (cumulative/integrated values)
                    cols = frame.Matrix.Cols  # channels
                    rows = frame.Matrix.Rows  # samples
                    raw_data = np.array(frame.Matrix.Data).reshape(rows, cols)
                    
                    # Check if raw data is all zeros (device may have stopped)
                    if np.all(raw_data == 0):
                        zero_frame_count += 1
                        if zero_frame_count == 1:
                            print(f"[EDI2] WARNING: Received all-zero frame (device may have stopped)")
                        continue
                    else:
                        if zero_frame_count > 0:
                            print(f"[EDI2] Data resumed after {zero_frame_count} zero frames")
                            zero_frame_count = 0
                    
                    # Differentiate to get instantaneous EEG values
                    # EDI2 gRPC returns integrated/accumulated voltages
                    if self._last_sample is not None:
                        # Check for stuck/constant values which would give zeros after diff
                        raw_diff = np.max(np.abs(raw_data[-1] - self._last_sample))
                        if raw_diff < 1e-10:  # Effectively no change
                            # Keep using last good sample to avoid zeros
                            pass
                        
                        # Prepend last sample from previous frame for continuous differentiation
                        extended_data = np.vstack([self._last_sample.reshape(1, -1), raw_data])
                        data = np.diff(extended_data, axis=0)
                    else:
                        # First frame: use diff within frame (lose first sample)
                        data = np.diff(raw_data, axis=0)
                    
                    # Store last sample for next frame
                    self._last_sample = raw_data[-1].copy()
                    
                    frame_count += 1
                    
                    # Add to buffer
                    with self.buffer_lock:
                        for sample in data:
                            self.data_buffer.append(sample)
                    
                    # Call callback if set
                    if self.on_data_callback:
                        self.on_data_callback(data)
                
                # Minimal sleep - just yield to other threads
                # At 500 Hz we get ~500 samples/sec, need to read fast
                time.sleep(0.001)
                
            except grpc.RpcError as e:
                if not self.stop_thread_flag.is_set():
                    print(f"[EDI2] Stream error: {e}")
                    if self.on_error_callback:
                        self.on_error_callback(e)
                break
            except Exception as e:
                if not self.stop_thread_flag.is_set():
                    print(f"[EDI2] Unexpected error: {e}")
                break
        
        print("[EDI2] Stream loop ended")
    
    def get_data(self, num_samples: int = None) -> Optional[np.ndarray]:
        """
        Get data from the buffer
        
        Args:
            num_samples: Number of samples to return. Returns all available if None.
            
        Returns:
            NumPy array of shape (samples, channels) or None if no data
        """
        with self.buffer_lock:
            if not self.data_buffer:
                return None
            
            if num_samples is None:
                data = np.array(list(self.data_buffer))
                self.data_buffer.clear()
            else:
                samples = min(num_samples, len(self.data_buffer))
                data = np.array([self.data_buffer.popleft() for _ in range(samples)])
            
            return data
    
    def get_latest_sample(self) -> Optional[np.ndarray]:
        """Get the most recent sample (all channels)"""
        with self.buffer_lock:
            if self.data_buffer:
                return np.array(self.data_buffer[-1])
        return None
    
    def get_channel_count(self) -> int:
        """Get number of channels"""
        return len(self.channels)
    
    def get_channel_info(self) -> List[ChannelInfo]:
        """Get channel information"""
        return self.channels
    
    def get_sample_rate(self) -> int:
        """Get current sampling rate"""
        return self.sample_rate
    
    def set_data_callback(self, callback: callable):
        """Set callback function for incoming data"""
        self.on_data_callback = callback
    
    def set_error_callback(self, callback: callable):
        """Set callback function for errors"""
        self.on_error_callback = callback
    
    def get_impedances(self) -> Dict[str, float]:
        """
        Get impedance measurements for all channels.
        
        This requires switching to impedance measurement mode temporarily.
        
        Returns:
            Dict of channel_name -> impedance in kOhm
        """
        if not self.is_connected or not self.stub:
            return {}
        
        was_streaming = self.is_streaming
        
        try:
            # Stop streaming if active (impedance requires different mode)
            if self.is_streaming:
                self.stop_streaming()
                time.sleep(0.5)
            
            # Switch to impedance mode
            stream_params = edi.StreamParams(
                ActiveChannels=list(range(len(self.channels))),
                Ranges={0: 1.0, 1: 1.5},
                SamplingRate=512.0,
                BufferSize=1000,
                DataReadyPercentage=50
            )
            
            self.stub.Amplifier_SetMode(
                edi.Amplifier_SetModeRequest(
                    AmplifierHandle=self.amplifier_handle,
                    Mode=edi.AmplifierMode.AmplifierMode_Impedance,
                    StreamParams=stream_params
                )
            )
            
            # Wait for impedance data
            time.sleep(1.0)
            
            # Get impedance frame
            frame_resp = self.stub.Amplifier_GetFrame(
                edi.Amplifier_GetFrameRequest(
                    AmplifierHandle=self.amplifier_handle
                )
            )
            
            impedances = {}
            for frame in frame_resp.FrameList:
                if frame.Impedance and frame.Impedance.Channels:
                    for i, ch_imp in enumerate(frame.Impedance.Channels):
                        if i < 64:  # Only reference channels
                            ch_name = self.channels[i].name if i < len(self.channels) else f"Ch{i+1}"
                            # Value is in Ohms, convert to kOhm
                            impedances[ch_name] = round(ch_imp.Value / 1000.0, 1)
            
            # Switch back to idle mode
            self.stub.Amplifier_SetMode(
                edi.Amplifier_SetModeRequest(
                    AmplifierHandle=self.amplifier_handle,
                    Mode=edi.AmplifierMode.AmplifierMode_Idle,
                    StreamParams=edi.StreamParams()
                )
            )
            
            # Cache the impedances
            self._cached_impedances = impedances.copy()
            self._impedance_timestamp = time.time()
            
            # Restart streaming if it was active
            if was_streaming:
                time.sleep(0.5)
                self.start_streaming(sample_rate=self.sample_rate)
            
            return impedances
            
        except Exception as e:
            print(f"[EDI2] Error getting impedances: {e}")
            # Try to return to idle mode
            try:
                self.stub.Amplifier_SetMode(
                    edi.Amplifier_SetModeRequest(
                        AmplifierHandle=self.amplifier_handle,
                        Mode=edi.AmplifierMode.AmplifierMode_Idle,
                        StreamParams=edi.StreamParams()
                    )
                )
            except:
                pass
            return {}
    
    def get_cached_impedances(self) -> Dict[str, float]:
        """
        Get cached impedance values without disrupting streaming.
        
        Returns cached values from last impedance check.
        Use get_impedances() or start_background_impedance_check() to update values.
        
        Returns:
            Dict of channel_name -> impedance in kOhm (may be stale)
        """
        return self._cached_impedances.copy()
    
    def get_impedance_age(self) -> float:
        """
        Get how old the cached impedance values are.
        
        Returns:
            Time in seconds since last impedance measurement, or inf if never measured
        """
        if self._impedance_timestamp == 0:
            return float('inf')
        return time.time() - self._impedance_timestamp
    
    def start_background_impedance_check(self) -> bool:
        """
        Start an impedance check in the background.
        
        This will pause streaming, measure impedances, cache them, and resume streaming.
        The measurement happens in a background thread so this returns immediately.
        
        Returns:
            True if background check was started, False if one is already running
        """
        if self._impedance_check_thread and self._impedance_check_thread.is_alive():
            print("[EDI2] Background impedance check already in progress")
            return False
        
        def _do_impedance_check():
            print("[EDI2] Starting background impedance check...")
            self.get_impedances()  # This updates cache
            print(f"[EDI2] Background impedance check complete: {len(self._cached_impedances)} channels")
        
        self._impedance_check_thread = threading.Thread(target=_do_impedance_check, daemon=True)
        self._impedance_check_thread.start()
        return True

    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
        return False


# =============================================================================
# Convenience Functions
# =============================================================================

def create_edi2_client(grpc_server_path: str = None) -> EDI2Client:
    """
    Factory function to create an EDI2 client
    
    Args:
        grpc_server_path: Optional custom path to EdigRPCApp.exe
        
    Returns:
        Configured EDI2Client instance
    """
    return EDI2Client(grpc_server_path=grpc_server_path)


def test_edi2_connection():
    """Quick test of EDI2 connectivity"""
    print("="*60)
    print("EDI2 CLIENT TEST")
    print("="*60)
    
    client = EDI2Client()
    
    try:
        # Discover devices
        print("\n[1] Discovering devices...")
        devices = client.discover_devices()
        
        if not devices:
            print("No devices found!")
            return False
        
        # Connect
        print(f"\n[2] Connecting to {devices[0]['serial']}...")
        if not client.connect(devices[0]['serial']):
            print("Connection failed!")
            return False
        
        # Check power
        print("\n[3] Checking power state...")
        power = client.get_power_state()
        print(f"  Battery: {power.get('battery_level', 'N/A')}%")
        print(f"  Charging: {power.get('is_charging', 'N/A')}")
        print(f"  Power On: {power.get('is_power_on', 'N/A')}")
        
        # Start streaming
        print("\n[4] Starting stream at 512 Hz...")
        if not client.start_streaming(sample_rate=512):
            print("Failed to start streaming!")
            return False
        
        # Collect data
        print("\n[5] Collecting data for 3 seconds...")
        time.sleep(3)
        
        data = client.get_data()
        if data is not None:
            print(f"  Collected: {data.shape[0]} samples x {data.shape[1]} channels")
            print(f"  Data range: {data.min():.2f} to {data.max():.2f}")
        else:
            print("  No data collected!")
        
        # Stop
        print("\n[6] Stopping stream...")
        client.stop_streaming()
        
        print("\n" + "="*60)
        print("TEST PASSED!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        client.disconnect()


if __name__ == "__main__":
    test_edi2_connection()
