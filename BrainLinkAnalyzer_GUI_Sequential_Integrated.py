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
    QMessageBox
)
from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QIcon
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
            battery_label = QLabel("Battery --%")
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
        
        layout.addStretch()
        
        # Help button
        self.help_button = QPushButton("Help")
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
            _STALE_S = 2.0
            now = time.time()
            
            # -------------------------------------------------------
            # CRITICAL: Check hardware signal quality FIRST
            # If signal=200, the onRaw() gate blocks samples, making
            # buffer empty. Must check this BEFORE buffer length to
            # show "Not Worn" instead of "No Signal".
            # -------------------------------------------------------
            _hw_signal = getattr(BL, 'headset_signal_quality', None)
            if _hw_signal is not None and _hw_signal >= 200:
                # Headset is transmitting but electrode has no contact
                self.eeg_status.setText("EEG: Not Worn")
                self.eeg_status.setStyleSheet("color: #f59e0b; font-weight: 700;")
                self._sq_displayed_noisy = True
                self._sq_noisy_reason = 'demo_signal'
                self._sq_worn_since = None
                if not getattr(self, '_sq_not_worn_since', None):
                    self._sq_not_worn_since = now
                self.signal_quality.setText("Signal: Headset Not Worn")
                self.signal_quality.setStyleSheet("color: #ef4444; font-weight: 700;")
                return
            
            # Check EEG connection status (buffer has data = device connected)
            if BL.live_data_buffer and len(BL.live_data_buffer) > 0:
                self.eeg_status.setText("EEG: Connected")
                self.eeg_status.setStyleSheet("color: #10b981; font-weight: 700;")
            else:
                self.eeg_status.setText("EEG: No Signal")
                self.eeg_status.setStyleSheet("color: #fbbf24; font-weight: 700;")
            
            # Professional multi-metric signal quality assessment (same as LiveEEGDialog)
            if len(BL.live_data_buffer) >= 512:
                recent_data = np.array(list(BL.live_data_buffer)[-512:])
                
                # Staleness check: frozen buffer means headset disconnected
                current_tail = tuple(recent_data[-4:])
                if current_tail != getattr(self, '_sq_last_tail', None):
                    self._sq_last_tail = current_tail
                    self._sq_last_change_time = now
                elif getattr(self, '_sq_last_change_time', None) and (now - self._sq_last_change_time) > _STALE_S:
                    self.eeg_status.setText("EEG: No Signal")
                    self.eeg_status.setStyleSheet("color: #fbbf24; font-weight: 700;")
                    self.signal_quality.setText("Signal: No Signal")
                    self.signal_quality.setStyleSheet("color: #94a3b8; font-weight: 700;")
                    return
                
                result = assess_eeg_signal_quality(recent_data, fs=512)
                if result is None:
                    return
                quality_score, status, details = result

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

                # Asymmetric hysteresis: 3s not_worn → Noisy; 5s worn → Good.
                if status == "not_worn":
                    self._sq_worn_since = None
                    if not getattr(self, '_sq_not_worn_since', None):
                        self._sq_not_worn_since = now
                    if (now - self._sq_not_worn_since) >= 3.0:
                        self._sq_displayed_noisy = True
                        self._sq_noisy_reason = details.get('not_worn_reason', 'not_worn')
                else:
                    self._sq_not_worn_since = None
                    if not getattr(self, '_sq_worn_since', None):
                        self._sq_worn_since = now
                    if (now - self._sq_worn_since) >= 5.0:
                        self._sq_displayed_noisy = False
                if getattr(self, '_sq_displayed_noisy', False):
                    if getattr(self, '_sq_noisy_reason', '') == 'demo_signal':
                        self.signal_quality.setText("Signal: Demo Signal")
                        self.signal_quality.setStyleSheet("color: #ef4444; font-weight: 700;")
                    else:
                        self.signal_quality.setText("Signal: Noisy")
                        self.signal_quality.setStyleSheet("color: #f59e0b; font-weight: 700;")
                else:
                    self.signal_quality.setText("Signal: Good")
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
    
    def cleanup(self):
        """Stop the update timer and close help dialog"""
        self.update_timer.stop()
        if self.help_dialog and self.help_dialog.isVisible():
            self.help_dialog.close()


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
        help_button = QPushButton("Help")
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
            'language_processing', 'motor_imagery', 'cognitive_load'
        ]
    
    def _apply_protocol_filter(self):
        """Apply protocol filter to task_combo based on selected protocol"""
        # Rebuild task combo to include cognitive tasks + selected protocol tasks
        if not hasattr(self, 'task_combo') or self.task_combo is None:
            return
        
        self.task_combo.blockSignals(True)
        self.task_combo.clear()
        
        # Add cognitive tasks (present in AVAILABLE_TASKS)
        for key in self._cognitive_tasks:
            if key in getattr(BL, 'AVAILABLE_TASKS', {}):
                self.task_combo.addItem(key)
        
        # Add protocol-specific tasks
        if self._selected_protocol and self._selected_protocol in self._protocol_groups:
            for key in self._protocol_groups[self._selected_protocol]:
                if key in getattr(BL, 'AVAILABLE_TASKS', {}):
                    self.task_combo.addItem(key)
        
        # Select first item if available
        if self.task_combo.count() > 0:
            self.task_combo.setCurrentIndex(0)
            try:
                self.update_task_preview(self.task_combo.currentText())
            except Exception:
                pass
        
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
        
        title = QLabel("User Manual")
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
        self.tab_widget.addTab(getting_started_tab, "Getting Started")
        
        # Tab 2: User Manual (existing content)
        manual_tab = self.create_manual_tab()
        self.tab_widget.addTab(manual_tab, "User Manual")
        
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
        
        close_button = QPushButton("Close")
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
        
        toc_title = QLabel("Contents")
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
# WORKFLOW STATE MANAGER
# ============================================================================# ============================================================================
# WORKFLOW STATE MANAGER
# ============================================================================

class WorkflowStep:
    """Enumeration of workflow steps"""
    OS_SELECTION = 0
    ENVIRONMENT_SELECTION = 1
    LOGIN = 2
    PARTNER_ID = 3
    LIVE_EEG = 4
    PATHWAY_SELECTION = 5
    CALIBRATION = 6
    TASK_SELECTION = 7
    MULTI_TASK_ANALYSIS = 8


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
        if step == WorkflowStep.ENVIRONMENT_SELECTION:
            self._show_environment_selection()
        elif step == WorkflowStep.LOGIN:
            self._show_login()
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
    def _show_environment_selection(self):
        dialog = EnvironmentSelectionDialog(self)
        self.current_dialog = dialog
        dialog.show()  # Use show() instead of exec()
        dialog.raise_()
        dialog.activateWindow()
    
    def _show_login(self):
        dialog = LoginDialog(self)
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

class OSSelectionDialog:
    """Removed - OS defaults to Windows"""
    pass


# ============================================================================
# STEP 2: ENVIRONMENT SELECTION (With REAL device detection)
# ============================================================================

class EnvironmentSelectionDialog(QDialog):
    """Step 2: Select region where the user has their Mindspeller account"""
    
    def __init__(self, workflow: WorkflowManager, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.setWindowTitle("MindLink - preparation section")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(450)
        
        # Set window icon
        set_window_icon(self)
        
        # UI Elements
        title_label = QLabel("IMPORTANT!!")
        title_label.setObjectName("DialogTitle")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: 700;")        
        # Set English (en) defaults immediately
        BL.BACKEND_URL = "https://en.mindspeller.com/api/cas/brainlink_data"
        self.workflow.main_window.login_url = "https://en.mindspeller.com/api/cas/token/login"
        self.workflow.main_window.current_region = "be"
        self.workflow.main_window.selected_environment = "English (en)"
        
        # Amplifier preparation instructions
        prep_card = QFrame()
        prep_card.setObjectName("DialogCard")
        prep_layout = QVBoxLayout(prep_card)
        prep_layout.setContentsMargins(16, 16, 16, 16)
        prep_layout.setSpacing(10)
        
        prep_label = QLabel("Before You Continue:")
        prep_label.setObjectName("DialogSectionTitle")
        
        info_label = QLabel(
            "Please ensure the headset is:\n\n"
            "  • Turned ON and worn on your head correctly\n\n"
            "The device connection will be confirmed when you sign in on the next step.\n\n"
            "Consult the setup help section(section 1 and 3) on how to put on the headset and confirm it is working."
        )
        info_label.setStyleSheet("font-size: 13px; color: #3b82f6; padding: 12px; background: #eff6ff; border-radius: 6px; border-left: 3px solid #3b82f6; line-height: 1.6;")
        info_label.setWordWrap(True)
        
        prep_layout.addWidget(prep_label)
        prep_layout.addWidget(info_label)
        
        # Help button for setup reference
        help_ref_button = QPushButton("Setup Help")
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
        nav_layout.addStretch()
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.on_next)
        
        nav_layout.addWidget(self.next_button)
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
 
        layout.addWidget(prep_card)
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
    
    def on_next(self):
        """Proceed to login"""
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.LOGIN))


# ============================================================================
# STEP 2.5: PARTNER ID INPUT
# ============================================================================

class PartnerIDDialog:
    """Removed - partner ID defaults to PARTNER_000001"""
    pass


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
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: 700;")
        
        subtitle_label = QLabel("Step 3 of 9: Enter your credentials")
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
        
        # Eye icon toggle button (FontAwesome via qtawesome)
        try:
            import qtawesome as qta
            _eye_icon = qta.icon('fa5s.eye', color='#64748b')
        except Exception:
            _eye_icon = None
        self.password_toggle_btn = QPushButton()
        if _eye_icon:
            self.password_toggle_btn.setIcon(_eye_icon)
        else:
            self.password_toggle_btn.setText("Show")
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
        
        self.login_button = QPushButton("Sign In")
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
        """Toggle password visibility with FontAwesome eye icon"""
        try:
            import qtawesome as qta
            if self.password_edit.echoMode() == QLineEdit.Password:
                self.password_edit.setEchoMode(QLineEdit.Normal)
                self.password_toggle_btn.setIcon(qta.icon('fa5s.eye-slash', color='#64748b'))
                self.password_toggle_btn.setText('')
            else:
                self.password_edit.setEchoMode(QLineEdit.Password)
                self.password_toggle_btn.setIcon(qta.icon('fa5s.eye', color='#64748b'))
                self.password_toggle_btn.setText('')
        except Exception:
            # Fallback to text if qtawesome fails
            if self.password_edit.echoMode() == QLineEdit.Password:
                self.password_edit.setEchoMode(QLineEdit.Normal)
                self.password_toggle_btn.setText('Hide')
            else:
                self.password_edit.setEchoMode(QLineEdit.Password)
                self.password_toggle_btn.setText('Show')
    
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
            # Call the REAL detect_brainlink function
            port = BL.detect_brainlink()
            
            if port:
                BL.SERIAL_PORT = port
                self.workflow.main_window.log_message(f"EEG headset detected on port: {port}")
                
                # Device detected, proceed with authentication
                self.status_label.setText("Device connected. Authenticating...")
                
                # Save credentials
                self.settings.setValue("username", username)
                self.settings.setValue("password", password)
                
                # Get login URL from main window (set in environment selection)
                login_url = getattr(self.workflow.main_window, 'login_url', None)
                
                # Fallback if not set
                if not login_url:
                    login_urls = {
                        "English (en)": "https://en.mindspeller.com/api/cas/token/login",
                        # "Dutch (nl)": "https://nl.mindspeller.com/api/cas/token/login",
                        # "Local": "http://127.0.0.1:5000/api/cas/token/login"
                    }
                    
                    # Determine which backend URL is set
                    current_backend = BL.BACKEND_URL
                    login_url = login_urls["English (en)"]
                    # elif "nl" in current_backend or "nl.mindspeller" in current_backend:
                    #     login_url = login_urls["Dutch (nl)"]
                    # else:
                    #     login_url = login_urls["Local"]
                
                # Store login_url in self for API calls
                self.login_url = login_url
                
                # Perform REAL authentication
                QTimer.singleShot(100, lambda: self._perform_login(username, password, login_url))
            else:
                # Show prominent error message
                self.error_info_label.setText(
                    "Warning: DEVICE CONNECTION FAILED\n\n"
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
        except Exception as e:
            self.error_info_label.setText(
                "Warning: DEVICE DETECTION ERROR\n\n"
                f"Error: {str(e)}\n\n"
                "TO RESOLVE:\n"
                "1. Close this application completely\n"
                "2. Turn OFF the EEG headset\n"
                "3. Turn ON the EEG headset\n"
                "4. Restart this application"
            )
            self.error_info_label.setVisible(True)
            self.status_label.setText("Device detection error. Please follow the instructions above.")
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
                    self.workflow.main_window.log_message("Login successful. JWT token obtained.")
                    
                    if hwid:
                        self.workflow.main_window.log_message(f"Hardware ID received: {hwid}")
                        BL.ALLOWED_HWIDS = [hwid]
                    
                    # Fetch userData from dedicated endpoint
                    self._fetch_user_data(jwt_token)
                    
                    # Fetch partners list for validation
                    self._fetch_partners_list(jwt_token)
                    
                    # Fetch user HWIDs
                    self._fetch_user_hwids(jwt_token)
                    
                    # Start device connection
                    self._connect_device()
                    
                    self.status_label.setText("Login successful. Please enter Partner ID...")
                    self.status_label.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")
                    # Hide error message on success
                    self.error_info_label.setVisible(False)
                    
                    # Auto-proceed to Partner ID after 1 second
                    QTimer.singleShot(1000, self.on_auto_next)
                else:
                    self.error_info_label.setText(
                        "Warning: AUTHENTICATION FAILED\n\n"
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
                    "Warning: AUTHENTICATION FAILED\n\n"
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
                "Warning: AUTHENTICATION ERROR\n\n"
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
                self.workflow.main_window.log_message(f"User data fetched successfully")
                
                # Log initial_protocol status for debugging
                initial_protocol = user_data.get('initial_protocol', '')
                if initial_protocol:
                    self.workflow.main_window.log_message(f"User has completed initial protocol: {initial_protocol}")
                    print(f"Initial protocol found: {initial_protocol}")
                else:
                    self.workflow.main_window.log_message("User has not completed initial protocol yet")
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
                self.workflow.main_window.log_message(f"Fetched {len(partners_list)} partners")
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
                self.workflow.main_window.log_message(f"Fetched {len(BL.ALLOWED_HWIDS)} authorized device IDs")
        except Exception as e:
            self.workflow.main_window.log_message(f"Error fetching HWIDs: {e}")
    
    def _connect_device(self):
        """Connect to the MindLink device"""
        import threading
        from cushy_serial import CushySerial
        
        port = BL.SERIAL_PORT
        if not port:
            port = BL.detect_brainlink()
            BL.SERIAL_PORT = port
        
        if not port:
            self.workflow.main_window.log_message("No MindLink device found!")
            return
        
        self.workflow.main_window.log_message(f"Connecting to MindLink device: {port}")
        
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
            
            self.workflow.main_window.log_message("MindLink connected successfully!")
        except Exception as e:
            self.workflow.main_window.log_message(f"Failed to connect: {str(e)}")
    
    def _complete_login(self):
        """Complete login"""
        self.status_label.setText("Login successful")
        self.status_label.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")
        self.login_button.setEnabled(True)
        self.login_button.setText("Sign In")
    
    def on_auto_next(self):
        """Auto-proceed to Live EEG after successful login"""
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_to_step(WorkflowStep.LIVE_EEG))
    
    def on_back(self):
        """Navigate back"""
        self._programmatic_close = True
        self.close()
        QTimer.singleShot(100, lambda: self.workflow.go_back())


# ============================================================================
# STEP 3.5: PATHWAY SELECTION (Protocol Selection)
# ============================================================================

class PathwaySelectionDialog:
    """Removed - pathway defaults to Personal Pathway"""
    pass


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
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: 700;")  # Header style, centered
        
        subtitle_label = QLabel("Step 5 of 9: Monitoring real brain activity")
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
        self.plot_widget.setLabel('bottom', 'Time (samples)')
        self.plot_widget.setTitle('Raw EEG Signal (upto 10s visual delay)', color='w', size='12pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color='#3b82f6', width=2))
        
        plot_layout.addWidget(self.plot_widget)
        
        # Status info
        self.info_label = QLabel("Signal quality: Good | Ensure proper electrode contact")
        self.info_label.setStyleSheet("color: #10b981; font-size: 11px; padding: 6px;")  # Reduced from 13px, 8px
        self.info_label.setAlignment(Qt.AlignCenter)
        
        # Important stabilization notice
        stabilization_notice = QLabel(
            " IMPORTANT: Please wait 20-30 seconds for the signal to stabilize after wearing the headset.\n\n"
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
        self.reconnect_help_button = QPushButton(" Device Disconnected?")
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
        self.update_timer.start(50)  # 20 Hz update rate
        
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
        # Debug: Print buffer size every 2 seconds
        if not hasattr(self, '_plot_debug_counter'):
            self._plot_debug_counter = 0
        self._plot_debug_counter += 1
        if self._plot_debug_counter >= 40:  # Every 2 seconds at 50ms
            self._plot_debug_counter = 0
            buf_size = len(BL.live_data_buffer)
            print(f"[Plot Debug] Buffer size: {buf_size} samples ({buf_size/512:.1f}s of data)")
        
        # -------------------------------------------------------
        # CRITICAL: Check hardware signal quality FIRST
        # If signal=200, the onRaw() gate blocks samples, making
        # buffer empty. Must check this BEFORE buffer length to
        # show "Not Worn" instead of "Device Disconnected".
        # -------------------------------------------------------
        _hw_signal = getattr(BL, 'headset_signal_quality', None)
        if _hw_signal is not None and _hw_signal >= 200:
            import time as _t
            _now = _t.time()
            # Headset is transmitting but electrode has no contact
            self._sq_displayed_noisy = True
            self._sq_noisy_reason = 'demo_signal'
            self._sq_worn_since = None
            if not getattr(self, '_sq_not_worn_since', None):
                self._sq_not_worn_since = _now
            self.info_label.setText("Headset Not Worn | Electrode contact lost - press headset firmly against forehead")
            self.info_label.setStyleSheet("color: #ef4444; font-size: 13px; padding: 8px; font-weight: 600;")
            # Reset transmission error since device IS transmitting
            self.no_data_count = 0
            if self.transmission_stopped:
                self.transmission_stopped = False
                self.transmission_error_label.setVisible(False)
                self.next_button.setEnabled(True)
            return
        
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
            import time as _t
            _now = _t.time()
            _result = assess_eeg_signal_quality(data, fs=512)
            if _result is None:
                return
            quality_score, status, details = _result

            # Asymmetric hysteresis: 3s not_worn → Noisy; 5s worn → Good.
            if status == "not_worn":
                self._sq_worn_since = None
                if not getattr(self, '_sq_not_worn_since', None):
                    self._sq_not_worn_since = _now
                if (_now - self._sq_not_worn_since) >= 3.0:
                    self._sq_displayed_noisy = True
                    self._sq_noisy_reason = details.get('not_worn_reason', 'not_worn')
            else:
                self._sq_not_worn_since = None
                if not getattr(self, '_sq_worn_since', None):
                    self._sq_worn_since = _now
                if (_now - self._sq_worn_since) >= 5.0:
                    self._sq_displayed_noisy = False
            if getattr(self, '_sq_displayed_noisy', False):
                if getattr(self, '_sq_noisy_reason', '') == 'demo_signal':
                    self.info_label.setText("Demo Signal detected | Adjust electrode contact - press headset firmly against forehead")
                    self.info_label.setStyleSheet("color: #ef4444; font-size: 13px; padding: 8px; font-weight: 600;")
                else:
                    self.info_label.setText("Signal Noisy | Headset not detected - Please wear the headset properly")
                    self.info_label.setStyleSheet("color: #f59e0b; font-size: 13px; padding: 8px; font-weight: 600;")
            else:
                self.info_label.setText("Signal quality: Good | Data flowing normally")
                self.info_label.setStyleSheet("color: #10b981; font-size: 13px; padding: 8px; font-weight: 600;")
        else:
            # No data detected - increment counter
            self.no_data_count += 1
            
            # After 20 consecutive checks (~1 second at 50ms intervals), show error
            if self.no_data_count >= 20 and not self.transmission_stopped:
                self.transmission_stopped = True
                self.transmission_error_label.setText(
                    "Warning: TRANSMISSION STOPPED\n\n"
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
            self.info_label.setText("No signal detected | Device may be disconnected")
            self.info_label.setStyleSheet("color: #ef4444; font-size: 13px; padding: 8px;")
    
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
        """Proceed to calibration"""
        self.update_timer.stop()
        self._programmatic_close = True
        self.close()
        self.workflow.go_to_step(WorkflowStep.CALIBRATION)
    
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
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: 700;")
        
        subtitle_label = QLabel("Step 7 of 9: Establish your baseline brain activity")
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
        self.eo_button.setVisible(False)
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
        """Update signal quality indicator - exact same logic as LiveEEGDialog.update_plot()."""
        import time as _time
        try:
            # -------------------------------------------------------
            # CRITICAL: Check hardware signal quality FIRST
            # If signal=200, the onRaw() gate blocks samples, making
            # buffer empty. Must check this BEFORE buffer length.
            # -------------------------------------------------------
            _hw_signal = getattr(BL, 'headset_signal_quality', None)
            now = _time.time()
            if _hw_signal is not None and _hw_signal >= 200:
                # Headset is transmitting but electrode has no contact
                self._sig_displayed_noisy = True
                self._sig_noisy_reason = 'demo_signal'
                self._sig_worn_since = None
                if not self._sig_not_worn_since:
                    self._sig_not_worn_since = now
                self.signal_quality_label.setText("Demo Signal")
                self.signal_quality_label.setStyleSheet(
                    "font-size: 12px; color: #dc2626; padding: 6px; "
                    "background: #fee2e2; border-radius: 4px; font-weight: 600;"
                )
                return
            
            if len(BL.live_data_buffer) >= 512:
                data = np.array(BL.live_data_buffer[-512:])

                result = assess_eeg_signal_quality(data, fs=512)
                if result is None:
                    return
                quality_score, status, details = result

                # Asymmetric hysteresis: 3s not_worn → Noisy; 5s worn → Good.
                now = _time.time()
                if status == "not_worn":
                    self._sig_worn_since = None
                    if not self._sig_not_worn_since:
                        self._sig_not_worn_since = now
                    if (now - self._sig_not_worn_since) >= 3.0:
                        self._sig_displayed_noisy = True
                        self._sig_noisy_reason = details.get('not_worn_reason', 'not_worn')
                else:
                    self._sig_not_worn_since = None
                    if not self._sig_worn_since:
                        self._sig_worn_since = now
                    if (now - self._sig_worn_since) >= 5.0:
                        self._sig_displayed_noisy = False

                if self._sig_displayed_noisy:
                    if self._sig_noisy_reason == 'demo_signal':
                        self.signal_quality_label.setText("Demo Signal")
                        self.signal_quality_label.setStyleSheet(
                            "font-size: 12px; color: #dc2626; padding: 6px; "
                            "background: #fee2e2; border-radius: 4px; font-weight: 600;"
                        )
                    else:
                        self.signal_quality_label.setText("Signal: Noisy")
                        self.signal_quality_label.setStyleSheet(
                            "font-size: 12px; color: #d97706; padding: 6px; "
                            "background: #fef3c7; border-radius: 4px; font-weight: 600;"
                        )
                else:
                    self.signal_quality_label.setText("Signal: Good")
                    self.signal_quality_label.setStyleSheet(
                        "font-size: 12px; color: #059669; padding: 6px; "
                        "background: #d1fae5; border-radius: 4px; font-weight: 600;"
                    )
            else:
                self.signal_quality_label.setText("Signal: Waiting...")
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
        title = QLabel("Eyes Closed Baseline")
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
            "<b style='color: #dc2626;'>Warning: Important: Check your speakers/headphones are ON!</b>"
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
            import time as _time
            # -------------------------------------------------------
            # CRITICAL: Check hardware signal quality FIRST
            # -------------------------------------------------------
            _hw_signal = getattr(BL, 'headset_signal_quality', None)
            now = _time.time()
            if _hw_signal is not None and _hw_signal >= 200:
                # Headset is transmitting but electrode has no contact
                _sq_state['displayed_noisy'] = True
                _sq_state['noisy_reason'] = 'demo_signal'
                signal_label.setText("Demo Signal")
                signal_label.setStyleSheet(
                    "font-size: 13px; color: #dc2626; padding: 8px; "
                    "background: #fee2e2; border-radius: 6px; font-weight: 600;"
                )
                return
            
            if len(BL.live_data_buffer) >= 512:
                data = np.array(list(BL.live_data_buffer)[-512:])
                current_tail = tuple(data[-4:])
                if current_tail != _sq_state['last_tail']:
                    _sq_state['last_tail'] = current_tail
                    _sq_state['last_change'] = now
                elif _sq_state['last_change'] and (now - _sq_state['last_change']) > _STALE_S:
                    signal_label.setText("Signal: No Signal")
                    signal_label.setStyleSheet(
                        "font-size: 13px; color: #6b7280; padding: 8px; "
                        "background: #f3f4f6; border-radius: 6px; font-weight: 600;"
                    )
                    return
                _sq_res = assess_eeg_signal_quality(data, fs=512)
                if _sq_res is None:
                    return
                quality_score, status, details = _sq_res
                # Asymmetric hysteresis: 3s not_worn → Noisy; 5s worn → Good.
                if status == "not_worn":
                    _sq_state['worn_since'] = None
                    if not _sq_state['not_worn_since']:
                        _sq_state['not_worn_since'] = now
                    if (now - _sq_state['not_worn_since']) >= 3.0:
                        _sq_state['displayed_noisy'] = True
                        _sq_state['noisy_reason'] = details.get('not_worn_reason', 'not_worn')
                else:
                    _sq_state['not_worn_since'] = None
                    if not _sq_state['worn_since']:
                        _sq_state['worn_since'] = now
                    if (now - _sq_state['worn_since']) >= 5.0:
                        _sq_state['displayed_noisy'] = False
                if _sq_state['displayed_noisy']:
                    if _sq_state.get('noisy_reason') == 'demo_signal':
                        signal_label.setText("Demo Signal")
                        signal_label.setStyleSheet(
                            "font-size: 13px; color: #dc2626; padding: 8px; "
                            "background: #fee2e2; border-radius: 6px; font-weight: 600;"
                        )
                    else:
                        signal_label.setText("Signal: Noisy")
                        signal_label.setStyleSheet(
                            "font-size: 13px; color: #d97706; padding: 8px; "
                            "background: #fef3c7; border-radius: 6px; font-weight: 600;"
                        )
                else:
                    signal_label.setText("Signal: Good")
                    signal_label.setStyleSheet(
                        "font-size: 13px; color: #059669; padding: 8px; "
                        "background: #d1fae5; border-radius: 6px; font-weight: 600;"
                    )
            else:
                signal_label.setText("Signal: Waiting...")
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
        start_btn = QPushButton("Start Recording")
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
        self.status_label.setText("Countdown starting...")
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
                self.status_label.setText("Recording: Eyes Closed")
                self.phase_label.setText("Close your eyes and relax... (30 seconds)")
                self.feature_engine.start_calibration_phase('eyes_closed')
                print("[CalibrationDialog] Started eyes_closed phase")
            elif self.countdown_phase == 'eyes_open':
                self.status_label.setText("Recording: Eyes Open")
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
        title = QLabel("Eyes Open Baseline")
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
            "<b style='color: #dc2626;'>Warning: Important: Keep eyes open but stay relaxed!</b>"
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
            import time as _time
            # -------------------------------------------------------
            # CRITICAL: Check hardware signal quality FIRST
            # -------------------------------------------------------
            _hw_signal = getattr(BL, 'headset_signal_quality', None)
            now = _time.time()
            if _hw_signal is not None and _hw_signal >= 200:
                # Headset is transmitting but electrode has no contact
                _sq_state['displayed_noisy'] = True
                _sq_state['noisy_reason'] = 'demo_signal'
                signal_label.setText("Demo Signal")
                signal_label.setStyleSheet(
                    "font-size: 13px; color: #dc2626; padding: 8px; "
                    "background: #fee2e2; border-radius: 6px; font-weight: 600;"
                )
                return
            
            if len(BL.live_data_buffer) >= 512:
                data = np.array(list(BL.live_data_buffer)[-512:])
                current_tail = tuple(data[-4:])
                if current_tail != _sq_state['last_tail']:
                    _sq_state['last_tail'] = current_tail
                    _sq_state['last_change'] = now
                elif _sq_state['last_change'] and (now - _sq_state['last_change']) > _STALE_S:
                    signal_label.setText("Signal: No Signal")
                    signal_label.setStyleSheet(
                        "font-size: 13px; color: #6b7280; padding: 8px; "
                        "background: #f3f4f6; border-radius: 6px; font-weight: 600;"
                    )
                    return
                _sq_res = assess_eeg_signal_quality(data, fs=512)
                if _sq_res is None:
                    return
                quality_score, status, details = _sq_res
                # Asymmetric hysteresis: 3s not_worn → Noisy; 5s worn → Good.
                if status == "not_worn":
                    _sq_state['worn_since'] = None
                    if not _sq_state['not_worn_since']:
                        _sq_state['not_worn_since'] = now
                    if (now - _sq_state['not_worn_since']) >= 3.0:
                        _sq_state['displayed_noisy'] = True
                        _sq_state['noisy_reason'] = details.get('not_worn_reason', 'not_worn')
                else:
                    _sq_state['not_worn_since'] = None
                    if not _sq_state['worn_since']:
                        _sq_state['worn_since'] = now
                    if (now - _sq_state['worn_since']) >= 5.0:
                        _sq_state['displayed_noisy'] = False
                if _sq_state['displayed_noisy']:
                    if _sq_state.get('noisy_reason') == 'demo_signal':
                        signal_label.setText("Demo Signal")
                        signal_label.setStyleSheet(
                            "font-size: 13px; color: #dc2626; padding: 8px; "
                            "background: #fee2e2; border-radius: 6px; font-weight: 600;"
                        )
                    else:
                        signal_label.setText("Signal: Noisy")
                        signal_label.setStyleSheet(
                            "font-size: 13px; color: #d97706; padding: 8px; "
                            "background: #fef3c7; border-radius: 6px; font-weight: 600;"
                        )
                else:
                    signal_label.setText("Signal: Good")
                    signal_label.setStyleSheet(
                        "font-size: 13px; color: #059669; padding: 8px; "
                        "background: #d1fae5; border-radius: 6px; font-weight: 600;"
                    )
            else:
                signal_label.setText("Signal: Waiting...")
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
        start_btn = QPushButton("Start Recording")
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
                self.ec_button.setVisible(False)
                self.eo_button.setVisible(True)
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
                    self.phase_label.setText("Both phases complete. Baseline computed successfully.")
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
        self.setMinimumSize(550, 500)
        
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
        
        # Fall back to all tasks if filtering failed
        if not self.available_task_ids:
            self.available_task_ids = list(BL.AVAILABLE_TASKS.keys())
        
        # UI Elements
        title_label = QLabel("Cognitive Tasks")
        title_label.setObjectName("DialogTitle")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: 700;")
        
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
        # Populate with task names as display text and task IDs as data
        # Get completed tasks to disable them
        completed_tasks = self._get_completed_task_ids()
        has_booking = getattr(self.workflow.main_window, 'has_advanced_booking', False)
        
        for task_id in self.available_task_ids:
            if task_id in BL.AVAILABLE_TASKS:
                task_name = BL.AVAILABLE_TASKS[task_id].get('name', task_id)
                is_advanced = self._is_advanced_task(task_id)
                
                # Add 'Advanced' tag for non-basic tasks
                if is_advanced:
                    task_name = f"{task_name} (Advanced)"
                
                # Mark completed tasks with checkmark
                if task_id in completed_tasks:
                    display_name = f"{task_name} (Completed)"
                else:
                    display_name = task_name
                
                self.task_combo.addItem(display_name, task_id)  # Display name, store ID as data
                
                model = self.task_combo.model()
                item = model.item(self.task_combo.count() - 1)
                
                # Disable if already completed
                if task_id in completed_tasks:
                    item.setEnabled(False)
                    item.setToolTip("This task has already been completed")
                # Disable advanced tasks when no booking exists
                elif is_advanced and not has_booking:
                    item.setEnabled(False)
                    item.setToolTip(
                        "Advanced task – requires a valid booking with the partner.\n"
                        "Please ask your partner to create a session booking for you."
                    )
        
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        self.task_combo.currentIndexChanged.connect(lambda _: self.update_task_preview())
        
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
        self.task_description.setTextFormat(Qt.RichText)
        self.task_description.setStyleSheet("font-size: 13px; color: #475569;")
        
        self.start_task_button = QPushButton("Start This Task")
        self.start_task_button.clicked.connect(self.start_selected_task)
        self.start_task_button.setStyleSheet("padding: 10px; font-size: 14px; font-weight: 600;")
        
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.task_description)
        preview_layout.addWidget(self.start_task_button)
        
        # Completed tasks info
        self.completed_label = QLabel()
        self.completed_label.setStyleSheet("font-size: 12px; color: #64748b; padding: 8px;")
        self.update_completed_tasks_display()
        
        # Initial task preview update
        self.update_task_preview()
        
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
        
        self.next_button = QPushButton("Proceed to Analysis →")
        self.next_button.clicked.connect(self.on_next)
        # Hidden until 4 tasks have been completed
        completed_count = len([t for t in self.workflow.main_window.feature_engine.calibration_data.get('tasks', {}).keys() 
                               if t not in ['baseline', 'eyes_closed', 'eyes_open']])
        self.next_button.setVisible(completed_count >= 4)
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
        """Center the dialog on the screen"""
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                dialog_geometry = self.frameGeometry()
                center_point = screen_geometry.center()
                dialog_geometry.moveCenter(center_point)
                self.move(dialog_geometry.topLeft())
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
        display = display.replace("", "")
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
            desc = task_info.get('description') or "No description available."
            duration = task_info.get('duration')
            instructions = task_info.get('instructions') or ""

            is_advanced = self._is_advanced_task(task_id)
            has_booking = getattr(self.workflow.main_window, 'has_advanced_booking', False)
            is_locked = is_advanced and not has_booking
            
            preview_text = f"<b>{task_name}</b>"
            
            if is_completed:
                preview_text += " <span style='color: #10b981; font-weight: 600;'>Completed</span>"
            
            preview_text += "<br><br>"
            preview_text += f"Description: {desc}<br>"
            if duration:
                preview_text += f"Duration: ~{duration} seconds<br><br>"
            else:
                preview_text += "Duration: Not specified<br><br>"
            if instructions:
                preview_text += f"Instructions: {instructions}"
            else:
                preview_text += "Instructions: Follow the on-screen prompts to complete this task."
            
            if is_completed:
                preview_text += "<br><br><span style='color: #f59e0b; font-weight: 600;'>Warning: This task has already been completed. Please select a different task.</span>"
            elif is_locked:
                preview_text += (
                    "<br><br><span style='color: #dc2626; font-weight: 600;'>"
                    "Advanced task – requires a valid booking with the partner.<br>"
                    "Please ask your partner to create an advanced session booking for you."
                    "</span>"
                )
            
            self.task_description.setText(preview_text)
            
            # Disable start button if task is completed or locked
            can_start = not is_completed and not is_locked
            self.start_task_button.setEnabled(can_start)
            if is_completed:
                self.start_task_button.setText("Task Already Completed")
            elif is_locked:
                self.start_task_button.setText("Booking Required")
            else:
                self.start_task_button.setText("Start This Task")
        else:
            self.task_description.setText("Task information not available")
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
        
        # Block advanced tasks without a booking
        if self._is_advanced_task(task_id) and not getattr(self.workflow.main_window, 'has_advanced_booking', False):
            QMessageBox.warning(
                self,
                "Booking Required",
                f"'{BL.AVAILABLE_TASKS[task_id].get('name', task_id)}' is an advanced task.\n\n"
                "A valid session booking with the partner is required to run advanced tasks.\n"
                "Please ask your partner to create a booking for you."
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
            self.workflow.main_window.log_message(f"Started task via start_task(): {task_id}")
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
            print(f"Tasks in 'tasks' dict: {list(tasks.keys())}")
            for task_name, task_data in tasks.items():
                print(f"  {task_name}: {len(task_data.get('features', []))} features")
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
        has_booking = getattr(self.workflow.main_window, 'has_advanced_booking', False)
        
        for task_id in self.available_task_ids:
            if task_id in BL.AVAILABLE_TASKS:
                task_name = BL.AVAILABLE_TASKS[task_id].get('name', task_id)
                is_advanced = self._is_advanced_task(task_id)
                
                if is_advanced:
                    task_name = f"{task_name} (Advanced)"
                
                if task_id in completed_tasks:
                    display_name = f"{task_name} (Completed)"
                else:
                    display_name = task_name
                
                self.task_combo.addItem(display_name, task_id)
                
                model = self.task_combo.model()
                item = model.item(self.task_combo.count() - 1)
                
                if task_id in completed_tasks:
                    item.setEnabled(False)
                    item.setToolTip("This task has already been completed")
                elif is_advanced and not has_booking:
                    item.setEnabled(False)
                    item.setToolTip(
                        "Advanced task – requires a valid booking with the partner.\n"
                        "Please ask your partner to create a session booking for you."
                    )
        
        # Try to select first available (non-disabled) task
        for i in range(self.task_combo.count()):
            item = self.task_combo.model().item(i)
            if item and item.isEnabled():
                self.task_combo.setCurrentIndex(i)
                break
        
        # Unblock signals and refresh description
        self.task_combo.blockSignals(False)
        
        # Always refresh the description after rebuilding the combo
        self.update_task_preview()  # direct call — no signal arg
    
    def update_completed_tasks_display(self):
        """Update the completed tasks counter"""
        tasks_data = self.workflow.main_window.feature_engine.calibration_data.get('tasks', {})
        completed_tasks = [t for t in tasks_data.keys() if t not in ['baseline', 'eyes_closed', 'eyes_open']]
        count = len(completed_tasks)
        
        if count == 0:
            self.completed_label.setText("No tasks completed yet. Complete 4 tasks to proceed.")
        elif count < 4:
            remaining = 4 - count
            task_list = ', '.join(completed_tasks)
            self.completed_label.setText(f"{count} task{'s' if count > 1 else ''} completed: {task_list} — {remaining} more needed to proceed.")
        else:
            task_list = ', '.join(completed_tasks)
            self.completed_label.setText(f"{count} tasks completed: {task_list}")
        
        # Update proceed button state
        if hasattr(self, 'next_button'):
            self.next_button.setVisible(count >= 4)
    
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
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: 700;")

        headset_label = QLabel("You can turn off and remove the headset now.")
        headset_label.setAlignment(Qt.AlignCenter)
        headset_label.setStyleSheet("font-size: 13px; color: #555; margin-bottom: 4px;")

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
        self.report_button.setVisible(False)  # Hidden until seeding fails
        self.report_button.setStyleSheet("padding: 10px;")
        
        # Two protocol-specific seed buttons
        _waiting_tooltip = "Please wait for the analysis to complete before proceeding."
        
        self.seed_initial_button = QPushButton("Upload Result to your profile")
        self.seed_initial_button.clicked.connect(lambda: self.seed_report("initial"))
        self.seed_initial_button.setEnabled(False)
        self.seed_initial_button.setToolTip(_waiting_tooltip)
        self.seed_initial_button.setStyleSheet("""
            padding: 10px;
            background-color: #1e3a8a;
        """)
        
        self.seed_advanced_button = QPushButton("Seed Advanced Protocol")
        self.seed_advanced_button.clicked.connect(lambda: self.seed_report("advanced"))
        self.seed_advanced_button.setEnabled(False)
        self.seed_advanced_button.setToolTip(_waiting_tooltip)
        self.seed_advanced_button.setStyleSheet("""
            padding: 10px;
            background-color: #1e3a8a;
        """)
        
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
        # if "en" in BL.BACKEND_URL or "en.mindspeller" in BL.BACKEND_URL:
        selected_region = "English (en)"
        # elif "nl" in BL.BACKEND_URL or "nl.mindspeller" in BL.BACKEND_URL:
        #     selected_region = "Dutch (nl)"
        # elif "127.0.0.1" in BL.BACKEND_URL or "localhost" in BL.BACKEND_URL:
        #     selected_region = "Local"
        
        # Add informational text about the buttons with selected region
        user_data = getattr(self.workflow.main_window, 'user_data', {})
        initial_protocol = user_data.get('initial_protocol', '')
        protocol_status = "Initial Protocol (first time)" if not initial_protocol else "Advanced Protocol (follow-up)"
        
        info_text = QLabel(
            f"Generate Report: Save locally & share via superadmin panel\n"
            f"Upload result: Send directly to Mindspeller database\n"

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
        
        self.finish_button = QPushButton("Finish")
        self.finish_button.clicked.connect(self.on_finish)
        self.finish_button.setEnabled(False)
        self.finish_button.setVisible(False)  # Hidden until seeding completes
        nav_layout.addStretch()
        nav_layout.addWidget(self.finish_button)
        nav_layout.addStretch()
        
        # Layout assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(headset_label)
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
            self.workflow.main_window.log_message("Disconnecting headset for analysis...")
            
            # Stop the BrainLink thread
            BL.stop_thread_flag = True
            
            # Close serial connection if it exists
            if hasattr(self.workflow.main_window, 'serial_obj') and self.workflow.main_window.serial_obj:
                try:
                    self.workflow.main_window.serial_obj.close()
                    self.workflow.main_window.log_message("Serial connection closed")
                except Exception as e:
                    self.workflow.main_window.log_message(f"Warning: Error closing serial: {e}")
            
            # Wait for thread to stop
            if hasattr(self.workflow.main_window, 'brainlink_thread') and self.workflow.main_window.brainlink_thread:
                if self.workflow.main_window.brainlink_thread.is_alive():
                    self.workflow.main_window.brainlink_thread.join(timeout=2.0)
                    if self.workflow.main_window.brainlink_thread.is_alive():
                        self.workflow.main_window.log_message("Warning: Thread did not stop cleanly")
                    else:
                        self.workflow.main_window.log_message("Data streaming stopped")
            
            self.workflow.main_window.log_message("Headset disconnected successfully")
        except Exception as e:
            self.workflow.main_window.log_message(f"Error disconnecting headset: {e}")
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
            " Computing baseline statistics...\n"
            " Preparing task comparisons...\n\n"
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
                    f"Permutation testing: {current:,}/{total:,} ({progress_pct}%)\n\n"
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
                
                print(f"\n>>> [WORKER THREAD] analyze_all_tasks_data() RETURNED <<<\n")
                print(f"Results type: {type(results)}")
                if isinstance(results, dict):
                    print(f"Results keys: {list(results.keys())}")
                    print(f"engine.multi_task_results is now: {hasattr(engine, 'multi_task_results')}")
                
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
        """Display the analysis results from multi_task_results"""
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
                    
                    results += f"\n{task_name}:\n"
                    results += f"  Fisher KM p-value: {fisher.get('km_p', 'N/A')}\n"
                    results += f"  Fisher significant: {fisher.get('significant', False)}\n"
                    results += f"  SumP p-value: {sum_p.get('perm_p', 'N/A')}\n"
                    results += f"  SumP significant: {sum_p.get('significant', False)}\n"
                    results += f"  Significant features: {feature_sel.get('sig_feature_count', 0)}\n"
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
            results += "Analysis complete! Click the Seed button to submit your results.\n"
            
            print(f">>> [MAIN THREAD] Setting results text (length: {len(results)} chars) <<<")
            self.results_text.setPlainText(results)
            print(f">>> [MAIN THREAD] Enabling seed buttons and finish button <<<")
            
            # Enable the visible seed button based on protocol status and highlight it bright blue
            seed_button_style = """
                padding: 10px;
                background-color: #2563eb;
                font-weight: 600;
            """
            if self.seed_initial_button.isVisible():
                self.seed_initial_button.setEnabled(True)
                self.seed_initial_button.setToolTip("")
                self.seed_initial_button.setStyleSheet(seed_button_style)
            if self.seed_advanced_button.isVisible():
                self.seed_advanced_button.setEnabled(True)
                self.seed_advanced_button.setToolTip("")
                self.seed_advanced_button.setStyleSheet(seed_button_style)
            
            # Play completion beep sequence
            for i in range(3):
                QTimer.singleShot(i * 250, lambda: play_beep(1000, 200))
            
            # analyze_button stays disabled permanently after successful analysis
            print(f">>> [MAIN THREAD] Results displayed successfully <<<")
        else:
            print(f">>> [MAIN THREAD] No results found - showing error message <<<")
            self.results_text.setPlainText("No analysis results found.\n\nPlease ensure tasks have been recorded and try analyzing again.")
            # Allow retry only when no results were found
            self.analyze_button.setEnabled(True)
        
        print(f">>> [MAIN THREAD] _display_results() COMPLETE <<<\n")
    
    @QtCore.Slot(str)
    def _show_error_callback(self, error_msg):
        """Show error message in UI (called from main thread)"""
        print(f">>> [MAIN THREAD] _show_error_callback() CALLED <<<")
        self.results_text.setPlainText(f"Error during analysis:\n{error_msg}\n\nSee console for details.")
        self.analyze_button.setEnabled(True)  # Allow retry on error
    
    def _generate_report_text(self):
        """Generate report text internally (without triggering download)"""
        engine = self.workflow.main_window.feature_engine
        
        # Generate the report text using the feature engine
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("MULTI-TASK EEG ANALYSIS REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Add results from multi_task_results
        for task_name, results in engine.multi_task_results.items():
            report_lines.append(f"\n{'='*60}")
            report_lines.append(f"Task: {task_name}")
            report_lines.append(f"{'='*60}")
            
            if isinstance(results, dict):
                for key, value in results.items():
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
            partner_id = "PARTNER_000001"  # Default fallback
        
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
                success_dialog.setWindowTitle("Report Seeded Successfully")
                success_dialog.setIcon(QMessageBox.Information)
                
                success_message = (
                    " Your EEG report has been successfully sent to the Mindspeller database!\n\n"
                    "Report Details:\n"
                    f"• User ID: {result.get('user_id', 'N/A')}\n"
                    f"• Session ID: {result.get('session_id', 'N/A')}\n"
                    f"• Report ID: {result.get('report_id', 'N/A')}\n\n"
                    "Your neuroprofiling report is now available in your Mindspeller account.\n"
                    "You can access it immediately at mindspeller.com\n"
                    "You can safely close this application now.\n\n"
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
                        f"Report seeded successfully! User ID: {result.get('user_id')}, "
                        f"Session ID: {result.get('session_id')}, Report ID: {result.get('report_id')}"
                    )
                except:
                    pass
                
                # Enable Finish button now that seeding succeeded
                self.finish_button.setVisible(True)
                self.finish_button.setEnabled(True)
                self.finish_button.setMinimumWidth(200)
                
            else:
                error_msg = response.json().get('error', 'Unknown error') if response.content else 'Unknown error'
                self.report_button.setVisible(True)
                self.report_button.setEnabled(True)
                QMessageBox.warning(
                    self,
                    "Seeding Failed",
                    f"Failed to seed report.\n\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {error_msg}\n\n"
                    f"You can use 'Generate Report' to save the report locally."
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
            self.report_button.setVisible(True)
            self.report_button.setEnabled(True)
            QMessageBox.critical(
                self,
                "Network Error",
                error_msg + "\n\nYou can use 'Generate Report' to save the report locally."
            )
        except Exception as e:
            # Ensure progress dialog is closed on error - use hide + deleteLater
            progress.hide()
            progress.close()
            progress.deleteLater()
            QtWidgets.QApplication.processEvents()
            self.report_button.setVisible(True)
            self.report_button.setEnabled(True)
            QMessageBox.critical(
                self,
                "Error",
                f"Unexpected error while seeding report:\n{str(e)}\n\nYou can use 'Generate Report' to save the report locally."
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
        # Whether the current user has a valid advanced-session booking with the partner
        self.has_advanced_booking = False
        
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
    
    def start_workflow(self):
        """Begin the sequential workflow"""
        # OS is always Windows by default
        self.user_os = "Windows"
        # Partner ID defaults to PARTNER_000001
        self.partner_id = "PARTNER_000001"
        # Protocol defaults to Personal Pathway
        self._selected_protocol = "Personal Pathway"
        try:
            self._apply_protocol_filter()
        except Exception:
            pass
        self.workflow.go_to_step(WorkflowStep.ENVIRONMENT_SELECTION)
    
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
