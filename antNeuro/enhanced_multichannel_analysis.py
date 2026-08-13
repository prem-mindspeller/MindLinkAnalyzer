#!/usr/bin/env python3
"""
Enhanced 64-Channel Feature Analysis Engine for ANT Neuro EEG

This module provides FULL multi-channel EEG feature extraction:
- Per-channel features (15+ features × 64 channels = 960+ features)
- Regional features (frontal, central, parietal, occipital, temporal averages)
- Spatial features (left-right asymmetry, inter-hemispheric coherence)
- Cross-channel connectivity

Total: ~1,500-2,000 features per analysis window

Author: BrainLink Companion Team
Date: February 2026
"""

import numpy as np
import time
from collections import deque
from typing import Optional, Dict, List, Any, Tuple
from scipy import signal
from scipy.stats import kurtosis, skew
import warnings

# Suppress numpy warnings for cleaner output
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Import base engine components
try:
    from BrainLinkAnalyzer_GUI_Enhanced import (
        EnhancedFeatureAnalysisEngine,
        EnhancedAnalyzerConfig
    )
    from BrainLinkAnalyzer_GUI import (
        EEG_BANDS,
        compute_psd,
        bandpower,
        notch_filter,
        bandpass_filter
    )
    BASE_ENGINE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import base engine: {e}")
    BASE_ENGINE_AVAILABLE = False
    
    # Create minimal fallback types for standalone usage
    EnhancedAnalyzerConfig = type('EnhancedAnalyzerConfig', (), {})
    EnhancedFeatureAnalysisEngine = object
    
    EEG_BANDS = {
        'delta': (0.5, 4),
        'theta': (4, 8),
        'alpha': (8, 13),
        'beta': (13, 30),
        'gamma': (30, 45)
    }


# Standard 10-20 electrode names for 64-channel cap (NA-265 layout)
CHANNEL_NAMES_64 = [
    # Connector 1: Channels 0-31
    'Fp1', 'Fp2', 'F9', 'F7', 'F3', 'Fz', 'F4', 'F8',
    'F10', 'FC5', 'FC1', 'FC2', 'FC6', 'T9', 'T7', 'C3',
    'C4', 'T8', 'T10', 'CP5', 'CP1', 'CP2', 'CP6', 'P9',
    'P7', 'P3', 'Pz', 'P4', 'P8', 'P10', 'O1', 'O2',
    # Connector 2: Channels 32-63
    'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6',
    'FC3', 'FCz', 'FC4', 'C5', 'C1', 'C2', 'C6', 'CP3',
    'CP4', 'P5', 'P1', 'P2', 'P6', 'PO5', 'PO3', 'PO4',
    'PO6', 'FT7', 'FT8', 'TP7', 'TP8', 'PO7', 'PO8', 'POz'
]

# Regional channel groupings for spatial analysis
CHANNEL_REGIONS = {
    'frontal': ['Fp1', 'Fp2', 'F7', 'F3', 'Fz', 'F4', 'F8', 'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6', 'F9', 'F10'],
    'central': ['FC5', 'FC1', 'FC2', 'FC6', 'C3', 'C4', 'FC3', 'FCz', 'FC4', 'C5', 'C1', 'C2', 'C6'],
    'temporal': ['T7', 'T8', 'T9', 'T10', 'FT7', 'FT8', 'TP7', 'TP8'],
    'parietal': ['CP5', 'CP1', 'CP2', 'CP6', 'P7', 'P3', 'Pz', 'P4', 'P8', 'CP3', 'CP4', 'P5', 'P1', 'P2', 'P6', 'P9', 'P10'],
    'occipital': ['O1', 'O2', 'PO5', 'PO3', 'PO4', 'PO6', 'PO7', 'PO8', 'POz']
}

# Hemispheric pairs for asymmetry analysis
ASYMMETRY_PAIRS = [
    ('Fp1', 'Fp2'), ('F7', 'F8'), ('F3', 'F4'), ('FC5', 'FC6'), ('FC1', 'FC2'),
    ('T7', 'T8'), ('C3', 'C4'), ('CP5', 'CP6'), ('CP1', 'CP2'),
    ('P7', 'P8'), ('P3', 'P4'), ('O1', 'O2'),
    ('AF7', 'AF8'), ('AF3', 'AF4'), ('F5', 'F6'), ('F1', 'F2'),
    ('FC3', 'FC4'), ('C5', 'C6'), ('C1', 'C2'), ('CP3', 'CP4'),
    ('P5', 'P6'), ('P1', 'P2'), ('PO5', 'PO6'), ('PO3', 'PO4'), ('PO7', 'PO8'),
    ('FT7', 'FT8'), ('TP7', 'TP8')
]

# Key channel indices for quick access
KEY_CHANNELS = {
    'attention': ['Fz', 'FCz', 'Pz'],  # Midline for attention/focus
    'memory': ['F3', 'F4', 'P3', 'P4'],  # Frontal-parietal for working memory
    'relaxation': ['O1', 'O2', 'Pz'],  # Posterior for alpha/relaxation
    'emotion': ['F3', 'F4', 'Fp1', 'Fp2'],  # Frontal for emotional processing
}


class Enhanced64ChannelEngine(EnhancedFeatureAnalysisEngine if BASE_ENGINE_AVAILABLE else object):
    """
    Full 64-channel EEG feature analysis engine.
    
    Features extracted:
    - Per-channel: 15+ features × 64 channels = 960+ features
    - Regional: Average features per brain region (5 regions × 15 features)
    - Asymmetry: Left-right power asymmetry for 27 electrode pairs × 5 bands
    - Coherence: Inter-regional coherence in each frequency band
    
    Total: ~1,500-2,000 features per analysis window
    """
    
    def __init__(
        self,
        sample_rate: int = 500,
        channel_count: int = 64,
        channel_names: List[str] = None,
        config: Optional[EnhancedAnalyzerConfig] = None,
        extract_all_channels: bool = True,
        extract_spatial: bool = True
    ):
        """
        Initialize the 64-channel engine.
        
        Args:
            sample_rate: Sampling rate in Hz (default 500 for ANT Neuro)
            channel_count: Number of channels (default 64)
            channel_names: List of channel names (default NA-265 layout)
            config: EnhancedAnalyzerConfig for analysis parameters
            extract_all_channels: If True, extract features from all 64 channels
            extract_spatial: If True, extract spatial/cross-channel features
        """
        # Initialize parent if available
        if BASE_ENGINE_AVAILABLE:
            super().__init__(config=config)
        else:
            self.config = config
            self.calibration_data = {
                'eyes_closed': {'features': [], 'timestamps': []},
                'eyes_open': {'features': [], 'timestamps': []},
                'task': {'features': [], 'timestamps': []},
                'tasks': {}
            }
            self.current_state = 'idle'
            self.current_task = None
            self.baseline_stats = {}
            self.latest_features = {}
        
        # Multi-channel configuration
        self.fs = sample_rate
        self.channel_count = min(channel_count, 64)  # Cap at 64 for now
        self.channel_names = channel_names or CHANNEL_NAMES_64[:self.channel_count]
        self.extract_all_channels = extract_all_channels
        self.extract_spatial = extract_spatial
        
        # Create channel name to index mapping
        self.channel_index = {name: i for i, name in enumerate(self.channel_names)}
        
        # Precompute region indices for fast lookup
        self.region_indices = {}
        for region, channels in CHANNEL_REGIONS.items():
            indices = [self.channel_index[ch] for ch in channels if ch in self.channel_index]
            if indices:
                self.region_indices[region] = indices
        
        # Precompute asymmetry pair indices
        self.asymmetry_indices = []
        for left, right in ASYMMETRY_PAIRS:
            if left in self.channel_index and right in self.channel_index:
                self.asymmetry_indices.append((
                    left, right,
                    self.channel_index[left],
                    self.channel_index[right]
                ))
        
        # Primary channel for single-channel compatibility (Fz)
        self.primary_channel = 'Fz'
        self.primary_channel_idx = self.channel_index.get('Fz', 5)
        
        # Multi-channel buffer settings
        self.window_size = 2.0  # 2 second windows
        self.window_samples = int(self.window_size * self.fs)
        self.step_samples = int(self.window_samples * 0.5)  # 50% overlap
        
        # Multi-channel buffer: stores full multi-channel samples
        self.multichannel_buffer = deque(maxlen=self.fs * 10)
        
        # Single-channel buffer for compatibility with parent class
        self.raw_buffer = deque(maxlen=self.fs * 10)
        
        # Sample counter
        self._sample_count = 0
        self._last_feature_time = 0
        
        # Frequency bands for multi-channel analysis
        self.bands = {
            'delta': (0.5, 4),
            'theta': (4, 8),
            'alpha': (8, 13),
            'beta': (13, 30),
            'gamma': (30, 45)
        }
        
        # Precompute filter coefficients for each band
        self._band_filters = {}
        for band_name, (low, high) in self.bands.items():
            try:
                nyq = self.fs / 2
                low_n = max(0.01, low / nyq)
                high_n = min(0.99, high / nyq)
                b, a = signal.butter(4, [low_n, high_n], btype='band')
                self._band_filters[band_name] = (b, a)
            except:
                pass
        
        # Estimate feature count
        per_ch_features = 17  # Features per channel (5 bands × 3 metrics + 2 ratios)
        n_regions = len(self.region_indices)
        n_asym_pairs = len(self.asymmetry_indices)
        
        total_features = (
            per_ch_features * self.channel_count +  # Per-channel features
            12 * n_regions +                        # Regional averages
            len(self.bands) * n_asym_pairs +        # Asymmetry features
            len(self.bands) * 5 +                   # Inter-regional coherence
            15                                       # Global + GFP features
        )
        
        print(f"[64CH ENGINE] Initialized: {channel_count} channels @ {sample_rate} Hz")
        print(f"[64CH ENGINE] Regions: {list(self.region_indices.keys())}")
        print(f"[64CH ENGINE] Asymmetry pairs: {len(self.asymmetry_indices)}")
        print(f"[64CH ENGINE] Estimated features per window: ~{total_features}")
        print(f"[64CH ENGINE] Extract all channels: {extract_all_channels}")
        print(f"[64CH ENGINE] Extract spatial features: {extract_spatial}")
    
    def add_data(self, new_data):
        """
        Add new EEG data and process it.
        
        Accepts:
        - Single value (float): Primary channel sample
        - 1D array (n_channels,): Single multi-channel sample
        - 1D array (n_samples,): Multiple single-channel samples
        - 2D array (n_samples, n_channels): Batch of multi-channel samples
        """
        if np.isscalar(new_data):
            # Single value - treat as primary channel only
            self.raw_buffer.append(new_data)
            self._sample_count += 1
        elif isinstance(new_data, np.ndarray):
            if new_data.ndim == 1:
                if len(new_data) == self.channel_count:
                    # Single multi-channel sample
                    self.raw_buffer.append(new_data[self.primary_channel_idx])
                    self.multichannel_buffer.append(new_data.copy())
                    self._sample_count += 1
                else:
                    # Multiple single-channel samples
                    self.raw_buffer.extend(new_data)
                    self._sample_count += len(new_data)
            elif new_data.ndim == 2:
                if new_data.shape[1] == self.channel_count:
                    # Batch of multi-channel samples (n_samples, n_channels)
                    primary_values = new_data[:, self.primary_channel_idx]
                    self.raw_buffer.extend(primary_values)
                    for sample in new_data:
                        self.multichannel_buffer.append(sample.copy())
                    self._sample_count += len(new_data)
                else:
                    # Assume single-channel batch
                    self.raw_buffer.extend(new_data.flatten())
                    self._sample_count += new_data.size
        else:
            arr = np.array(new_data)
            return self.add_data(arr)
        
        # Process if we have enough multi-channel data
        if len(self.multichannel_buffer) >= self.window_samples:
            # Throttle feature extraction to avoid overwhelming the system
            current_time = time.time()
            if current_time - self._last_feature_time >= 0.5:  # Max 2 Hz feature extraction
                self._last_feature_time = current_time
                
                # Get multi-channel window
                mc_window = np.array(list(self.multichannel_buffer)[-self.window_samples:])
                
                # Extract full multi-channel features
                features = self.extract_multichannel_features(mc_window)
                
                if features is not None:
                    self.latest_features = features
                    
                    # Store based on current state
                    if self.current_state == 'eyes_closed':
                        self.calibration_data['eyes_closed']['features'].append(features)
                        self.calibration_data['eyes_closed']['timestamps'].append(time.time())
                    elif self.current_state == 'eyes_open':
                        self.calibration_data['eyes_open']['features'].append(features)
                        self.calibration_data['eyes_open']['timestamps'].append(time.time())
                    elif self.current_state == 'task':
                        self.calibration_data['task']['features'].append(features)
                        self.calibration_data['task']['timestamps'].append(time.time())
                        if self.current_task:
                            tasks = self.calibration_data.setdefault('tasks', {})
                            bucket = tasks.setdefault(self.current_task, {'features': [], 'timestamps': []})
                            bucket['features'].append(features)
                            bucket['timestamps'].append(time.time())
                    
                    return features
        
        return None
    
    def extract_multichannel_features(self, mc_data: np.ndarray) -> Dict[str, float]:
        """
        Extract comprehensive features from multi-channel EEG data.
        
        Args:
            mc_data: Shape (n_samples, n_channels) multi-channel EEG window
        
        Returns:
            Dictionary with ~1,500-2,000 features
        """
        features = {}
        n_samples, n_channels = mc_data.shape
        
        # Validate data
        if n_samples < 256 or n_channels < 1:
            return None
        
        # Remove DC offset per channel
        mc_data = mc_data - np.mean(mc_data, axis=0, keepdims=True)
        
        # Apply notch filter for line noise (vectorized across channels)
        try:
            b_notch, a_notch = signal.iirnotch(60.0, 30.0, self.fs)
            mc_data = signal.filtfilt(b_notch, a_notch, mc_data, axis=0)
        except:
            pass
        
        # Compute PSD for all channels at once using Welch method
        nperseg = min(n_samples, 256)
        try:
            freqs, psd_all = signal.welch(mc_data, self.fs, nperseg=nperseg, axis=0)
        except:
            return None
        
        # psd_all shape: (n_freqs, n_channels)
        
        # ==================================================================
        # 1. PER-CHANNEL FEATURES (if enabled)
        # ==================================================================
        if self.extract_all_channels:
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
                
                # Cross-band ratios for this channel
                alpha_power = features.get(f'{ch_name}_alpha_power', 0)
                theta_power = features.get(f'{ch_name}_theta_power', 0)
                beta_power = features.get(f'{ch_name}_beta_power', 0)
                
                features[f'{ch_name}_alpha_theta_ratio'] = float(alpha_power / (theta_power + 1e-10))
                features[f'{ch_name}_beta_alpha_ratio'] = float(beta_power / (alpha_power + 1e-10))
                features[f'{ch_name}_total_power'] = float(total_power)
        
        # ==================================================================
        # 2. REGIONAL AVERAGE FEATURES
        # ==================================================================
        for region_name, ch_indices in self.region_indices.items():
            if not ch_indices:
                continue
            
            # Average PSD across channels in this region
            region_psd = np.mean(psd_all[:, ch_indices], axis=1)
            total_power = np.sum(region_psd) + 1e-12
            
            for band_name, (low, high) in self.bands.items():
                mask = (freqs >= low) & (freqs <= high)
                band_power = np.sum(region_psd[mask])
                
                features[f'{region_name}_{band_name}_power'] = float(band_power)
                features[f'{region_name}_{band_name}_relative'] = float(band_power / total_power)
            
            # Regional ratios
            alpha = features.get(f'{region_name}_alpha_power', 0)
            theta = features.get(f'{region_name}_theta_power', 0)
            beta = features.get(f'{region_name}_beta_power', 0)
            
            features[f'{region_name}_alpha_theta_ratio'] = float(alpha / (theta + 1e-10))
            features[f'{region_name}_beta_alpha_ratio'] = float(beta / (alpha + 1e-10))
            features[f'{region_name}_total_power'] = float(total_power)
        
        # ==================================================================
        # 3. SPATIAL FEATURES (if enabled)
        # ==================================================================
        if self.extract_spatial:
            # 3a. LEFT-RIGHT ASYMMETRY
            # Asymmetry Index = ln(Right) - ln(Left)
            # Positive = right hemisphere dominant, Negative = left dominant
            for left_name, right_name, left_idx, right_idx in self.asymmetry_indices:
                left_psd = psd_all[:, left_idx]
                right_psd = psd_all[:, right_idx]
                
                for band_name, (low, high) in self.bands.items():
                    mask = (freqs >= low) & (freqs <= high)
                    left_power = np.sum(left_psd[mask]) + 1e-12
                    right_power = np.sum(right_psd[mask]) + 1e-12
                    
                    # Asymmetry index (Davidson method)
                    asym = np.log(right_power) - np.log(left_power)
                    features[f'asym_{left_name}_{right_name}_{band_name}'] = float(asym)
            
            # 3b. FRONTAL ALPHA ASYMMETRY (FAA) - key marker for emotional processing
            if 'F3' in self.channel_index and 'F4' in self.channel_index:
                f3_idx = self.channel_index['F3']
                f4_idx = self.channel_index['F4']
                alpha_mask = (freqs >= 8) & (freqs <= 13)
                f3_alpha = np.sum(psd_all[alpha_mask, f3_idx]) + 1e-12
                f4_alpha = np.sum(psd_all[alpha_mask, f4_idx]) + 1e-12
                features['frontal_alpha_asymmetry'] = float(np.log(f4_alpha) - np.log(f3_alpha))
            
            # 3c. INTER-REGIONAL COHERENCE
            # Compute coherence between key region pairs
            region_pairs = [
                ('frontal', 'parietal'),
                ('frontal', 'occipital'),
                ('central', 'parietal'),
                ('temporal', 'parietal'),
                ('frontal', 'temporal')
            ]
            
            for region1, region2 in region_pairs:
                if region1 in self.region_indices and region2 in self.region_indices:
                    # Use representative channel from each region
                    idx1 = self.region_indices[region1][0]
                    idx2 = self.region_indices[region2][0]
                    
                    # Compute coherence
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
            
            # 3d. GLOBAL FIELD POWER (GFP) - measure of overall brain activity
            gfp = np.std(mc_data, axis=1)  # Standard deviation across channels at each time point
            features['gfp_mean'] = float(np.mean(gfp))
            features['gfp_std'] = float(np.std(gfp))
            features['gfp_max'] = float(np.max(gfp))
        
        # ==================================================================
        # 4. SUMMARY FEATURES (always extracted)
        # ==================================================================
        # Global average band powers
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
        
        # Number of channels with good signal
        channel_powers = np.sum(psd_all, axis=0)
        features['n_good_channels'] = int(np.sum(channel_powers > np.percentile(channel_powers, 10)))
        features['n_features_extracted'] = len(features)
        
        return features
    
    def extract_features(self, window_data):
        """
        Override parent's single-channel extract_features for compatibility.
        Falls back to parent implementation for single-channel data.
        """
        if BASE_ENGINE_AVAILABLE:
            return super().extract_features(window_data)
        else:
            return self._basic_extract_features(window_data)
    
    def _basic_extract_features(self, window_data):
        """Basic single-channel feature extraction fallback"""
        features = {}
        window_data = window_data - np.mean(window_data)
        
        try:
            nperseg = min(len(window_data), 256)
            freqs, psd = signal.welch(window_data, self.fs, nperseg=nperseg)
        except:
            return None
        
        total_power = np.sum(psd) + 1e-12
        
        for band_name, (low, high) in self.bands.items():
            mask = (freqs >= low) & (freqs <= high)
            power = np.sum(psd[mask])
            features[f'{band_name}_power'] = float(power)
            features[f'{band_name}_relative'] = float(power / total_power)
        
        features['total_power'] = float(total_power)
        return features
    
    def start_calibration_phase(self, phase: str, task_type: str = None):
        """Start a calibration phase"""
        self.current_state = phase
        self.current_task = task_type
        self.state_start_time = time.time()
        
        feature_count = len(self.calibration_data.get(phase, {}).get('features', []))
        print(f"[64CH ENGINE] Started {phase} phase (task: {task_type})")
        print(f"[64CH ENGINE] Existing features in {phase}: {feature_count}")
    
    def stop_calibration_phase(self):
        """Stop the current calibration phase"""
        if self.current_state == 'idle':
            return
        
        duration = time.time() - self.state_start_time if self.state_start_time else 0
        phase = self.current_state
        feature_count = len(self.calibration_data.get(phase, {}).get('features', []))
        
        print(f"Stopped calibration phase: {phase}")
        print(f"Duration: {duration:.1f}s, Features collected: {feature_count}")
        
        if feature_count > 0:
            # Report feature count
            sample_features = self.calibration_data[phase]['features'][0]
            print(f"Features per window: {len(sample_features)}")
        
        if phase == 'task' and self.current_task:
            tasks = self.calibration_data.get('tasks', {})
            task_bucket = tasks.get(self.current_task, {})
            task_features = len(task_bucket.get('features', []))
            if task_features > 0:
                print(f"Task '{self.current_task}' saved with {task_features} feature windows")
        
        self.current_state = 'idle'
        self.current_task = None
        self.state_start_time = None
    
    def set_log_function(self, log_func):
        """Set logging function for compatibility"""
        self._log_func = log_func
    
    def compute_baseline_statistics(self):
        """Compute baseline statistics from eyes-closed data"""
        if BASE_ENGINE_AVAILABLE:
            return super().compute_baseline_statistics()
        
        ec_features = self.calibration_data['eyes_closed']['features']
        if not ec_features:
            print("No eyes-closed features for baseline")
            return False
        
        import pandas as pd
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
        
        print(f"[64CH ENGINE] Baseline computed from {len(ec_features)} windows")
        print(f"[64CH ENGINE] Total features in baseline: {len(self.baseline_stats)}")
        return True


def create_enhanced_engine(sample_rate: int = 500, channel_count: int = 64, **kwargs) -> Enhanced64ChannelEngine:
    """
    Factory function to create an Enhanced64ChannelEngine.
    """
    config = EnhancedAnalyzerConfig() if BASE_ENGINE_AVAILABLE else None
    return Enhanced64ChannelEngine(
        sample_rate=sample_rate,
        channel_count=channel_count,
        config=config,
        extract_all_channels=True,
        extract_spatial=True,
        **kwargs
    )
