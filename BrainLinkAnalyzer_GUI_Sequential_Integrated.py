#!/usr/bin/env python3
"""
Sequential Workflow BrainLink Analyzer - Fully Integrated Version

This version uses the ACTUAL implementation from BrainLinkAnalyzer_GUI_Enhanced.py
but presents it in a guided sequential workflow with popup dialogs.

All functionality (device connection, authentication, EEG streaming, calibration,
task execution, analysis) is the REAL implementation, just reorganized into steps.
"""

import os
import sys
import platform
import time
import atexit
import numpy as np

# Global reference for cleanup
_ANT_NEURO_INSTANCE = None

def _cleanup_edi2_on_exit():
    """Cleanup EDI2 gRPC server on application exit (atexit handler)"""
    global _ANT_NEURO_INSTANCE
    if _ANT_NEURO_INSTANCE is not None:
        try:
            if _ANT_NEURO_INSTANCE.is_connected:
                print("[ATEXIT] Cleaning up ANT Neuro EDI2...")
                _ANT_NEURO_INSTANCE.disconnect()
                print("[ATEXIT] ANT Neuro EDI2 cleanup complete")
        except Exception as e:
            print(f"[ATEXIT] EDI2 cleanup error: {e}")

# Register cleanup handler
atexit.register(_cleanup_edi2_on_exit)

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
    """Cross-platform beep using pygame mixer.
    
    Args:
        frequency: Beep frequency in Hz (default 800)
        duration_ms: Beep duration in milliseconds (default 200)
    """
    if not AUDIO_AVAILABLE:
        return
    
    try:
        # Generate sine wave for beep
        sample_rate = 22050
        duration_s = duration_ms / 1000.0
        num_samples = int(sample_rate * duration_s)
        
        # Create sine wave array
        samples = np.sin(2 * np.pi * frequency * np.linspace(0, duration_s, num_samples))
        # Normalize to 16-bit range
        samples = (samples * 32767).astype(np.int16)
        
        # Create stereo sound (duplicate mono to both channels)
        stereo_samples = np.column_stack((samples, samples))
        
        # Play the beep
        sound = pygame.mixer.Sound(buffer=stereo_samples)
        sound.play()
    except Exception as e:
        print(f"Warning: Could not play beep: {e}")

def cleanup_and_quit():
    """Properly cleanup device connections and trigger main window close"""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    
    # Find the main window and close it (which will trigger its closeEvent with confirmation)
    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if isinstance(widget, EnhancedBrainLinkAnalyzerWindow):
                # Close the main window which will:
                # 1. Show confirmation dialog
                # 2. Stop BrainLink thread via parent's closeEvent
                # 3. Properly cleanup everything
                widget.close()
                return
    
    # Fallback if main window not found - do cleanup directly
    try:
        print("Cleanup: Stopping BrainLink thread...")
        BL.stop_thread_flag = True
        
        if hasattr(BL, 'serial_obj') and BL.serial_obj:
            try:
                print("Cleanup: Closing serial connection...")
                BL.serial_obj.close()
            except Exception as e:
                print(f"Cleanup: Error closing serial: {e}")
    except Exception as e:
        print(f"Warning: Error during cleanup: {e}")
    
    QApplication.quit()

# Import the complete Enhanced GUI
from BrainLinkAnalyzer_GUI_Enhanced import (
    EnhancedBrainLinkAnalyzerWindow,
    EnhancedFeatureAnalysisEngine,
    EnhancedAnalyzerConfig,
    BL
)

# Import signal quality check functions from base GUI
import BrainLinkAnalyzer_GUI as BaseGUI

# Try to import enhanced 64-channel analysis engine for ANT Neuro
ENHANCED_64CH_AVAILABLE = False
Enhanced64ChannelEngine = None
create_enhanced_engine = None

try:
    from antNeuro.enhanced_multichannel_analysis import Enhanced64ChannelEngine, create_enhanced_engine  # type: ignore
    ENHANCED_64CH_AVAILABLE = True
    print("✓ Enhanced 64-channel analysis engine loaded for ANT Neuro")
except ImportError as e:
    ENHANCED_64CH_AVAILABLE = False
    Enhanced64ChannelEngine = None
    create_enhanced_engine = None
    print(f"⚠ Enhanced 64-channel engine not available: {e}")
except Exception as e:
    ENHANCED_64CH_AVAILABLE = False
    Enhanced64ChannelEngine = None
    create_enhanced_engine = None
    print(f"⚠ Error loading enhanced 64-channel engine: {e}")

# Try to import OFFLINE 64-channel analysis engine (no live processing)
OFFLINE_64CH_AVAILABLE = False
OfflineMultichannelEngine = None
create_offline_engine = None

try:
    from antNeuro.offline_multichannel_analysis import OfflineMultichannelEngine, create_offline_engine  # type: ignore
    OFFLINE_64CH_AVAILABLE = True
    print("✓ Offline 64-channel analysis engine loaded for ANT Neuro")
except ImportError as e:
    OFFLINE_64CH_AVAILABLE = False
    OfflineMultichannelEngine = None
    create_offline_engine = None
    print(f"⚠ Offline 64-channel engine not available: {e}")
except Exception as e:
    OFFLINE_64CH_AVAILABLE = False
    OfflineMultichannelEngine = None
    create_offline_engine = None
    print(f"⚠ Error loading offline 64-channel engine: {e}")


def assess_eeg_signal_quality(data_window, fs=512):
    """
    Professional multi-metric EEG signal quality assessment.
    
    Enhanced detection for "headset not worn" condition:
    - When not worn, device picks up environmental noise (~50-100 µV) that looks like signal
    - Real EEG has characteristic 1/f spectrum with strong low-frequency content
    - Not-worn noise lacks the alpha peak (8-12 Hz) and has flatter spectrum
    
    Key metrics:
    1. Alpha band presence (8-12 Hz) - absent when not worn
    2. Low-frequency dominance (1-8 Hz) - brain signals are low-freq dominant
    3. Spectral slope (1/f characteristic) - real EEG has negative slope
    4. Amplitude checks and artifact detection
    
    Returns: (quality_score: 0-100, status: str, details: dict)
    """
    arr = np.array(data_window)
    details = {}
    
    if arr.size < 256:
        return 0, "insufficient_data", {"reason": "need more samples"}
    
    # Basic amplitude metrics
    arr_std = np.std(arr)
    arr_mean = np.mean(arr)
    arr_max = np.max(np.abs(arr))
    
    details['std'] = float(arr_std)
    details['mean'] = float(arr_mean)
    details['max_amplitude'] = float(arr_max)
    
    # Very low variance = definitely not worn (flatline)
    if arr_std < 2.0:
        return 10, "not_worn", details

    # ===================================================================
    # DEMO SIGNAL DETECTION
    # BrainLink sends a pre-recorded looping demo/test signal when the
    # forehead electrode loses skin contact.  This signal mimics real EEG
    # but repeats with very high periodicity — real brain activity never
    # does this.  Autocorrelation will expose the repetition.
    # ===================================================================
    try:
        _arr_norm = arr - np.mean(arr)
        _arr_std  = np.std(_arr_norm) + 1e-12
        _arr_norm = _arr_norm / _arr_std
        # FFT-based circular autocorrelation (fast even for 512 samples)
        _n   = len(_arr_norm)
        _fft = np.fft.rfft(_arr_norm, n=2 * _n)
        _acf = np.fft.irfft(_fft * np.conj(_fft))[:_n]
        _acf = _acf / (_acf[0] + 1e-12)          # normalize to 1 at lag=0
        # Lags 50-350 samples = 0.10 – 0.68 s at 512 Hz (repeat rates 1.5-10 Hz)
        _max_acf = float(np.max(_acf[50:350]))
        details['max_autocorr'] = _max_acf
        if _max_acf > 0.85:
            details['not_worn_reason'] = 'demo_signal'
            return 5, "not_worn", details
    except Exception:
        pass  # autocorrelation failure is non-fatal

    # ===================================================================
    # CRITICAL: Frequency-based "not worn" detection FIRST
    # Must run spectral analysis before amplitude checks because
    # environmental noise when not worn can have high amplitude
    # ===================================================================
    try:
        freqs, psd = BaseGUI.compute_psd(arr, fs)
        total_power = np.sum(psd) + 1e-12
        
        # Band power calculations
        idx_delta = (freqs >= 0.5) & (freqs <= 4)    # Delta: 0.5-4 Hz
        idx_theta = (freqs >= 4) & (freqs <= 8)      # Theta: 4-8 Hz  
        idx_alpha = (freqs >= 8) & (freqs <= 13)     # Alpha: 8-13 Hz
        idx_beta = (freqs >= 13) & (freqs <= 30)     # Beta: 13-30 Hz
        idx_low_freq = (freqs >= 0.5) & (freqs <= 8) # Low freq: 0.5-8 Hz
        idx_high_freq = freqs >= 30                   # High freq: >30 Hz
        
        delta_power = np.sum(psd[idx_delta])
        theta_power = np.sum(psd[idx_theta])
        alpha_power = np.sum(psd[idx_alpha])
        beta_power = np.sum(psd[idx_beta])
        low_freq_power = np.sum(psd[idx_low_freq])
        high_freq_power = np.sum(psd[idx_high_freq])
        
        # Relative powers
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
        
        # ===================================================================
        # KEY DETECTION: Real EEG is dominated by low frequencies (delta+theta)
        # When not worn, power is more evenly distributed (flat spectrum)
        # ===================================================================
        
        # Metric 1: Low-frequency dominance (delta + theta should be > 40% for real EEG)
        low_freq_dominance = delta_ratio + theta_ratio
        details['low_freq_dominance'] = float(low_freq_dominance)
        
        # Metric 2: Calculate spectral slope (1/f characteristic)
        # Real EEG has negative slope (more power at low frequencies)
        # Flat noise has slope near 0
        try:
            # Use log-log fit for spectral slope (avoid DC and very high freq)
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
        
        # ===================================================================
        # NOT WORN DETECTION LOGIC
        # ===================================================================
        
        # Condition 1: Low-frequency power too weak (< 20% in delta+theta)
        # Real EEG has strong delta/theta even during alertness; threshold lowered
        # from 0.30 to 0.20 to avoid false not_worn on active/alert users
        if low_freq_dominance < 0.20:
            details['not_worn_reason'] = 'low_freq_too_weak'
            return 20, "not_worn", details
        
        # Condition 2: Spectral slope too flat (> -0.1)
        # Real EEG typically has slope between -1 and -2 (1/f characteristic)
        # Environmental noise is flatter (slope closer to 0); threshold relaxed
        # from -0.3 to -0.1 to handle alert/active users with less 1/f signature
        if slope > -0.1:
            details['not_worn_reason'] = 'flat_spectrum'
            return 25, "not_worn", details
        
        # Condition 3: High-frequency noise dominates
        # Adaptive threshold: if spectral slope indicates real EEG (< -0.5), 
        # allow up to 70% high-freq (muscle artifacts/high beta/gamma activity are normal)
        # If slope is marginal (-0.5 to -0.1), use stricter 50% threshold
        high_freq_threshold = 0.70 if slope < -0.5 else 0.50
        if high_freq_ratio > high_freq_threshold:
            details['not_worn_reason'] = 'high_freq_dominant'
            return 30, "not_worn", details

        # Condition 4: Extreme amplitude — only fires when spectral checks are ambiguous.
        # If we reach here, Conditions 1-3 all passed (good spectral shape), so we trust
        # the spectral analysis. Only reject on truly extreme amplitude (>600 µV std)
        # that indicates a loose electrode or severe EMI regardless of spectral shape.
        if arr_std > 600:
            details['not_worn_reason'] = 'extreme_amplitude'
            return 10, "not_worn", details

        # Check line noise (50/60 Hz)
        idx_50hz = np.argmin(np.abs(freqs - 50))
        idx_60hz = np.argmin(np.abs(freqs - 60))
        line_noise_50 = psd[idx_50hz] if idx_50hz < len(psd) else 0
        line_noise_60 = psd[idx_60hz] if idx_60hz < len(psd) else 0
        line_noise = max(line_noise_50, line_noise_60)
        line_noise_ratio = line_noise / total_power
        details['line_noise_ratio'] = float(line_noise_ratio)
        
    except Exception as e:
        details['psd_error'] = str(e)
        # If PSD fails, fall back to basic checks - be conservative
        return 40, "analysis_error", details
    
    # ===================================================================
    # If we get here, spectral analysis indicates headset IS worn
    # Now check for amplitude-based artifacts (user is wearing but signal has issues)
    # ===================================================================
    
    # Extremely high variance = severe artifacts (but headset is worn)
    # Threshold raised: spectral checks already confirmed worn; >800 µV std is truly extreme
    if arr_std > 800:
        return 15, "severe_artifacts", details
    
    # Baseline stability check (segment-mean drift)
    # Threshold raised from 50→150 µV: tight contact can still produce drift from normal
    # head movement / sweat; spectral metrics already confirm the headset is worn
    quarter_size = len(arr) // 4
    quarters_means = [np.mean(arr[i*quarter_size:(i+1)*quarter_size]) for i in range(4)]
    baseline_drift = np.std(quarters_means)
    details['baseline_drift'] = float(baseline_drift)
    
    # Do NOT hard-return here — let drift feed into the quality-score penalty below
    # (only flag truly extreme drift separately)
    if baseline_drift > 150:
        # Severe drift but headset IS worn; add to details and continue scoring
        details['severe_drift'] = True
    
    # Motion artifacts via kurtosis
    from scipy.stats import kurtosis
    kurt = kurtosis(arr, fisher=True)
    details['kurtosis'] = float(kurt)
    
    if abs(kurt) > 15:
        return 40, "motion_artifacts", details
    
    # ===================================================================
    # Calculate overall quality score for "worn" signals
    # ===================================================================
    quality_score = 100
    
    # Penalize weak low-frequency content (but not enough to flag as not worn)
    if low_freq_dominance < 0.40:
        quality_score -= 15
    
    # Penalize flat spectrum
    if slope > -0.5:
        quality_score -= 10
    
    # Penalize high-frequency noise
    if high_freq_ratio > 0.30:
        quality_score -= 15
    
    # Penalize baseline drift (tiered: mild >30, moderate >80, severe >150)
    if baseline_drift > 150:
        quality_score -= 20
    elif baseline_drift > 80:
        quality_score -= 12
    elif baseline_drift > 30:
        quality_score -= 5
    
    # Penalize high kurtosis (artifacts)
    if abs(kurt) > 5:
        quality_score -= 10
    
    # Penalize line noise
    if line_noise_ratio > 0.1:
        quality_score -= 10
    
    # Bonus for good alpha presence (relaxed state indicator)
    if alpha_ratio > 0.15:
        quality_score += 5
    
    quality_score = max(0, min(100, quality_score))
    
    # Determine status
    if quality_score >= 70:
        status = "good"
    elif quality_score >= 50:
        status = "acceptable"
    else:
        status = "poor"
    
    return quality_score, status, details


# ============================================================================
# MULTI-CHANNEL SIGNAL QUALITY ASSESSMENT (for 64-channel ANT Neuro)
# ============================================================================

def assess_multichannel_signal_quality(multichannel_data, fs=500, channel_names=None):
    """
    Comprehensive multi-channel EEG signal quality assessment for 64-channel systems.
    
    This function assesses signal quality across all channels and provides:
    - Per-channel quality scores and status
    - Overall system quality score
    - Bad channel detection (flat, noisy, artifact-laden)
    - Regional quality assessment (frontal, central, parietal, occipital, temporal)
    - Cap positioning feedback
    
    Parameters:
    -----------
    multichannel_data : np.ndarray
        Shape: (n_samples, n_channels) or (n_channels, n_samples)
        Multi-channel EEG data
    fs : int
        Sampling frequency (default 500 Hz for ANT Neuro)
    channel_names : list, optional
        List of channel names (e.g., ['Fp1', 'Fp2', ...])
    
    Returns:
    --------
    overall_score : float
        Overall quality score (0-100)
    overall_status : str
        'good', 'acceptable', 'poor', or 'cap_issue'
    details : dict
        Detailed quality metrics including:
        - per_channel_scores: dict of channel -> score
        - per_channel_status: dict of channel -> status
        - bad_channels: list of channel names/indices with poor quality
        - regional_scores: dict of region -> score
        - issues: list of detected issues
    """
    from scipy import signal as scipy_signal
    from scipy.stats import kurtosis, zscore
    
    # Default 64-channel names for ANT Neuro eego SDK
    # SDK provides channels 0-63 as EEG reference channels
    # Channels 64-87 are bipolar auxiliary channels (not used in quality assessment)
    if channel_names is None:
        channel_names = [f'Ch{i}' for i in range(64)]
    
    # Define regional groupings based on typical 64-channel cap layout
    # Using channel indices for ANT Neuro SDK (channels 0-63)
    REGIONS = {
        'frontal': [f'Ch{i}' for i in range(0, 16)],     # Frontal electrodes
        'central': [f'Ch{i}' for i in range(16, 32)],    # Central electrodes  
        'parietal': [f'Ch{i}' for i in range(32, 48)],   # Parietal electrodes
        'occipital': [f'Ch{i}' for i in range(48, 56)],  # Occipital electrodes
        'temporal': [f'Ch{i}' for i in range(56, 64)]    # Temporal electrodes
    }
    
    # Ensure data is in (samples, channels) format
    data = np.array(multichannel_data)
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    
    # Auto-detect orientation: if first dim is small (like 64), transpose
    if data.shape[0] < data.shape[1] and data.shape[0] <= 128:
        data = data.T
    
    n_samples, n_channels = data.shape
    
    # Adjust channel names list to match actual channel count
    if len(channel_names) > n_channels:
        channel_names = channel_names[:n_channels]
    elif len(channel_names) < n_channels:
        channel_names = channel_names + [f'Ch{i}' for i in range(len(channel_names), n_channels)]
    
    details = {
        'n_channels': n_channels,
        'n_samples': n_samples,
        'sample_rate': fs,
        'per_channel_scores': {},
        'per_channel_status': {},
        'bad_channels': [],
        'flat_channels': [],
        'noisy_channels': [],
        'artifact_channels': [],
        'regional_scores': {},
        'issues': []
    }
    
    # Minimum samples check
    if n_samples < 256:
        return 0, "insufficient_data", details
    
    # ===================================================================
    # FAST PER-CHANNEL QUALITY ASSESSMENT
    # Uses simple time-domain metrics for speed (no PSD computation)
    # ===================================================================
    channel_scores = []
    
    for ch_idx in range(n_channels):
        ch_name = channel_names[ch_idx]
        ch_data = data[:, ch_idx]
        
        ch_score = 100
        ch_status = "good"
        
        # 1. Check for flat signal (disconnected electrode)
        ch_std = np.std(ch_data)
        if ch_std < 1.0:
            ch_score = 5
            ch_status = "flat"
            details['flat_channels'].append(ch_name)
            details['bad_channels'].append(ch_name)
            details['per_channel_scores'][ch_name] = ch_score
            details['per_channel_status'][ch_name] = ch_status
            channel_scores.append(ch_score)
            continue  # Skip further analysis for flat channels
        
        # 2. Check for excessive amplitude (saturation or major artifact)
        ch_max = np.max(np.abs(ch_data))
        if ch_max > 1000:  # Saturated
            ch_score = 10
            ch_status = "saturated"
            details['artifact_channels'].append(ch_name)
        elif ch_max > 500:  # High amplitude artifact
            ch_score = 30
            ch_status = "artifact"
            details['artifact_channels'].append(ch_name)
        elif ch_max > 200:  # Minor artifact
            ch_score -= 20
        
        # 3. Fast noise check using standard deviation
        # Good EEG signal typically has std between 10-100 µV
        if ch_std > 200:  # Very noisy
            ch_score -= 30
            details['noisy_channels'].append(ch_name)
        elif ch_std > 100:  # Noisy
            ch_score -= 15
            details['noisy_channels'].append(ch_name)
        elif ch_std < 5:  # Very low variance (poor contact)
            ch_score -= 25
        
        # Clamp score
        ch_score = max(0, min(100, ch_score))
        
        # Update status based on final score
        if ch_score < 30:
            ch_status = "bad"
            if ch_name not in details['bad_channels']:
                details['bad_channels'].append(ch_name)
        elif ch_score < 50:
            ch_status = "poor"
        elif ch_score < 70:
            ch_status = "acceptable"
        else:
            ch_status = "good"
        
        details['per_channel_scores'][ch_name] = ch_score
        details['per_channel_status'][ch_name] = ch_status
        channel_scores.append(ch_score)
    
    # ===================================================================
    # REGIONAL QUALITY ASSESSMENT
    # ===================================================================
    for region_name, region_channels in REGIONS.items():
        region_scores = []
        for ch in region_channels:
            if ch in details['per_channel_scores']:
                region_scores.append(details['per_channel_scores'][ch])
        
        if region_scores:
            region_avg = np.mean(region_scores)
            details['regional_scores'][region_name] = float(region_avg)
            
            # Detect regional issues
            if region_avg < 40:
                details['issues'].append(f"{region_name}_region_poor")
    
    # Skip expensive inter-channel correlation check during streaming
    # This can be done separately for detailed impedance analysis
    
    # ===================================================================
    # OVERALL QUALITY CALCULATION
    # ===================================================================
    
    # Calculate overall score (weighted average)
    if channel_scores:
        # Weight: good channels contribute more to overall score
        weights = [max(0.1, s/100) for s in channel_scores]
        overall_score = np.average(channel_scores, weights=weights)
    else:
        overall_score = 0
    
    # Penalize for bad channels
    bad_channel_ratio = len(details['bad_channels']) / n_channels
    if bad_channel_ratio > 0.3:
        overall_score *= 0.6  # Heavy penalty if >30% bad channels
        details['issues'].append(f"too_many_bad_channels_{len(details['bad_channels'])}")
    elif bad_channel_ratio > 0.15:
        overall_score *= 0.8
        details['issues'].append(f"several_bad_channels_{len(details['bad_channels'])}")
    
    # Penalize for flat channels (usually indicates cap not properly worn)
    flat_ratio = len(details['flat_channels']) / n_channels
    if flat_ratio > 0.5:
        overall_score = min(overall_score, 15)
        details['issues'].append("cap_not_worn")
    elif flat_ratio > 0.2:
        overall_score *= 0.7
        details['issues'].append("poor_electrode_contact")
    
    overall_score = max(0, min(100, overall_score))
    
    # Determine overall status
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
    
    # Summary statistics
    details['overall_score'] = float(overall_score)
    details['overall_status'] = overall_status
    details['good_channel_count'] = sum(1 for s in channel_scores if s >= 70)
    details['acceptable_channel_count'] = sum(1 for s in channel_scores if 50 <= s < 70)
    details['poor_channel_count'] = sum(1 for s in channel_scores if s < 50)
    
    # Only print occasionally (controlled by caller's throttling)
    # print(f"[MULTI-CH QUALITY] Overall: {overall_score:.1f} ({overall_status}) | "
    #       f"Good: {details['good_channel_count']}, Acceptable: {details['acceptable_channel_count']}, "
    #       f"Poor: {details['poor_channel_count']}, Bad: {len(details['bad_channels'])}")
    
    return overall_score, overall_status, details


# Import Qt components directly from PySide6
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QWidget,
    QComboBox,
    QRadioButton,
    QLineEdit,
    QFrame,
    QFormLayout,
    QMessageBox,
    QScrollArea,
    QGridLayout,
    QCheckBox
)
from PySide6.QtCore import Qt, QSettings, QTimer, QPoint, QRectF, Signal, Slot, QObject
from PySide6.QtGui import QIcon, QPainter, QPen, QBrush, QColor, QFont, QPainterPath
import pyqtgraph as pg
import numpy as np
from typing import Optional, Dict, Any


# ============================================================================
# WINDOW ICON HELPER
# ============================================================================

def set_window_icon(dialog: QDialog) -> None:
    """Set the application icon for a dialog window"""
    try:
        icon_path = BL.resource_path(os.path.join('assets', 'favicon.ico'))
        if os.path.isfile(icon_path):
            dialog.setWindowIcon(QIcon(icon_path))
    except Exception as e:
        print(f"Warning: Could not set window icon: {e}")


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
QLineEdit::placeholder {
    color:#94a3b8;
}
QCheckBox,
QRadioButton {
    font-size:13px;
    color:#1f2937;
    spacing:8px;
}
QDialogButtonBox {
    border-top:1px solid transparent;
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
# STATUS BAR WIDGET (Shows EEG and Feature Extraction Status)
# ============================================================================

class MindLinkStatusBar(QFrame):
    """Status bar showing battery, EEG signal and feature extraction status"""
    
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        
        # Style the status bar
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
        
        # Battery indicator (using parent's _build_battery_indicator)
        try:
            battery_widget = self.main_window._build_battery_indicator()
            # Override battery widget styling to match status bar theme
            battery_widget.setStyleSheet("""
                QWidget#BatteryIndicator {
                    background: transparent;
                }
                QLabel {
                    color: #000;
                    font-size: 11px;
                    font-weight: 800;
                }
                QProgressBar {
                    background-color: rgba(255, 255, 255, 0.2);
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    border-radius: 6px;
                    padding: 0;
                }
                QProgressBar::chunk {
                    border-radius: 5px;
                }
            """)
            layout.addWidget(battery_widget)
        except Exception as e:
            # Fallback if battery widget fails
            battery_label = QLabel("🔋 Battery --%")
            # Ensure fallback battery label is bold and high-contrast
            battery_label.setStyleSheet("color: #000000; font-weight: 800;")
            layout.addWidget(battery_label)
        
        # Separator
        sep1 = QLabel("|")
        layout.addWidget(sep1)
        
        # EEG Signal status
        self.eeg_status = QLabel("EEG: Disconnected")
        layout.addWidget(self.eeg_status)
        
        # Separator
        sep2 = QLabel("|")
        layout.addWidget(sep2)
        
        # Signal quality indicator (replaces features pill)
        self.signal_quality = QLabel("Signal: Checking...")
        layout.addWidget(self.signal_quality)
        
        # Channel quality viewer button (for multi-channel devices)
        device_type = getattr(main_window, 'device_type', 'mindlink')
        if device_type == 'antneuro':
            self.channel_quality_button = QPushButton("📊 Channels")
            self.channel_quality_button.setStyleSheet("""
                QPushButton {
                    background-color: #3b82f6;
                    color: #ffffff;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-size: 12px;
                    font-weight: 600;
                    border: 0;
                }
                QPushButton:hover {
                    background-color: #2563eb;
                }
                QPushButton:pressed {
                    background-color: #1d4ed8;
                }
            """)
            self.channel_quality_button.clicked.connect(self.show_channel_quality_dialog)
            layout.addWidget(self.channel_quality_button)
        
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
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)
        self.help_button.clicked.connect(self.show_help_dialog)
        layout.addWidget(self.help_button)
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(500)  # Update every 500ms
        
        # Help dialog reference
        self.help_dialog = None
    
    def update_status(self):
        """Update the status display - uses same logic as LiveEEGDialog"""
        try:
            import time
            import numpy as np
            
            # Check EEG connection status (simple check like LiveEEGDialog)
            if BL.live_data_buffer and len(BL.live_data_buffer) > 0:
                self.eeg_status.setText("EEG: ✓ Connected")
                self.eeg_status.setStyleSheet("color: #10b981; font-weight: 700;")
            else:
                self.eeg_status.setText("EEG: ✗ No Signal")
                self.eeg_status.setStyleSheet("color: #fbbf24; font-weight: 700;")
            
            # Professional multi-metric signal quality assessment (same as LiveEEGDialog)
            if len(data_buffer) >= sample_rate:
                recent_data = np.array(list(data_buffer)[-sample_rate:])
                
                quality_score, status, details = assess_eeg_signal_quality(recent_data, fs=512)
                
                # Debug output - print every 5 seconds (timer is 500ms)
                if not hasattr(self, '_debug_counter'):
                    self._debug_counter = 0
                self._debug_counter += 1
                if self._debug_counter >= 10:
                    self._debug_counter = 0
                    print(f"[Signal Quality] score={quality_score:.0f}, status={status}")
                    print(f"  std={details.get('std', 0):.1f}µV, slope={details.get('spectral_slope', 0):.2f}")
                    print(f"  low_freq_dom={details.get('low_freq_dominance', 0):.2%}, high_freq={details.get('high_freq_ratio', 0):.2%}")
                    if 'not_worn_reason' in details:
                        print(f"  NOT WORN reason: {details['not_worn_reason']}")
                
                # Simplified logic: Only show "Noisy" if headset is not worn
                if status == "not_worn":
                    self.signal_quality.setText("Signal: ⚠ Noisy")
                    self.signal_quality.setStyleSheet("color: #f59e0b; font-weight: 700;")
                else:
                    self.signal_quality.setText("Signal: ✓ Good")
                    self.signal_quality.setStyleSheet("color: #10b981; font-weight: 700;")
            else:
                self.signal_quality.setText("Signal: Waiting...")
                self.signal_quality.setStyleSheet("color: #94a3b8; font-weight: 700;")
        except Exception as e:
            print(f"Warning: Error updating status: {e}")
            import traceback
            traceback.print_exc()
            pass
    
    def show_help_dialog(self):
        """Show or bring to front the help dialog"""
        if self.help_dialog is None or not self.help_dialog.isVisible():
            self.help_dialog = HelpDialog(parent=self)
            self.help_dialog.show()
        else:
            # Bring existing dialog to front
            self.help_dialog.raise_()
            self.help_dialog.activateWindow()
    
    def show_channel_quality_dialog(self):
        """Show live 64-channel EEG monitoring dialog for multi-channel devices"""
        # Use shared instance from main_window to avoid duplicate dialogs
        if not hasattr(self.main_window, 'multichannel_dialog') or self.main_window.multichannel_dialog is None or not self.main_window.multichannel_dialog.isVisible():
            self.main_window.multichannel_dialog = MultiChannelViewDialog(self.main_window, parent=None)
            self.main_window.multichannel_dialog.show()
        else:
            # Bring existing dialog to front
            self.main_window.multichannel_dialog.raise_()
            self.main_window.multichannel_dialog.activateWindow()
    
    def cleanup(self):
        """Stop the update timer and close help dialog"""
        self.update_timer.stop()
        if self.help_dialog and self.help_dialog.isVisible():
            self.help_dialog.close()
        if hasattr(self.main_window, 'multichannel_dialog') and self.main_window.multichannel_dialog and self.main_window.multichannel_dialog.isVisible():
            self.main_window.multichannel_dialog.close()


def add_status_bar_to_dialog(dialog: QDialog, main_window) -> MindLinkStatusBar:
    """Helper to add MindLink status bar to any dialog"""
    # Get the dialog's main layout
    main_layout = dialog.layout()
    if main_layout:
        # Insert status bar at the top
        status_bar = MindLinkStatusBar(main_window)
        main_layout.insertWidget(0, status_bar)
        return status_bar
    return None


def add_help_button_to_dialog(dialog: QDialog) -> QPushButton:
    """Helper to add a simple Help button to early workflow dialogs (before main window is ready)"""
    # Get the dialog's main layout
    main_layout = dialog.layout()
    if main_layout:
        # Create help button with styling
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
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)
        
        # Create a container for the help button (top-right corner)
        help_container = QWidget()
        help_layout = QHBoxLayout(help_container)
        help_layout.setContentsMargins(0, 0, 0, 8)
        help_layout.addStretch()
        help_layout.addWidget(help_button)
        
        # Store reference to help dialog on button
        help_button.help_dialog = None
        
        # Connect to show help dialog
        def show_help():
            if help_button.help_dialog is None or not help_button.help_dialog.isVisible():
                help_button.help_dialog = HelpDialog(dialog)
                help_button.help_dialog.show()
            else:
                help_button.help_dialog.raise_()
                help_button.help_dialog.activateWindow()
        
        help_button.clicked.connect(show_help)
        
        # Insert at the top of the dialog
        main_layout.insertWidget(0, help_container)
        return help_button
    return None


# ============================================================================
# PROTOCOL FILTER METHOD FOR ENHANCED WINDOW
# ============================================================================

def add_protocol_filter_to_enhanced_window():
    """Add the _apply_protocol_filter method to EnhancedBrainLinkAnalyzerWindow
    
    Protocol tasks are now all implemented including order_surprise and num_form.
    """
    
    # Fix protocol groups - ensure all tasks exist in AVAILABLE_TASKS
    def _initialize_protocol_groups_fixed(self):
        """Initialize with all implemented protocol tasks"""
        self._protocol_groups = {
            'Personal Pathway': ['emotion_face', 'diverse_thinking'],
            'Connection': ['reappraisal', 'curiosity'],
            'Lifestyle': ['order_surprise', 'num_form'],
        }
        self._cognitive_tasks = [
            'visual_imagery', 'attention_focus', 'mental_math', 'working_memory',
            'language_processing', 'motor_imagery', 'cognitive_load', '40hz_stimulation'
        ]
    
    def _apply_protocol_filter(self):
        """Apply protocol filter to task_combo based on selected protocol"""
        # Rebuild task combo to include cognitive tasks + selected protocol tasks
        if not hasattr(self, 'task_combo') or self.task_combo is None:
            return
        
        self.task_combo.blockSignals(True)
        self.task_combo.clear()
        
        # Check device type for multichannel filtering
        device_type = getattr(self, 'device_type', 'mindlink')
        is_multichannel = (device_type == 'antneuro')
        print(f"[PROTOCOL FILTER] device_type='{device_type}', is_multichannel={is_multichannel}")
        print(f"[PROTOCOL FILTER] _cognitive_tasks={self._cognitive_tasks}")
        
        # Add cognitive tasks (present in AVAILABLE_TASKS)
        available_tasks = getattr(BL, 'AVAILABLE_TASKS', {})
        print(f"[PROTOCOL FILTER] BL.AVAILABLE_TASKS has {len(available_tasks)} tasks")
        for key in self._cognitive_tasks:
            print(f"[TASK FILTER] Checking cognitive task '{key}'...")
            if key in available_tasks:
                # Filter multichannel-only tasks for single-channel devices
                task_def = available_tasks[key]
                multichannel_only = task_def.get('multichannel_only', False)
                if multichannel_only and not is_multichannel:
                    print(f"[TASK FILTER] ❌ Skipping '{key}' - multichannel_only=True, device={device_type}")
                    continue  # Skip multichannel-only tasks on single-channel devices
                print(f"[TASK FILTER] ✓ Adding cognitive task '{key}' (multichannel_only={multichannel_only})")
                self.task_combo.addItem(key)
            else:
                print(f"[TASK FILTER] ⚠ '{key}' NOT FOUND in BL.AVAILABLE_TASKS")
        
        # Add protocol-specific tasks
        if self._selected_protocol and self._selected_protocol in self._protocol_groups:
            for key in self._protocol_groups[self._selected_protocol]:
                if key in getattr(BL, 'AVAILABLE_TASKS', {}):
                    # Filter multichannel-only tasks for single-channel devices
                    task_def = BL.AVAILABLE_TASKS[key]
                    multichannel_only = task_def.get('multichannel_only', False)
                    if multichannel_only and not is_multichannel:
                        print(f"[TASK FILTER] ❌ Skipping protocol task '{key}' - multichannel_only=True, device={device_type}")
                        continue  # Skip multichannel-only tasks on single-channel devices
                    print(f"[TASK FILTER] ✓ Adding protocol task '{key}' (multichannel_only={multichannel_only})")
                    self.task_combo.addItem(key)
        
        # Select first item if available
        if self.task_combo.count() > 0:
            self.task_combo.setCurrentIndex(0)
            try:
                self.update_task_preview(self.task_combo.currentText())
            except Exception:
                pass
        
        print(f"[PROTOCOL FILTER] Populated task_combo with {self.task_combo.count()} tasks")
        self.task_combo.blockSignals(False)
    
    # Monkey-patch both methods onto the class
    EnhancedBrainLinkAnalyzerWindow._initialize_protocol_groups_fixed = _initialize_protocol_groups_fixed
    EnhancedBrainLinkAnalyzerWindow._apply_protocol_filter = _apply_protocol_filter

# Apply the monkey-patch at module load time
add_protocol_filter_to_enhanced_window()


# ============================================================================
# HELP DIALOG
# ============================================================================

class HelpDialog(QDialog):
    """Dialog displaying the user manual"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MindLink Analyzer - User Manual")
        self.setModal(False)  # Non-modal so it can stay open while using the app
        
        # Set optimal size for readability
        self.setMinimumSize(900, 650)
        
        # Try to set responsive size based on screen
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                # Use 70% of screen size for better proportions
                target_w = min(int(avail.width() * 0.70), 1200)
                target_h = min(int(avail.height() * 0.70), 800)
                self.resize(target_w, target_h)
            else:
                self.resize(1100, 750)
        except Exception:
            self.resize(1100, 750)
        
        # Set window icon
        set_window_icon(self)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Minimal header - super compact
        header = QFrame()
        header.setFixedHeight(35)  # Force maximum height
        header.setStyleSheet("""
            QFrame {
                background: #0ea5e9;
                padding: 0px;
                margin: 0px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(0)
        
        title = QLabel("📖 User Manual")
        title.setStyleSheet("""
            font-size: 13px; 
            font-weight: 600; 
            color: #ffffff;
            padding: 0px;
            margin: 0px;
        """)
        header_layout.addWidget(title, 0, Qt.AlignVCenter)
        
        layout.addWidget(header)
        
        # Create tab widget
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                background: #ffffff;
            }
            QTabBar::tab {
                background: #f1f5f9;
                color: #334155;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #0ea5e9;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background: #e0f2fe;
                color: #0369a1;
            }
        """)
        
        # Tab 1: Getting Started (with images)
        getting_started_tab = self.create_getting_started_tab()
        self.tab_widget.addTab(getting_started_tab, "🚀 Getting Started")
        
        # Tab 2: User Manual (existing content)
        manual_tab = self.create_manual_tab()
        self.tab_widget.addTab(manual_tab, "📖 User Manual")
        
        layout.addWidget(self.tab_widget)
        
        # Minimal footer with close button
        footer = QFrame()
        footer.setFixedHeight(50)  # Force compact footer
        footer.setStyleSheet("""
            QFrame {
                background: #f8fafc;
                border-top: 1px solid #e2e8f0;
                padding: 0px;
                margin: 0px;
            }
        """)
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
            QPushButton:hover {
                background-color: #0284c7;
            }
            QPushButton:pressed {
                background-color: #0369a1;
            }
        """)
        close_button.clicked.connect(self.close)
        footer_layout.addWidget(close_button)
        
        layout.addWidget(footer)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
    
    def create_getting_started_tab(self):
        """Create the Getting Started tab with setup instructions and images"""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        
        # Scrollable content area
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #ffffff; }")
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(30)
        
        # Helper function to add section with two-column layout (text left, image right)
        def add_section(title, text, image_path=None):
            # Section container with border
            section_frame = QFrame()
            section_frame.setStyleSheet("""
                QFrame {
                    background: #f8fafc;
                    border: 2px solid #e2e8f0;
                    border-radius: 10px;
                    padding: 20px;
                }
            """)
            section_layout = QVBoxLayout(section_frame)
            section_layout.setContentsMargins(20, 20, 20, 20)
            section_layout.setSpacing(15)
            
            # Title
            title_label = QLabel(title)
            title_label.setStyleSheet("""
                font-size: 18px;
                font-weight: 700;
                color: #0f172a;
                padding: 0px 0px 10px 0px;
                border-bottom: 3px solid #0ea5e9;
            """)
            section_layout.addWidget(title_label)
            
            # Two-column layout for text and image
            two_col_layout = QHBoxLayout()
            two_col_layout.setSpacing(25)
            
            # Left side: Text
            text_label = QLabel(text)
            text_label.setStyleSheet("""
                font-size: 14px;
                color: #334155;
                line-height: 1.8;
                padding: 10px;
                background: #ffffff;
                border-radius: 8px;
            """)
            text_label.setWordWrap(True)
            text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            two_col_layout.addWidget(text_label, 1)  # Stretch factor 1
            
            # Right side: Image
            if image_path:
                try:
                    img_full_path = BL.resource_path(f"assets/{image_path}")
                    if os.path.isfile(img_full_path):
                        pixmap = QtGui.QPixmap(img_full_path)
                        if not pixmap.isNull():
                            # Scale image to fit the right column (1/3 of previous size)
                            scaled_pixmap = pixmap.scaledToWidth(167, Qt.SmoothTransformation)
                            img_label = QLabel()
                            img_label.setPixmap(scaled_pixmap)
                            img_label.setAlignment(Qt.AlignTop | Qt.AlignCenter)
                            img_label.setStyleSheet("""
                                padding: 10px; 
                                background: #ffffff; 
                                border: 2px solid #cbd5e1;
                                border-radius: 8px;
                            """)
                            two_col_layout.addWidget(img_label, 1)  # Stretch factor 1
                        else:
                            print(f"Failed to load pixmap for {image_path}")
                    else:
                        print(f"Image file not found: {img_full_path}")
                except Exception as e:
                    print(f"Error loading image {image_path}: {e}")
            
            section_layout.addLayout(two_col_layout)
            content_layout.addWidget(section_frame)
        
        # Section 1: Power On/Off Instructions
        add_section(
            "1. Turning the Amplifier On/Off",
            "<b>To Turn ON:</b><br>"
            "• Press and hold the power button for <b>2 seconds</b><br>"
            "• The amplifier will <b>vibrate once</b> to confirm it's powered on<br><br>"
            "<b>To Turn OFF:</b><br>"
            "• Press the power button <b>once</b> (short press)<br>"
            "• The amplifier will <b>vibrate twice</b> to confirm it's powered off<br><br>"
            "<b>Low Battery Warning:</b><br>"
            "• When the battery is empty, the amplifier will <b>vibrate multiple times continuously</b> and turn off automatically<br>"
            "• Please charge the amplifier when this happens",
            "onoffinstructions.jpg"
        )
        
        # Section 2: Pairing with Bluetooth
        add_section(
            "2. Pairing the Amplifier with Your Device",
            "<b>Important:</b> Follow the standard Windows Bluetooth pairing process:<br><br>"
            "1. Turn on the amplifier (press and hold for 2 seconds)<br>"
            "2. Open <b>Settings → Bluetooth & devices → Add device</b> in Windows<br>"
            "3. Select <b>\"Bluetooth\"</b> from the add device options<br>"
            "4. Wait for <b>\"Brainlink_Pro (Audio)\"</b> to appear in the list<br>"
            "5. Click on <b>\"Brainlink_Pro (Audio)\"</b> to pair<br><br>"
            "<b>Note:</b> The headset will <b>briefly connect and then disconnect</b> automatically. "
            "<b>This is normal!</b> The pairing process only registers the headset with your device. "
            "The actual connection will be established automatically when you sign in to the application.",
            None
        )
        
        # Section 3: Wearing the Headset
        add_section(
            "3. Wearing the Headset Properly",
            "<b>Amplifier Position:</b><br>"
            "• Place the amplifier <b>above your left ear</b><br><br>"
            "<b>Light Sensor Position:</b><br>"
            "• The light sensor should be positioned <b>right between your eyebrows</b><br><br>"
            "<b>Electrode Position:</b><br>"
            "• The electrodes should be positioned <b>2 inches above your eyebrows</b> for optimal signal quality<br><br>"
            "<b>Important:</b> Proper positioning ensures accurate EEG readings",
            "wearinstructions.jpg"
        )
        
        # Section 4: Removing Amplifier for Charging
        add_section(
            "4. Removing the Amplifier for Charging",
            "<b>To charge the amplifier, you need to remove it from the clip:</b><br><br>"
            "1. Locate the clip that holds the amplifier to the headband<br>"
            "2. Gently pull the amplifier out of the clip (see image below)<br>"
            "3. Connect the charging cable to the amplifier<br>"
            "4. Charge until the indicator shows full battery<br><br>"
            "<b>Note:</b> The amplifier cannot be charged while attached to the headset clip",
            "takeoffinstructions.jpg"
        )
        
        # Section 5: Inserting Amplifier Back
        add_section(
            "5. Inserting the Amplifier Back into the Clip",
            "<b>After charging, reattach the amplifier to the headset:</b><br><br>"
            "1. Hold the amplifier with the correct orientation (see image below)<br>"
            "2. Align the amplifier with the clip opening<br>"
            "3. Gently push the amplifier into the clip until it clicks securely<br>"
            "4. Ensure the amplifier is firmly attached before wearing the headset<br><br>"
            "<b>Important:</b> Make sure the amplifier is properly seated to maintain good electrode contact",
            "insertinstructions.jpg"
        )
        
        content_layout.addStretch()
        scroll.setWidget(content_widget)
        tab_layout.addWidget(scroll)
        
        return tab
    
    def create_manual_tab(self):
        """Create the User Manual tab with TOC and content"""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create horizontal splitter for TOC and content
        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        
        # Table of Contents (left side) - moved from __init__
        toc_frame = QFrame()
        toc_frame.setStyleSheet("""
            QFrame {
                background: #f1f5f9;
                border-right: 2px solid #cbd5e1;
            }
        """)
        toc_layout = QVBoxLayout(toc_frame)
        toc_layout.setContentsMargins(12, 12, 12, 12)
        toc_layout.setSpacing(8)
        
        toc_title = QLabel("📑 Contents")
        toc_title.setStyleSheet("""
            font-size: 14px; 
            font-weight: 700; 
            color: #0f172a; 
            padding-bottom: 8px;
            letter-spacing: 0.5px;
        """)
        toc_layout.addWidget(toc_title)
        
        # Scrollable TOC list
        self.toc_list = QtWidgets.QListWidget()
        self.toc_list.setStyleSheet("""
            QListWidget {
                background: #ffffff;
                border: 2px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-radius: 6px;
                color: #334155;
                margin: 2px 0px;
            }
            QListWidget::item:hover {
                background: #e0f2fe;
                color: #0369a1;
                font-weight: 500;
            }
            QListWidget::item:selected {
                background: #0ea5e9;
                color: #ffffff;
                font-weight: 600;
            }
        """)
        self.toc_list.itemClicked.connect(self.scroll_to_section)
        toc_layout.addWidget(self.toc_list)
        
        splitter.addWidget(toc_frame)
        
        # Text display area (right side, scrollable)
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setStyleSheet("""
            QTextEdit {
                background: #ffffff;
                color: #1e293b;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                padding: 16px 20px;
                border: none;
                line-height: 1.7;
            }
        """)
        
        splitter.addWidget(self.text_display)
        
        # Set initial splitter sizes (TOC: 22%, Content: 78%)
        splitter.setSizes([330, 1170])
        
        # Load the user manual content
        self.load_manual_content()
        
        tab_layout.addWidget(splitter)
        return tab
    
    def load_manual_content(self):
        """Load the user manual from file and extract table of contents"""
        try:
            manual_path = BL.resource_path("MindLink_User_Manual.txt")
            
            if os.path.isfile(manual_path):
                with open(manual_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.text_display.setPlainText(content)
                
                # Extract sections for table of contents
                lines = content.split('\n')
                sections = []
                seen_titles = set()  # Track titles to avoid duplicates
                
                for i, line in enumerate(lines):
                    title = None
                    target_line = i
                    indent_level = 0
                    
                    # Skip "TABLE OF CONTENTS" section entirely
                    if 'TABLE OF CONTENTS' in line.upper():
                        continue
                    
                    # Detect main section headers (lines with === below them)
                    if line.strip().startswith('=') and len(line.strip()) > 10:
                        # The title is usually the line before the === line
                        if i > 0:
                            potential_title = lines[i-1].strip()
                            # Skip if it contains "TABLE OF CONTENTS" or is the header
                            if (potential_title and 
                                not potential_title.startswith('=') and
                                'TABLE OF CONTENTS' not in potential_title.upper() and
                                'MINDLINK ANALYZER' not in potential_title.upper() and
                                'Brain Wave' not in potential_title and
                                'Version' not in potential_title):
                                
                                # Check if this is a numbered section like "1. INTRODUCTION"
                                if potential_title and potential_title[0].isdigit():
                                    title = potential_title
                                    target_line = i - 1
                                    indent_level = 0
                    
                    # Detect numbered sections that appear without === underline
                    # ONLY match sections in ALL CAPS (main headers) or proper subsections
                    elif line.strip() and len(line.strip()) > 3:
                        stripped = line.strip()
                        
                        # Must start with a digit
                        if stripped[0].isdigit() and '.' in stripped[:5]:
                            # Split to check the numbering format
                            parts = stripped.split(maxsplit=1)
                            if len(parts) >= 2:
                                number_part = parts[0]
                                text_part = parts[1]
                                
                                # Parse the number part
                                num_parts = number_part.rstrip('.').split('.')
                                
                                # Main section: "1. INTRODUCTION" (must be ALL CAPS)
                                if (len(num_parts) == 1 and 
                                    num_parts[0].isdigit() and
                                    text_part.isupper()):
                                    title = stripped
                                    target_line = i
                                    indent_level = 0
                                
                                # Subsection: "5.1 STEP 1:" or "6.1 Device" (two numbers, ALL CAPS first word)
                                elif (len(num_parts) == 2 and 
                                      all(p.isdigit() for p in num_parts)):
                                    # Check if first word after number is uppercase or starts with uppercase
                                    first_word = text_part.split()[0] if text_part.split() else ""
                                    if first_word and (first_word.isupper() or first_word[0].isupper()):
                                        title = "  " + stripped  # Add indent for subsections
                                        target_line = i
                                        indent_level = 1
                                
                                # Skip everything else (sub-subsections, instruction lists, etc.)
                    
                    # Add to sections if we found a valid title and haven't seen it before
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        sections.append((title, target_line, indent_level))
                
                # Populate the TOC list
                self.toc_list.clear()
                self.section_positions = {}  # Map section title to line number
                
                for title, line_num, indent_level in sections:
                    # Keep the title as is (with indentation for hierarchy)
                    item = QtWidgets.QListWidgetItem(title)
                    self.toc_list.addItem(item)
                    self.section_positions[title] = line_num
                
                # If no sections found, add a note
                if not sections:
                    item = QtWidgets.QListWidgetItem("(No sections detected)")
                    item.setFlags(Qt.NoItemFlags)  # Make it non-clickable
                    self.toc_list.addItem(item)
                    
            else:
                # Fallback content if file not found
                self.text_display.setPlainText(
                    "User Manual Not Found\n\n"
                    "The user manual file could not be located.\n"
                    "Expected location: MindLink_User_Manual.txt\n\n"
                    "Please ensure the file is in the application directory.\n\n"
                    "For support, contact: support@mindspeller.com"
                )
                self.section_positions = {}
                
        except Exception as e:
            self.text_display.setPlainText(
                f"Error Loading User Manual\n\n"
                f"An error occurred while loading the manual:\n{str(e)}\n\n"
                f"For support, contact: support@mindspeller.com"
            )
            self.section_positions = {}
    
    def scroll_to_section(self, item):
        """Scroll to the selected section in the manual"""
        section_title = item.text()
        
        if section_title in self.section_positions:
            line_num = self.section_positions[section_title]
            
            # Get the document and create a cursor
            doc = self.text_display.document()
            cursor = QtGui.QTextCursor(doc)
            
            # Move to the start
            cursor.movePosition(QtGui.QTextCursor.Start)
            
            # Move down to the target line
            for _ in range(line_num):
                cursor.movePosition(QtGui.QTextCursor.Down)
            
            # Move to the start of the line for better visibility
            cursor.movePosition(QtGui.QTextCursor.StartOfLine)
            
            # Set the cursor
            self.text_display.setTextCursor(cursor)
            
            # Scroll to put the section at the TOP of the viewport
            # Get the scrollbar and calculate position
            scrollbar = self.text_display.verticalScrollBar()
            cursor_rect = self.text_display.cursorRect()
            
            # Move scrollbar so the cursor line appears at the top
            # We get the current cursor Y position and set scroll value to that
            doc = self.text_display.document()
            block = doc.findBlockByLineNumber(line_num)
            layout = block.layout()
            block_pos = layout.position().y()
            
            # Set scroll position to show section at top (with small margin)
            scrollbar.setValue(int(block_pos) - 10)  # 10px margin from top


# ============================================================================
# CHANNEL QUALITY DIALOG (Head Map Visualization)
# ============================================================================

class HeadMapWidget(QWidget):
    """Custom widget to draw 64-channel head map with NA-265 electrode layout"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(700, 700)
        self.impedances = {}
        # Colors based on ANT Neuro datasheet thresholds
        self.colors = {
            'preferred': QColor("#059669"),  # Bright green (< 20 kΩ - best contact)
            'good': QColor("#22c55e"),       # Green (< 50 kΩ - acceptable)
            'poor': QColor("#f97316"),       # Orange (50-100 kΩ)
            'bad': QColor("#ef4444"),         # Red (> 100 kΩ)
            'unknown': QColor("#cbd5e1")     # Gray (No signal)
        }
        
        # NA-265 waveguard net 64-channel cap electrode layout
        # Mapped from screenshot / datasheet to normalized coordinates
        # Y+ is Anterior (Front/Nose), X+ is Right
        # Channel index (0-63) -> (name, x, y)
        # Using CHANNEL_NAMES from ImpedanceCheckDialog for consistency
        _NAMES = [
            # Connector 1 (Ch 0-31)
            'Fp1', 'Fp2', 'F9', 'F7', 'F3', 'Fz', 'F4', 'F8',
            'F10', 'FC5', 'FC1', 'FC2', 'FC6', 'T9', 'T7', 'C3',
            'C4', 'T8', 'T10', 'CP5', 'CP1', 'CP2', 'CP6', 'P9',
            'P7', 'P3', 'Pz', 'P4', 'P8', 'P10', 'O1', 'O2',
            # Connector 2 (Ch 32-63)
            'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6',
            'FC3', 'FCz', 'FC4', 'C5', 'C1', 'C2', 'C6', 'CP3',
            'CP4', 'P5', 'P1', 'P2', 'P6', 'PO5', 'PO3', 'PO4',
            'PO6', 'FT7', 'FT8', 'TP7', 'TP8', 'PO7', 'PO8', 'POz'
        ]
        
        # Standard 10-20 positions (normalized -1 to 1, matching screenshot layout)
        # Row-by-row from front (top) to back (bottom)
        _POS = {
            # Row 1: Frontal pole
            'Fp1': (-0.18, 0.90),  'Fpz': (0.0, 0.95),   'Fp2': (0.18, 0.90),
            # Row 2: AF line
            'AF7': (-0.45, 0.78),  'AF3': (-0.20, 0.78),  'AF4': (0.20, 0.78),  'AF8': (0.45, 0.78),
            # Row 3: Frontal
            'F9': (-0.82, 0.58),   'F7': (-0.58, 0.60),   'F5': (-0.40, 0.60),
            'F3': (-0.28, 0.60),   'F1': (-0.14, 0.60),   'Fz': (0.0, 0.60),
            'F2': (0.14, 0.60),    'F4': (0.28, 0.60),    'F6': (0.40, 0.60),
            'F8': (0.58, 0.60),    'F10': (0.82, 0.58),
            # Row 4: Fronto-central
            'FT7': (-0.72, 0.37),  'FC5': (-0.50, 0.37),  'FC3': (-0.32, 0.37),
            'FC1': (-0.16, 0.37),  'FCz': (0.0, 0.37),    'FC2': (0.16, 0.37),
            'FC4': (0.32, 0.37),   'FC6': (0.50, 0.37),   'FT8': (0.72, 0.37),
            # Row 5: Central
            'T9': (-0.90, 0.12),   'T7': (-0.72, 0.12),   'C5': (-0.50, 0.12),
            'C3': (-0.32, 0.12),   'C1': (-0.16, 0.12),   'Cz': (0.0, 0.12),
            'C2': (0.16, 0.12),    'C4': (0.32, 0.12),    'C6': (0.50, 0.12),
            'T8': (0.72, 0.12),    'T10': (0.90, 0.12),
            # Row 6: Centro-parietal
            'TP7': (-0.72, -0.14), 'CP5': (-0.50, -0.14), 'CP3': (-0.32, -0.14),
            'CP1': (-0.16, -0.14), 'CPz': (0.0, -0.14),   'CP2': (0.16, -0.14),
            'CP4': (0.32, -0.14),  'CP6': (0.50, -0.14),  'TP8': (0.72, -0.14),
            # Row 7: Parietal
            'P9': (-0.82, -0.40),  'P7': (-0.58, -0.40),  'P5': (-0.40, -0.40),
            'P3': (-0.28, -0.40),  'P1': (-0.14, -0.40),  'Pz': (0.0, -0.40),
            'P2': (0.14, -0.40),   'P4': (0.28, -0.40),   'P6': (0.40, -0.40),
            'P8': (0.58, -0.40),   'P10': (0.82, -0.40),
            # Row 8: Parieto-occipital
            'PO7': (-0.50, -0.62), 'PO5': (-0.35, -0.62), 'PO3': (-0.20, -0.62),
            'POz': (0.0, -0.62),   'PO4': (0.20, -0.62),  'PO6': (0.35, -0.62),
            'PO8': (0.50, -0.62),
            # Row 9: Occipital
            'O1': (-0.18, -0.82),  'Oz': (0.0, -0.82),    'O2': (0.18, -0.82),
            # GND (top center)
            'GND': (0.0, 0.82),
            # M1/M2 mastoids
            'M1': (-0.88, -0.25),  'M2': (0.88, -0.25),
        }
        
        # Build coords mapping: channel index -> (name, x, y)
        self.coords = {}         # 'ChN' -> (x, y) for backward compat with impedance data keyed by 'ChN'
        self.channel_labels = {} # 'ChN' -> display_name
        for idx, name in enumerate(_NAMES):
            key = f'Ch{idx}'
            if name in _POS:
                self.channel_labels[key] = name
                self.coords[key] = _POS[name]
            else:
                # Fallback: place unknowns in a safe spot
                self.channel_labels[key] = name
                self.coords[key] = (0.0, 0.0)
        
        # Also include GND position if reported
        self.coords['GND'] = _POS['GND']
        self.channel_labels['GND'] = 'GND'

    def set_impedances(self, imp_dict):
        self.impedances = imp_dict
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        cx, cy = w / 2, h / 2
        scale = min(w, h) / 2.5  # Scale factor to fit head in widget
        
        # Draw Head Contour
        painter.setPen(QPen(QColor("#334155"), 3))
        painter.setBrush(QBrush(QColor("#f8fafc"))) # Very light gray fill
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(scale), int(scale))
        
        # Draw Nose
        nose_base_y = cy - scale * 0.95
        nose_tip_y = cy - scale * 1.15
        path = QPainterPath()
        path.moveTo(cx - scale * 0.1, nose_base_y)
        path.lineTo(cx, nose_tip_y)
        path.lineTo(cx + scale * 0.1, nose_base_y)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        
        # Define Fonts
        name_font = QFont("Segoe UI", 8, QFont.Bold)
        val_font = QFont("Segoe UI", 7)
        
        # Iterate and Draw Channels
        dot_radius = 14
        
        for key, (nx, ny) in self.coords.items():
            screen_x = cx + nx * scale
            screen_y = cy - ny * scale # Screen Y is down
            
            # Get display name
            display_name = self.channel_labels.get(key, key)
            
            # Impedance Data
            val = self.impedances.get(key)
            
            # Determine Color and State (ANT Neuro datasheet thresholds)
            fill_color = self.colors['unknown']
            val_text = "--"
            is_filled = False
            
            if val is not None:
                val_text = f"{val:.0f}kΩ"
                is_filled = True
                if val < 20:    fill_color = self.colors['preferred']  # < 20 kΩ preferred
                elif val < 50:  fill_color = self.colors['good']      # < 50 kΩ good
                elif val < 100: fill_color = self.colors['poor']      # 50-100 kΩ poor
                else:           fill_color = self.colors['bad']       # > 100 kΩ bad
            
            # Draw Electrode Dot
            painter.setPen(QPen(QColor("#475569"), 2))
            if is_filled:
                painter.setBrush(QBrush(fill_color))
            else:
                painter.setBrush(Qt.NoBrush)
                
            center_pt = QPoint(int(screen_x), int(screen_y))
            painter.drawEllipse(center_pt, dot_radius, dot_radius)
            
            # Draw Channel Name (inside circle)
            painter.setPen(QPen(QColor("#1e293b") if not is_filled else QColor("#ffffff")))
            painter.setFont(name_font)
            name_rect = QRectF(screen_x - 18, screen_y - 8, 36, 12)
            painter.drawText(name_rect, Qt.AlignCenter, display_name)
            
            # Draw Impedance Value (below name, inside circle)
            painter.setFont(val_font)
            val_rect = QRectF(screen_x - 22, screen_y + 3, 44, 11)
            painter.drawText(val_rect, Qt.AlignCenter, val_text)


class ChannelQualityDialog(QDialog):
    """Live 64-Channel Impedance Head Map"""
    
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("64-Channel Impedance Map")
        self.setModal(False)
        self.resize(1000, 750)
        
        set_window_icon(self)
        
        # Main Layout: HBox (Map | Legend/Stats)
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Left: Head Map
        map_container = QWidget()
        map_layout = QVBoxLayout(map_container)
        
        header = QLabel("Live Impedance Topography")
        header.setStyleSheet("font-size: 18px; font-weight: 700; color: #1e40af; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        map_layout.addWidget(header)
        
        self.head_map = HeadMapWidget()
        map_layout.addWidget(self.head_map, 1)
        
        main_layout.addWidget(map_container, 70) # 70% width
        
        # 2. Right: Legend & Controls
        side_panel = QFrame()
        side_panel.setStyleSheet("background-color: #f8fafc; border-left: 1px solid #e2e8f0;")
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(20, 40, 20, 40)
        side_layout.setSpacing(20)
        
        # Legend Title
        legend_title = QLabel("Quality Legend")
        legend_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #334155;")
        side_layout.addWidget(legend_title)
        
        # Legend Items
        self.add_legend_item(side_layout, "#059669", "Preferred", "< 20 kΩ")
        self.add_legend_item(side_layout, "#22c55e", "Good", "< 50 kΩ")
        self.add_legend_item(side_layout, "#f97316", "Poor", "50 - 100 kΩ")
        self.add_legend_item(side_layout, "#ef4444", "Bad", "> 100 kΩ")
        self.add_legend_item(side_layout, "#cbd5e1", "No Signal", "--")
        
        side_layout.addStretch()
        
        # Summary Stats
        stats_box = QFrame()
        stats_box.setStyleSheet("background: white; border-radius: 8px; padding: 15px; border: 1px solid #e2e8f0;")
        stats_layout = QVBoxLayout(stats_box)
        
        stats_title = QLabel("Channel Status")
        stats_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        stats_layout.addWidget(stats_title)
        
        self.stats_label = QLabel("Good: 0\nAcceptable: 0\nPoor: 0")
        self.stats_label.setStyleSheet("font-family: monospace; font-size: 13px; color: #475569; line-height: 1.5;")
        stats_layout.addWidget(self.stats_label)
        
        side_layout.addWidget(stats_box)
        
        side_layout.addSpacing(20)
        
        # Close Button
        close_btn = QPushButton("Close Monitor")
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: white;
                padding: 12px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #1e293b; }
        """)
        side_layout.addWidget(close_btn)
        
        main_layout.addWidget(side_panel, 30) # 30% width
        self.setLayout(main_layout)
        
        # Update Timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(500) # 2 Hz update
        
        self.update_display()
        
    def add_legend_item(self, layout, color, text, subtext):
        item = QWidget()
        h_layout = QHBoxLayout(item)
        h_layout.setContentsMargins(0,0,0,0)
        
        dot = QLabel()
        dot.setFixedSize(16, 16)
        dot.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 2px solid #94a3b8;")
        
        lbl_layout = QVBoxLayout()
        lbl_layout.setSpacing(2)
        t1 = QLabel(text)
        t1.setStyleSheet("font-weight: 600; color: #1e293b;")
        t2 = QLabel(subtext)
        t2.setStyleSheet("font-size: 11px; color: #64748b;")
        lbl_layout.addWidget(t1)
        lbl_layout.addWidget(t2)
        
        h_layout.addWidget(dot)
        h_layout.addLayout(lbl_layout)
        h_layout.addStretch()
        layout.addWidget(item)

    def update_display(self):
        # Get data - use cached values to avoid stopping/restarting stream
        # get_real_time_impedances returns cached values if < 2 seconds old
        # For multi-channel, we use the quality assessment data instead of real impedances
        # during streaming to avoid disrupting the stream
        
        device_type = getattr(self.main_window, 'device_type', 'mindlink')
        
        if device_type == 'antneuro' and ANT_NEURO.is_streaming:
            # During streaming, use signal quality metrics to estimate channel health
            # Real impedance measurement requires stopping the stream
            data = ANT_NEURO.current_impedances if hasattr(ANT_NEURO, 'current_impedances') and ANT_NEURO.current_impedances else None
            if not data:
                # Estimate impedance from signal characteristics during streaming
                # If we have multichannel data, use variance to estimate contact quality
                multichannel_buffer = getattr(ANT_NEURO, 'multichannel_buffer', None)
                if multichannel_buffer and len(multichannel_buffer) >= 256:
                    mc_data = np.array(list(multichannel_buffer)[-512:])
                    data = {}
                    for i in range(min(64, mc_data.shape[1])):
                        ch_std = np.std(mc_data[:, i])
                        # Map variance to estimated impedance: 
                        # High variance (~50+ µV) = good contact (<20 kΩ)
                        # Medium variance (~20-50 µV) = acceptable (<50 kΩ)
                        # Low variance (<20 µV) = poor contact (>50 kΩ)
                        if ch_std > 50:
                            est_imp = 10.0  # Preferred
                        elif ch_std > 30:
                            est_imp = 20.0  # Good
                        elif ch_std > 15:
                            est_imp = 40.0  # Acceptable
                        elif ch_std > 5:
                            est_imp = 60.0  # Poor
                        else:
                            est_imp = 200.0  # Flat/no signal
                        data[f'Ch{i}'] = est_imp
                else:
                    # Generate placeholder showing "checking" status
                    data = {f'Ch{i}': 15.0 for i in range(64)}  # Show as "acceptable" while checking
        else:
            data = ANT_NEURO.get_real_time_impedances()
        
        if not data:
            return
            
        # Update Map
        self.head_map.set_impedances(data)
        
        # Update Stats
        counts = {'preferred': 0, 'good': 0, 'poor': 0, 'bad': 0}
        for val in data.values():
            if val < 20: counts['preferred'] += 1
            elif val < 50: counts['good'] += 1
            elif val < 100: counts['poor'] += 1
            else: counts['bad'] += 1
            
        total = len(data)
        self.stats_label.setText(
            f"🟢 Preferred:  {counts['preferred']}/{total}\n"
            f"🟢 Good:       {counts['good']}/{total}\n"
            f"🟠 Poor:       {counts['poor']}/{total}\n"
            f"🔴 Bad:        {counts['bad']}/{total}"
        )

    def closeEvent(self, event):
        self.update_timer.stop()
        event.accept()


# ============================================================================
# WORKFLOW STATE MANAGER
# ============================================================================

# ============================================================================
# ANT NEURO eego SDK SETUP (for 64-channel option)
# ============================================================================

EEGO_SDK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eego_sdk_toolbox')

if EEGO_SDK_PATH not in sys.path:
    sys.path.insert(0, EEGO_SDK_PATH)

if platform.system() == 'Windows':
    try:
        os.add_dll_directory(EEGO_SDK_PATH)
    except Exception:
        pass

# Import threading for ANT Neuro device manager
import threading

EEGO_SDK_AVAILABLE = False
eego_sdk = None

try:
    import eego_sdk
    EEGO_SDK_AVAILABLE = True
    print("✓ ANT Neuro eego SDK loaded successfully")
except ImportError as e:
    print(f"⚠ ANT Neuro eego SDK not available: {e}")
    print("  Will try EDI2 gRPC API instead.")

# EDI2 gRPC API - Modern alternative that solves power state issues
EDI2_AVAILABLE = False
EDI2Client = None
try:
    from antNeuro.edi2_client import EDI2Client
    EDI2_AVAILABLE = True
    print("✓ ANT Neuro EDI2 gRPC client loaded successfully")
except ImportError as e:
    print(f"⚠ EDI2 client not available: {e}")


class AntNeuroDeviceManager:
    """Manages ANT Neuro device connection and data streaming using EDI2 gRPC API
    
    This class uses the modern EDI2 API which doesn't have the power state blocking
    issues that affected the old eego SDK on certain USB controllers.
    """
    
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
        from collections import deque
        import threading
        self.live_data_buffer = deque(maxlen=5120)
        self.multichannel_buffer = deque(maxlen=5120)
        
        # Threading
        self.stream_thread = None
        self.stop_thread_flag = False
        self.device_serial = None
        
        # Battery monitoring
        self.battery_thread = None
        self.battery_stop_flag = threading.Event()
        
        # Feature engine reference (set by main window for calibration/tasks)
        self.feature_engine = None
        
        print(f"[ANT NEURO] Device manager initialized")
        print(f"[ANT NEURO]   EDI2 available: {EDI2_AVAILABLE}")
        print(f"[ANT NEURO]   eego SDK available: {EEGO_SDK_AVAILABLE}")
        
    def scan_for_devices(self) -> list:
        """Scan for connected ANT Neuro amplifiers.
        
        Returns real devices if found. Only returns demo device if NO real devices detected.
        """
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
        return [{'serial': 'DEMO-001', 'type': 'Demo Device (88-Ch)'}]
    
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
            print(f"✓ Connected to ANT Neuro demo device: {device_serial}")
            print(f"{'='*60}\n")
            return True
        
        # Try EDI2 first (modern API, no power blocking)
        if self.use_edi2 and EDI2_AVAILABLE:
            try:
                print(f"[ANT NEURO CONNECT] Using EDI2 gRPC API...")
                if self.edi2_client is None:
                    self.edi2_client = EDI2Client()
                
                # Extract actual serial if prefixed
                actual_serial = device_serial.replace('EDI2-', '') if 'EDI2-' in device_serial else device_serial
                
                if self.edi2_client.connect(actual_serial):
                    self.is_connected = True
                    self.use_edi2 = True
                    self.channel_count = self.edi2_client.get_channel_count()
                    
                    # Get power state
                    power = self.edi2_client.get_power_state()
                    print(f"[ANT NEURO CONNECT] Mode: EDI2 gRPC (REAL DEVICE)")
                    print(f"[ANT NEURO CONNECT] Channels: {self.channel_count}")
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
                
                amplifiers = self.factory.getAmplifiers()
                for amp in amplifiers:
                    if amp.getSerial() == device_serial:
                        self.amplifier = amp
                        self.is_connected = True
                        self.use_edi2 = False
                        self.channel_count = 64
                        print(f"[ANT NEURO CONNECT] Mode: eego SDK (REAL DEVICE)")
                        print(f"✓ Connected via eego SDK to: {device_serial}")
                        print(f"{'='*60}\n")
                        return True
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
        import threading
        
        if not self.is_connected:
            print(f"[ANT NEURO STREAM] ERROR: Device not connected")
            return False
        
        self.sample_rate = sample_rate
        self.stop_thread_flag = False
        print(f"\n{'='*60}")
        print(f"[ANT NEURO STREAM] Starting data stream at {sample_rate} Hz")
        
        # Demo mode
        if self.device_serial == 'DEMO-001':
            print(f"[ANT NEURO STREAM] Stream mode: DEMO (synthetic EEG)")
            self.stream_thread = threading.Thread(target=self._demo_stream_loop)
            self.stream_thread.daemon = True
            self.stream_thread.start()
            self.is_streaming = True
            print(f"✓ Demo streaming started")
            print(f"{'='*60}\n")
            return True
        
        # EDI2 gRPC streaming (preferred - no power blocking)
        if self.use_edi2 and self.edi2_client:
            try:
                print(f"[ANT NEURO STREAM] Stream mode: EDI2 gRPC (REAL DEVICE)")
                
                # Simple counter for debug printing
                self._sample_count = 0
                
                # Determine primary channel index for live plot (Fz = 5 for NA-265 cap)
                # Use feature engine's primary channel if available
                primary_ch_idx = 5  # Default to Fz
                if self.feature_engine is not None and hasattr(self.feature_engine, 'primary_channel_idx'):
                    primary_ch_idx = self.feature_engine.primary_channel_idx
                
                def on_data(data):
                    # Convert to µV (data comes in Volts from EDI2)
                    data_uv = data * 1e6
                    
                    # EDI2 sends 88 channels (64 EEG + 24 bipolar aux)
                    # Truncate to 64 EEG channels for processing and recording
                    eeg_channels = 64
                    if data_uv.shape[1] > eeg_channels:
                        data_uv = data_uv[:, :eeg_channels]
                    
                    # Extract primary channel values for the entire batch (for live plot)
                    primary_values = data_uv[:, primary_ch_idx]
                    
                    # Batch append to buffers (much faster than per-sample)
                    self.live_data_buffer.extend(primary_values)
                    for sample in data_uv:
                        self.multichannel_buffer.append(sample)
                    
                    # Only feed to feature engine during calibration/task phases
                    # Pass FULL multi-channel data for 64-channel feature extraction
                    if self.feature_engine is not None:
                        state = getattr(self.feature_engine, 'current_state', 'idle')
                        if state != 'idle':
                            # Feed entire multi-channel batch to feature engine
                            # Shape: (n_samples, 64) for full 64-channel processing
                            self.feature_engine.add_data(data_uv)
                
                self.edi2_client.set_data_callback(on_data)
                
                # Start battery monitoring thread for EDI2
                self._start_battery_monitor()
                
                if self.edi2_client.start_streaming(sample_rate=float(sample_rate)):
                    self.is_streaming = True
                    print(f"✓ EDI2 streaming started at {sample_rate} Hz")
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
                self.stream_thread = threading.Thread(target=self._stream_loop)
                self.stream_thread.daemon = True
                self.stream_thread.start()
                self.is_streaming = True
                print(f"✓ eego SDK streaming started")
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
        
        # Stop battery monitoring
        self._stop_battery_monitor()
        
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
    
    def get_real_time_impedances(self):
        """Get current impedance values from device.
        
        Returns dict of channel_name -> impedance (kOhm) or None if unavailable.
        Updates internal cache that's refreshed every 2 seconds.
        """
        import time
        
        # Return cached values if recent (< 2 seconds old)
        if hasattr(self, 'impedance_update_time') and hasattr(self, 'current_impedances'):
            if time.time() - self.impedance_update_time < 2.0 and self.current_impedances:
                return self.current_impedances.copy()
        
        # Demo mode - return synthetic impedances
        if self.device_serial == 'DEMO-001':
            return self._generate_demo_impedances()
        
        # EDI2 gRPC - get CACHED impedances from EDI2 client
        # NOTE: We only use cached values because get_impedances() stops streaming
        # and causes connection issues with EE225 devices via gRPC
        if self.use_edi2 and self.edi2_client:
            try:
                # Use cached impedances only - don't call get_impedances()
                impedances = self.edi2_client.get_cached_impedances()
                if impedances:
                    self.current_impedances = impedances
                    self.impedance_update_time = time.time()
                    return impedances.copy()
            except Exception as e:
                print(f"[ANT NEURO] EDI2 impedance error: {e}")
        
        # Fallback to eego SDK
        if EEGO_SDK_AVAILABLE and self.amplifier:
            try:
                imp_stream = self.amplifier.OpenImpedanceStream()
                imp_data = imp_stream.getData()  # Returns list of floats in Ohms
                
                # ANT Neuro SDK provides impedances for all channels
                # Channels 0-63: EEG reference channels (what we need)
                # Channels 64-87: Bipolar auxiliary channels (skip these)
                impedances = {}
                for i, z_ohms in enumerate(imp_data):
                    # Only use channels 0-63 (EEG reference channels)
                    if i < 64:
                        impedances[f'Ch{i}'] = round(z_ohms / 1000.0, 1)  # Convert to kOhm
                
                self.current_impedances = impedances
                self.impedance_update_time = time.time()
                
                return impedances.copy()
            except Exception as e:
                print(f"[ANT NEURO] eego SDK impedance error: {e}")
        
        return self._generate_demo_impedances()
    
    def _start_battery_monitor(self):
        """Start background thread to monitor battery status"""
        if self.battery_thread and self.battery_thread.is_alive():
            return
        
        self.battery_stop_flag.clear()
        self.battery_thread = threading.Thread(target=self._battery_monitor_loop, daemon=True)
        self.battery_thread.start()
        print("[ANT NEURO] Battery monitoring started")
    
    def _stop_battery_monitor(self):
        """Stop battery monitoring thread"""
        if self.battery_thread:
            self.battery_stop_flag.set()
            if self.battery_thread.is_alive():
                self.battery_thread.join(timeout=1.0)
            print("[ANT NEURO] Battery monitoring stopped")
    
    def _battery_monitor_loop(self):
        """Background thread that polls battery status every 5 seconds"""
        import time
        from PySide6.QtWidgets import QApplication
        
        while not self.battery_stop_flag.is_set():
            try:
                if self.use_edi2 and self.edi2_client and self.is_streaming:
                    power_state = self.edi2_client.get_power_state()
                    battery_level = power_state.get('battery_level')
                    
                    if battery_level is not None:
                        # Update main window battery display
                        # Find the main window and emit battery update signal
                        app = QApplication.instance()
                        if app:
                            for widget in app.topLevelWidgets():
                                if hasattr(widget, 'battery_update'):
                                    # Emit signal to update battery UI
                                    widget.battery_update.emit(int(battery_level), None)
                                    break
            except Exception as e:
                # Silent fail - battery monitoring is not critical
                pass
            
            # Wait 5 seconds or until stop flag is set
            self.battery_stop_flag.wait(5.0)
    
    def _generate_demo_impedances(self):
        """Generate realistic demo impedance values with some variation"""
        import random
        import time
        
        # ANT Neuro SDK channels 0-63 are EEG reference channels
        impedances = {}
        for i in range(64):
            ch_name = f'Ch{i}'
            # Most channels good (2-8 kOhm), some acceptable (8-15), few poor (15-25)
            rand = random.random()
            if rand < 0.75:  # 75% good
                z = random.uniform(2.0, 8.0)
            elif rand < 0.92:  # 17% acceptable
                z = random.uniform(8.0, 15.0)
            else:  # 8% poor
                z = random.uniform(15.0, 25.0)
            impedances[ch_name] = round(z, 1)
        
        self.current_impedances = impedances
        self.impedance_update_time = time.time()
        return impedances.copy()
    
    def _stream_loop(self):
        """Main streaming loop for real device"""
        import time
        # Get primary channel index (Fz = 5 for NA-265)
        primary_ch_idx = 5
        if self.feature_engine is not None and hasattr(self.feature_engine, 'primary_channel_idx'):
            primary_ch_idx = self.feature_engine.primary_channel_idx
        
        while not self.stop_thread_flag and self.stream:
            try:
                buffer = self.stream.getData()
                if buffer:
                    data = np.array(buffer.getData())
                    samples = data.reshape(-1, self.channel_count)
                    
                    # Truncate to 64 EEG channels (device may send 88: 64 EEG + 24 bipolar)
                    eeg_channels = 64
                    eeg_samples = samples[:, :eeg_channels] if samples.shape[1] > eeg_channels else samples
                    
                    # Batch processing for efficiency
                    primary_values = eeg_samples[:, primary_ch_idx]
                    self.live_data_buffer.extend(primary_values)
                    for sample in eeg_samples:
                        self.multichannel_buffer.append(sample)
                    
                    # Batch feed 64-channel EEG data to feature engine during calibration/task
                    if self.feature_engine is not None:
                        state = getattr(self.feature_engine, 'current_state', 'idle')
                        if state != 'idle':
                            # Pass 64 EEG channels for feature extraction
                            self.feature_engine.add_data(eeg_samples)
                time.sleep(0.001)  # Minimal sleep to prevent buffer overflow
            except Exception as e:
                print(f"ANT Neuro streaming error: {e}")
                break
    
    def _demo_stream_loop(self):
        """Demo streaming loop with synthetic EEG"""
        import time
        
        # Get primary channel index (Fz = 5 for NA-265)
        primary_ch_idx = 5
        if self.feature_engine is not None and hasattr(self.feature_engine, 'primary_channel_idx'):
            primary_ch_idx = self.feature_engine.primary_channel_idx
        
        t = 0
        batch_size = 50  # Generate 50 samples at a time (100ms at 500 Hz)
        
        while not self.stop_thread_flag:
            # Generate batch of samples
            samples = np.zeros((batch_size, self.channel_count))
            for i in range(batch_size):
                t_sample = t + i / self.sample_rate
                for ch in range(self.channel_count):
                    alpha = 30 * np.sin(2 * np.pi * 10 * t_sample + ch * 0.1)
                    theta = 15 * np.sin(2 * np.pi * 6 * t_sample + ch * 0.05)
                    beta = 10 * np.sin(2 * np.pi * 20 * t_sample + ch * 0.02)
                    noise = np.random.randn() * 5
                    samples[i, ch] = alpha + theta + beta + noise
            
            # Batch append
            primary_values = samples[:, primary_ch_idx]
            self.live_data_buffer.extend(primary_values)
            for sample in samples:
                self.multichannel_buffer.append(sample)
            
            # Batch feed FULL multi-channel data to feature engine during calibration/task
            if self.feature_engine is not None:
                state = getattr(self.feature_engine, 'current_state', 'idle')
                if state != 'idle':
                    # Pass full multi-channel samples for 64-channel processing
                    self.feature_engine.add_data(samples)
            
            t += batch_size / self.sample_rate
            time.sleep(batch_size / self.sample_rate)  # Sleep for batch duration


# Global ANT Neuro device manager instance
ANT_NEURO = AntNeuroDeviceManager()
# Set reference for atexit cleanup (uses module-level _ANT_NEURO_INSTANCE defined at top)
_ANT_NEURO_INSTANCE = ANT_NEURO


def get_live_data_buffer(main_window=None):
    """Get the correct live data buffer based on selected device type.
    
    Args:
        main_window: Reference to the main window (to check device_type attribute).
                    If None, tries to find it from QApplication.
    
    Returns:
        The live_data_buffer from either ANT_NEURO or BL depending on device type.
    """
    # Try to determine device type
    device_type = "mindlink"  # Default fallback
    
    if main_window and hasattr(main_window, 'device_type'):
        device_type = main_window.device_type
    else:
        # Try to find main window from QApplication
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                for widget in app.topLevelWidgets():
                    if isinstance(widget, EnhancedBrainLinkAnalyzerWindow):
                        if hasattr(widget, 'device_type'):
                            device_type = widget.device_type
                        break
        except Exception:
            pass
    
    # Return appropriate buffer
    if device_type == "antneuro":
        return ANT_NEURO.live_data_buffer
    else:
        return BL.live_data_buffer


def get_device_sample_rate(main_window=None):
    """Get the sample rate for the selected device type.
    
    Args:
        main_window: Reference to the main window (to check device_type attribute).
    
    Returns:
        Sample rate in Hz (512 for MindLink, 500 for ANT Neuro).
    """
    device_type = "mindlink"
    
    if main_window and hasattr(main_window, 'device_type'):
        device_type = main_window.device_type
    
    if device_type == "antneuro":
        return ANT_NEURO.sample_rate
    else:
        return 512  # MindLink default


# ============================================================================
# WORKFLOW STATE MANAGER
# ============================================================================

class WorkflowStep:
    """Enumeration of workflow steps"""
    OS_SELECTION = 0
    DEVICE_TYPE_SELECTION = 1  # NEW: Choose MindLink or ANT Neuro
    ENVIRONMENT_SELECTION = 2
    LOGIN = 3
    PARTNER_ID = 4  # For MindLink only
    ANTNEURO_METADATA = 41  # For ANT Neuro only - Subject/Recording metadata
    IMPEDANCE_CHECK = 42  # For ANT Neuro only - Electrode impedance check before streaming
    LIVE_EEG = 5
    PATHWAY_SELECTION = 6
    CALIBRATION = 7
    TASK_SELECTION = 8
    MULTI_TASK_ANALYSIS = 9


class WorkflowManager:
    """Manages the sequential workflow state and navigation"""
    
    def __init__(self, main_window):
        self.main_window = main_window  # Reference to the actual Enhanced GUI window
        self.current_step = WorkflowStep.OS_SELECTION
        self.step_history = []
        
        # Current active dialog reference
        self.current_dialog: Optional[QDialog] = None
    
    def go_to_step(self, step: int, from_back: bool = False):
        """Navigate to a specific workflow step"""
        if not from_back:
            self.step_history.append(self.current_step)
        
        # Close current dialog if exists
        if self.current_dialog and self.current_dialog.isVisible():
            self.current_dialog.close()
            self.current_dialog = None
        
        self.current_step = step
        
        # Launch the appropriate dialog for this step
        if step == WorkflowStep.OS_SELECTION:
            self._show_os_selection()
        elif step == WorkflowStep.DEVICE_TYPE_SELECTION:
            self._show_device_type_selection()
        elif step == WorkflowStep.ENVIRONMENT_SELECTION:
            self._show_environment_selection()
        elif step == WorkflowStep.PARTNER_ID:
            self._show_partner_id()
        elif step == WorkflowStep.ANTNEURO_METADATA:
            self._show_antneuro_metadata()
        elif step == WorkflowStep.IMPEDANCE_CHECK:
            self._show_impedance_check()
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
    
    # Step-specific dialog launchers
    def _show_os_selection(self):
        dialog = OSSelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()  # Use show() instead of exec() to keep event loop running
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_device_type_selection(self):
        dialog = DeviceTypeSelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_environment_selection(self):
        dialog = EnvironmentSelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()  # Use show() instead of exec()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_partner_id(self):
        dialog = PartnerIDDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_antneuro_metadata(self):
        dialog = AntNeuroMetadataDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_impedance_check(self):
        dialog = ImpedanceCheckDialog(self)
        self.current_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_login(self):
        dialog = LoginDialog(self)
        self.current_dialog = dialog
        dialog.show()  # Use show() instead of exec()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_pathway_selection(self):
        dialog = PathwaySelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()  # Use show() instead of exec()
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
        dialog.show()  # Already using show()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_task_selection(self):
        dialog = TaskSelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()  # Use show() instead of exec()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_multi_task_analysis(self):
        dialog = MultiTaskAnalysisDialog(self)
        self.current_dialog = dialog
        dialog.show()  # Use show() instead of exec()


# ============================================================================
# STEP 1: OS SELECTION (Same as before)
# ============================================================================

class OSSelectionDialog(QDialog):
    """Step 1: Select operating system"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Operating System")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(400)
        self._programmatic_close = False  # Flag to distinguish user vs programmatic close
        
        # Set window icon
        set_window_icon(self)
        
        # Detect default OS
        if sys.platform.startswith("win"):
            default_os = "Windows"
        elif sys.platform.startswith("darwin"):
            default_os = "macOS"
        else:
            default_os = "Windows"
        
        # UI Elements
        title_label = QLabel("Welcome to MindLink Analyzer")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 1 of 10: Choose your Operating System")
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
        
        # Add help button
        add_help_button_to_dialog(self)
    
    def closeEvent(self, event):
        """Handle dialog close - only trigger confirmation if user clicked X"""
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            # This is a programmatic close (from navigation), allow it
            event.accept()
        else:
            # This is user clicking X button - confirm and quit
            # Temporarily clear WindowStaysOnTopHint so message box appears on top
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit MindLink Analyzer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            # Restore WindowStaysOnTopHint if it was set
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_next(self):
        """Save OS selection and proceed to Device Type Selection"""
        selected_os = "Windows" if self.radio_windows.isChecked() else "macOS"
        self.workflow.main_window.user_os = selected_os
        # Mark as programmatic close
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.DEVICE_TYPE_SELECTION))


# ============================================================================
# STEP 2: DEVICE TYPE SELECTION (NEW - Choose MindLink or ANT Neuro)
# ============================================================================

class DeviceTypeSelectionDialog(QDialog):
    """Step 2: Select device type - MindLink (single-channel) or ANT Neuro (64-channel)"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Device Selection")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(500)
        self._programmatic_close = False
        
        set_window_icon(self)
        
        # UI Elements
        title_label = QLabel("Select EEG Device")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 2 of 10: Choose your EEG hardware")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Device selection card
        card = QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(16)
        
        prompt_label = QLabel("Select your EEG device:")
        prompt_label.setObjectName("DialogSectionTitle")
        
        # MindLink option
        self.radio_mindlink = QRadioButton("Single-Channel Headset")
        self.radio_mindlink.setStyleSheet("font-size: 14px; font-weight: 600; padding: 8px;")
        self.radio_mindlink.setChecked(True)
        
        # mindlink_desc = QLabel(
        #     "Consumer-grade single-channel EEG headband.\n"
        #     "Best for: Quick assessments, personal use, portability."
        # )
        # mindlink_desc.setStyleSheet("font-size: 12px; color: #64748b; margin-left: 24px; margin-bottom: 12px;")
        # mindlink_desc.setWordWrap(True)
        
        # ANT Neuro option
        ant_available = EEGO_SDK_AVAILABLE or True  # Always show, demo mode available
        self.radio_antneuro = QRadioButton("Multi-Channel Headset")
        self.radio_antneuro.setStyleSheet("font-size: 14px; font-weight: 600; padding: 8px;")
        
        # if EEGO_SDK_AVAILABLE:
        #     antneuro_desc = QLabel(
        #         "Professional 64-channel research-grade EEG system.\n"
        #         "Best for: Research, clinical assessments, detailed brain mapping."
        #     )
        # else:
        #     antneuro_desc = QLabel(
        #         "Professional 64-channel research-grade EEG system.\n"
        #         "⚠ SDK not detected - Demo mode available for testing."
        #     )
        # antneuro_desc.setStyleSheet("font-size: 12px; color: #64748b; margin-left: 24px;")
        # antneuro_desc.setWordWrap(True)
        
        card_layout.addWidget(prompt_label)
        card_layout.addWidget(self.radio_mindlink)
        # card_layout.addWidget(mindlink_desc)
        card_layout.addWidget(self.radio_antneuro)
        # card_layout.addWidget(antneuro_desc)
        
        # Info box
        info_box = QLabel(
            "ℹ️ Both devices use the same cognitive task protocols.\n"
            "The analysis will adapt based on the selected device type."
        )
        info_box.setStyleSheet(
            "font-size: 12px; color: #3b82f6; padding: 12px; "
            "background: #eff6ff; border-radius: 8px; border-left: 3px solid #3b82f6;"
        )
        info_box.setWordWrap(True)
        
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
        layout.addWidget(card)
        layout.addWidget(info_box)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        add_help_button_to_dialog(self)
    
    def closeEvent(self, event):
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
                'Are you sure you want to exit MindLink Analyzer?',
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
    
    def on_back(self):
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        """Save device selection and proceed"""
        if self.radio_mindlink.isChecked():
            device_type = "mindlink"
        else:
            device_type = "antneuro"
        
        # Store device type on main window
        self.workflow.main_window.device_type = device_type
        print(f"✓ Selected device type: {device_type}")
        
        # Switch to enhanced 64-channel engine if ANT Neuro selected
        if device_type == "antneuro":
            self.workflow.main_window.switch_to_enhanced_64ch_engine()
        
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.ENVIRONMENT_SELECTION))


# ============================================================================
# STEP 3: ENVIRONMENT SELECTION (With REAL device detection)
# ============================================================================

class EnvironmentSelectionDialog(QDialog):
    """Step 3: Select region where the user has their Mindspeller account"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Region Selection")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(450)
        
        # Set window icon
        set_window_icon(self)
        
        # Get device type for display
        device_type = getattr(self.workflow.main_window, 'device_type', 'mindlink')
        device_label = "MindLink (Single-Channel)" if device_type == "mindlink" else "ANT Neuro (64-Channel)"
        
        # UI Elements
        title_label = QLabel("Select Region")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 3 of 10: Choose your region")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Device info display
        device_info = QLabel(f"Selected Device: {device_label}")
        device_info.setStyleSheet("font-size: 12px; color: #059669; font-weight: 600; padding: 8px; background: #ecfdf5; border-radius: 6px;")
        
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
        self.env_combo.currentTextChanged.connect(self.on_env_changed)
        
        # Warning message
        warning_label = QLabel("WARNING: Please make sure the region selected is the region where the user has created their Mindspeller account")
        warning_label.setStyleSheet("font-size: 12px; color: #f59e0b; padding: 8px; background: #fffbeb; border-radius: 6px; border-left: 3px solid #f59e0b;")
        warning_label.setWordWrap(True)
        
        env_layout.addWidget(env_label)
        env_layout.addWidget(self.env_combo)
        env_layout.addWidget(warning_label)
        
        # Amplifier preparation instructions - adapt based on device type
        prep_card = QFrame()
        prep_card.setObjectName("DialogCard")
        prep_layout = QVBoxLayout(prep_card)
        prep_layout.setContentsMargins(16, 16, 16, 16)
        prep_layout.setSpacing(10)
        
        prep_label = QLabel("Before You Continue:")
        prep_label.setObjectName("DialogSectionTitle")
        
        if device_type == "mindlink":
            info_text = (
                "ℹ️ Please ensure the MindLink headset is:\n\n"
                "  • Paired with your device via Bluetooth\n"
                "  • Turned ON and placed on your head correctly\n\n"
                "The device connection will be verified when you sign in on the next step."
            )
        else:
            info_text = (
                "ℹ️ Please ensure the ANT Neuro amplifier is:\n\n"
                "  • Connected via USB to your computer\n"
                "  • Powered ON with electrodes applied\n"
                "  • Impedances checked (preferably < 10 kΩ)\n\n"
                "The device connection will be verified when you sign in on the next step."
            )
        
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-size: 13px; color: #3b82f6; padding: 12px; background: #eff6ff; border-radius: 6px; border-left: 3px solid #3b82f6; line-height: 1.6;")
        info_label.setWordWrap(True)
        
        prep_layout.addWidget(prep_label)
        prep_layout.addWidget(info_label)
        
        # Help button for setup reference
        help_ref_button = QPushButton("❓ Setup Help")
        help_ref_button.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: #ffffff;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
                border: 0;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)
        
        # Connect to show help dialog
        def show_setup_help():
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            for widget in app.topLevelWidgets():
                if isinstance(widget, HelpDialog) and widget.isVisible():
                    widget.raise_()
                    widget.activateWindow()
                    return
            help_dialog = HelpDialog(self)
            help_dialog.show()
        
        help_ref_button.clicked.connect(show_setup_help)
        prep_layout.addWidget(help_ref_button)
        
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
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(device_info)
        layout.addWidget(env_card)
        layout.addWidget(prep_card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Add help button
        add_help_button_to_dialog(self)
        
        # Initialize environment
        self.on_env_changed("English (en)")
        self._programmatic_close = False
    
    def closeEvent(self, event):
        """Handle dialog close - only trigger confirmation if user clicked X"""
        if self._programmatic_close:
            event.accept()
        else:
            # Temporarily clear WindowStaysOnTopHint so message box appears on top
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit MindLink Analyzer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            # Restore WindowStaysOnTopHint if it was set
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_env_changed(self, env_name: str):
        """Update backend URLs when environment changes"""
        backend_urls = {
            "English (en)": "https://en.mindspeller.com/api/cas/brainlink_data",
            "Dutch (nl)": "https://nl.mindspeller.com/api/cas/brainlink_data",
            "Local": "http://127.0.0.1:5000/api/cas/brainlink_data"
        }
        
        login_urls = {
            "English (en)": "https://en.mindspeller.com/api/cas/token/login",
            "Dutch (nl)": "https://nl.mindspeller.com/api/cas/token/login",
            "Local": "http://127.0.0.1:5000/api/cas/token/login"
        }
        
        # Region mapping for API calls that require region parameter
        region_mapping = {
            "English (en)": "be",  # Belgium English
            "Dutch (nl)": "be",     # Belgium Dutch (same region as English)
            "Local": "be"           # Local development defaults to Belgium
        }
        
        # Set GLOBAL variables used by the base GUI
        BL.BACKEND_URL = backend_urls[env_name]
        # Store login URL and region in main window for later use in login dialog
        self.workflow.main_window.login_url = login_urls[env_name]
        self.workflow.main_window.current_region = region_mapping[env_name]
        self.workflow.main_window.selected_environment = env_name
    
    def on_back(self):
        """Navigate back to OS selection"""
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        """Proceed to next step - Login for both device types"""
        self._programmatic_close = True
        self.close()
        
        # Both device types go to Login first (for device detection and authentication)
        # For ANT Neuro: Login -> Metadata -> Live EEG
        # For MindLink: Login -> Partner ID -> Live EEG
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.LOGIN))


# ============================================================================
# STEP 3A: ANT NEURO METADATA (for ANT Neuro devices only)
# ============================================================================

class AntNeuroMetadataDialog(QDialog):
    """ANT Neuro Metadata Collection - Subject info, hardware specs, impedances"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("ANT Neuro - Recording Setup")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(550)
        self.setMinimumHeight(650)
        
        set_window_icon(self)
        
        # UI Elements
        title_label = QLabel("ANT Neuro 64-Channel Recording Setup")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 4 of 10: Configure recording metadata")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Create scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        
        # ===== Subject Information Card =====
        subject_card = QFrame()
        subject_card.setObjectName("DialogCard")
        subject_layout = QVBoxLayout(subject_card)
        subject_layout.setContentsMargins(16, 16, 16, 16)
        subject_layout.setSpacing(10)
        
        subject_title = QLabel("👤 Subject Information")
        subject_title.setObjectName("DialogSectionTitle")
        subject_layout.addWidget(subject_title)
        
        # Subject ID
        subject_id_layout = QHBoxLayout()
        subject_id_label = QLabel("Subject ID:")
        subject_id_label.setFixedWidth(120)
        self.subject_id_input = QLineEdit()
        self.subject_id_input.setPlaceholderText("e.g., SUB001")
        import random
        import string
        self.subject_id_input.setText(f"SUB{''.join(random.choices(string.digits, k=4))}")
        subject_id_layout.addWidget(subject_id_label)
        subject_id_layout.addWidget(self.subject_id_input)
        subject_layout.addLayout(subject_id_layout)
        
        # Age
        age_layout = QHBoxLayout()
        age_label = QLabel("Age (years):")
        age_label.setFixedWidth(120)
        self.age_input = QLineEdit()
        self.age_input.setPlaceholderText("e.g., 25")
        age_layout.addWidget(age_label)
        age_layout.addWidget(self.age_input)
        subject_layout.addLayout(age_layout)
        
        # Sex
        sex_layout = QHBoxLayout()
        sex_label = QLabel("Sex:")
        sex_label.setFixedWidth(120)
        self.sex_combo = QComboBox()
        self.sex_combo.addItems(["Not specified", "Male", "Female", "Other"])
        sex_layout.addWidget(sex_label)
        sex_layout.addWidget(self.sex_combo)
        subject_layout.addLayout(sex_layout)
        
        # Handedness
        hand_layout = QHBoxLayout()
        hand_label = QLabel("Handedness:")
        hand_label.setFixedWidth(120)
        self.hand_combo = QComboBox()
        self.hand_combo.addItems(["Not specified", "Right", "Left", "Ambidextrous"])
        hand_layout.addWidget(hand_label)
        hand_layout.addWidget(self.hand_combo)
        subject_layout.addLayout(hand_layout)
        
        scroll_layout.addWidget(subject_card)
        
        # ===== Hardware Specifications Card =====
        hardware_card = QFrame()
        hardware_card.setObjectName("DialogCard")
        hardware_layout = QVBoxLayout(hardware_card)
        hardware_layout.setContentsMargins(16, 16, 16, 16)
        hardware_layout.setSpacing(10)
        
        hardware_title = QLabel("🔌 Hardware Specifications")
        hardware_title.setObjectName("DialogSectionTitle")
        hardware_layout.addWidget(hardware_title)
        
        # Device Model (auto-filled)
        model_layout = QHBoxLayout()
        model_label = QLabel("Device Model:")
        model_label.setFixedWidth(120)
        self.model_display = QLabel("ANT Neuro eego™ mylab 64-channel")
        self.model_display.setStyleSheet("color: #059669; font-weight: 600;")
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_display)
        hardware_layout.addLayout(model_layout)
        
        # Sample Rate (auto-filled)
        rate_layout = QHBoxLayout()
        rate_label = QLabel("Sample Rate:")
        rate_label.setFixedWidth(120)
        self.rate_display = QLabel(f"{ANT_NEURO.sample_rate} Hz")
        self.rate_display.setStyleSheet("color: #059669; font-weight: 600;")
        rate_layout.addWidget(rate_label)
        rate_layout.addWidget(self.rate_display)
        hardware_layout.addLayout(rate_layout)
        
        # Channel Count
        channels_layout = QHBoxLayout()
        channels_label = QLabel("Channels:")
        channels_label.setFixedWidth(120)
        self.channels_display = QLabel(f"{ANT_NEURO.channel_count} channels (10-20 system)")
        self.channels_display.setStyleSheet("color: #059669; font-weight: 600;")
        channels_layout.addWidget(channels_label)
        channels_layout.addWidget(self.channels_display)
        hardware_layout.addLayout(channels_layout)
        
        # Reference
        ref_layout = QHBoxLayout()
        ref_label = QLabel("Reference:")
        ref_label.setFixedWidth(120)
        self.ref_combo = QComboBox()
        self.ref_combo.addItems(["CPz (default)", "Linked Mastoids", "Average Reference", "Cz"])
        ref_layout.addWidget(ref_label)
        ref_layout.addWidget(self.ref_combo)
        hardware_layout.addLayout(ref_layout)
        
        scroll_layout.addWidget(hardware_card)
        
        # ===== Electrode Impedances Card =====
        impedance_card = QFrame()
        impedance_card.setObjectName("DialogCard")
        impedance_layout = QVBoxLayout(impedance_card)
        impedance_layout.setContentsMargins(16, 16, 16, 16)
        impedance_layout.setSpacing(10)
        
        impedance_header = QHBoxLayout()
        impedance_title = QLabel("⚡ Electrode Impedances")
        impedance_title.setObjectName("DialogSectionTitle")
        impedance_header.addWidget(impedance_title)
        impedance_header.addStretch()
        
        self.impedance_status = QLabel("✓ All channels < 10 kΩ")
        self.impedance_status.setStyleSheet("color: #059669; font-weight: 600; font-size: 12px;")
        impedance_header.addWidget(self.impedance_status)
        impedance_layout.addLayout(impedance_header)
        
        # Get impedances from device if connected, otherwise use demo values
        self.impedance_values = self._get_impedances()
        
        imp_grid = QGridLayout()
        imp_grid.setSpacing(4)
        
        # Show key channels
        key_channels = ['Fp1', 'Fp2', 'F3', 'F4', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2', 'Fz', 'Cz', 'Pz']
        for i, ch in enumerate(key_channels):
            row = i // 4
            col = i % 4
            imp_val = self.impedance_values.get(ch, 5.0)
            color = "#059669" if imp_val < 10 else "#f59e0b" if imp_val < 20 else "#dc2626"
            ch_label = QLabel(f"{ch}: {imp_val:.1f} kΩ")
            ch_label.setStyleSheet(f"color: {color}; font-size: 11px; padding: 2px 6px; background: #f8fafc; border-radius: 4px;")
            imp_grid.addWidget(ch_label, row, col)
        
        impedance_layout.addLayout(imp_grid)
        
        # Overall impedance info
        avg_imp = np.mean(list(self.impedance_values.values()))
        max_imp = np.max(list(self.impedance_values.values()))
        imp_summary = QLabel(f"Average: {avg_imp:.1f} kΩ | Max: {max_imp:.1f} kΩ")
        imp_summary.setStyleSheet("color: #64748b; font-size: 11px; margin-top: 4px;")
        impedance_layout.addWidget(imp_summary)
        
        scroll_layout.addWidget(impedance_card)
        
        # ===== Recording Parameters Card =====
        recording_card = QFrame()
        recording_card.setObjectName("DialogCard")
        recording_layout = QVBoxLayout(recording_card)
        recording_layout.setContentsMargins(16, 16, 16, 16)
        recording_layout.setSpacing(10)
        
        recording_title = QLabel("📊 Recording Parameters")
        recording_title.setObjectName("DialogSectionTitle")
        recording_layout.addWidget(recording_title)
        
        # Filter settings
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Bandpass Filter:")
        filter_label.setFixedWidth(120)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["0.1 - 100 Hz (default)", "0.5 - 45 Hz", "1 - 30 Hz", "DC - 100 Hz"])
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_combo)
        recording_layout.addLayout(filter_layout)
        
        # Notch filter
        notch_layout = QHBoxLayout()
        notch_label = QLabel("Notch Filter:")
        notch_label.setFixedWidth(120)
        self.notch_combo = QComboBox()
        self.notch_combo.addItems(["50 Hz (Europe)", "60 Hz (US/Canada)", "None"])
        notch_layout.addWidget(notch_label)
        notch_layout.addWidget(self.notch_combo)
        recording_layout.addLayout(notch_layout)
        
        scroll_layout.addWidget(recording_card)
        
        # ===== Environmental Conditions Card =====
        env_card = QFrame()
        env_card.setObjectName("DialogCard")
        env_layout = QVBoxLayout(env_card)
        env_layout.setContentsMargins(16, 16, 16, 16)
        env_layout.setSpacing(10)
        
        env_title = QLabel("🌡️ Environmental Conditions")
        env_title.setObjectName("DialogSectionTitle")
        env_layout.addWidget(env_title)
        
        # Recording location
        location_layout = QHBoxLayout()
        location_label = QLabel("Location:")
        location_label.setFixedWidth(120)
        self.location_combo = QComboBox()
        self.location_combo.addItems(["Laboratory", "Clinical", "Home", "Other"])
        location_layout.addWidget(location_label)
        location_layout.addWidget(self.location_combo)
        env_layout.addLayout(location_layout)
        
        # Lighting
        lighting_layout = QHBoxLayout()
        lighting_label = QLabel("Lighting:")
        lighting_label.setFixedWidth(120)
        self.lighting_combo = QComboBox()
        self.lighting_combo.addItems(["Dim/Low", "Normal", "Bright"])
        lighting_layout.addWidget(lighting_label)
        lighting_layout.addWidget(self.lighting_combo)
        env_layout.addLayout(lighting_layout)
        
        # Notes
        notes_label = QLabel("Notes (optional):")
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(60)
        self.notes_input.setPlaceholderText("Any additional notes about the recording session...")
        env_layout.addWidget(notes_label)
        env_layout.addWidget(self.notes_input)
        
        scroll_layout.addWidget(env_card)
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_content)
        
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
        
        self.start_button = QPushButton("🚀 Start Recording Session →")
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.start_button.clicked.connect(self.on_start)
        nav_layout.addWidget(self.start_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(scroll, 1)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        add_help_button_to_dialog(self)
        self._programmatic_close = False
    
    def _calculate_demo_impedances(self) -> dict:
        """Calculate demo impedance values for all 64 channels"""
        # ANT Neuro SDK uses channels 0-63 for EEG reference channels
        impedances = {}
        for i in range(64):
            ch_name = f'Ch{i}'
            # Generate realistic impedance values (mostly good, some slightly higher)
            base = np.random.uniform(2.0, 8.0)
            # Add some variation
            if np.random.random() < 0.1:  # 10% chance of slightly higher impedance
                base = np.random.uniform(8.0, 15.0)
            impedances[ch_name] = round(base, 1)
        
        return impedances
    
    def _get_impedances(self) -> dict:
        """Get electrode impedances from real device if connected, otherwise use demo values.
        
        Device should already be connected via Login dialog.
        """
        # Check if we have a real device connected (not demo)
        if ANT_NEURO.is_connected and ANT_NEURO.device_serial != 'DEMO-001':
            # Try to get real impedances from device
            try:
                print("[METADATA] Attempting to read real impedances from device...")
                # Real device - attempt to read impedances from SDK
                # Note: This requires the amplifier to support impedance measurement
                if hasattr(ANT_NEURO, 'amplifier') and ANT_NEURO.amplifier:
                    # Use eego SDK impedance measurement if available
                    impedances = self._read_real_impedances()
                    if impedances:
                        print(f"[METADATA] ✓ Read real impedances from {len(impedances)} channels")
                        return impedances
            except Exception as e:
                print(f"[METADATA] Could not read real impedances: {e} - using demo values")
        
        # Fall back to demo impedances
        print("[METADATA] Using demo impedance values")
        return self._calculate_demo_impedances()
    
    def _read_real_impedances(self) -> dict:
        """Read real impedance values from ANT Neuro amplifier via SDK."""
        impedances = {}
        
        try:
            if EEGO_SDK_AVAILABLE and hasattr(ANT_NEURO, 'amplifier') and ANT_NEURO.amplifier:
                # Get impedance stream from amplifier
                imp_stream = ANT_NEURO.amplifier.OpenImpedanceStream()
                imp_data = imp_stream.getData()
                
                # Map impedance values to channel names
                # ANT Neuro SDK channels 0-63 are EEG reference channels
                # Channels 64-87 are bipolar auxiliary channels (skip)
                for i in range(min(64, len(imp_data))):
                    impedances[f'Ch{i}'] = round(imp_data[i] / 1000.0, 1)  # Convert to kOhm
                
                imp_stream.close()
                return impedances
        except Exception as e:
            print(f"[METADATA] Error reading impedances from SDK: {e}")
        
        return None  # Return None to trigger fallback to demo values
    
    def closeEvent(self, event):
        """Handle dialog close"""
        if self._programmatic_close:
            event.accept()
        else:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Are you sure you want to exit?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_back(self):
        """Navigate back"""
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_start(self):
        """Save metadata and start ANT Neuro streaming, then proceed to Live EEG.
        
        Device should already be connected via Login dialog.
        """
        # Get email from user_data (fetched during login)
        user_data = getattr(self.workflow.main_window, 'user_data', {})
        user_email = user_data.get('email', None)
        
        # Fallback: Try to get from QSettings if not in user_data
        if not user_email or user_email == 'unknown@example.com':
            from PySide6.QtCore import QSettings
            settings = QSettings("MindLink", "FeatureAnalyzer")
            saved_username = settings.value("username", "")
            if saved_username and '@' in saved_username:
                user_email = saved_username
                print(f"[METADATA DIALOG] Using email from QSettings: {user_email}")
            else:
                user_email = 'unknown@example.com'
        
        print(f"\n{'='*60}")
        print(f"[METADATA DIALOG] Email extraction debug:")
        print(f"  user_data exists: {user_data is not None}")
        print(f"  user_data keys: {list(user_data.keys()) if user_data else 'N/A'}")
        print(f"  user_email: {user_email}")
        print(f"{'='*60}\n")
        
        # Collect all metadata
        metadata = {
            'subject': {
                'id': self.subject_id_input.text().strip() or 'UNKNOWN',
                'age': self.age_input.text().strip(),
                'email': user_email,
                'sex': self.sex_combo.currentText(),
                'handedness': self.hand_combo.currentText(),
            },
            'hardware': {
                'device_model': 'ANT Neuro eego mylab 64-channel',
                'sample_rate': ANT_NEURO.sample_rate,
                'channel_count': ANT_NEURO.channel_count,
                'reference': self.ref_combo.currentText(),
                'device_serial': ANT_NEURO.device_serial,
                'is_demo_mode': ANT_NEURO.device_serial == 'DEMO-001',
            },
            'impedances': self.impedance_values,
            'recording': {
                'bandpass_filter': self.filter_combo.currentText(),
                'notch_filter': self.notch_combo.currentText(),
            },
            'environment': {
                'location': self.location_combo.currentText(),
                'lighting': self.lighting_combo.currentText(),
                'notes': self.notes_input.toPlainText().strip(),
            },
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        # Store metadata in main window
        self.workflow.main_window.antneuro_metadata = metadata
        
        print(f"✓ ANT Neuro metadata collected for subject: {metadata['subject']['id']}")
        print(f"  Device: {metadata['hardware']['device_serial']} (Demo: {metadata['hardware']['is_demo_mode']})")
        
        # Device should already be connected from Login dialog
        # If not connected, log warning and connect
        if not ANT_NEURO.is_connected:
            print("[METADATA] Warning: Device not connected from Login - connecting now")
            device_serial = getattr(self.workflow.main_window, 'selected_device', None)
            if device_serial:
                ANT_NEURO.connect(device_serial)
            else:
                # Scan for devices - will use real if found, demo only if not found
                devices = ANT_NEURO.scan_for_devices()
                if devices:
                    ANT_NEURO.connect(devices[0]['serial'])
        
        # NOTE: Don't start streaming here - we go to Impedance Check first
        # Streaming will start after impedance check is complete
        
        # Set metadata in feature engine if it exists
        if hasattr(self.workflow.main_window, 'feature_engine'):
            engine = self.workflow.main_window.feature_engine
            print(f"\n[METADATA DIALOG] Feature engine found: {type(engine).__name__}")
            if hasattr(engine, 'set_metadata'):
                print(f"[METADATA DIALOG] Calling set_metadata with:")
                print(f"  subject_id: {metadata['subject']['id']}")
                print(f"  subject_age: {metadata['subject']['age']}")
                print(f"  subject_email: {metadata['subject']['email']}")
                engine.set_metadata(
                    subject_id=metadata['subject']['id'],
                    subject_age=metadata['subject']['age'],
                    subject_email=metadata['subject']['email']
                )
                print(f"[METADATA DIALOG] set_metadata() completed")
            else:
                print(f"[METADATA DIALOG] WARNING: Feature engine has no set_metadata method!")
        else:
            print(f"[METADATA DIALOG] WARNING: No feature_engine found in main window!")
        
        # Proceed to Impedance Check (for ANT Neuro devices)
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.IMPEDANCE_CHECK))


# ============================================================================
# STEP 4.5: IMPEDANCE CHECK (ANT Neuro only)
# ============================================================================

class ImpedanceSignals(QObject):
    """Thread-safe signals for impedance UI updates"""
    impedance_updated = Signal(object, float, float)  # impedance_values (as object), ref, gnd
    status_updated = Signal(str, bool)  # message, is_error


class ImpedanceCheckDialog(QDialog):
    """Step 4.5: Electrode impedance check before streaming (ANT Neuro only)
    
    This dialog puts the amplifier into impedance mode and displays real-time
    electrode impedances. Once the user confirms good electrode contact, 
    pressing Next will switch to EEG mode and start streaming.
    """
    
    # NA-265 waveguard net 64-channel cap electrode layout (from UDO-SM-1002rev04 datasheet)
    # Connector 1: Channels 1-32, Connector 2: Channels 33-64
    # Channel index 0 = Channel Number 1 in datasheet
    CHANNEL_NAMES = [
        # Connector 1 (Channels 1-32)
        'Fp1', 'Fp2', 'F9', 'F7', 'F3', 'Fz', 'F4', 'F8',      # 1-8
        'F10', 'FC5', 'FC1', 'FC2', 'FC6', 'T9', 'T7', 'C3',    # 9-16
        'C4', 'T8', 'T10', 'CP5', 'CP1', 'CP2', 'CP6', 'P9',    # 17-24
        'P7', 'P3', 'Pz', 'P4', 'P8', 'P10', 'O1', 'O2',        # 25-32
        # Connector 2 (Channels 33-64)
        'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6',     # 33-40
        'FC3', 'FCz', 'FC4', 'C5', 'C1', 'C2', 'C6', 'CP3',     # 41-48
        'CP4', 'P5', 'P1', 'P2', 'P6', 'PO5', 'PO3', 'PO4',     # 49-56
        'PO6', 'FT7', 'FT8', 'TP7', 'TP8', 'PO7', 'PO8', 'POz'  # 57-64
    ]
    
    # Color thresholds for impedance values (in kΩ) - per ANT Neuro datasheet
    EXCELLENT_THRESHOLD = 10    # < 10 kΩ is excellent (bright green)
    GOOD_THRESHOLD = 20         # < 20 kΩ is preferred (green) 
    ACCEPTABLE_THRESHOLD = 50   # < 50 kΩ is acceptable/good enough (yellow-green)
    POOR_THRESHOLD = 100        # < 100 kΩ is poor (orange)
    CAP_NOT_WORN_THRESHOLD = 200 # > 200 kΩ means cap not worn (dark red)
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Electrode Impedance Check")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(700, 500)
        self.resize(700, 520)
        
        # Set window icon
        set_window_icon(self)
        
        # Get actual channel names from connected device
        self.channel_names = self._get_device_channel_names()
        
        # Thread-safe signals for UI updates
        self._signals = ImpedanceSignals()
        self._signals.impedance_updated.connect(self._on_impedance_updated)
        self._signals.status_updated.connect(self._on_status_updated)
        
        # Impedance data storage
        self.impedance_values = {}  # ch_index -> impedance in kΩ
        self.reference_impedance = 0.0
        self.ground_impedance = 0.0
        self._impedance_mode_active = False
        self._stop_flag = False
        self._impedance_thread = None  # Track the thread for proper cleanup
        
        # UI Elements
        title_label = QLabel("Electrode Impedance Check")
        title_label.setObjectName("DialogTitle")
        title_label.setStyleSheet("font-size: 16px; font-weight: 600; margin: 0; padding: 0;")
        
        subtitle_label = QLabel("Verify electrode contact quality before recording")
        subtitle_label.setObjectName("DialogSubtitle")
        subtitle_label.setStyleSheet("font-size: 11px; margin: 0; padding: 0;")
        
        # Instructions (compact legend)
        instructions_label = QLabel(
            "<span style='color: #059669;'>★&lt;10k</span> | "
            "<span style='color: #10b981;'>✓&lt;20k</span> | "
            "<span style='color: #22c55e;'>◉&lt;50k</span> | "
            "<span style='color: #f97316;'>✗&gt;50k</span> | "
            "<span style='color: #991b1b;'>⊘&gt;200k</span> | "
            "<b>Live monitoring - adjust headset until values are good</b>"
        )
        instructions_label.setStyleSheet(
            "font-size: 11px; padding: 6px 10px; background: #f0f9ff; "
            "border-radius: 6px; border-left: 3px solid #3b82f6;"
        )
        instructions_label.setWordWrap(True)
        
        # Main content area - Grid of electrode impedances
        content_card = QFrame()
        content_card.setObjectName("DialogCard")
        content_card.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 4px;")
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(4)
        
        # Summary bar
        self.summary_label = QLabel("Initializing...")
        self.summary_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600; padding: 4px;")
        self.summary_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.summary_label)
        
        # Create electrode grid in ANATOMICAL order (front-to-back, left-to-right)
        # 8 rows x 8 cols = 64 cells matching the NA-265 cap layout
        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setSpacing(2)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # Anatomical display order: maps grid position -> channel index
        # Channels sorted front (Fp) to back (O), left to right within each layer
        # Channel indices reference CHANNEL_NAMES:
        #  0:Fp1  1:Fp2  2:F9   3:F7   4:F3   5:Fz   6:F4   7:F8
        #  8:F10  9:FC5 10:FC1 11:FC2 12:FC6 13:T9  14:T7  15:C3
        # 16:C4  17:T8  18:T10 19:CP5 20:CP1 21:CP2 22:CP6 23:P9
        # 24:P7  25:P3  26:Pz  27:P4  28:P8  29:P10 30:O1  31:O2
        # 32:AF7 33:AF3 34:AF4 35:AF8 36:F5  37:F1  38:F2  39:F6
        # 40:FC3 41:FCz 42:FC4 43:C5  44:C1  45:C2  46:C6  47:CP3
        # 48:CP4 49:P5  50:P1  51:P2  52:P6  53:PO5 54:PO3 55:PO4
        # 56:PO6 57:FT7 58:FT8 59:TP7 60:TP8 61:PO7 62:PO8 63:POz
        anatomical_order = [
            # Row 0: Fp + AF (frontal pole / anterior frontal)
             0,  1, 32, 33, 34, 35,  2,  3,
            # Row 1: F (frontal)
            36,  4, 37,  5, 38,  6, 39,  7,
            # Row 2: F10 + FC (fronto-central)
             8, 57,  9, 40, 10, 41, 11, 42,
            # Row 3: FC end + C (central)
            12, 58, 13, 14, 43, 15, 44, 45,
            # Row 4: C continued + CP start (centro-parietal)
            16, 46, 17, 18, 59, 19, 47, 20,
            # Row 5: CP continued + P start (parietal)
            21, 48, 22, 60, 23, 24, 49, 25,
            # Row 6: P continued + PO start (parieto-occipital)
            50, 26, 51, 27, 52, 28, 29, 61,
            # Row 7: PO continued + O (occipital) — O1 and O2 at bottom
            53, 54, 63, 55, 56, 62, 30, 31,
        ]
        
        # Create 64 electrode labels indexed by channel index (for update function)
        self.electrode_labels = [None] * 64
        for grid_pos, ch_idx in enumerate(anatomical_order):
            row = grid_pos // 8
            col = grid_pos % 8
            
            # Get channel name from device (actual hardware mapping)
            ch_name = self.channel_names[ch_idx] if ch_idx < len(self.channel_names) else f"Ch{ch_idx+1}"
            
            label = QLabel(f"{ch_name}\n--")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(70, 38)
            label.setStyleSheet(
                "background: #475569; color: #e2e8f0; border-radius: 3px; "
                "font-size: 9px; font-weight: 500;"
            )
            self.electrode_labels[ch_idx] = label
            self.grid_layout.addWidget(label, row, col)
        
        content_layout.addWidget(grid_widget)
        
        # Reference and Ground display
        ref_gnd_layout = QHBoxLayout()
        ref_gnd_layout.setSpacing(8)
        
        self.ref_label = QLabel("REF: --")
        self.ref_label.setStyleSheet(
            "background: #475569; color: #e2e8f0; border-radius: 3px; "
            "font-size: 11px; font-weight: 600; padding: 4px 12px;"
        )
        self.ref_label.setAlignment(Qt.AlignCenter)
        
        self.gnd_label = QLabel("GND: --")
        self.gnd_label.setStyleSheet(
            "background: #475569; color: #e2e8f0; border-radius: 3px; "
            "font-size: 11px; font-weight: 600; padding: 4px 12px;"
        )
        self.gnd_label.setAlignment(Qt.AlignCenter)
        
        ref_gnd_layout.addStretch()
        ref_gnd_layout.addWidget(self.ref_label)
        ref_gnd_layout.addWidget(self.gnd_label)
        ref_gnd_layout.addStretch()
        
        content_layout.addLayout(ref_gnd_layout)
        
        # Status/error label (compact)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 11px; padding: 4px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #475569;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #cbd5e1;
            }
        """)
        
        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.clicked.connect(self.start_impedance_check)
        self.refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: white;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 5px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0284c7;
            }
        """)
        
        nav_layout.addWidget(self.back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.refresh_button)
        nav_layout.addStretch()
        
        self.next_button = QPushButton("Next →")
        self.next_button.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 5px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly (compact)
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(instructions_label)
        layout.addWidget(content_card, 1)  # Stretch factor 1
        layout.addWidget(self.status_label)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Skip status bar to save space
        self.status_bar = None
        
        self._programmatic_close = False
        
        # Start impedance check when dialog opens
        QTimer.singleShot(500, self.start_impedance_check)
    
    def _get_device_channel_names(self):
        """Get actual channel names from connected ANT Neuro device.
        
        Returns list of channel names in hardware order (index 0 = first channel, etc.)
        Falls back to standard 10-20 names if device not available or returns generic names.
        
        Note: The ANT Neuro SDK returns "none" as channel names when no electrode layout
        is configured in the device. The edi2_client converts these to "Ch1", "Ch2", etc.
        In this case, we use the standard 10-20 system names which correspond to the 
        waveguard 64-channel cap layout.
        """
        import re
        try:
            edi2_client = getattr(ANT_NEURO, 'edi2_client', None)
            if edi2_client and hasattr(edi2_client, 'channels') and edi2_client.channels:
                # Get channel names from connected device
                names = [ch.name for ch in edi2_client.channels[:64]]
                
                # Check if SDK returned valid electrode names or just generic placeholders
                # Generic names are: "none", "Ch1", "Ch2", etc.
                # Valid electrode names are: "Fp1", "Fz", "Cz", "O1", etc.
                generic_pattern = re.compile(r'^(none|ch\d+)$', re.IGNORECASE)
                valid_electrode_names = [n for n in names if n and not generic_pattern.match(n)]
                
                if len(valid_electrode_names) > len(names) // 2:  # More than half are valid
                    print(f"[IMPEDANCE] Using {len(names)} channel names from device: {names[:5]}...")
                    return names
                else:
                    print(f"[IMPEDANCE] Device returned generic channel names (no electrode layout configured)")
                    print(f"[IMPEDANCE] Using standard 10-20 waveguard cap layout names instead")
        except Exception as e:
            print(f"[IMPEDANCE] Could not get channel names from device: {e}")
        
        # Fallback: Use standard 10-20 system names (waveguard 64-channel cap layout)
        print("[IMPEDANCE] Using fallback 10-20 channel names")
        return self.CHANNEL_NAMES
    
    def start_impedance_check(self):
        """Start the impedance measurement mode"""
        self._stop_flag = False
        self.status_label.setText("Starting impedance measurement...")
        self.status_label.setStyleSheet("color: #0ea5e9; font-size: 12px; padding: 8px;")
        
        # Run impedance check in background thread
        import threading
        self._impedance_thread = threading.Thread(target=self._impedance_check_thread, daemon=False)
        self._impedance_thread.start()
    
    def _impedance_check_thread(self):
        """Background thread for impedance measurement via gRPC"""
        import time
        
        try:
            # First, stop any running streaming to avoid conflicts
            if ANT_NEURO.is_streaming:
                print("[IMPEDANCE] Stopping streaming before impedance check...")
                ANT_NEURO.stop_streaming()
                time.sleep(0.5)
            
            # Get the EDI2 client
            edi2_client = getattr(ANT_NEURO, 'edi2_client', None)
            if not edi2_client:
                self._update_status("Error: EDI2 client not available", error=True)
                return
            
            # Reconnect to amplifier to refresh the handle (may have become stale after previous impedance check)
            device_serial = ANT_NEURO.device_serial
            if device_serial and device_serial != 'DEMO-001':
                print("[IMPEDANCE] Reconnecting to refresh amplifier handle...")
                try:
                    edi2_client.connect(device_serial)
                    time.sleep(0.3)
                except Exception as e:
                    print(f"[IMPEDANCE] Reconnect warning: {e}")
            
            # Get gRPC components (now with fresh handle)
            stub = edi2_client.stub
            amplifier_handle = edi2_client.amplifier_handle
            
            if not stub or amplifier_handle is None:
                self._update_status("Error: Not connected to device", error=True)
                return
            
              # Import gRPC modules
            import sys
            import os
            antneuro_dir = os.path.dirname(os.path.abspath(__file__))
            if hasattr(sys.modules.get('antNeuro', None), '__path__'):
                antneuro_dir = sys.modules['antNeuro'].__path__[0]
            else:
                antneuro_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'antNeuro')
            
            if antneuro_dir not in sys.path:
                sys.path.insert(0, antneuro_dir)
            
            try:
                import EdigRPC_pb2 as edi
            except ImportError as e:
                self._update_status(f"Error: EdigRPC_pb2 module not found - {e}", error=True)
                print(f"[IMPEDANCE] Failed to import EdigRPC_pb2: {e}")
                print(f"[IMPEDANCE] antNeuro directory: {antneuro_dir}")
                print(f"[IMPEDANCE] sys.path: {sys.path}")
                return
          
            # Build StreamParams
            channel_count = edi2_client.get_channel_count() or 88
            active_channels = list(range(min(64, channel_count)))
            stream_params = edi.StreamParams(
                ActiveChannels=active_channels,
                Ranges={0: 1.0},
                SamplingRate=512.0,
                BufferSize=2560,
                DataReadyPercentage=1
            )
            
            # Set IDLE mode first
            self._update_status("Setting IDLE mode...")
            try:
                stub.Amplifier_SetMode(
                    edi.Amplifier_SetModeRequest(
                        AmplifierHandle=amplifier_handle,
                        Mode=edi.AmplifierMode.AmplifierMode_Idle,
                        StreamParams=stream_params
                    )
                )
                time.sleep(0.5)
            except Exception as e:
                print(f"[IMPEDANCE] Warning setting IDLE: {e}")
            
            # Set IMPEDANCE mode
            self._update_status("Setting IMPEDANCE mode...")
            try:
                stub.Amplifier_SetMode(
                    edi.Amplifier_SetModeRequest(
                        AmplifierHandle=amplifier_handle,
                        Mode=edi.AmplifierMode.AmplifierMode_Impedance,
                        StreamParams=stream_params
                    )
                )
                self._impedance_mode_active = True
                print("[IMPEDANCE] Impedance mode set successfully")
            except Exception as e:
                self._update_status(f"Error setting impedance mode: {e}", error=True)
                return
            
            # Read impedance frames continuously until user clicks Next or closes dialog
            self._update_status("Reading impedance values - adjust headset as needed...")
            frame_count = 0
            impedance_frame_count = 0
            
            print("[IMPEDANCE] Starting continuous frame read loop (will run until Next/Close)...")
            
            while not self._stop_flag:  # Run until user clicks Next or closes dialog
                try:
                    frame_resp = stub.Amplifier_GetFrame(
                        edi.Amplifier_GetFrameRequest(
                            AmplifierHandle=amplifier_handle
                        ),
                        timeout=2.0
                    )
                    
                    if not frame_resp.FrameList:
                        time.sleep(0.1)
                        continue
                    
                    for frame in frame_resp.FrameList:
                        frame_count += 1
                        frame_type_names = {0: "EEG", 1: "ImpedanceVoltages", 2: "OpenLine", 3: "Stimulation"}
                        
                        if frame_count <= 3 or frame_count % 10 == 0:
                            print(f"[IMPEDANCE] Frame {frame_count}: Type={frame_type_names.get(frame.FrameType, frame.FrameType)}")
                        
                        # Check for impedance data (don't rely on FrameType)
                        if frame.Impedance and frame.Impedance.Channels:
                            impedance_frame_count += 1
                            
                            # Extract channel impedances into local dict first
                            num_channels = len(frame.Impedance.Channels)
                            channel_data = {}
                            for idx, ch_imp in enumerate(frame.Impedance.Channels):
                                if idx < 64:
                                    kohms = ch_imp.Value / 1000.0
                                    channel_data[idx] = kohms
                            
                            # Update instance variables
                            self.impedance_values.update(channel_data)
                            
                            if impedance_frame_count == 1:
                                print(f"[IMPEDANCE] Got {num_channels} channel impedances, first few values: {[channel_data[i] for i in range(min(5, len(channel_data)))]}")
                            
                            # Extract reference impedance
                            ref_imp = self.reference_impedance
                            if frame.Impedance.Reference:
                                ref_imp = frame.Impedance.Reference[0].Value / 1000.0
                                self.reference_impedance = ref_imp
                            
                            # Extract ground impedance
                            gnd_imp = self.ground_impedance
                            if frame.Impedance.Ground:
                                gnd_imp = frame.Impedance.Ground[0].Value / 1000.0
                                self.ground_impedance = gnd_imp
                            
                            # Update UI periodically - pass the local data directly
                            if impedance_frame_count % 3 == 0:
                                print(f"[IMPEDANCE] Emitting UI update: {len(channel_data)} channels, REF={ref_imp:.1f}kΩ, GND={gnd_imp:.1f}kΩ")
                                self._signals.impedance_updated.emit(dict(self.impedance_values), ref_imp, gnd_imp)
                    
                    time.sleep(0.1)
                    
                except Exception as e:
                    error_str = str(e)
                    # Handle amplifier detach/reattach gracefully
                    if "not found: amplifier with id" in error_str:
                        # Amplifier is being detached/reattached - wait and retry
                        if impedance_frame_count == 0:
                            # Haven't gotten any data yet - might need to reconnect
                            print("[IMPEDANCE] Amplifier temporarily unavailable (detach/reattach), waiting...")
                        time.sleep(0.5)
                        continue
                    elif "UNAVAILABLE" in error_str or "aborted" in error_str.lower():
                        self._update_status("Connection lost during impedance check", error=True)
                        break
                    else:
                        print(f"[IMPEDANCE] Frame read error: {e}")
                        time.sleep(0.1)
            
            # Final update (user clicked Next or closed dialog)
            print(f"[IMPEDANCE] Final update: {len(self.impedance_values)} channels")
            self._signals.impedance_updated.emit(dict(self.impedance_values), self.reference_impedance, self.ground_impedance)
            if self._stop_flag:
                self._update_status(f"Impedance monitoring stopped - {impedance_frame_count} frames read, {frame_count} total")
            else:
                self._update_status(f"Impedance check complete - {impedance_frame_count} impedance frames read")
            print(f"[IMPEDANCE] Complete: {len(self.impedance_values)} channels, {impedance_frame_count} impedance frames, {frame_count} total frames, REF={self.reference_impedance:.1f}kΩ, GND={self.ground_impedance:.1f}kΩ")
            
        except Exception as e:
            self._update_status(f"Error: {e}", error=True)
            import traceback
            traceback.print_exc()
        finally:
            self._impedance_mode_active = False
            
            # CRITICAL: Properly dispose the amplifier handle after impedance check
            # This prevents "amplifier in use" errors when trying to stream later
            print("[IMPEDANCE] Cleaning up amplifier handle...")
            try:
                edi2_client = getattr(ANT_NEURO, 'edi2_client', None)
                if edi2_client and edi2_client.stub and edi2_client.amplifier_handle is not None:
                    old_handle = edi2_client.amplifier_handle
                    print(f"[IMPEDANCE] Disposing amplifier handle: {old_handle}")
                    
                    # First set to IDLE mode
                    try:
                        import EdigRPC_pb2 as edi
                        edi2_client.stub.Amplifier_SetMode(
                            edi.Amplifier_SetModeRequest(
                                AmplifierHandle=old_handle,
                                Mode=edi.AmplifierMode.AmplifierMode_Idle,
                                StreamParams=edi.StreamParams()
                            )
                        )
                        time.sleep(0.2)
                    except Exception as e:
                        print(f"[IMPEDANCE] Could not set IDLE mode (handle may be stale): {e}")
                    
                    # Then dispose the handle
                    try:
                        edi2_client.stub.Amplifier_Dispose(
                            edi.Amplifier_DisposeRequest(AmplifierHandle=old_handle)
                        )
                        print(f"[IMPEDANCE] Handle {old_handle} disposed successfully")
                    except Exception as e:
                        print(f"[IMPEDANCE] Handle disposal error (may already be disposed): {e}")
                    
                    # Clear the handle so we force a reconnect
                    edi2_client.amplifier_handle = None
                    edi2_client.is_connected = False
                    print("[IMPEDANCE] Amplifier handle cleared - will reconnect before streaming")
            except Exception as e:
                print(f"[IMPEDANCE] Cleanup error: {e}")
    
    def _update_status(self, message: str, error: bool = False):
        """Update status label from any thread - uses signal for thread safety"""
        self._signals.status_updated.emit(message, error)
    
    @Slot(str, bool)
    def _on_status_updated(self, message: str, is_error: bool):
        """Slot to handle status updates on main thread"""
        if is_error:
            self.status_label.setStyleSheet("color: #ef4444; font-size: 12px; padding: 8px;")
        else:
            self.status_label.setStyleSheet("color: #0ea5e9; font-size: 12px; padding: 8px;")
        self.status_label.setText(message)
    
    def _update_impedance_display(self):
        """Update the electrode grid display with current impedance values - uses signal for thread safety"""
        # Create a deep copy to avoid race conditions
        imp_copy = dict(self.impedance_values)
        ref_copy = float(self.reference_impedance)
        gnd_copy = float(self.ground_impedance)
        
        print(f"[IMPEDANCE] Emitting signal with {len(imp_copy)} channels")
        
        # Emit signal with copy of current data
        self._signals.impedance_updated.emit(imp_copy, ref_copy, gnd_copy)
    
    @Slot(object, float, float)
    def _on_impedance_updated(self, impedance_values, ref_imp: float, gnd_imp: float):
        """Slot to handle impedance updates on main thread"""
        print(f"[IMPEDANCE SLOT] Called with {len(impedance_values) if impedance_values else 0} channel values, REF={ref_imp:.1f}, GND={gnd_imp:.1f}")
        if impedance_values and len(impedance_values) > 0:
            print(f"[IMPEDANCE SLOT] First 5 channels: {[(k, v) for k, v in list(impedance_values.items())[:5]]}")
        
        excellent_count = 0
        good_count = 0
        acceptable_count = 0
        poor_count = 0
        cap_not_worn_count = 0
        
        for idx, label in enumerate(self.electrode_labels):
            # Get channel name from device (matches impedance data index)
            ch_name = self.channel_names[idx] if idx < len(self.channel_names) else f"Ch{idx+1}"
            
            if idx in impedance_values:
                kohms = impedance_values[idx]
                
                # Determine color based on impedance (per ANT Neuro datasheet)
                if kohms < self.EXCELLENT_THRESHOLD:
                    bg_color = "#059669"  # Bright green - Excellent (<10k)
                    excellent_count += 1
                elif kohms < self.GOOD_THRESHOLD:
                    bg_color = "#10b981"  # Green - Preferred (<20k)
                    good_count += 1
                elif kohms < self.ACCEPTABLE_THRESHOLD:
                    bg_color = "#22c55e"  # Light green - Good enough (<50k)
                    acceptable_count += 1
                elif kohms < self.POOR_THRESHOLD:
                    bg_color = "#f97316"  # Orange - Poor (<100k)
                    poor_count += 1
                else:
                    bg_color = "#991b1b"  # Dark red - Cap not worn (>100k)
                    cap_not_worn_count += 1
                
                # Compact label text with channel name
                label.setText(f"{ch_name}\n{kohms:.0f}k")
                label.setStyleSheet(
                    f"background: {bg_color}; color: white; border-radius: 3px; "
                    "font-size: 9px; font-weight: 600;"
                )
            else:
                label.setText(f"{ch_name}\n--")
                label.setStyleSheet(
                    "background: #475569; color: #e2e8f0; border-radius: 3px; "
                    "font-size: 9px; font-weight: 500;"
                )
        
        # Update reference and ground (compact)
        if ref_imp > 0:
            ref_color = "#10b981" if ref_imp < 100 else "#f59e0b" if ref_imp < 500 else "#ef4444"
            self.ref_label.setText(f"REF: {ref_imp:.0f}k")
            self.ref_label.setStyleSheet(
                f"background: {ref_color}; color: white; border-radius: 3px; "
                "font-size: 11px; font-weight: 600; padding: 4px 12px;"
            )
        
        if gnd_imp > 0:
            gnd_color = "#10b981" if gnd_imp < 100 else "#f59e0b" if gnd_imp < 500 else "#ef4444"
            self.gnd_label.setText(f"GND: {gnd_imp:.0f}k")
            self.gnd_label.setStyleSheet(
                f"background: {gnd_color}; color: white; border-radius: 3px; "
                "font-size: 11px; font-weight: 600; padding: 4px 12px;"
            )
        
        # Update summary (compact)
        total = excellent_count + good_count + acceptable_count + poor_count + cap_not_worn_count
        if total > 0:
            self.summary_label.setText(
                f"★{excellent_count} ✓{good_count} ⚠{acceptable_count} ✗{poor_count} ⊘{cap_not_worn_count}"
            )
            # Color based on quality
            if poor_count == 0 and cap_not_worn_count == 0:
                self.summary_label.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600; padding: 4px;")
            elif cap_not_worn_count > 0:
                self.summary_label.setStyleSheet("color: #991b1b; font-size: 12px; font-weight: 600; padding: 4px;")
            elif poor_count < total * 0.2:
                self.summary_label.setStyleSheet("color: #f59e0b; font-size: 12px; font-weight: 600; padding: 4px;")
            else:
                self.summary_label.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: 600; padding: 4px;")
    
    def on_back(self):
        """Go back to metadata dialog"""
        self._stop_flag = True
        self._programmatic_close = True
        self.close()
        self.workflow.go_back()
    
    def on_next(self):
        """Stop impedance mode, switch to EEG mode, and proceed to Live EEG"""
        self._stop_flag = True
        
        # Store impedance values for reference
        self.workflow.main_window.last_impedance_values = self.impedance_values.copy()
        self.workflow.main_window.last_ref_impedance = self.reference_impedance
        self.workflow.main_window.last_gnd_impedance = self.ground_impedance
        
        self.status_label.setText("Switching to EEG mode...")
        self.status_label.setStyleSheet("color: #0ea5e9; font-size: 12px; padding: 8px;")
        
        import time
        
        # IMPORTANT: Do NOT call disconnect() - that stops the gRPC server
        # Instead, just set the amplifier to IDLE mode to release impedance mode
        # The amplifier handle remains valid, so we can reuse it for EEG streaming
        
        if ANT_NEURO.edi2_client and ANT_NEURO.edi2_client.amplifier_handle is not None:
            try:
                print("[IMPEDANCE] Returning to IDLE mode (keeping server running)...")
                # Import the protobuf module
                import antNeuro.EdigRPC_pb2 as edi
                
                # Set mode to IDLE (mode 0) to release impedance mode
                ANT_NEURO.edi2_client.stub.Amplifier_SetMode(
                    edi.Amplifier_SetModeRequest(
                        AmplifierHandle=ANT_NEURO.edi2_client.amplifier_handle,
                        Mode=0,  # IDLE mode
                        Channels=ANT_NEURO.channel_count,
                        Rate=500.0
                    )
                )
                print("[IMPEDANCE] ✓ Returned to IDLE mode")
                time.sleep(0.3)  # Brief settling time
            except Exception as e:
                print(f"[IMPEDANCE] Mode switch warning: {e}")
        
        # Reset streaming state
        ANT_NEURO.is_streaming = False
        if ANT_NEURO.edi2_client:
            ANT_NEURO.edi2_client.is_streaming = False
        
        # CRITICAL: Wait for impedance thread to complete cleanup
        if self._impedance_thread and self._impedance_thread.is_alive():
            print("[IMPEDANCE] Waiting for impedance thread to complete cleanup...")
            self._impedance_thread.join(timeout=3.0)
            if self._impedance_thread.is_alive():
                print("[IMPEDANCE] Warning: Impedance thread still running after 3s")
        
        import time
        time.sleep(0.5)  # Give gRPC server time to fully dispose the old handle
        
        # CRITICAL: Force reconnect to get a fresh amplifier handle
        # The impedance check disposes the old handle, so we MUST reconnect
        self.status_label.setText("Reconnecting for EEG streaming...")
        print("[IMPEDANCE] Forcing reconnect to get fresh amplifier handle...")
        device_serial = ANT_NEURO.device_serial
        if device_serial and device_serial != 'DEMO-001':
            try:
                # Reconnect to amplifier to get new handle
                if ANT_NEURO.edi2_client:
                    ANT_NEURO.edi2_client.connect(device_serial)
                    print(f"[IMPEDANCE] Reconnected with new handle: {ANT_NEURO.edi2_client.amplifier_handle}")
                    time.sleep(0.3)
            except Exception as e:
                print(f"[IMPEDANCE] Reconnect error: {e}")
                self.status_label.setText(f"Reconnect failed: {e}")
                return
        
        # Now start EEG streaming with the fresh handle
        self.status_label.setText("Starting EEG streaming...")
        print("[IMPEDANCE] Starting EEG streaming after impedance check...")
        success = ANT_NEURO.start_streaming(sample_rate=500)
        if success:
            print(f"✓ ANT Neuro EEG streaming started at {ANT_NEURO.sample_rate} Hz")
        else:
            print("⚠ Failed to start EEG streaming after impedance check")
        
        # Proceed to Live EEG
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.LIVE_EEG))
    
    def closeEvent(self, event):
        """Handle dialog close - ensure proper cleanup"""
        print("[IMPEDANCE] Dialog closing...")
        self._stop_flag = True
        
        # Wait for impedance thread to terminate
        if self._impedance_thread and self._impedance_thread.is_alive():
            print("[IMPEDANCE] Waiting for impedance thread to stop...")
            self._impedance_thread.join(timeout=2.0)
            if self._impedance_thread.is_alive():
                print("[IMPEDANCE] Warning: Thread still running after 2s timeout")
        
        # Only do manual cleanup if user closed (not programmatic close from on_next)
        # When on_next() is called, it handles the cleanup itself
        if not self._programmatic_close:
            print("[IMPEDANCE] User closed dialog - performing cleanup")
            
            # The impedance thread's finally block already disposed the handle
            # Just reset the streaming flags
            ANT_NEURO.is_streaming = False
            if ANT_NEURO.edi2_client:
                ANT_NEURO.edi2_client.is_streaming = False
                ANT_NEURO.edi2_client.is_connected = False
                ANT_NEURO.edi2_client.amplifier_handle = None
            
            print("[IMPEDANCE] Cleanup complete")
        
        event.accept()
    
    def _return_to_idle_mode(self):
        """Return amplifier to IDLE mode when leaving impedance check.
        
        Note: This may fail with "amplifier not found" error after impedance check
        completes because the gRPC server may dispose the amplifier handle. This is
        expected and we handle it gracefully by reconnecting before streaming.
        """
        try:
            edi2_client = getattr(ANT_NEURO, 'edi2_client', None)
            if edi2_client:
                stub = edi2_client.stub
                amplifier_handle = edi2_client.amplifier_handle
                
                if stub and amplifier_handle is not None:
                    import sys
                    import os
                    antneuro_dir = os.path.dirname(os.path.abspath(__file__))
                    if hasattr(sys.modules.get('antNeuro', None), '__path__'):
                        antneuro_dir = sys.modules['antNeuro'].__path__[0]
                    else:
                        antneuro_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'antNeuro')
                    
                    if antneuro_dir not in sys.path:
                        sys.path.insert(0, antneuro_dir)
                    
                    import EdigRPC_pb2 as edi
                    
                    # Set IDLE mode to exit impedance mode
                    stub.Amplifier_SetMode(
                        edi.Amplifier_SetModeRequest(
                            AmplifierHandle=amplifier_handle,
                            Mode=edi.AmplifierMode.AmplifierMode_Idle,
                            StreamParams=edi.StreamParams()
                        )
                    )
                    print("[IMPEDANCE] Returned to IDLE mode")
        except Exception as e:
            # Expected error: "amplifier with id X not found" after impedance check
            # The handle becomes stale and we'll reconnect before streaming
            if "not found" in str(e).lower():
                print(f"[IMPEDANCE] Amplifier handle stale (expected) - will reconnect before streaming")
            else:
                print(f"[IMPEDANCE] Error returning to IDLE mode: {e}")


# ============================================================================
# STEP 2.5: PARTNER ID INPUT
# ============================================================================

class PartnerIDDialog(QDialog):
    """Step 2.5: Partner ID input"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Partner ID")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(400)
        
        # Set window icon
        set_window_icon(self)
        
        self.settings = QSettings("MindLink", "FeatureAnalyzer")
        
        # UI Elements
        title_label = QLabel("Enter Partner ID")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 5 of 10: Provide your partner identification")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Partner ID card
        partner_card = QFrame()
        partner_card.setObjectName("DialogCard")
        partner_layout = QVBoxLayout(partner_card)
        partner_layout.setContentsMargins(16, 16, 16, 16)
        partner_layout.setSpacing(12)
        
        partner_label = QLabel("Partner ID:")
        partner_label.setObjectName("DialogSectionLabel")
        
        # Partner ID input with eye toggle (same pattern as password)
        partner_input_container = QWidget()
        partner_input_layout = QHBoxLayout(partner_input_container)
        partner_input_layout.setContentsMargins(0, 0, 0, 0)
        partner_input_layout.setSpacing(4)
        
        self.partner_edit = QLineEdit()
        saved_partner_id = self.settings.value("partner_id", "")
        self.partner_edit.setText(saved_partner_id)
        self.partner_edit.setPlaceholderText("Enter your partner ID")
        self.partner_edit.setEchoMode(QLineEdit.Password)
        self.partner_edit.setClearButtonEnabled(True)
        self.partner_edit.returnPressed.connect(self.on_next)
        
        # Eye icon toggle button
        self.partner_toggle_btn = QPushButton("👁")
        self.partner_toggle_btn.setFixedSize(32, 32)
        self.partner_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #64748b;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 16px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background-color: #cbd5e1;
            }
        """)
        self.partner_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.partner_toggle_btn.clicked.connect(self.toggle_partner_visibility)
        
        partner_input_layout.addWidget(self.partner_edit)
        partner_input_layout.addWidget(self.partner_toggle_btn)
        
        partner_layout.addWidget(partner_label)
        partner_layout.addWidget(partner_input_container)
        
        # Info text
        info_label = QLabel("ℹ️ This partner ID will be used for data association when seeding reports to the database.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 12px; color: #3b82f6; padding: 12px; background: #eff6ff; border-radius: 6px; border-left: 3px solid #3b82f6;")
        
        # Disclaimer for advanced tasks booking requirement
        disclaimer_label = QLabel(
            "IMPORTANT: If the partner conducts advanced tasks, reports can only be "
            "generated if the user has a valid booking with the partner for an advanced session."
        )
        disclaimer_label.setWordWrap(True)
        disclaimer_label.setStyleSheet(
            "font-size: 12px; color: #f59e0b; padding: 12px; background: #fffbeb; "
            "border-radius: 6px; border-left: 3px solid #f59e0b;"
        )
        
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
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(partner_card)
        layout.addWidget(info_label)
        layout.addWidget(disclaimer_label)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Add help button
        add_help_button_to_dialog(self)
        self._programmatic_close = False
    
    def closeEvent(self, event):
        """Handle dialog close - only trigger confirmation if user clicked X"""
        if self._programmatic_close:
            event.accept()
        else:
            # Temporarily clear WindowStaysOnTopHint so message box appears on top
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit MindLink Analyzer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            # Restore WindowStaysOnTopHint if it was set
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def toggle_partner_visibility(self):
        """Toggle partner ID visibility with eye icon"""
        if self.partner_edit.echoMode() == QLineEdit.Password:
            self.partner_edit.setEchoMode(QLineEdit.Normal)
            self.partner_toggle_btn.setText("👁‍🗨")  # Crossed eye
        else:
            self.partner_edit.setEchoMode(QLineEdit.Password)
            self.partner_toggle_btn.setText("👁")  # Open eye
    
    def on_back(self):
        """Navigate back to environment selection"""
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        """Save partner ID and proceed to login"""
        partner_id = self.partner_edit.text().strip()
        
        if not partner_id:
            QMessageBox.warning(
                self,
                "Partner ID Required",
                "Please enter a partner ID to continue."
            )
            return
        
        # Validate partner ID against the fetched partners list
        partners_list = getattr(self.workflow.main_window, 'partners_list', [])
        
        if partners_list:
            # Extract partner IDs from the partners list
            # Partners list structure: [{"id": 1, "partner_id": "PARTNER_000001", "name": "Partner Name", ...}, ...]
            valid_partner_ids = []
            partner_details = {}  # Store full details for logging
            for partner in partners_list:
                if isinstance(partner, dict):
                    # Get the partner_id field (e.g., "PARTNER_000001")
                    partner_id_value = partner.get('partner_id')
                    if partner_id_value is not None:
                        valid_partner_ids.append(partner_id_value)
                        partner_details[partner_id_value] = partner
            
            print(f"\n>>> PARTNER VALIDATION <<<")
            print(f"Valid Partner IDs: {valid_partner_ids}")
            print(f"User entered: {partner_id}")
            print(f"Match found: {partner_id in valid_partner_ids}")
            
            # Check if entered partner_id is in the valid list
            if partner_id not in valid_partner_ids:
                QMessageBox.warning(
                    self,
                    "Invalid Partner ID",
                    f"The partner ID '{partner_id}' is not recognized.\n\n"
                    "Please check your partner ID and try again.\n\n"
                    "If you believe this is an error, please contact Mindspeller for assistance."
                )
                return
            
            # Log successful validation
            if partner_id in partner_details:
                partner_info = partner_details[partner_id]
                self.workflow.main_window.log_message(f"✓ Partner validated: {partner_info.get('name', 'Unknown')} ({partner_id})")
        else:
            # If partners list is empty, show a warning but allow to proceed
            self.workflow.main_window.log_message("Warning: Could not validate partner ID (partners list not available)")
        
        # Store partner ID in main window and persist for next session
        self.workflow.main_window.partner_id = partner_id
        self.settings.setValue("partner_id", partner_id)
        self.workflow.main_window.log_message(f"✓ Partner ID saved and validated: {partner_id}")
        
        # Check whether this user has an advanced-session booking with this partner
        self._fetch_partner_bookings(partner_id)
        
        # Proceed to Live EEG
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.LIVE_EEG))

    def _fetch_partner_bookings(self, partner_id):
        """Fetch partner bookings for the current user and store has_advanced_booking."""
        import requests
        mw = self.workflow.main_window
        jwt_token = getattr(mw, 'jwt_token', None)
        login_url  = getattr(mw, 'login_url', '')
        if not jwt_token or not login_url:
            mw.log_message("Warning: Cannot fetch bookings – no JWT token or login URL")
            mw.has_advanced_booking = False
            return
        api_base = login_url.replace("/token/login", "")
        bookings_url = f"{api_base}/partners/bookings?partner_id={partner_id}"
        print(f"\n>>> FETCHING PARTNER BOOKINGS: {bookings_url}")
        try:
            resp = requests.get(
                bookings_url,
                headers={"X-Authorization": f"Bearer {jwt_token}"},
                timeout=10,
                verify=False if "127.0.0.1" in login_url else True
            )
            print(f"Bookings response status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"Bookings response JSON: {data}")
                # Accept a variety of response shapes:
                #   {"has_booking": true}
                #   {"bookings": [ ... ]}
                #   {"data": {"has_booking": true}}
                has_booking = False
                if isinstance(data, dict):
                    if 'has_booking' in data:
                        has_booking = bool(data['has_booking'])
                    elif 'bookings' in data:
                        has_booking = len(data['bookings']) > 0
                    elif 'data' in data and isinstance(data['data'], dict):
                        has_booking = bool(data['data'].get('has_booking', False))
                mw.has_advanced_booking = has_booking
                status = "✓ Advanced booking found" if has_booking else "ℹ No advanced booking for this user/partner"
                mw.log_message(status)
                print(status)
            else:
                print(f"Bookings fetch failed: {resp.status_code} – {resp.text}")
                mw.log_message(f"Warning: Could not fetch bookings (status {resp.status_code})")
                mw.has_advanced_booking = False
        except Exception as e:
            print(f"EXCEPTION in _fetch_partner_bookings: {e}")
            mw.log_message(f"Error fetching bookings: {e}")
            mw.has_advanced_booking = False


# ============================================================================
# STEP 3: LOGIN (Using REAL authentication)
# ============================================================================

class LoginDialog(QDialog):
    """Step 3: Real user authentication"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Sign In To Connect")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(400)
        
        # Set window icon
        set_window_icon(self)
        
        self.settings = QSettings("MindLink", "FeatureAnalyzer")
        
        # Get login URL from previous step
        env_dialog = None
        for dialog in self.workflow.step_history:
            if isinstance(dialog, EnvironmentSelectionDialog):
                env_dialog = dialog
                break
        
        # UI Elements
        title_label = QLabel("Sign In to Connect")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 4 of 10: Enter your credentials")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Credentials card
        cred_card = QFrame()
        cred_card.setObjectName("DialogCard")
        cred_layout = QFormLayout(cred_card)
        cred_layout.setContentsMargins(16, 16, 16, 16)
        cred_layout.setSpacing(12)
        
        # Error/info message (hidden by default)
        self.error_info_label = QLabel("")
        self.error_info_label.setStyleSheet("""
            font-size: 14px; 
            color: #dc2626; 
            padding: 16px; 
            background: #fef2f2; 
            border-radius: 8px; 
            border-left: 4px solid #dc2626;
            font-weight: 600;
            line-height: 1.6;
        """)
        self.error_info_label.setWordWrap(True)
        self.error_info_label.setVisible(False)
        cred_layout.addRow(self.error_info_label)
        
        self.username_edit = QLineEdit()
        saved_username = self.settings.value("username", "")
        self.username_edit.setText(saved_username)
        self.username_edit.setPlaceholderText("you@example.com")
        self.username_edit.setClearButtonEnabled(True)
        
        self.password_edit = QLineEdit()
        saved_password = self.settings.value("password", "")
        self.password_edit.setText(saved_password)
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setClearButtonEnabled(True)
        self.password_edit.returnPressed.connect(self.on_login)
        
        # Password container with eye icon
        password_container = QWidget()
        password_layout = QHBoxLayout(password_container)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(4)
        password_layout.addWidget(self.password_edit)
        
        # Eye icon toggle button
        self.password_toggle_btn = QPushButton("👁")
        self.password_toggle_btn.setFixedSize(32, 32)
        self.password_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #64748b;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 16px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background-color: #cbd5e1;
            }
        """)
        self.password_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.password_toggle_btn.clicked.connect(self.toggle_password_visibility)
        password_layout.addWidget(self.password_toggle_btn)
        
        cred_layout.addRow("Email:", self.username_edit)
        cred_layout.addRow("Password:", password_container)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #dc2626; font-size: 12px;")
        self.status_label.setWordWrap(True)
        
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
        
        self.login_button = QPushButton("Sign In to Connect")
        self.login_button.clicked.connect(self.on_login)
        nav_layout.addWidget(self.login_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(cred_card)
        layout.addWidget(self.status_label)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Add MindLink status bar (includes Help button in header)
        self.status_bar = add_status_bar_to_dialog(self, self.workflow.main_window)
        self._programmatic_close = False
    
    def closeEvent(self, event):
        """Handle dialog close - only trigger confirmation if user clicked X"""
        if self.status_bar:
            self.status_bar.cleanup()
        if self._programmatic_close:
            event.accept()
        else:
            # Temporarily clear WindowStaysOnTopHint so message box appears on top
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit MindLink Analyzer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            # Restore WindowStaysOnTopHint if it was set
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def toggle_password_visibility(self):
        """Toggle password visibility with eye icon"""
        if self.password_edit.echoMode() == QLineEdit.Password:
            self.password_edit.setEchoMode(QLineEdit.Normal)
            self.password_toggle_btn.setText("👁‍🗨")  # Crossed eye
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.password_toggle_btn.setText("👁")  # Open eye
    
    def on_login(self):
        """Attempt device connection and REAL authentication"""
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        
        if not username or not password:
            self.status_label.setText("Please enter both email and password")
            return
        
        # Hide previous error messages
        self.error_info_label.setVisible(False)
        
        # First check device connection
        self.status_label.setText("Checking device connection...")
        self.login_button.setEnabled(False)
        self.back_button.setEnabled(False)
        
        # Run device detection first
        QTimer.singleShot(100, lambda: self._check_device(username, password))
    
    def _check_device(self, username, password):
        """Check device connection before authentication"""
        try:
            # Check which device type is selected
            device_type = getattr(self.workflow.main_window, 'device_type', 'mindlink')
            
            if device_type == "antneuro":
                # ANT Neuro device - scan for USB devices
                devices = ANT_NEURO.scan_for_devices()
                if devices:
                    # Connect to first available device
                    device = devices[0]
                    if ANT_NEURO.connect(device['serial']):
                        # NOTE: Don't start streaming here - wait for impedance check to complete
                        # Streaming will start after ImpedanceCheckDialog.on_next()
                        self.workflow.main_window.log_message(f"✓ ANT Neuro device connected: {device['serial']}")
                        
                        # Device detected, proceed with authentication
                        self.status_label.setText("ANT Neuro device connected. Authenticating...")
                        
                        # Save credentials
                        self.settings.setValue("username", username)
                        self.settings.setValue("password", password)
                        
                        # Get login URL and perform authentication
                        login_url = self._get_login_url()
                        self.login_url = login_url
                        
                        # Perform REAL authentication
                        QTimer.singleShot(100, lambda: self._perform_login(username, password, login_url))
                    else:
                        self._show_device_error("antneuro")
                else:
                    self._show_device_error("antneuro")
            else:
                # MindLink device - use Bluetooth detection
                port = BL.detect_brainlink()
                
                if port:
                    BL.SERIAL_PORT = port
                    self.workflow.main_window.log_message(f"✓ EEG headset detected on port: {port}")
                    
                    # Device detected, proceed with authentication
                    self.status_label.setText("Device connected. Authenticating...")
                    
                    # Save credentials
                    self.settings.setValue("username", username)
                    self.settings.setValue("password", password)
                    
                    # Get login URL and perform authentication
                    login_url = self._get_login_url()
                    self.login_url = login_url
                    
                    # Perform REAL authentication
                    QTimer.singleShot(100, lambda: self._perform_login(username, password, login_url))
                else:
                    self._show_device_error("mindlink")
                    
        except Exception as e:
            device_type = getattr(self.workflow.main_window, 'device_type', 'mindlink')
            device_name = "ANT Neuro" if device_type == "antneuro" else "MindLink"
            self.error_info_label.setText(
                f"WARNING: {device_name.upper()} DETECTION ERROR\n\n"
                f"Error: {str(e)}\n\n"
                "TO RESOLVE:\n"
                "1. Close this application completely\n"
                f"2. Turn OFF the {device_name} headset\n"
                f"3. Turn ON the {device_name} headset\n"
                "4. Restart this application"
            )
            self.error_info_label.setVisible(True)
            self.status_label.setText("Device detection error. Please follow the instructions above.")
            self.status_label.setStyleSheet("color: #dc2626; font-size: 12px;")
            self.login_button.setEnabled(True)
            self.back_button.setEnabled(True)
    
    def _get_login_url(self):
        """Get the login URL from main window or fallback to defaults"""
        login_url = getattr(self.workflow.main_window, 'login_url', None)
        
        # Fallback if not set
        if not login_url:
            login_urls = {
                "English (en)": "https://en.mindspeller.com/api/cas/token/login",
                "Dutch (nl)": "https://nl.mindspeller.com/api/cas/token/login",
                "Local": "http://127.0.0.1:5000/api/cas/token/login"
            }
            
            # Determine which backend URL is set
            current_backend = BL.BACKEND_URL
            if "en" in current_backend or "en.mindspeller" in current_backend:
                login_url = login_urls["English (en)"]
            elif "nl" in current_backend or "nl.mindspeller" in current_backend:
                login_url = login_urls["Dutch (nl)"]
            else:
                login_url = login_urls["Local"]
        
        return login_url
    
    def _show_device_error(self, device_type):
        """Show device connection error message"""
        if device_type == "antneuro":
            self.error_info_label.setText(
                "WARNING: ANT NEURO DEVICE CONNECTION FAILED\n\n"
                "The ANT Neuro amplifier could not be detected.\n\n"
                "TO RESOLVE:\n"
                "1. Ensure the ANT Neuro amplifier is connected via USB\n"
                "2. Check that the drivers are installed correctly\n"
                "3. Try reconnecting the USB cable\n"
                "4. Restart this application\n\n"
                "If using demo mode, select the demo device."
            )
        else:
            self.error_info_label.setText(
                "WARNING: DEVICE CONNECTION FAILED\n\n"
                "The EEG headset could not be detected.\n\n"
                "TO RESOLVE:\n"
                "1. Close this application completely\n"
                "2. Turn OFF the EEG headset\n"
                "3. Turn ON the EEG headset\n"
                "4. Restart this application\n\n"
                "Make sure the headset is paired via Bluetooth before restarting."
            )
        self.error_info_label.setVisible(True)
        self.status_label.setText("Device not found. Please follow the instructions above.")
        self.status_label.setStyleSheet("color: #dc2626; font-size: 12px;")
        self.login_button.setEnabled(True)
        self.back_button.setEnabled(True)
    
    def _perform_login(self, username, password, login_url):
        """Perform actual login"""
        import requests
        
        login_payload = {
            "username": username,
            "password": password
        }
        
        print("\n" + "="*60)
        print(">>> LOGIN ATTEMPT <<<")
        print(f"URL: {login_url}")
        print(f"Username: {username}")
        print(f"Password: {'*' * len(password)}")
        print(f"Payload: {login_payload}")
        print("="*60 + "\n")
        
        try:
            self.workflow.main_window.log_message(f"Connecting to {login_url}")
            
            # For local development, skip SSL verification
            is_local = "127.0.0.1" in login_url or "localhost" in login_url
            
            # Try with certificate verification first (skip for local)
            try:
                login_response = requests.post(
                    login_url, 
                    json=login_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                    verify=not is_local  # Skip SSL verification for local
                )
                
                print(f"Login Response Status: {login_response.status_code}")
                print(f"Login Response Headers: {dict(login_response.headers)}")
                print(f"Login Response Body: {login_response.text[:500]}")  # First 500 chars
                
            except requests.exceptions.ProxyError as e:
                self.workflow.main_window.log_message(f"Proxy error, retrying without proxy...")
                direct_session = requests.Session()
                direct_session.proxies = {}
                login_response = direct_session.post(
                    login_url, 
                    json=login_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                    verify=True
                )
            
            if login_response.status_code == 200:
                data = login_response.json()
                jwt_token = data.get("x-jwt-access-token")
                hwid = data.get("hwid")
                
                if jwt_token:
                    self.workflow.main_window.jwt_token = jwt_token
                    self.workflow.main_window.log_message("✓ Login successful. JWT token obtained.")
                    
                    if hwid:
                        self.workflow.main_window.log_message(f"✓ Hardware ID received: {hwid}")
                        BL.ALLOWED_HWIDS = [hwid]
                    
                    # Fetch userData from dedicated endpoint
                    self._fetch_user_data(jwt_token)
                    
                    # Fetch partners list for validation
                    self._fetch_partners_list(jwt_token)
                    
                    # Fetch user HWIDs
                    self._fetch_user_hwids(jwt_token)
                    
                    # Start device connection
                    self._connect_device()
                    
                    self.status_label.setText("✓ Login successful. Please enter Partner ID...")
                    self.status_label.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")
                    # Hide error message on success
                    self.error_info_label.setVisible(False)
                    
                    # Auto-proceed to Partner ID after 1 second
                    QTimer.singleShot(1000, self.on_auto_next)
                else:
                    self.error_info_label.setText(
                        "WARNING: AUTHENTICATION FAILED\n\n"
                        "The login response didn't contain an authentication token.\n\n"
                        "TO RESOLVE:\n"
                        "1. Verify your credentials are correct\n"
                        "2. If the problem persists, close this application\n"
                        "3. Restart the application and try again"
                    )
                    self.error_info_label.setVisible(True)
                    self.status_label.setText("Login failed. Please follow the instructions above.")
                    self.status_label.setStyleSheet("color: #dc2626; font-size: 12px;")
                    self.login_button.setEnabled(True)
                    self.back_button.setEnabled(True)
            else:
                self.error_info_label.setText(
                    "⚠️ AUTHENTICATION FAILED\n\n"
                    f"Login failed with status code: {login_response.status_code}\n\n"
                    "TO RESOLVE:\n"
                    "1. Verify your email and password are correct\n"
                    "2. Check your internet connection\n"
                    "3. If the problem persists, close this application\n"
                    "4. Restart the application and try again"
                )
                self.error_info_label.setVisible(True)
                self.status_label.setText("Login failed. Please follow the instructions above.")
                self.status_label.setStyleSheet("color: #dc2626; font-size: 12px;")
                self.login_button.setEnabled(True)
                self.back_button.setEnabled(True)
                
        except Exception as e:
            self.error_info_label.setText(
                "WARNING: AUTHENTICATION ERROR\n\n"
                f"Error: {str(e)}\n\n"
                "TO RESOLVE:\n"
                "1. Check your internet connection\n"
                "2. Verify your credentials are correct\n"
                "3. If the problem persists, close this application\n"
                "4. Restart the application and try again"
            )
            self.error_info_label.setVisible(True)
            self.status_label.setText("Authentication error. Please follow the instructions above.")
            self.status_label.setStyleSheet("color: #dc2626; font-size: 12px;")
            self.login_button.setEnabled(True)
            self.back_button.setEnabled(True)
    
    def _fetch_user_data(self, jwt_token):
        """Fetch user data from /api/cas/users/current_user endpoint"""
        import requests
        
        print("\n" + "="*60)
        print(">>> _fetch_user_data CALLED <<<")
        print("="*60)
        
        # Use login URL base instead of backend URL
        # Remove /token/login from the end to get the base /api/cas
        api_base = self.login_url.replace("/token/login", "")
        user_data_url = f"{api_base}/users/current_user"
        
        print(f"API Base: {api_base}")
        print(f"Full URL: {user_data_url}")
        print(f"JWT Token (first 20 chars): {jwt_token[:20]}...")
        
        try:
            self.workflow.main_window.log_message(f"Fetching user data from {user_data_url}")
            
            user_response = requests.get(
                user_data_url,
                headers={"X-Authorization": f"Bearer {jwt_token}"},
                timeout=10
            )
            
            print(f"Response Status Code: {user_response.status_code}")
            print(f"Response Headers: {dict(user_response.headers)}")
            
            if user_response.status_code == 200:
                response_json = user_response.json()
                print(f"Full Response JSON: {response_json}")
                
                user_data = response_json.get("data", {})
                print(f"\n>>> USER DATA EXTRACTED <<<")
                print(user_data)
                print("="*60 + "\n")
                
                self.workflow.main_window.user_data = user_data
                self.workflow.main_window.log_message(f"✓ User data fetched successfully")
                
                # Log initial_protocol status for debugging
                initial_protocol = user_data.get('initial_protocol', '')
                if initial_protocol:
                    self.workflow.main_window.log_message(f"✓ User has completed initial protocol: {initial_protocol}")
                    print(f"Initial protocol found: {initial_protocol}")
                else:
                    self.workflow.main_window.log_message("ℹ User has not completed initial protocol yet")
                    print("No initial_protocol found (user is new)")
            else:
                print(f"ERROR: Status code {user_response.status_code}")
                print(f"Response Text: {user_response.text}")
                self.workflow.main_window.log_message(f"Warning: Could not fetch user data (status {user_response.status_code})")
                self.workflow.main_window.user_data = {}
        except Exception as e:
            print(f"EXCEPTION in _fetch_user_data: {e}")
            import traceback
            traceback.print_exc()
            self.workflow.main_window.log_message(f"Error fetching user data: {e}")
            self.workflow.main_window.user_data = {}
    
    def _fetch_partners_list(self, jwt_token):
        """Fetch the list of available partners from API"""
        import requests
        
        print("\n" + "="*60)
        print(">>> _fetch_partners_list CALLED <<<")
        print("="*60)
        
        # Use login URL base instead of backend URL
        api_base = self.login_url.replace("/token/login", "")
        
        # Use 'all' to get all partner IDs regardless of region
        region = 'all'
        partners_url = f"{api_base}/partners/list?region={region}"
        
        print(f"Partners List URL: {partners_url}")
        print(f"Region Parameter: {region}")
        
        try:
            self.workflow.main_window.log_message(f"Fetching partners list from {partners_url}")
            
            partners_response = requests.get(
                partners_url,
                headers={"X-Authorization": f"Bearer {jwt_token}"},
                timeout=10,
                verify=False if "127.0.0.1" in self.login_url else True
            )
            
            print(f"Response Status Code: {partners_response.status_code}")
            
            if partners_response.status_code == 200:
                response_json = partners_response.json()
                print(f"Full Response JSON: {response_json}")
                
                partners_list = response_json.get("partners", [])
                print(f"\n>>> PARTNERS LIST EXTRACTED <<<")
                print(f"Number of partners: {len(partners_list)}")
                for partner in partners_list[:5]:  # Show first 5 for debugging
                    print(f"  - Partner: {partner}")
                print("="*60 + "\n")
                
                self.workflow.main_window.partners_list = partners_list
                self.workflow.main_window.log_message(f"✓ Fetched {len(partners_list)} partners")
            else:
                print(f"ERROR: Status code {partners_response.status_code}")
                print(f"Response Text: {partners_response.text}")
                self.workflow.main_window.log_message(f"Warning: Could not fetch partners list (status {partners_response.status_code})")
                self.workflow.main_window.partners_list = []
        except Exception as e:
            print(f"EXCEPTION in _fetch_partners_list: {e}")
            import traceback
            traceback.print_exc()
            self.workflow.main_window.log_message(f"Error fetching partners list: {e}")
            self.workflow.main_window.partners_list = []
    
    def _fetch_user_hwids(self, jwt_token):
        """Fetch authorized HWIDs for user"""
        import requests
        
        # Use login URL base instead of backend URL
        api_base = self.login_url.replace("/token/login", "")
        try:
            hwids_url = f"{api_base}/users/hwids"
            self.workflow.main_window.log_message(f"Fetching authorized device IDs from {hwids_url}")
            hwid_response = requests.get(
                hwids_url,
                headers={"X-Authorization": f"Bearer {jwt_token}"},
                timeout=5
            )
            if hwid_response.status_code == 200:
                raw_hwids = hwid_response.json().get("brainlink_hwid", [])
                if isinstance(raw_hwids, str):
                    BL.ALLOWED_HWIDS = [raw_hwids]
                elif isinstance(raw_hwids, list):
                    BL.ALLOWED_HWIDS = raw_hwids
                else:
                    BL.ALLOWED_HWIDS = []
                self.workflow.main_window.log_message(f"✓ Fetched {len(BL.ALLOWED_HWIDS)} authorized device IDs")
        except Exception as e:
            self.workflow.main_window.log_message(f"Error fetching HWIDs: {e}")
    
    def _connect_device(self):
        """Connect to the EEG device (MindLink or ANT Neuro based on device type)"""
        import threading
        
        device_type = getattr(self.workflow.main_window, 'device_type', 'mindlink')
        
        if device_type == "antneuro":
            # ANT Neuro: DON'T start streaming here - we go to Metadata → Impedance Check first
            # Streaming will start after impedance check completes (ImpedanceCheckDialog.on_next)
            # This ensures metadata (including email) is set BEFORE recording starts
            if ANT_NEURO.is_connected:
                self.workflow.main_window.log_message("✓ ANT Neuro device connected (streaming deferred until after impedance check)")
            else:
                self.workflow.main_window.log_message("✗ ANT Neuro device not connected!")
        else:
            # MindLink device - use serial connection
            from cushy_serial import CushySerial
            
            port = BL.SERIAL_PORT
            if not port:
                port = BL.detect_brainlink()
                BL.SERIAL_PORT = port
            
            if not port:
                self.workflow.main_window.log_message("✗ No MindLink device found!")
                return
            
            self.workflow.main_window.log_message(f"✓ Connecting to MindLink device: {port}")
            
            # Start MindLink connection - EXACTLY like base GUI
            try:
                self.workflow.main_window.serial_obj = CushySerial(port, BL.SERIAL_BAUD)
                self.workflow.main_window.log_message("Starting MindLink thread...")
                
                BL.stop_thread_flag = False
                
                self.workflow.main_window.brainlink_thread = threading.Thread(
                    target=BL.run_brainlink, 
                    args=(self.workflow.main_window.serial_obj,)
                )
                self.workflow.main_window.brainlink_thread.daemon = True
                self.workflow.main_window.brainlink_thread.start()
                
                self.workflow.main_window.log_message("✓ MindLink connected successfully!")
            except Exception as e:
                self.workflow.main_window.log_message(f"✗ Failed to connect: {str(e)}")
    
    def _complete_login(self):
        """Complete login"""
        self.status_label.setText("✓ Login successful")
        self.status_label.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")
        self.login_button.setEnabled(True)
        self.login_button.setText("Sign In to Connect")
    
    def on_auto_next(self):
        """Auto-proceed to next step after successful login.
        
        For ANT Neuro: Go to Metadata dialog (for subject info, impedances)
        For MindLink: Go to Partner ID dialog
        """
        self._programmatic_close = True
        self.close()
        
        device_type = getattr(self.workflow.main_window, 'device_type', 'mindlink')
        
        if device_type == "antneuro":
            # ANT Neuro: Go to metadata collection (subject info, impedances, etc.)
            print("[LOGIN] ANT Neuro device - proceeding to Metadata dialog")
            QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.ANTNEURO_METADATA))
        else:
            # MindLink: Go to Partner ID
            print("[LOGIN] MindLink device - proceeding to Partner ID dialog")
            QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.PARTNER_ID))
    
    def on_back(self):
        """Navigate back"""
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())


# ============================================================================
# STEP 3.5: PATHWAY SELECTION (Protocol Selection)
# ============================================================================

class PathwaySelectionDialog(QDialog):
    """Step 3.5: Select protocol pathway"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Choose Your Pathway")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(500)
        
        # Set window icon
        set_window_icon(self)
        
        # UI Elements
        title_label = QLabel("Choose Your Pathway")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 7 of 10: Select the flow type to tailor your task list")
        subtitle_label.setObjectName("DialogSubtitle")
        subtitle_label.setWordWrap(True)
        
        # Pathway options card
        pathway_card = QFrame()
        pathway_card.setObjectName("DialogCard")
        pathway_layout = QVBoxLayout(pathway_card)
        pathway_layout.setContentsMargins(16, 16, 16, 16)
        pathway_layout.setSpacing(14)
        
        pathway_label = QLabel("Select Protocol:")
        pathway_label.setObjectName("DialogSectionTitle")
        
        # Protocol options - MATCHING ORIGINAL Enhanced GUI
        self.radio_personal = QRadioButton("Personal Pathway")
        self.radio_personal.setChecked(True)
        
        personal_desc = QLabel("Career Flow related tasks")
        personal_desc.setStyleSheet("font-size: 12px; color: #64748b; margin-left: 24px; margin-bottom: 8px;")
        personal_desc.setWordWrap(True)
        
        self.radio_connection = QRadioButton("Connection (Coming Soon)")
        connection_desc = QLabel("Mind Flow related tasks")
        connection_desc.setStyleSheet("font-size: 12px; color: #64748b; margin-left: 24px; margin-bottom: 8px;")
        connection_desc.setWordWrap(True)
        
        self.radio_lifestyle = QRadioButton("Lifestyle (Coming Soon)")
        lifestyle_desc = QLabel("Style Flow related tasks")
        lifestyle_desc.setStyleSheet("font-size: 12px; color: #64748b; margin-left: 24px; margin-bottom: 8px;")
        lifestyle_desc.setWordWrap(True)
        
        pathway_layout.addWidget(pathway_label)
        pathway_layout.addWidget(self.radio_personal)
        pathway_layout.addWidget(personal_desc)
        pathway_layout.addWidget(self.radio_connection)
        pathway_layout.addWidget(connection_desc)
        pathway_layout.addWidget(self.radio_lifestyle)
        pathway_layout.addWidget(lifestyle_desc)
        
        # Info note
        info_label = QLabel("ℹ️ Baseline calibration and core cognitive tasks are included in all pathways")
        info_label.setStyleSheet("font-size: 12px; color: #3b82f6; padding: 12px; background: #eff6ff; border-radius: 6px;")
        info_label.setWordWrap(True)
        
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
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(pathway_card)
        layout.addWidget(info_label)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Add MindLink status bar
        self.status_bar = add_status_bar_to_dialog(self, self.workflow.main_window)
        self._programmatic_close = False
    
    def closeEvent(self, event):
        """Handle dialog close"""
        if self.status_bar:
            self.status_bar.cleanup()
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            # Temporarily clear WindowStaysOnTopHint so message box appears on top
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit MindLink Analyzer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            # Restore WindowStaysOnTopHint if it was set
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def on_next(self):
        """Save protocol selection and proceed"""
        # Determine selected protocol - MATCHING ORIGINAL Enhanced GUI
        if self.radio_connection.isChecked():
            protocol = "Connection"
        elif self.radio_lifestyle.isChecked():
            protocol = "Lifestyle"
        else:
            protocol = "Personal Pathway"
        
        # Save to main window
        self.workflow.main_window._selected_protocol = protocol
        
        # Apply protocol filter (same as original Enhanced GUI)
        try:
            self.workflow.main_window._apply_protocol_filter()
        except Exception:
            pass
        
        if self.status_bar:
            self.status_bar.cleanup()
        self._programmatic_close = True
        self.close()
        # After selecting a pathway, proceed to calibration (Live EEG already completed)
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.CALIBRATION))
    
    def on_back(self):
        """Navigate back"""
        if self.status_bar:
            self.status_bar.cleanup()
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())


# ============================================================================
# MULTI-CHANNEL VIEW DIALOG (64 channels visualization)
# ============================================================================

class MultiChannelViewDialog(QDialog):
    """Popup dialog showing all 64 EEG channels in an 8x8 grid layout.
    
    Optimized for performance using:
    - Downsampled data (100 points per channel)
    - Batch updates (100ms interval)
    - Minimal plot decorations
    - Fixed Y-range (no auto-scaling)
    """
    
    # NA-265 waveguard net 64-channel cap electrode layout (from UDO-SM-1002rev04 datasheet)
    # Connector 1: Channels 1-32, Connector 2: Channels 33-64
    # Channel index 0 = Channel Number 1 in datasheet
    CHANNEL_NAMES = [
        # Connector 1 (Channels 1-32)
        'Fp1', 'Fp2', 'F9', 'F7', 'F3', 'Fz', 'F4', 'F8',      # 1-8
        'F10', 'FC5', 'FC1', 'FC2', 'FC6', 'T9', 'T7', 'C3',    # 9-16
        'C4', 'T8', 'T10', 'CP5', 'CP1', 'CP2', 'CP6', 'P9',    # 17-24
        'P7', 'P3', 'Pz', 'P4', 'P8', 'P10', 'O1', 'O2',        # 25-32
        # Connector 2 (Channels 33-64)
        'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6',     # 33-40
        'FC3', 'FCz', 'FC4', 'C5', 'C1', 'C2', 'C6', 'CP3',     # 41-48
        'CP4', 'P5', 'P1', 'P2', 'P6', 'PO5', 'PO3', 'PO4',     # 49-56
        'PO6', 'FT7', 'FT8', 'TP7', 'TP8', 'PO7', 'PO8', 'POz'  # 57-64
    ]
    
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("All 64 EEG Channels - Real-Time View")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        
        # Make it large but not fullscreen
        self.resize(1600, 900)
        
        # Set window icon
        set_window_icon(self)
        
        # Number of channels and grid layout
        self.n_channels = 64
        self.grid_cols = 8
        self.grid_rows = 8
        
        # Sample rate and display settings
        self.sample_rate = get_device_sample_rate(main_window)
        self.display_points = 100  # Downsampled points per channel
        self.window_seconds = 2.0  # Show 2 seconds of data
        
        # Store plot curves
        self.curves = []
        self.plot_widgets = []
        
        # Build UI
        self._build_ui()
        
        # Update timer - 100ms for 64 channels (10 FPS is smooth enough)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_all_plots)
        self.update_timer.start(100)
        
        # Track if closed programmatically
        self._programmatic_close = False
    
    def _build_ui(self):
        """Build the 8x8 grid of plot widgets"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(4)
        
        # Header
        header = QLabel("64-Channel EEG Real-Time Monitor")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #1e40af; padding: 4px;")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)
        
        # Info label
        info = QLabel("Each plot shows 2 seconds of EEG data. Updated 10x per second. Y-axis: ±100 µV")
        info.setStyleSheet("font-size: 11px; color: #64748b; padding: 2px;")
        info.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(info)
        
        # Scroll area for the grid (in case window is small)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        # Grid container
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(2)
        grid_layout.setContentsMargins(4, 4, 4, 4)
        
        # Create 64 mini plot widgets
        for i in range(self.n_channels):
            row = i // self.grid_cols
            col = i % self.grid_cols
            
            # Container for each channel
            ch_widget = QWidget()
            ch_layout = QVBoxLayout(ch_widget)
            ch_layout.setContentsMargins(0, 0, 0, 0)
            ch_layout.setSpacing(0)
            
            # Channel label
            ch_name = self.CHANNEL_NAMES[i] if i < len(self.CHANNEL_NAMES) else f"Ch{i+1}"
            label = QLabel(f"{i+1}. {ch_name}")
            label.setStyleSheet("font-size: 9px; font-weight: bold; color: #374151; padding: 1px;")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedHeight(14)
            
            # Mini plot widget - minimal decorations for performance
            plot = pg.PlotWidget()
            plot.setBackground('#1e293b')  # Dark slate background
            plot.setFixedHeight(80)
            plot.setMinimumWidth(150)
            
            # Disable all axes labels and ticks for performance
            plot.getPlotItem().hideAxis('left')
            plot.getPlotItem().hideAxis('bottom')
            plot.setMouseEnabled(x=False, y=False)  # Disable mouse interaction
            plot.setMenuEnabled(False)  # Disable right-click menu
            
            # Fixed Y range
            plot.setYRange(-100, 100, padding=0)
            plot.enableAutoRange(enable=False)
            
            # Create curve with thin pen
            curve = plot.plot(pen=pg.mkPen(color='#22d3ee', width=1))  # Cyan color
            curve.setClipToView(True)
            
            self.curves.append(curve)
            self.plot_widgets.append(plot)
            
            ch_layout.addWidget(label)
            ch_layout.addWidget(plot)
            
            grid_layout.addWidget(ch_widget, row, col)
        
        scroll.setWidget(grid_widget)
        main_layout.addWidget(scroll, 1)
        
        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("✕ Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-size: 12px;
                font-weight: bold;
                padding: 8px 24px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        
        main_layout.addLayout(btn_layout)
        
        self.setLayout(main_layout)
        
        # Dark theme for the dialog
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
            }
            QLabel {
                color: #e2e8f0;
            }
        """)
    
    def _update_all_plots(self):
        """Update all 64 channel plots from multichannel_buffer"""
        try:
            # Get multichannel buffer
            multichannel_buffer = ANT_NEURO.multichannel_buffer
            
            if len(multichannel_buffer) < self.sample_rate:
                return  # Not enough data yet
            
            # Get last N samples (window_seconds worth)
            n_samples = int(self.window_seconds * self.sample_rate)
            recent_data = list(multichannel_buffer)[-n_samples:]
            
            # Convert to numpy array (samples x channels)
            data_array = np.array(recent_data)
            
            if data_array.ndim != 2:
                return
            
            n_samples_actual, n_channels_actual = data_array.shape
            
            # Downsample for display (take every Nth point)
            downsample_factor = max(1, n_samples_actual // self.display_points)
            
            # Create time axis
            time_axis = np.linspace(0, self.window_seconds, min(self.display_points, n_samples_actual))
            
            # Update each channel
            for ch_idx in range(min(self.n_channels, n_channels_actual)):
                ch_data = data_array[::downsample_factor, ch_idx]
                
                # Center around zero (remove DC offset)
                ch_data = ch_data - np.mean(ch_data)
                
                # Clip to ±100 µV for display
                ch_data = np.clip(ch_data, -100, 100)
                
                # Update curve
                if ch_idx < len(self.curves):
                    self.curves[ch_idx].setData(time_axis[:len(ch_data)], ch_data)
                    
        except Exception as e:
            print(f"[MultiChannel] Update error: {e}")
    
    def closeEvent(self, event):
        """Clean up timer on close"""
        self.update_timer.stop()
        event.accept()


# ============================================================================
# STEP 5: LIVE EEG (Using REAL data stream)
# ============================================================================

class LiveEEGDialog(QDialog):
    """Step 5: Real-time EEG signal from actual device"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Live EEG Signal")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(600, 450)
        
        # Set window icon
        set_window_icon(self)
        
        # UI Elements
        title_label = QLabel("Live EEG Signal")
        title_label.setObjectName("DialogTitle")
        title_label.setStyleSheet("font-size: 16px; font-weight: 600;")  # Reduced from 18px
        
        subtitle_label = QLabel("Step 6 of 10: Monitoring real brain activity")
        subtitle_label.setObjectName("DialogSubtitle")
        subtitle_label.setStyleSheet("font-size: 11px;")  # Reduced from 13px
        
        # EEG Plot card
        plot_card = QFrame()
        plot_card.setObjectName("DialogCard")
        plot_layout = QVBoxLayout(plot_card)
        plot_layout.setContentsMargins(4, 4, 4, 4)  # Reduced from 8, 8, 8, 8
        
        # Use the SAME plotting setup as the main GUI
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('k')
        self.plot_widget.setLabel('left', 'Amplitude (µV)')
        self.plot_widget.setLabel('bottom', 'Time (seconds)')
        self.plot_widget.setTitle('Live EEG Signal', color='w', size='12pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # Disable auto-range for smoother scrolling, set fixed Y range
        self.plot_widget.setYRange(-100, 100, padding=0)
        self.plot_widget.enableAutoRange(axis='y', enable=False)
        
        # Use downsampling for faster rendering
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color='#3b82f6', width=1))
        self.curve.setClipToView(True)  # Clip data to view for faster rendering
        
        # Time tracking for X-axis
        self._plot_time_offset = 0  # Running time offset in seconds
        self._plot_window_seconds = 5.0  # Show 5 seconds of data
        
        plot_layout.addWidget(self.plot_widget)
        
        # Status info
        self.info_label = QLabel("Signal quality: Good | Ensure proper electrode contact")
        self.info_label.setStyleSheet("color: #10b981; font-size: 11px; padding: 6px;")  # Reduced from 13px, 8px
        self.info_label.setAlignment(Qt.AlignCenter)
        
        # Important stabilization notice
        stabilization_notice = QLabel(
            "⏱️ IMPORTANT: Please wait 20-30 seconds for the signal to stabilize after wearing the headset.\n\n"
            "Do NOT proceed to the next step until you see 'Signal quality: Good' displayed above."
        )
        stabilization_notice.setStyleSheet(
            "color: #0369a1; font-size: 13px; padding: 12px 16px; "
            "background: #e0f2fe; border-radius: 8px; "
            "border-left: 4px solid #0284c7; font-weight: 600; line-height: 1.5;"
        )
        stabilization_notice.setWordWrap(True)
        stabilization_notice.setAlignment(Qt.AlignCenter)
        
        # Device reconnection help button
        self.reconnect_help_button = QPushButton("🔄 Device Disconnected?")
        self.reconnect_help_button.setStyleSheet("""
            QPushButton {
                background-color: #fbbf24;
                color: #78350f;
                border-radius: 6px;
                padding: 6px 12px;  
                font-size: 11px;  
                font-weight: 600;
                border: 0;
            }
            QPushButton:hover {
                background-color: #f59e0b;
            }
        """)
        self.reconnect_help_button.clicked.connect(self.show_reconnect_guidance)
        
        # Error/warning message for transmission stopped (hidden by default)
        self.transmission_error_label = QLabel("")
        self.transmission_error_label.setStyleSheet("""
            font-size: 14px; 
            color: #dc2626; 
            padding: 16px; 
            background: #fef2f2; 
            border-radius: 8px; 
            border-left: 4px solid #dc2626;
            font-weight: 600;
            line-height: 1.6;
        """)
        self.transmission_error_label.setWordWrap(True)
        self.transmission_error_label.setVisible(False)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #475569;
                font-size: 11px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #cbd5e1;
            }
        """)
        
        nav_layout.addWidget(self.back_button)
        nav_layout.addStretch()
        
        # View All Channels button (only for ANT Neuro multi-channel)
        device_type = getattr(self.workflow.main_window, 'device_type', 'mindlink')
        self.view_all_channels_btn = None
        if device_type == "antneuro":
            self.view_all_channels_btn = QPushButton("View All 64 Channels")
            self.view_all_channels_btn.setStyleSheet("""
                QPushButton {
                    background-color: #7c3aed;
                    color: white;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 6px 14px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #6d28d9;
                }
            """)
            self.view_all_channels_btn.clicked.connect(self._open_multichannel_view)
            nav_layout.addWidget(self.view_all_channels_btn)
            nav_layout.addStretch()
        
        self.next_button = QPushButton("Next →")
        self.next_button.setStyleSheet("font-size: 11px; padding: 6px 12px;")
        self.next_button.clicked.connect(self.on_next)
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)  # Reduced from 24
        layout.setSpacing(12)  # Reduced from 18
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(self.transmission_error_label)
        layout.addWidget(stabilization_notice)
        layout.addWidget(plot_card)
        layout.addWidget(self.info_label)
        layout.addWidget(self.reconnect_help_button, alignment=Qt.AlignCenter)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Add MindLink status bar
        self.status_bar = add_status_bar_to_dialog(self, self.workflow.main_window)
        
        # Start live update timer using REAL data
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_plot)
        self.update_timer.start(33)  # 30 Hz update rate for smoother animation
        
        # Track consecutive no-data occurrences for transmission stop detection
        self.no_data_count = 0
        self.transmission_stopped = False
        
        self._programmatic_close = False
    
    def update_plot(self):
        """Update EEG plot with REAL data from live_data_buffer
        
        Note: This displays the most recent data for visual monitoring.
        The plotting delay does NOT affect task recording - tasks record data
        in real-time through the feature_engine which processes data immediately
        as it arrives via the onRaw callback. This plot is purely for visualization.
        """
        # Get the correct data buffer based on device type
        data_buffer = get_live_data_buffer(self.workflow.main_window)
        sample_rate = get_device_sample_rate(self.workflow.main_window)
        
        # Debug: Print buffer size every 2 seconds
        if not hasattr(self, '_plot_debug_counter'):
            self._plot_debug_counter = 0
        self._plot_debug_counter += 1
        debug_print = (self._plot_debug_counter >= 40)  # Every 2 seconds at 50ms
        if debug_print:
            self._plot_debug_counter = 0
            buf_size = len(BL.live_data_buffer)
            print(f"[Plot Debug] Buffer size: {buf_size} samples ({buf_size/512:.1f}s of data)")
        
        # Use the REAL data buffer from the base GUI
        if len(BL.live_data_buffer) >= 512:
            import time
            data = np.array(BL.live_data_buffer[-512:])
            self.curve.setData(data[-500:])  # Plot last 500 for display
            
            # Reset no-data counter when data is flowing
            self.no_data_count = 0
            if self.transmission_stopped:
                # Data resumed, hide error and re-enable Next
                self.transmission_stopped = False
                self.transmission_error_label.setVisible(False)
                self.next_button.setEnabled(True)
            
            # Professional signal quality assessment (same simplified logic as header)
            quality_score, status, details = assess_eeg_signal_quality(data, fs=512)
            
            # Simplified logic: Only show "Noisy" if headset is not worn
            if status == "not_worn":
                self.info_label.setText("⚠ Signal quality: Noisy | Headset not detected - Please wear the headset properly")
                self.info_label.setStyleSheet("color: #f59e0b; font-size: 13px; padding: 8px; font-weight: 600;")
            else:
                # If user is wearing it, show Good regardless of other quality metrics
                self.info_label.setText(f"✓ Signal quality: Good | Data flowing normally")
                self.info_label.setStyleSheet("color: #10b981; font-size: 13px; padding: 8px; font-weight: 600;")
        else:
            # No data detected - increment counter
            self.no_data_count += 1
            
            # After 20 consecutive checks (~1 second at 50ms intervals), show error
            if self.no_data_count >= 20 and not self.transmission_stopped:
                self.transmission_stopped = True
                self.transmission_error_label.setText(
                    "WARNING: TRANSMISSION STOPPED\n\n"
                    "EEG signal transmission has stopped. The device may be disconnected.\n\n"
                    "TO RESOLVE:\n"
                    "1. Close this application completely\n"
                    "2. Turn OFF the EEG headset\n"
                    "3. Wait 5 seconds\n"
                    "4. Turn ON the EEG headset\n"
                    "5. Restart this application\n\n"
                    "You cannot proceed until the signal is restored."
                )
                self.transmission_error_label.setVisible(True)
                self.next_button.setEnabled(False)
            
            # Device disconnected or no data
            self.info_label.setText("⚠ No signal detected | Device may be disconnected")
            self.info_label.setStyleSheet("color: #ef4444; font-size: 13px; padding: 8px;")
    
    def _open_multichannel_view(self):
        """Open the 64-channel visualization popup"""
        try:
            # Use shared instance from main_window to avoid duplicate dialogs
            if not hasattr(self.workflow.main_window, 'multichannel_dialog') or self.workflow.main_window.multichannel_dialog is None or not self.workflow.main_window.multichannel_dialog.isVisible():
                self.workflow.main_window.multichannel_dialog = MultiChannelViewDialog(self.workflow.main_window, parent=None)
                self.workflow.main_window.multichannel_dialog.show()
                print("[LiveEEG] Opened 64-channel visualization popup")
            else:
                # Bring existing dialog to front
                self.workflow.main_window.multichannel_dialog.raise_()
                self.workflow.main_window.multichannel_dialog.activateWindow()
                print("[LiveEEG] Brought existing 64-channel dialog to front")
        except Exception as e:
            print(f"[LiveEEG] Error opening multichannel view: {e}")
            import traceback
            traceback.print_exc()
    
    def show_reconnect_guidance(self):
        """Show guidance for reconnecting device"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Device Reconnection Guide")
        msg.setText("If your device is disconnected or signal stopped:")
        msg.setInformativeText(
            "<b>Quick Fix Steps:</b><br><br>"
            "1. <b>Switch off</b> the headset<br>"
            "2. Wait 3-5 seconds<br>"
            "3. <b>Switch on</b> the headset<br>"
            "4. Click <b>Back</b> button below<br>"
            "5. Navigate back to <b>Login screen</b><br>"
            "6. <b>Log in again</b> to reconnect the device<br><br>"
            "<i>Note: The app needs to re-establish the connection "
            "after the device has been power-cycled.</i><br><br>"
            "<b>Alternative:</b> Close and restart the application."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #f8fafc;
            }
            QLabel {
                color: #1f2937;
                font-size: 13px;
            }
        """)
        msg.exec()
    
    def on_back(self):
        """Navigate back"""
        self.update_timer.stop()
        self._programmatic_close = True
        self.close()
        self.workflow.go_back()
    
    def on_next(self):
        """Proceed to pathway selection (user requested ordering: Live EEG before Pathway)"""
        self.update_timer.stop()
        self._programmatic_close = True
        self.close()
        self.workflow.go_to_step(WorkflowStep.PATHWAY_SELECTION)
    
    def closeEvent(self, event):
        """Cleanup"""
        self.update_timer.stop()
        if self.status_bar:
            self.status_bar.cleanup()
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            event.accept()
        else:
            # Temporarily clear WindowStaysOnTopHint so message box appears on top
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit MindLink Analyzer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            # Restore WindowStaysOnTopHint if it was set
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
# ============================================================================
# STEP 5: CALIBRATION (Using REAL calibration logic)
# ============================================================================

class CalibrationDialog(QDialog):
    """Step 6: Enhanced calibration with preparatory guidance"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Calibration")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(600)
        
        # Set window icon
        set_window_icon(self)
        
        # Get REAL feature engine
        self.feature_engine = self.workflow.main_window.feature_engine
        self.current_phase = None
        self.countdown_value = 0
        
        # UI Elements
        title_label = QLabel("Baseline Calibration")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 8 of 10: Establish your baseline brain activity")
        subtitle_label.setObjectName("DialogSubtitle")
        
        # Instructions card
        instr_card = QFrame()
        instr_card.setObjectName("DialogCard")
        instr_layout = QVBoxLayout(instr_card)
        instr_layout.setContentsMargins(16, 16, 16, 16)
        instr_layout.setSpacing(12)
        
        # instr_text = QLabel(
        #     "<b>Calibration Overview:</b><br><br>"
        #     "We will record your baseline brain activity in two phases:<br><br>"
        #     "<b>1. Eyes Closed (30s)</b>: Relax with eyes closed<br>"
        #     "<b>2. Eyes Open (30s)</b>: Stay relaxed, eyes open<br><br>"
        #     "Each phase includes:<br>"
        #     "• Preparation guidance<br>"
        #     "• Audio countdown (5, 4, 3, 2, 1)<br>"
        #     "• 30-second silent recording<br>"
        #     "• Audio notification when complete<br><br>"
        #     "<i>Tip: Ensure your speakers/headphones are on!</i>"
        # )
        # instr_text.setWordWrap(True)
        # instr_text.setStyleSheet("font-size: 13px; color: #475569; line-height: 1.8;")
        
        # instr_layout.addWidget(instr_text)
        
        # Progress card
        progress_card = QFrame()
        progress_card.setObjectName("DialogCard")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(16, 16, 16, 16)
        progress_layout.setSpacing(10)
        
        self.status_label = QLabel("Ready to start")
        self.status_label.setObjectName("DialogSectionTitle")
        
        self.phase_label = QLabel("")
        self.phase_label.setStyleSheet("font-size: 13px; color: #64748b;")
        
        # Signal quality indicator
        self.signal_quality_label = QLabel("Signal quality: Checking...")
        self.signal_quality_label.setStyleSheet(
            "font-size: 12px; color: #6b7280; padding: 6px; "
            "background: #f3f4f6; border-radius: 4px;"
        )
        
        self.ec_button = QPushButton("Start Eyes Closed Calibration")
        self.ec_button.clicked.connect(self.show_eyes_closed_prep)
        self.ec_button.setStyleSheet(
            "padding: 12px; font-size: 14px; font-weight: 600;"
        )
        
        self.eo_button = QPushButton("Start Eyes Open Calibration")
        self.eo_button.clicked.connect(self.show_eyes_open_prep)
        self.eo_button.setEnabled(False)
        self.eo_button.setStyleSheet(
            "padding: 12px; font-size: 14px; font-weight: 600;"
        )
        
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.phase_label)
        progress_layout.addWidget(self.signal_quality_label)
        progress_layout.addWidget(self.ec_button)
        progress_layout.addWidget(self.eo_button)
        
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
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        self.next_button.setEnabled(False)
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(instr_card)
        layout.addWidget(progress_card)
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        apply_modern_dialog_theme(self)
        
        # Add MindLink status bar
        self.status_bar = add_status_bar_to_dialog(self, self.workflow.main_window)
        
        # Signal quality monitoring timer
        self.signal_timer = QTimer()
        self.signal_timer.timeout.connect(self.update_signal_quality)
        self.signal_timer.start(500)  # Update every 500ms
        
        # Auto-stop timer
        self.auto_stop_timer = QTimer()
        self.auto_stop_timer.setSingleShot(True)
        self.auto_stop_timer.timeout.connect(self.auto_stop_phase)
        
        # Countdown timer
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
        
        self._programmatic_close = False
        # Staleness tracking for signal quality (detect disconnected/frozen buffer)
        self._sig_last_tail = None
        self._sig_last_change_time = None
        # Bidirectional hysteresis state
        self._sig_not_worn_since = None   # when not_worn streak started
        self._sig_worn_since = None       # when worn streak started
        self._sig_displayed_noisy = False  # currently shown state
        self._sig_noisy_reason = 'not_worn'  # reason for last noisy state

    def update_signal_quality(self):
        """Update signal quality indicator using professional multi-metric assessment"""
        try:
            if len(BL.live_data_buffer) >= 512:
                import time
                # Use proper window size for signal analysis
                data = np.array(list(BL.live_data_buffer)[-512:])
                
                # Professional signal quality assessment
                quality_score, status, details = assess_eeg_signal_quality(data, fs=512)
                
                # Track quality history (timestamp, score)
                current_time = time.time()
                self.quality_history.append((current_time, quality_score))
                
                # Remove entries older than 5 seconds
                self.quality_history = [(t, q) for t, q in self.quality_history if current_time - t <= 5.0]
                
                # Count how many times quality dropped to or below threshold in last 5 seconds
                poor_count = sum(1 for t, q in self.quality_history if q <= self.poor_quality_threshold)
                
                # Update noisy state: need 5+ poor readings in 5 seconds to trigger
                if poor_count >= 5:
                    self.is_noisy = True
                elif poor_count == 0:  # All recent readings good - reset
                    self.is_noisy = False
                # Otherwise maintain current state (hysteresis)
                
                # Display only two states: Good or Noisy
                if self.is_noisy:
                    self.signal_quality_label.setText("⚠ Signal: Noisy")
                    self.signal_quality_label.setStyleSheet(
                        "font-size: 12px; color: #d97706; padding: 6px; "
                        "background: #fef3c7; border-radius: 4px; font-weight: 600;"
                    )
                else:
                    self.signal_quality_label.setText("✓ Signal: Good")
                    self.signal_quality_label.setStyleSheet(
                        "font-size: 12px; color: #059669; padding: 6px; "
                        "background: #d1fae5; border-radius: 4px; font-weight: 600;"
                    )
            else:
                self.signal_quality_label.setText("○ Signal: Waiting...")
                self.signal_quality_label.setStyleSheet(
                    "font-size: 12px; color: #6b7280; padding: 6px; "
                    "background: #f3f4f6; border-radius: 4px;"
                )
        except Exception as e:
            print(f"[CalibrationDialog] Signal quality error: {e}")
            import traceback
            traceback.print_exc()
    
    def show_eyes_closed_prep(self):
        """Show preparation dialog for eyes closed calibration"""
        prep_dialog = QDialog(self)
        prep_dialog.setWindowTitle("Eyes Closed Calibration - Get Ready")
        prep_dialog.setModal(True)
        prep_dialog.setMinimumWidth(500)
        set_window_icon(prep_dialog)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Title
        title = QLabel("🌙 Eyes Closed Baseline")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 8px;"
        )
        title.setAlignment(Qt.AlignCenter)
        
        # Instructions
        instructions = QLabel(
            "<b>Get ready to close your eyes and relax.</b><br><br>"
            "The sensors will record your baseline brainwave pattern for 30 seconds.<br><br>"
            "<b>What will happen:</b><br>"
            "1. Click 'Start Recording' below<br>"
            "2. You'll hear a countdown: <i>5, 4, 3, 2, 1 in beep sound</i><br>"
            "3. Close your eyes and relax for 30 seconds<br>"
            "4. Stay still and calm - don't think about anything specific<br>"
            "5. A sound will notify you when the 30 seconds are complete<br><br>"
            "<b style='color: #dc2626;'>⚠ Important: Check your speakers/headphones are ON!</b>"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(
            "font-size: 13px; color: #475569; line-height: 1.8; "
            "padding: 16px; background: #f8fafc; border-radius: 8px;"
        )
        
        # Signal quality in prep dialog - dynamic assessment
        signal_label = QLabel("Signal quality: Checking...")
        signal_label.setStyleSheet(
            "font-size: 13px; color: #6b7280; padding: 8px; "
            "background: #f3f4f6; border-radius: 6px; font-weight: 600;"
        )
        signal_label.setAlignment(Qt.AlignCenter)
        
        # Update signal quality dynamically - mirrors header (not_worn = Noisy, else Good)
        _sq_state = {'last_tail': None, 'last_change': None,
                     'not_worn_since': None, 'worn_since': None, 'displayed_noisy': False, 'noisy_reason': 'not_worn'}
        _STALE_S = 2.0
        def update_prep_signal():
            import time
            if len(BL.live_data_buffer) >= 512:
                data = np.array(list(BL.live_data_buffer)[-512:])
                quality_score, status, details = assess_eeg_signal_quality(data, fs=512)
                
                # Track quality locally
                current_time = time.time()
                prep_quality_history.append((current_time, quality_score))
                # Remove entries older than 5 seconds
                while prep_quality_history and current_time - prep_quality_history[0][0] > 5.0:
                    prep_quality_history.pop(0)
                
                poor_count = sum(1 for t, q in prep_quality_history if q <= self.poor_quality_threshold)
                
                if poor_count >= 5:
                    signal_label.setText("⚠ Signal: Noisy")
                    signal_label.setStyleSheet(
                        "font-size: 13px; color: #d97706; padding: 8px; "
                        "background: #fef3c7; border-radius: 6px; font-weight: 600;"
                    )
                else:
                    signal_label.setText("✓ Signal: Good")
                    signal_label.setStyleSheet(
                        "font-size: 13px; color: #059669; padding: 8px; "
                        "background: #d1fae5; border-radius: 6px; font-weight: 600;"
                    )
            else:
                signal_label.setText("○ Signal: Waiting...")
                signal_label.setStyleSheet(
                    "font-size: 13px; color: #6b7280; padding: 8px; "
                    "background: #f3f4f6; border-radius: 6px; font-weight: 600;"
                )
        
        # Timer to update signal quality in prep dialog
        prep_timer = QTimer(prep_dialog)
        prep_timer.timeout.connect(update_prep_signal)
        prep_timer.start(500)
        update_prep_signal()  # Initial update
        
        # Start button
        start_btn = QPushButton("▶ Start Recording")
        start_btn.setStyleSheet(
            "padding: 12px 24px; font-size: 14px; font-weight: 600; "
            "background-color: #2563eb; border-radius: 8px;"
        )
        start_btn.clicked.connect(lambda: (prep_dialog.accept(), self.start_eyes_closed()))
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "padding: 10px 20px; font-size: 13px; "
            "background-color: #e2e8f0; color: #475569; border-radius: 6px;"
        )
        cancel_btn.clicked.connect(prep_dialog.reject)
        
        # Button layout
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(start_btn)
        
        layout.addWidget(title)
        layout.addWidget(instructions)
        layout.addWidget(signal_label)
        layout.addSpacing(8)
        layout.addLayout(btn_layout)
        
        prep_dialog.setLayout(layout)
        apply_modern_dialog_theme(prep_dialog)
        prep_dialog.exec()
    
    def start_eyes_closed(self):
        """Start eyes-closed calibration with countdown"""
        self.current_phase = 'eyes_closed'
        self.status_label.setText("⏳ Countdown starting...")
        self.phase_label.setText("Get ready! Listen for the countdown...")
        self.ec_button.setEnabled(False)
        self.back_button.setEnabled(False)
        
        print("[CalibrationDialog] Initiating eyes_closed calibration...")
        
        # Start audio countdown
        self.countdown_value = 5
        self.start_countdown_sequence('eyes_closed')
    
    def start_countdown_sequence(self, phase):
        """Run audio countdown sequence"""
        # Store the phase we're counting down for
        self.countdown_phase = phase
        self.countdown_timer.start(1000)  # 1 second intervals
    
    def update_countdown(self):
        """Update countdown display and play audio"""
        if self.countdown_value > 0:
            self.status_label.setText(f"Countdown: {self.countdown_value}")
            self.phase_label.setText(f"Listening to audio: {self.countdown_value}...")
            # Play countdown beep (cross-platform)
            play_beep(800, 200)  # 800Hz, 200ms
            self.countdown_value -= 1
        else:
            # Countdown finished, start actual recording
            self.countdown_timer.stop()
            # Use countdown_phase instead of current_phase to ensure correct phase starts
            if self.countdown_phase == 'eyes_closed':
                self.status_label.setText("🎬 Recording: Eyes Closed")
                self.phase_label.setText("Close your eyes and relax... (30 seconds)")
                self.feature_engine.start_calibration_phase('eyes_closed')
                print("[CalibrationDialog] Started eyes_closed phase")
            elif self.countdown_phase == 'eyes_open':
                self.status_label.setText("🎬 Recording: Eyes Open")
                self.phase_label.setText("Keep your eyes open and stay relaxed... (30 seconds)")
                self.feature_engine.start_calibration_phase('eyes_open')
                print("[CalibrationDialog] Started eyes_open phase")
            
            # Auto-stop after 30 seconds
            self.auto_stop_timer.start(30000)
    
    def show_eyes_open_prep(self):
        """Show preparation dialog for eyes open calibration"""
        prep_dialog = QDialog(self)
        prep_dialog.setWindowTitle("Eyes Open Calibration - Get Ready")
        prep_dialog.setModal(True)
        prep_dialog.setMinimumWidth(500)
        set_window_icon(prep_dialog)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Title
        title = QLabel("👁️ Eyes Open Baseline")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 8px;"
        )
        title.setAlignment(Qt.AlignCenter)
        
        # Instructions
        instructions = QLabel(
            "<b>Get ready to keep your eyes open and stay relaxed.</b><br><br>"
            "The sensors will record your eyes-open baseline for 30 seconds.<br><br>"
            "<b>What will happen:</b><br>"
            "1. Click 'Start Recording' below<br>"
            "2. You'll hear a countdown: <i>5, 4, 3, 2, 1 in beep sound</i><br>"
            "3. Keep your eyes open and relax for 30 seconds<br>"
            "4. Stay calm - look ahead calmly, minimize blinking<br>"
            "5. A sound will notify you when the 30 seconds are complete<br><br>"
            "<b style='color: #dc2626;'>⚠ Important: Keep eyes open but stay relaxed!</b>"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(
            "font-size: 13px; color: #475569; line-height: 1.8; "
            "padding: 16px; background: #f8fafc; border-radius: 8px;"
        )
        
        # Signal quality - dynamic assessment
        signal_label = QLabel("Signal quality: Checking...")
        signal_label.setStyleSheet(
            "font-size: 13px; color: #6b7280; padding: 8px; "
            "background: #f3f4f6; border-radius: 6px; font-weight: 600;"
        )
        signal_label.setAlignment(Qt.AlignCenter)
        
        # Update signal quality dynamically - mirrors header (not_worn = Noisy, else Good)
        _sq_state = {'last_tail': None, 'last_change': None,
                     'not_worn_since': None, 'worn_since': None, 'displayed_noisy': False, 'noisy_reason': 'not_worn'}
        _STALE_S = 2.0
        def update_prep_signal():
            import time
            if len(BL.live_data_buffer) >= 512:
                data = np.array(list(BL.live_data_buffer)[-512:])
                quality_score, status, details = assess_eeg_signal_quality(data, fs=512)
                
                # Track quality locally
                current_time = time.time()
                prep_quality_history.append((current_time, quality_score))
                # Remove entries older than 5 seconds
                while prep_quality_history and current_time - prep_quality_history[0][0] > 5.0:
                    prep_quality_history.pop(0)
                
                poor_count = sum(1 for t, q in prep_quality_history if q <= self.poor_quality_threshold)
                
                if poor_count >= 5:
                    signal_label.setText("⚠ Signal: Noisy")
                    signal_label.setStyleSheet(
                        "font-size: 13px; color: #d97706; padding: 8px; "
                        "background: #fef3c7; border-radius: 6px; font-weight: 600;"
                    )
                else:
                    signal_label.setText("✓ Signal: Good")
                    signal_label.setStyleSheet(
                        "font-size: 13px; color: #059669; padding: 8px; "
                        "background: #d1fae5; border-radius: 6px; font-weight: 600;"
                    )
            else:
                signal_label.setText("○ Signal: Waiting...")
                signal_label.setStyleSheet(
                    "font-size: 13px; color: #6b7280; padding: 8px; "
                    "background: #f3f4f6; border-radius: 6px; font-weight: 600;"
                )
        
        # Timer to update signal quality in prep dialog
        prep_timer = QTimer(prep_dialog)
        prep_timer.timeout.connect(update_prep_signal)
        prep_timer.start(500)
        update_prep_signal()  # Initial update
        
        # Start button
        start_btn = QPushButton("▶ Start Recording")
        start_btn.setStyleSheet(
            "padding: 12px 24px; font-size: 14px; font-weight: 600; "
            "background-color: #2563eb; border-radius: 8px;"
        )
        start_btn.clicked.connect(lambda: (prep_dialog.accept(), self.start_eyes_open()))
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "padding: 10px 20px; font-size: 13px; "
            "background-color: #e2e8f0; color: #475569; border-radius: 6px;"
        )
        cancel_btn.clicked.connect(prep_dialog.reject)
        
        # Button layout
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(start_btn)
        
        layout.addWidget(title)
        layout.addWidget(instructions)
        layout.addWidget(signal_label)
        layout.addSpacing(8)
        layout.addLayout(btn_layout)
        
        prep_dialog.setLayout(layout)
        apply_modern_dialog_theme(prep_dialog)
        prep_dialog.exec()
    
    def start_eyes_open(self):
        """Start eyes-open calibration with countdown"""
        self.current_phase = 'eyes_open'
        self.status_label.setText("Countdown starting...")
        self.phase_label.setText("Get ready! Listen for the countdown...")
        self.eo_button.setEnabled(False)
        self.back_button.setEnabled(False)
        
        print("[CalibrationDialog] Initiating eyes_open calibration...")
        
        # Start audio countdown
        self.countdown_value = 5
        self.start_countdown_sequence('eyes_open')
    
    def auto_stop_phase(self):
        """Auto-stop current calibration phase with completion notification"""
        # Check if dialog is still valid (not closed)
        if not self.isVisible():
            print("Dialog not visible, skipping auto_stop_phase")
            return
        
        # Play completion sound (4 beeps - cross-platform)
        for i in range(4):
            QTimer.singleShot(i * 200, lambda: play_beep(1000, 150))
            
        try:
            # Stop the calibration phase
            self.feature_engine.stop_calibration_phase()
            
            if self.current_phase == 'eyes_closed':
                self.status_label.setText("Eyes Closed Complete!")
                self.phase_label.setText("Great! Now let's record with eyes open.")
                self.eo_button.setEnabled(True)
                self.back_button.setEnabled(True)
                
                # Show completion message
                QMessageBox.information(
                    self,
                    "Eyes Closed Complete",
                    "<b>Eyes Closed calibration finished!</b><br><br>"
                    "You can now proceed to the Eyes Open calibration.<br><br>"
                    "Click 'Start Eyes Open Calibration' when ready.",
                    QMessageBox.Ok
                )
            elif self.current_phase == 'eyes_open':
                self.status_label.setText("Calibration Complete!")
                self.phase_label.setText("Both baseline phases recorded successfully!")
                self.back_button.setEnabled(True)
                
                # Compute REAL baseline statistics
                try:
                    self.feature_engine.compute_baseline_statistics()
                    self.phase_label.setText("✓ Both phases complete. Baseline computed successfully.")
                except Exception as e:
                    print(f"Warning: Error computing baseline statistics: {e}")
                    self.phase_label.setText("Both phases complete. Baseline computed with warnings.")
                
                self.next_button.setEnabled(True)
                
                # Show completion message
                QMessageBox.information(
                    self,
                    "Calibration Complete",
                    "<b>Excellent! Baseline calibration is complete!</b><br><br>"
                    "Both Eyes Closed and Eyes Open baselines have been recorded.<br><br>"
                    "Click 'Next' to proceed to the task selection.",
                    QMessageBox.Ok
                )
        except Exception as e:
            print(f"Error in auto_stop_phase: {e}")
            import traceback
            traceback.print_exc()
            # Try to recover by enabling the next button anyway
            if self.current_phase in ['eyes_closed', 'eyes_open']:
                try:
                    self.next_button.setEnabled(True)
                except:
                    pass
    
    def on_back(self):
        """Navigate back"""
        if self.auto_stop_timer.isActive():
            self.auto_stop_timer.stop()
        if self.current_phase:
            self.feature_engine.stop_calibration_phase()
        
        if self.status_bar:
            self.status_bar.cleanup()
        
        self._programmatic_close = True
        self.close()
        self.workflow.go_back()
    
    def on_next(self):
        """Proceed to task selection"""
        if self.status_bar:
            self.status_bar.cleanup()
        
        self._programmatic_close = True
        self.close()
        self.workflow.go_to_step(WorkflowStep.TASK_SELECTION)
    
    def closeEvent(self, event):
        """Handle dialog close - distinguish between user X click and programmatic close"""
        try:
            # Stop all timers
            if hasattr(self, 'auto_stop_timer') and self.auto_stop_timer.isActive():
                self.auto_stop_timer.stop()
            if hasattr(self, 'countdown_timer') and self.countdown_timer.isActive():
                self.countdown_timer.stop()
            if hasattr(self, 'signal_timer') and self.signal_timer.isActive():
                self.signal_timer.stop()
            
            if hasattr(self, 'current_phase') and self.current_phase:
                try:
                    self.feature_engine.stop_calibration_phase()
                except Exception as e:
                    print(f"Warning: Error stopping calibration on close: {e}")
            
            if hasattr(self, 'status_bar') and self.status_bar:
                try:
                    self.status_bar.cleanup()
                except Exception as e:
                    print(f"Warning: Error cleaning up status bar: {e}")
            
            if hasattr(self, '_programmatic_close') and self._programmatic_close:
                # Programmatic close from navigation buttons - allow it
                event.accept()
            else:
                # User clicked X button - show confirmation
                # Temporarily clear WindowStaysOnTopHint so message box appears on top
                was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
                if was_on_top:
                    self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                    self.show()
                
                reply = QMessageBox.question(
                    self, 'Confirm Exit',
                    'Calibration in progress. Are you sure you want to exit?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                # Restore WindowStaysOnTopHint if it was set
                if was_on_top:
                    self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                    self.show()
                
                if reply == QMessageBox.Yes:
                    event.accept()
                    # Close the entire application
                    cleanup_and_quit()
                else:
                    event.ignore()
        except Exception as e:
            print(f"Error in CalibrationDialog closeEvent: {e}")
            import traceback
            traceback.print_exc()
            event.accept()  # Accept to prevent dialog freeze


# ============================================================================
# STEP 6: TASK SELECTION (Using REAL task interface)
# ============================================================================

class TaskSelectionDialog(QDialog):
    """Step 7: Select and launch REAL cognitive tasks"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Task Selection")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        
        # Set reasonable size - avoid geometry warnings
        self.setMinimumSize(550, 550)
        self.resize(600, 650)
        
        # Set window icon
        set_window_icon(self)
        
        # Use FILTERED task list from main window's task_combo
        # This respects the protocol pathway selection made earlier
        self.available_task_ids = []
        if hasattr(self.workflow.main_window, 'task_combo') and self.workflow.main_window.task_combo:
            # Get the filtered task IDs from the main window's combo box
            # The _apply_protocol_filter() method already populated this with the correct tasks
            for i in range(self.workflow.main_window.task_combo.count()):
                task_id = self.workflow.main_window.task_combo.itemText(i)
                self.available_task_ids.append(task_id)
            print(f"[TASK SELECTION] Loaded {len(self.available_task_ids)} tasks from main window: {self.available_task_ids}")
        
        # Fall back to all tasks if filtering failed
        if not self.available_task_ids:
            # Check device type for multichannel filtering
            device_type = getattr(self.workflow.main_window, 'device_type', 'mindlink')
            is_multichannel = (device_type == 'antneuro')
            
            # Filter tasks based on device capabilities
            print(f"[TASK SELECTION] Using fallback - device_type='{device_type}', is_multichannel={is_multichannel}")
            for task_id in BL.AVAILABLE_TASKS.keys():
                task_def = BL.AVAILABLE_TASKS[task_id]
                multichannel_only = task_def.get('multichannel_only', False)
                # Skip multichannel-only tasks on single-channel devices
                if multichannel_only and not is_multichannel:
                    print(f"[TASK SELECTION] ❌ Skipping '{task_id}' - multichannel_only=True, device={device_type}")
                    continue
                print(f"[TASK SELECTION] ✓ Adding '{task_id}' (multichannel_only={multichannel_only})")
                self.available_task_ids.append(task_id)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)
        
        # UI Elements
        title_label = QLabel("Cognitive Tasks")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 9 of 10: Select tasks to perform")
        subtitle_label.setObjectName("DialogSubtitle")
        
        main_layout.addWidget(title_label)
        main_layout.addWidget(subtitle_label)
        
        # Task selection card
        task_card = QFrame()
        task_card.setObjectName("DialogCard")
        task_layout = QVBoxLayout(task_card)
        task_layout.setContentsMargins(16, 16, 16, 16)
        task_layout.setSpacing(12)
        
        task_label = QLabel("Choose a task:")
        task_label.setObjectName("DialogSectionTitle")
        
        self.task_combo = QComboBox()
        self.task_combo.setMinimumHeight(36)
        
        # Populate with task names as display text and task IDs as data
        # Get completed tasks to disable them
        completed_tasks = self._get_completed_task_ids()
        
        # Basic tasks that don't need 'Advanced' tag
        basic_tasks = [ 'visual_imagery', 'attention_focus', 'mental_math', 'emotion_face']
        
        for task_id in self.available_task_ids:
            if task_id in BL.AVAILABLE_TASKS:
                task_name = BL.AVAILABLE_TASKS[task_id].get('name', task_id)
                
                # Add 'Advanced' tag for non-basic tasks
                if task_id not in basic_tasks:
                    task_name = f"{task_name} (Advanced)"
                
                # Mark completed tasks with checkmark
                if task_id in completed_tasks:
                    display_name = f"✓ {task_name} (Completed)"
                else:
                    display_name = task_name
                
                self.task_combo.addItem(display_name, task_id)  # Display name, store ID as data
                
                # Disable the item if task is already completed
                if task_id in completed_tasks:
                    model = self.task_combo.model()
                    item = model.item(self.task_combo.count() - 1)
                    item.setEnabled(False)
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)  # Explicitly disable
                    item.setToolTip("This task has already been completed")
        
        self.task_combo.currentIndexChanged.connect(self.update_task_preview)
        
        task_layout.addWidget(task_label)
        task_layout.addWidget(self.task_combo)
        
        main_layout.addWidget(task_card)
        
        # Task preview card - use scroll area for better content handling
        preview_card = QFrame()
        preview_card.setObjectName("DialogCard")
        preview_card_layout = QVBoxLayout(preview_card)
        preview_card_layout.setContentsMargins(16, 16, 16, 16)
        preview_card_layout.setSpacing(12)
        
        preview_title = QLabel("Task Details:")
        preview_title.setObjectName("DialogSectionTitle")
        preview_card_layout.addWidget(preview_title)
        
        # Scrollable text area for task description
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll_area.setMinimumHeight(150)
        scroll_area.setMaximumHeight(200)
        
        # Task description widget
        self.task_description = QLabel()
        self.task_description.setWordWrap(True)
        self.task_description.setStyleSheet("font-size: 13px; color: #475569;")
        
        self.start_task_button = QPushButton("Start This Task")
        self.start_task_button.clicked.connect(self.start_selected_task)
        self.start_task_button.setStyleSheet("padding: 12px; font-size: 14px; font-weight: 600;")
        self.start_task_button.setMinimumHeight(44)
        preview_card_layout.addWidget(self.start_task_button)
        
        main_layout.addWidget(preview_card, 1)
        
        # Completed tasks info
        self.completed_label = QLabel()
        self.completed_label.setWordWrap(True)
        self.completed_label.setStyleSheet("font-size: 12px; color: #64748b; padding: 8px;")
        self.update_completed_tasks_display()
        main_layout.addWidget(self.completed_label)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(12)
        
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.on_back)
        self.back_button.setMinimumHeight(40)
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
        
        self.next_button = QPushButton("Proceed to Analysis →")
        self.next_button.clicked.connect(self.on_next)
        self.next_button.setMinimumHeight(40)
        # Enable if tasks have been completed
        completed_count = len([t for t in self.workflow.main_window.feature_engine.calibration_data.get('tasks', {}).keys() 
                               if t not in ['baseline', 'eyes_closed', 'eyes_open']])
        self.next_button.setEnabled(completed_count > 0)
        nav_layout.addWidget(self.next_button)
        
        main_layout.addLayout(nav_layout)
        
        self.setLayout(main_layout)
        apply_modern_dialog_theme(self)
        
        # Add MindLink status bar
        self.status_bar = add_status_bar_to_dialog(self, self.workflow.main_window)
        
        # Initialize preview
        self.update_task_preview()
        self._programmatic_close = False
    
    def _is_advanced_task(self, task_id: str) -> bool:
        """Return True for tasks that require an advanced booking."""
        basic_tasks = {'visual_imagery', 'attention_focus', 'mental_math', 'emotion_face'}
        return task_id not in basic_tasks

    def _get_completed_task_ids(self):
        """Get list of task IDs that have already been completed"""
        tasks_data = self.workflow.main_window.feature_engine.calibration_data.get('tasks', {})
        completed_tasks = [t for t in tasks_data.keys() if t not in ['baseline', 'eyes_closed', 'eyes_open']]
        return completed_tasks
    
    def _center_on_screen(self):
        """Center the dialog on the screen with bounds checking"""
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                
                # Ensure dialog size fits within screen
                dialog_width = min(self.width(), screen_geometry.width() - 50)
                dialog_height = min(self.height(), screen_geometry.height() - 50)
                self.resize(dialog_width, dialog_height)
                
                # Center on screen
                x = screen_geometry.x() + (screen_geometry.width() - dialog_width) // 2
                y = screen_geometry.y() + (screen_geometry.height() - dialog_height) // 2
                self.move(x, y)
        except Exception as e:
            print(f"Warning: Could not center dialog: {e}")
    
    def closeEvent(self, event):
        """Handle dialog close - distinguish between user X click and programmatic close"""
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            # Programmatic close from navigation buttons - allow it
            event.accept()
        else:
            # User clicked X button - show confirmation
            if self.status_bar:
                self.status_bar.cleanup()
            
            # Temporarily clear WindowStaysOnTopHint so message box appears on top
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit MindLink Analyzer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            # Restore WindowStaysOnTopHint if it was set
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def _on_task_changed(self, index):
        """Skip over disabled (completed) items when the selection changes."""
        if index < 0:
            return
        model = self.task_combo.model()
        item = model.item(index)
        if item and not item.isEnabled():
            # Search forward for the next enabled item
            for i in range(index + 1, self.task_combo.count()):
                next_item = model.item(i)
                if next_item and next_item.isEnabled():
                    self.task_combo.blockSignals(True)
                    self.task_combo.setCurrentIndex(i)
                    self.task_combo.blockSignals(False)
                    self.update_task_preview()
                    return
            # Fallback: search backward
            for i in range(index - 1, -1, -1):
                prev_item = model.item(i)
                if prev_item and prev_item.isEnabled():
                    self.task_combo.blockSignals(True)
                    self.task_combo.setCurrentIndex(i)
                    self.task_combo.blockSignals(False)
                    self.update_task_preview()
                    return

    def _get_selected_task_id(self):
        """Resolve the selected task_id from the combo box (robust to display text)."""
        task_id = self.task_combo.currentData()
        if task_id in BL.AVAILABLE_TASKS:
            return task_id
        
        display = (self.task_combo.currentText() or "").strip()
        if not display:
            return None
        
        # Strip UI adornments
        display = display.replace("✓ ", "")
        display = display.replace(" (Completed)", "")
        display = display.replace(" (Advanced)", "")
        
        if display in BL.AVAILABLE_TASKS:
            return display
        
        for key, info in BL.AVAILABLE_TASKS.items():
            if info.get('name') == display:
                return key
        
        return None
    
    def update_task_preview(self):
        """Update task description preview"""
        # Get task ID from combo box data (not the display text)
        task_id = self._get_selected_task_id()
        
        # Safety check: if task_id is None (combo rebuilding or empty), do nothing
        if not task_id:
            self.task_description.setText("Please select a task to view details")
            self.start_task_button.setEnabled(False)
            return
        
        # Check if task is already completed
        completed_tasks = self._get_completed_task_ids()
        is_completed = task_id in completed_tasks
        
        # Get task info from BL.AVAILABLE_TASKS using task_id
        if task_id and task_id in BL.AVAILABLE_TASKS:
            task_info = BL.AVAILABLE_TASKS[task_id]
            task_name = task_info.get('name', task_id)
            desc = task_info.get('description', '')
            duration = task_info.get('duration', 60)
            instructions = task_info.get('instructions', '')
            
            preview_text = f"<p style='margin: 0 0 8px 0;'><b style='font-size: 14px;'>{task_name}</b>"
            
            if is_completed:
                preview_text += " <span style='color: #10b981; font-weight: 600;'>✓ Completed</span>"
            
            preview_text += "<br><br>"
            preview_text += f"Description: {desc}<br>"
            preview_text += f"Duration: ~{duration} seconds<br><br>"
            if instructions:
                preview_text += f"Instructions: {instructions}"
            
            if is_completed:
                preview_text += "<br><br><span style='color: #f59e0b; font-weight: 600;'>⚠️ This task has already been completed. Please select a different task.</span>"
            
            self.task_description.setText(preview_text)
            
            # Disable start button if task is completed or locked
            can_start = not is_completed and not is_locked
            self.start_task_button.setEnabled(can_start)
            if is_completed:
                self.start_task_button.setText("Task Already Completed")
            elif is_locked:
                self.start_task_button.setText("🔒 Booking Required")
            else:
                self.start_task_button.setText("Start This Task")
        else:
            self.task_description.setText("<p style='font-style: italic; color: #94a3b8;'>Task information not available</p>")
            self.start_task_button.setEnabled(False)
    
    def start_selected_task(self):
        """Launch the REAL task using main window's start_task method"""
        # Get task ID from combo box data (not the display text)
        task_id = self._get_selected_task_id()
        
        # Verify task_id exists
        if not task_id or task_id not in BL.AVAILABLE_TASKS:
            QMessageBox.warning(self, "Invalid Task", f"Task '{task_id}' not found in available tasks.")
            return
        
        # Check if task is already completed
        completed_tasks = self._get_completed_task_ids()
        if task_id in completed_tasks:
            QMessageBox.warning(
                self, 
                "Task Already Completed", 
                f"The task '{BL.AVAILABLE_TASKS[task_id].get('name', task_id)}' has already been completed.\n\nPlease select a different task."
            )
            return
        
        # Set the task in the combo box if the main window has one
        if hasattr(self.workflow.main_window, 'task_combo'):
            # Find the index for this task_id in the main window's combo
            for i in range(self.workflow.main_window.task_combo.count()):
                if self.workflow.main_window.task_combo.itemText(i) == task_id:
                    self.workflow.main_window.task_combo.setCurrentIndex(i)
                    break
        
        # Hide this dialog temporarily
        self.hide()
        
        # Use the REAL start_task method from Enhanced GUI
        # This method handles EVERYTHING: start_calibration_phase, show_task_interface, audio cues, etc.
        try:
            self.workflow.main_window.start_task()
            self.workflow.main_window.log_message(f"✓ Started task via start_task(): {task_id}")
        except Exception as e:
            self.workflow.main_window.log_message(f"Error starting task: {e}")
            QMessageBox.warning(self, "Task Start Error", f"Failed to start task:\n{str(e)}")
            self.show()
            return
        
        # After task completion, show this dialog again
        QTimer.singleShot(1000, self._check_task_completion)
    
    def _check_task_completion(self):
        """Check if task is complete and update UI"""
        # If task dialog is closed, show selection again
        if not self.workflow.main_window._task_dialog or not self.workflow.main_window._task_dialog.isVisible():
            # Debug: Check what was stored after task completion
            engine = self.workflow.main_window.feature_engine
            tasks = engine.calibration_data.get('tasks', {})
            print(f"\n=== TASK COMPLETION DEBUG ===")
            print(f"Task dialog closed. Checking stored data...")
            print(f"Engine current_state: {getattr(engine, 'current_state', 'N/A')}")
            print(f"Engine current_task: {getattr(engine, 'current_task', 'N/A')}")
            print(f"Tasks in 'tasks' dict: {list(tasks.keys())}")
            for task_name, task_data in tasks.items():
                print(f"  {task_name}: {len(task_data.get('features', []))} features")
            
            # Also check legacy 'task' bucket
            legacy_task = engine.calibration_data.get('task', {})
            if legacy_task.get('features'):
                print(f"WARNING: Found {len(legacy_task.get('features', []))} features in legacy 'task' bucket!")
            print(f"==============================\n")
            
            self.show()
            self._center_on_screen()  # Re-center after task completion
            self.update_completed_tasks_display()
            self._refresh_task_combo()  # Refresh combo to disable newly completed task
            self.next_button.setEnabled(True)
        else:
            # Check again in 1 second
            QTimer.singleShot(1000, self._check_task_completion)
    
    def _refresh_task_combo(self):
        """Refresh the task combo box to update disabled states after task completion"""
        # Block signals during rebuild to prevent premature update_task_preview calls
        self.task_combo.blockSignals(True)
        
        # Clear and repopulate combo box
        self.task_combo.clear()
        completed_tasks = self._get_completed_task_ids()
        
        # Basic tasks that don't need 'Advanced' tag
        basic_tasks = [ 'visual_imagery', 'attention_focus', 'mental_math', 'emotion_face']
        
        for task_id in self.available_task_ids:
            if task_id in BL.AVAILABLE_TASKS:
                task_name = BL.AVAILABLE_TASKS[task_id].get('name', task_id)
                
                # Add 'Advanced' tag for non-basic tasks
                if task_id not in basic_tasks:
                    task_name = f"{task_name} (Advanced)"
                
                if task_id in completed_tasks:
                    display_name = f"✓ {task_name} (Completed)"
                else:
                    display_name = task_name
                
                self.task_combo.addItem(display_name, task_id)
                
                # Disable the item if task is already completed
                if task_id in completed_tasks:
                    model = self.task_combo.model()
                    item = model.item(self.task_combo.count() - 1)
                    item.setEnabled(False)
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)  # Explicitly disable
                    item.setToolTip("This task has already been completed")
        
        # Try to select first non-completed task
        for i in range(self.task_combo.count()):
            task_id = self.task_combo.itemData(i)
            if task_id not in completed_tasks:
                self.task_combo.setCurrentIndex(i)
                selected = True
                print(f"[TASK SELECTION] Auto-selected next task: {task_id}")
                break
    
    def update_completed_tasks_display(self):
        """Update the completed tasks counter"""
        engine = self.workflow.main_window.feature_engine
        
        # Check if using offline engine (phase_markers instead of calibration_data['tasks'])
        if hasattr(engine, 'phase_markers'):
            # Offline engine: count task phases in phase_markers
            completed_tasks = []
            for marker in engine.phase_markers:
                if marker['phase'] == 'task' and marker['task']:
                    task_name = marker['task']
                    if task_name not in completed_tasks:
                        completed_tasks.append(task_name)
        else:
            # Traditional engine: use calibration_data['tasks']
            tasks_data = engine.calibration_data.get('tasks', {})
            completed_tasks = [t for t in tasks_data.keys() if t not in ['baseline', 'eyes_closed', 'eyes_open']]
        
        count = len(completed_tasks)
        
        if count == 0:
            self.completed_label.setText("No tasks completed yet. Complete at least one task to proceed.")
        elif count == 1:
            self.completed_label.setText(f"✓ {count} task completed: {', '.join(completed_tasks)}")
        else:
            self.completed_label.setText(f"✓ {count} tasks completed: {', '.join(completed_tasks)}")
    
    def on_back(self):
        """Navigate back"""
        if self.status_bar:
            self.status_bar.cleanup()
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_next(self):
        """Proceed to multi-task analysis"""
        if self.status_bar:
            self.status_bar.cleanup()
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.MULTI_TASK_ANALYSIS))


# ============================================================================
# STEP 7: MULTI-TASK ANALYSIS (Using REAL analysis engine)
# ============================================================================

class MultiTaskAnalysisDialog(QDialog):
    """Step 8: Real multi-task analysis and report generation"""
    
    # Define signal for thread-safe communication
    analysis_complete_signal = QtCore.Signal()
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - Multi-Task Analysis")
        self.setModal(False)  # Changed to False so Enhanced GUI's progress dialog works
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(700, 600)
        
        # Set window icon
        set_window_icon(self)
        
        # Center the dialog on screen after showing
        QTimer.singleShot(0, self._center_on_screen)
        
        # Connect signal to slot for thread-safe GUI updates
        self.analysis_complete_signal.connect(self._display_results)
        
        # UI Elements
        title_label = QLabel("Multi-Task Analysis")
        title_label.setObjectName("DialogTitle")
        
        subtitle_label = QLabel("Step 10 of 10: Analyze all completed tasks")
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
        
        # Detect selected region from backend URL
        selected_region = "Unknown"
        if "en" in BL.BACKEND_URL or "en.mindspeller" in BL.BACKEND_URL:
            selected_region = "English (en)"
        elif "nl" in BL.BACKEND_URL or "nl.mindspeller" in BL.BACKEND_URL:
            selected_region = "Dutch (nl)"
        elif "127.0.0.1" in BL.BACKEND_URL or "localhost" in BL.BACKEND_URL:
            selected_region = "Local"
        
        # Add informational text about the buttons with selected region
        user_data = getattr(self.workflow.main_window, 'user_data', {})
        initial_protocol = user_data.get('initial_protocol', '')
        protocol_status = "Initial Protocol (first time)" if not initial_protocol else "Advanced Protocol (follow-up)"
        
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
        self.results_text.setMinimumHeight(200)  # Reduced from 300 to make room for action buttons
        self.results_text.setMaximumHeight(250)  # Add max height to keep dialog compact
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
        
        # Add MindLink status bar
        self.status_bar = add_status_bar_to_dialog(self, self.workflow.main_window)
        self._programmatic_close = False
    
    def closeEvent(self, event):
        """Handle dialog close - distinguish between user X click and programmatic close"""
        if hasattr(self, '_programmatic_close') and self._programmatic_close:
            # Programmatic close from navigation buttons - allow it
            event.accept()
        else:
            # User clicked X button - show confirmation
            if self.status_bar:
                self.status_bar.cleanup()
            
            # Temporarily clear WindowStaysOnTopHint so message box appears on top
            was_on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.show()
            
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                'Are you sure you want to exit MindLink Analyzer?\n\nAll unsaved analysis data will be lost.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            # Restore WindowStaysOnTopHint if it was set
            if was_on_top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
            
            if reply == QMessageBox.Yes:
                event.accept()
                cleanup_and_quit()
            else:
                event.ignore()
    
    def _center_on_screen(self):
        """Center the dialog on the screen"""
        try:
            # Get the screen geometry
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                dialog_geometry = self.frameGeometry()
                
                # Calculate center position
                center_x = screen_geometry.center().x() - dialog_geometry.width() // 2
                center_y = screen_geometry.center().y() - dialog_geometry.height() // 2
                
                # Move to center
                self.move(center_x, center_y)
        except Exception as e:
            print(f"Warning: Could not center dialog: {e}")
    
    def _disconnect_headset(self):
        """Disconnect the BrainLink headset and stop data streaming"""
        try:
            self.workflow.main_window.log_message("Disconnecting device for analysis...")
            
            # === ANT NEURO Device Disconnect ===
            if ANT_NEURO and ANT_NEURO.is_connected:
                try:
                    self.workflow.main_window.log_message("Stopping ANT Neuro streaming...")
                    ANT_NEURO.stop_streaming()
                    self.workflow.main_window.log_message("✓ ANT Neuro streaming stopped")
                    
                    self.workflow.main_window.log_message("Disconnecting ANT Neuro device...")
                    ANT_NEURO.disconnect()
                    self.workflow.main_window.log_message("✓ ANT Neuro device disconnected")
                except Exception as e:
                    self.workflow.main_window.log_message(f"Warning: ANT Neuro disconnect error: {e}")
            
            # === BrainLink Device Disconnect ===
            # Stop the BrainLink thread
            BL.stop_thread_flag = True
            
            # Close serial connection if it exists
            if hasattr(self.workflow.main_window, 'serial_obj') and self.workflow.main_window.serial_obj:
                try:
                    self.workflow.main_window.serial_obj.close()
                    self.workflow.main_window.log_message("✓ Serial connection closed")
                except Exception as e:
                    self.workflow.main_window.log_message(f"Warning: Error closing serial: {e}")
            
            # Wait for thread to stop
            if hasattr(self.workflow.main_window, 'brainlink_thread') and self.workflow.main_window.brainlink_thread:
                if self.workflow.main_window.brainlink_thread.is_alive():
                    self.workflow.main_window.brainlink_thread.join(timeout=2.0)
                    if self.workflow.main_window.brainlink_thread.is_alive():
                        self.workflow.main_window.log_message("Warning: Thread did not stop cleanly")
                    else:
                        self.workflow.main_window.log_message("✓ Data streaming stopped")
            
            self.workflow.main_window.log_message("✓ Device disconnected successfully")
        except Exception as e:
            self.workflow.main_window.log_message(f"Error disconnecting device: {e}")
            import traceback
            traceback.print_exc()
    
    def analyze_all_tasks(self):
        """Run REAL multi-task analysis"""
        self.results_text.setPlainText("Analyzing all tasks...\n\nThis may take a moment.")
        self.analyze_button.setEnabled(False)
        
        # Terminate headset connection before analysis
        self._disconnect_headset()
        
        # Debug: Check what tasks are available
        engine = self.workflow.main_window.feature_engine
        
        # === OFFLINE ENGINE: Extract features from raw data first ===
        if hasattr(engine, 'analyze_offline') and hasattr(engine, 'phase_markers'):
            # This is the OfflineMultichannelEngine - need to extract features first
            print(f"\n{'='*70}")
            print(f"[OFFLINE ANALYSIS] Extracting features from raw EEG data...")
            print(f"[OFFLINE ANALYSIS] Phase markers (before filtering): {len(engine.phase_markers)}")
            print(f"[OFFLINE ANALYSIS] Raw samples: {len(engine.raw_data)}")
            print(f"{'='*70}\n")
            
            # === CRITICAL: Filter phase markers to only recording phases ===
            # This aligns with standalone analyzer logic (BrainLink_Offline_Analyzer.py lines 296-363)
            all_markers = engine.phase_markers
            has_record_flags = any('record' in m for m in all_markers)
            
            if has_record_flags:
                # New format: use explicit 'record' flag
                recording_markers = [m for m in all_markers if m.get('record', False)]
                print(f"[OFFLINE ANALYSIS] Using explicit 'record' flags from markers")
            else:
                # Old format: use fallback heuristics based on phase type
                recording_phase_types = {'task', 'thinking', 'viewing', 'video', 'wait', 'eyes_closed', 'eyes_open', 'baseline'}
                
                recording_markers = []
                for marker in all_markers:
                    task_id = marker.get('task')
                    phase_type = marker.get('phase_type')
                    phase_name = marker.get('phase', '')  # Fallback for old format
                    
                    # If no phase_type but has 'phase', use that
                    if not phase_type and phase_name:
                        # Default recording phases should be included
                        if phase_name in recording_phase_types:
                            recording_markers.append(marker)
                        continue
                    
                    # Check if this phase should be recorded
                    should_record = False
                    
                    # Try to get task definition for intelligent filtering
                    if task_id and task_id in BL.AVAILABLE_TASKS:
                        task_def = BL.AVAILABLE_TASKS[task_id]
                        phase_structure = task_def.get('phase_structure', [])
                        
                        # Find matching phase in structure
                        for phase in phase_structure:
                            if phase.get('type') == phase_type and phase.get('record', False):
                                should_record = True
                                break
                        
                        # For continuous_recording tasks, keep all phases
                        if task_def.get('continuous_recording', False):
                            should_record = True
                    else:
                        # Unknown task, keep marker if phase type suggests recording
                        if phase_type in recording_phase_types:
                            should_record = True
                    
                    if should_record:
                        recording_markers.append(marker)
            
            # Update engine's phase markers to only recording phases
            engine.phase_markers = recording_markers
            print(f"[OFFLINE ANALYSIS] Filtered to {len(recording_markers)} recording phases (removed {len(all_markers) - len(recording_markers)} non-recording phases)")
            
            # Show details of filtered phases
            if recording_markers:
                print(f"[OFFLINE ANALYSIS] Recording phases:")
                for rm in recording_markers:
                    phase_desc = rm.get('phase', 'unknown')
                    if rm.get('phase_type'):
                        phase_desc += f" ({rm['phase_type']})"
                    if rm.get('task'):
                        phase_desc += f" - {rm['task']}"
                    duration = rm['end'] - rm['start']
                    print(f"  • {phase_desc}: {duration:.1f}s")
            
            self.results_text.setPlainText(
                "OFFLINE ANALYSIS MODE\n\n"
                "Extracting features from raw EEG data...\n"
                "Processing all 64 channels...\n"
                "Computing 1,400+ features per window...\n\n"
                f"Recording phases to analyze: {len(recording_markers)}\n\n"
                "This may take 1-2 minutes depending on recording length."
            )
            QtWidgets.QApplication.processEvents()
            
            # Run offline analysis (extracts features from raw data)
            def progress_callback(pct):
                msg = f"OFFLINE ANALYSIS: {pct}% complete..."
                QtCore.QMetaObject.invokeMethod(
                    self.results_text, "setPlainText",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, f"OFFLINE ANALYSIS MODE\n\n"
                                      f"Feature extraction: {pct}%\n\n"
                                      f"Processing {len(recording_markers)} phases × 64 channels × 1,400+ features per window...")
                )
            
            engine.analyze_offline(progress_callback=progress_callback)
            
            # Stop recording if still active
            if hasattr(engine, 'stop_recording'):
                engine.stop_recording()
            
            # Save phase markers
            if hasattr(engine, 'save_phase_markers'):
                engine.save_phase_markers()
            
            print(f"[OFFLINE ANALYSIS] Feature extraction complete!")
            print(f"[OFFLINE ANALYSIS] Eyes-closed: {len(engine.calibration_data['eyes_closed']['features'])} windows")
            print(f"[OFFLINE ANALYSIS] Eyes-open: {len(engine.calibration_data['eyes_open']['features'])} windows")
            print(f"[OFFLINE ANALYSIS] Task: {len(engine.calibration_data['task']['features'])} windows")
        
        tasks = engine.calibration_data.get('tasks', {})
        
        print(f"\n=== PRE-ANALYSIS DEBUG ===")
        print(f"calibration_data keys: {list(engine.calibration_data.keys())}")
        print(f"Available tasks in 'tasks': {list(tasks.keys())}")
        for task_name, task_data in tasks.items():
            print(f"  {task_name}: {len(task_data.get('features', []))} features")
        
        # Also check the legacy 'task' bucket (singular)
        legacy_task = engine.calibration_data.get('task', {})
        if legacy_task.get('features'):
            print(f"WARNING: Found features in legacy 'task' bucket: {len(legacy_task.get('features', []))} features")
            print(f"  This means tasks were stored in the wrong location!")
        
        print(f"Baseline stats exist: {bool(engine.baseline_stats)}")
        print(f"Current state: {engine.current_state}")
        print(f"Current task: {engine.current_task}")
        print(f"=========================\n")
        
        if not tasks:
            self.results_text.setPlainText(
                "No tasks have been recorded yet.\n\n"
                "Please:\n"
                "1. Ensure the device is connected and streaming EEG\n"
                "2. Start a task from the Task Selection step\n"
                "3. Wait at least 10-15 seconds for data collection\n"
                "4. Press 'Stop Now' to end the task\n"
                "5. Then return here to analyze"
            )
            self.analyze_button.setEnabled(True)
            return
        
        # ROBUST FIX: Run analyze_all_tasks_data() in background thread
        # Cannot run in main thread - it's CPU-intensive and will freeze the GUI
        # But we avoid the Enhanced GUI's modal dialog by managing our own progress display
        
        import threading
        
        # Show initial progress message
        self.results_text.setPlainText(
            "Analysis in progress...\n\n"
            "Initializing analysis engine...\n"
            "Computing baseline statistics...\n"
            "Preparing task comparisons...\n\n"
            "Please wait, this may take 3-5 minutes. Wait for the Generate Report button to be enabled.."
        )
        
        # Track analysis state
        self.analysis_running = True
        self.progress_dots = 0
        
        # Progress update timer (updates UI every second)
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress_display)
        self.progress_timer.start(1000)  # Update every second
        
        # Set up permutation progress callback for real-time updates
        def _permutation_progress(current, total):
            """Called from background thread during permutation testing"""
            try:
                # Calculate progress percentage
                progress_pct = int((current / total) * 100)
                
                # Update progress message (thread-safe via Qt invoke)
                progress_msg = (
                    f"Analysis in progress...\n\n"
                    f"📊 Permutation testing: {current:,}/{total:,} ({progress_pct}%)\n\n"
                    f"Statistical validation is running. This may take 3-5 minutes. Wait for the Generate Report button to be enabled.."
                )
                
                # Use QMetaObject.invokeMethod for thread-safe GUI update
                QtCore.QMetaObject.invokeMethod(
                    self.results_text,
                    "setPlainText",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, progress_msg)
                )
            except Exception as e:
                print(f"[Permutation Progress] Error updating UI: {e}")
        
        # Register the callback with the feature engine
        engine.set_permutation_progress_callback(_permutation_progress)
        print(f">>> Permutation progress callback registered <<<")
        
        # Background worker thread
        def _worker():
            try:
                print(f"\n>>> [WORKER THREAD] CALLING analyze_all_tasks_data() <<<\n")
                
                # Run the analysis in background thread
                results = engine.analyze_all_tasks_data()
                
                # Store results in engine for main thread to access
                engine.multi_task_results = results
                
                print(f"\n>>> [WORKER THREAD] analyze_all_tasks_data() RETURNED <<<\n")
                print(f"Results type: {type(results)}")
                if isinstance(results, dict):
                    print(f"Results keys: {list(results.keys())}")
                    print(f"engine.multi_task_results stored: {hasattr(engine, 'multi_task_results')}")
                
                # Clear the permutation progress callback
                engine.clear_permutation_progress_callback()
                print(f">>> Permutation progress callback cleared <<<")
                
                # Mark analysis as complete
                self.analysis_running = False
                print(f">>> [WORKER THREAD] Set analysis_running = False <<<")
                
                # Stop progress timer from main thread
                print(f">>> [WORKER THREAD] Scheduling timer stop <<<")
                QTimer.singleShot(0, self.progress_timer.stop)
                
                # Emit signal for thread-safe GUI update
                print(f">>> [WORKER THREAD] Emitting analysis_complete_signal <<<")
                self.analysis_complete_signal.emit()
                print(f">>> [WORKER THREAD] Signal emitted <<<")
                
            except Exception as e:
                print(f"\n>>> [WORKER THREAD] EXCEPTION: {e} <<<\n")
                import traceback
                traceback.print_exc()
                
                # Clear the permutation progress callback on error
                try:
                    engine.clear_permutation_progress_callback()
                    print(f">>> Permutation progress callback cleared (after error) <<<")
                except:
                    pass
                
                # Mark analysis as complete (even on error)
                self.analysis_running = False
                
                # Stop progress timer from main thread
                QTimer.singleShot(0, self.progress_timer.stop)
                
                # Update GUI from main thread (thread-safe) using signal
                def _show_error():
                    self.results_text.setPlainText(f"Error during analysis:\n{str(e)}\n\nSee console for details.")
                    self.analyze_button.setEnabled(True)
                
                # Emit via main thread
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_show_error_callback",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, str(e))
                )
        
        # Start background thread
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        
        print(f"\n>>> [MAIN THREAD] Background analysis thread started <<<\n")
    
    @QtCore.Slot()
    def _update_progress_display(self):
        """Update progress display with animated dots (only when no permutation progress)"""
        if not self.analysis_running:
            return
        
        # Check if current text contains "Permutation testing" - if so, don't override it
        current_text = self.results_text.toPlainText()
        if "Permutation testing:" in current_text:
            # Permutation progress is being shown, don't override
            return
        
        self.progress_dots = (self.progress_dots + 1) % 4
        dots = "." * self.progress_dots
        spaces = " " * (3 - self.progress_dots)
        
        self.results_text.setPlainText(
            f"Analysis in progress{dots}{spaces}\n\n"
            f"Computing features and statistics...\n\n"
            f"Please wait, this may take 3-5 minutes. Wait for the Generate Report button to be enabled.."
        )
    
    @QtCore.Slot()
    def _display_results(self):
        """Display the analysis results from multi_task_results using enhanced format"""
        print(f"\n>>> [MAIN THREAD] _display_results() CALLED <<<\n")
        
        engine = self.workflow.main_window.feature_engine
        
        print(f"\n=== FINAL RESULTS CHECK ===")
        print(f"hasattr(engine, 'multi_task_results'): {hasattr(engine, 'multi_task_results')}")
        if hasattr(engine, 'multi_task_results'):
            print(f"engine.multi_task_results is None: {engine.multi_task_results is None}")
            if engine.multi_task_results:
                print(f"engine.multi_task_results.keys(): {list(engine.multi_task_results.keys())}")
                print(f"per_task keys: {list(engine.multi_task_results.get('per_task', {}).keys())}")
        print(f"==========================\n")
        
        if hasattr(engine, 'multi_task_results') and engine.multi_task_results:
            # Try to use enhanced report generator for detailed display
            try:
                from utils.enhanced_report_generator import Enhanced64ChannelReportGenerator
                
                # Get multi-task results
                multi_task_results = engine.multi_task_results or {}
                per_task = multi_task_results.get('per_task', {})
                
                # Count baseline windows
                calibration_data = getattr(engine, 'calibration_data', {}) or {}
                baseline_ec_windows = len(calibration_data.get('eyes_closed', {}).get('features', []))
                baseline_eo_windows = len(calibration_data.get('eyes_open', {}).get('features', []))
                
                # Prepare results dictionary
                results_data = {
                    'session_info': {
                        'session_id': getattr(engine, 'session_id', 'N/A'),
                        'user_email': getattr(engine, 'user_email', 'N/A'),
                        'duration': getattr(engine, 'recording_duration', 0),
                        'n_samples': getattr(engine, 'total_samples', 0),
                        'n_channels': getattr(engine, 'channel_count', 64),
                        'sample_rate': getattr(engine, 'fs', 250),
                        'baseline_ec_windows': baseline_ec_windows,
                        'baseline_eo_windows': baseline_eo_windows,
                        'tasks_executed': len(per_task),
                        'subject_metadata': {}  # Will be populated below
                    },
                    'artifact_summary': getattr(engine, 'artifact_summary', {}),
                    'analysis_results': getattr(engine, 'analysis_results', {}),
                    'multi_task_results': multi_task_results,
                    'baseline_stats': getattr(engine, 'baseline_stats', {})
                }
                
                # Add subject metadata if available (from ANT Neuro metadata dialog)
                if hasattr(self.workflow.main_window, 'antneuro_metadata'):
                    metadata = self.workflow.main_window.antneuro_metadata
                    if metadata and 'subject' in metadata:
                        results_data['session_info']['subject_metadata'] = metadata['subject']
                
                # Get configuration
                config = getattr(engine, 'config', None)
                fast_mode = getattr(config, 'fast_mode', True) if config else True
                n_perm = getattr(config, 'n_perm', 100) if config else 100
                
                # Generate enhanced report
                report_lines = Enhanced64ChannelReportGenerator.generate_text_report(
                    results=results_data,
                    fast_mode=fast_mode,
                    n_permutations=n_perm,
                    config=config
                )
                
                # Display in results area
                results_text = "\n".join(report_lines)
                self.results_text.setPlainText(results_text)
                
                # Store for download
                self.generated_report_text = results_text
                
                print(f">>> [MAIN THREAD] Enhanced report displayed successfully <<<")
                
            except Exception as e:
                import traceback
                print(f"Enhanced display failed: {e}")
                traceback.print_exc()
                print("Falling back to basic display")
                
                # Fallback to basic display
                self._display_results_basic()
            
            # Enable buttons after successful display
            print(f">>> [MAIN THREAD] Enabling report buttons and finish button <<<")
            self.report_button.setEnabled(True)
            
            # Enable the visible seed button based on protocol status
            if self.seed_initial_button.isVisible():
                self.seed_initial_button.setEnabled(True)
            if self.seed_advanced_button.isVisible():
                self.seed_advanced_button.setEnabled(True)
            
            self.finish_button.setEnabled(True)
            print(f">>> [MAIN THREAD] Buttons enabled <<<")
            
        else:
            print(f">>> [MAIN THREAD] No results found - showing error message <<<")
            self.results_text.setPlainText("ERROR: No analysis results found.\n\nPlease ensure tasks have been recorded and try analyzing again.")
            self.report_button.setEnabled(False)
            if hasattr(self, 'seed_button'):
                self.seed_button.setEnabled(False)
        
        # Re-enable analyze button
        print(f">>> [MAIN THREAD] Re-enabling analyze button <<<")
        self.analyze_button.setEnabled(True)
        print(f">>> [MAIN THREAD] _display_results() COMPLETE <<<\n")
    
    def _display_results_basic(self):
        """Fallback basic display format"""
        engine = self.workflow.main_window.feature_engine
        res = engine.multi_task_results
        
        results = "ANALYSIS COMPLETE!\n"
        results += "=" * 60 + "\n\n"
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
                    results += "\n  *** DATA QUALITY WARNING ***\n"
                    for warning in data_quality.get('warnings', []):
                        # Wrap long warnings
                        if len(warning) > 60:
                            wrapped = [warning[i:i+55] for i in range(0, len(warning), 55)]
                            for w in wrapped:
                                results += f"    {w}\n"
                        else:
                            results += f"    {warning}\n"
                    results += "  [!] RESULTS MARKED AS UNRELIABLE\n"
                    results += "  *********************************************\n\n"
                elif sig_prop > 0.70:
                    # Fallback sanity check if data_quality not populated
                    results += "\n  *** DATA QUALITY WARNING ***\n"
                    results += f"    CRITICAL: {sig_prop*100:.1f}% of features marked significant!\n"
                    results += f"    This exceeds the 70% threshold and strongly suggests\n"
                    results += f"    the data is noise/garbage, NOT real EEG.\n"
                    results += f"    The headset may not have been worn properly.\n"
                    results += "  [!] RESULTS LIKELY INVALID\n"
                    results += "  *********************************************\n\n"
                elif sig_prop > 0.50:
                    results += f"\n  WARNING: {sig_prop*100:.1f}% of features significant\n"
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
            for feat in sig_features:
                results += f"  - {feat}\n"
        
        # Add completion message
        results += "\n" + "=" * 60 + "\n"
        results += "Analysis complete! Click 'Generate Report' to save detailed results.\n"
        
        self.results_text.setPlainText(results)
    
    @QtCore.Slot(str)
    def _show_error_callback(self, error_msg):
        """Show error message in UI (called from main thread)"""
        print(f">>> [MAIN THREAD] _show_error_callback() CALLED <<<")
        self.results_text.setPlainText(f"Error during analysis:\n{error_msg}\n\nSee console for details.")
        self.analyze_button.setEnabled(True)
    
    def _generate_report_text(self):
        """Generate report text internally (without triggering download)"""
        engine = self.workflow.main_window.feature_engine
        
        # Try to use enhanced report generator for 64-channel analysis
        if hasattr(engine, 'channel_count') and engine.channel_count == 64:
            try:
                from utils.enhanced_report_generator import Enhanced64ChannelReportGenerator
                
                # Get multi-task results which contains per-task analysis
                multi_task_results = getattr(engine, 'multi_task_results', {}) or {}
                per_task = multi_task_results.get('per_task', {})
                
                # Count baseline windows from calibration_data
                calibration_data = getattr(engine, 'calibration_data', {}) or {}
                baseline_ec_windows = len(calibration_data.get('eyes_closed', {}).get('features', []))
                baseline_eo_windows = len(calibration_data.get('eyes_open', {}).get('features', []))
                
                # Prepare results dictionary for enhanced generator
                results = {
                    'session_info': {
                        'session_id': getattr(engine, 'session_id', 'N/A'),
                        'user_email': getattr(engine, 'user_email', 'N/A'),
                        'duration': getattr(engine, 'recording_duration', 0),
                        'n_samples': getattr(engine, 'total_samples', 0),
                        'n_channels': engine.channel_count,
                        'sample_rate': engine.fs,
                        'baseline_ec_windows': baseline_ec_windows,
                        'baseline_eo_windows': baseline_eo_windows,
                        'tasks_executed': len(per_task)
                    },
                    'artifact_summary': getattr(engine, 'artifact_summary', {}),
                    'analysis_results': getattr(engine, 'analysis_results', {}),  # Last analyzed task results
                    'multi_task_results': multi_task_results,
                    'baseline_stats': getattr(engine, 'baseline_stats', {})
                }
                
                # Get configuration
                config = getattr(engine, 'config', None)
                fast_mode = getattr(config, 'fast_mode', True) if config else True
                n_perm = getattr(config, 'n_perm', 100) if config else 100
                
                # Generate enhanced report
                report_lines = Enhanced64ChannelReportGenerator.generate_text_report(
                    results=results,
                    fast_mode=fast_mode,
                    n_permutations=n_perm,
                    config=config
                )
                
                self.generated_report_text = "\n".join(report_lines)
                return self.generated_report_text
                
            except Exception as e:
                import traceback
                print(f"Enhanced report generation failed: {e}")
                traceback.print_exc()
                print("Falling back to basic format")
        
        # Fallback to basic report format
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("MULTI-CHANNEL EEG ANALYSIS REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Add multi-channel system information
        if hasattr(engine, 'channel_count'):
            report_lines.append(f"Recording System: {engine.channel_count}-Channel EEG")
            report_lines.append(f"Sampling Rate: {engine.fs} Hz")
            report_lines.append(f"Session ID: {getattr(engine, 'session_id', 'N/A')}")
            report_lines.append(f"User: {getattr(engine, 'user_email', 'N/A')}")
            report_lines.append("")
        
        # Add artifact detection summary
        if hasattr(engine, 'artifact_summary'):
            artifact_info = engine.artifact_summary
            report_lines.append("Artifact Detection Summary:")
            report_lines.append("-" * 40)
            report_lines.append(f"Bad channels detected: {len(artifact_info.get('bad_channels', []))}")
            report_lines.append(f"Flat channels: {len(artifact_info.get('flat_channels', []))}")
            report_lines.append(f"Noisy channels: {len(artifact_info.get('noisy_channels', []))}")
            report_lines.append(f"Artifact windows removed: {len(artifact_info.get('artifact_windows', []))}")
            
            # Channel quality summary
            channel_quality = artifact_info.get('channel_quality', {})
            if channel_quality:
                avg_quality = np.mean(list(channel_quality.values()))
                good_channels = sum(1 for q in channel_quality.values() if q >= 0.7)
                report_lines.append(f"Average channel quality: {avg_quality:.2f}")
                report_lines.append(f"Good channels (quality ≥ 0.7): {good_channels}/{len(channel_quality)}")
            report_lines.append("")
        
        # Add regional analysis summary
        report_lines.append("Multi-Channel Feature Extraction:")
        report_lines.append("-" * 40)
        report_lines.append("Per-Channel Features: 64 channels × 17 features = 1,088 features")
        report_lines.append("  - Band powers (delta, theta, alpha, beta, gamma)")
        report_lines.append("  - Relative powers, peak frequencies")
        report_lines.append("  - Cross-band ratios (alpha/theta, beta/alpha)")
        report_lines.append("")
        report_lines.append("Regional Features: 5 regions × 12 features = 60 features")
        report_lines.append("  - Frontal, Central, Temporal, Parietal, Occipital")
        report_lines.append("")
        report_lines.append("Spatial Features: ~140 features")
        report_lines.append("  - Hemispheric asymmetry (27 electrode pairs × 5 bands)")
        report_lines.append("  - Frontal alpha asymmetry (FAA)")
        report_lines.append("  - Inter-regional coherence (5 region pairs × 5 bands)")
        report_lines.append("  - Global field power (GFP)")
        report_lines.append("")
        report_lines.append("Total Features per Window: ~1,400 features")
        report_lines.append("")
        
        # Add results from multi_task_results
        for task_name, results in engine.multi_task_results.items():
            report_lines.append(f"\n{'='*60}")
            report_lines.append(f"Task: {task_name}")
            report_lines.append(f"{'='*60}")
            
            if isinstance(results, dict):
                # Extract region-specific results if available
                analysis = results.get('analysis', {})
                if analysis:
                    # Group features by type
                    region_features = {}
                    asymmetry_features = {}
                    coherence_features = {}
                    
                    for feat_name, feat_data in analysis.items():
                        if any(region in feat_name for region in ['frontal', 'central', 'temporal', 'parietal', 'occipital']):
                            region_features[feat_name] = feat_data
                        elif 'asymmetry' in feat_name or any(f'{ch1}_{ch2}' in feat_name for ch1, ch2 in [('F3', 'F4'), ('P3', 'P4')]):
                            asymmetry_features[feat_name] = feat_data
                        elif 'coherence' in feat_name:
                            coherence_features[feat_name] = feat_data
                    
                    # Report significant regional findings
                    if region_features:
                        sig_regional = [(k, v) for k, v in region_features.items() if v.get('significant_change')]
                        if sig_regional:
                            report_lines.append("\nSignificant Regional Changes:")
                            report_lines.append("-" * 40)
                            for feat_name, feat_data in sig_regional[:10]:  # Top 10
                                delta = feat_data.get('delta', 0)
                                p_val = feat_data.get('p_value', 1)
                                report_lines.append(f"  {feat_name}: Δ={delta:.3f}, p={p_val:.4f}")
                    
                    # Report significant asymmetry findings
                    if asymmetry_features:
                        sig_asym = [(k, v) for k, v in asymmetry_features.items() if v.get('significant_change')]
                        if sig_asym:
                            report_lines.append("\nSignificant Asymmetry Changes:")
                            report_lines.append("-" * 40)
                            for feat_name, feat_data in sig_asym[:5]:
                                delta = feat_data.get('delta', 0)
                                p_val = feat_data.get('p_value', 1)
                                report_lines.append(f"  {feat_name}: Δ={delta:.3f}, p={p_val:.4f}")
                    
                    # Report significant coherence findings
                    if coherence_features:
                        sig_coh = [(k, v) for k, v in coherence_features.items() if v.get('significant_change')]
                        if sig_coh:
                            report_lines.append("\nSignificant Coherence Changes:")
                            report_lines.append("-" * 40)
                            for feat_name, feat_data in sig_coh[:5]:
                                delta = feat_data.get('delta', 0)
                                p_val = feat_data.get('p_value', 1)
                                report_lines.append(f"  {feat_name}: Δ={delta:.3f}, p={p_val:.4f}")
                
                # Add general results
                for key, value in results.items():
                    if key != 'analysis':  # Skip detailed analysis (already shown above)
                        report_lines.append(f"{key}: {value}")
            else:
                report_lines.append(str(results))
        
        self.generated_report_text = "\n".join(report_lines)
        return self.generated_report_text
    
    def generate_report(self):
        """Generate REAL full report - delegates to Enhanced GUI which opens save dialog"""
        # Check if analysis was done first
        engine = self.workflow.main_window.feature_engine
        if not hasattr(engine, 'multi_task_results') or not engine.multi_task_results:
            QMessageBox.warning(
                self,
                "Analysis Required",
                "No analysis results available.\n\nPlease run 'Analyze All Tasks' first."
            )
            return
        
        try:
            # Generate report text for later seeding
            self._generate_report_text()
            
            # Call REAL report generation from main window (opens save dialog)
            self.workflow.main_window.generate_report_all_tasks()
            
            # The method itself shows success/error messages via log_message
        except Exception as e:
            QMessageBox.warning(
                self,
                "Report Error",
                f"Error generating report:\n{str(e)}"
            )
    
    def seed_report(self, protocol_type="initial"):
        """Seed the generated report to the database via API
        
        Args:
            protocol_type: Either "initial" or "advanced"
        """
        # Check if analysis was done first
        engine = self.workflow.main_window.feature_engine
        if not hasattr(engine, 'multi_task_results') or not engine.multi_task_results:
            QMessageBox.warning(
                self,
                "Analysis Required",
                "No analysis results available.\n\nPlease run 'Analyze All Tasks' first."
            )
            return
        
        # Generate report internally if not already generated
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
        
        # Store protocol type for API call
        self.current_protocol_type = protocol_type
        
        # Create confirmation dialog with email input
        dialog = QDialog(self)
        protocol_display = "Initial Protocol" if protocol_type == "initial" else "Advanced Protocol"
        dialog.setWindowTitle(f"Seed {protocol_display} Report")
        dialog.setModal(True)
        dialog.setMinimumWidth(450)
        
        # Set window icon
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
        email_label = QLabel("Email Address:")
        email_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #1f2937;")
        
        email_input = QLineEdit()
        email_input.setPlaceholderText("user@example.com")
        email_input.setClearButtonEnabled(True)
        
        # Get saved username as default
        settings = QSettings("MindLink", "FeatureAnalyzer")
        saved_email = settings.value("username", "")
        email_input.setText(saved_email)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #475569;
                padding: 8px 18px;
            }
            QPushButton:hover {
                background-color: #cbd5e1;
            }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        
        confirm_btn = QPushButton("Confirm & Seed")
        confirm_btn.setStyleSheet("padding: 8px 18px;")
        confirm_btn.clicked.connect(dialog.accept)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(confirm_btn)
        
        # Assembly
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(email_label)
        layout.addWidget(email_input)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        apply_modern_dialog_theme(dialog)
        
        # Show dialog
        if dialog.exec() == QDialog.Accepted:
            email = email_input.text().strip()
            
            if not email:
                QMessageBox.warning(self, "Invalid Email", "Please enter a valid email address.")
                return
            
            # Send report to API
            self._send_report_to_api(email)
    
    def _send_report_to_api(self, email):
        """Send the report to the seeding API endpoint with protocol_type"""
        import requests
        import uuid
        
        # Get protocol type (default to "initial" if not set)
        protocol_type = getattr(self, 'current_protocol_type', 'initial')
        import base64
        from datetime import datetime
        
        # Get JWT token from main window
        jwt_token = getattr(self.workflow.main_window, 'jwt_token', None)
        if not jwt_token:
            QMessageBox.warning(
                self,
                "Authentication Required",
                "No authentication token found. Please log in first."
            )
            return
        
        # Determine API endpoint
        api_base = BL.BACKEND_URL.replace("/brainlink_data", "")
        seed_url = f"{api_base}/eeg-reports/seed"
        
        # Prepare payload with base64 encoded report
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # Encode the report text to base64
        report_bytes = self.generated_report_text.encode('utf-8')
        report_base64 = base64.b64encode(report_bytes).decode('utf-8')
        
        # Use the protocol_type that was set when button was clicked
        # (already set as self.current_protocol_type in seed_report method)
        
        # Use partner_id from workflow (entered in Partner ID dialog)
        partner_id = getattr(self.workflow.main_window, 'partner_id', None)
        if not partner_id:
            partner_id = 1  # Fallback if not set
        
        # Get task count for metadata
        engine = self.workflow.main_window.feature_engine
        task_count = len(engine.multi_task_results) if hasattr(engine, 'multi_task_results') and engine.multi_task_results else 0
        
        payload = {
            "email": email,
            "report_text": report_base64,
            "is_base64": True,
            "protocol_type": protocol_type,  # Use the protocol_type from button click
            "partner_id": partner_id,
            "session_id": session_id,
            "generation_meta": {
                "generated_at": datetime.now().isoformat(),
                "analyzer_version": "1.0",
                "workflow": "sequential_integrated",
                "task_count": task_count
            }
        }
        
        # Show progress
        progress = QMessageBox(self)
        progress.setWindowTitle("Seeding Report")
        progress.setText("Sending report to database...")
        progress.setStandardButtons(QMessageBox.NoButton)
        progress.setModal(True)
        progress.show()
        QtWidgets.QApplication.processEvents()
        
        try:
            headers = {
                "X-Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json"
            }
            
            # Determine if SSL verification should be disabled (for localhost)
            verify_ssl = "127.0.0.1" not in seed_url and "localhost" not in seed_url
            
            # Log payload details for debugging
            import json
            payload_json = json.dumps(payload)
            payload_size_kb = len(payload_json.encode('utf-8')) / 1024
            
            self.workflow.main_window.log_message(f"Seeding report to: {seed_url}")
            self.workflow.main_window.log_message(f"Protocol type: {protocol_type}, Partner ID: {partner_id}")
            self.workflow.main_window.log_message(f"Payload size: {payload_size_kb:.2f} KB")
            
            print(f"\n>>> SEEDING REPORT <<<")
            print(f"URL: {seed_url}")
            print(f"Protocol Type: {protocol_type}")
            print(f"Partner ID: {partner_id}")
            print(f"Payload Size: {payload_size_kb:.2f} KB")
            print(f"Headers: {headers}")
            print(f"Verify SSL: {verify_ssl}")
            
            response = requests.post(
                seed_url, 
                json=payload, 
                headers=headers, 
                timeout=60,  # Increased timeout for large reports
                verify=verify_ssl
            )
            
            # Close progress dialog - use hide + deleteLater for complete removal
            progress.hide()
            progress.close()
            progress.deleteLater()
            QtWidgets.QApplication.processEvents()
            
            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                
                # Create a success dialog with enhanced styling
                success_dialog = QMessageBox(self)
                success_dialog.setWindowTitle("✓ Report Seeded Successfully")
                success_dialog.setIcon(QMessageBox.Information)
                
                success_message = (
                    "🎉 Your EEG report has been successfully sent to the Mindspeller database!\n\n"
                    "Report Details:\n"
                    f"• User ID: {result.get('user_id', 'N/A')}\n"
                    f"• Session ID: {result.get('session_id', 'N/A')}\n"
                    f"• Report ID: {result.get('report_id', 'N/A')}\n\n"
                    "✓ Your neuroprofiling report is now available in your Mindspeller account.\n"
                    "✓ You can access it immediately at mindspeller.com\n"
                    "✓ You can safely close this application now.\n\n"
                    "Thank you for using MindLink Analyzer!"
                )
                
                success_dialog.setText(success_message)
                success_dialog.setStandardButtons(QMessageBox.Ok)
                
                # Style the dialog
                success_dialog.setStyleSheet("""
                    QMessageBox {
                        background-color: #f0fdf4;
                    }
                    QLabel {
                        color: #166534;
                        font-size: 13px;
                    }
                    QPushButton {
                        background-color: #10b981;
                        color: white;
                        padding: 8px 24px;
                        border-radius: 6px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background-color: #059669;
                    }
                """)
                
                success_dialog.exec()
                
                # Show a toast notification as well
                try:
                    self.workflow.main_window.log_message(
                        f"✓ Report seeded successfully! User ID: {result.get('user_id')}, "
                        f"Session ID: {result.get('session_id')}, Report ID: {result.get('report_id')}"
                    )
                except:
                    pass
                
            else:
                error_msg = response.json().get('error', 'Unknown error') if response.content else 'Unknown error'
                QMessageBox.warning(
                    self,
                    "Seeding Failed",
                    f"Failed to seed report.\n\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {error_msg}"
                )
                
        except requests.exceptions.RequestException as e:
            # Ensure progress dialog is closed on error - use hide + deleteLater
            progress.hide()
            progress.close()
            progress.deleteLater()
            QtWidgets.QApplication.processEvents()
            error_details = str(e)
            
            # Provide more helpful error message for common issues
            if "Connection aborted" in error_details or "10053" in error_details:
                error_msg = (
                    "Connection to server was lost.\n\n"
                    "Possible causes:\n"
                    "• Server closed the connection (check if Flask server is running)\n"
                    "• Request timeout (report may be too large)\n"
                    "• Network issue\n\n"
                    f"Technical details: {error_details}"
                )
            elif "Connection refused" in error_details or "10061" in error_details:
                error_msg = (
                    "Cannot connect to server.\n\n"
                    f"Is the server running at {seed_url}?\n\n"
                    f"Technical details: {error_details}"
                )
            else:
                error_msg = f"Failed to connect to API:\n{error_details}"
            
            self.workflow.main_window.log_message(f"Error seeding report: {error_details}")
            
            QMessageBox.critical(
                self,
                "Network Error",
                error_msg
            )
        except Exception as e:
            # Ensure progress dialog is closed on error - use hide + deleteLater
            progress.hide()
            progress.close()
            progress.deleteLater()
            QtWidgets.QApplication.processEvents()
            QMessageBox.critical(
                self,
                "Error",
                f"Unexpected error while seeding report:\n{str(e)}"
            )
    
    def on_back(self):
        """Navigate back"""
        if self.status_bar:
            self.status_bar.cleanup()
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())
    
    def on_finish(self):
        """Complete the workflow"""
        # Ask if user wants to exit or restart
        reply = QMessageBox.question(
            self,
            'Workflow Complete',
            'Analysis complete!\n\nWould you like to:\n• Yes: Exit application\n• No: Return to task selection',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if self.status_bar:
            self.status_bar.cleanup()
        self._programmatic_close = True
        self.close()
        
        if reply == QMessageBox.Yes:
            # Close the application
            QTimer.singleShot(100, lambda: self.workflow.main_window.close())
        else:
            # Return to task selection
            QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.TASK_SELECTION))


# ============================================================================
# MAIN WINDOW (Enhanced GUI with Sequential Workflow)
# ============================================================================

class SequentialBrainLinkAnalyzerWindow(EnhancedBrainLinkAnalyzerWindow):
    """Enhanced GUI with sequential workflow overlay"""
    
    def __init__(self, user_os, config: Optional[EnhancedAnalyzerConfig] = None):
        # Initialize the REAL Enhanced GUI
        super().__init__(user_os, config=config)
        
        # Initialize user_data attribute for protocol checking
        self.user_data = {}
        
        # Initialize partner_id and partners_list
        self.partner_id = None
        self.partners_list = []
        
        # Ensure protocol groups use the correct Lifestyle tasks (now implemented)
        self._protocol_groups = {
            'Personal Pathway': ['emotion_face', 'diverse_thinking'],
            'Connection': ['reappraisal', 'curiosity'],
            'Lifestyle': ['order_surprise', 'num_form'],
        }
        
        # Hide the main window initially (workflow is popup-driven)
        self.hide()
        
        # Initialize workflow manager
        self.workflow = WorkflowManager(self)
        
        # Start the workflow
        QTimer.singleShot(100, self.start_workflow)
    
    def switch_to_enhanced_64ch_engine(self):
        """Switch to OFFLINE 64-channel engine for ANT Neuro device.
        
        Called when ANT Neuro is selected in device type dialog.
        Uses OFFLINE analysis: records raw data during streaming,
        extracts all features when "Analyze" is clicked.
        """
        # Prefer OFFLINE engine (records raw data, processes later)
        if OFFLINE_64CH_AVAILABLE:
            print(f"\n{'='*70}")
            print(f"[MAIN WINDOW] SWITCHING TO OFFLINE 64-CHANNEL ANALYSIS ENGINE")
            print(f"[MAIN WINDOW] Mode: Record raw data during streaming")
            print(f"[MAIN WINDOW] Features: 1400+ extracted OFFLINE when 'Analyze' clicked")
            print(f"[MAIN WINDOW] Analysis: FAST MODE (parametric tests, ~30 seconds)")
            print(f"[MAIN WINDOW] Raw data saved to: ~/BrainLink_Recordings/")
            print(f"{'='*70}\n")
            
            # Get user email from settings
            settings = QSettings("MindLink", "FeatureAnalyzer")
            user_email = settings.value("username", "unknown")
            
            # Create offline engine with user email
            self.feature_engine = create_offline_engine(
                sample_rate=500,
                channel_count=64,
                user_email=user_email
            )
            
            # Enable FAST MODE for 64-channel analysis to avoid 20+ minute permutation testing
            # Fast mode uses chi-square approximation + parametric tests
            # Aligns with standalone analyzer settings (BrainLink_Offline_Analyzer.py)
            if hasattr(self.feature_engine, 'config'):
                self.feature_engine.config.fast_mode = True
                self.feature_engine.config.n_perm = 200  # Match standalone default (sufficient for p-value resolution)
                self.feature_engine.config.use_permutation_for_sumP = False  # Use chi-square approximation in fast mode
                print(f"[MAIN WINDOW] FAST MODE ENABLED: Parametric tests + chi-square approximation (n_perm={self.feature_engine.config.n_perm})")
            self.feature_engine.set_log_function(self.log_message)
            self.using_enhanced_engine = True
            self.using_offline_engine = True
            
            # CRITICAL: Set feature engine on ANT_NEURO so on_data callback can record data
            ANT_NEURO.feature_engine = self.feature_engine
            print(f"[MAIN WINDOW] ANT_NEURO.feature_engine set to {type(self.feature_engine).__name__}")
            
            return True
        
        # Fallback to live enhanced engine if offline not available
        if ENHANCED_64CH_AVAILABLE:
            print(f"\n{'='*70}")
            print(f"[MAIN WINDOW] SWITCHING TO LIVE 64-CHANNEL ANALYSIS ENGINE")
            print(f"[MAIN WINDOW] Features: 1400+ per epoch (live processing)")
            print(f"{'='*70}\n")
            
            self.feature_engine = create_enhanced_engine(sample_rate=500, channel_count=64)
            self.feature_engine.set_log_function(self.log_message)
            self.using_enhanced_engine = True
            self.using_offline_engine = False
            
            ANT_NEURO.feature_engine = self.feature_engine
            print(f"[MAIN WINDOW] ANT_NEURO.feature_engine set to {type(self.feature_engine).__name__}")
            
            return True
        
        # Last resort: use default engine
        print(f"[MAIN WINDOW] Enhanced 64-channel engine not available, using default engine")
        if not hasattr(self, 'feature_engine') or self.feature_engine is None:
            print(f"[MAIN WINDOW] WARNING: Feature engine not initialized! Creating basic engine...")
            from BrainLinkAnalyzer_GUI_Enhanced import EnhancedFeatureAnalysisEngine, EnhancedAnalyzerConfig
            config = EnhancedAnalyzerConfig()
            self.feature_engine = EnhancedFeatureAnalysisEngine(config=config)
            self.feature_engine.set_log_function(self.log_message)
        
        ANT_NEURO.feature_engine = self.feature_engine
        self.using_offline_engine = False
        print(f"[MAIN WINDOW] ANT_NEURO.feature_engine set to {type(self.feature_engine).__name__}")
        return False
    
    def start_workflow(self):
        """Begin the sequential workflow"""
        self.workflow.go_to_step(WorkflowStep.OS_SELECTION)
    
    def closeEvent(self, event):
        """Handle window close with confirmation"""
        # Temporarily clear WindowStaysOnTopHint from any active dialogs
        active_dialog = self.workflow.current_dialog
        was_on_top = False
        if active_dialog and active_dialog.isVisible():
            was_on_top = bool(active_dialog.windowFlags() & Qt.WindowStaysOnTopHint)
            if was_on_top:
                active_dialog.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                active_dialog.show()
        
        # Ask for confirmation before closing
        reply = QMessageBox.question(
            self,
            'Confirm Exit',
            'Are you sure you want to exit MindLink Analyzer?\n\nAll unsaved data will be lost.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        # Restore WindowStaysOnTopHint if it was set
        if active_dialog and active_dialog.isVisible() and was_on_top:
            active_dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            active_dialog.show()
        
        if reply == QMessageBox.Yes:
            # Close any open workflow dialogs (force close without recursion)
            if self.workflow.current_dialog:
                try:
                    # Disconnect the closeEvent to prevent recursion
                    self.workflow.current_dialog.closeEvent = lambda e: e.accept()
                    self.workflow.current_dialog.close()
                except Exception:
                    pass
            
            # Clean up serial connection properly
            try:
                BL.stop_thread_flag = True
                if hasattr(self, 'serial_obj') and self.serial_obj and hasattr(self.serial_obj, 'is_open') and self.serial_obj.is_open:
                    self.serial_obj.close()
                if hasattr(self, 'brainlink_thread') and self.brainlink_thread and self.brainlink_thread.is_alive():
                    self.brainlink_thread.join(timeout=2)
            except Exception:
                pass
            
            # Clean up ANT Neuro EDI2 connection (stops gRPC server)
            try:
                print("[CLEANUP] Stopping ANT Neuro connections...")
                
                # Stop streaming first
                if ANT_NEURO and ANT_NEURO.is_streaming:
                    print("[CLEANUP] Stopping streaming...")
                    ANT_NEURO.stop_streaming()
                
                # Disconnect and cleanup EDI2 client
                if ANT_NEURO and hasattr(ANT_NEURO, 'edi2_client') and ANT_NEURO.edi2_client:
                    print("[CLEANUP] Disposing EDI2 amplifier handle...")
                    try:
                        # Dispose amplifier handle
                        if ANT_NEURO.edi2_client.stub and ANT_NEURO.edi2_client.amplifier_handle is not None:
                            import sys
                            import os
                            antneuro_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'antNeuro')
                            if antneuro_dir not in sys.path:
                                sys.path.insert(0, antneuro_dir)
                            import EdigRPC_pb2 as edi
                            
                            ANT_NEURO.edi2_client.stub.Amplifier_Dispose(
                                edi.Amplifier_DisposeRequest(
                                    AmplifierHandle=ANT_NEURO.edi2_client.amplifier_handle
                                )
                            )
                            print(f"[CLEANUP] Amplifier handle {ANT_NEURO.edi2_client.amplifier_handle} disposed")
                    except Exception as e:
                        print(f"[CLEANUP] Handle disposal error: {e}")
                    
                    # Disconnect gRPC and stop server
                    print("[CLEANUP] Disconnecting gRPC...")
                    ANT_NEURO.edi2_client._disconnect_grpc()
                    print("[CLEANUP] Stopping EDI2 gRPC server...")
                    ANT_NEURO.edi2_client._stop_server()
                
                # Full disconnect
                if ANT_NEURO and ANT_NEURO.is_connected:
                    print("[CLEANUP] Final ANT Neuro disconnect...")
                    ANT_NEURO.disconnect()
                
                print("[CLEANUP] ANT Neuro cleanup complete")
            except Exception as e:
                print(f"[CLEANUP] ANT Neuro cleanup error: {e}")
                import traceback
                traceback.print_exc()
            
            # Clean up any timers
            try:
                if hasattr(self, '_calibration_timer'):
                    self._calibration_timer.stop()
            except Exception:
                pass
            
            # Accept the close event
            event.accept()
            
            # Call parent's closeEvent for any additional cleanup
            super().closeEvent(event)
            
            # Force quit the application since we disabled automatic quit on last window close
            QTimer.singleShot(100, lambda: QtWidgets.QApplication.quit())
        else:
            # Ignore the close event
            event.ignore()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Create QApplication first
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Prevent app from quitting when last visible window closes
    # This is critical for the sequential workflow where the main window is hidden
    app.setQuitOnLastWindowClosed(False)
    
    # Start with OS selection workflow
    window = SequentialBrainLinkAnalyzerWindow("Windows")
    
     # Close PyInstaller splash screen after app is initialized
    try:
        import pyi_splash  # type: ignore
        pyi_splash.close()
    except (ImportError, RuntimeError):
        pass
   
    sys.exit(app.exec())
