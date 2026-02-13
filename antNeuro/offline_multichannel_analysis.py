#!/usr/bin/env python3
"""
Offline 64-Channel EEG Recording and Analysis Engine

This module implements OFFLINE analysis for 64-channel EEG:
1. During streaming: Record raw data to CSV/Excel with timestamps
2. Mark phase transitions (eyes_closed, eyes_open, task)
3. After recording: Load raw data, segment by phase, extract features, analyze

Advantages:
- Zero computational overhead during streaming
- Raw data preserved for reanalysis
- Can apply sophisticated artifact rejection offline
- Full 1,400+ features extracted without time pressure

Author: BrainLink Companion Team
Date: February 2026
"""

import numpy as np
import pandas as pd
import time
import os
from datetime import datetime
from collections import deque
from typing import Optional, Dict, List, Any, Tuple
from scipy import signal
from scipy import stats
import warnings
import threading
import copy

# Progress bar for long operations
try:
    from tqdm import tqdm
except ImportError:
    # Fallback if tqdm not installed
    def tqdm(iterable, desc=None, total=None, **kwargs):
        if desc:
            print(f"[PROGRESS] {desc}...")
        return iterable

# Statistical functions are standalone - no GUI dependencies needed
# We'll implement them directly in this module for CSV analysis

warnings.filterwarnings('ignore', category=RuntimeWarning)

# Import channel names from enhanced engine
try:
    from antNeuro.enhanced_multichannel_analysis import (
        CHANNEL_NAMES_64,
        CHANNEL_REGIONS,
        ASYMMETRY_PAIRS,
        KEY_CHANNELS
    )
except ImportError:
    # Fallback definitions
    CHANNEL_NAMES_64 = [
        'Fp1', 'Fp2', 'F9', 'F7', 'F3', 'Fz', 'F4', 'F8',
        'F10', 'FC5', 'FC1', 'FC2', 'FC6', 'T9', 'T7', 'C3',
        'C4', 'T8', 'T10', 'CP5', 'CP1', 'CP2', 'CP6', 'P9',
        'P7', 'P3', 'Pz', 'P4', 'P8', 'P10', 'O1', 'O2',
        'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6',
        'FC3', 'FCz', 'FC4', 'C5', 'C1', 'C2', 'C6', 'CP3',
        'CP4', 'P5', 'P1', 'P2', 'P6', 'PO5', 'PO3', 'PO4',
        'PO6', 'FT7', 'FT8', 'TP7', 'TP8', 'PO7', 'PO8', 'POz'
    ]
    CHANNEL_REGIONS = {
        'frontal': ['Fp1', 'Fp2', 'F7', 'F3', 'Fz', 'F4', 'F8', 'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6', 'F9', 'F10'],
        'central': ['FC5', 'FC1', 'FC2', 'FC6', 'C3', 'C4', 'FC3', 'FCz', 'FC4', 'C5', 'C1', 'C2', 'C6'],
        'temporal': ['T7', 'T8', 'T9', 'T10', 'FT7', 'FT8', 'TP7', 'TP8'],
        'parietal': ['CP5', 'CP1', 'CP2', 'CP6', 'P7', 'P3', 'Pz', 'P4', 'P8', 'CP3', 'CP4', 'P5', 'P1', 'P2', 'P6', 'P9', 'P10'],
        'occipital': ['O1', 'O2', 'PO5', 'PO3', 'PO4', 'PO6', 'PO7', 'PO8', 'POz']
    }
    ASYMMETRY_PAIRS = [
        ('Fp1', 'Fp2'), ('F7', 'F8'), ('F3', 'F4'), ('FC5', 'FC6'), ('FC1', 'FC2'),
        ('T7', 'T8'), ('C3', 'C4'), ('CP5', 'CP6'), ('CP1', 'CP2'),
        ('P7', 'P8'), ('P3', 'P4'), ('O1', 'O2'),
        ('AF7', 'AF8'), ('AF3', 'AF4'), ('F5', 'F6'), ('F1', 'F2'),
        ('FC3', 'FC4'), ('C5', 'C6'), ('C1', 'C2'), ('CP3', 'CP4'),
        ('P5', 'P6'), ('P1', 'P2'), ('PO5', 'PO6'), ('PO3', 'PO4'), ('PO7', 'PO8'),
        ('FT7', 'FT8'), ('TP7', 'TP8')
    ]


class OfflineMultichannelEngine:
    """
    Offline 64-channel EEG recording and analysis engine.
    
    Inherits from EnhancedFeatureAnalysisEngine to get analyze_all_tasks_data().
    
    Usage:
        engine = OfflineMultichannelEngine(sample_rate=500, channel_count=64)
        
        # During streaming - just record data
        engine.add_data(multichannel_samples)
        
        # Mark phase transitions
        engine.start_phase('eyes_closed')
        engine.stop_phase()
        engine.start_phase('eyes_open')
        engine.stop_phase()
        engine.start_phase('task', task_type='visual_imagery')
        engine.stop_phase()
        
        # After all recording - offline analysis
        results = engine.analyze_offline(progress_callback=lambda p: print(f"{p}%"))
    """
    
    def __init__(
        self,
        sample_rate: int = 500,
        channel_count: int = 64,
        channel_names: List[str] = None,
        save_dir: str = None,
        window_size: float = 2.0,
        window_overlap: float = 0.5,
        user_email: str = None
    ):
        """
        Initialize the offline recording engine.
        
        Args:
            sample_rate: Sampling rate in Hz
            channel_count: Number of channels
            channel_names: List of channel names
            save_dir: Directory to save raw data files
            window_size: Analysis window size in seconds
            window_overlap: Window overlap ratio (0-1)
        """
        # Analysis configuration
        class Config:
            alpha = 0.05
            n_perm = 200  # Default for --fast mode
            n_boot = 500  # Bootstrap iterations for effect size CI (fast mode)
            fast_mode = True
            fdr_alpha = 0.05
            effect_measure = 'delta'
            omnibus = 'Friedman'
            posthoc = 'Wilcoxon'
            seed = None
        
        self.config = Config()
        
        self.fs = sample_rate
        self.channel_count = min(channel_count, 64)
        self.channel_names = channel_names or CHANNEL_NAMES_64[:self.channel_count]
        self.window_size = window_size
        self.window_overlap = window_overlap
        self.window_samples = int(self.fs * self.window_size)
        
        # Block-based analysis defaults (matching EnhancedFeatureAnalysisEngine)
        self.block_seconds = 4.0  # Match scientific paper (4s blocks)
        self.nmin_sessions = 2
        
        # Caches for block computations and RNG
        self._cached_block_summaries = {}
        self._rng = None
        
        # Export profiles for analysis results
        self.last_export_full = {}
        self.last_export_integer = {}
        self.task_summary = {}
        
        # Create save directory
        if save_dir is None:
            save_dir = os.path.join(os.path.expanduser("~"), "BrainLink_Recordings")
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)
        
        # Create session ID with user email
        self.user_email = user_email or "unknown"
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Metadata for filename (will be set via set_metadata)
        self.subject_id = None
        self.subject_age = None
        self.subject_email = None
        
        # Session file - will be renamed after metadata is set
        # Sanitize email for filename (replace @ and . with underscores)
        email_safe = self.user_email.replace('@', '_').replace('.', '_')
        self.session_file = os.path.join(self.save_dir, f"session_{self.session_id}_{email_safe}.csv")
        
        # Raw data buffer (in-memory, will also write to disk)
        self.raw_data = []  # List of (timestamp, sample_array) tuples
        self.recording_start_time = None
        
        # Phase markers
        self.phase_markers = []  # List of {'phase': str, 'task': str, 'start': float, 'end': float}
        self.current_phase = None
        self.current_task = None
        self.phase_start_time = None
        
        # Analysis results (override parent's to ensure clean state)
        self.calibration_data = {
            'eyes_closed': {'features': [], 'timestamps': []},
            'eyes_open': {'features': [], 'timestamps': []},
            'task': {'features': [], 'timestamps': []},
            'tasks': {}
        }
        self.baseline_stats = {}
        self.latest_features = {}
        
        # For compatibility with existing code
        self.current_state = 'idle'
        
        # Channel index mapping
        self.channel_index = {name: i for i, name in enumerate(self.channel_names)}
        
        # Primary channel index (Fz) for compatibility
        self.primary_channel_idx = self.channel_index.get('Fz', 5)
        
        # Region indices
        self.region_indices = {}
        for region, channels in CHANNEL_REGIONS.items():
            indices = [self.channel_index[ch] for ch in channels if ch in self.channel_index]
            if indices:
                self.region_indices[region] = indices
        
        # Asymmetry pair indices
        self.asymmetry_indices = []
        for left, right in ASYMMETRY_PAIRS:
            if left in self.channel_index and right in self.channel_index:
                self.asymmetry_indices.append((
                    left, right,
                    self.channel_index[left],
                    self.channel_index[right]
                ))
        
        # Frequency bands
        self.bands = {
            'delta': (0.5, 4),
            'theta': (4, 8),
            'alpha': (8, 13),
            'beta': (13, 30),
            'gamma': (30, 45)
        }
        
        # File writer (for streaming to disk)
        self._file_handle = None
        self._write_lock = threading.Lock()
        self._samples_written = 0
        
        # Permutation progress callback (for GUI updates)
        self._permutation_progress_callback = None
        
        print(f"[OFFLINE ENGINE] Initialized: {channel_count} channels @ {sample_rate} Hz")
        print(f"[OFFLINE ENGINE] Session ID: {self.session_id}")
        print(f"[OFFLINE ENGINE] Save directory: {self.save_dir}")
    
    def set_permutation_progress_callback(self, callback):
        """Set callback for permutation progress updates"""
        self._permutation_progress_callback = callback
    
    def clear_permutation_progress_callback(self):
        """Clear the permutation progress callback"""
        self._permutation_progress_callback = None
    
    def set_metadata(self, subject_id: str = None, subject_age: str = None, subject_email: str = None):
        """Set subject metadata for filename generation."""
        self.subject_id = subject_id or "UNKNOWN"
        self.subject_age = subject_age or "00"
        self.subject_email = subject_email or "unknown@example.com"
        
        # Construct new session filename with metadata
        email_safe = self.subject_email.replace('@', '_').replace('.', '_').replace(' ', '_')
        age_safe = self.subject_age.replace(' ', '')
        id_safe = self.subject_id.replace(' ', '_')
        
        # Format: session_<timestamp>_<SubjectID>_<Age>_<email>.csv
        new_session_file = os.path.join(
            self.save_dir, 
            f"session_{self.session_id}_{id_safe}_{age_safe}_{email_safe}.csv"
        )
        
        # If recording already started with old filename, rename it
        if self._file_handle is not None and self.session_file != new_session_file:
            print(f"[OFFLINE ENGINE] Renaming session file due to metadata update")
            print(f"  Old: {self.session_file}")
            print(f"  New: {new_session_file}")
            
            # Close current file
            self._file_handle.close()
            
            # Rename file on disk if it exists
            if os.path.exists(self.session_file):
                try:
                    os.rename(self.session_file, new_session_file)
                except Exception as e:
                    print(f"[OFFLINE ENGINE] Warning: Could not rename file: {e}")
            
            # Reopen with new filename in append mode
            self._file_handle = open(new_session_file, 'a', newline='')
        
        # Update session file path
        self.session_file = new_session_file
        
        print(f"[OFFLINE ENGINE] Metadata set: ID={self.subject_id}, Age={self.subject_age}, Email={self.subject_email}")
        print(f"[OFFLINE ENGINE] Session file: {self.session_file}")
    
    def start_recording(self):
        """Start recording raw data to disk."""
        self.recording_start_time = time.time()
        self.raw_data = []
        self._samples_written = 0
        
        # Open CSV file with headers
        self._file_handle = open(self.session_file, 'w', newline='')
        headers = ['timestamp', 'sample_index'] + self.channel_names[:self.channel_count]
        self._file_handle.write(','.join(headers) + '\n')
        
        print(f"[OFFLINE ENGINE] Recording started: {self.session_file}")
    
    def stop_recording(self):
        """Stop recording and close file."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        
        print(f"[OFFLINE ENGINE] Recording stopped: {self._samples_written} samples written")
        print(f"[OFFLINE ENGINE] File: {self.session_file}")
    
    def detect_artifacts(self, data: np.ndarray) -> Dict[str, Any]:
        """
        Detect artifacts in multi-channel EEG data.
        
        Args:
            data: Shape (n_samples, n_channels)
        
        Returns:
            Dictionary with artifact information:
            - bad_channels: List of channel indices with poor signal
            - artifact_windows: List of (start_idx, end_idx) with artifacts
            - flat_channels: Channels with flat/zero signal
            - noisy_channels: Channels with excessive amplitude
        """
        n_samples, n_channels = data.shape
        artifact_info = {
            'bad_channels': [],
            'flat_channels': [],
            'noisy_channels': [],
            'artifact_windows': [],
            'channel_quality': {}  # Quality score per channel (0-1)
        }
        
        # 1. Detect flat channels (likely disconnected)
        for ch_idx in range(n_channels):
            ch_data = data[:, ch_idx]
            std = np.std(ch_data)
            
            # Flat signal detection (<0.1 µV std)
            if std < 0.1:
                artifact_info['flat_channels'].append(ch_idx)
                artifact_info['bad_channels'].append(ch_idx)
                artifact_info['channel_quality'][ch_idx] = 0.0
                continue
            
            # Check for excessive amplitude (>200 µV)
            max_amp = np.max(np.abs(ch_data))
            if max_amp > 200:
                artifact_info['noisy_channels'].append(ch_idx)
                artifact_info['bad_channels'].append(ch_idx)
                artifact_info['channel_quality'][ch_idx] = 0.3
                continue
            
            # Compute quality score based on std and amplitude
            # Good EEG typically has 5-50 µV std
            if 5 <= std <= 50 and max_amp <= 150:
                quality = 1.0
            elif 2 <= std <= 80 and max_amp <= 200:
                quality = 0.7
            else:
                quality = 0.5
            
            artifact_info['channel_quality'][ch_idx] = quality
        
        # 2. Detect high-amplitude artifact windows
        window_size = int(0.5 * self.fs)  # 0.5 second windows
        for start_idx in range(0, n_samples - window_size, window_size // 2):
            end_idx = start_idx + window_size
            window = data[start_idx:end_idx, :]
            
            # Check for sudden amplitude spikes across channels
            max_per_channel = np.max(np.abs(window), axis=0)
            if np.mean(max_per_channel) > 150:  # Average across channels exceeds threshold
                artifact_info['artifact_windows'].append((start_idx, end_idx))
        
        return artifact_info
    
    def remove_artifacts(self, data: np.ndarray, artifact_info: Dict[str, Any] = None) -> np.ndarray:
        """
        Remove artifacts from multi-channel EEG data.
        
        Args:
            data: Shape (n_samples, n_channels)
            artifact_info: Artifact detection results (if None, will detect automatically)
        
        Returns:
            Cleaned data with artifacts removed/interpolated
        """
        if artifact_info is None:
            artifact_info = self.detect_artifacts(data)
        
        cleaned_data = data.copy()
        n_samples, n_channels = data.shape
        
        # 1. Remove bad channels by interpolating from neighbors
        bad_channels = artifact_info.get('bad_channels', [])
        if bad_channels:
            print(f"[ARTIFACT REMOVAL] Interpolating {len(bad_channels)} bad channels")
            for bad_ch in bad_channels:
                if 0 < bad_ch < n_channels - 1:
                    # Simple average of neighbors
                    cleaned_data[:, bad_ch] = (cleaned_data[:, bad_ch - 1] + cleaned_data[:, bad_ch + 1]) / 2
                elif bad_ch == 0 and n_channels > 1:
                    cleaned_data[:, bad_ch] = cleaned_data[:, bad_ch + 1]
                elif bad_ch == n_channels - 1 and n_channels > 1:
                    cleaned_data[:, bad_ch] = cleaned_data[:, bad_ch - 1]
        
        # 2. Remove high-amplitude artifact windows by linear interpolation
        artifact_windows = artifact_info.get('artifact_windows', [])
        if artifact_windows:
            print(f"[ARTIFACT REMOVAL] Interpolating {len(artifact_windows)} artifact windows")
            for start_idx, end_idx in artifact_windows:
                if start_idx > 0 and end_idx < n_samples - 1:
                    # Linear interpolation across all channels
                    for ch_idx in range(n_channels):
                        before = cleaned_data[start_idx - 1, ch_idx]
                        after = cleaned_data[end_idx + 1, ch_idx]
                        n_samples_interp = end_idx - start_idx
                        interpolated = np.linspace(before, after, n_samples_interp)
                        cleaned_data[start_idx:end_idx, ch_idx] = interpolated
        
        return cleaned_data
    
    def add_data(self, new_data):
        """
        Add new EEG data (just record, no processing).
        
        Args:
            new_data: Shape (n_samples, n_channels) or (n_channels,) for single sample
        """
        if self.recording_start_time is None:
            self.start_recording()
        
        current_time = time.time()
        relative_time = current_time - self.recording_start_time
        
        # Handle different input formats
        if np.isscalar(new_data):
            return  # Can't record single values without channel info
        
        data = np.atleast_2d(new_data)
        if data.shape[1] != self.channel_count and data.shape[0] == self.channel_count:
            data = data.T  # Transpose if needed
        
        # Truncate extra channels if device sends more than expected
        # (e.g., ANT Neuro EDI2 sends 88 channels: 64 EEG + 24 bipolar)
        if data.shape[1] > self.channel_count:
            data = data[:, :self.channel_count]
        
        # Store in memory
        for i, sample in enumerate(data):
            timestamp = relative_time + i / self.fs
            self.raw_data.append((timestamp, sample.copy()))
        
        # Write to disk (batched for efficiency)
        if self._file_handle:
            with self._write_lock:
                lines = []
                for i, sample in enumerate(data):
                    timestamp = relative_time + i / self.fs
                    sample_idx = self._samples_written + i
                    values = [f"{timestamp:.6f}", str(sample_idx)] + [f"{v:.6f}" for v in sample]
                    lines.append(','.join(values))
                self._file_handle.write('\n'.join(lines) + '\n')
                self._samples_written += len(data)
    
    def start_phase(self, phase: str, task_type: str = None, phase_subtype: str = None, should_record: bool = True):
        """
        Mark the start of a calibration/task phase or sub-phase.
        
        Args:
            phase: 'eyes_closed', 'eyes_open', or 'task'
            task_type: Task name (for task phase)
            phase_subtype: Detailed phase type (e.g., 'cue', 'baseline', 'execution', 'rest')
            should_record: Whether this phase should be recorded for analysis
        """
        self.current_phase = phase
        self.current_task = task_type
        self.current_phase_subtype = phase_subtype
        self.current_should_record = should_record
        self.current_state = phase  # For compatibility
        self.phase_start_time = time.time()
        
        relative_time = 0
        if self.recording_start_time:
            relative_time = self.phase_start_time - self.recording_start_time
        
        phase_desc = f"{phase}"
        if phase_subtype:
            phase_desc += f" ({phase_subtype})"
        if task_type:
            phase_desc += f" - {task_type}"
        record_flag = "RECORDING" if should_record else "NOT RECORDED"
        print(f"[OFFLINE ENGINE] Phase started: {phase_desc} [{record_flag}] at t={relative_time:.2f}s")
    
    def stop_phase(self):
        """Mark the end of current phase."""
        if self.current_phase is None:
            return
        
        end_time = time.time()
        relative_start = 0
        relative_end = 0
        
        if self.recording_start_time:
            relative_start = self.phase_start_time - self.recording_start_time
            relative_end = end_time - self.recording_start_time
        
        marker = {
            'phase': self.current_phase,
            'task': self.current_task,
            'start': relative_start,
            'end': relative_end
        }
        
        # Add detailed phase information if available
        if hasattr(self, 'current_phase_subtype') and self.current_phase_subtype:
            marker['phase_type'] = self.current_phase_subtype
        if hasattr(self, 'current_should_record'):
            marker['record'] = self.current_should_record
        
        self.phase_markers.append(marker)
        
        duration = relative_end - relative_start
        phase_desc = self.current_phase
        if hasattr(self, 'current_phase_subtype') and self.current_phase_subtype:
            phase_desc += f" ({self.current_phase_subtype})"
        print(f"[OFFLINE ENGINE] Phase ended: {phase_desc} (duration: {duration:.1f}s)")
        
        self.current_phase = None
        self.current_task = None
        self.current_state = 'idle'
        self.phase_start_time = None
        if hasattr(self, 'current_phase_subtype'):
            self.current_phase_subtype = None
        if hasattr(self, 'current_should_record'):
            self.current_should_record = True
    
    # Compatibility methods
    def start_calibration_phase(self, phase: str, task_type: str = None):
        """Compatibility wrapper for start_phase."""
        self.start_phase(phase, task_type)
    
    def stop_calibration_phase(self):
        """Compatibility wrapper for stop_phase."""
        self.stop_phase()
    
    def set_log_function(self, log_func):
        """Set logging function for compatibility."""
        self._log_func = log_func
    
    def analyze_offline(self, progress_callback=None) -> Dict[str, Any]:
        """
        Perform offline analysis on recorded data.
        
        This is called when the user clicks "Analyze" after recording.
        Extracts features from all phases and runs statistical analysis.
        
        Args:
            progress_callback: Function to call with progress (0-100)
        
        Returns:
            Dictionary with analysis results
        """
        print(f"\n{'='*70}")
        print(f"[OFFLINE ENGINE] STARTING OFFLINE ANALYSIS")
        print(f"[OFFLINE ENGINE] Total samples: {len(self.raw_data)}")
        print(f"[OFFLINE ENGINE] Phase markers: {len(self.phase_markers)}")
        print(f"{'='*70}\n")
        
        if not self.raw_data:
            print("[OFFLINE ENGINE] No data to analyze!")
            return None
        
        if not self.phase_markers:
            print("[OFFLINE ENGINE] No phase markers found!")
            return None
        
        # Convert raw data to numpy array
        timestamps = np.array([t for t, _ in self.raw_data])
        samples = np.array([s for _, s in self.raw_data])
        
        total_phases = len(self.phase_markers)
        
        # Clear accumulated artifact summary before processing all phases
        self.artifact_summary = {}
        self._accumulated_artifact_info = {
            'bad_channels': set(),
            'flat_channels': set(),
            'noisy_channels': set(),
            'artifact_windows': [],
            'channel_quality': {},
        }
        
        # Reset calibration data buckets before accumulation
        self.calibration_data['eyes_closed'] = {'features': [], 'timestamps': []}
        self.calibration_data['eyes_open'] = {'features': [], 'timestamps': []}
        self.calibration_data['task'] = {'features': [], 'timestamps': []}
        self.calibration_data['tasks'] = {}
        
        # Process each phase
        for phase_idx, marker in enumerate(self.phase_markers):
            phase = marker['phase']
            task = marker['task']
            start_time = marker['start']
            end_time = marker['end']
            
            if progress_callback:
                progress_callback(int(phase_idx / total_phases * 50))
            
            print(f"[OFFLINE ENGINE] Processing phase: {phase} (t={start_time:.1f}s to {end_time:.1f}s)")
            
            # Extract samples for this phase
            mask = (timestamps >= start_time) & (timestamps <= end_time)
            phase_data = samples[mask]
            
            if len(phase_data) < self.fs * self.window_size:
                print(f"  Warning: Not enough data for phase {phase} ({len(phase_data)} samples)")
                continue
            
            # Extract features using windowing
            features_list = self._extract_windowed_features(phase_data, progress_callback, 
                                                            base_progress=int(phase_idx / total_phases * 50))
            
            if not features_list:
                continue
            
            # ACCUMULATE features (tasks with multiple sub-phases need all features combined)
            if phase == 'eyes_closed':
                self.calibration_data['eyes_closed']['features'].extend(features_list)
                self.calibration_data['eyes_closed']['timestamps'] = list(
                    range(len(self.calibration_data['eyes_closed']['features'])))
            elif phase == 'eyes_open':
                self.calibration_data['eyes_open']['features'].extend(features_list)
                self.calibration_data['eyes_open']['timestamps'] = list(
                    range(len(self.calibration_data['eyes_open']['features'])))
            elif phase == 'task':
                self.calibration_data['task']['features'].extend(features_list)
                self.calibration_data['task']['timestamps'] = list(
                    range(len(self.calibration_data['task']['features'])))
                
                if task:
                    tasks = self.calibration_data.setdefault('tasks', {})
                    if task in tasks:
                        # Accumulate features for same task across sub-phases
                        tasks[task]['features'].extend(features_list)
                        tasks[task]['timestamps'] = list(range(len(tasks[task]['features'])))
                    else:
                        tasks[task] = {
                            'features': list(features_list),
                            'timestamps': list(range(len(features_list)))
                        }
            
            print(f"  Extracted {len(features_list)} feature windows ({len(features_list[0])} features each)")
        
        # Finalize accumulated artifact summary (union of all phases)
        self._finalize_artifact_summary()
        
        if progress_callback:
            progress_callback(60)
        
        # Compute baseline
        self.compute_baseline_statistics()
        
        if progress_callback:
            progress_callback(100)
        
        print(f"\n[OFFLINE ENGINE] Analysis complete!")
        print(f"  Eyes-closed windows: {len(self.calibration_data['eyes_closed']['features'])}")
        print(f"  Eyes-open windows: {len(self.calibration_data['eyes_open']['features'])}")
        print(f"  Task windows: {len(self.calibration_data['task']['features'])}")
        for task_name, task_data in self.calibration_data.get('tasks', {}).items():
            print(f"  Task '{task_name}' windows: {len(task_data.get('features', []))}")
        
        return self.calibration_data
    
    def _extract_windowed_features(self, data: np.ndarray, progress_callback=None, base_progress=0) -> List[Dict]:
        """
        Extract features from data using sliding windows.
        
        Args:
            data: Shape (n_samples, n_channels)
            progress_callback: Progress callback
            base_progress: Base progress value
        
        Returns:
            List of feature dictionaries
        """
        n_samples = len(data)
        window_samples = int(self.window_size * self.fs)
        step_samples = int(window_samples * (1 - self.window_overlap))
        
        # Perform artifact detection on full data
        artifact_info = self.detect_artifacts(data)
        print(f"[ARTIFACT DETECTION] Bad channels: {len(artifact_info['bad_channels'])}")
        print(f"[ARTIFACT DETECTION] Artifact windows: {len(artifact_info['artifact_windows'])}")
        
        # Apply artifact removal
        cleaned_data = self.remove_artifacts(data, artifact_info)
        
        # Store artifact info for reporting, converting indices → channel names
        # (The report generator and quality checks expect string channel names as keys)
        # ACCUMULATE across all phases (don't overwrite) so the final summary
        # reflects the worst-case across the entire recording session.
        if not hasattr(self, 'artifact_summary'):
            self.artifact_summary = {}
        if not hasattr(self, '_accumulated_artifact_info'):
            self._accumulated_artifact_info = {
                'bad_channels': set(),
                'flat_channels': set(),
                'noisy_channels': set(),
                'artifact_windows': [],
                'channel_quality': {},
            }
        
        idx_to_name = lambda idx: (self.channel_names[idx]
                                   if idx < len(self.channel_names) else f'Ch{idx}')
        
        # Accumulate bad/flat/noisy channels (union across phases)
        for i in artifact_info.get('bad_channels', []):
            self._accumulated_artifact_info['bad_channels'].add(idx_to_name(i))
        for i in artifact_info.get('flat_channels', []):
            self._accumulated_artifact_info['flat_channels'].add(idx_to_name(i))
        for i in artifact_info.get('noisy_channels', []):
            self._accumulated_artifact_info['noisy_channels'].add(idx_to_name(i))
        self._accumulated_artifact_info['artifact_windows'].extend(
            artifact_info.get('artifact_windows', []))
        # For channel_quality, keep worst (lowest) quality score per channel
        for ch_idx, quality in artifact_info.get('channel_quality', {}).items():
            ch_name = idx_to_name(ch_idx)
            existing = self._accumulated_artifact_info['channel_quality'].get(ch_name, 1.0)
            self._accumulated_artifact_info['channel_quality'][ch_name] = min(existing, quality)
        
        features_list = []
        n_windows = (n_samples - window_samples) // step_samples + 1
        
        for i, start_idx in enumerate(range(0, n_samples - window_samples + 1, step_samples)):
            end_idx = start_idx + window_samples
            window_data = cleaned_data[start_idx:end_idx]
            
            features = self._extract_multichannel_features(window_data)
            if features:
                features_list.append(features)
        
        return features_list
    
    def _finalize_artifact_summary(self):
        """Convert accumulated artifact info into the final artifact_summary dict.
        
        Called once after all phases have been processed by analyze_offline().
        Produces the same format expected by Enhanced64ChannelReportGenerator.
        """
        acc = getattr(self, '_accumulated_artifact_info', None)
        if not acc:
            return
        
        self.artifact_summary = {
            'bad_channels': sorted(acc['bad_channels']),
            'flat_channels': sorted(acc['flat_channels']),
            'noisy_channels': sorted(acc['noisy_channels']),
            'artifact_windows': acc['artifact_windows'],
            'channel_quality': acc['channel_quality'],
        }
        
        n_bad = len(self.artifact_summary['bad_channels'])
        n_total = self.channel_count
        print(f"[ARTIFACT SUMMARY] Final: {n_bad}/{n_total} bad channels across all phases")
        if n_bad > 0:
            print(f"[ARTIFACT SUMMARY] Bad channels: {', '.join(self.artifact_summary['bad_channels'][:10])}"
                  f"{'...' if n_bad > 10 else ''}")
    
    def _extract_multichannel_features(self, mc_data: np.ndarray) -> Dict[str, float]:
        """
        Extract comprehensive features from multi-channel EEG window.
        
        Args:
            mc_data: Shape (n_samples, n_channels)
        
        Returns:
            Dictionary with ~1,400 features
        """
        features = {}
        n_samples, n_channels = mc_data.shape
        
        if n_samples < 256 or n_channels < 1:
            return None
        
        # Remove DC offset
        mc_data = mc_data - np.mean(mc_data, axis=0, keepdims=True)
        
        # Apply notch filter for line noise
        try:
            b_notch, a_notch = signal.iirnotch(60.0, 30.0, self.fs)
            mc_data = signal.filtfilt(b_notch, a_notch, mc_data, axis=0)
        except:
            pass
        
        # Compute PSD for all channels
        nperseg = min(n_samples, 256)
        try:
            freqs, psd_all = signal.welch(mc_data, self.fs, nperseg=nperseg, axis=0)
        except:
            return None
        
        # ==================================================================
        # 1. PER-CHANNEL FEATURES
        # ==================================================================
        for ch_idx in range(min(n_channels, self.channel_count)):
            ch_name = self.channel_names[ch_idx] if ch_idx < len(self.channel_names) else f'Ch{ch_idx}'
            psd = psd_all[:, ch_idx]
            total_power = np.sum(psd) + 1e-12
            
            for band_name, (low, high) in self.bands.items():
                mask = (freqs >= low) & (freqs <= high)
                band_power = np.sum(psd[mask])
                
                features[f'{ch_name}_{band_name}_power'] = float(band_power)
                features[f'{ch_name}_{band_name}_relative'] = float(band_power / total_power)
                
                # Peak frequency in band
                if np.any(mask) and band_power > 0:
                    band_psd = psd[mask]
                    band_freqs = freqs[mask]
                    peak_idx = np.argmax(band_psd)
                    features[f'{ch_name}_{band_name}_peak_freq'] = float(band_freqs[peak_idx])
            
            # Cross-band ratios
            alpha_power = features.get(f'{ch_name}_alpha_power', 0)
            theta_power = features.get(f'{ch_name}_theta_power', 0)
            beta_power = features.get(f'{ch_name}_beta_power', 0)
            
            features[f'{ch_name}_alpha_theta_ratio'] = float(alpha_power / (theta_power + 1e-10))
            features[f'{ch_name}_beta_alpha_ratio'] = float(beta_power / (alpha_power + 1e-10))
            features[f'{ch_name}_total_power'] = float(total_power)
        
        # ==================================================================
        # 2. REGIONAL FEATURES
        # ==================================================================
        for region_name, ch_indices in self.region_indices.items():
            if not ch_indices:
                continue
            
            region_psd = np.mean(psd_all[:, ch_indices], axis=1)
            total_power = np.sum(region_psd) + 1e-12
            
            for band_name, (low, high) in self.bands.items():
                mask = (freqs >= low) & (freqs <= high)
                band_power = np.sum(region_psd[mask])
                
                features[f'{region_name}_{band_name}_power'] = float(band_power)
                features[f'{region_name}_{band_name}_relative'] = float(band_power / total_power)
            
            alpha = features.get(f'{region_name}_alpha_power', 0)
            theta = features.get(f'{region_name}_theta_power', 0)
            beta = features.get(f'{region_name}_beta_power', 0)
            
            features[f'{region_name}_alpha_theta_ratio'] = float(alpha / (theta + 1e-10))
            features[f'{region_name}_beta_alpha_ratio'] = float(beta / (alpha + 1e-10))
            features[f'{region_name}_total_power'] = float(total_power)
        
        # ==================================================================
        # 3. SPATIAL FEATURES
        # ==================================================================
        # Asymmetry
        for left_name, right_name, left_idx, right_idx in self.asymmetry_indices:
            left_psd = psd_all[:, left_idx]
            right_psd = psd_all[:, right_idx]
            
            for band_name, (low, high) in self.bands.items():
                mask = (freqs >= low) & (freqs <= high)
                left_power = np.sum(left_psd[mask]) + 1e-12
                right_power = np.sum(right_psd[mask]) + 1e-12
                
                asym = np.log(right_power) - np.log(left_power)
                features[f'asym_{left_name}_{right_name}_{band_name}'] = float(asym)
        
        # Frontal Alpha Asymmetry
        if 'F3' in self.channel_index and 'F4' in self.channel_index:
            f3_idx = self.channel_index['F3']
            f4_idx = self.channel_index['F4']
            alpha_mask = (freqs >= 8) & (freqs <= 13)
            f3_alpha = np.sum(psd_all[alpha_mask, f3_idx]) + 1e-12
            f4_alpha = np.sum(psd_all[alpha_mask, f4_idx]) + 1e-12
            features['frontal_alpha_asymmetry'] = float(np.log(f4_alpha) - np.log(f3_alpha))
        
        # Inter-regional coherence
        region_pairs = [
            ('frontal', 'parietal'),
            ('frontal', 'occipital'),
            ('central', 'parietal'),
            ('temporal', 'parietal'),
            ('frontal', 'temporal')
        ]
        
        for region1, region2 in region_pairs:
            if region1 in self.region_indices and region2 in self.region_indices:
                idx1 = self.region_indices[region1][0]
                idx2 = self.region_indices[region2][0]
                
                try:
                    f_coh, coh = signal.coherence(
                        mc_data[:, idx1], mc_data[:, idx2],
                        fs=self.fs, nperseg=min(n_samples, 128)
                    )
                    
                    for band_name, (low, high) in self.bands.items():
                        mask = (f_coh >= low) & (f_coh <= high)
                        if np.any(mask):
                            mean_coh = np.mean(coh[mask])
                            features[f'coh_{region1}_{region2}_{band_name}'] = float(mean_coh)
                except:
                    pass
        
        # Global Field Power
        gfp = np.std(mc_data, axis=1)
        features['gfp_mean'] = float(np.mean(gfp))
        features['gfp_std'] = float(np.std(gfp))
        features['gfp_max'] = float(np.max(gfp))
        
        # ==================================================================
        # 4. GLOBAL FEATURES
        # ==================================================================
        global_psd = np.mean(psd_all, axis=1)
        global_total = np.sum(global_psd) + 1e-12
        
        for band_name, (low, high) in self.bands.items():
            mask = (freqs >= low) & (freqs <= high)
            band_power = np.sum(global_psd[mask])
            features[f'global_{band_name}_power'] = float(band_power)
            features[f'global_{band_name}_relative'] = float(band_power / global_total)
        
        features['global_total_power'] = float(global_total)
        features['global_alpha_theta_ratio'] = float(
            features.get('global_alpha_power', 0) / (features.get('global_theta_power', 1e-10) + 1e-10)
        )
        features['global_beta_alpha_ratio'] = float(
            features.get('global_beta_power', 0) / (features.get('global_alpha_power', 1e-10) + 1e-10)
        )
        
        features['n_good_channels'] = int(n_channels)
        features['n_features_extracted'] = len(features)
        
        return features
    
    def compute_baseline_statistics(self):
        """Compute baseline statistics from eyes-closed data."""
        ec_features = self.calibration_data['eyes_closed']['features']
        if not ec_features:
            print("[OFFLINE ENGINE] No eyes-closed features for baseline")
            return False
        
        df = pd.DataFrame(ec_features)
        self.baseline_stats = {}
        
        for col in df.columns:
            values = df[col].dropna().values
            if len(values) > 0:
                self.baseline_stats[col] = {
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values) + 1e-12),
                    'median': float(np.median(values))
                }
        
        print(f"[OFFLINE ENGINE] Baseline computed from {len(ec_features)} windows")
        print(f"[OFFLINE ENGINE] Total features in baseline: {len(self.baseline_stats)}")
        return True
    
    def save_phase_markers(self):
        """Save phase markers to a JSON file."""
        import json
        # Include metadata in markers filename (matching CSV filename pattern)
        if self.subject_id and self.subject_age and self.subject_email:
            email_safe = self.subject_email.replace('@', '_').replace('.', '_').replace(' ', '_')
            age_safe = self.subject_age.replace(' ', '')
            id_safe = self.subject_id.replace(' ', '_')
            markers_file = os.path.join(
                self.save_dir, 
                f"markers_{self.session_id}_{id_safe}_{age_safe}_{email_safe}.json"
            )
        else:
            # Fallback to old format if metadata not set
            email_safe = self.user_email.replace('@', '_').replace('.', '_')
            markers_file = os.path.join(self.save_dir, f"markers_{self.session_id}_{email_safe}.json")
        
        with open(markers_file, 'w') as f:
            marker_data = {
                'session_id': self.session_id,
                'user_email': self.user_email,
                'sample_rate': self.fs,
                'channel_count': self.channel_count,
                'channel_names': self.channel_names,
                'recording_file': self.session_file,
                'phase_markers': self.phase_markers
            }
            
            # Add subject metadata if available
            if self.subject_id or self.subject_age or self.subject_email:
                marker_data['subject_metadata'] = {
                    'id': self.subject_id or 'UNKNOWN',
                    'age': self.subject_age or '00',
                    'email': self.subject_email or 'unknown@example.com'
                }
            
            json.dump(marker_data, f, indent=2)
        
        print(f"[OFFLINE ENGINE] Phase markers saved: {markers_file}")
        return markers_file
    
    # ==================================================================
    # STATISTICAL ANALYSIS METHODS
    # ==================================================================
    
    def _bootstrap_hedges_g_ci(self, task_values: np.ndarray, baseline_values: np.ndarray, 
                               n_boot: int = 1000, ci_level: float = 0.95) -> Dict[str, float]:
        """
        Compute Hedges' g effect size with bootstrap confidence interval.
        
        Hedges' g uses baseline SD (not pooled SD like Cohen's d) for unequal-variance scenarios.
        Includes small-sample bias correction factor.
        
        Args:
            task_values: Task condition measurements (n_task,)
            baseline_values: Baseline condition measurements (n_baseline,)
            n_boot: Number of bootstrap iterations
            ci_level: Confidence interval level (e.g., 0.95 for 95% CI)
        
        Returns:
            Dictionary with 'effect_size', 'ci_lower', 'ci_upper'
        """
        n_task = len(task_values)
        n_baseline = len(baseline_values)
        n_total = n_task + n_baseline
        
        # Hedges' g uses baseline SD as reference (Glass's Δ formulation)
        mean_task = np.mean(task_values)
        mean_baseline = np.mean(baseline_values)
        sd_baseline = np.std(baseline_values, ddof=1)
        
        if sd_baseline < 1e-10:
            return {'effect_size': 0.0, 'ci_lower': 0.0, 'ci_upper': 0.0}
        
        # Raw effect size (Glass's Δ)
        glass_delta = (mean_task - mean_baseline) / sd_baseline
        
        # Hedges' correction factor for small samples
        correction_factor = 1 - (3 / (4 * n_total - 9))
        hedges_g = glass_delta * correction_factor
        
        # VECTORIZED Bootstrap confidence interval (much faster than loop)
        # Generate all bootstrap indices at once
        boot_task_indices = np.random.randint(0, n_task, size=(n_boot, n_task))
        boot_baseline_indices = np.random.randint(0, n_baseline, size=(n_boot, n_baseline))
        
        # Sample all bootstrap replicates at once
        boot_task_samples = task_values[boot_task_indices]  # Shape: (n_boot, n_task)
        boot_baseline_samples = baseline_values[boot_baseline_indices]  # Shape: (n_boot, n_baseline)
        
        # Compute means and SDs for all bootstrap samples
        boot_mean_task = np.mean(boot_task_samples, axis=1)
        boot_mean_baseline = np.mean(boot_baseline_samples, axis=1)
        boot_sd_baseline = np.std(boot_baseline_samples, axis=1, ddof=1)
        
        # Compute effect sizes (handle zero SD with masking)
        valid_mask = boot_sd_baseline > 1e-10
        boot_effects = np.zeros(n_boot)
        boot_effects[valid_mask] = ((boot_mean_task[valid_mask] - boot_mean_baseline[valid_mask]) 
                                    / boot_sd_baseline[valid_mask]) * correction_factor
        
        alpha = 1 - ci_level
        ci_lower = np.percentile(boot_effects, 100 * alpha / 2)
        ci_upper = np.percentile(boot_effects, 100 * (1 - alpha / 2))
        
        return {
            'effect_size': float(hedges_g),
            'ci_lower': float(ci_lower),
            'ci_upper': float(ci_upper)
        }
    
    def _friedman_permutation_test(self, baseline_features: List[Dict], task_features: List[Dict],
                                   feature_names: List[str], n_perm: int = 200) -> Dict[str, Any]:
        """
        Friedman test with permutation-based p-value for omnibus significance.
        
        Args:
            baseline_features: List of baseline feature dictionaries
            task_features: List of task feature dictionaries
            feature_names: List of feature names to test
            n_perm: Number of permutations
        
        Returns:
            Dictionary with test statistics and p-value
        """
        if len(task_features) < 3:
            return {'statistic': 0.0, 'p_value': 1.0, 'note': 'Insufficient data'}
        
        # Extract feature matrix (windows x features)
        baseline_matrix = np.array([[f.get(fn, 0) for fn in feature_names] for f in baseline_features])
        task_matrix = np.array([[f.get(fn, 0) for fn in feature_names] for f in task_features])
        
        n_baseline = len(baseline_matrix)
        n_task = len(task_matrix)
        
        # Compute observed Friedman statistic
        try:
            # Combine baseline and task for test
            combined = np.vstack([baseline_matrix, task_matrix])
            conditions = np.array([0] * n_baseline + [1] * n_task)
            
            # Friedman test on feature rankings
            observed_stat = 0.0
            for feat_idx in range(len(feature_names)):
                feat_data = combined[:, feat_idx]
                # Use variance as simple statistic (more robust than Friedman with 2 conditions)
                baseline_var = np.var(baseline_matrix[:, feat_idx])
                task_var = np.var(task_matrix[:, feat_idx])
                observed_stat += abs(task_var - baseline_var)
            
            # Permutation test
            perm_stats = []
            for perm_i in range(n_perm):
                perm_idx = np.random.permutation(len(conditions))
                perm_conditions = conditions[perm_idx]
                perm_baseline = combined[perm_conditions == 0]
                perm_task = combined[perm_conditions == 1]
                
                perm_stat = 0.0
                for feat_idx in range(len(feature_names)):
                    baseline_var = np.var(perm_baseline[:, feat_idx])
                    task_var = np.var(perm_task[:, feat_idx])
                    perm_stat += abs(task_var - baseline_var)
                
                perm_stats.append(perm_stat)
                
                # Invoke progress callback if set
                if self._permutation_progress_callback:
                    try:
                        self._permutation_progress_callback(perm_i + 1, n_perm)
                    except Exception as e:
                        print(f"[PERMUTATION] Callback error: {e}")
            
            perm_stats = np.array(perm_stats)
            p_value = np.sum(perm_stats >= observed_stat) / n_perm
            
            return {
                'statistic': float(observed_stat),
                'p_value': float(p_value),
                'n_permutations': n_perm
            }
        except Exception as e:
            return {'statistic': 0.0, 'p_value': 1.0, 'error': str(e)}
    
    def analyze_task_data(self) -> Dict[str, Any]:
        """
        Analyze task data vs baseline with Hedges' g effect sizes and permutation tests.
        
        Returns:
            Dictionary with per-feature analysis results
        """
        if not hasattr(self, 'baseline_stats') or not self.baseline_stats:
            print("[OFFLINE ENGINE] Computing baseline statistics...")
            self.compute_baseline_statistics()
        
        baseline_features = self.calibration_data.get('eyes_closed', {}).get('features', [])
        task_features = self.calibration_data.get('task', {}).get('features', [])
        
        if not task_features:
            print("[OFFLINE ENGINE] No task data to analyze")
            return None
        
        if len(task_features) < 3 or len(baseline_features) < 3:
            print(f"[OFFLINE ENGINE] Insufficient data (baseline: {len(baseline_features)}, task: {len(task_features)})")
            return None
        
        print(f"[OFFLINE ENGINE] Analyzing {len(task_features)} task windows vs {len(baseline_features)} baseline windows")
        print(f"[OFFLINE ENGINE] Computing Hedges' g effect sizes with {self.config.n_perm} permutations...")
        
        # Get all feature names
        feature_names = list(self.baseline_stats.keys())
        
        # Compute per-feature statistics
        per_feature = {}
        significant_count = 0
        
        for feat_name in tqdm(feature_names, desc="Computing effect sizes", unit="features"):
            baseline_values = np.array([f.get(feat_name, 0) for f in baseline_features])
            task_values = np.array([f.get(feat_name, 0) for f in task_features])
            
            # Skip if no variance
            if np.std(baseline_values) < 1e-10:
                continue
            
            # Compute Hedges' g with bootstrap CI (use config n_boot for speed)
            hedges_result = self._bootstrap_hedges_g_ci(task_values, baseline_values, n_boot=self.config.n_boot)
            
            # Wilcoxon test (non-parametric)
            try:
                stat, p_value = stats.mannwhitneyu(task_values, baseline_values, alternative='two-sided')
            except:
                p_value = 1.0
            
            b_mean = float(np.mean(baseline_values))
            t_mean = float(np.mean(task_values))
            per_feature[feat_name] = {
                'hedges_g': hedges_result['effect_size'],
                'g_ci_lower': hedges_result['ci_lower'],
                'g_ci_upper': hedges_result['ci_upper'],
                'p_value': float(p_value),
                'baseline_mean': b_mean,
                'task_mean': t_mean,
                'delta': t_mean - b_mean,
                'significant': p_value < self.config.alpha and abs(hedges_result['effect_size']) > 0.2
            }
            
            if per_feature[feat_name]['significant']:
                significant_count += 1
        
        # Omnibus test (permutation-based Friedman)
        print(f"[OFFLINE ENGINE] Running omnibus permutation test...")
        omnibus_result = self._friedman_permutation_test(baseline_features, task_features, 
                                                         feature_names, self.config.n_perm)
        
        # === COMPREHENSIVE SUMMARY STATISTICS ===
        feature_names_in_results = [fn for fn in feature_names if fn in per_feature]
        all_p_values = [per_feature[fn]['p_value'] for fn in feature_names_in_results]
        k_features = len(all_p_values)
        
        # 1. FDR correction (Benjamini-Hochberg)
        rejected, p_adjusted = self._bh_fdr(all_p_values, self.config.fdr_alpha)
        for i, fname in enumerate(feature_names_in_results):
            per_feature[fname]['q_value'] = p_adjusted[i]
            per_feature[fname]['fdr_significant'] = rejected[i]
        fdr_sig_count = sum(rejected)
        
        # 2. Fisher combined test: T = -2 * sum(log(p_i)), df = 2k
        p_arr = np.array(all_p_values, dtype=np.float64)
        p_arr = np.clip(p_arr, 1e-300, 1.0)
        fisher_stat = float(-2.0 * np.sum(np.log(p_arr)))
        fisher_df = 2.0 * k_features
        fisher_p = self._chi2_sf(fisher_stat, int(fisher_df))
        fisher_sig = fisher_p < self.config.alpha
        
        # KM correlation adjustment (simplified - full matrix too expensive for 1300+ features)
        km_mean_r = 0.0
        km_df = fisher_df
        km_df_ratio = km_df / (2.0 * max(k_features, 1))
        
        # 3. Sum-P test (Irwin-Hall normal approximation)
        sum_p_observed = float(np.sum(p_arr))
        if k_features > 0:
            sum_p_mean = k_features * 0.5
            sum_p_var = k_features / 12.0
            sum_p_z = (sum_p_observed - sum_p_mean) / np.sqrt(max(sum_p_var, 1e-18))
            try:
                sum_p_pval = float(stats.norm.cdf(sum_p_z))
            except Exception:
                sum_p_pval = 1.0
        else:
            sum_p_pval = 1.0
        sum_p_sig = sum_p_pval < self.config.alpha
        
        # 4. Composite score = sum(-log10(q)) for FDR-significant features
        composite_score = 0.0
        for i, fname in enumerate(feature_names_in_results):
            if rejected[i]:
                composite_score += float(-np.log10(max(p_adjusted[i], 1e-300)))
        
        # 5. Effect size statistics (significant features)
        abs_d_values = [abs(per_feature[fn]['hedges_g'])
                        for fn in feature_names_in_results
                        if per_feature[fn].get('significant', False)]
        mean_abs_d = float(np.mean(abs_d_values)) if abs_d_values else 0.0
        median_abs_d = float(np.median(abs_d_values)) if abs_d_values else 0.0
        # Fraction of significant features with |d| > 5 (noise indicator)
        extreme_d_frac = (sum(1 for v in abs_d_values if v > 5.0) / max(len(abs_d_values), 1)) if abs_d_values else 0.0
        
        # 6. Data quality validation (cap-not-worn / noise detection)
        # Use MEDIAN |d| instead of mean — robust to outlier total_power features
        # that legitimately spike during cognitive tasks like mental_math.
        # Cap-not-worn: noise affects ALL features → median stays high (>5)
        # Proper cap: only a few total_power features are extreme → median stays normal (<3)
        sig_proportion = significant_count / max(len(per_feature), 1)
        data_quality_reliable = True
        data_quality_warnings = []
        
        if median_abs_d > 5.0:
            data_quality_reliable = False
            data_quality_warnings.append(
                f"CRITICAL: Abnormally large effect sizes (median |d| = {median_abs_d:.1f}). "
                f"Real EEG data rarely exceeds d=3.0. Cap may not be worn properly."
            )
        
        if sig_proportion > 0.85:
            data_quality_reliable = False
            data_quality_warnings.append(
                f"CRITICAL: {sig_proportion*100:.0f}% of features significant "
                f"(expected <30% for real EEG). Suggests noise or disconnected cap."
            )
        
        if hasattr(self, 'artifact_summary') and self.artifact_summary:
            bad_ch = len(self.artifact_summary.get('bad_channels', []))
            if bad_ch > self.channel_count * 0.35:
                data_quality_warnings.append(
                    f"WARNING: {bad_ch}/{self.channel_count} channels flagged as bad "
                    f"({bad_ch/self.channel_count*100:.0f}%). Check electrode contact."
                )
                if bad_ch > self.channel_count * 0.5:
                    data_quality_reliable = False
        
        n_baseline = len(baseline_features)
        n_task = len(task_features)
        
        print(f"[OFFLINE ENGINE] Analysis complete: {significant_count}/{len(per_feature)} features significant")
        print(f"[OFFLINE ENGINE] Omnibus p-value: {omnibus_result.get('p_value', 1.0):.4f}")
        print(f"[OFFLINE ENGINE] Fisher combined p = {fisher_p:.6g}, SumP = {sum_p_observed:.4f} (p={sum_p_pval:.6g})")
        print(f"[OFFLINE ENGINE] CompositeScore = {composite_score:.3f}, Mean|d| = {mean_abs_d:.4f}, Median|d| = {median_abs_d:.4f}")
        print(f"[OFFLINE ENGINE] Extreme features (|d|>5): {sum(1 for v in abs_d_values if v > 5.0)}/{len(abs_d_values)} ({extreme_d_frac*100:.1f}%)")
        if not data_quality_reliable:
            for w in data_quality_warnings:
                print(f"[OFFLINE ENGINE] ⚠ {w}")
        
        return {
            'per_feature': per_feature,
            'omnibus': omnibus_result,
            'summary': {
                'total_features': len(per_feature),
                'significant_features': significant_count,
                'baseline_windows': n_baseline,
                'task_windows': n_task,
                'ess': {
                    'baseline_blocks': n_baseline,
                    'task_blocks': n_task,
                },
                'fisher': {
                    'km_p': fisher_p,
                    'significant': fisher_sig,
                    'km_df': km_df,
                    'k_features': k_features,
                    'km_mean_r': km_mean_r,
                    'km_df_ratio': km_df_ratio,
                    'alpha': self.config.alpha,
                },
                'sum_p': {
                    'value': sum_p_observed,
                    'chi2_p': sum_p_pval,
                    'significant': sum_p_sig,
                    'permutation_used': False,
                },
                'composite': {
                    'score': composite_score,
                },
                'effect_size_mean': mean_abs_d,
                'effect_size_median': median_abs_d,
                'extreme_d_fraction': extreme_d_frac,
                'feature_selection': {
                    'total_features': len(per_feature),
                    'fdr_alpha': self.config.fdr_alpha,
                },
                'data_quality': {
                    'reliable': data_quality_reliable,
                    'warnings': data_quality_warnings,
                    'sig_prop': sig_proportion,
                    'sig_count': significant_count,
                    'total_features': len(per_feature),
                },
            }
        }
    
    # === HELPER METHODS FOR ADVANCED STATISTICAL ANALYSIS ===
    
    @staticmethod
    def _chi2_sf(stat: float, df: int) -> float:
        """Survival function (1-CDF) for chi-square. Uses SciPy if available; else normal approx."""
        try:
            return float(stats.chi2.sf(stat, df))
        except Exception:
            pass
        # Normal approximation: chi2_k ~ N(k, 2k)
        try:
            from math import erfc, sqrt
            if df <= 0:
                return 1.0
            mean = float(df)
            std = float(np.sqrt(2.0 * df))
            z = (stat - mean) / (std + 1e-18)
            return float(0.5 * erfc(z / np.sqrt(2.0)))
        except Exception:
            return 1.0
    
    @staticmethod
    def _bh_fdr(p_values, alpha=0.05):
        """Benjamini–Hochberg FDR procedure.
        Returns (rejected_mask, p_adjusted_list).
        """
        if not p_values:
            return [], []
        # Pair p-values with their original indices
        m = len(p_values)
        pairs = sorted([(max(min(float(p), 1.0), 1e-300), i) for i, p in enumerate(p_values)], key=lambda x: x[0])
        p_sorted = [p for p, _ in pairs]
        idx_sorted = [i for _, i in pairs]
        # Compute adjusted p-values (BH step-up)
        q = [0.0] * m
        prev = 1.0
        for k in range(m - 1, -1, -1):
            val = (m / (k + 1.0)) * p_sorted[k]
            prev = min(prev, val)
            q[k] = prev
        # Re-map to original order
        p_adj = [0.0] * m
        for pos, orig_idx in enumerate(idx_sorted):
            p_adj[orig_idx] = min(q[pos], 1.0)
        rejected = [pa <= alpha for pa in p_adj]
        return rejected, p_adj
    
    @staticmethod
    def _holm_bonferroni(p_values, alpha=0.05):
        """Holm-Bonferroni step-down correction for family-wise error rate.
        
        More powerful than Bonferroni while still controlling FWER.
        Used for cross-task correction of omnibus p-values.
        
        Returns (rejected_mask, p_adjusted_list).
        """
        if not p_values:
            return [], []
        m = len(p_values)
        pairs = sorted([(max(min(float(p), 1.0), 1e-300), i) for i, p in enumerate(p_values)], key=lambda x: x[0])
        p_sorted = [p for p, _ in pairs]
        idx_sorted = [i for _, i in pairs]
        
        # Step-down: multiply p[i] by (m - i)
        p_adj_sorted = [0.0] * m
        for i in range(m):
            adjusted = p_sorted[i] * (m - i)
            # Enforce monotonicity (each adjusted p >= previous)
            if i > 0:
                adjusted = max(adjusted, p_adj_sorted[i - 1])
            p_adj_sorted[i] = min(adjusted, 1.0)
        
        # Re-map to original order
        p_adj = [0.0] * m
        for pos, orig_idx in enumerate(idx_sorted):
            p_adj[orig_idx] = p_adj_sorted[pos]
        
        rejected = [pa <= alpha for pa in p_adj]
        return rejected, p_adj
    
    def _get_rng(self) -> np.random.Generator:
        if self._rng is None:
            seed = self.config.seed if self.config.seed is not None else int(time.time() * 1000) % (2**32)
            self._rng = np.random.default_rng(seed)
        return self._rng
    
    def _window_duration_sec(self) -> float:
        try:
            return float(self.window_samples) / float(self.fs)
        except Exception:
            return 2.0
    
    def _build_blocks(self, features_list: List[Dict[str, Any]], timestamps: List[float]) -> List[Dict[str, Any]]:
        """Aggregate features into non-overlapping temporal blocks."""
        if not features_list:
            return []
        block_sec = float(self.block_seconds)
        # Use cache keyed by list id and block length when possible
        cache_key = ("blocks", id(features_list), block_sec)
        cached = self._cached_block_summaries.get(cache_key)
        if cached is not None:
            return cached
        # Compute block index per window by elapsed time
        if timestamps and len(timestamps) == len(features_list):
            t0 = float(timestamps[0])
            rel = [max(0.0, float(t) - t0) for t in timestamps]
            block_idx = [int(r // block_sec) for r in rel]
        else:
            # Fallback: derive block size by window duration
            wsec = max(1e-6, self._window_duration_sec())
            per_block = max(1, int(round(block_sec / wsec)))
            block_idx = [i // per_block for i in range(len(features_list))]
        # Aggregate by block index: mean of features present in all entries
        df = pd.DataFrame(features_list)
        df['_block'] = block_idx
        grouped = df.groupby('_block', sort=True)
        block_df = grouped.mean(numeric_only=True).drop(columns=[c for c in ['_block'] if c in grouped.obj.columns], errors='ignore')
        # Convert to list of dicts
        blocks = [row._asdict() if hasattr(row, '_asdict') else row.to_dict() for _, row in block_df.iterrows()]
        self._cached_block_summaries[cache_key] = blocks
        return blocks
    
    @staticmethod
    def _friedman_fallback(rows: np.ndarray) -> Tuple[float, float]:
        """Fallback Friedman test implementation."""
        # rows.shape = (observations, treatments)
        n, k = rows.shape
        if n < 2 or k < 2:
            return 0.0, 1.0
        ranks = np.argsort(np.argsort(rows, axis=1), axis=1).astype(float) + 1.0
        sum_ranks = np.sum(ranks, axis=0)
        chi2 = (12.0 / (n * k * (k + 1))) * np.sum((sum_ranks - (n * (k + 1) / 2.0)) ** 2)
        p_val = float(OfflineMultichannelEngine._chi2_sf(chi2, k - 1))
        return float(chi2), p_val
    
    def _friedman_test(self, rows: np.ndarray) -> Tuple[float, float]:
        """Friedman test for repeated measures (non-parametric)."""
        try:
            stat, p_val = stats.friedmanchisquare(*[rows[:, i] for i in range(rows.shape[1])])
            return float(stat), float(p_val)
        except Exception:
            pass
        return self._friedman_fallback(rows)
    
    @staticmethod
    def _sign_test_pvalue(diff: np.ndarray) -> float:
        """Sign test for paired differences."""
        diff = diff[np.isfinite(diff)]
        diff = diff[diff != 0]
        n = diff.size
        if n == 0:
            return 1.0
        pos = int(np.sum(diff > 0))
        tail = min(pos, n - pos)

        # Prefer SciPy's exact binomial implementation when available
        try:
            return float(stats.binomtest(pos, n, 0.5).pvalue)
        except Exception:
            pass

        if n <= 60:
            # Exact probability via cumulative binomial
            import math
            cumulative = math.fsum(math.comb(n, k) for k in range(tail + 1))
            base_prob = cumulative / (2 ** n)
            if n % 2 == 0 and pos == n - pos:
                center_prob = math.comb(n, tail) / (2 ** n)
                p_val = 2.0 * base_prob - center_prob
            else:
                p_val = 2.0 * base_prob
            return float(min(1.0, max(0.0, p_val)))

        # Normal approximation with continuity correction for large n
        z = abs(pos - n / 2.0 - 0.5) / (np.sqrt(n) / 2.0)
        from math import erfc
        return float(erfc(z / np.sqrt(2.0)))
    
    def _analyze_across_tasks(self, tasks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Cross-task comparison using Friedman test and pairwise Wilcoxon/sign tests."""
        if not tasks or len(tasks) < 2:
            return {}
        if not self.baseline_stats:
            return {}

        valid_tasks: Dict[str, Dict[str, Any]] = {}
        valid_task_names: List[str] = []
        skipped: List[str] = []
        for name in sorted(tasks.keys()):
            data = tasks.get(name)
            if not isinstance(data, dict):
                skipped.append(name)
                continue
            feature_entries = data.get('features') or []
            if not isinstance(feature_entries, list):
                skipped.append(name)
                continue
            cleaned_entries = [entry for entry in feature_entries if isinstance(entry, dict) and entry]
            if not cleaned_entries:
                skipped.append(name)
                continue
            valid_task_names.append(name)
            valid_tasks[name] = {'features': cleaned_entries, 'timestamps': data.get('timestamps', [])}

        if len(valid_task_names) < 2:
            print(f"[OFFLINE ENGINE] Cross-task analysis requires at least two tasks with valid feature data.")
            return {}

        if skipped:
            print(f"[OFFLINE ENGINE] Omitting task(s) without valid feature data from cross-task comparison: {', '.join(skipped)}")

        task_names = valid_task_names
        feature_sets = []
        for data in valid_tasks.values():
            feat_names = set()
            for entry in data.get('features', []):
                feat_names.update(entry.keys())
            feature_sets.append(feat_names)
        if not feature_sets:
            return {}
        common_features = set.intersection(*feature_sets)
        common_features = [f for f in common_features if f in self.baseline_stats]
        if not common_features:
            return {}

        feature_results: Dict[str, Any] = {}
        feature_sequence: List[str] = []
        omnibus_pvalues: List[float] = []

        # Build per-task block effect arrays per feature
        per_task_blocks: Dict[str, List[Dict[str, Any]]] = {}
        for task in task_names:
            flist = valid_tasks[task]['features']
            tlist = valid_tasks[task].get('timestamps', [])
            per_task_blocks[task] = self._build_blocks(flist, tlist)
        # Equalize sessions count by trimming to min length across tasks
        min_sessions = min(len(v) for v in per_task_blocks.values()) if per_task_blocks else 0
        
        print(f"[OFFLINE ENGINE] Across-task analysis: Tasks={len(task_names)}, Block counts={{{', '.join([f'{t}:{len(per_task_blocks[t])}' for t in task_names])}}}, min={min_sessions}")
        
        if min_sessions < self.nmin_sessions:
            # Ranking-only mode: insufficient sessions for significance testing
            msg = (f"⚠ Across-task significance testing disabled: N={min_sessions} sessions < Nmin={self.nmin_sessions}. "
                   f"Showing descriptive rankings only (median effect per task).")
            print(f"[OFFLINE ENGINE] {msg}")
            
            ranking_only: Dict[str, Any] = {}
            sorted_features_ranking = sorted(common_features)
            for feature in tqdm(sorted_features_ranking, desc="Ranking features", unit="features"):
                arrays = []
                for task in task_names:
                    vals = [blk.get(feature) for blk in per_task_blocks[task] if feature in blk]
                    arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
                    stats_dict = self.baseline_stats[feature]
                    mean = float(stats_dict['mean'])
                    std = float(stats_dict['std'])
                    eff = (arr - mean) / (std + 1e-12) if self.config.effect_measure == 'z' else (arr - mean)
                    arrays.append(eff[:min_sessions] if min_sessions > 0 else eff)
                if not arrays:
                    continue
                medians = [float(np.median(a)) if a.size > 0 else 0.0 for a in arrays]
                order = sorted(range(len(task_names)), key=lambda i: medians[i], reverse=True)
                ranking = [{ 'task': task_names[idx], 'median_effect': medians[idx], 'rank': r+1 } for r, idx in enumerate(order)]
                ranking_only[feature] = {
                    'ranking': ranking,
                    'sessions': min_sessions,
                    'significance': 'disabled',
                }
            return {
                'task_order': task_names,
                'features': ranking_only,
                'fdr_alpha': self.config.fdr_alpha,
                'ranking_only': True,
                'nmin_sessions': self.nmin_sessions,
                'sessions_used': min_sessions,
                'message': msg,
            }

        sorted_features = sorted(common_features)
        
        # In fast mode, limit features tested to top N most variable (saves massive time)
        if getattr(self.config, 'fast_mode', True) and len(sorted_features) > 200:
            # Select top 200 most variable features across tasks
            feature_variance = {}
            for feat in sorted_features:
                variances = []
                for task in task_names:
                    vals = [blk.get(feat) for blk in per_task_blocks[task] if feat in blk]
                    arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
                    if arr.size > 0:
                        variances.append(np.var(arr))
                feature_variance[feat] = np.mean(variances) if variances else 0
            
            sorted_features = sorted(sorted_features, key=lambda f: feature_variance.get(f, 0), reverse=True)[:200]
            print(f"[OFFLINE ENGINE] Fast mode: testing top 200 most variable features (of {len(common_features)})")
        
        print(f"[OFFLINE ENGINE] Starting across-task Friedman tests for {len(sorted_features)} features...")
        
        # Pre-import scipy.stats for pairwise tests (avoid import inside loop)
        from scipy import stats as scipy_stats
        
        # Skip pairwise in fast mode to save time
        skip_pairwise = getattr(self.config, 'fast_mode', True)
        
        for feature in tqdm(sorted_features, desc="Across-task analysis", unit="features"):
            raw_arrays = []
            for task in task_names:
                vals = [blk.get(feature) for blk in per_task_blocks[task] if feature in blk]
                arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
                stats_dict = self.baseline_stats[feature]
                mean = float(stats_dict['mean'])
                std = float(stats_dict['std'])
                eff = (arr - mean) / (std + 1e-12) if self.config.effect_measure == 'z' else (arr - mean)
                raw_arrays.append(eff)
            if not raw_arrays:
                continue
            # Determine equalized row count for this feature across tasks
            per_feature_rows = min((a.size for a in raw_arrays), default=0)
            # Also respect the global min_sessions cap
            n_rows = min(per_feature_rows, min_sessions)
            if n_rows < 2:
                continue
            per_task_arrays = [a[:n_rows] for a in raw_arrays]
            data_matrix = np.column_stack(per_task_arrays)

            stat, p_val = self._friedman_test(data_matrix)
            omnibus_pvalues.append(p_val)

            pairwise_indices: List[Tuple[int, int]] = []
            pairwise_pvals: List[float] = []
            num_tasks = len(task_names)
            
            # Only compute pairwise tests if not in fast mode (expensive!)
            if not skip_pairwise:
                for i in range(num_tasks):
                    for j in range(i + 1, num_tasks):
                        diff = data_matrix[:, i] - data_matrix[:, j]
                        try:
                            _, p_pair = scipy_stats.wilcoxon(diff)
                        except Exception:
                            p_pair = self._sign_test_pvalue(diff)
                        pairwise_indices.append((i, j))
                        pairwise_pvals.append(p_pair)

            ranking = []
            medians = [float(np.median(data_matrix[:, idx])) for idx in range(num_tasks)]
            order = sorted(range(num_tasks), key=lambda i: medians[i], reverse=True)
            for rank, idx in enumerate(order, start=1):
                ranking.append({
                    'task': task_names[idx],
                    'median_effect': medians[idx],
                    'rank': rank,
                })

            feature_results[feature] = {
                'omnibus_stat': float(stat),
                'omnibus_p': float(p_val),
                'method': self.config.omnibus,
                'task_order': task_names,
                'pairwise_indices': pairwise_indices,
                'pairwise_pvals': pairwise_pvals,
                'ranking': ranking,
                'matrix': data_matrix.tolist(),
            }
            feature_sequence.append(feature)

        if not feature_results:
            return {}

        _, omnibus_qvals = self._bh_fdr(omnibus_pvalues, alpha=self.config.fdr_alpha)
        for feature, q_val in zip(feature_sequence, omnibus_qvals):
            feature_results[feature]['omnibus_q'] = q_val
            feature_results[feature]['omnibus_sig'] = q_val <= self.config.fdr_alpha

            pairwise_pvals = feature_results[feature]['pairwise_pvals']
            if pairwise_pvals:
                _, pairwise_q = self._bh_fdr(pairwise_pvals, alpha=self.config.fdr_alpha)
            else:
                pairwise_q = []
            num_tasks = len(task_names)
            q_matrix = [[None for _ in range(num_tasks)] for _ in range(num_tasks)]
            sig_matrix = [[False for _ in range(num_tasks)] for _ in range(num_tasks)]
            for idx, (i, j) in enumerate(feature_results[feature]['pairwise_indices']):
                qv = pairwise_q[idx] if idx < len(pairwise_q) else None
                q_matrix[i][j] = q_matrix[j][i] = qv
                sig = bool(qv is not None and qv <= self.config.fdr_alpha)
                sig_matrix[i][j] = sig_matrix[j][i] = sig
            feature_results[feature]['posthoc_q'] = q_matrix
            feature_results[feature]['posthoc_sig'] = sig_matrix

        return {
            'task_order': task_names,
            'features': feature_results,
            'fdr_alpha': self.config.fdr_alpha,
        }
    
    def analyze_all_tasks_data(self) -> Dict[str, Any]:
        """
        Analyze all recorded tasks with comprehensive statistical pipeline.
        
        Includes:
        - Input validation and normalization
        - Per-task analysis with Hedges' g effect sizes
        - Combined analysis (all tasks pooled)
        - Across-task comparison (Friedman + pairwise tests)
        - Cross-task FWER correction (Holm-Bonferroni)
        - Export profiles for reports
        
        Returns:
            Dictionary with per_task, combined, across_task, and cross_task_correction results
        """
        if not hasattr(self, 'baseline_stats') or not self.baseline_stats:
            print("[OFFLINE ENGINE] Computing baseline statistics...")
            self.compute_baseline_statistics()
        
        # === INPUT VALIDATION AND NORMALIZATION ===
        raw_tasks = self.calibration_data.get('tasks', {}) or {}
        normalized_tasks: Dict[str, Dict[str, Any]] = {}
        skipped_tasks: List[Tuple[str, str]] = []
        
        # Tasks to exclude from analysis (data collection only, analyzed offline separately)
        excluded_tasks = {'40hz_stimulation', 'gamma_entrainment'}
        
        for task_name, raw_data in raw_tasks.items():
            # Skip data-collection-only tasks
            if task_name.lower() in excluded_tasks:
                print(f"[OFFLINE ENGINE] Skipping '{task_name}' (data collection only - analyzed offline)")
                continue
            if not isinstance(raw_data, dict):
                skipped_tasks.append((task_name, "invalid task container"))
                continue
            raw_features = raw_data.get('features') or []
            if not isinstance(raw_features, list):
                skipped_tasks.append((task_name, "feature bucket is not a list"))
                continue
            timestamps_container = raw_data.get('timestamps')
            if isinstance(timestamps_container, (list, tuple)):
                raw_timestamps = list(timestamps_container)
            else:
                raw_timestamps = []
            cleaned_features: List[Dict[str, Any]] = []
            cleaned_timestamps: List[Any] = []
            for idx, entry in enumerate(raw_features):
                if not isinstance(entry, dict):
                    continue
                if not entry:
                    continue
                cleaned_features.append(entry)
                timestamp_value = raw_timestamps[idx] if idx < len(raw_timestamps) else None
                cleaned_timestamps.append(timestamp_value)
            if not cleaned_features:
                skipped_tasks.append((task_name, "no valid feature windows recorded"))
                continue
            normalized_tasks[task_name] = {
                'features': cleaned_features,
                'timestamps': cleaned_timestamps,
            }
        
        if skipped_tasks:
            for task_name, reason in skipped_tasks:
                msg = f"Skipping task '{task_name}' in multi-task analysis: {reason}."
                print(f"[OFFLINE ENGINE] {msg}")
        
        tasks = normalized_tasks
        
        if not tasks:
            msg = "Multi-task analysis skipped: no tasks with valid feature data were recorded."
            print(f"[OFFLINE ENGINE] {msg}")
            return {
                'per_task': {},
                'combined': {
                    'analysis': {},
                    'summary': {},
                    'export_full': {},
                    'export_integer': {},
                },
                'across_task': {},
                'cross_task_correction': {},
            }
        
        print(f"\n[OFFLINE ENGINE] ============================================")
        print(f"[OFFLINE ENGINE] MULTI-TASK ANALYSIS ({len(tasks)} tasks)")
        print(f"[OFFLINE ENGINE] ============================================\n")
        
        # === PER-TASK ANALYSIS ===
        task_bucket = self.calibration_data.setdefault('task', {'features': [], 'timestamps': []})
        original_task_features_src = task_bucket.get('features')
        if isinstance(original_task_features_src, (list, tuple)):
            original_task_features = list(original_task_features_src)
        else:
            original_task_features = []

        original_task_timestamps_src = task_bucket.get('timestamps')
        if isinstance(original_task_timestamps_src, (list, tuple)):
            original_task_timestamps = list(original_task_timestamps_src)
        else:
            original_task_timestamps = []
        
        per_task_results: Dict[str, Any] = {}
        
        for idx, (task_name, data) in enumerate(tasks.items(), 1):
            print(f"[OFFLINE ENGINE] Analyzing task {idx}/{len(tasks)}: {task_name}")
            print(f"[OFFLINE ENGINE] -" * 20)
            
            # Temporarily set this task as the active task
            task_bucket['features'] = list(data.get('features', []))
            task_bucket['timestamps'] = list(data.get('timestamps', []))
            
            # Run analysis
            analysis = self.analyze_task_data()
            
            if analysis:
                # Populate export profiles (simplified for offline engine)
                summary = analysis.get('summary', {})
                exports_full = {
                    'summary': summary,
                    'features': analysis.get('per_feature', {}),
                }
                exports_int = {
                    'summary': {'significant_features': summary.get('significant_features', 0)},
                }
                
                per_task_results[task_name] = {
                    'analysis': copy.deepcopy(analysis),
                    'summary': copy.deepcopy(summary),
                    'export_full': exports_full,
                    'export_integer': exports_int,
                }
                
                print(f"[OFFLINE ENGINE] {task_name}: {summary['significant_features']} significant features")
                omnibus_p = analysis.get('omnibus', {}).get('p_value', 1.0)
                print(f"[OFFLINE ENGINE] Omnibus p = {omnibus_p:.4f}\n")
            else:
                print(f"[OFFLINE ENGINE] {task_name}: Insufficient data for analysis\n")
        
        # Restore original task bucket
        task_bucket['features'] = original_task_features
        task_bucket['timestamps'] = original_task_timestamps
        
        # === COMBINED ANALYSIS (ALL TASKS POOLED) ===
        print(f"[OFFLINE ENGINE] Analyzing combined (all tasks)...")
        print(f"[OFFLINE ENGINE] -" * 20)
        
        combined_features = []
        combined_timestamps = []
        for data in tasks.values():
            combined_features.extend(list(data.get('features', [])))
            combined_timestamps.extend(list(data.get('timestamps', [])))
        
        task_bucket['features'] = combined_features
        task_bucket['timestamps'] = combined_timestamps
        combined_analysis = self.analyze_task_data()
        
        if combined_analysis:
            combined_summary = combined_analysis.get('summary', {})
            print(f"[OFFLINE ENGINE] Combined: {combined_summary['significant_features']} significant features")
            omnibus_p = combined_analysis.get('omnibus', {}).get('p_value', 1.0)
            print(f"[OFFLINE ENGINE] Omnibus p = {omnibus_p:.4f}\n")
            
            combined_exports_full = {
                'summary': combined_summary,
                'features': combined_analysis.get('per_feature', {}),
            }
            combined_exports_int = {
                'summary': {'significant_features': combined_summary.get('significant_features', 0)},
            }
        else:
            combined_summary = {}
            combined_exports_full = {}
            combined_exports_int = {}
        
        # Restore again
        task_bucket['features'] = original_task_features
        task_bucket['timestamps'] = original_task_timestamps
        
        # === ACROSS-TASK ANALYSIS (FRIEDMAN + PAIRWISE) ===
        across_task = self._analyze_across_tasks(tasks)
        
        # === CROSS-TASK FAMILY-WISE ERROR CORRECTION (HOLM-BONFERRONI) ===
        cross_task_correction = {}
        if len(per_task_results) >= 2:
            task_names = list(per_task_results.keys())
            omnibus_pvals = []
            for t in task_names:
                summary = per_task_results[t].get('summary', {})
                omnibus_result = per_task_results[t].get('analysis', {}).get('omnibus', {})
                p_value = omnibus_result.get('p_value')
                if p_value is not None and isinstance(p_value, (int, float)):
                    omnibus_pvals.append(float(p_value))
                else:
                    omnibus_pvals.append(1.0)  # Missing p-value treated as non-significant
            
            # Apply Holm-Bonferroni step-down correction
            rejected, adjusted_pvals = self._holm_bonferroni(omnibus_pvals, alpha=self.config.alpha)
            
            # Store corrected results
            for i, t in enumerate(task_names):
                if 'summary' not in per_task_results[t]:
                    per_task_results[t]['summary'] = {}
                omnibus_dict = per_task_results[t]['summary'].setdefault('omnibus', {})
                omnibus_dict['p_fwer'] = adjusted_pvals[i]
                omnibus_dict['fwer_significant'] = rejected[i]
            
            cross_task_correction = {
                'method': 'Holm-Bonferroni',
                'n_tasks': len(task_names),
                'alpha': self.config.alpha,
                'raw_pvals': dict(zip(task_names, omnibus_pvals)),
                'adjusted_pvals': dict(zip(task_names, adjusted_pvals)),
                'significant_tasks': [t for t, sig in zip(task_names, rejected) if sig],
            }
            
            print(f"[OFFLINE ENGINE] FWER correction: {len([s for s in rejected if s])}/{len(task_names)} tasks significant after Holm-Bonferroni")
        
        print(f"[OFFLINE ENGINE] ============================================")
        print(f"[OFFLINE ENGINE] ANALYSIS COMPLETE")
        print(f"[OFFLINE ENGINE] ============================================\n")
        
        return {
            'per_task': per_task_results,
            'combined': {
                'analysis': copy.deepcopy(combined_analysis) if combined_analysis else {},
                'summary': combined_summary,
                'export_full': combined_exports_full,
                'export_integer': combined_exports_int,
            },
            'across_task': across_task,
            'cross_task_correction': cross_task_correction,
        }
    
    def export_features_to_excel(self, output_file: str = None):
        """Export extracted features to Excel file."""
        if output_file is None:
            # Include user email in features filename
            email_safe = self.user_email.replace('@', '_').replace('.', '_')
            output_file = os.path.join(self.save_dir, f"features_{self.session_id}_{email_safe}.xlsx")
        
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            # Eyes closed features
            if self.calibration_data['eyes_closed']['features']:
                df_ec = pd.DataFrame(self.calibration_data['eyes_closed']['features'])
                df_ec.to_excel(writer, sheet_name='Eyes_Closed', index=False)
            
            # Eyes open features
            if self.calibration_data['eyes_open']['features']:
                df_eo = pd.DataFrame(self.calibration_data['eyes_open']['features'])
                df_eo.to_excel(writer, sheet_name='Eyes_Open', index=False)
            
            # Task features
            if self.calibration_data['task']['features']:
                df_task = pd.DataFrame(self.calibration_data['task']['features'])
                df_task.to_excel(writer, sheet_name='Task', index=False)
            
            # Baseline statistics
            if self.baseline_stats:
                df_baseline = pd.DataFrame(self.baseline_stats).T
                df_baseline.to_excel(writer, sheet_name='Baseline_Stats')
        
        print(f"[OFFLINE ENGINE] Features exported: {output_file}")
        return output_file


def create_offline_engine(sample_rate: int = 500, channel_count: int = 64, user_email: str = None, **kwargs) -> OfflineMultichannelEngine:
    """Factory function to create an OfflineMultichannelEngine.
    
    Args:
        sample_rate: Sampling rate in Hz
        channel_count: Number of EEG channels
        user_email: User's email for filename identification
        **kwargs: Additional arguments for OfflineMultichannelEngine
    
    Returns:
        Configured OfflineMultichannelEngine instance
    """
    return OfflineMultichannelEngine(
        sample_rate=sample_rate,
        channel_count=channel_count,
        user_email=user_email,
        **kwargs
    )
