#!/usr/bin/env python3
"""
ANT Neuro 64-Channel EEG Analyzer - Sequential Workflow Integrated Version
==========================================================================

This is the MAIN application file for the ANT Neuro analyzer.
It mirrors BrainLinkAnalyzer_GUI_Sequential_Integrated.py exactly with:
- Same UI dialogs and styling
- Same sequential workflow (OS Selection → Login → Calibration → Tasks)
- Same calibration protocol
- Same task execution

The only differences:
- Uses ANT Neuro eego SDK instead of BrainLink serial connection
- Enhanced 64-channel analysis capabilities
- Professional EEG topographic visualization

RUN THIS FILE to start the ANT Neuro analyzer application.

Author: BrainLink Companion Team
Date: February 2026
Device: ANT Neuro eego 64-channel EEG
"""

import os
import sys
import platform
import numpy as np

# Set Qt environment BEFORE any imports
os.environ.setdefault('PYQTGRAPH_QT_LIB', 'PySide6')

# Fix Qt plugin path
try:
    import PySide6
    pyside_dir = os.path.dirname(PySide6.__file__)
    plugins_dir = os.path.join(pyside_dir, 'plugins', 'platforms')
    if os.path.isdir(plugins_dir):
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugins_dir
except Exception:
    pass

# Initialize pygame mixer for cross-platform audio
try:
    import pygame.mixer
    pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
    AUDIO_AVAILABLE = True
except Exception:
    AUDIO_AVAILABLE = False
    print("Warning: pygame not available, audio beeps will be disabled")


def play_beep(frequency=800, duration_ms=200):
    """Cross-platform beep using pygame mixer."""
    if not AUDIO_AVAILABLE:
        return
    try:
        sample_rate = 22050
        duration_s = duration_ms / 1000.0
        num_samples = int(sample_rate * duration_s)
        samples = np.sin(2 * np.pi * frequency * np.linspace(0, duration_s, num_samples))
        samples = (samples * 32767).astype(np.int16)
        stereo_samples = np.column_stack((samples, samples))
        sound = pygame.mixer.Sound(buffer=stereo_samples)
        sound.play()
    except Exception as e:
        print(f"Warning: Could not play beep: {e}")


# ============================================================================
# ANT Neuro eego SDK Setup
# ============================================================================

EEGO_SDK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'eego_sdk_toolbox'
)

if EEGO_SDK_PATH not in sys.path:
    sys.path.insert(0, EEGO_SDK_PATH)

if platform.system() == 'Windows':
    try:
        os.add_dll_directory(EEGO_SDK_PATH)
    except Exception:
        pass

EEGO_SDK_AVAILABLE = False
eego_sdk = None

try:
    import eego_sdk
    EEGO_SDK_AVAILABLE = True
    print("✓ eego SDK loaded successfully")
except ImportError as e:
    print(f"⚠ eego SDK not available: {e}")
    print(f"  Expected path: {EEGO_SDK_PATH}")
    print("  The application will run in demo mode.")

# EDI2 gRPC API - Modern alternative that solves power state issues
EDI2_AVAILABLE = False
try:
    from edi2_client import EDI2Client
    EDI2_AVAILABLE = True
    print("✓ EDI2 gRPC client loaded successfully")
except ImportError as e:
    print(f"⚠ EDI2 client not available: {e}")


# ============================================================================
# Import shared utilities and task definitions from BrainLink
# ============================================================================

# Add parent directory to path for shared imports
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# Import ONLY the task definitions and constants, NOT the GUI classes
# This prevents BrainLink port scanning from running
from BrainLinkAnalyzer_GUI import (
    AVAILABLE_TASKS,
    EEG_BANDS,
    WINDOW_SIZE,
    OVERLAP_SIZE,
)

# Import Qt components
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import (
    QDialog, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QWidget, QComboBox, QRadioButton, QLineEdit, QFrame, QFormLayout,
    QMessageBox, QCheckBox, QProgressBar, QGroupBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QGridLayout
)
from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QIcon
import pyqtgraph as pg
from typing import Optional, Dict, Any
from collections import deque
import requests
import ssl
import threading
import time
import copy
import math

# Import enhanced 64-channel analysis engine
try:
    from enhanced_multichannel_analysis import Enhanced64ChannelEngine, create_enhanced_engine
    ENHANCED_64CH_AVAILABLE = True
    print("✓ Enhanced 64-channel analysis engine loaded")
except ImportError as e:
    ENHANCED_64CH_AVAILABLE = False
    print(f"⚠ Enhanced 64-channel engine not available: {e}")
    print("  Falling back to simplified analysis")


# ============================================================================
# ANT Neuro Feature Engine (Simplified Fallback)
# ============================================================================

class AntNeuroFeatureEngine:
    """Feature extraction and analysis engine for ANT Neuro 64-channel EEG
    
    This is a simplified version that matches BrainLink's interface for 
    compatibility with the same workflow, but uses ANT Neuro-specific processing.
    """
    
    def __init__(self, sample_rate: int = 500):
        self.sample_rate = sample_rate
        self.channel_count = 64
        
        # Calibration data storage (matches BrainLink structure)
        self.calibration_data = {
            'eyes_closed': {'features': [], 'timestamps': []},
            'eyes_open': {'features': [], 'timestamps': []},
            'task': {'features': [], 'timestamps': []},
            'tasks': {},  # Multi-task storage
        }
        
        # State tracking
        self.current_state = 'idle'
        self.current_task = None
        self.baseline_stats = {}
        
        # Results storage
        self.multi_task_results = None
        self.task_summary = {}
        self.last_export_full = {}
        self.last_export_integer = {}
        
        # Progress callbacks
        self._permutation_progress_callback = None
        self._general_progress_callback = None
        
        # Log function
        self.log_message = None
    
    def set_log_function(self, log_fn):
        """Set the logging function"""
        self.log_message = log_fn
    
    def start_calibration_phase(self, phase: str):
        """Start a calibration phase (eyes_closed or eyes_open)"""
        self.current_state = phase
        if phase not in self.calibration_data:
            self.calibration_data[phase] = {'features': [], 'timestamps': []}
        print(f"\n{'='*60}")
        print(f"[ANT NEURO ENGINE] CALIBRATION PHASE STARTED: {phase.upper()}")
        print(f"[ANT NEURO ENGINE] State: {self.current_state}")
        print(f"[ANT NEURO ENGINE] Sample rate: {self.sample_rate} Hz")
        print(f"[ANT NEURO ENGINE] Channels: {self.channel_count}")
        print(f"[ANT NEURO ENGINE] Features will be extracted and stored")
        print(f"{'='*60}\n")
    
    def stop_calibration_phase(self):
        """Stop the current calibration phase"""
        feature_count = len(self.calibration_data.get(self.current_state, {}).get('features', []))
        print(f"\n{'='*60}")
        print(f"[ANT NEURO ENGINE] CALIBRATION PHASE STOPPED: {self.current_state.upper()}")
        print(f"[ANT NEURO ENGINE] Features collected: {feature_count}")
        print(f"[ANT NEURO ENGINE] Returning to idle state")
        print(f"{'='*60}\n")
        self.current_state = 'idle'
    
    def start_task(self, task_name: str):
        """Start recording a task"""
        self.current_task = task_name
        self.current_state = 'task'
        
        # Initialize task storage
        if 'tasks' not in self.calibration_data:
            self.calibration_data['tasks'] = {}
        
        if task_name not in self.calibration_data['tasks']:
            self.calibration_data['tasks'][task_name] = {'features': [], 'timestamps': []}
        
        print(f"\n{'='*60}")
        print(f"[ANT NEURO ENGINE] TASK STARTED: {task_name}")
        print(f"[ANT NEURO ENGINE] State: {self.current_state}")
        print(f"[ANT NEURO ENGINE] Task data will be recorded and analyzed")
        print(f"{'='*60}\n")
    
    def stop_task(self):
        """Stop the current task"""
        if self.current_task:
            feature_count = len(self.calibration_data.get('tasks', {}).get(self.current_task, {}).get('features', []))
            print(f"\n{'='*60}")
            print(f"[ANT NEURO ENGINE] TASK STOPPED: {self.current_task}")
            print(f"[ANT NEURO ENGINE] Features collected: {feature_count}")
            print(f"[ANT NEURO ENGINE] Task ready for analysis")
            print(f"{'='*60}\n")
        self.current_task = None
        self.current_state = 'idle'
    
    def add_features(self, features: Dict[str, Any], timestamp: float = None):
        """Add extracted features to the current phase/task"""
        if timestamp is None:
            timestamp = time.time()
        
        if self.current_state in ['eyes_closed', 'eyes_open']:
            self.calibration_data[self.current_state]['features'].append(features)
            self.calibration_data[self.current_state]['timestamps'].append(timestamp)
        elif self.current_state == 'task' and self.current_task:
            self.calibration_data['tasks'][self.current_task]['features'].append(features)
            self.calibration_data['tasks'][self.current_task]['timestamps'].append(timestamp)
    
    def compute_baseline_statistics(self):
        """Compute baseline statistics from calibration data"""
        ec_features = self.calibration_data.get('eyes_closed', {}).get('features', [])
        eo_features = self.calibration_data.get('eyes_open', {}).get('features', [])
        
        print(f"\n{'='*60}")
        print(f"[ANT NEURO ENGINE] COMPUTING BASELINE STATISTICS")
        print(f"[ANT NEURO ENGINE] Eyes closed features: {len(ec_features)}")
        print(f"[ANT NEURO ENGINE] Eyes open features: {len(eo_features)}")
        
        # Combine for baseline
        all_baseline = ec_features + eo_features
        
        if not all_baseline:
            print(f"[ANT NEURO ENGINE] ERROR: No baseline data available")
            print(f"{'='*60}\n")
            return
        
        print(f"[ANT NEURO ENGINE] Total baseline samples: {len(all_baseline)}")
        
        # Compute mean and std for each feature
        feature_names = set()
        for f in all_baseline:
            if isinstance(f, dict):
                feature_names.update(f.keys())
        
        print(f"[ANT NEURO ENGINE] Unique features found: {len(feature_names)}")
        
        self.baseline_stats = {}
        for fname in feature_names:
            values = [f.get(fname) for f in all_baseline if isinstance(f, dict) and fname in f and f[fname] is not None]
            if values:
                mean_val = np.mean(values)
                std_val = np.std(values) if len(values) > 1 else 1.0
                self.baseline_stats[fname] = {
                    'mean': mean_val,
                    'std': std_val,
                    'n': len(values)
                }
                print(f"[ANT NEURO ENGINE]   {fname}: mean={mean_val:.4f}, std={std_val:.4f}, n={len(values)}")
        
        print(f"[ANT NEURO ENGINE] ✓ Baseline statistics computed for {len(self.baseline_stats)} features")
        print(f"{'='*60}\n")
    
    def set_permutation_progress_callback(self, callback):
        """Set callback for permutation progress updates"""
        self._permutation_progress_callback = callback
    
    def clear_permutation_progress_callback(self):
        """Clear the permutation progress callback"""
        self._permutation_progress_callback = None
    
    def analyze_task_data(self) -> Dict[str, Any]:
        """Analyze current task data against baseline"""
        task_data = self.calibration_data.get('task', {}).get('features', [])
        
        print(f"\n{'='*60}")
        print(f"[ANT NEURO ENGINE] ANALYZING TASK DATA")
        print(f"[ANT NEURO ENGINE] Task: {self.current_task or 'current'}")
        print(f"[ANT NEURO ENGINE] Task samples: {len(task_data)}")
        print(f"[ANT NEURO ENGINE] Baseline features: {len(self.baseline_stats)}")
        
        if not task_data or not self.baseline_stats:
            print(f"[ANT NEURO ENGINE] ERROR: Insufficient data for analysis")
            print(f"{'='*60}\n")
            return {}
        
        results = {}
        significant_features = []
        
        for fname, baseline in self.baseline_stats.items():
            task_values = [f.get(fname) for f in task_data if isinstance(f, dict) and fname in f and f[fname] is not None]
            
            if not task_values:
                continue
            
            task_mean = np.mean(task_values)
            baseline_mean = baseline['mean']
            baseline_std = baseline['std'] if baseline['std'] > 0 else 1.0
            
            delta = task_mean - baseline_mean
            effect_size_d = delta / baseline_std
            
            # Simple statistical test (t-test approximation)
            from scipy import stats
            if len(task_values) > 1:
                t_stat, p_value = stats.ttest_1samp(task_values, baseline_mean)
            else:
                p_value = 1.0
            
            # Determine significance
            significant = p_value < 0.05 and abs(effect_size_d) > 0.2
            
            results[fname] = {
                'task_mean': task_mean,
                'baseline_mean': baseline_mean,
                'delta': delta,
                'effect_size_d': effect_size_d,
                'p_value': p_value,
                'significant_change': significant,
            }
            
            if significant:
                significant_features.append(fname)
                print(f"[ANT NEURO ENGINE]   ✓ {fname}: δ={delta:.4f}, d={effect_size_d:.4f}, p={p_value:.4f} [SIGNIFICANT]")
        
        # Update task_summary
        significant_count = len(significant_features)
        self.task_summary = {
            'fisher': {'km_p': 0.05, 'significant': significant_count > 0, 'km_df': len(results) * 2},
            'sum_p': {'perm_p': 0.05, 'significant': significant_count > 0, 'value': significant_count},
            'feature_selection': {'sig_feature_count': significant_count},
        }
        
        print(f"[ANT NEURO ENGINE] Analysis complete: {len(results)} features analyzed")
        print(f"[ANT NEURO ENGINE] Significant features: {significant_count}")
        if significant_features:
            print(f"[ANT NEURO ENGINE] Significant: {', '.join(significant_features[:5])}{'...' if len(significant_features) > 5 else ''}")
        print(f"{'='*60}\n")
        
        return results
    
    def analyze_all_tasks_data(self) -> Dict[str, Any]:
        """Analyze all recorded tasks - matches BrainLink interface"""
        print(f"\n{'='*60}")
        print(f"[ANT NEURO ENGINE] MULTI-TASK ANALYSIS STARTED")
        
        if not self.baseline_stats:
            print(f"[ANT NEURO ENGINE] No baseline stats found, computing...")
            try:
                self.compute_baseline_statistics()
            except Exception as e:
                print(f"[ANT NEURO ENGINE] ERROR computing baseline: {e}")
        
        tasks = self.calibration_data.get('tasks', {})
        print(f"[ANT NEURO ENGINE] Tasks to analyze: {len(tasks)}")
        
        if not tasks:
            print(f"[ANT NEURO ENGINE] No tasks recorded, returning empty results")
            print(f"{'='*60}\n")
            self.multi_task_results = {
                'per_task': {},
                'combined': {'analysis': {}, 'summary': {}},
                'across_task': {},
            }
            return self.multi_task_results
        
        print(f"[ANT NEURO ENGINE] Task list: {', '.join(tasks.keys())}")
        
        # Save original task bucket
        task_bucket = self.calibration_data.setdefault('task', {'features': [], 'timestamps': []})
        original_features = list(task_bucket.get('features', []))
        original_timestamps = list(task_bucket.get('timestamps', []))
        
        per_task_results = {}
        total_steps = len(tasks) + 1
        current_step = 0
        
        # Report initial progress
        if self._permutation_progress_callback:
            try:
                self._permutation_progress_callback(0, total_steps * 100)
            except Exception:
                pass
        
        try:
            for task_name, data in tasks.items():
                # Set task data for analysis
                task_bucket['features'] = list(data.get('features', []))
                task_bucket['timestamps'] = list(data.get('timestamps', []))
                self.current_task = task_name
                
                # Run analysis
                analysis = self.analyze_task_data() or {}
                summary = copy.deepcopy(self.task_summary)
                
                per_task_results[task_name] = {
                    'analysis': copy.deepcopy(analysis),
                    'summary': summary,
                    'export_full': copy.deepcopy(self.last_export_full),
                    'export_integer': copy.deepcopy(self.last_export_integer),
                }
                
                current_step += 1
                
                # Report progress
                if self._permutation_progress_callback:
                    try:
                        progress = int((current_step / total_steps) * 100)
                        self._permutation_progress_callback(progress, 100)
                    except Exception:
                        pass
                
                # Small delay to allow UI updates
                time.sleep(0.1)
        finally:
            # Restore original task bucket
            task_bucket['features'] = original_features
            task_bucket['timestamps'] = original_timestamps
            self.current_task = None
        
        # Combined analysis (all tasks together)
        combined_features = []
        combined_timestamps = []
        for data in tasks.values():
            combined_features.extend(list(data.get('features', [])))
            combined_timestamps.extend(list(data.get('timestamps', [])))
        
        task_bucket['features'] = combined_features
        task_bucket['timestamps'] = combined_timestamps
        self.current_task = 'combined'
        
        combined_analysis = self.analyze_task_data() or {}
        combined_summary = copy.deepcopy(self.task_summary)
        
        # Final progress
        if self._permutation_progress_callback:
            try:
                self._permutation_progress_callback(100, 100)
            except Exception:
                pass
        
        # Restore
        task_bucket['features'] = original_features
        task_bucket['timestamps'] = original_timestamps
        self.current_task = None
        
        # Build results
        self.multi_task_results = {
            'per_task': per_task_results,
            'combined': {
                'analysis': copy.deepcopy(combined_analysis),
                'summary': combined_summary,
            },
            'across_task': self._analyze_across_tasks(tasks),
        }
        
        return self.multi_task_results
    
    def _analyze_across_tasks(self, tasks: Dict[str, Dict]) -> Dict[str, Any]:
        """Analyze features across all tasks"""
        if len(tasks) < 2:
            return {}
        
        # Find features that are significant across multiple tasks
        feature_results = {}
        all_features = set()
        
        for task_name, data in tasks.items():
            for f in data.get('features', []):
                if isinstance(f, dict):
                    all_features.update(f.keys())
        
        for fname in all_features:
            task_count = 0
            for task_name, data in tasks.items():
                values = [f.get(fname) for f in data.get('features', []) 
                         if isinstance(f, dict) and fname in f and f[fname] is not None]
                if len(values) >= 3:
                    task_count += 1
            
            feature_results[fname] = {
                'omnibus_sig': task_count >= 2,
                'task_count': task_count,
            }
        
        return {'features': feature_results}


# ============================================================================
# ANT Neuro Device Manager
# ============================================================================

class AntNeuroDeviceManager:
    """Manages ANT Neuro device connection and data streaming using EDI2 gRPC API"""
    
    def __init__(self):
        # EDI2 client (preferred - no power state blocking)
        self.edi2_client = None
        self.use_edi2 = EDI2_AVAILABLE  # Prefer EDI2 over eego SDK
        
        # Legacy eego SDK (fallback)
        self.factory = None
        self.amplifier = None
        self.stream = None
        
        self.is_connected = False
        self.is_streaming = False
        self.sample_rate = 512
        self.channel_count = 88  # EDI2 supports 88 channels (64 ref + 24 bipolar)
        
        # Data buffer (single channel for compatibility with BrainLink flow)
        self.live_data_buffer = deque(maxlen=5120)  # 10 seconds at 512 Hz
        
        # 64-channel buffer for enhanced analysis
        self.multichannel_buffer = deque(maxlen=5120)
        
        # Threading
        self.stream_thread = None
        self.stop_thread_flag = False
        
        # Device info
        self.device_serial = None
        
        print(f"[ANT NEURO] Device manager initialized")
        print(f"[ANT NEURO]   EDI2 available: {EDI2_AVAILABLE}")
        print(f"[ANT NEURO]   eego SDK available: {EEGO_SDK_AVAILABLE}")
        
    def scan_for_devices(self) -> list:
        """Scan for connected ANT Neuro amplifiers"""
        # Try EDI2 first (modern API, no power blocking)
        if self.use_edi2 and EDI2_AVAILABLE:
            try:
                print("[ANT NEURO] Scanning with EDI2 gRPC API...")
                if self.edi2_client is None:
                    self.edi2_client = EDI2Client()
                
                devices = self.edi2_client.discover_devices()
                if devices:
                    result = [{'serial': d['serial'], 'type': f"EDI2-{d.get('type', 'Unknown')}"} for d in devices]
                    print(f"[ANT NEURO] Found {len(result)} device(s) via EDI2")
                    return result
            except Exception as e:
                print(f"[ANT NEURO] EDI2 scan failed: {e}")
        
        # Fallback to eego SDK
        if EEGO_SDK_AVAILABLE:
            try:
                print("[ANT NEURO] Scanning with eego SDK...")
                if self.factory is None:
                    self.factory = eego_sdk.factory()
                
                amplifiers = self.factory.getAmplifiers()
                devices = []
                for amp in amplifiers:
                    devices.append({
                        'serial': amp.getSerial(),
                        'type': amp.getType()
                    })
                
                if devices:
                    print(f"[ANT NEURO] Found {len(devices)} device(s) via eego SDK")
                    return devices
            except Exception as e:
                print(f"[ANT NEURO] eego SDK scan failed: {e}")
        
        # No devices found - return demo
        print("[ANT NEURO] No devices found, returning demo device")
        return [{'serial': 'DEMO-001', 'type': 'Demo Device'}]
    
    def connect(self, device_serial: str) -> bool:
        """Connect to an ANT Neuro amplifier"""
        self.device_serial = device_serial
        print(f"\n{'='*60}")
        print(f"[ANT NEURO CONNECT] Attempting to connect to device: {device_serial}")
        
        # Demo mode
        if device_serial == 'DEMO-001':
            self.is_connected = True
            self.use_edi2 = False
            self.channel_count = 64
            print(f"[ANT NEURO CONNECT] Mode: DEMO (synthetic data)")
            print(f"[ANT NEURO CONNECT] Channels: {self.channel_count}")
            print(f"[ANT NEURO CONNECT] Sample rate: {self.sample_rate} Hz")
            print(f"✓ Connected to demo device: {device_serial}")
            print(f"{'='*60}\n")
            return True
        
        # Try EDI2 first (modern API, no power blocking)
        if self.use_edi2 and EDI2_AVAILABLE and 'EDI2' in str(device_serial) or self.edi2_client is not None:
            try:
                print(f"[ANT NEURO CONNECT] Using EDI2 gRPC API...")
                if self.edi2_client is None:
                    self.edi2_client = EDI2Client()
                
                # Extract actual serial if prefixed
                actual_serial = device_serial.replace('EDI2-', '') if device_serial.startswith('EDI2-') else device_serial
                
                if self.edi2_client.connect(actual_serial):
                    self.is_connected = True
                    self.use_edi2 = True
                    self.channel_count = self.edi2_client.get_channel_count()
                    
                    # Get power state
                    power = self.edi2_client.get_power_state()
                    print(f"[ANT NEURO CONNECT] Mode: EDI2 gRPC (REAL DEVICE)")
                    print(f"[ANT NEURO CONNECT] Channels: {self.channel_count}")
                    print(f"[ANT NEURO CONNECT] Sample rate: {self.sample_rate} Hz")
                    print(f"[ANT NEURO CONNECT] Battery: {power.get('battery_level', 'N/A')}%, PowerOn: {power.get('is_power_on', 'N/A')}")
                    print(f"✓ Connected via EDI2 to: {device_serial}")
                    print(f"{'='*60}\n")
                    return True
                else:
                    print(f"[ANT NEURO CONNECT] EDI2 connection failed, trying eego SDK...")
            except Exception as e:
                print(f"[ANT NEURO CONNECT] EDI2 error: {e}")
        
        # Fallback to eego SDK
        if EEGO_SDK_AVAILABLE:
            try:
                if self.factory is None:
                    self.factory = eego_sdk.factory()
                    print(f"[ANT NEURO CONNECT] eego SDK factory initialized")
                
                amplifiers = self.factory.getAmplifiers()
                print(f"[ANT NEURO CONNECT] Found {len(amplifiers)} amplifier(s)")
                
                for amp in amplifiers:
                    if amp.getSerial() == device_serial:
                        self.amplifier = amp
                        self.is_connected = True
                        self.use_edi2 = False
                        self.channel_count = 64
                        print(f"[ANT NEURO CONNECT] Mode: eego SDK (REAL DEVICE)")
                        print(f"[ANT NEURO CONNECT] Channels: {self.channel_count}")
                        print(f"[ANT NEURO CONNECT] Sample rate: {self.sample_rate} Hz")
                        print(f"✓ Connected via eego SDK to: {device_serial}")
                        print(f"{'='*60}\n")
                        return True
                
                print(f"[ANT NEURO CONNECT] ERROR: Device {device_serial} not found")
            except Exception as e:
                print(f"[ANT NEURO CONNECT] eego SDK error: {e}")
        
        print(f"[ANT NEURO CONNECT] ERROR: Could not connect to {device_serial}")
        print(f"{'='*60}\n")
        return False
    
    def disconnect(self):
        """Disconnect from the amplifier"""
        self.stop_streaming()
        
        # Disconnect EDI2
        if self.edi2_client:
            try:
                self.edi2_client.disconnect()
            except:
                pass
            self.edi2_client = None
        
        # Disconnect eego SDK
        if self.amplifier:
            self.amplifier = None
        
        self.is_connected = False
        print("Disconnected from ANT Neuro amplifier")
    
    def start_streaming(self, sample_rate: int = 512) -> bool:
        """Start EEG data streaming"""
        if not self.is_connected:
            print(f"[ANT NEURO STREAM] ERROR: Device not connected, cannot start streaming")
            return False
        
        self.sample_rate = sample_rate
        self.stop_thread_flag = False
        print(f"\n{'='*60}")
        print(f"[ANT NEURO STREAM] Starting data stream at {sample_rate} Hz")
        
        # Demo mode
        if self.device_serial == 'DEMO-001':
            print(f"[ANT NEURO STREAM] Stream mode: DEMO (synthetic EEG)")
            print(f"[ANT NEURO STREAM] Generating: Alpha (10Hz) + Theta (6Hz) + Beta (20Hz) + Noise")
            print(f"[ANT NEURO STREAM] Buffer size: {self.live_data_buffer.maxlen} samples")
            self.stream_thread = threading.Thread(target=self._demo_stream_loop)
            self.stream_thread.daemon = True
            self.stream_thread.start()
            self.is_streaming = True
            print(f"✓ Demo streaming started successfully")
            print(f"{'='*60}\n")
            return True
        
        # EDI2 gRPC streaming (preferred - no power blocking)
        if self.use_edi2 and self.edi2_client:
            try:
                print(f"[ANT NEURO STREAM] Stream mode: EDI2 gRPC (REAL DEVICE)")
                
                # Set up data callback to populate buffers
                def on_data(data):
                    for sample in data:
                        # Truncate to 64 EEG channels (device sends 88: 64 EEG + 24 bipolar)
                        eeg_sample = sample[:64] if len(sample) > 64 else sample
                        # Add Fz (channel 0) to single-channel buffer for compatibility
                        self.live_data_buffer.append(eeg_sample[0])
                        # Add full 64-ch EEG sample to multichannel buffer
                        self.multichannel_buffer.append(eeg_sample)
                
                self.edi2_client.set_data_callback(on_data)
                
                if self.edi2_client.start_streaming(sample_rate=float(sample_rate)):
                    self.is_streaming = True
                    print(f"[ANT NEURO STREAM] Buffer size: {self.live_data_buffer.maxlen} samples")
                    print(f"✓ EDI2 streaming started successfully")
                    print(f"{'='*60}\n")
                    return True
                else:
                    print(f"[ANT NEURO STREAM] EDI2 start_streaming returned False")
            except Exception as e:
                print(f"[ANT NEURO STREAM] EDI2 error: {e}")
                import traceback
                traceback.print_exc()
        
        # Fallback to eego SDK
        if EEGO_SDK_AVAILABLE and self.amplifier:
            try:
                print(f"[ANT NEURO STREAM] Stream mode: eego SDK (REAL DEVICE)")
                self.stream = self.amplifier.OpenEegStream(sample_rate)
                print(f"[ANT NEURO STREAM] eego stream opened")
                print(f"[ANT NEURO STREAM] Buffer size: {self.live_data_buffer.maxlen} samples")
                
                self.stream_thread = threading.Thread(target=self._stream_loop)
                self.stream_thread.daemon = True
                self.stream_thread.start()
                self.is_streaming = True
                print(f"✓ eego SDK streaming started successfully")
                print(f"{'='*60}\n")
                return True
            except Exception as e:
                print(f"[ANT NEURO STREAM] eego SDK error: {e}")
        
        print(f"[ANT NEURO STREAM] ERROR: Could not start streaming")
        print(f"{'='*60}\n")
        return False
    
    def stop_streaming(self):
        """Stop EEG data streaming"""
        self.stop_thread_flag = True
        self.is_streaming = False
        
        # Stop EDI2 streaming
        if self.use_edi2 and self.edi2_client:
            try:
                self.edi2_client.stop_streaming()
            except:
                pass
        
        # Stop thread
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=2)
        
        # Stop eego SDK stream
        if self.stream:
            try:
                self.stream = None
            except Exception:
                pass
    
    def _stream_loop(self):
        """Main streaming loop for real device"""
        while not self.stop_thread_flag and self.stream:
            try:
                buffer = self.stream.getData()
                if buffer:
                    data = np.array(buffer.getData())
                    # Reshape to channels x samples
                    samples = data.reshape(-1, self.channel_count)
                    
                    # Truncate to 64 EEG channels (device may send 88: 64 EEG + 24 bipolar)
                    eeg_channels = 64
                    eeg_samples = samples[:, :eeg_channels] if samples.shape[1] > eeg_channels else samples
                    
                    for sample in eeg_samples:
                        # Add Fz (channel 0) to single-channel buffer for compatibility
                        self.live_data_buffer.append(sample[0])
                        # Add full 64-ch EEG sample to multichannel buffer
                        self.multichannel_buffer.append(sample)
                
                time.sleep(0.01)  # 10ms polling
            except Exception as e:
                print(f"Streaming error: {e}")
                break
    
    def _demo_stream_loop(self):
        """Demo streaming loop with synthetic EEG"""
        t = 0
        sample_count = 0
        last_log_time = time.time()
        
        print(f"[ANT NEURO DEMO STREAM] Loop started, generating synthetic data...")
        
        while not self.stop_thread_flag:
            # Generate synthetic EEG for 64 channels
            sample = np.zeros(self.channel_count)
            
            for ch in range(self.channel_count):
                # Alpha wave (10 Hz) + noise
                alpha = 30 * np.sin(2 * np.pi * 10 * t + ch * 0.1)
                # Theta wave (6 Hz)
                theta = 15 * np.sin(2 * np.pi * 6 * t + ch * 0.05)
                # Beta wave (20 Hz)
                beta = 10 * np.sin(2 * np.pi * 20 * t + ch * 0.02)
                # Noise
                noise = np.random.randn() * 5
                
                sample[ch] = alpha + theta + beta + noise
            
            self.live_data_buffer.append(sample[0])  # Fz for single-channel
            self.multichannel_buffer.append(sample)
            
            sample_count += 1
            
            # Log every 5 seconds
            if time.time() - last_log_time >= 5.0:
                print(f"[ANT NEURO DEMO STREAM] Generated {sample_count} samples, buffer: {len(self.live_data_buffer)}/{self.live_data_buffer.maxlen}, Fz amplitude: {sample[0]:.2f}µV")
                sample_count = 0
                last_log_time = time.time()
            
            t += 1 / self.sample_rate
            time.sleep(1 / self.sample_rate)
        
        print(f"[ANT NEURO DEMO STREAM] Loop stopped")


# Global device manager instance
ANT = AntNeuroDeviceManager()


def cleanup_and_quit():
    """Properly cleanup device connections and quit"""
    from PySide6.QtWidgets import QApplication
    
    try:
        print("Cleanup: Stopping ANT Neuro stream...")
        ANT.stop_streaming()
        ANT.disconnect()
    except Exception as e:
        print(f"Warning: Error during cleanup: {e}")
    
    QApplication.quit()


# ============================================================================
# Signal Quality Assessment (from BrainLink)
# ============================================================================

def compute_psd(data, fs):
    """Compute Power Spectral Density using Welch's method."""
    from scipy import signal
    freqs, psd = signal.welch(data, fs=fs, nperseg=min(256, len(data)))
    return freqs, psd


def assess_eeg_signal_quality(data_window, fs=512):
    """Professional multi-metric EEG signal quality assessment."""
    arr = np.array(data_window)
    details = {}
    
    if arr.size < 256:
        return 0, "insufficient_data", {"reason": "need more samples"}
    
    arr_std = np.std(arr)
    arr_mean = np.mean(arr)
    arr_max = np.max(np.abs(arr))
    
    details['std'] = float(arr_std)
    details['mean'] = float(arr_mean)
    details['max_amplitude'] = float(arr_max)
    
    if arr_std < 2.0:
        return 10, "not_worn", details
    
    try:
        freqs, psd = compute_psd(arr, fs)
        total_power = np.sum(psd) + 1e-12
        
        idx_delta = (freqs >= 0.5) & (freqs <= 4)
        idx_theta = (freqs >= 4) & (freqs <= 8)
        idx_alpha = (freqs >= 8) & (freqs <= 13)
        idx_low_freq = (freqs >= 0.5) & (freqs <= 8)
        idx_high_freq = freqs >= 30
        
        delta_power = np.sum(psd[idx_delta])
        theta_power = np.sum(psd[idx_theta])
        alpha_power = np.sum(psd[idx_alpha])
        low_freq_power = np.sum(psd[idx_low_freq])
        high_freq_power = np.sum(psd[idx_high_freq])
        
        delta_ratio = delta_power / total_power
        theta_ratio = theta_power / total_power
        alpha_ratio = alpha_power / total_power
        low_freq_ratio = low_freq_power / total_power
        high_freq_ratio = high_freq_power / total_power
        
        details['delta_ratio'] = float(delta_ratio)
        details['theta_ratio'] = float(theta_ratio)
        details['alpha_ratio'] = float(alpha_ratio)
        details['low_freq_ratio'] = float(low_freq_ratio)
        details['high_freq_ratio'] = float(high_freq_ratio)
        
        low_freq_dominance = delta_ratio + theta_ratio
        details['low_freq_dominance'] = float(low_freq_dominance)
        
        try:
            valid_idx = (freqs >= 1) & (freqs <= 40) & (psd > 0)
            if np.sum(valid_idx) > 10:
                log_freqs = np.log10(freqs[valid_idx])
                log_psd = np.log10(psd[valid_idx])
                slope, _ = np.polyfit(log_freqs, log_psd, 1)
                details['spectral_slope'] = float(slope)
            else:
                slope = 0
                details['spectral_slope'] = 0.0
        except Exception:
            slope = 0
            details['spectral_slope'] = 0.0
        
        if low_freq_dominance < 0.30:
            details['not_worn_reason'] = 'low_freq_too_weak'
            return 20, "not_worn", details
        
        if slope > -0.3:
            details['not_worn_reason'] = 'flat_spectrum'
            return 25, "not_worn", details
        
        if high_freq_ratio > 0.50:
            details['not_worn_reason'] = 'high_freq_dominant'
            return 30, "not_worn", details
        
    except Exception as e:
        details['psd_error'] = str(e)
        return 40, "analysis_error", details
    
    if arr_std > 500:
        return 15, "severe_artifacts", details
    
    from scipy.stats import kurtosis
    kurt = kurtosis(arr, fisher=True)
    details['kurtosis'] = float(kurt)
    
    quality_score = 100
    
    if low_freq_dominance < 0.40:
        quality_score -= 15
    if slope > -0.5:
        quality_score -= 10
    if high_freq_ratio > 0.30:
        quality_score -= 15
    if abs(kurt) > 5:
        quality_score -= 10
    if alpha_ratio > 0.15:
        quality_score += 5
    
    quality_score = max(0, min(100, quality_score))
    
    if quality_score >= 70:
        status = "good"
    elif quality_score >= 50:
        status = "acceptable"
    else:
        status = "poor"
    
    return quality_score, status, details


# ============================================================================
# MULTI-CHANNEL SIGNAL QUALITY ASSESSMENT (for 64-channel systems)
# ============================================================================

def assess_multichannel_signal_quality(multichannel_data, fs=500, channel_names=None):
    """
    Comprehensive multi-channel EEG signal quality assessment for 64-channel systems.
    
    Returns:
    --------
    overall_score : float (0-100)
    overall_status : str ('good', 'acceptable', 'poor', 'cap_issue')
    details : dict with per-channel and regional quality metrics
    """
    from scipy import signal as scipy_signal
    from scipy.stats import kurtosis
    
    # Default 64-channel names
    if channel_names is None:
        channel_names = [
            'Fp1', 'Fp2', 'F7', 'F3', 'Fz', 'F4', 'F8',
            'FC5', 'FC1', 'FC2', 'FC6',
            'T7', 'C3', 'Cz', 'C4', 'T8',
            'CP5', 'CP1', 'CP2', 'CP6',
            'P7', 'P3', 'Pz', 'P4', 'P8',
            'PO7', 'PO3', 'POz', 'PO4', 'PO8',
            'O1', 'Oz', 'O2',
            'AF7', 'AF3', 'AF4', 'AF8',
            'F5', 'F1', 'F2', 'F6',
            'FT7', 'FT8', 'FC3', 'FC4',
            'C5', 'C1', 'C2', 'C6',
            'TP7', 'TP8', 'CP3', 'CP4',
            'P5', 'P1', 'P2', 'P6',
            'PO5', 'PO6', 'CB1', 'CB2',
            'GND', 'REF', 'M1', 'M2'
        ]
    
    # Regional groupings
    REGIONS = {
        'frontal': ['Fp1', 'Fp2', 'F7', 'F3', 'Fz', 'F4', 'F8', 'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6'],
        'central': ['FC5', 'FC1', 'FC2', 'FC6', 'C3', 'Cz', 'C4', 'FC3', 'FC4', 'C5', 'C1', 'C2', 'C6'],
        'parietal': ['CP5', 'CP1', 'CP2', 'CP6', 'P7', 'P3', 'Pz', 'P4', 'P8', 'CP3', 'CP4', 'P5', 'P1', 'P2', 'P6'],
        'occipital': ['PO7', 'PO3', 'POz', 'PO4', 'PO8', 'O1', 'Oz', 'O2', 'PO5', 'PO6'],
        'temporal': ['T7', 'T8', 'FT7', 'FT8', 'TP7', 'TP8']
    }
    
    data = np.array(multichannel_data)
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    
    if data.shape[0] < data.shape[1] and data.shape[0] <= 128:
        data = data.T
    
    n_samples, n_channels = data.shape
    
    if len(channel_names) > n_channels:
        channel_names = channel_names[:n_channels]
    elif len(channel_names) < n_channels:
        channel_names = channel_names + [f'Ch{i}' for i in range(len(channel_names), n_channels)]
    
    details = {
        'n_channels': n_channels,
        'n_samples': n_samples,
        'per_channel_scores': {},
        'per_channel_status': {},
        'bad_channels': [],
        'flat_channels': [],
        'noisy_channels': [],
        'regional_scores': {},
        'issues': []
    }
    
    if n_samples < 256:
        return 0, "insufficient_data", details
    
    # Per-channel assessment
    channel_scores = []
    for ch_idx in range(n_channels):
        ch_name = channel_names[ch_idx]
        ch_data = data[:, ch_idx]
        ch_score = 100
        
        ch_std = np.std(ch_data)
        if ch_std < 1.0:
            ch_score = 5
            details['flat_channels'].append(ch_name)
        
        ch_max = np.max(np.abs(ch_data))
        if ch_max > 500:
            ch_score = min(ch_score, 20)
            details['bad_channels'].append(ch_name)
        
        if ch_std >= 1.0:
            try:
                freqs, psd = scipy_signal.welch(ch_data, fs=fs, nperseg=min(256, n_samples))
                total_power = np.sum(psd) + 1e-12
                
                idx_low = (freqs >= 0.5) & (freqs <= 8)
                idx_high = freqs >= 30
                
                low_freq_ratio = np.sum(psd[idx_low]) / total_power
                high_freq_ratio = np.sum(psd[idx_high]) / total_power
                
                if low_freq_ratio < 0.25:
                    ch_score -= 20
                if high_freq_ratio > 0.40:
                    ch_score -= 15
                    if ch_name not in details['noisy_channels']:
                        details['noisy_channels'].append(ch_name)
            except Exception:
                ch_score -= 10
        
        ch_score = max(0, min(100, ch_score))
        
        if ch_score < 30 and ch_name not in details['bad_channels']:
            details['bad_channels'].append(ch_name)
        
        details['per_channel_scores'][ch_name] = ch_score
        details['per_channel_status'][ch_name] = "good" if ch_score >= 70 else "acceptable" if ch_score >= 50 else "poor"
        channel_scores.append(ch_score)
    
    # Regional assessment
    for region_name, region_channels in REGIONS.items():
        region_scores = [details['per_channel_scores'][ch] for ch in region_channels if ch in details['per_channel_scores']]
        if region_scores:
            details['regional_scores'][region_name] = float(np.mean(region_scores))
    
    # Overall calculation
    if channel_scores:
        weights = [max(0.1, s/100) for s in channel_scores]
        overall_score = np.average(channel_scores, weights=weights)
    else:
        overall_score = 0
    
    bad_ratio = len(details['bad_channels']) / n_channels
    flat_ratio = len(details['flat_channels']) / n_channels
    
    if bad_ratio > 0.3:
        overall_score *= 0.6
    elif bad_ratio > 0.15:
        overall_score *= 0.8
    
    if flat_ratio > 0.5:
        overall_score = min(overall_score, 15)
    elif flat_ratio > 0.2:
        overall_score *= 0.7
    
    overall_score = max(0, min(100, overall_score))
    
    if flat_ratio > 0.5:
        overall_status = "cap_not_worn"
    elif overall_score >= 70:
        overall_status = "good"
    elif overall_score >= 50:
        overall_status = "acceptable"
    elif overall_score >= 30:
        overall_status = "poor"
    else:
        overall_status = "cap_issue"
    
    details['overall_score'] = float(overall_score)
    details['good_channel_count'] = sum(1 for s in channel_scores if s >= 70)
    details['poor_channel_count'] = sum(1 for s in channel_scores if s < 50)
    
    print(f"[MULTI-CH QUALITY] Overall: {overall_score:.1f} ({overall_status}) | Good: {details['good_channel_count']}/{n_channels}")
    
    return overall_score, overall_status, details


# ============================================================================
# RESOURCE PATH HELPER
# ============================================================================

def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)


# ============================================================================
# WINDOW ICON HELPER
# ============================================================================

def set_window_icon(dialog: QDialog) -> None:
    """Set the application icon for a dialog window"""
    try:
        icon_path = resource_path(os.path.join('assets', 'favicon.ico'))
        if os.path.isfile(icon_path):
            dialog.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass


# ============================================================================
# MODERN DIALOG STYLING
# ============================================================================

MODERN_DIALOG_STYLESHEET = """
QDialog {
    background:#f8fafc;
}
QLabel#DialogTitle {
    font-size:18px;
    font-weight:600;
    color:#1f2937;
}
QLabel#DialogSubtitle {
    font-size:13px;
    color:#475569;
}
QLabel#DialogSectionTitle,
QLabel#DialogSectionLabel {
    font-size:13px;
    font-weight:600;
    color:#1f2937;
}
QFrame#DialogCard {
    background:#ffffff;
    border:1px solid #e2e8f0;
    border-radius:12px;
}
QLineEdit,
QComboBox,
QTextEdit {
    font-size:13px;
    padding:8px 10px;
    border:1px solid #cbd5e1;
    border-radius:8px;
    background:#f8fafc;
    color:#1f2937;
}
QLineEdit:focus,
QComboBox:focus,
QTextEdit:focus {
    border-color:#3b82f6;
    background:#ffffff;
}
QCheckBox,
QRadioButton {
    font-size:13px;
    color:#1f2937;
    spacing:8px;
}
QPushButton {
    background-color:#2563eb;
    color:#ffffff;
    border-radius:8px;
    padding:8px 18px;
    font-size:13px;
    border:0;
}
QPushButton:hover {
    background-color:#1d4ed8;
}
QPushButton:pressed {
    background-color:#1e40af;
}
QPushButton:disabled {
    background-color:#dbeafe;
    color:#64748b;
}
"""


def apply_modern_dialog_theme(dialog: QDialog) -> None:
    """Apply the refreshed light theme to modal dialogs"""
    dialog.setStyleSheet(MODERN_DIALOG_STYLESHEET)


# ============================================================================
# STATUS BAR WIDGET
# ============================================================================

class MindLinkStatusBar(QFrame):
    """Status bar showing EEG signal and feature extraction status"""
    
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        
        self.setStyleSheet("""
            QFrame {
                background: #1e40af;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)
        
        # Device label
        self.device_label = QLabel("ANT Neuro 64-Ch")
        self.device_label.setStyleSheet("color: #93c5fd; font-weight: 600;")
        layout.addWidget(self.device_label)
        
        # Separator
        sep1 = QLabel("|")
        layout.addWidget(sep1)
        
        # EEG Signal status
        self.eeg_status = QLabel("EEG: Disconnected")
        layout.addWidget(self.eeg_status)
        
        # Separator
        sep2 = QLabel("|")
        layout.addWidget(sep2)
        
        # Signal quality indicator
        self.signal_quality = QLabel("Signal: Checking...")
        layout.addWidget(self.signal_quality)
        
        layout.addStretch()
        
        # Help button
        self.help_button = QPushButton("❓ Help")
        self.help_button.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: #ffffff;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 600;
                border: 0;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        self.help_button.clicked.connect(self.show_help_dialog)
        layout.addWidget(self.help_button)
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(500)
        
        self.help_dialog = None
    
    def update_status(self):
        """Update the status display"""
        try:
            if ANT.is_streaming and len(ANT.live_data_buffer) > 0:
                self.eeg_status.setText("EEG: ✓ Connected")
                self.eeg_status.setStyleSheet("color: #10b981; font-weight: 700;")
            else:
                self.eeg_status.setText("EEG: ✗ No Signal")
                self.eeg_status.setStyleSheet("color: #fbbf24; font-weight: 700;")
            
            if len(ANT.live_data_buffer) >= 512:
                recent_data = np.array(list(ANT.live_data_buffer)[-512:])
                quality_score, status, details = assess_eeg_signal_quality(recent_data, fs=512)
                
                if status == "not_worn":
                    self.signal_quality.setText("Signal: ⚠ Noisy")
                    self.signal_quality.setStyleSheet("color: #f59e0b; font-weight: 700;")
                else:
                    self.signal_quality.setText("Signal: ✓ Good")
                    self.signal_quality.setStyleSheet("color: #10b981; font-weight: 700;")
            else:
                self.signal_quality.setText("Signal: Waiting...")
                self.signal_quality.setStyleSheet("color: #94a3b8; font-weight: 700;")
        except Exception:
            pass
    
    def show_help_dialog(self):
        """Show help dialog"""
        if self.help_dialog is None or not self.help_dialog.isVisible():
            self.help_dialog = HelpDialog(parent=self)
            self.help_dialog.show()
        else:
            self.help_dialog.raise_()
            self.help_dialog.activateWindow()
    
    def cleanup(self):
        """Stop the update timer"""
        self.update_timer.stop()
        if self.help_dialog and self.help_dialog.isVisible():
            self.help_dialog.close()


def add_status_bar_to_dialog(dialog: QDialog, main_window) -> MindLinkStatusBar:
    """Helper to add MindLink status bar to any dialog"""
    main_layout = dialog.layout()
    if main_layout:
        status_bar = MindLinkStatusBar(main_window)
        main_layout.insertWidget(0, status_bar)
        return status_bar
    return None


def add_help_button_to_dialog(dialog: QDialog) -> QPushButton:
    """Helper to add a simple Help button to early workflow dialogs"""
    main_layout = dialog.layout()
    if main_layout:
        help_button = QPushButton("❓ Help")
        help_button.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: #ffffff;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
                border: 0;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        
        help_container = QWidget()
        help_layout = QHBoxLayout(help_container)
        help_layout.setContentsMargins(0, 0, 0, 8)
        help_layout.addStretch()
        help_layout.addWidget(help_button)
        
        help_button.help_dialog = None
        
        def show_help():
            if help_button.help_dialog is None or not help_button.help_dialog.isVisible():
                help_button.help_dialog = HelpDialog(dialog)
                help_button.help_dialog.show()
            else:
                help_button.help_dialog.raise_()
                help_button.help_dialog.activateWindow()
        
        help_button.clicked.connect(show_help)
        main_layout.insertWidget(0, help_container)
        return help_button
    return None


# ============================================================================
# HELP DIALOG
# ============================================================================

class HelpDialog(QDialog):
    """Dialog displaying the user manual"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ANT Neuro Analyzer - User Manual")
        self.setModal(False)
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        
        set_window_icon(self)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(40)
        header.setStyleSheet("QFrame { background: #0ea5e9; padding: 0; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        
        title = QLabel("📖 ANT Neuro 64-Channel EEG Analyzer - User Manual")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #ffffff;")
        header_layout.addWidget(title)
        
        layout.addWidget(header)
        
        # Content
        content = QTextEdit()
        content.setReadOnly(True)
        content.setStyleSheet("""
            QTextEdit {
                background: #ffffff;
                border: none;
                padding: 20px;
                font-size: 13px;
                color: #1f2937;
            }
        """)
        content.setHtml("""
            <h2>ANT Neuro 64-Channel EEG Analyzer</h2>
            
            <h3>Getting Started</h3>
            <p>This application provides professional EEG analysis using the ANT Neuro eego 64-channel system.
            The workflow is identical to the MindLink Analyzer but with enhanced multichannel capabilities.</p>
            
            <h3>Workflow Steps</h3>
            <ol>
                <li><b>OS Selection</b> - Confirm your operating system</li>
                <li><b>Region Selection</b> - Choose your Mindspeller account region</li>
                <li><b>Partner ID</b> - Enter your partner identification (if applicable)</li>
                <li><b>Login</b> - Authenticate with your Mindspeller credentials</li>
                <li><b>Pathway Selection</b> - Choose your analysis pathway</li>
                <li><b>Live EEG</b> - Verify signal quality and connection</li>
                <li><b>Calibration</b> - Perform eyes-closed baseline recording</li>
                <li><b>Task Selection</b> - Choose and execute cognitive tasks</li>
                <li><b>Analysis</b> - View comprehensive results and reports</li>
            </ol>
            
            <h3>Device Setup</h3>
            <p>Ensure your ANT Neuro eego amplifier is:</p>
            <ul>
                <li>Connected via USB to your computer</li>
                <li>Properly grounded and electrodes applied</li>
                <li>Impedances checked (preferably < 10 kΩ)</li>
            </ul>
            
            <h3>Signal Quality</h3>
            <p>The status bar shows real-time signal quality. For best results:</p>
            <ul>
                <li>Ensure good electrode contact</li>
                <li>Minimize movement during recording</li>
                <li>Reduce electrical interference sources</li>
            </ul>
            
            <h3>Support</h3>
            <p>For technical support, contact your Mindspeller representative.</p>
        """)
        layout.addWidget(content)
        
        # Footer
        footer = QFrame()
        footer.setFixedHeight(50)
        footer.setStyleSheet("QFrame { background: #f8fafc; border-top: 1px solid #e2e8f0; }")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 8, 16, 8)
        footer_layout.addStretch()
        
        close_button = QPushButton("✕ Close")
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: #ffffff;
                border-radius: 8px;
                padding: 10px 28px;
                font-size: 14px;
                font-weight: 600;
                border: 0;
            }
            QPushButton:hover { background-color: #0284c7; }
        """)
        close_button.clicked.connect(self.close)
        footer_layout.addWidget(close_button)
        
        layout.addWidget(footer)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)


# ============================================================================
# WORKFLOW STEP ENUM
# ============================================================================

class WorkflowStep:
    OS_SELECTION = 0
    ENVIRONMENT_SELECTION = 1
    PARTNER_ID = 2
    LOGIN = 3
    PATHWAY_SELECTION = 4
    LIVE_EEG = 5
    CALIBRATION = 6
    TASK_SELECTION = 7
    MULTI_TASK_ANALYSIS = 8


# ============================================================================
# WORKFLOW MANAGER
# ============================================================================

class WorkflowManager:
    """Manages the sequential workflow state and navigation"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.current_step = WorkflowStep.OS_SELECTION
        self.step_history = []
        self.current_dialog: Optional[QDialog] = None
    
    def go_to_step(self, step: int, from_back: bool = False):
        """Navigate to a specific workflow step"""
        if not from_back:
            self.step_history.append(self.current_step)
        
        if self.current_dialog and self.current_dialog.isVisible():
            self.current_dialog.close()
            self.current_dialog = None
        
        self.current_step = step
        
        if step == WorkflowStep.OS_SELECTION:
            self._show_os_selection()
        elif step == WorkflowStep.ENVIRONMENT_SELECTION:
            self._show_environment_selection()
        elif step == WorkflowStep.PARTNER_ID:
            self._show_partner_id()
        elif step == WorkflowStep.LOGIN:
            self._show_login()
        elif step == WorkflowStep.PATHWAY_SELECTION:
            self._show_pathway_selection()
        elif step == WorkflowStep.LIVE_EEG:
            self._show_live_eeg()
        elif step == WorkflowStep.CALIBRATION:
            self._show_calibration()
        elif step == WorkflowStep.TASK_SELECTION:
            self._show_task_selection()
        elif step == WorkflowStep.MULTI_TASK_ANALYSIS:
            self._show_multi_task_analysis()
    
    def go_back(self):
        """Navigate to previous step"""
        if self.step_history:
            previous_step = self.step_history.pop()
            self.go_to_step(previous_step, from_back=True)
    
    def can_go_back(self) -> bool:
        """Check if back navigation is available"""
        return len(self.step_history) > 0
    
    def _show_os_selection(self):
        dialog = OSSelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_environment_selection(self):
        dialog = EnvironmentSelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_partner_id(self):
        dialog = PartnerIDDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_login(self):
        dialog = LoginDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_pathway_selection(self):
        dialog = PathwaySelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_live_eeg(self):
        dialog = LiveEEGDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_calibration(self):
        dialog = CalibrationDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_task_selection(self):
        dialog = TaskSelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_multi_task_analysis(self):
        dialog = MultiTaskAnalysisDialog(self)
        self.current_dialog = dialog
        dialog.show()


# ============================================================================
# STEP 1: OS SELECTION
# ============================================================================

class OSSelectionDialog(QDialog):
    """Step 1: Select operating system"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Operating System")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(400)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        # Detect default OS
        if sys.platform.startswith("win"):
            default_os = "Windows"
        elif sys.platform.startswith("darwin"):
            default_os = "macOS"
        else:
            default_os = "Windows"
        
        # UI Elements
        title_label = QLabel("Welcome to ANT Neuro 64-Channel Analyzer")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 1 of 9: Choose your Operating System")
        subtitle_label.setObjectName("DialogSubtitle")
        
        card = QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        prompt_label = QLabel("Select your OS:")
        prompt_label.setObjectName("DialogSectionTitle")
        
        self.radio_windows = QRadioButton("Windows")
        self.radio_macos = QRadioButton("macOS")
        
        if default_os == "Windows":
            self.radio_windows.setChecked(True)
        else:
            self.radio_macos.setChecked(True)
        
        card_layout.addWidget(prompt_label)
        card_layout.addWidget(self.radio_windows)
        card_layout.addWidget(self.radio_macos)
        card_layout.addStretch()
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        add_help_button_to_dialog(self)
    
    def closeEvent(self, event):
        """Handle dialog close"""
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_next(self):
        """Save OS selection and proceed"""
        selected_os = "Windows" if self.radio_windows.isChecked() else "macOS"
        self.workflow.main_window.user_os = selected_os
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.ENVIRONMENT_SELECTION))


# ============================================================================
# STEP 2: ENVIRONMENT SELECTION
# ============================================================================

class EnvironmentSelectionDialog(QDialog):
    """Step 2: Select region"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Region Selection")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(450)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        # UI Elements
        title_label = QLabel("Select Region")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 2 of 9: Choose your region")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Environment selection card
        env_card = QFrame()
        env_card.setObjectName("DialogCard")
        env_layout = QVBoxLayout(env_card)
        env_layout.setContentsMargins(16, 16, 16, 16)
        env_layout.setSpacing(10)
        
        env_label = QLabel("Region:")
        env_label.setObjectName("DialogSectionTitle")
        
        self.env_combo = QComboBox()
        self.env_combo.addItems(["English (en)", "Dutch (nl)", "Local"])
        
        warning_label = QLabel("⚠️ Please make sure the region selected is the region where the user has created their Mindspeller account")
        warning_label.setStyleSheet("font-size: 12px; color: #f59e0b; padding: 8px; background: #fffbeb; border-radius: 6px; border-left: 3px solid #f59e0b;")
        warning_label.setWordWrap(True)
        
        env_layout.addWidget(env_label)
        env_layout.addWidget(self.env_combo)
        env_layout.addWidget(warning_label)
        
        # Device scanning card
        device_card = QFrame()
        device_card.setObjectName("DialogCard")
        device_layout = QVBoxLayout(device_card)
        device_layout.setContentsMargins(16, 16, 16, 16)
        device_layout.setSpacing(10)
        
        device_label = QLabel("ANT Neuro Device:")
        device_label.setObjectName("DialogSectionTitle")
        
        self.device_combo = QComboBox()
        self.scan_button = QPushButton("🔍 Scan for Devices")
        self.scan_button.clicked.connect(self.scan_devices)
        
        device_layout.addWidget(device_label)
        device_layout.addWidget(self.device_combo)
        device_layout.addWidget(self.scan_button)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        nav_layout.addWidget(self.back_button)
        
        nav_layout.addStretch()
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(env_card)
        layout.addWidget(device_card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        add_help_button_to_dialog(self)
        
        # Initial device scan
        QTimer.singleShot(500, self.scan_devices)
    
    def closeEvent(self, event):
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def scan_devices(self):
        """Scan for ANT Neuro devices"""
        self.device_combo.clear()
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Scanning...")
        
        QtWidgets.QApplication.processEvents()
        
        devices = ANT.scan_for_devices()
        
        for device in devices:
            self.device_combo.addItem(f"{device['serial']} ({device['type']})", device['serial'])
        
        self.scan_button.setEnabled(True)
        self.scan_button.setText("🔍 Scan for Devices")
    
    def on_back(self):
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        # Save environment
        env_text = self.env_combo.currentText()
        if "en" in env_text:
            env = "en"
        elif "nl" in env_text:
            env = "nl"
        else:
            env = "local"
        
        self.workflow.main_window.environment = env
        print(f"\n{'='*60}")
        print(f"[ENVIRONMENT SELECTION] Region selected: {env}")
        
        # Save selected device
        if self.device_combo.count() > 0:
            device_serial = self.device_combo.currentData()
            self.workflow.main_window.selected_device = device_serial
            print(f"[ENVIRONMENT SELECTION] ANT Neuro device selected: {device_serial}")
            print(f"[WORKFLOW] ANT Neuro path activated - will proceed to Partner ID → Login → Pathway → Live EEG")
        print(f"{'='*60}\n")
        
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.PARTNER_ID))


# ============================================================================
# STEP 3: PARTNER ID
# ============================================================================

class PartnerIDDialog(QDialog):
    """Step 3: Enter partner ID"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Partner ID")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(450)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        title_label = QLabel("Partner Identification")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 3 of 9: Enter partner ID (optional)")
        subtitle_label.setObjectName("DialogSubtitle")
        
        card = QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        partner_label = QLabel("Partner ID:")
        partner_label.setObjectName("DialogSectionTitle")
        
        self.partner_input = QLineEdit()
        self.partner_input.setPlaceholderText("Enter partner ID or leave empty")
        
        info_label = QLabel("ℹ️ If you don't have a partner ID, you can skip this step.")
        info_label.setStyleSheet("font-size: 11px; color: #64748b;")
        info_label.setWordWrap(True)
        
        card_layout.addWidget(partner_label)
        card_layout.addWidget(self.partner_input)
        card_layout.addWidget(info_label)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        nav_layout.addWidget(self.back_button)
        
        nav_layout.addStretch()
        
        self.skip_button = QPushButton("Skip")
        self.skip_button.setStyleSheet("""
            QPushButton {
                background-color: #64748b;
                color: #ffffff;
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 13px;
                border: 0;
            }
            QPushButton:hover { background-color: #475569; }
        """)
        self.skip_button.clicked.connect(self.on_skip)
        nav_layout.addWidget(self.skip_button)
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        add_help_button_to_dialog(self)
    
    def closeEvent(self, event):
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_back(self):
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_skip(self):
        self.workflow.main_window.partner_id = None
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.LOGIN))
    
    def on_next(self):
        partner_id = self.partner_input.text().strip()
        self.workflow.main_window.partner_id = partner_id if partner_id else None
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.LOGIN))


# ============================================================================
# STEP 4: LOGIN
# ============================================================================

class LoginDialog(QDialog):
    """Step 4: Login with credentials"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Login")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(450)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        # Load saved credentials
        self.settings = QSettings("Mindspeller", "AntNeuroAnalyzer")
        
        title_label = QLabel("Sign In to Connect")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 4 of 9: Enter your credentials")
        subtitle_label.setObjectName("DialogSubtitle")
        
        card = QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        
        # Email/Username
        email_label = QLabel("Email:")
        email_label.setObjectName("DialogSectionLabel")
        self.email_input = QLineEdit()
        self.email_input.setText(self.settings.value("username", ""))
        self.email_input.setPlaceholderText("you@example.com")
        
        # Password
        password_label = QLabel("Password:")
        password_label.setObjectName("DialogSectionLabel")
        
        password_container = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter your password")
        
        self.show_password_button = QPushButton("👁")
        self.show_password_button.setFixedWidth(40)
        self.show_password_button.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #1f2937;
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
                border: 0;
            }
            QPushButton:hover { background-color: #cbd5e1; }
        """)
        self.show_password_button.clicked.connect(self.toggle_password_visibility)
        
        password_container.addWidget(self.password_input)
        password_container.addWidget(self.show_password_button)
        
        # Remember me
        self.remember_check = QCheckBox("Remember email")
        self.remember_check.setChecked(self.settings.value("remember", False, type=bool))
        
        card_layout.addWidget(email_label)
        card_layout.addWidget(self.email_input)
        card_layout.addWidget(password_label)
        card_layout.addLayout(password_container)
        card_layout.addWidget(self.remember_check)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; color: #ef4444;")
        self.status_label.setWordWrap(True)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        nav_layout.addWidget(self.back_button)
        
        nav_layout.addStretch()
        
        self.login_button = QPushButton("Login →")
        self.login_button.clicked.connect(self.on_login)
        nav_layout.addWidget(self.login_button)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(card)
        layout.addWidget(self.status_label)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        add_help_button_to_dialog(self)
    
    def toggle_password_visibility(self):
        """Toggle password visibility"""
        if self.password_input.echoMode() == QLineEdit.Password:
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.show_password_button.setText("🔒")
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            self.show_password_button.setText("👁")
    
    def closeEvent(self, event):
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_back(self):
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_login(self):
        """Perform login - matches BrainLink protocol exactly"""
        username = self.email_input.text().strip()
        password = self.password_input.text()
        
        if not username or not password:
            self.status_label.setText("Please enter both email and password.")
            return
        
        self.login_button.setEnabled(False)
        self.back_button.setEnabled(False)
        self.login_button.setText("Connecting...")
        self.status_label.setText("Checking device connection...")
        QtWidgets.QApplication.processEvents()
        
        # First connect to ANT Neuro device
        selected_device = getattr(self.workflow.main_window, 'selected_device', 'DEMO-001')
        
        if not ANT.is_connected:
            if ANT.connect(selected_device):
                self.status_label.setText("Device connected. Authenticating...")
                QtWidgets.QApplication.processEvents()
            else:
                self.status_label.setText("Failed to connect to device.")
                self.status_label.setStyleSheet("font-size: 12px; color: #ef4444;")
                self.login_button.setEnabled(True)
                self.back_button.setEnabled(True)
                self.login_button.setText("Login →")
                return
        
        # Determine login URL based on environment
        env = getattr(self.workflow.main_window, 'environment', 'en')
        if env == "local":
            login_url = "http://127.0.0.1:5000/api/cas/token/login"
        else:
            login_url = f"https://{env}.mindspeller.com/api/cas/token/login"
        
        # Store login_url for later API calls
        self.login_url = login_url
        
        # Use 'username' field like BrainLink does (NOT 'email')
        login_payload = {
            "username": username,
            "password": password
        }
        
        print("\n" + "=" * 60)
        print(">>> LOGIN ATTEMPT <<<")
        print(f"URL: {login_url}")
        print(f"Username: {username}")
        print(f"Payload keys: {list(login_payload.keys())}")
        print("=" * 60 + "\n")
        
        try:
            # For local development, skip SSL verification
            is_local = "127.0.0.1" in login_url or "localhost" in login_url
            
            response = requests.post(
                login_url,
                json=login_payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
                verify=not is_local
            )
            
            print(f"Response Status: {response.status_code}")
            print(f"Response Body: {response.text[:500]}")
            
        except requests.exceptions.SSLError:
            print("SSL error, retrying without verification...")
            try:
                response = requests.post(
                    login_url,
                    json=login_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                    verify=False
                )
            except Exception as e:
                self.status_label.setText(f"Connection error: {e}")
                self.login_button.setEnabled(True)
                self.back_button.setEnabled(True)
                self.login_button.setText("Login →")
                return
        except requests.exceptions.ProxyError:
            print("Proxy error, retrying without proxy...")
            try:
                direct_session = requests.Session()
                direct_session.proxies = {}
                response = direct_session.post(
                    login_url,
                    json=login_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                    verify=True
                )
            except Exception as e:
                self.status_label.setText(f"Connection error: {e}")
                self.login_button.setEnabled(True)
                self.back_button.setEnabled(True)
                self.login_button.setText("Login →")
                return
        except Exception as e:
            self.status_label.setText(f"Connection error: {e}")
            self.login_button.setEnabled(True)
            self.back_button.setEnabled(True)
            self.login_button.setText("Login →")
            return
        
        if response.status_code == 200:
            data = response.json()
            jwt_token = data.get("x-jwt-access-token")
            hwid = data.get("hwid")
            
            if jwt_token:
                print("✓ Login successful. JWT token obtained.")
                
                # Save credentials
                settings = QSettings("Mindspeller", "AntNeuroAnalyzer")
                if self.remember_check.isChecked():
                    settings.setValue("username", username)
                    settings.setValue("remember", True)
                else:
                    settings.remove("username")
                    settings.setValue("remember", False)
                
                # Store auth info on main window
                self.workflow.main_window.jwt_token = jwt_token
                self.workflow.main_window.user_email = username
                self.workflow.main_window.user_data = data
                self.workflow.main_window.login_url = login_url
                
                if hwid:
                    print(f"✓ Hardware ID received: {hwid}")
                    self.workflow.main_window.hwid = hwid
                
                # Fetch user data from /api/cas/users/current_user
                self._fetch_user_data(jwt_token)
                
                # Start device streaming
                if not ANT.is_streaming:
                    ANT.start_streaming()
                
                self.status_label.setText("✓ Login successful!")
                self.status_label.setStyleSheet("font-size: 12px; color: #10b981; font-weight: 600;")
                
                # Auto-proceed after 1 second
                QTimer.singleShot(1000, self._proceed_to_next)
            else:
                self.status_label.setText("Login failed: No token in response")
                self.login_button.setEnabled(True)
                self.back_button.setEnabled(True)
                self.login_button.setText("Login →")
        else:
            try:
                error_msg = response.json().get("error", f"HTTP {response.status_code}")
            except Exception:
                error_msg = f"HTTP {response.status_code}"
            self.status_label.setText(f"Login failed: {error_msg}")
            self.login_button.setEnabled(True)
            self.back_button.setEnabled(True)
            self.login_button.setText("Login →")
    
    def _fetch_user_data(self, jwt_token):
        """Fetch user data from /api/cas/users/current_user endpoint"""
        try:
            # Use login URL base
            api_base = self.login_url.replace("/token/login", "")
            user_data_url = f"{api_base}/users/current_user"
            
            print(f"Fetching user data from: {user_data_url}")
            
            user_response = requests.get(
                user_data_url,
                headers={"X-Authorization": f"Bearer {jwt_token}"},
                timeout=10
            )
            
            if user_response.status_code == 200:
                response_json = user_response.json()
                print(f"User data received: {list(response_json.keys())}")
                
                # Store user data
                if 'userData' in response_json:
                    self.workflow.main_window.user_data = response_json['userData']
                else:
                    self.workflow.main_window.user_data = response_json
            else:
                print(f"User data fetch failed: {user_response.status_code}")
        except Exception as e:
            print(f"Error fetching user data: {e}")
    
    def _proceed_to_next(self):
        """Proceed to next step after successful login"""
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.PATHWAY_SELECTION))


# ============================================================================
# STEP 5: PATHWAY SELECTION
# ============================================================================

class PathwaySelectionDialog(QDialog):
    """Step 5: Select analysis pathway"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Pathway Selection")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(500)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        title_label = QLabel("Select Analysis Pathway")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 5 of 9: Choose your pathway")
        subtitle_label.setObjectName("DialogSubtitle")
        
        card = QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        
        pathway_label = QLabel("Available Pathways:")
        pathway_label.setObjectName("DialogSectionTitle")
        
        self.pathway_combo = QComboBox()
        self.pathway_combo.addItems([
            "Personal Pathway",
            "Connection",
            "Lifestyle",
            "Cognitive Assessment"
        ])
        
        description_label = QLabel(
            "Each pathway contains specific cognitive tasks designed to measure "
            "different aspects of brain activity and mental processing."
        )
        description_label.setStyleSheet("font-size: 12px; color: #64748b;")
        description_label.setWordWrap(True)
        
        card_layout.addWidget(pathway_label)
        card_layout.addWidget(self.pathway_combo)
        card_layout.addWidget(description_label)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        nav_layout.addWidget(self.back_button)
        
        nav_layout.addStretch()
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        add_help_button_to_dialog(self)
    
    def closeEvent(self, event):
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_back(self):
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        pathway = self.pathway_combo.currentText()
        self.workflow.main_window.selected_pathway = pathway
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.LIVE_EEG))


# ============================================================================
# STEP 6: LIVE EEG
# ============================================================================

class LiveEEGDialog(QDialog):
    """Step 6: Live EEG monitoring"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Live EEG")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(700, 500)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        title_label = QLabel("Live EEG Signal")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 6 of 9: Verify signal quality before calibration")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # EEG Plot
        plot_card = QFrame()
        plot_card.setObjectName("DialogCard")
        plot_layout = QVBoxLayout(plot_card)
        plot_layout.setContentsMargins(8, 8, 8, 8)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.setLabel('left', 'Amplitude', units='µV')
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.setTitle('Fz Channel (Reference)', color='k')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setYRange(-100, 100)
        self.plot_widget.setXRange(-5, 0)  # Fixed 5-second window for smooth scrolling
        self.plot_widget.enableAutoRange(axis='x', enable=False)  # Disable auto-ranging
        
        self.plot_curve = self.plot_widget.plot(pen=pg.mkPen(color='b', width=1.5))
        
        plot_layout.addWidget(self.plot_widget)
        
        # Signal quality indicator
        quality_card = QFrame()
        quality_card.setObjectName("DialogCard")
        quality_layout = QHBoxLayout(quality_card)
        quality_layout.setContentsMargins(16, 12, 16, 12)
        
        self.quality_label = QLabel("Signal Quality: Checking...")
        self.quality_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        quality_layout.addWidget(self.quality_label)
        
        quality_layout.addStretch()
        
        self.samples_label = QLabel("Samples: 0")
        self.samples_label.setStyleSheet("font-size: 12px; color: #64748b;")
        quality_layout.addWidget(self.samples_label)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        nav_layout.addWidget(self.back_button)
        
        nav_layout.addStretch()
        
        self.next_button = QPushButton("Proceed to Calibration →")
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(plot_card, 1)
        layout.addWidget(quality_card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_plot)
        self.update_timer.start(50)  # 20 Hz update
    
    def update_plot(self):
        """Update the EEG plot"""
        try:
            if len(ANT.live_data_buffer) > 0:
                data = np.array(list(ANT.live_data_buffer))
                
                # Display last 5 seconds (2560 samples at 512 Hz)
                display_samples = min(len(data), 2560)
                display_data = data[-display_samples:]
                
                # Create time axis
                time_axis = np.linspace(-display_samples/512, 0, len(display_data))
                
                self.plot_curve.setData(time_axis, display_data)
                self.samples_label.setText(f"Samples: {len(data)}")
                
                # Update quality
                if len(data) >= 512:
                    quality_score, status, _ = assess_eeg_signal_quality(data[-512:], fs=512)
                    
                    if status == "not_worn":
                        self.quality_label.setText("Signal Quality: ⚠ Poor - Check headset placement")
                        self.quality_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #f59e0b;")
                    elif status == "good":
                        self.quality_label.setText(f"Signal Quality: ✓ Good ({quality_score:.0f}%)")
                        self.quality_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #10b981;")
                    else:
                        self.quality_label.setText(f"Signal Quality: {status} ({quality_score:.0f}%)")
                        self.quality_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #3b82f6;")
        except Exception as e:
            print(f"Plot update error: {e}")
    
    def closeEvent(self, event):
        self.update_timer.stop()
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_back(self):
        self.update_timer.stop()
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        self.update_timer.stop()
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.CALIBRATION))


# ============================================================================
# STEP 7: CALIBRATION
# ============================================================================

class CalibrationDialog(QDialog):
    """Step 7: Calibration (Eyes Closed Baseline)"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Calibration")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(600, 450)
        self._programmatic_close = False
        
        self.calibration_duration = 60  # seconds
        self.is_calibrating = False
        self.calibration_data = []
        
        set_window_icon(self)
        
        title_label = QLabel("Calibration - Eyes Closed Baseline")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 7 of 9: Record baseline brain activity")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Instructions card
        instructions_card = QFrame()
        instructions_card.setObjectName("DialogCard")
        instructions_layout = QVBoxLayout(instructions_card)
        instructions_layout.setContentsMargins(16, 16, 16, 16)
        
        instructions_text = QLabel(
            "<b>Instructions:</b><br><br>"
            "1. Sit comfortably and relax<br>"
            "2. Close your eyes when instructed<br>"
            "3. Keep your eyes closed for 60 seconds<br>"
            "4. Try to relax and avoid movement<br>"
            "5. Open your eyes when you hear the completion sound"
        )
        instructions_text.setStyleSheet("font-size: 13px; color: #1f2937;")
        instructions_text.setWordWrap(True)
        instructions_layout.addWidget(instructions_text)
        
        # Progress card
        progress_card = QFrame()
        progress_card.setObjectName("DialogCard")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(16, 16, 16, 16)
        progress_layout.setSpacing(12)
        
        self.status_label = QLabel("Ready to start calibration")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #1f2937;")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, self.calibration_duration)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                text-align: center;
                font-weight: 600;
                height: 30px;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 6px;
            }
        """)
        
        self.time_label = QLabel("0:00 / 1:00")
        self.time_label.setStyleSheet("font-size: 14px; color: #64748b;")
        self.time_label.setAlignment(Qt.AlignCenter)
        
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.time_label)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        nav_layout.addWidget(self.back_button)
        
        nav_layout.addStretch()
        
        self.start_button = QPushButton("▶ Start Calibration")
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                border-radius: 8px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 600;
                border: 0;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        self.start_button.clicked.connect(self.start_calibration)
        nav_layout.addWidget(self.start_button)
        
        self.next_button = QPushButton("Next →")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(instructions_card)
        layout.addWidget(progress_card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Calibration timer
        self.calibration_timer = QTimer()
        self.calibration_timer.timeout.connect(self.update_calibration)
        self.elapsed_seconds = 0
    
    def start_calibration(self):
        """Start the calibration recording"""
        self.is_calibrating = True
        self.calibration_data = []
        self.multichannel_epochs = []  # Store 64-channel epochs
        self.elapsed_seconds = 0
        self.epoch_counter = 0
        
        # Tell feature engine we're starting eyes-closed calibration
        print(f"\n[CALIBRATION] Starting eyes-closed calibration phase")
        print(f"[CALIBRATION] Using {'ENHANCED 64-channel' if self.workflow.main_window.using_enhanced_engine else 'simplified'} engine")
        self.workflow.main_window.feature_engine.start_calibration_phase('eyes_closed')
        
        self.start_button.setEnabled(False)
        self.back_button.setEnabled(False)
        self.status_label.setText("👁 Close your eyes now...")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #2563eb;")
        
        play_beep(800, 300)  # Start beep
        
        self.calibration_timer.start(1000)  # 1 second intervals
    
    def update_calibration(self):
        """Update calibration progress"""
        self.elapsed_seconds += 1
        
        # Collect single-channel data (for backward compatibility)
        if len(ANT.live_data_buffer) > 0:
            self.calibration_data.extend(list(ANT.live_data_buffer))
        
        # Collect 64-channel data and extract features
        if len(ANT.multichannel_buffer) >= 500:  # At least 1 second of data at 500Hz
            # Get the last second of multichannel data as an epoch
            epoch_data = np.array(list(ANT.multichannel_buffer)[-500:])
            
            # Check if using enhanced engine
            if self.workflow.main_window.using_enhanced_engine:
                # Add epoch for feature extraction (64-channel)
                self.workflow.main_window.feature_engine.add_epoch(epoch_data)
                self.epoch_counter += 1
                
                if self.epoch_counter % 5 == 0:
                    print(f"[CALIBRATION] Epoch {self.epoch_counter}: {epoch_data.shape} samples extracted")
            else:
                # Simple engine: extract basic features
                features = {
                    'mean': float(np.mean(epoch_data)),
                    'std': float(np.std(epoch_data)),
                    'max': float(np.max(epoch_data)),
                    'min': float(np.min(epoch_data)),
                }
                self.workflow.main_window.feature_engine.add_features(features)
        
        # Update UI
        self.progress_bar.setValue(self.elapsed_seconds)
        mins = self.elapsed_seconds // 60
        secs = self.elapsed_seconds % 60
        self.time_label.setText(f"{mins}:{secs:02d} / 1:00")
        
        if self.elapsed_seconds >= self.calibration_duration:
            self.complete_calibration()
    
    def complete_calibration(self):
        """Complete calibration"""
        self.calibration_timer.stop()
        self.is_calibrating = False
        
        # Stop calibration phase in feature engine
        self.workflow.main_window.feature_engine.stop_calibration_phase()
        
        # Compute baseline statistics from calibration data
        print(f"\n[CALIBRATION] Computing baseline statistics...")
        self.workflow.main_window.feature_engine.compute_baseline_statistics()
        
        play_beep(1000, 500)  # Completion beep
        
        self.status_label.setText("✓ Calibration Complete! You may open your eyes.")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #10b981;")
        
        # Store calibration data
        self.workflow.main_window.baseline_data = np.array(self.calibration_data)
        
        print(f"[CALIBRATION] Calibration complete")
        print(f"[CALIBRATION] Epochs collected: {getattr(self, 'epoch_counter', 0)}")
        print(f"[CALIBRATION] Baseline statistics computed")
        
        self.back_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.start_button.setText("🔄 Redo Calibration")
        self.next_button.setEnabled(True)
    
    def closeEvent(self, event):
        self.calibration_timer.stop()
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            if self.is_calibrating:
                QMessageBox.warning(self, "Calibration in Progress", 
                    "Please wait for calibration to complete or click Back to cancel.")
                event.ignore()
                return
            
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_back(self):
        self.calibration_timer.stop()
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.TASK_SELECTION))


# ============================================================================
# STEP 8: TASK SELECTION (Matches BrainLink exactly)
# ============================================================================

class TaskSelectionDialog(QDialog):
    """Step 8: Select and launch cognitive tasks - matches BrainLink protocol"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Task Selection")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(550, 500)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        # Determine available tasks based on selected pathway
        pathway = getattr(self.workflow.main_window, 'selected_pathway', 'Cognitive Assessment')
        
        # Protocol groups mapping (matches BrainLink)
        protocol_groups = {
            'Personal Pathway': ['emotion_face', 'diverse_thinking'],
            'Connection': ['reappraisal', 'curiosity'],
            'Lifestyle': ['order_surprise', 'num_form'],
        }
        
        # Cognitive tasks (always included for Cognitive Assessment pathway)
        cognitive_tasks = [
            'visual_imagery', 'attention_focus', 'mental_math', 'working_memory',
            'language_processing', 'motor_imagery', 'cognitive_load'
        ]
        
        # Determine which tasks to show
        if pathway in protocol_groups:
            self.available_task_ids = protocol_groups[pathway]
        else:
            self.available_task_ids = cognitive_tasks
        
        # Track completed tasks
        self.completed_task_ids = list(getattr(self.workflow.main_window, 'completed_tasks', []))
        
        # UI Elements
        title_label = QLabel("Cognitive Tasks")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 8 of 9: Select tasks to perform")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Task selection card
        task_card = QFrame()
        task_card.setObjectName("DialogCard")
        task_layout = QVBoxLayout(task_card)
        task_layout.setContentsMargins(16, 16, 16, 16)
        task_layout.setSpacing(12)
        
        task_label = QLabel("Choose a task:")
        task_label.setObjectName("DialogSectionTitle")
        
        self.task_combo = QComboBox()
        
        # Basic tasks that don't need 'Advanced' tag
        basic_tasks = ['visual_imagery', 'attention_focus', 'mental_math', 'emotion_face']
        
        # Populate combo with task names
        for task_id in self.available_task_ids:
            if task_id in AVAILABLE_TASKS:
                task_info = AVAILABLE_TASKS[task_id]
                task_name = task_info.get('name', task_id)
                
                # Add 'Advanced' tag for non-basic tasks
                if task_id not in basic_tasks:
                    display_name = f"{task_name} (Advanced)"
                else:
                    display_name = task_name
                
                # Mark completed tasks
                if task_id in self.completed_task_ids:
                    display_name = f"✓ {display_name} (Completed)"
                
                self.task_combo.addItem(display_name, task_id)
                
                # Disable completed tasks
                if task_id in self.completed_task_ids:
                    model = self.task_combo.model()
                    item = model.item(self.task_combo.count() - 1)
                    item.setEnabled(False)
                    item.setToolTip("This task has already been completed")
        
        self.task_combo.currentIndexChanged.connect(self.update_task_preview)
        
        task_layout.addWidget(task_label)
        task_layout.addWidget(self.task_combo)
        
        # Task preview card
        preview_card = QFrame()
        preview_card.setObjectName("DialogCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(10)
        
        preview_title = QLabel("Task Details:")
        preview_title.setObjectName("DialogSectionTitle")
        
        self.task_description = QLabel()
        self.task_description.setWordWrap(True)
        self.task_description.setStyleSheet("font-size: 13px; color: #475569;")
        
        self.start_task_button = QPushButton("▶ Start This Task")
        self.start_task_button.clicked.connect(self.start_selected_task)
        self.start_task_button.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
                border: 0;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #d1d5db; color: #9ca3af; }
        """)
        
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.task_description)
        preview_layout.addWidget(self.start_task_button)
        
        # Completed tasks info
        self.completed_label = QLabel()
        self.completed_label.setStyleSheet("""
            font-size: 12px; color: #64748b; padding: 12px;
            background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px;
        """)
        self.update_completed_tasks_display()
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #475569;
            }
            QPushButton:hover { background-color: #cbd5e1; }
        """)
        nav_layout.addWidget(self.back_button)
        
        nav_layout.addStretch()
        
        self.next_button = QPushButton("Proceed to Analysis →")
        self.next_button.clicked.connect(self.on_next)
        self.next_button.setEnabled(len(self.completed_task_ids) > 0)
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(task_card)
        layout.addWidget(preview_card)
        layout.addWidget(self.completed_label)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Initialize preview
        self.update_task_preview()
    
    def update_task_preview(self):
        """Update task description preview"""
        task_id = self.task_combo.currentData()
        is_completed = task_id in self.completed_task_ids
        
        if task_id and task_id in AVAILABLE_TASKS:
            task_info = AVAILABLE_TASKS[task_id]
            task_name = task_info.get('name', task_id)
            desc = task_info.get('description', '')
            duration = task_info.get('duration', 60)
            instructions = task_info.get('instructions', '')
            
            preview_text = f"<b>{task_name}</b>"
            
            if is_completed:
                preview_text += " <span style='color: #10b981; font-weight: 600;'>✓ Completed</span>"
            
            preview_text += "<br><br>"
            preview_text += f"<b>Description:</b> {desc}<br><br>"
            preview_text += f"<b>Duration:</b> ~{duration} seconds<br><br>"
            if instructions:
                preview_text += f"<b>Instructions:</b><br>{instructions}"
            
            if is_completed:
                preview_text += "<br><br><span style='color: #f59e0b; font-weight: 600;'>⚠️ This task has already been completed. Please select a different task.</span>"
            
            self.task_description.setText(preview_text)
            
            # Disable start button if task is completed
            self.start_task_button.setEnabled(not is_completed)
            if is_completed:
                self.start_task_button.setText("Task Already Completed")
            else:
                self.start_task_button.setText("▶ Start This Task")
        else:
            self.task_description.setText("Task information not available")
            self.start_task_button.setEnabled(False)
    
    def start_selected_task(self):
        """Start the selected task with proper execution flow"""
        task_id = self.task_combo.currentData()
        
        if not task_id or task_id not in AVAILABLE_TASKS:
            QMessageBox.warning(self, "Invalid Task", f"Task '{task_id}' not found in available tasks.")
            return
        
        if task_id in self.completed_task_ids:
            QMessageBox.warning(
                self,
                "Task Already Completed",
                f"This task has already been completed.\nPlease select a different task."
            )
            return
        
        task_info = AVAILABLE_TASKS[task_id]
        task_name = task_info.get('name', task_id)
        duration = task_info.get('duration', 60)
        instructions = task_info.get('instructions', '')
        
        # Show task execution dialog
        self.hide()
        
        task_dialog = TaskExecutionDialog(
            task_id=task_id,
            task_info=task_info,
            ant_device=ANT,
            main_window=self.workflow.main_window,  # Pass main_window for feature engine access
            parent=None
        )
        
        result = task_dialog.exec()
        
        if result == QDialog.Accepted:
            # Task completed successfully
            self.completed_task_ids.append(task_id)
            self.workflow.main_window.completed_tasks = self.completed_task_ids
            self.update_completed_tasks_display()
            self._refresh_task_combo()
            self.next_button.setEnabled(True)
        
        self.show()
    
    def _refresh_task_combo(self):
        """Refresh the task combo box to update disabled states"""
        current_task_id = self.task_combo.currentData()
        self.task_combo.clear()
        
        basic_tasks = ['visual_imagery', 'attention_focus', 'mental_math', 'emotion_face']
        
        for task_id in self.available_task_ids:
            if task_id in AVAILABLE_TASKS:
                task_info = AVAILABLE_TASKS[task_id]
                task_name = task_info.get('name', task_id)
                
                if task_id not in basic_tasks:
                    display_name = f"{task_name} (Advanced)"
                else:
                    display_name = task_name
                
                if task_id in self.completed_task_ids:
                    display_name = f"✓ {display_name} (Completed)"
                
                self.task_combo.addItem(display_name, task_id)
                
                if task_id in self.completed_task_ids:
                    model = self.task_combo.model()
                    item = model.item(self.task_combo.count() - 1)
                    item.setEnabled(False)
        
        # Select first non-completed task
        for i in range(self.task_combo.count()):
            task_id = self.task_combo.itemData(i)
            if task_id not in self.completed_task_ids:
                self.task_combo.setCurrentIndex(i)
                break
    
    def update_completed_tasks_display(self):
        """Update the completed tasks counter"""
        count = len(self.completed_task_ids)
        
        if count == 0:
            self.completed_label.setText("No tasks completed yet. Complete at least one task to proceed.")
        else:
            task_names = []
            for tid in self.completed_task_ids:
                if tid in AVAILABLE_TASKS:
                    task_names.append(AVAILABLE_TASKS[tid].get('name', tid))
            
            if count == 1:
                self.completed_label.setText(f"✓ {count} task completed: {', '.join(task_names)}")
            else:
                self.completed_label.setText(f"✓ {count} tasks completed: {', '.join(task_names)}")
    
    def closeEvent(self, event):
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?\n\nCompleted tasks will be lost.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_back(self):
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        if not self.completed_task_ids:
            reply = QMessageBox.question(
                self, 'No Tasks Completed',
                'No tasks have been completed. Proceed to results anyway?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        self.workflow.main_window.completed_tasks = self.completed_task_ids
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.MULTI_TASK_ANALYSIS))


# ============================================================================
# TASK EXECUTION DIALOG (Real task with phases and audio cues)
# ============================================================================

class TaskExecutionDialog(QDialog):
    """Dialog for executing a cognitive task with proper phases and audio cues"""
    
    def __init__(self, task_id: str, task_info: dict, ant_device, main_window, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.task_name = task_info.get('name', task_id)  # Store task name
        self.task_info = task_info
        self.ant_device = ant_device
        self.main_window = main_window  # Store reference to main window for feature engine
        
        self.setWindowTitle(f"ANT Neuro - {task_info.get('name', 'Task')}")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(600, 400)
        
        set_window_icon(self)
        
        self.duration = task_info.get('duration', 60)
        self.phase_structure = task_info.get('phase_structure', [])
        self.current_phase_index = 0
        self.elapsed_seconds = 0
        self.phase_elapsed = 0
        self.is_running = False
        self.task_data = []
        
        # UI
        layout = QVBoxLayout()
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        self.title_label = QLabel(task_info.get('name', 'Task'))
        self.title_label.setStyleSheet("font-size: 24px; font-weight: 700; color: #1f2937;")
        self.title_label.setAlignment(Qt.AlignCenter)
        
        self.instruction_label = QLabel(task_info.get('instructions', ''))
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setStyleSheet("""
            font-size: 14px; color: #475569; padding: 20px;
            background: #f8fafc; border-radius: 12px;
            border: 1px solid #e2e8f0;
        """)
        self.instruction_label.setAlignment(Qt.AlignCenter)
        
        self.phase_label = QLabel("Ready to start")
        self.phase_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #2563eb;")
        self.phase_label.setAlignment(Qt.AlignCenter)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, self.duration)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #e2e8f0;
                border-radius: 10px;
                text-align: center;
                font-weight: 600;
                height: 35px;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #10b981);
                border-radius: 8px;
            }
        """)
        
        self.time_label = QLabel(f"0:00 / {self.duration // 60}:{self.duration % 60:02d}")
        self.time_label.setStyleSheet("font-size: 16px; color: #64748b; font-weight: 500;")
        self.time_label.setAlignment(Qt.AlignCenter)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #475569;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #cbd5e1; }
        """)
        self.cancel_button.clicked.connect(self.cancel_task)
        
        self.start_button = QPushButton("▶ Start Task")
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                border-radius: 8px;
                padding: 12px 32px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #d1d5db; }
        """)
        self.start_button.clicked.connect(self.start_task)
        
        btn_layout.addWidget(self.cancel_button)
        btn_layout.addStretch()
        btn_layout.addWidget(self.start_button)
        
        layout.addWidget(self.title_label)
        layout.addWidget(self.instruction_label)
        layout.addWidget(self.phase_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.time_label)
        layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
        # Timer for task execution
        self.task_timer = QTimer()
        self.task_timer.timeout.connect(self.update_task)
        
        # Countdown timer
        self.countdown_value = 5
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
    
    def start_task(self):
        """Start the task with countdown"""
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.phase_label.setText("Get ready...")
        
        # Start countdown
        self.countdown_value = 5
        self.countdown_timer.start(1000)
    
    def update_countdown(self):
        """Update countdown and play beeps"""
        if self.countdown_value > 0:
            self.phase_label.setText(f"Starting in {self.countdown_value}...")
            play_beep(800, 200)
            self.countdown_value -= 1
        else:
            self.countdown_timer.stop()
            self.begin_task_execution()
    
    def begin_task_execution(self):
        """Begin the actual task execution"""
        self.is_running = True
        self.elapsed_seconds = 0
        self.phase_elapsed = 0
        self.current_phase_index = 0
        self.task_data = []
        self.task_epoch_counter = 0
        
        # Tell feature engine we're starting this task
        print(f"\n[TASK EXECUTION] Starting task: {self.task_name}")
        print(f"[TASK EXECUTION] Duration: {self.duration} seconds")
        print(f"[TASK EXECUTION] Using {'ENHANCED 64-channel' if self.main_window.using_enhanced_engine else 'simplified'} engine")
        self.main_window.feature_engine.start_task(self.task_name)
        
        play_beep(1000, 300)  # Start beep
        
        # Update phase display
        self.update_phase_display()
        
        # Start task timer
        self.task_timer.start(1000)
        self.cancel_button.setEnabled(True)
    
    def update_phase_display(self):
        """Update the display for current phase"""
        if self.phase_structure and self.current_phase_index < len(self.phase_structure):
            phase = self.phase_structure[self.current_phase_index]
            phase_type = phase.get('type', 'task')
            instruction = phase.get('instruction', 'Continue with the task...')
            
            if phase_type == 'cue':
                self.phase_label.setText(f"📋 {instruction}")
                self.phase_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #f59e0b;")
            elif phase_type == 'task' or phase_type == 'thinking' or phase_type == 'viewing':
                self.phase_label.setText(f"🎯 {instruction}")
                self.phase_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #10b981;")
            else:
                self.phase_label.setText(instruction)
                self.phase_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #2563eb;")
        else:
            self.phase_label.setText("🎯 Continue with the task...")
            self.phase_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #10b981;")
    
    def update_task(self):
        """Update task progress"""
        self.elapsed_seconds += 1
        self.phase_elapsed += 1
        
        # Collect single-channel EEG data (backward compatibility)
        if len(self.ant_device.live_data_buffer) > 0:
            self.task_data.extend(list(self.ant_device.live_data_buffer))
        
        # Extract 64-channel features
        if len(self.ant_device.multichannel_buffer) >= 500:  # At least 1 second at 500Hz
            epoch_data = np.array(list(self.ant_device.multichannel_buffer)[-500:])
            
            if self.main_window.using_enhanced_engine:
                # Add epoch for 64-channel feature extraction
                self.main_window.feature_engine.add_epoch(epoch_data)
                self.task_epoch_counter += 1
                
                if self.task_epoch_counter % 5 == 0:
                    print(f"[TASK {self.task_name}] Epoch {self.task_epoch_counter}: {epoch_data.shape}")
            else:
                # Simple engine: extract basic features
                features = {
                    'mean': float(np.mean(epoch_data)),
                    'std': float(np.std(epoch_data)),
                }
                self.main_window.feature_engine.add_features(features)
        
        # Update progress
        self.progress_bar.setValue(self.elapsed_seconds)
        mins = self.elapsed_seconds // 60
        secs = self.elapsed_seconds % 60
        total_mins = self.duration // 60
        total_secs = self.duration % 60
        self.time_label.setText(f"{mins}:{secs:02d} / {total_mins}:{total_secs:02d}")
        
        # Check phase transitions
        if self.phase_structure and self.current_phase_index < len(self.phase_structure):
            current_phase = self.phase_structure[self.current_phase_index]
            phase_duration = current_phase.get('duration', 10)
            
            if self.phase_elapsed >= phase_duration:
                self.current_phase_index += 1
                self.phase_elapsed = 0
                play_beep(600, 150)  # Phase change beep
                self.update_phase_display()
        
        # Check if task complete
        if self.elapsed_seconds >= self.duration:
            self.complete_task()
    
    def complete_task(self):
        """Complete the task"""
        self.task_timer.stop()
        self.is_running = False
        
        # Stop task in feature engine
        self.main_window.feature_engine.stop_task()
        print(f"[TASK EXECUTION] Task '{self.task_name}' complete")
        print(f"[TASK EXECUTION] Epochs collected: {getattr(self, 'task_epoch_counter', 0)}")
        
        # Double beep for completion
        play_beep(1000, 300)
        QTimer.singleShot(400, lambda: play_beep(1000, 300))
        
        self.phase_label.setText("✓ Task Complete!")
        self.phase_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #10b981;")
        
        QTimer.singleShot(1500, self.accept)
    
    def cancel_task(self):
        """Cancel the task"""
        if self.is_running:
            reply = QMessageBox.question(
                self, 'Cancel Task',
                'Are you sure you want to cancel this task?\nProgress will be lost.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        self.task_timer.stop()
        self.countdown_timer.stop()
        self.reject()
    
    def closeEvent(self, event):
        if self.is_running:
            event.ignore()
            self.cancel_task()
        else:
            event.accept()


# ============================================================================
# STEP 9: MULTI-TASK ANALYSIS
# ============================================================================

class MultiTaskAnalysisDialog(QDialog):
    """Step 9: Real multi-task analysis and report generation
    
    This dialog matches BrainLinkAnalyzer_GUI_Sequential_Integrated.py exactly:
    - User must click "Analyze All Tasks" first
    - Permutation testing runs in background thread
    - "Generate Report" and "Seed Protocol" buttons enable after analysis completes
    - "Finish" button enables after analysis completes
    """
    
    # Define signal for thread-safe communication
    analysis_complete_signal = QtCore.Signal()
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Multi-Task Analysis")
        self.setModal(False)  # Changed to False so progress dialog works
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(700, 600)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        # Center the dialog on screen after showing
        QTimer.singleShot(0, self._center_on_screen)
        
        # Connect signal to slot for thread-safe GUI updates
        self.analysis_complete_signal.connect(self._display_results)
        
        # UI Elements
        title_label = QLabel("Multi-Task Analysis")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 9 of 9: Analyze all completed tasks")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Analysis actions card
        actions_card = QFrame()
        actions_card.setObjectName("DialogCard")
        actions_layout = QVBoxLayout(actions_card)
        actions_layout.setContentsMargins(16, 16, 16, 16)
        actions_layout.setSpacing(12)
        
        actions_label = QLabel("Analysis Actions:")
        actions_label.setObjectName("DialogSectionTitle")
        
        button_layout = QHBoxLayout()
        
        self.analyze_button = QPushButton("Analyze All Tasks")
        self.analyze_button.clicked.connect(self.analyze_all_tasks)
        self.analyze_button.setStyleSheet("padding: 10px;")
        
        self.report_button = QPushButton("Generate Report")
        self.report_button.clicked.connect(self.generate_report)
        self.report_button.setEnabled(False)
        self.report_button.setStyleSheet("padding: 10px;")
        
        # Two protocol-specific seed buttons
        self.seed_initial_button = QPushButton("Seed Initial Protocol")
        self.seed_initial_button.clicked.connect(lambda: self.seed_report("initial"))
        self.seed_initial_button.setEnabled(False)
        self.seed_initial_button.setStyleSheet("""
            padding: 10px;
            background-color: #1e3a8a;
        """)
        self.seed_initial_button.setToolTip("Seed initial protocol report to Mindspeller API")
        
        self.seed_advanced_button = QPushButton("Seed Advanced Protocol")
        self.seed_advanced_button.clicked.connect(lambda: self.seed_report("advanced"))
        self.seed_advanced_button.setEnabled(False)
        self.seed_advanced_button.setStyleSheet("""
            padding: 10px;
            background-color: #1e3a8a;
        """)
        self.seed_advanced_button.setToolTip("Seed advanced protocol report to Mindspeller API")
        
        # Determine which button to enable based on userData
        user_data = getattr(self.workflow.main_window, 'user_data', {})
        initial_protocol = user_data.get('initial_protocol', '')
        
        # If initial_protocol is empty, enable initial button; otherwise enable advanced button
        if not initial_protocol:
            # User hasn't done initial protocol yet
            self.seed_initial_button.setEnabled(False)  # Will be enabled after analysis
            self.seed_advanced_button.setVisible(False)  # Hide advanced button
        else:
            # User has completed initial protocol
            self.seed_initial_button.setVisible(False)  # Hide initial button
            self.seed_advanced_button.setEnabled(False)  # Will be enabled after analysis
        
        button_layout.addWidget(self.analyze_button)
        button_layout.addWidget(self.report_button)
        button_layout.addWidget(self.seed_initial_button)
        button_layout.addWidget(self.seed_advanced_button)
        
        actions_layout.addWidget(actions_label)
        actions_layout.addLayout(button_layout)
        
        # Add informational text about the buttons
        user_data = getattr(self.workflow.main_window, 'user_data', {})
        initial_protocol = user_data.get('initial_protocol', '')
        protocol_status = "Initial Protocol (first time)" if not initial_protocol else "Advanced Protocol (follow-up)"
        
        # Determine selected region from environment
        env = getattr(self.workflow.main_window, 'environment', 'en')
        if env == 'en':
            selected_region = "English (en)"
        elif env == 'nl':
            selected_region = "Dutch (nl)"
        else:
            selected_region = "Local"
        
        info_text = QLabel(
            f"📄 Generate Report: Save locally & share via superadmin panel\n"
            f"☁️  Seed Protocol: Send directly to Mindspeller database\n"
            f"    Protocol Type: {protocol_status}\n"
            f"    Selected Region: {selected_region} (from Step 2)"
        )
        info_text.setStyleSheet("""
            font-size: 11px; 
            color: #64748b; 
            padding: 8px 12px; 
            background: #f1f5f9; 
            border-radius: 6px;
            margin-top: 8px;
        """)
        info_text.setWordWrap(True)
        actions_layout.addWidget(info_text)
        
        # Store generated report text for seeding
        self.generated_report_text = None
        
        # Results display card
        results_card = QFrame()
        results_card.setObjectName("DialogCard")
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(16, 16, 16, 16)
        results_layout.setSpacing(10)
        
        results_label = QLabel("Results:")
        results_label.setObjectName("DialogSectionTitle")
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMinimumHeight(200)
        self.results_text.setMaximumHeight(250)
        self.results_text.setPlainText("Click 'Analyze All Tasks' to begin analysis...")
        
        results_layout.addWidget(results_label)
        results_layout.addWidget(self.results_text)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #475569;
            }
            QPushButton:hover {
                background-color: #cbd5e1;
            }
        """)
        
        nav_layout.addWidget(self.back_button)
        nav_layout.addStretch()
        
        self.finish_button = QPushButton("Finish")
        self.finish_button.clicked.connect(self.on_finish)
        self.finish_button.setEnabled(False)  # Disabled until analysis completes
        nav_layout.addWidget(self.finish_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(actions_card)
        layout.addWidget(results_card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Add status bar
        self.status_bar = add_status_bar_to_dialog(self, self.workflow.main_window)
    
    def closeEvent(self, event):
        """Handle dialog close"""
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            if self.status_bar:
                self.status_bar.cleanup()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit ANT Neuro Analyzer?\n\nAll unsaved analysis data will be lost.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def _center_on_screen(self):
        """Center the dialog on the screen"""
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                dialog_geometry = self.frameGeometry()
                center_x = screen_geometry.center().x() - dialog_geometry.width() // 2
                center_y = screen_geometry.center().y() - dialog_geometry.height() // 2
                self.move(center_x, center_y)
        except Exception as e:
            print(f"Warning: Could not center dialog: {e}")
    
    def _disconnect_device(self):
        """Disconnect the ANT Neuro device and stop data streaming"""
        try:
            self.workflow.main_window.log_message("Disconnecting device for analysis...")
            ANT.stop_streaming()
            self.workflow.main_window.log_message("✓ Device disconnected successfully")
        except Exception as e:
            self.workflow.main_window.log_message(f"Error disconnecting device: {e}")
    
    def analyze_all_tasks(self):
        """Run REAL multi-task analysis - matches BrainLink exactly"""
        self.results_text.setPlainText("Analyzing all tasks...\n\nThis may take a moment.")
        self.analyze_button.setEnabled(False)
        
        # Disconnect device before analysis
        self._disconnect_device()
        
        # Get the feature engine
        engine = self.workflow.main_window.feature_engine
        tasks = engine.calibration_data.get('tasks', {})
        
        print(f"\n=== PRE-ANALYSIS DEBUG ===")
        print(f"calibration_data keys: {list(engine.calibration_data.keys())}")
        print(f"Available tasks in 'tasks': {list(tasks.keys())}")
        for task_name, task_data in tasks.items():
            print(f"  {task_name}: {len(task_data.get('features', []))} features")
        print(f"Baseline stats exist: {bool(engine.baseline_stats)}")
        print(f"=========================\n")
        
        if not tasks:
            self.results_text.setPlainText(
                "No tasks have been recorded yet.\n\n"
                "Please:\n"
                "1. Ensure the device is connected and streaming EEG\n"
                "2. Start a task from the Task Selection step\n"
                "3. Wait at least 10-15 seconds for data collection\n"
                "4. Complete the task duration\n"
                "5. Then return here to analyze"
            )
            self.analyze_button.setEnabled(True)
            return
        
        # Show initial progress message
        self.results_text.setPlainText(
            "Analysis in progress...\n\n"
            "⏳ Initializing analysis engine...\n"
            "⏳ Computing baseline statistics...\n"
            "⏳ Preparing task comparisons...\n\n"
            "Please wait, this may take 3-5 minutes. Wait for the Generate Report button to be enabled.."
        )
        
        # Track analysis state
        self.analysis_running = True
        self.progress_dots = 0
        
        # Progress update timer
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress_display)
        self.progress_timer.start(1000)
        
        # Set up permutation progress callback
        def _permutation_progress(current, total):
            """Called from background thread during analysis"""
            try:
                progress_pct = int((current / total) * 100) if total > 0 else 0
                progress_msg = (
                    f"Analysis in progress...\n\n"
                    f"📊 Processing: {progress_pct}%\n\n"
                    f"Please wait. Wait for the Generate Report button to be enabled.."
                )
                QtCore.QMetaObject.invokeMethod(
                    self.results_text,
                    "setPlainText",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, progress_msg)
                )
            except Exception as e:
                print(f"[Permutation Progress] Error updating UI: {e}")
        
        # Register the callback
        engine.set_permutation_progress_callback(_permutation_progress)
        print(f">>> Permutation progress callback registered <<<")
        
        # Background worker thread
        def _worker():
            try:
                print(f"\n>>> [WORKER THREAD] CALLING analyze_all_tasks_data() <<<\n")
                
                # Run the analysis
                results = engine.analyze_all_tasks_data()
                
                print(f"\n>>> [WORKER THREAD] analyze_all_tasks_data() RETURNED <<<\n")
                print(f"Results type: {type(results)}")
                if isinstance(results, dict):
                    print(f"Results keys: {list(results.keys())}")
                
                # Clear the progress callback
                engine.clear_permutation_progress_callback()
                
                # Mark analysis as complete
                self.analysis_running = False
                
                # Stop progress timer from main thread
                QTimer.singleShot(0, self.progress_timer.stop)
                
                # Emit signal for thread-safe GUI update
                print(f">>> [WORKER THREAD] Emitting analysis_complete_signal <<<")
                self.analysis_complete_signal.emit()
                
            except Exception as e:
                print(f"\n>>> [WORKER THREAD] EXCEPTION: {e} <<<\n")
                import traceback
                traceback.print_exc()
                
                try:
                    engine.clear_permutation_progress_callback()
                except:
                    pass
                
                self.analysis_running = False
                QTimer.singleShot(0, self.progress_timer.stop)
                
                # Show error in main thread
                QtCore.QMetaObject.invokeMethod(
                    self.results_text,
                    "setPlainText",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, f"Error during analysis:\n{str(e)}\n\nSee console for details.")
                )
                
                # Re-enable analyze button
                def _reenable():
                    self.analyze_button.setEnabled(True)
                QTimer.singleShot(0, _reenable)
        
        # Start background thread
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        
        print(f"\n>>> [MAIN THREAD] Background analysis thread started <<<\n")
    
    @QtCore.Slot()
    def _update_progress_display(self):
        """Update progress display with animated dots"""
        if not self.analysis_running:
            return
        
        # Check if current text contains progress percentage - if so, don't override it
        current_text = self.results_text.toPlainText()
        if "Processing:" in current_text:
            return
        
        self.progress_dots = (self.progress_dots + 1) % 4
        dots = "." * self.progress_dots
        spaces = " " * (3 - self.progress_dots)
        
        self.results_text.setPlainText(
            f"Analysis in progress{dots}{spaces}\n\n"
            f"⏳ Computing features and statistics...\n\n"
            f"Please wait, this may take 3-5 minutes. Wait for the Generate Report button to be enabled.."
        )
    
    @QtCore.Slot()
    def _display_results(self):
        """Display the analysis results from multi_task_results"""
        print(f"\n>>> [MAIN THREAD] _display_results() CALLED <<<\n")
        
        engine = self.workflow.main_window.feature_engine
        
        print(f"\n=== FINAL RESULTS CHECK ===")
        print(f"hasattr(engine, 'multi_task_results'): {hasattr(engine, 'multi_task_results')}")
        if hasattr(engine, 'multi_task_results') and engine.multi_task_results:
            print(f"engine.multi_task_results.keys(): {list(engine.multi_task_results.keys())}")
        print(f"==========================\n")
        
        if hasattr(engine, 'multi_task_results') and engine.multi_task_results:
            res = engine.multi_task_results
            
            results = "✅ ANALYSIS COMPLETE!\n"
            results += "=" * 60 + "\n\n"
            
            # Show engine type and configuration
            if self.workflow.main_window.using_enhanced_engine:
                results += "🔬 ENHANCED 64-CHANNEL ANALYSIS\n"
                results += "-" * 40 + "\n"
                config = res.get('config', {})
                results += f"  Channels: {config.get('n_channels', 64)}\n"
                results += f"  Sample Rate: {config.get('sample_rate', 500)} Hz\n"
                results += f"  Permutations: {config.get('n_permutations', 5000)}\n"
                results += f"  Correction: {config.get('correction_method', 'Kost-McDermott')}\n"
                results += f"  Bands: {', '.join(config.get('bands', []))}\n"
                results += "\n"
            else:
                results += "📊 SIMPLIFIED SINGLE-CHANNEL ANALYSIS\n\n"
            
            results += "=== MULTI-TASK ANALYSIS RESULTS ===\n\n"
            
            # Per-task results
            per_task = res.get('per_task', {})
            if per_task:
                results += "Per-Task Analysis:\n"
                results += "-" * 40 + "\n"
                for task_name, data in sorted(per_task.items()):
                    summary = data.get('summary', {}) or {}
                    fisher = summary.get('fisher', {})
                    sum_p = summary.get('sum_p', {})
                    feature_sel = summary.get('feature_selection', {}) or {}
                    
                    # ============================================================
                    # DATA QUALITY CHECK - Display warning for garbage data
                    # ============================================================
                    data_quality = summary.get('data_quality', {})
                    sig_count = feature_sel.get('sig_feature_count', 0)
                    total_features = feature_sel.get('total_features', 0)
                    
                    # Calculate significant proportion for sanity check
                    if total_features > 0:
                        sig_prop = sig_count / total_features
                    else:
                        sig_prop = 0
                    
                    results += f"\n{task_name}:\n"
                    
                    # Show data quality warning prominently
                    if data_quality and not data_quality.get('reliable', True):
                        results += "\n  ⚠️⚠️⚠️ DATA QUALITY WARNING ⚠️⚠️⚠️\n"
                        for warning in data_quality.get('warnings', []):
                            # Wrap long warnings
                            if len(warning) > 60:
                                wrapped = [warning[i:i+55] for i in range(0, len(warning), 55)]
                                for w in wrapped:
                                    results += f"    {w}\n"
                            else:
                                results += f"    {warning}\n"
                        results += "  ❌ RESULTS MARKED AS UNRELIABLE\n"
                        results += "  ⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️\n\n"
                    elif sig_prop > 0.70:
                        # Fallback sanity check if data_quality not populated
                        results += "\n  ⚠️⚠️⚠️ DATA QUALITY WARNING ⚠️⚠️⚠️\n"
                        results += f"    CRITICAL: {sig_prop*100:.1f}% of features marked significant!\n"
                        results += f"    This exceeds the 70% threshold and strongly suggests\n"
                        results += f"    the data is noise/garbage, NOT real EEG.\n"
                        results += f"    The headset may not have been worn properly.\n"
                        results += "  ❌ RESULTS LIKELY INVALID\n"
                        results += "  ⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️\n\n"
                    elif sig_prop > 0.50:
                        results += f"\n  ⚠️ WARNING: {sig_prop*100:.1f}% of features significant\n"
                        results += f"    This is unusually high - may indicate data quality issues.\n\n"
                    
                    results += f"  Fisher KM p-value: {fisher.get('km_p', 'N/A')}\n"
                    results += f"  Fisher significant: {fisher.get('significant', False)}\n"
                    results += f"  SumP p-value: {sum_p.get('perm_p', 'N/A')}\n"
                    results += f"  SumP significant: {sum_p.get('significant', False)}\n"
                    results += f"  Significant features: {sig_count}"
                    if total_features > 0:
                        results += f" / {total_features} ({sig_prop*100:.1f}%)\n"
                    else:
                        results += "\n"
                results += "\n"
            
            # Combined analysis results
            combined = res.get('combined', {})
            combined_summary = combined.get('summary', {})
            if combined_summary:
                results += "All Tasks Combined:\n"
                results += "-" * 40 + "\n"
                fisher_c = combined_summary.get('fisher', {})
                sum_p_c = combined_summary.get('sum_p', {})
                results += f"  Fisher KM p-value: {fisher_c.get('km_p', 'N/A')}\n"
                results += f"  Fisher significant: {fisher_c.get('significant', False)}\n"
                results += f"  SumP p-value: {sum_p_c.get('perm_p', 'N/A')}\n"
                results += f"  SumP significant: {sum_p_c.get('significant', False)}\n"
                results += "\n"
            
            # Across-task significant features
            across = res.get('across_task', {})
            features = across.get('features', {})
            sig_features = [f for f, info in features.items() if info.get('omnibus_sig')]
            if sig_features:
                results += "Across-Task Significant Features:\n"
                results += "-" * 40 + "\n"
                for feat in sig_features[:10]:  # Limit to 10
                    results += f"  - {feat}\n"
            
            # Add completion message
            results += "\n" + "=" * 60 + "\n"
            results += "✅ Analysis complete! Click 'Generate Report' to save detailed results.\n"
            
            print(f">>> [MAIN THREAD] Setting results text (length: {len(results)} chars) <<<")
            self.results_text.setPlainText(results)
            print(f">>> [MAIN THREAD] Enabling report buttons and finish button <<<")
            self.report_button.setEnabled(True)
            
            # Enable the visible seed button based on protocol status
            if self.seed_initial_button.isVisible():
                self.seed_initial_button.setEnabled(True)
            if self.seed_advanced_button.isVisible():
                self.seed_advanced_button.setEnabled(True)
            
            self.finish_button.setEnabled(True)
            print(f">>> [MAIN THREAD] Results displayed successfully <<<")
        else:
            print(f">>> [MAIN THREAD] No results found - showing error message <<<")
            self.results_text.setPlainText("❌ No analysis results found.\n\nPlease ensure tasks have been recorded and try analyzing again.")
            self.report_button.setEnabled(False)
            self.seed_initial_button.setEnabled(False)
            self.seed_advanced_button.setEnabled(False)
        
        print(f">>> [MAIN THREAD] Re-enabling analyze button <<<")
        self.analyze_button.setEnabled(True)
        print(f">>> [MAIN THREAD] _display_results() COMPLETE <<<\n")
    
    def _generate_report_text(self):
        """Generate report text internally"""
        engine = self.workflow.main_window.feature_engine
        
        # Use the main window's generate method
        self.generated_report_text = self.workflow.main_window.generate_report_all_tasks()
        return self.generated_report_text
    
    def generate_report(self):
        """Generate REAL full report - delegates to main window"""
        engine = self.workflow.main_window.feature_engine
        if not hasattr(engine, 'multi_task_results') or not engine.multi_task_results:
            QMessageBox.warning(
                self,
                "Analysis Required",
                "No analysis results available.\n\nPlease run 'Analyze All Tasks' first."
            )
            return
        
        try:
            # Call report generation from main window
            self.generated_report_text = self.workflow.main_window.generate_report_all_tasks()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Report Error",
                f"Error generating report:\n{str(e)}"
            )
    
    def seed_report(self, protocol_type="initial"):
        """Seed the generated report to the database via API"""
        engine = self.workflow.main_window.feature_engine
        if not hasattr(engine, 'multi_task_results') or not engine.multi_task_results:
            QMessageBox.warning(
                self,
                "Analysis Required",
                "No analysis results available.\n\nPlease run 'Analyze All Tasks' first."
            )
            return
        
        # Generate report if not already generated
        if not self.generated_report_text:
            try:
                self._generate_report_text()
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Report Generation Error",
                    f"Error generating report for seeding:\n{str(e)}"
                )
                return
        
        # Create confirmation dialog with email input
        dialog = QDialog(self)
        protocol_display = "Initial Protocol" if protocol_type == "initial" else "Advanced Protocol"
        dialog.setWindowTitle(f"Seed {protocol_display} Report")
        dialog.setModal(True)
        dialog.setMinimumWidth(450)
        
        set_window_icon(dialog)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        
        # Title
        title = QLabel(f"Confirm {protocol_display} Seeding")
        title.setObjectName("DialogTitle")
        
        # Info text
        info = QLabel(f"Enter the email address for which this {protocol_display} EEG report should be seeded in the database:")
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 13px; color: #475569; margin-bottom: 8px;")
        
        # Email input
        email_input = QLineEdit()
        email_input.setPlaceholderText("user@example.com")
        email_input.setText(getattr(self.workflow.main_window, 'user_email', '') or '')
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        confirm_btn = QPushButton("Seed Report")
        confirm_btn.clicked.connect(dialog.accept)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(confirm_btn)
        
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(email_input)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        apply_modern_dialog_theme(dialog)
        
        if dialog.exec() == QDialog.Accepted:
            email = email_input.text().strip()
            if not email:
                QMessageBox.warning(self, "Email Required", "Please enter an email address.")
                return
            
            # TODO: Implement actual API seeding
            QMessageBox.information(
                self,
                "Seed Protocol",
                f"Report seeding to {email} for {protocol_display}.\n\n"
                f"API integration pending - feature coming soon!"
            )
    
    def on_back(self):
        """Go back to task selection"""
        if self.status_bar:
            self.status_bar.cleanup()
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_finish(self):
        """Complete the session"""
        reply = QMessageBox.question(
            self,
            'Session Complete',
            'Session complete!\n\nWould you like to:\n• Yes: Exit application\n• No: Start new session',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if self.status_bar:
            self.status_bar.cleanup()
        self._programmatic_close = True
        self.close()
        
        if reply == QMessageBox.Yes:
            cleanup_and_quit()
        else:
            # Restart workflow
            QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.PATHWAY_SELECTION))


# ============================================================================
# MAIN WINDOW (Hidden - Workflow is Dialog-based)
# ============================================================================

class AntNeuroAnalyzerWindow(QtWidgets.QMainWindow):
    """Main window that holds state and resources - standalone, no BrainLink inheritance"""
    
    def __init__(self, user_os: str):
        super().__init__()
        
        self.setWindowTitle("ANT Neuro 64-Channel EEG Analyzer")
        self.setMinimumSize(400, 300)
        
        # Set window icon
        icon_path = os.path.join(PARENT_DIR, "assets", "icon_Mindspeller.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # ANT Neuro specific attributes
        self.user_os = user_os
        self.environment = "en"
        self.partner_id = None
        self.jwt_token = None
        self.user_email = None
        self.user_data = {}
        self.selected_device = "DEMO-001"
        self.selected_pathway = None
        self.baseline_data = None
        self.completed_tasks = []
        self.login_url = None
        self.hwid = None
        
        # Initialize feature engine for EEG analysis
        # Use enhanced 64-channel engine if available
        if ENHANCED_64CH_AVAILABLE:
            print(f"\n{'='*70}")
            print(f"[MAIN WINDOW] Using ENHANCED 64-Channel Analysis Engine")
            print(f"[MAIN WINDOW] Features: 2500+ per epoch (40+ per channel × 64 channels)")
            print(f"[MAIN WINDOW] Bands: delta, theta, alpha1, alpha2, beta1, beta2, beta3, gamma")
            print(f"[MAIN WINDOW] Spatial: coherence, asymmetry, connectivity")
            print(f"[MAIN WINDOW] Statistics: 5000 permutations, Kost-McDermott correction")
            print(f"{'='*70}\n")
            self.feature_engine = create_enhanced_engine(sample_rate=500, channel_count=64)
            self.using_enhanced_engine = True
        else:
            print(f"\n[MAIN WINDOW] Using simplified single-channel compatible engine")
            self.feature_engine = AntNeuroFeatureEngine(sample_rate=500)
            self.using_enhanced_engine = False
        
        self.feature_engine.set_log_function(self.log_message)
        
        # Create minimal central widget (hidden during workflow)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("ANT Neuro Analyzer - Workflow in progress..."))
        self.setCentralWidget(central)
        
        # Hide the main window (workflow is popup-driven)
        self.hide()
        
        # Initialize workflow manager
        self.workflow = WorkflowManager(self)
        
        # Start the workflow
        QTimer.singleShot(100, self.start_workflow)
    
    def start_workflow(self):
        """Begin the sequential workflow"""
        self.workflow.go_to_step(WorkflowStep.OS_SELECTION)
    
    def log_message(self, message: str):
        """Log a message (for compatibility)"""
        print(f"[ANT Neuro] {message}")
    
    def generate_report_all_tasks(self):
        """Generate a report for all completed tasks - opens save dialog"""
        from PySide6.QtWidgets import QFileDialog
        
        res = getattr(self.feature_engine, 'multi_task_results', None)
        if not res:
            QMessageBox.information(
                self, "Analysis Required",
                "No analysis results available.\n\nPlease run 'Analyze All Tasks' first."
            )
            return
        
        # Generate report text
        lines = []
        lines.append("ANT Neuro 64-Channel EEG Analysis Report")
        lines.append("=" * 72)
        lines.append(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"User: {self.user_email or 'N/A'}")
        lines.append(f"Device: ANT Neuro 64-Channel EEG")
        lines.append(f"Pathway: {self.selected_pathway or 'N/A'}")
        lines.append(f"Tasks Completed: {len(self.completed_tasks)}")
        lines.append("")
        
        # Per-task results
        lines.append("Per-Task Statistical Summaries")
        lines.append("-" * 40)
        
        per_task = res.get('per_task', {})
        for tname in sorted(per_task.keys()):
            tinfo = per_task[tname] or {}
            summary = tinfo.get("summary", {}) if isinstance(tinfo, dict) else {}
            fisher = summary.get("fisher", {})
            sum_p = summary.get("sum_p", {})
            
            lines.append(f"\n[{tname}]")
            lines.append(f"  Fisher_KM_p={fisher.get('km_p', 'N/A')} sig={fisher.get('significant', False)}")
            lines.append(f"  SumP_p={sum_p.get('perm_p', 'N/A')} sig={sum_p.get('significant', False)}")
            
            # Feature details
            analysis = tinfo.get("analysis", {}) or {}
            sig_features = [f for f, d in analysis.items() if d.get('significant_change')]
            if sig_features:
                lines.append(f"  Significant Features ({len(sig_features)}):")
                for feat in sig_features[:5]:
                    d = analysis[feat]
                    lines.append(f"    {feat}: p={d.get('p_value', 'N/A'):.4g}, d={d.get('effect_size_d', 'N/A'):.3f}")
        
        # Combined analysis
        combined = res.get('combined', {})
        combined_summary = combined.get('summary', {})
        if combined_summary:
            lines.append("\n" + "=" * 40)
            lines.append("All Tasks Combined:")
            lines.append("-" * 40)
            fisher_c = combined_summary.get('fisher', {})
            sum_p_c = combined_summary.get('sum_p', {})
            lines.append(f"  Fisher_KM_p={fisher_c.get('km_p', 'N/A')} sig={fisher_c.get('significant', False)}")
            lines.append(f"  SumP_p={sum_p_c.get('perm_p', 'N/A')} sig={sum_p_c.get('significant', False)}")
        
        lines.append("\n" + "=" * 72)
        lines.append("End of Report")
        
        report_text = "\n".join(lines)
        
        # Save dialog
        default_name = f"ANTNeuro_Report_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Save Report", default_name, "Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(report_text)
                self.log_message(f"✓ Report saved to: {file_path}")
                QMessageBox.information(None, "Report Saved", f"Report saved successfully to:\n{file_path}")
            except Exception as e:
                self.log_message(f"Error saving report: {e}")
                QMessageBox.warning(None, "Save Error", f"Error saving report:\n{e}")
        
        return report_text
    
    def closeEvent(self, event):
        """Handle window close"""
        active_dialog = self.workflow.current_dialog
        was_on_top = False
        if active_dialog and active_dialog.isVisible():
            was_on_top = bool(active_dialog.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                active_dialog.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                active_dialog.show()
        
        reply = QMessageBox.question(
            self,
            'Confirm Exit',
            'Are you sure you want to exit ANT Neuro Analyzer?\n\nAll unsaved data will be lost.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if active_dialog and active_dialog.isVisible() and was_on_top:
            active_dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            active_dialog.show()
        
        if reply == QMessageBox.Yes:
            if self.workflow.current_dialog:
                try:
                    self.workflow.current_dialog.closeEvent = lambda e: e.accept()
                    self.workflow.current_dialog.close()
                except Exception:
                    pass
            
            # Cleanup ANT Neuro connection
            try:
                ANT.stop_streaming()
                ANT.disconnect()
            except Exception:
                pass
            
            event.accept()
            QTimer.singleShot(100, lambda: QtWidgets.QApplication.quit())
        else:
            event.ignore()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point"""
    print("=" * 70)
    print("ANT Neuro 64-Channel EEG Analyzer")
    print("Version 1.0 - February 2026")
    print("=" * 70)
    print()
    
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    
    # Create main window (stays hidden, workflow uses dialogs)
    window = AntNeuroAnalyzerWindow("Windows")
    # Don't call window.show() - the workflow dialogs handle visibility
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
