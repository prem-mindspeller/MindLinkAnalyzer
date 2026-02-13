#!/usr/bin/env python3
"""
Enhanced MindLink Feature Analysis GUI
Implements targeted recommendations with the following changes:
- Eyes-closed-only baseline protocol for calibration
- Blink/ocular artifact-aware baseline window rejection
- Spectral normalization hooks (configurable)
- Per-feature significance via Welch's t-test (no Mann-Whitney)
- P-value summation composite score across features
- Cosine similarity between baseline and task feature vectors

This module subclasses the original GUI to minimize intrusive changes.
"""
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
import threading
import argparse
import copy
import json
import math
import os
import platform
import sys  # Needed for QApplication argv usage and reliability
import threading
import time
import weakref

try:
    from utils.led_stimulator import LEDStimulatorController as _LEDStimulatorController
except ImportError:
    _LEDStimulatorController = None  # pyserial / module not available

_QT_PLATFORM_ALIASES = {
    "windows": "windows",
    "win32": "windows",
    "win": "windows",
    "darwin": "cocoa",
    "macos": "cocoa",
    "mac": "cocoa",
    "linux": "xcb",
    "linux2": "xcb",
}


def _qt_platform_key(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return _QT_PLATFORM_ALIASES.get(name.strip().lower())

import numpy as np
import pandas as pd
def _set_qt_plugin_path(path: str) -> None:
    if not path:
        return
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = path


# When running from a PyInstaller bundle, prefer the bundled plugin path first
_frozen_root = getattr(sys, '_MEIPASS', None)
if _frozen_root:
    _plugins_dir = os.path.join(_frozen_root, 'PySide6', 'plugins')
    if os.path.isdir(_plugins_dir):
        _set_qt_plugin_path(os.path.join(_plugins_dir, 'platforms'))
        os.environ.setdefault('QT_PLUGIN_PATH', _plugins_dir)

# If still not set, fallback to site-packages (development environment)
if not os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH'):
    try:
        import PySide6, os as _os2  # noqa: F401
        _pyside_dir = os.path.dirname(PySide6.__file__)
        _plat = os.path.join(_pyside_dir, 'plugins', 'platforms')
        _set_qt_plugin_path(_plat)
    except Exception:
        pass
# Final safety: only keep the path if it exists; otherwise unset to let Qt search defaults
_cur = os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH')
if _cur and not os.path.isdir(_cur):
    os.environ.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
# Prefer a platform plugin that matches the host OS when none provided
if not os.environ.get('QT_QPA_PLATFORM'):
    _host_qt_platform = _qt_platform_key(platform.system())
    if _host_qt_platform:
        os.environ['QT_QPA_PLATFORM'] = _host_qt_platform
# Select a usable Qt binding and configure pyqtgraph accordingly


def _dbg(message: str) -> None:
    """Lightweight conditional debug logger for import/setup steps."""
    if os.environ.get("BL_DEBUG_IMPORTS", "0").lower() in {"1", "true", "yes"}:
        print(f"[BrainLinkAnalyzer Enhanced] {message}")

# If plugin path still unset after importing binding, attempt dynamic discovery
try:
    # Secondary dynamic resolution only if path still unset (development run, not frozen)
    if platform.system() == 'Windows' and not os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH'):
        from PySide6 import QtCore as _QtCoreTmp  # type: ignore
        dyn_plugins = _QtCoreTmp.QLibraryInfo.location(_QtCoreTmp.QLibraryInfo.PluginsPath)
        plat_dir = os.path.join(dyn_plugins, 'platforms')
        if os.path.isdir(plat_dir):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plat_dir
except Exception:
    pass

# Import pyqtgraph after setting the env var; use its Qt shim for widgets/core
_dbg("import pyqtgraph")
import pyqtgraph as pg
_dbg("import pyqtgraph.Qt")
from pyqtgraph.Qt import QtCore, QtWidgets
_dbg("import PySide6.QtGui QPixmap")
from PySide6.QtGui import QPixmap, QIcon, QFont, QPalette, QColor
from PySide6 import QtGui  # For QAction and other GUI components
from PySide6.QtCore import QUrl  # Needed for video source handling
_dbg("setup multimedia lazy loader")
# Allow disabling QtMultimedia via env if native crashes persist (set BL_DISABLE_QT_MULTIMEDIA=1)
DISABLE_QT_MULTIMEDIA = os.environ.get("BL_DISABLE_QT_MULTIMEDIA", "0") in ("1", "true", "True")
FROZEN_BUILD = bool(getattr(sys, 'frozen', False))
# Attempt to reduce ffmpeg / codec related crashes (entrypoint errors) by disabling bundled ffmpeg if problematic
os.environ.setdefault("PYSIDE_DISABLE_INTERNAL_FFMPEG", "1")
# Optional verbose plugin diagnostics if user sets BL_QT_DEBUG_PLUGINS=1
if os.environ.get("BL_QT_DEBUG_PLUGINS") in ("1","true","True"):
    os.environ.setdefault("QT_DEBUG_PLUGINS", "1")
_MULTIMEDIA_AVAILABLE = False
QMediaPlayer = QAudioOutput = QMediaSource = QVideoWidget = None  # type: ignore
def _lazy_import_multimedia():
    global _MULTIMEDIA_AVAILABLE, QMediaPlayer, QAudioOutput, QMediaSource, QVideoWidget
    if DISABLE_QT_MULTIMEDIA:
        _dbg("QtMultimedia disabled via env flag")
        return False
    if _MULTIMEDIA_AVAILABLE or QMediaPlayer is not None:
        return _MULTIMEDIA_AVAILABLE
    try:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP, QAudioOutput as _QAO, QMediaSource as _QMS  # type: ignore
        from PySide6.QtMultimediaWidgets import QVideoWidget as _QVW  # type: ignore
        QMediaPlayer, QAudioOutput, QMediaSource, QVideoWidget = _QMP, _QAO, _QMS, _QVW
        _MULTIMEDIA_AVAILABLE = True
        _dbg("multimedia loaded lazily")
    except Exception as e:
        _dbg(f"multimedia lazy load failed: {e}")
        _MULTIMEDIA_AVAILABLE = False
    return _MULTIMEDIA_AVAILABLE

def _allow_embedded_video() -> bool:
    """Decide if we should embed video using QtMultimedia.
    Conservative default: disable embedding everywhere to avoid native codec/driver crashes.
    Set BL_FORCE_EMBED_VIDEO=1 to opt in; BL_FORCE_NO_VIDEO always disables.
    """
    if os.environ.get('BL_FORCE_NO_VIDEO') in ('1','true','True'):
        return False
    # If the user opts in explicitly, allow embedding even in packaged builds
    if os.environ.get('BL_FORCE_EMBED_VIDEO') in ('1','true','True'):
        return True
    # Default: do not embed
    return False
try:
    # Optional: enable painter antialiasing at widget level
    from pyqtgraph.Qt import QtGui as _QtGui
except Exception:
    _QtGui = None

# Hard-set pyqtgraph visibility and performance options to match the stable legacy setup
try:
    pg.setConfigOption('useOpenGL', False)
    pg.setConfigOption('antialias', True)
    pg.setConfigOption('background', 'k')   # black background
    pg.setConfigOption('foreground', 'w')   # white axes/text
    pg.setConfigOption('crashWarning', True)
    pg.setConfigOption('imageAxisOrder', 'row-major')
except Exception:
    pass

# Optional SciPy stats import; fall back to lightweight implementations if unavailable
try:
    from scipy.stats import (
        ttest_ind as _scipy_ttest_ind,  # type: ignore
        chi2 as _scipy_chi2,  # type: ignore
        friedmanchisquare as _scipy_friedman,  # type: ignore
        f_oneway as _scipy_f_oneway,  # type: ignore
        wilcoxon as _scipy_wilcoxon,  # type: ignore,
    )
except Exception:
    _scipy_ttest_ind = None
    _scipy_chi2 = None
    _scipy_friedman = None
    _scipy_f_oneway = None
    _scipy_wilcoxon = None

try:  # SciPy >= 1.7
    from scipy.stats import binomtest as _scipy_binomtest  # type: ignore
except Exception:
    try:  # Deprecated alias (SciPy < 1.7)
        from scipy.stats import binom_test as _scipy_binom_test_old  # type: ignore

        class _LegacyBinomTestWrapper:
            def __init__(self, successes: int, trials: int, prob: float = 0.5):
                self.pvalue = float(_scipy_binom_test_old(successes, trials, prob))

        def _scipy_binomtest(successes: int, trials: int, prob: float = 0.5):
            return _LegacyBinomTestWrapper(successes, trials, prob)

    except Exception:
        _scipy_binomtest = None

# Import original application as a module
_dbg("import base GUI BL")
import BrainLinkAnalyzer_GUI as BL
_dbg("base GUI imported")


BOOL_TRUE = {"1", "true", "yes", "on", "y", "t"}
MODE_CHOICES = ("aggregate_only", "feature_selection")
DEPENDENCE_CORRECTION_CHOICES = ("Kost-McDermott", "none")
EXPORT_PROFILE_CHOICES = ("full", "integer_only")
EFFECT_MEASURE_CHOICES = ("delta", "z")
OMNIBUS_CHOICES = ("Friedman", "RM-ANOVA")
POSTHOC_CHOICES = ("Wilcoxon",)
PERM_PRESETS = {
    "ultrafast": 50,   # Very quick, still detects p<0.02
    "fast": 100,       # Quick mode, detects p<0.01  
    "default": 200,    # Balanced speed/precision
    "strict": 500,     # Higher precision
    "research": 1000,  # Research-grade precision
}


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return str(val).strip().lower() in BOOL_TRUE


def _env_int(name: str, default: Optional[int]) -> Optional[int]:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_choice(name: str, default: str, choices: Tuple[str, ...]) -> str:
    val = os.environ.get(name)
    if not val:
        return default
    val_clean = val.strip()
    if val_clean in choices:
        return val_clean
    val_lower = val_clean.lower()
    for opt in choices:
        if opt.lower() == val_lower:
            return opt
    return default


@dataclass
class EnhancedAnalyzerConfig:
    alpha: float = 0.05
    mode: str = "aggregate_only"
    dependence_correction: str = "Kost-McDermott"
    use_permutation_for_sumP: bool = True
    # n_perm=1000 gives p-value resolution of 0.001, sufficient after Holm-Bonferroni across 5 tasks
    # At block-level permutation (~15-22 labels), 1000 perms takes <10 seconds per task
    n_perm: int = 1000  # Standard mode; use n_perm=100 only for fast/preview mode
    n_perm_fast: int = 100  # Fast mode permutation count (coarser p-value resolution)
    discretization_bins: int = 5
    export_profile: str = "full"
    effect_measure: str = "delta"
    omnibus: str = "Friedman"
    posthoc: str = "Wilcoxon"
    fdr_alpha: float = 0.05
    seed: Optional[int] = None
    runtime_preset: Optional[str] = None
    min_effect_size: float = 0.5
    min_percent_change: float = 10.0
    correlation_guard: bool = True
    # Newly configurable analysis parameters
    block_seconds: float = 4.0  # Reduced from 8.0 for ~2x more blocks -> better power
    mt_tapers: int = 3
    # Fast analysis mode: skip permutation testing entirely, use only parametric tests
    fast_mode: bool = True  # If True, uses only Welch's t-test + FDR (no permutation)
    nmin_sessions: int = 2  # Minimum 2 sessions needed for statistical comparison
    # Sample size requirements for stable effect size estimates
    min_blocks_per_condition: int = 8  # Minimum blocks for acceptable power
    bootstrap_ci_samples: int = 1000  # Bootstrap iterations for confidence intervals
    compute_bootstrap_ci: bool = True  # Whether to compute 95% CIs for Cohen's d
    # Line noise filtering (50Hz EU / 60Hz US)
    line_noise_freq: float = 60.0  # Mains frequency (50.0 for EU/Asia, 60.0 for Americas)
    apply_notch_filter: bool = True  # Apply notch filter at line_noise_freq and harmonics
    # Adaptive EMG threshold (self-calibrating per session)
    emg_adaptive_threshold: bool = True  # Use baseline-adaptive threshold instead of fixed 1.5
    emg_fixed_ratio: float = 1.5  # Fallback fixed ratio if adaptive fails
    
    # Performance note: Permutation testing is optimized with:
    # 1. Vectorized Welch t-test (5-10x faster than looping)
    # 2. Throttled progress callbacks (reduces overhead)
    # 3. Pre-allocated arrays (minimizes memory allocation)
    # Typical performance: ~1000 permutations/second for 50 features

    def __post_init__(self) -> None:
        self.mode = self.mode if self.mode in MODE_CHOICES else MODE_CHOICES[0]
        if self.dependence_correction not in DEPENDENCE_CORRECTION_CHOICES:
            self.dependence_correction = DEPENDENCE_CORRECTION_CHOICES[0]
        if self.export_profile not in EXPORT_PROFILE_CHOICES:
            self.export_profile = EXPORT_PROFILE_CHOICES[0]
        if self.effect_measure not in EFFECT_MEASURE_CHOICES:
            self.effect_measure = EFFECT_MEASURE_CHOICES[0]
        if self.omnibus not in OMNIBUS_CHOICES:
            self.omnibus = OMNIBUS_CHOICES[0]
        if self.posthoc not in POSTHOC_CHOICES:
            self.posthoc = POSTHOC_CHOICES[0]
        if self.runtime_preset and self.runtime_preset not in PERM_PRESETS:
            self.runtime_preset = None
        if self.runtime_preset:
            self.n_perm = PERM_PRESETS[self.runtime_preset]
        self.alpha = float(self.alpha)
        self.fdr_alpha = float(self.fdr_alpha)
        self.discretization_bins = max(2, int(self.discretization_bins))
        self.n_perm = max(1, int(self.n_perm))
        self.min_effect_size = max(0.0, float(self.min_effect_size))
        self.min_percent_change = max(0.0, float(self.min_percent_change))
        self.correlation_guard = bool(self.correlation_guard)
        # Coerce and validate newly added parameters
        try:
            self.block_seconds = float(self.block_seconds)
            if self.block_seconds <= 0:
                self.block_seconds = 8.0
        except Exception:
            self.block_seconds = 8.0
        try:
            self.mt_tapers = int(self.mt_tapers)
            if self.mt_tapers < 1:
                self.mt_tapers = 1
        except Exception:
            self.mt_tapers = 3
        try:
            self.nmin_sessions = int(self.nmin_sessions)
            if self.nmin_sessions < 2:
                self.nmin_sessions = 2
        except Exception:
            self.nmin_sessions = 2  # Minimum needed for statistical comparison

    @property
    def is_feature_selection(self) -> bool:
        return self.mode == "feature_selection"

    @classmethod
    def from_sources(cls, argv: Optional[List[str]] = None) -> "EnhancedAnalyzerConfig":
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--alpha", type=float, default=None)
        parser.add_argument("--mode", choices=MODE_CHOICES, default=None)
        parser.add_argument("--dependence-correction", choices=DEPENDENCE_CORRECTION_CHOICES, default=None)
        parser.add_argument("--sumP-permutations", dest="use_perm", action="store_true")
        parser.add_argument("--no-sumP-permutations", dest="use_perm", action="store_false")
        parser.set_defaults(use_perm=None)
        parser.add_argument("--n-perm", type=int, default=None)
        parser.add_argument("--discretization-bins", type=int, default=None)
        parser.add_argument("--export-profile", choices=EXPORT_PROFILE_CHOICES, default=None)
        parser.add_argument("--effect-measure", choices=EFFECT_MEASURE_CHOICES, default=None)
        parser.add_argument("--omnibus", choices=OMNIBUS_CHOICES, default=None)
        parser.add_argument("--posthoc", choices=POSTHOC_CHOICES, default=None)
        parser.add_argument("--fdr-alpha", type=float, default=None)
        parser.add_argument("--seed", type=int, default=None)
        parser.add_argument("--perm-preset", choices=tuple(PERM_PRESETS.keys()), default=None)
        parser.add_argument("--min-effect-size", type=float, default=None)
        parser.add_argument("--min-percent-change", type=float, default=None)
        parser.add_argument("--correlation-guard", dest="corr_guard", action="store_true")
        parser.add_argument("--no-correlation-guard", dest="corr_guard", action="store_false")
        parser.set_defaults(corr_guard=None)
        # Newly added CLI options
        parser.add_argument("--block-seconds", type=float, default=None, help="Seconds per analysis block for block-based stats")
        parser.add_argument("--mt-tapers", type=int, default=None, help="Number of DPSS tapers for multitaper PSD")
        parser.add_argument("--nmin-sessions", type=int, default=None, help="Minimum sessions required to enable across-task significance tests")
        parser.add_argument("--config-help", action="help", help="Show configuration options and exit")

        parsed, _ = parser.parse_known_args(argv or [])

        env_alpha = _env_float("BL_ALPHA", 0.05)
        env_mode = _env_choice("BL_MODE", MODE_CHOICES[0], MODE_CHOICES)
        env_dep = _env_choice("BL_DEPENDENCE_CORRECTION", DEPENDENCE_CORRECTION_CHOICES[0], DEPENDENCE_CORRECTION_CHOICES)
        env_use_perm = os.environ.get("BL_USE_PERMUTATION_FOR_SUMP")
        env_perm_flag = None
        if env_use_perm is not None:
            env_perm_flag = _env_bool("BL_USE_PERMUTATION_FOR_SUMP", True)
        env_n_perm = _env_int("BL_N_PERM", None)
        env_bins = _env_int("BL_DISCRETIZATION_BINS", None)
        env_export = _env_choice("BL_EXPORT_PROFILE", EXPORT_PROFILE_CHOICES[0], EXPORT_PROFILE_CHOICES)
        env_effect = _env_choice("BL_EFFECT_MEASURE", EFFECT_MEASURE_CHOICES[0], EFFECT_MEASURE_CHOICES)
        env_omnibus = _env_choice("BL_OMNIBUS", OMNIBUS_CHOICES[0], OMNIBUS_CHOICES)
        env_posthoc = _env_choice("BL_POSTHOC", POSTHOC_CHOICES[0], POSTHOC_CHOICES)
        env_fdr_alpha = _env_float("BL_FDR_ALPHA", 0.05)
        env_seed = _env_int("BL_RANDOM_SEED", None)
        env_preset = os.environ.get("BL_PERM_PRESET")
        if env_preset and env_preset not in PERM_PRESETS:
            env_preset = None
        env_min_effect = _env_float("BL_MIN_EFFECT_SIZE", 0.5)
        env_min_pct = _env_float("BL_MIN_PERCENT_CHANGE", 10.0)
        env_corr_guard = _env_bool("BL_CORRELATION_GUARD", True)
        # Newly added environment overrides
        env_block_seconds = _env_float("BL_BLOCK_SECONDS", None)
        env_mt_tapers = _env_int("BL_MT_TAPERS", None)
        env_nmin_sessions = _env_int("BL_NMIN_SESSIONS", None)

        n_perm_value = None
        if parsed.n_perm is not None:
            n_perm_value = parsed.n_perm
        elif env_n_perm is not None:
            n_perm_value = env_n_perm
        else:
            n_perm_value = PERM_PRESETS.get(parsed.perm_preset or env_preset or "", 1000)

        use_perm_value = parsed.use_perm if parsed.use_perm is not None else (env_perm_flag if env_perm_flag is not None else True)

        cfg = cls(
            alpha=parsed.alpha if parsed.alpha is not None else env_alpha,
            mode=parsed.mode or env_mode,
            dependence_correction=parsed.dependence_correction or env_dep,
            use_permutation_for_sumP=use_perm_value,
            n_perm=n_perm_value,
            discretization_bins=parsed.discretization_bins or env_bins or 5,
            export_profile=parsed.export_profile or env_export,
            effect_measure=parsed.effect_measure or env_effect,
            omnibus=parsed.omnibus or env_omnibus,
            posthoc=parsed.posthoc or env_posthoc,
            fdr_alpha=parsed.fdr_alpha if parsed.fdr_alpha is not None else env_fdr_alpha,
            seed=parsed.seed if parsed.seed is not None else env_seed,
            runtime_preset=parsed.perm_preset or env_preset,
            min_effect_size=parsed.min_effect_size if parsed.min_effect_size is not None else env_min_effect,
            min_percent_change=parsed.min_percent_change if parsed.min_percent_change is not None else env_min_pct,
            correlation_guard=parsed.corr_guard if parsed.corr_guard is not None else env_corr_guard,
            block_seconds=(parsed.block_seconds if parsed.block_seconds is not None else (env_block_seconds if env_block_seconds is not None else 8.0)),
            mt_tapers=(parsed.mt_tapers if parsed.mt_tapers is not None else (env_mt_tapers if env_mt_tapers is not None else 3)),
            nmin_sessions=(parsed.nmin_sessions if parsed.nmin_sessions is not None else (env_nmin_sessions if env_nmin_sessions is not None else 2)),
        )
        return cfg


# Binding-agnostic Qt references via pyqtgraph's shim
QDialog = QtWidgets.QDialog
QLabel = QtWidgets.QLabel
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QPushButton = QtWidgets.QPushButton
QTextEdit = QtWidgets.QTextEdit
QWidget = QtWidgets.QWidget
Qt = QtCore.Qt
QTimer = QtCore.QTimer


class CrosshairDialog(QDialog):
    """Instructional cue dialog (kept minimal; not used for EC)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fixation Cross - Keep Eyes Open and Relaxed")
        self.setModal(False)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        layout = QVBoxLayout(self)
        label = QLabel("+", self)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font: 72pt 'Arial'; color: #FF3333;")
        layout.addWidget(label)
        self.setMinimumSize(200, 200)


class EnhancedFeatureAnalysisEngine(BL.FeatureAnalysisEngine):
    def __init__(
        self,
        normalization_method: str = 'snr_based',
        blink_sigma: float = 3.0,
        config: Optional[EnhancedAnalyzerConfig] = None,
    ):
        super().__init__()
        self.config = config or EnhancedAnalyzerConfig()
        # Configuration
        self.normalization_method = normalization_method
        self.blink_sigma = blink_sigma
        # Block-based analysis defaults
        self.block_seconds = getattr(self.config, 'block_seconds', 8.0)
        self.nmin_sessions = getattr(self.config, 'nmin_sessions', 2)
        self.mt_tapers = getattr(self.config, 'mt_tapers', 3)
        # Mains frequency heuristic (Windows: 60Hz, others default 50Hz)
        try:
            self.mains_hz = 60.0 if platform.system() == 'Windows' else 50.0
        except Exception:
            self.mains_hz = 50.0
        # Prefer 2-second windows for processing
        try:
            if hasattr(self, 'window_seconds'):
                self.window_seconds = 2.0
            if hasattr(self, 'fs') and hasattr(self, 'window_samples'):
                self.window_samples = int(self.fs * getattr(self, 'window_seconds', 2.0))
            # Recompute step size if overlap fields are available
            if hasattr(self, 'window_overlap') and hasattr(self, 'window_samples') and hasattr(self, 'step_samples'):
                self.step_samples = max(1, int(self.window_samples * (1.0 - float(self.window_overlap))))
        except Exception:
            pass
        # Buffers for blink detection statistics over recent raw samples
        self.recent_window_envelopes = deque(maxlen=60)
        # Per-task storage in addition to aggregate 'task'
        if 'tasks' not in self.calibration_data:
            self.calibration_data['tasks'] = {}
        # Diagnostics counters for EC windows
        self.baseline_kept = 0
        self.baseline_rejected = 0
        # Gamma EMG guard statistics
        self.gamma_windows_total = 0
        self.gamma_windows_kept = 0
        # Permutation and correlation caches
        self._perm_index_cache: Dict[Tuple[str, int, int, int], np.ndarray] = {}
        self._cached_corr_matrices: Dict[Tuple[Any, ...], np.ndarray] = {}
        self._cached_block_summaries: Dict[Tuple[str, int, float], Any] = {}
        self._cached_block_corr: Dict[Tuple[str, Tuple[str, ...], int, float], np.ndarray] = {}
        self.last_export_full: Dict[str, Any] = {}
        self.last_export_integer: Dict[str, Any] = {}
        # Cancellation / progress hooks for long-running permutation tasks
        self._perm_cancelled = False
        self._perm_progress_callback = None  # Callable[[int, int], None]
        # General (non-permutation) multi-task analysis progress callback
        self._general_progress_callback = None  # Callable[[int, int], None]
        # Feature-level progress callback for fine-grained task analysis updates
        self._feature_progress_callback = None  # Callable[[str, int, int], None] -> (task_name, processed_features, total_features)
        # Overall single-task analysis cancellation flag
        self._analysis_cancelled = False

    # Cancellation / progress API
    def cancel_permutations(self) -> None:
        """Signal cancellation for any in-flight permutation computations."""
        self._perm_cancelled = True

    def reset_permutation_cancel(self) -> None:
        """Reset the cancellation flag before starting a new permutation run."""
        self._perm_cancelled = False

    def set_permutation_progress_callback(self, cb) -> None:
        """Set a progress callback function accepting (completed_perms, total_perms)."""
        self._perm_progress_callback = cb

    def clear_permutation_progress_callback(self) -> None:
        self._perm_progress_callback = None

    def set_general_progress_callback(self, cb) -> None:
        """Set a general progress callback for per-task analysis phase.

        Callback receives (completed_steps, total_steps) where total_steps = number of per-task analyses + 1 (combined).
        """
        self._general_progress_callback = cb

    def clear_general_progress_callback(self) -> None:
        self._general_progress_callback = None

    def set_feature_progress_callback(self, cb) -> None:
        """Set fine-grained per-feature progress callback.

        Callback signature: (task_name: str, processed_features: int, total_features: int).
        Emitted from analyze_task_data for each active task (including combined).
        """
        self._feature_progress_callback = cb

    def clear_feature_progress_callback(self) -> None:
        self._feature_progress_callback = None

    # --- Analysis-wide cancellation (features + permutations) ---
    def cancel_analysis(self) -> None:
        """Cancel the current analysis (features + permutations)."""
        self._analysis_cancelled = True
        self.cancel_permutations()

    def reset_analysis_cancel(self) -> None:
        self._analysis_cancelled = False

    # --- Minimal statistical helpers (SciPy optional) ---
    @staticmethod
    def _welch_ttest(x: np.ndarray, y: np.ndarray):
        """Return (t_stat, p_value) for Welch's t-test.
        Uses SciPy if available; otherwise a conservative normal approximation.
        Guard against zero-variance degenerate cases to avoid spurious tiny p-values.
        """
        # Prefer SciPy if present
        if _scipy_ttest_ind is not None:
            try:
                res = _scipy_ttest_ind(x, y, equal_var=False)
                # Ensure consistent (t_stat, p_val) tuple
                return float(res.statistic), float(res.pvalue)
            except Exception:
                pass
        # Fallback: compute t-stat and p-value using normal approximation (reasonable for df>30)
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        nx = max(1, x.size)
        ny = max(1, y.size)
        mx = float(np.mean(x))
        my = float(np.mean(y))
        vx = float(np.var(x, ddof=1)) if nx > 1 else 0.0
        vy = float(np.var(y, ddof=1)) if ny > 1 else 0.0
        # If both groups have (near) zero variance, treat as non-testable (p=1.0)
        if vx <= 1e-15 and vy <= 1e-15:
            return 0.0, 1.0
        denom = float(np.sqrt((vx / max(nx, 1)) + (vy / max(ny, 1))))
        if denom <= 1e-15:
            # Degenerate denominator; avoid artificially inflating t
            return 0.0, 1.0
        t_stat = (mx - my) / denom
        # Welch–Satterthwaite df
        with np.errstate(divide='ignore', invalid='ignore'):
            num = (vx / nx + vy / ny) ** 2
            den = ((vx**2) / (nx**2 * max(nx - 1, 1))) + ((vy**2) / (ny**2 * max(ny - 1, 1)))
            df = float(num / den) if den > 0 else float(nx + ny - 2)
        # Two-tailed normal approximation for p-value
        try:
            from math import erfc, sqrt
            z = abs(t_stat)
            p = float(erfc(z / sqrt(2.0)))  # 2*(1-Phi(|z|))
        except Exception:
            p = 1.0
        return t_stat, p

    @staticmethod
    def _chi2_sf(stat: float, df: int) -> float:
        """Survival function (1-CDF) for chi-square. Uses SciPy if available; else normal approx."""
        if _scipy_chi2 is not None:
            try:
                return float(_scipy_chi2.sf(stat, df))
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

    # --- Multiple testing and p-value combination helpers ---
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

    @staticmethod
    def _bootstrap_hedges_g_ci(task_vals: np.ndarray, baseline_vals: np.ndarray, 
                                n_bootstrap: int = 1000, ci_level: float = 0.95,
                                rng: np.random.Generator = None):
        """Compute Hedges' g (Glass's delta with correction) and bootstrapped 95% CI.
        
        Uses baseline SD as reference (consistent with Welch's t-test unequal variance
        assumption). Hedges' correction factor applied for small sample bias.
        
        Returns (observed_g, ci_lower, ci_upper).
        """
        task_vals = np.asarray(task_vals, dtype=float)
        baseline_vals = np.asarray(baseline_vals, dtype=float)
        
        if task_vals.size < 2 or baseline_vals.size < 2:
            return 0.0, np.nan, np.nan
        
        def hedges_g(task, baseline):
            n_task, n_baseline = task.size, baseline.size
            m_task, m_baseline = np.mean(task), np.mean(baseline)
            # Glass's delta: use baseline SD as stable reference
            sd_baseline = np.std(baseline, ddof=1) if n_baseline > 1 else 1.0
            glass_delta = (m_task - m_baseline) / (sd_baseline + 1e-12)
            # Hedges' correction factor for small sample bias
            n_total = n_task + n_baseline
            correction = 1 - (3 / (4 * n_total - 9)) if n_total > 9 else 1.0
            return glass_delta * correction
        
        observed_g = hedges_g(task_vals, baseline_vals)
        
        if rng is None:
            rng = np.random.default_rng()
        
        boot_g = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            boot_task = rng.choice(task_vals, size=len(task_vals), replace=True)
            boot_baseline = rng.choice(baseline_vals, size=len(baseline_vals), replace=True)
            boot_g[i] = hedges_g(boot_task, boot_baseline)
        
        # Percentile method for CI
        alpha_half = (1 - ci_level) / 2
        ci_lower = float(np.percentile(boot_g, alpha_half * 100))
        ci_upper = float(np.percentile(boot_g, (1 - alpha_half) * 100))
        
        return float(observed_g), ci_lower, ci_upper
    
    # Alias for backward compatibility
    _bootstrap_cohens_d_ci = _bootstrap_hedges_g_ci

    @staticmethod
    def _fishers_method(p_values):
        """Fisher's method for combining independent p-values."""
        if not p_values:
            return None, None
        # Clip p-values to avoid log(0)
        clipped = [max(min(float(p), 1.0), 1e-300) for p in p_values]
        stat = -2.0 * float(np.sum(np.log(clipped)))
        df = 2 * len(clipped)
    # Use our chi-square survival function (SciPy if available)
        p_comb = float(EnhancedFeatureAnalysisEngine._chi2_sf(stat, df))
        return stat, p_comb

    def _km_from_corr(self, fisher_stat: float, corr: Optional[np.ndarray]) -> Tuple[float, float, float, Optional[float]]:
        """Kost–McDermott correction using a provided correlation matrix (Spearman).
        Returns (adjusted_stat, p_value, df_km, mean_offdiag_r).
        """
        if corr is None or corr.size == 0:
            k = 0
        else:
            k = corr.shape[0]
        if k <= 1:
            return fisher_stat, float(self._chi2_sf(fisher_stat, 2 * max(k, 1))), float(2 * max(k, 1)), None
        mu = 2.0 * k
        cov_sum = 0.0
        r_sum = 0.0
        r_count = 0
        for i in range(k):
            for j in range(i + 1, k):
                r = float(corr[i, j])
                r_sum += r
                r_count += 1
                cov = 3.263 * r + 0.710 * (r ** 2) + 0.027 * (r ** 3)
                cov_sum += cov
        mean_r = r_sum / r_count if r_count > 0 else 0.0
        sigma_sq = 4.0 * k + 2.0 * cov_sum
        if sigma_sq <= 0:
            return fisher_stat, float(self._chi2_sf(fisher_stat, 2 * k)), float(2 * k), mean_r
        c = sigma_sq / (2.0 * mu)
        df = max(1.0, (2.0 * (mu ** 2)) / sigma_sq)
        adjusted_stat = fisher_stat / c
        if _scipy_chi2 is not None:
            p_val = float(_scipy_chi2.sf(adjusted_stat, df))
        else:
            p_val = float(self._chi2_sf(adjusted_stat, int(round(df))))
        return adjusted_stat, p_val, df, mean_r

    # --- Expectation alignment ---
    def _evaluate_expectation_alignment(self, task_name: Optional[str]) -> Dict[str, Any]:
        """Production expectation-alignment with task-specific rules and thresholds.
        
        Returns dict with:
        - grade: A/B/C/D based on key-feature passes
        - passes: list of features that met directional expectation with p_dir/d/pct/rule
        - top_drivers: top 2-3 features by |d|
        - counter_directional: bool if ≥70% features go against expectation
        - notes: any warnings (gamma guarded, insufficient metrics)
        - insufficient_metrics: True if key features have no valid d/p_dir
        """
        results = getattr(self, 'analysis_results', {}) or {}
        expected_map = {}
        passed_features = []
        key_dir_counts = {'with': 0, 'against': 0}
        insufficient_metrics = False
        
        # Task-specific thresholds for d and %Δ (production values)
        task_thresholds = {
            'mental_math': {'alpha': 0.25, 'beta': 0.35, 'gamma': 0.30, 'pct_relative': 5.0},
            'attention_focus': {'alpha': 0.25, 'beta': 0.35, 'gamma': 0.30, 'pct_relative': 5.0},
            'visual_imagery': {'alpha': 0.30, 'gamma': 0.30, 'pct_relative': 8.0},
            'working_memory': {'theta': 0.30, 'beta': 0.35, 'alpha': 0.25, 'pct_relative': 5.0},
            'cognitive_load': {'theta': 0.30, 'alpha': 0.25, 'pct_relative': 5.0},
            'motor_imagery': {'alpha': 0.25, 'beta': 0.30, 'pct_relative': 5.0},
            'language_processing': {'alpha': 0.25, 'beta': 0.35, 'pct_relative': 5.0},
        }
        
        t = (task_name or '').lower()
        thr = task_thresholds.get(t, {'alpha': 0.25, 'beta': 0.30, 'gamma': 0.30, 'pct_relative': 5.0})
        
        # Collect features with expectations
        for feat, entry in results.items():
            exp = self._expected_direction(task_name, feat)
            if exp is None:
                continue
            expected_map[feat] = exp
            
            # Check observed direction vs expectation
            delta = float(entry.get('delta', 0.0))
            dir_ok = (delta > 0 and exp == 'up') or (delta < 0 and exp == 'down')
            key_dir_counts['with' if dir_ok else 'against'] += 1
            
            # Check if feature passed significance with directional criteria
            if entry.get('significant_change'):
                flags = entry.get('decision_flags', {})
                p_dir = flags.get('p_one_sided')
                d_val = entry.get('effect_size_d')
                pct = entry.get('percent_change')
                rule = flags.get('pass_rule', 'unknown')
                
                # Determine which band/feature threshold applies
                feat_thr_d = 0.25  # default
                if 'alpha' in feat:
                    feat_thr_d = thr.get('alpha', 0.25)
                elif 'beta' in feat:
                    feat_thr_d = thr.get('beta', 0.30)
                elif 'gamma' in feat:
                    feat_thr_d = thr.get('gamma', 0.30)
                elif 'theta' in feat:
                    feat_thr_d = thr.get('theta', 0.30)
                
                # Check if metrics meet threshold
                d_meets = (d_val is not None and not np.isnan(d_val) and abs(d_val) >= feat_thr_d)
                pct_meets = (pct is not None and not np.isnan(pct) and abs(pct) >= thr['pct_relative'])
                
                passed_features.append({
                    'feature': feat,
                    'direction': exp,
                    'p_dir': p_dir,
                    'd': d_val,
                    'pct': pct,
                    'rule': rule,
                    'd_meets_thr': d_meets,
                    'pct_meets_thr': pct_meets,
                })
        
        # Task-specific grading rules (production)
        t_lower = t.lower()
        main_pass = False
        grade_notes = []
        
        try:
            if t_lower == 'mental_math':
                # Expect: alpha↓, beta↑, beta_alpha_ratio↑, gamma↑
                alpha_down = any(f['feature'] == 'alpha_relative' and f['direction'] == 'down' 
                                and f.get('d_meets_thr', False) for f in passed_features)
                beta_up = any(f['feature'] == 'beta_relative' and f['direction'] == 'up' 
                             and f.get('d_meets_thr', False) for f in passed_features)
                ratio_up = any(f['feature'] == 'beta_alpha_ratio' and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                gamma_up = any(f['feature'] == 'gamma_relative' and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                
                # Grade A: alpha↓ + (beta↑ or ratio↑) + gamma↑
                if alpha_down and (beta_up or ratio_up) and gamma_up:
                    main_pass = True
                    grade_notes.append('All key features (α↓, β/ratio↑, γ↑) passed')
                elif alpha_down and (beta_up or ratio_up):
                    main_pass = True
                    grade_notes.append('Core features (α↓, β/ratio↑) passed')
                else:
                    grade_notes.append('Missing core mental_math features')
                    
            elif t_lower == 'attention_focus':
                # Expect: alpha↓, beta↑, beta_alpha_ratio↑
                alpha_down = any(f['feature'] == 'alpha_relative' and f['direction'] == 'down' 
                                and f.get('d_meets_thr', False) for f in passed_features)
                beta_up = any(f['feature'] == 'beta_relative' and f['direction'] == 'up' 
                             and f.get('d_meets_thr', False) for f in passed_features)
                ratio_up = any(f['feature'] == 'beta_alpha_ratio' and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                
                # Grade A: alpha↓ + (beta↑ or ratio↑)
                if alpha_down and (beta_up or ratio_up):
                    main_pass = True
                    grade_notes.append('Core features (α↓, β/ratio↑) passed')
                else:
                    grade_notes.append('Missing core attention_focus features')
                    
            elif t_lower == 'visual_imagery':
                alpha_up = any(f['feature'] == 'alpha_relative' and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                ratio_up = any(f['feature'] == 'alpha_theta_ratio' and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                main_pass = alpha_up or ratio_up
                grade_notes.append('Visual imagery: alpha/ratio signature')
                
            elif t_lower == 'working_memory':
                theta_up = any(f['feature'].startswith('theta_') and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                alpha_down = any(f['feature'] == 'alpha_relative' and f['direction'] == 'down' 
                                and f.get('d_meets_thr', False) for f in passed_features)
                ratio_up = any(f['feature'] == 'beta_alpha_ratio' and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                main_pass = theta_up and (alpha_down or ratio_up)
                grade_notes.append('Working memory: theta + alpha/ratio')
                
            elif t_lower == 'cognitive_load':
                theta_up = any(f['feature'].startswith('theta_') and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                alpha_down = any(f['feature'] == 'alpha_relative' and f['direction'] == 'down' 
                                and f.get('d_meets_thr', False) for f in passed_features)
                main_pass = theta_up and alpha_down
                grade_notes.append('Cognitive load: theta↑ + alpha↓')
                
            elif t_lower == 'motor_imagery':
                alpha_down = any(f['feature'] == 'alpha_relative' and f['direction'] == 'down' 
                                and f.get('d_meets_thr', False) for f in passed_features)
                beta_up = any(f['feature'] == 'beta_relative' and f['direction'] == 'up' 
                             and f.get('d_meets_thr', False) for f in passed_features)
                ratio_up = any(f['feature'] == 'beta_alpha_ratio' and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                main_pass = alpha_down or beta_up or ratio_up
                grade_notes.append('Motor imagery: alpha↓ or beta↑')
                
            elif t_lower == 'language_processing':
                alpha_down = any(f['feature'] == 'alpha_relative' and f['direction'] == 'down' 
                                and f.get('d_meets_thr', False) for f in passed_features)
                ratio_up = any(f['feature'] == 'beta_alpha_ratio' and f['direction'] == 'up' 
                              and f.get('d_meets_thr', False) for f in passed_features)
                main_pass = alpha_down and ratio_up
                grade_notes.append('Language: alpha↓ + ratio↑')
                
        except Exception as e:
            main_pass = False
            grade_notes.append(f'Grading error: {str(e)}')
        
        # Check for insufficient metrics on key features
        key_features_map = {
            'mental_math': ['alpha_relative', 'beta_relative', 'beta_alpha_ratio', 'gamma_relative'],
            'attention_focus': ['alpha_relative', 'beta_relative', 'beta_alpha_ratio'],
            'visual_imagery': ['alpha_relative', 'alpha_theta_ratio'],
            'working_memory': ['theta_relative', 'alpha_relative', 'beta_alpha_ratio'],
            'cognitive_load': ['theta_relative', 'alpha_relative'],
            'motor_imagery': ['alpha_relative', 'beta_relative', 'beta_alpha_ratio'],
            'language_processing': ['alpha_relative', 'beta_alpha_ratio'],
        }
        key_feats = key_features_map.get(t_lower, [])
        missing_metrics = []
        for kf in key_feats:
            entry = results.get(kf, {})
            d_val = entry.get('effect_size_d')
            p_dir = entry.get('decision_flags', {}).get('p_one_sided')
            reason = entry.get('reason', '')
            if d_val is None or np.isnan(d_val) or p_dir is None:
                missing_metrics.append(f"{kf}({reason if reason else 'no_d_or_p'})")
        
        if missing_metrics:
            insufficient_metrics = True
            grade_notes.append(f"Insufficient metrics: {', '.join(missing_metrics)}")
        
        # Assign grade A/B/C/D
        grade = 'D'
        n_pass = len(passed_features)
        if main_pass and n_pass >= 3:
            grade = 'A'
        elif main_pass:
            grade = 'B'
        elif n_pass >= 2:
            grade = 'C'
        
        # Counter-directional flag (≥70% features against expectation)
        total_dir = key_dir_counts['with'] + key_dir_counts['against']
        counter = False
        if total_dir >= 3:
            frac_against = key_dir_counts['against'] / float(total_dir)
            counter = frac_against >= 0.70
        
        # Top 2-3 drivers by |d|
        drivers = sorted(
            [{'feature': f['feature'], 'd': abs(f.get('d', 0.0) or 0.0)} for f in passed_features],
            key=lambda x: x['d'], reverse=True
        )[:3]
        
        # Notes: gamma EMG status
        notes = []
        try:
            task_features = self.calibration_data.get('task', {}).get('features', [])
            emg_flags = [int(e.get('_emg_guard', 0)) for e in task_features]
            if any(v == 1 for v in emg_flags):
                notes.append('Gamma evaluation guarded by EMG flag in some windows')
        except Exception:
            pass
        
        notes.extend(grade_notes)
        
        return {
            'grade': grade,
            'passes': passed_features,
            'top_drivers': drivers,
            'counter_directional': counter,
            'notes': notes,
            'insufficient_metrics': insufficient_metrics,
        }

    # --- Utility: simple blink detection on a window ---
    def _is_blinky_window(self, x: np.ndarray) -> bool:
        """Conservative blink heuristic using robust dispersion (MAD) and proportion.
        Flags as blink only if both a very large deviation exists AND a small
        fraction of samples exceed a lower threshold, to avoid rejecting normal EC.
        """
        x = np.asarray(x, dtype=float)
        med = float(np.median(x))
        dev = np.abs(x - med)
        mad = float(np.median(dev)) + 1e-12
        scale = 1.4826 * mad  # approx std for normally distributed data
        # Very high spike threshold and a lower threshold for proportion check
        hi_thr = 8.0 * scale
        lo_thr = 5.0 * scale
        if scale <= 1e-9:
            return False
        has_spike = bool(np.max(dev) > hi_thr)
        frac_hi = float(np.mean(dev > lo_thr))
        return has_spike and (frac_hi > 0.01)

    # --- Optional PSD normalization hook ---
    def _normalize_psd(self, psd: np.ndarray, method: str):
        if method == 'total_power':
            denom = np.sum(psd) + 1e-12
            return psd / denom
        elif method == 'snr_based':
            noise_floor = np.percentile(psd, 10)
            nf = max(noise_floor, 1e-12)
            return (psd - nf) / nf
        elif method == 'z_transform':
            mu, sd = np.mean(psd), np.std(psd) + 1e-12
            return (psd - mu) / sd
        elif method == 'robust_scaling':
            med = np.median(psd)
            mad = np.median(np.abs(psd - med))
            scale = 1.4826 * (mad + 1e-12)
            return (psd - med) / scale
        return psd

    def extract_features(self, window_data):
        # Override to add PSD normalization and robust peak descriptors
        x = np.asarray(window_data, dtype=float)
        x = x - np.mean(x)
        try:
            # Ensure sample rate present
            self.fs = float(getattr(self, 'fs', 256.0))
        except Exception:
            self.fs = 256.0
        
        # ====================================================================
        # LINE NOISE REMOVAL - Apply notch filter at mains frequency + harmonics
        # ====================================================================
        if getattr(self.config, 'apply_notch_filter', True) and len(x) > 10:
            try:
                from scipy import signal as sig
                line_freq = getattr(self.config, 'line_noise_freq', 60.0)
                nyq = self.fs / 2.0
                Q = 30.0  # Quality factor (narrowness of notch)
                # Apply notch at fundamental and first two harmonics
                for harmonic in [1, 2, 3]:
                    freq = line_freq * harmonic
                    if freq < nyq - 1:
                        w0 = freq / nyq
                        b, a = sig.iirnotch(w0, Q)
                        x = sig.filtfilt(b, a, x)
            except Exception:
                pass  # Skip if scipy unavailable or error
        
        # PSD via multitaper if available
        psd = None
        freqs = None
        use_multitaper = True
        if use_multitaper:
            try:
                from scipy.signal.windows import dpss  # type: ignore
                from numpy.fft import rfft, rfftfreq
                K = max(1, int(self.mt_tapers))
                NW = 2.5  # time-bandwidth product (typical)
                tapers = dpss(x.size, NW=NW, Kmax=K, sym=False)
                psd_accum = None
                for k in range(K):
                    xk = x * tapers[k]
                    Xk = rfft(xk)
                    Pk = (np.abs(Xk) ** 2) / (self.fs * x.size)
                    if psd_accum is None:
                        psd_accum = Pk
                    else:
                        psd_accum += Pk
                psd = psd_accum / float(K)
                freqs = rfftfreq(x.size, d=1.0 / self.fs)
            except Exception:
                pass
        if psd is None or freqs is None:
            freqs, psd = BL.compute_psd(x, self.fs)

        # Global noise floor for SNR-adapted band powers
        try:
            noise_floor = np.percentile(psd, 10)
        except Exception:
            noise_floor = float(np.min(psd)) if psd.size else 0.0
        snr_psd = np.maximum(psd - noise_floor, 0.0)

        # Keep a normalized PSD only for peak descriptors
        psd_norm = self._normalize_psd(psd, self.normalization_method)

        total_power = np.var(x)
        features = {}
        band_powers = {}

        # Use extended bands: include theta1/theta2 and beta1/beta2
        extended_bands = dict(getattr(BL, 'EEG_BANDS', {}))
        # Fill in common defaults if base is missing
        if not extended_bands:
            extended_bands = {
                'delta': (1, 4),
                'theta': (4, 8),
                'alpha': (8, 13),
                'beta': (13, 30),
                'gamma': (30, 50),
            }
        # Add splits
        extended_bands.update({
            'theta1': (4, 6),
            'theta2': (6, 8),
            'beta1': (13, 20),
            'beta2': (20, 30),
        })

        # Precompute total SNR power across spectrum for relative metrics
        try:
            total_snr_power_spectrum = float(np.trapz(snr_psd, freqs)) if psd.size else 0.0
        except Exception:
            total_snr_power_spectrum = float(np.sum(snr_psd))

        for band_name, (low, high) in extended_bands.items():
            mask = (freqs >= low) & (freqs <= high)
            if np.any(mask):
                band_freqs = freqs[mask]
                band_psd = psd[mask]
                band_snr_psd = snr_psd[mask]
                band_psd_norm = psd_norm[mask]

                # Absolute and relative power
                try:
                    # Raw power (for reference)
                    raw_power = float(np.trapz(band_psd, band_freqs))
                except Exception:
                    raw_power = float(np.sum(band_psd))
                try:
                    # SNR-adapted power (preferred)
                    snr_power = float(np.trapz(band_snr_psd, band_freqs))
                except Exception:
                    snr_power = float(np.sum(band_snr_psd))

                band_powers[band_name] = snr_power
                features[f'{band_name}_power'] = snr_power
                features[f'{band_name}_power_raw'] = raw_power

                # Prefer relative metrics based on SNR-adapted totals
                denom = total_snr_power_spectrum if total_snr_power_spectrum > 0 else (total_power + 1e-12)
                rel_power = snr_power / (denom + 1e-12)
                features[f'{band_name}_relative'] = rel_power

                # Robust peak descriptors from normalized PSD
                if len(band_psd_norm) > 0:
                    peak_idx = int(np.argmax(band_psd_norm))
                    peak_amp = float(band_psd_norm[peak_idx])
                    peak_freq = float(band_freqs[peak_idx])
                    features[f'{band_name}_peak_freq'] = peak_freq
                    features[f'{band_name}_peak_amp'] = float(band_psd[peak_idx])
                    # Relative prominence within band
                    mean_band = np.mean(band_psd_norm) + 1e-12
                    features[f'{band_name}_peak_rel_amp'] = peak_amp / mean_band
                    # Spectral entropy within band (stable)
                    p = band_psd_norm / (np.sum(band_psd_norm) + 1e-12)
                    # Numerical guard: clip & renormalize to avoid log2 warnings and negative rounding
                    p = np.clip(p, 1e-12, 1.0)
                    p = p / (np.sum(p) + 1e-12)
                    features[f'{band_name}_entropy'] = float(-np.sum(p * np.log2(p)))
                else:
                    mid = (low + high) / 2
                    features[f'{band_name}_peak_freq'] = mid
                    features[f'{band_name}_peak_amp'] = 0.0
                    features[f'{band_name}_peak_rel_amp'] = 0.0
                    features[f'{band_name}_entropy'] = 0.0
            else:
                mid = (low + high) / 2
                for suf, val in [('peak_freq', mid), ('peak_amp', 0.0), ('peak_rel_amp', 0.0), ('entropy', 0.0)]:
                    features[f'{band_name}_{suf}'] = val
                features[f'{band_name}_power'] = 0.0
                features[f'{band_name}_power_raw'] = 0.0
                features[f'{band_name}_relative'] = 0.0

        # ====================================================================
        # HIGH-FREQUENCY EMG GUARD FOR GAMMA METRICS
        # Uses adaptive threshold (baseline_mean + 2*baseline_SD) when available,
        # falls back to fixed ratio threshold otherwise.
        # ====================================================================
        gamma_windows_total = 1  # This window
        gamma_windows_kept = 0
        ratio_hf_mid = 0.0
        slope = 0.0
        try:
            hf_mask = (freqs >= 35) & (freqs <= 45)
            mid_mask = (freqs >= 20) & (freqs <= 30)
            hf_power_sum = float(np.trapz(psd[hf_mask], freqs[hf_mask]) if np.any(hf_mask) else 0.0)
            mid_power_sum = float(np.trapz(psd[mid_mask], freqs[mid_mask]) if np.any(mid_mask) else 0.0)
            ratio_hf_mid = hf_power_sum / (mid_power_sum + 1e-12)
            
            # Spectral slope on 20–45 Hz (EMG has flatter slope than EEG's 1/f)
            use_mask = (freqs >= 20) & (freqs <= 45)
            f_sel = freqs[use_mask]
            p_sel = psd[use_mask]
            if f_sel.size >= 3:
                logf = np.log(f_sel + 1e-12)
                logp = np.log(p_sel + 1e-18)
                A = np.vstack([logf, np.ones_like(logf)]).T
                slope, _ = np.linalg.lstsq(A, logp, rcond=None)[0]
            else:
                slope = 0.0
            
            # Determine EMG threshold (adaptive or fixed)
            use_adaptive = getattr(self.config, 'emg_adaptive_threshold', True)
            fixed_ratio = getattr(self.config, 'emg_fixed_ratio', 1.5)
            
            if use_adaptive and hasattr(self, '_baseline_emg_stats') and self._baseline_emg_stats:
                # Use adaptive threshold: baseline_mean + 2*baseline_SD
                base_mean = self._baseline_emg_stats.get('ratio_mean', 0.8)
                base_std = self._baseline_emg_stats.get('ratio_std', 0.3)
                adaptive_threshold = base_mean + 2.0 * base_std
                # Ensure threshold is at least the fixed fallback
                adaptive_threshold = max(adaptive_threshold, fixed_ratio * 0.8)
                emg_flag = bool(ratio_hf_mid > adaptive_threshold or slope > -0.6)
            else:
                # Fixed threshold fallback
                emg_flag = bool(ratio_hf_mid > fixed_ratio or slope > -0.6)
            
        except Exception:
            emg_flag = False
        
        # Store EMG ratio for baseline computation (used to calibrate adaptive threshold)
        features['_emg_ratio'] = ratio_hf_mid
        features['_emg_slope'] = slope
        features['_emg_guard'] = 1 if emg_flag else 0
        features['_gamma_evaluated'] = 0 if emg_flag else 1
        
        if emg_flag:
            # Remove gamma features and mark as guarded-out
            for k in list(features.keys()):
                if k.startswith('gamma_'):
                    features.pop(k, None)
            gamma_windows_kept = 0
        else:
            gamma_windows_kept = 1
        
        # Update session-level gamma statistics (for later reporting)
        if not hasattr(self, 'gamma_windows_total'):
            self.gamma_windows_total = 0
        if not hasattr(self, 'gamma_windows_kept'):
            self.gamma_windows_kept = 0
        self.gamma_windows_total += gamma_windows_total
        self.gamma_windows_kept += gamma_windows_kept

        # Cross-band ratios
        alpha = band_powers.get('alpha', 0.0)
        theta = band_powers.get('theta', 0.0)
        beta = band_powers.get('beta', 0.0)
        theta1 = band_powers.get('theta1', 0.0)
        theta2 = band_powers.get('theta2', 0.0)
        beta1 = band_powers.get('beta1', 0.0)
        beta2 = band_powers.get('beta2', 0.0)
        features['alpha_theta_ratio'] = alpha / (theta + 1e-10)
        features['beta_alpha_ratio'] = beta / (alpha + 1e-10)
        # New split-band ratios
        features['beta2_beta1_ratio'] = beta2 / (beta1 + 1e-10)
        features['theta2_theta1_ratio'] = theta2 / (theta1 + 1e-10)
        features['total_power'] = total_power

        return features

    def add_data(self, new_data):
        # Same windowing as base, but reject only extreme blink artifacts for baseline accumulation
        features = super().add_data(new_data)
        if features is None:
            return None
        # If currently collecting eyes_closed baseline, check for extreme artifacts only
        if self.current_state == 'eyes_closed' and len(self.raw_buffer) >= self.window_samples:
            x = np.array(list(self.raw_buffer)[-self.window_samples:])
            # Initialize counters if missing
            if not hasattr(self, 'baseline_rejected'):
                self.baseline_rejected = 0
            if not hasattr(self, 'baseline_kept'):
                self.baseline_kept = 0
            
            # Use a much more lenient blink detection for eyes-closed baseline
            # Only reject windows with extreme artifacts (>10 sigma from median)
            med = float(np.median(x))
            mad = float(np.median(np.abs(x - med))) + 1e-12
            scale = 1.4826 * mad
            extreme_threshold = 10.0 * scale  # Very lenient threshold
            
            # Only reject if there are extreme outliers (>20 sigma) AND many of them
            extreme_outliers = np.abs(x - med) > (20.0 * scale)
            is_extreme_artifact = np.sum(extreme_outliers) > (len(x) * 0.05)  # >5% extreme outliers
            
            if is_extreme_artifact and scale > 10.0:  # Also require significant variance
                # Remove last appended feature if it was added to calibration store
                if len(self.calibration_data['eyes_closed']['features']) > 0:
                    self.calibration_data['eyes_closed']['features'].pop()
                    self.calibration_data['eyes_closed']['timestamps'].pop()
                self.baseline_rejected += 1
                print(f"❌ Rejected EC window: extreme artifacts detected (scale={scale:.1f}, outliers={np.sum(extreme_outliers)})")
            else:
                self.baseline_kept += 1
                # More frequent logging to show progress
                if self.baseline_kept % 5 == 0:  # Log every 5 kept windows instead of 10
                    print(f"✅ EC Progress: {self.baseline_kept} windows kept, {self.baseline_rejected} rejected (median={med:.1f}, scale={scale:.1f})")
                elif self.baseline_kept == 1:  # Always show first window
                    print(f"✅ First EC window accepted (median={med:.1f}, scale={scale:.1f})")
        
        # While in a task, also store into a per-task bucket
        if self.current_state == 'task' and self.current_task and features is not None:
            tasks = self.calibration_data.setdefault('tasks', {})
            bucket = tasks.setdefault(self.current_task, {'features': [], 'timestamps': []})
            bucket['features'].append(features)
            bucket['timestamps'].append(time.time())
        return features

    def compute_baseline_statistics(self):
        """Use eyes-closed-only baseline as requested."""
        ec_features = self.calibration_data['eyes_closed']['features']
        eo_features = self.calibration_data['eyes_open']['features']
        
        print(f"\n=== COMPUTING BASELINE STATISTICS ===")
        print(f"Available EC features: {len(ec_features)}")
        print(f"Available EO features: {len(eo_features)}")
        
        if len(ec_features) == 0:
            print("⚠️  WARNING: No eyes-closed features available, falling back to base behavior")
            # Fallback to base behavior if EC absent
            result = super().compute_baseline_statistics()
            if result:
                print(f"✅ Fallback baseline computed with {len(self.baseline_stats)} features")
            return result
            
        df = pd.DataFrame(ec_features)
        self.baseline_stats = {}
        
        print(f"Eyes-closed DataFrame shape: {df.shape}")
        print(f"Available feature columns: {list(df.columns)}")
        try:
            bands = dict(getattr(BL, 'EEG_BANDS', {}))
            print(f"Band edges (Hz): {bands}")
        except Exception:
            pass
        try:
            print(f"Notch mains: {getattr(self, 'mains_hz', 'unknown')} Hz | PSD: multitaper tapers={getattr(self, 'mt_tapers', 3)}")
        except Exception:
            pass
        
        for feature in df.columns:
            values = df[feature].values
            self.baseline_stats[feature] = {
                'mean': float(np.mean(values)),
                'std': float(np.std(values) + 1e-12),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'median': float(np.median(values)),
                'q25': float(np.percentile(values, 25)),
                'q75': float(np.percentile(values, 75)),
            }
        
        print(f"✅ Eyes-closed-only baseline computed successfully!")
        print(f"✅ {len(self.baseline_stats)} feature statistics computed from {len(ec_features)} windows")
        
        # Show sample statistics for key features
        key_features = ['alpha_relative', 'theta_relative', 'beta_relative', 'alpha_theta_ratio']
        for feat in key_features:
            if feat in self.baseline_stats:
                stats = self.baseline_stats[feat]
                print(f"   {feat}: mean={stats['mean']:.3f} ± {stats['std']:.3f}")
        
        # ====================================================================
        # COMPUTE BASELINE EMG STATISTICS FOR ADAPTIVE THRESHOLDING
        # ====================================================================
        try:
            emg_ratios = [f.get('_emg_ratio', 0.0) for f in ec_features if isinstance(f, dict)]
            emg_ratios = [r for r in emg_ratios if r is not None and np.isfinite(r)]
            if len(emg_ratios) >= 3:
                self._baseline_emg_stats = {
                    'ratio_mean': float(np.mean(emg_ratios)),
                    'ratio_std': float(np.std(emg_ratios)),
                    'ratio_median': float(np.median(emg_ratios)),
                    'n_samples': len(emg_ratios),
                }
                thresh = self._baseline_emg_stats['ratio_mean'] + 2.0 * self._baseline_emg_stats['ratio_std']
                print(f"   EMG adaptive threshold: {thresh:.3f} (mean={self._baseline_emg_stats['ratio_mean']:.3f} + 2×{self._baseline_emg_stats['ratio_std']:.3f})")
            else:
                self._baseline_emg_stats = None
                print(f"   EMG adaptive threshold: N/A (insufficient baseline samples)")
        except Exception as e:
            self._baseline_emg_stats = None
            print(f"   EMG adaptive threshold: N/A (error: {e})")
        
        return self.baseline_stats

    # --- Helper utilities for advanced analysis ---
    def _baseline_dataframe(self, feature_list: List[str]) -> Optional[pd.DataFrame]:
        pool = self.calibration_data.get('eyes_closed', {}).get('features', [])
        if not pool:
            return None
        df = pd.DataFrame(pool)
        if feature_list:
            cols = [f for f in feature_list if f in df.columns]
            if cols:
                return df[cols].copy()
        return df

    def _task_dataframe(self, feature_list: List[str]) -> Optional[pd.DataFrame]:
        pool = self.calibration_data.get('task', {}).get('features', [])
        if not pool:
            return None
        df = pd.DataFrame(pool)
        if feature_list:
            cols = [f for f in feature_list if f in df.columns]
            if cols:
                return df[cols].copy()
        return df

    def _get_rng(self) -> np.random.Generator:
        seed = self.config.seed if self.config.seed is not None else int(time.time() * 1000) % (2**32)
        return np.random.default_rng(seed)

    # --- Block utilities (non-overlapping, time-based) ---
    def _window_duration_sec(self) -> float:
        try:
            return float(self.window_samples) / float(self.fs)
        except Exception:
            return 2.0

    def _build_blocks(self, features_list: List[Dict[str, Any]], timestamps: List[float]) -> List[Dict[str, Any]]:
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

    def _equalize_blocks(self, base_blocks: List[Dict[str, Any]], task_blocks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        n_base = len(base_blocks)
        n_task = len(task_blocks)
        if n_base == 0 or n_task == 0:
            return [], []
        n = min(n_base, n_task)
        if n_base > n:
            idx = self._get_rng().choice(n_base, size=n, replace=False)
            base_blocks = [base_blocks[i] for i in sorted(idx)]
        else:
            base_blocks = base_blocks[:n]
        if n_task > n:
            idx = self._get_rng().choice(n_task, size=n, replace=False)
            task_blocks = [task_blocks[i] for i in sorted(idx)]
        else:
            task_blocks = task_blocks[:n]
        return base_blocks, task_blocks

    def _block_spearman_corr(self, base_blocks: List[Dict[str, Any]], task_blocks: List[Dict[str, Any]], features: List[str]) -> np.ndarray:
        if not features:
            return np.empty((0, 0))
        key = ("block_corr", tuple(features), len(base_blocks) + len(task_blocks), self.block_seconds)
        cached = self._cached_block_corr.get(key)
        if cached is not None:
            return cached
        if not base_blocks and not task_blocks:
            corr = np.eye(len(features))
        else:
            all_blocks = (base_blocks or []) + (task_blocks or [])
            df = pd.DataFrame(all_blocks)
            try:
                corr = df[features].corr(method='spearman').to_numpy()
                corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
            except Exception:
                corr = np.eye(len(features))
        self._cached_block_corr[key] = corr
        return corr

    def _compute_effect_value(self, feature: str, task_mean: float, baseline_stats: Dict[str, Any]) -> float:
        b_mean = float(baseline_stats[feature]['mean'])
        b_std = float(baseline_stats[feature]['std'])
        if self.config.effect_measure == 'z':
            return (task_mean - b_mean) / (b_std + 1e-12)
        return task_mean - b_mean

    def _baseline_effect_samples(self, feature: str, baseline_df: Optional[pd.DataFrame]) -> Optional[np.ndarray]:
        if baseline_df is None or feature not in baseline_df.columns:
            return None
        values = np.asarray(baseline_df[feature].values, dtype=float)
        stats = self.baseline_stats.get(feature)
        if stats is None:
            return None
        mean = float(stats['mean'])
        std = float(stats['std'])
        if self.config.effect_measure == 'z':
            return (values - mean) / (std + 1e-12)
        return values - mean

    @staticmethod
    def _digitize_effect(value: float, bins: np.ndarray) -> int:
        if bins.size <= 1:
            return 0
        idx = int(np.digitize([value], bins[1:-1], right=True)[0])
        return max(0, min(idx, bins.size - 2))

    def _discretize(self, feature: str, effect_value: float, baseline_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        bins = self.config.discretization_bins
        baseline_samples = self._baseline_effect_samples(feature, baseline_df)
        if baseline_samples is None or baseline_samples.size == 0:
            edges = np.linspace(-1, 1, bins + 1)
        else:
            quantiles = np.linspace(0, 1, bins + 1)
            try:
                edges = np.quantile(baseline_samples, quantiles)
            except Exception:
                edges = np.linspace(np.min(baseline_samples), np.max(baseline_samples), bins + 1)
        edges = np.asarray(edges, dtype=float)
        # Ensure strictly increasing
        edges = np.unique(edges)
        if edges.size <= 1:
            edges = np.linspace(effect_value - 1.0, effect_value + 1.0, bins + 1)
        # Guarantee number of edges = bins+1
        if edges.size != bins + 1:
            edges = np.linspace(edges.min(), edges.max() if edges.max() > edges.min() else edges.min() + 1.0, bins + 1)
        discrete_idx = self._digitize_effect(effect_value, edges)
        return {
            'bins': edges.tolist(),
            'discrete_index': int(discrete_idx),
        }

    def _spearman_corr(self, baseline_df: Optional[pd.DataFrame], features: List[str]) -> np.ndarray:
        if not features:
            return np.empty((0, 0))
        baseline_len = len(baseline_df) if baseline_df is not None else 0
        key = ("spearman", baseline_len, tuple(features))
        cached = self._cached_corr_matrices.get(key)
        if cached is not None:
            return cached
        if baseline_df is None or baseline_df.empty:
            corr = np.eye(len(features))
        else:
            try:
                corr_df = baseline_df[features].copy()
                corr = corr_df.corr(method='spearman').to_numpy()
                corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
            except Exception:
                corr = np.eye(len(features))
        self._cached_corr_matrices[key] = corr
        return corr

    def _effective_feature_count(self, baseline_df: Optional[pd.DataFrame], features: List[str]) -> float:
        if not features:
            return 0.0
        try:
            corr = self._spearman_corr(baseline_df, features)
            if corr.size == 0:
                return float(len(features))
            eigvals = np.linalg.eigvalsh(corr)
            eff = float(np.sum(np.clip(eigvals, 0.0, 1.0)))
            return max(1.0, eff)
        except Exception:
            return float(len(features))

    def _correlation_guard_factor(self, baseline_df: Optional[pd.DataFrame], features: List[str]) -> float:
        if not self.config.correlation_guard or not features:
            return 1.0
        nominal = max(1.0, float(len(features)))
        eff = self._effective_feature_count(baseline_df, features)
        factor = eff / nominal
        return float(np.clip(factor, 0.05, 1.0))

    # --- Directional priors and thresholds ---
    def _feature_classification(self, feature: str) -> Tuple[str, bool, bool]:
        name = feature.lower()
        band = 'other'
        if name.startswith('alpha_') or ('alpha' in name and 'ratio' not in name):
            band = 'alpha'
        if name.startswith('beta_') or ('beta' in name and 'ratio' not in name):
            band = 'beta'
        if name.startswith('theta_') or ('theta' in name and 'ratio' not in name):
            band = 'theta'
        if name.startswith('gamma_') or ('gamma' in name and 'ratio' not in name):
            band = 'gamma'
        is_ratio = ('ratio' in name)
        is_relative = name.endswith('_relative') or is_ratio
        if is_ratio and band == 'other':
            band = 'ratio'
        return band, is_relative, is_ratio

    def _thresholds_for_feature(self, feature: str) -> Tuple[float, float]:
        band, is_relative, is_ratio = self._feature_classification(feature)
        d_map = {
            'gamma': 0.30,
            'ratio': 0.30,
            'beta': 0.35,
            'theta': 0.30,
            'alpha': 0.25,
        }
        d_thr = d_map.get(band, 0.30)
        pct_thr = 0.05 if (is_relative or is_ratio) else 0.10
        return d_thr, pct_thr * 100.0

    def _expected_direction(self, task_name: Optional[str], feature: str) -> Optional[str]:
        t = (task_name or '').lower()
        f = feature.lower()
        if t == 'mental_math':
            if f.startswith('alpha_'): return 'down'
            if f.startswith('beta_') or 'beta_alpha_ratio' in f: return 'up'
            if f.startswith('gamma_'): return 'up'
            if f == 'alpha_theta_ratio': return 'down'
        elif t == 'visual_imagery':
            if f.startswith('alpha_'): return 'up'
            if f == 'alpha_theta_ratio': return 'up'
            if 'beta_alpha_ratio' in f: return 'down'
        elif t == 'working_memory':
            if f.startswith('theta_'): return 'up'
            if f.startswith('alpha_'): return 'down'
            if 'beta_alpha_ratio' in f or f.startswith('beta_'): return 'up'
            if f.startswith('gamma_'): return 'up'
        elif t == 'attention_focus':
            if f.startswith('alpha_'): return 'down'
            if f.startswith('beta_') or 'beta_alpha_ratio' in f: return 'up'
            if f.startswith('theta_'): return 'down'
        elif t == 'language_processing':
            if f.startswith('beta_') or 'beta_alpha_ratio' in f: return 'up'
            if f.startswith('alpha_'): return 'down'
            if f.startswith('gamma_'): return 'up'
        elif t == 'motor_imagery':
            if f.startswith('alpha_'): return 'down'
            if 'beta_alpha_ratio' in f or f.startswith('beta_'): return 'up'
        elif t == 'cognitive_load':
            if f.startswith('theta_'): return 'up'
            if f.startswith('alpha_'): return 'down'
            if f.startswith('beta_') or 'beta_alpha_ratio' in f: return 'up'
        return None

    def _kost_mcdermott_pvalue(self, fisher_stat: float, features: List[str], baseline_df: Optional[pd.DataFrame]) -> Tuple[float, float, float]:
        k = len(features)
        if k == 0:
            return fisher_stat, 1.0, 0.0
        if self.config.dependence_correction.lower() != 'kost-mcdermott' or k == 1:
            return fisher_stat, float(self._chi2_sf(fisher_stat, 2 * k)), float(2 * k)
        corr = self._spearman_corr(baseline_df, features)
        mu = 2.0 * k
        cov_sum = 0.0
        for i in range(k):
            for j in range(i + 1, k):
                r = float(corr[i, j])
                cov = 3.263 * r + 0.710 * (r ** 2) + 0.027 * (r ** 3)
                cov_sum += cov
        sigma_sq = 4.0 * k + 2.0 * cov_sum
        if sigma_sq <= 0:
            return fisher_stat, float(self._chi2_sf(fisher_stat, 2 * k)), float(2 * k)
        c = sigma_sq / (2.0 * mu)
        df = max(1.0, (2.0 * (mu ** 2)) / sigma_sq)
        adjusted_stat = fisher_stat / c
        if _scipy_chi2 is not None:
            p_val = float(_scipy_chi2.sf(adjusted_stat, df))
        else:
            p_val = float(self._chi2_sf(adjusted_stat, int(round(df))))
        return adjusted_stat, p_val, df

    def _get_permutation_indices(self, feature_key: str, total_len: int, n_perm: int, rng: np.random.Generator) -> np.ndarray:
        cache_key = (feature_key, total_len, n_perm)
        cached = self._perm_index_cache.get(cache_key)
        if cached is not None and cached.shape[0] >= n_perm:
            return cached[:n_perm]
        perms = np.vstack([rng.permutation(total_len) for _ in range(n_perm)])
        self._perm_index_cache[cache_key] = perms
        return perms

    def _permutation_sum_p(
        self,
        per_feature_data: Dict[str, Tuple[np.ndarray, np.ndarray]],
        observed_sum: float,
    ) -> Tuple[Optional[float], Optional[float], bool]:
        # Fast mode: skip permutation testing entirely
        if getattr(self.config, 'fast_mode', False):
            # Use asymptotic approximation instead of permutation
            # For large n, sum of -log(p) ~ chi-square(2k) under null
            # Return observed_sum with chi-square based p-value
            k = len(per_feature_data)
            if k > 0:
                from scipy import stats
                # Fisher's method p-value (chi-square approximation)
                chi2_p = 1.0 - stats.chi2.cdf(2 * observed_sum, 2 * k) if observed_sum > 0 else 1.0
                return observed_sum, chi2_p, False
            return observed_sum, None, False
        
        if not self.config.use_permutation_for_sumP:
            return None, None, False
        if not per_feature_data:
            return None, None, False
        n_perm = self.config.n_perm
        rng = self._get_rng()
        # Streaming permutation: avoid allocating (n_perm, total_len) index arrays which
        # can be huge for large total_len (causes MemoryError). Instead, precompute the
        # combined arrays for each feature and draw a single permutation per-feature per-iteration.
        # Vectorized setup: stack combined arrays row-wise
        feature_names = list(per_feature_data.keys())
        if not feature_names:
            return observed_sum, None, False
        combined_rows = []
        n_task = None
        for f in feature_names:
            task_vals, base_vals = per_feature_data[f]
            if n_task is None:
                n_task = int(task_vals.size)
            combined_rows.append(np.concatenate([task_vals, base_vals]))
        combined = np.vstack(combined_rows)  # shape (F, T+B)
        total_len = combined.shape[1]
        F = combined.shape[0]
        perm_distribution = np.zeros(n_perm, dtype=float)
        self.reset_permutation_cancel()
        try:
            self._last_permutation_partial = False
        except Exception:
            pass
        
        # OPTIMIZATION: Vectorized t-test computation (5-10x faster than loop)
        # Pre-compute constants for vectorized Welch t-test
        from math import erfc, sqrt as math_sqrt
        
        # Progress callback throttling: only emit every N iterations to reduce overhead
        progress_interval = max(1, n_perm // 100)  # Update ~100 times max
        
        for idx in range(n_perm):
            if self._perm_cancelled:
                completed = idx
                if completed <= 0:
                    return observed_sum, None, False
                less_equal_partial = float(np.sum(perm_distribution[:completed] <= observed_sum))
                perm_p_partial = (less_equal_partial + 1.0) / (completed + 1.0)
                try:
                    self._last_permutation_partial = True
                except Exception:
                    pass
                return observed_sum, float(perm_p_partial), True
            
            # Permute once for all features
            perm_idx = rng.permutation(total_len)
            permuted = combined[:, perm_idx]
            task_block = permuted[:, :n_task]  # shape (F, n_task)
            base_block = permuted[:, n_task:]  # shape (F, n_base)
            
            # VECTORIZED WELCH T-TEST (compute all features at once)
            # Means: shape (F,)
            mx = np.mean(task_block, axis=1)
            my = np.mean(base_block, axis=1)
            
            # Variances: shape (F,)
            vx = np.var(task_block, axis=1, ddof=1)
            vy = np.var(base_block, axis=1, ddof=1)
            
            # Welch t-statistic: shape (F,)
            nx = task_block.shape[1]
            ny = base_block.shape[1]
            denom = np.sqrt((vx / nx) + (vy / ny) + 1e-18)
            t_stats = np.where(denom > 0, (mx - my) / denom, 0.0)
            
            # Two-tailed p-values using normal approximation (vectorized)
            z = np.abs(t_stats)
            # Use numpy's vectorized operations instead of loop
            p_vals = np.array([erfc(zi / math_sqrt(2.0)) for zi in z])
            
            # Handle NaN/inf (replace with 1.0)
            p_vals = np.nan_to_num(p_vals, nan=1.0, posinf=1.0, neginf=1.0)
            
            # Sum p-values across features
            row_sum = float(np.sum(p_vals))
            perm_distribution[idx] = row_sum
            
            # Throttled progress callback (only every N iterations)
            if self._perm_progress_callback is not None and (idx + 1) % progress_interval == 0:
                try:
                    self._perm_progress_callback(idx + 1, n_perm)
                except Exception:
                    pass
        
        # Final progress update
        if self._perm_progress_callback is not None:
            try:
                self._perm_progress_callback(n_perm, n_perm)
            except Exception:
                pass
        
        less_equal = float(np.sum(perm_distribution <= observed_sum))
        perm_p = (less_equal + 1.0) / (n_perm + 1.0)
        return observed_sum, float(perm_p), True

    @staticmethod
    def _friedman_fallback(rows: np.ndarray) -> Tuple[float, float]:
        # rows.shape = (observations, treatments)
        n, k = rows.shape
        if n < 2 or k < 2:
            return 0.0, 1.0
        ranks = np.argsort(np.argsort(rows, axis=1), axis=1).astype(float) + 1.0
        sum_ranks = np.sum(ranks, axis=0)
        chi2 = (12.0 / (n * k * (k + 1))) * np.sum((sum_ranks - (n * (k + 1) / 2.0)) ** 2)
        p_val = float(EnhancedFeatureAnalysisEngine._chi2_sf(chi2, k - 1))
        return float(chi2), p_val

    def _friedman_test(self, rows: np.ndarray) -> Tuple[float, float]:
        if _scipy_friedman is not None:
            try:
                stat, p_val = _scipy_friedman(*[rows[:, i] for i in range(rows.shape[1])])
                return float(stat), float(p_val)
            except Exception:
                pass
        return self._friedman_fallback(rows)

    @staticmethod
    def _sign_test_pvalue(diff: np.ndarray) -> float:
        diff = diff[np.isfinite(diff)]
        diff = diff[diff != 0]
        n = diff.size
        if n == 0:
            return 1.0
        pos = int(np.sum(diff > 0))
        tail = min(pos, n - pos)

        # Prefer SciPy's exact binomial implementation when available
        if _scipy_binomtest is not None:
            try:
                return float(_scipy_binomtest(pos, n, 0.5).pvalue)
            except Exception:
                pass

        if n <= 60:
            # Exact probability via cumulative binomial; manageable for small n
            cumulative = math.fsum(math.comb(n, k) for k in range(tail + 1))
            base_prob = cumulative / (2 ** n)
            if n % 2 == 0 and pos == n - pos:
                center_prob = math.comb(n, tail) / (2 ** n)
                p_val = 2.0 * base_prob - center_prob
            else:
                p_val = 2.0 * base_prob
            return float(min(1.0, max(0.0, p_val)))

        # Normal approximation with continuity correction for large n
        mean = n / 2.0
        std = math.sqrt(n / 4.0) + 1e-12
        z = (abs(pos - mean) - 0.5) / std
        z = max(0.0, z)
        p_val = math.erfc(z / math.sqrt(2.0))
        return float(min(1.0, max(0.0, p_val)))

    def _permutation_sum_p_blocks(
        self,
        per_feature_blocks: Dict[str, Tuple[np.ndarray, np.ndarray]],
    ) -> Tuple[Optional[float], Optional[float], bool, Optional[float], Dict[str, Any]]:
        """Block-level permutation for SumP.
        Returns (observed_sum, perm_p, used_permutation_flag, ess_blocks, metadata).
        """
        # Always run block permutations if n_perm > 0 (independent of mode)
        n_perm = int(self.config.n_perm)
        if n_perm <= 0:
            return None, None, False, None, {}
        if not per_feature_blocks:
            return None, None, False, None, {}
        
        rng = self._get_rng()
        seed_val = getattr(self.config, 'seed', None)
        
        # Determine equalized block count (ESS per condition) by downsampling larger side
        any_item = next(iter(per_feature_blocks.values()))
        n_task = len(any_item[0])
        n_base = len(any_item[1])
        n = min(n_task, n_base)
        if n == 0:
            return None, None, False, 0.0, {}
        ess = float(n)
        
        # Log metadata
        metadata = {
            'perm_unit': 'block',
            'block_len_sec': float(self.block_seconds),
            'n_blocks_used': int(n),
            'ess_baseline': int(n),
            'ess_task': int(n),
            'n_baseline_total': int(n_base),
            'n_task_total': int(n_task),
            'n_perm': int(n_perm),
            'seed': seed_val,
        }
        # Observed sum of p-values using block means per feature
        obs_sum = 0.0
        for f, (task_arr, base_arr) in per_feature_blocks.items():
            # Equalize arrays to n
            t = np.asarray(task_arr, dtype=float)
            b = np.asarray(base_arr, dtype=float)
            if t.size > n:
                idx = rng.choice(t.size, size=n, replace=False)
                t = t[idx]
            else:
                t = t[:n]
            if b.size > n:
                idx = rng.choice(b.size, size=n, replace=False)
                b = b[idx]
            else:
                b = b[:n]
            _, p = self._welch_ttest(t, b)
            p = float(np.nan_to_num(p, nan=1.0))
            obs_sum += p
        
        # Log start of permutation
        print(f"[SumP Block Perm] Starting {n_perm} permutations on {len(per_feature_blocks)} features, {n} blocks per condition...")
        
        # Permutation distribution
        perm_vals = np.zeros(n_perm, dtype=float)
        for i in range(n_perm):
            s = 0.0
            for f, (task_arr, base_arr) in per_feature_blocks.items():
                t = np.asarray(task_arr, dtype=float)
                b = np.asarray(base_arr, dtype=float)
                # Downsample to n if either side is larger
                if t.size > n:
                    idx = rng.choice(t.size, size=n, replace=False)
                    t = t[idx]
                else:
                    t = t[:n]
                if b.size > n:
                    idx = rng.choice(b.size, size=n, replace=False)
                    b = b[idx]
                else:
                    b = b[:n]
                # Concatenate and permute
                comb = np.concatenate([t, b])
                comb_len = len(comb)  # Actual combined length (may be < 2*n if original arrays were shorter)
                perm_idx = rng.permutation(comb_len)
                # Split permuted indices to create task and baseline permutations
                split_point = len(t)  # Use actual task array length, not n
                t_perm = comb[perm_idx[:split_point]]
                b_perm = comb[perm_idx[split_point:]]
                _, p = self._welch_ttest(t_perm, b_perm)
                s += float(np.nan_to_num(p, nan=1.0))
            perm_vals[i] = s
            # Progress callback: update every 1% (or every iteration for small n_perm)
            progress_interval = max(1, n_perm // 100)
            if self._perm_progress_callback is not None and ((i + 1) % progress_interval == 0 or (i + 1) == n_perm):
                try:
                    self._perm_progress_callback(i + 1, n_perm)
                except Exception:
                    pass
            # Console logging for visibility (every 10%)
            if (i + 1) % max(1, n_perm // 10) == 0 or (i + 1) == n_perm:
                print(f"[SumP Block Perm] Progress: {i+1}/{n_perm} ({100*(i+1)//n_perm}%)")
        less_equal = float(np.sum(perm_vals <= obs_sum))
        perm_p = (less_equal + 1.0) / (n_perm + 1.0)
        
        # Log summary
        print(f"[SumP Block Perm] unit=block, block_len={metadata['block_len_sec']}s, n_blocks={metadata['n_blocks_used']}, n_perm={metadata['n_perm']}, seed={metadata['seed']}")
        
        return obs_sum, float(perm_p), True, ess, metadata

    def analyze_task_data(self):
        """Analyze the current task synchronously and return per-feature analysis results."""
        # Ensure baseline stats exist
        if not getattr(self, 'baseline_stats', None):
            try:
                self.compute_baseline_statistics()
            except Exception:
                pass

        ec_features = self.calibration_data.get('eyes_closed', {}).get('features', [])
        eo_features = self.calibration_data.get('eyes_open', {}).get('features', [])
        task_features = self.calibration_data.get('task', {}).get('features', [])

        if not task_features:
            # Nothing to analyze
            return None

        # =====================================================================
        # CRITICAL DATA QUALITY VALIDATION
        # Check if data looks like real EEG before running statistical tests
        # =====================================================================
        data_quality_issues = []
        data_quality_valid = True
        
        # Check 1: Minimum window/block counts for adequate statistical power
        # With 4 blocks, 95% CI on Cohen's d=0.5 is ±0.89 (too wide)
        # With 8 blocks, 95% CI on Cohen's d=0.5 is ±0.63 (acceptable)
        min_baseline = getattr(self.config, 'min_blocks_per_condition', 8)
        min_task = getattr(self.config, 'min_blocks_per_condition', 8)
        
        baseline_count = max(len(ec_features), len(eo_features))
        task_count = len(task_features)
        
        if baseline_count < min_baseline:
            data_quality_issues.append(f"Insufficient baseline data ({baseline_count} < {min_baseline} windows)")
            data_quality_valid = False
        
        if task_count < min_task:
            data_quality_issues.append(f"Insufficient task data ({task_count} < {min_task} windows)")
            data_quality_valid = False
        
        # Check 2: Verify signal looks like EEG (not flat/noise) using spectral analysis
        try:
            # Sample a few windows and check spectral properties
            sample_windows = task_features[:min(5, len(task_features))]
            flat_signal_count = 0
            noise_signal_count = 0
            
            for window_data in sample_windows:
                if not isinstance(window_data, dict):
                    continue
                
                # Check if all power values are near-zero (flat signal)
                total_power = window_data.get('total_power', window_data.get('global_total_power', 0))
                if isinstance(total_power, (int, float)) and total_power < 1e-6:
                    flat_signal_count += 1
                    continue
                
                # Check spectral distribution (real EEG has strong delta/theta)
                delta_rel = window_data.get('delta_relative', window_data.get('global_delta_relative', 0))
                theta_rel = window_data.get('theta_relative', window_data.get('global_theta_relative', 0))
                gamma_rel = window_data.get('gamma_relative', window_data.get('global_gamma_relative', 0))
                
                if isinstance(delta_rel, (int, float)) and isinstance(theta_rel, (int, float)):
                    low_freq_power = delta_rel + theta_rel
                    # Real EEG typically has >30% power in delta+theta
                    if low_freq_power < 0.15:  # Very low delta+theta suggests noise
                        noise_signal_count += 1
                    # High gamma dominance often indicates muscle artifact or noise
                    if isinstance(gamma_rel, (int, float)) and gamma_rel > 0.4:
                        noise_signal_count += 1
            
            # If most samples look problematic, flag the data
            n_samples = len(sample_windows)
            if n_samples > 0:
                if flat_signal_count / n_samples > 0.5:
                    data_quality_issues.append("Flat signal detected - headset may not be worn")
                    data_quality_valid = False
                if noise_signal_count / n_samples > 0.5:
                    data_quality_issues.append("Noise-like spectrum detected - data may be artifacts, not EEG")
                    # Don't invalidate, but warn
        except Exception as e:
            print(f"[DATA QUALITY] Error checking spectral properties: {e}")
        
        # Store quality assessment
        self._data_quality_valid = data_quality_valid
        self._data_quality_issues = data_quality_issues
        
        if data_quality_issues:
            print("\n" + "="*70)
            print("⚠️  DATA QUALITY WARNINGS:")
            for issue in data_quality_issues:
                print(f"    • {issue}")
            print("="*70 + "\n")
        
        # Default to eyes-closed baseline if available
        chosen_baseline_label = 'eyes_closed' if len(ec_features) > 0 else 'eyes_open'
        baseline_source_features = ec_features if chosen_baseline_label == 'eyes_closed' else eo_features
        
        # Initialize block-equalized variables (may be set later by KM computation)
        eb_eq = None
        et_eq = None
        
        baseline_df = pd.DataFrame(baseline_source_features) if baseline_source_features else None
        task_df = pd.DataFrame(task_features)

        print("\n=== BASELINE DATA ANALYSIS ===")
        print(f"Eyes-Closed (EC) windows: {len(ec_features)}")
        print(f"Eyes-Open (EO) windows: {len(eo_features)}")
        print(f"Task windows: {len(task_features)}")
        print(f"Total baseline features computed: {len(self.baseline_stats)}")
        print(f"Chosen baseline: {chosen_baseline_label} ({len(baseline_source_features)} windows)")

        if hasattr(self, 'baseline_kept') and hasattr(self, 'baseline_rejected'):
            total_ec = self.baseline_kept + self.baseline_rejected
            if total_ec > 0:
                keep_rate = (self.baseline_kept / total_ec) * 100.0
                print(f"EC Quality Control: {self.baseline_kept} kept, {self.baseline_rejected} rejected ({keep_rate:.1f}% keep rate)")

        available_features = [f for f in task_df.columns if f in self.baseline_stats]
        preferred_features = [f for f in available_features if f.endswith('_relative') or ('ratio' in f)] or available_features

        self.analysis_results = {}
        p_for_combo: List[float] = []
        combo_features: List[str] = []
        effect_sizes: List[float] = []
        composite_contrib: List[float] = []
        per_feature_perm: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

        total_features = len(available_features)
        processed_features = 0
        # Emit initial feature progress so UI moves immediately
        print(f"[ENGINE] About to emit initial feature progress: task={self.current_task or 'task'}, total={total_features}")
        print(f"[ENGINE] Feature callback registered: {self._feature_progress_callback is not None}")
        try:
            if self._feature_progress_callback is not None:
                print(f"[ENGINE] Calling feature callback with: task={self.current_task or 'task'}, done=0, total={total_features}")
                self._feature_progress_callback(self.current_task or 'task', 0, total_features)
                print(f"[ENGINE] Initial feature callback emitted successfully")
        except Exception as e:
            import traceback
            print(f"[ENGINE] Feature callback error: {e}")
            print(f"[ENGINE] Traceback: {traceback.format_exc()}")
        for feature in available_features:
            if baseline_df is None or feature not in baseline_df.columns:
                # Mark as NA if no baseline available
                self.analysis_results[feature] = {
                    'delta': np.nan,
                    'percent_change': np.nan,
                    'effect_size_d': np.nan,
                    'p_value': 1.0,
                    'significant_change': False,
                    'reason': 'NA (no baseline)'
                }
                continue
            if getattr(self, '_analysis_cancelled', False):
                print("⚠️ Analysis cancelled during feature loop; returning partial results.")
                break
            
            # Check if this is a gamma feature that was guarded out
            is_gamma = feature.startswith('gamma_')
            gamma_guarded = False
            if is_gamma:
                # Check if gamma was evaluated in task windows
                gamma_eval_flags = [int(f.get('_gamma_evaluated', 1)) for f in task_features if isinstance(f, dict)]
                gamma_guarded = all(f == 0 for f in gamma_eval_flags) if gamma_eval_flags else False
                if gamma_guarded:
                    self.analysis_results[feature] = {
                        'delta': np.nan,
                        'percent_change': np.nan,
                        'effect_size_d': np.nan,
                        'p_value': 1.0,
                        'significant_change': False,
                        'reason': 'Guarded-out (EMG)',
                        'gamma_evaluated': False,
                    }
                    continue
            
            # Use BLOCK SUMMARIES for consistent unit with SumP and ESS
            # Extract block-level values for this feature
            if eb_eq and et_eq:  # Use equalized blocks from KM computation
                task_block_vals = np.asarray([blk.get(feature) for blk in et_eq if feature in blk and np.isfinite(blk.get(feature))], dtype=float)
                base_block_vals = np.asarray([blk.get(feature) for blk in eb_eq if feature in blk and np.isfinite(blk.get(feature))], dtype=float)
            else:
                # Fallback: use all windows if blocks aren't available
                task_block_vals = np.asarray(task_df[feature].dropna().values, dtype=float)
                base_block_vals = np.asarray(baseline_df[feature].dropna().values, dtype=float)
            
            # Require minimal sample sizes per group to ensure stable inference
            if task_block_vals.size < 3 or base_block_vals.size < 3:
                self.analysis_results[feature] = {
                    'delta': np.nan,
                    'percent_change': np.nan,
                    'effect_size_d': np.nan,
                    'p_value': 1.0,
                    'significant_change': False,
                    'reason': f'Insufficient samples (task={task_block_vals.size}, base={base_block_vals.size})'
                }
                continue

            b_mean = float(np.mean(base_block_vals))
            b_std = float(np.std(base_block_vals) + 1e-12)
            t_mean = float(np.mean(task_block_vals))
            t_std = float(np.std(task_block_vals) + 1e-12)

            var_task = float(np.var(task_block_vals, ddof=1)) if task_block_vals.size > 1 else 0.0
            var_base = float(np.var(base_block_vals, ddof=1)) if base_block_vals.size > 1 else 0.0
            pooled = float(np.sqrt(max(0.0, (var_task + var_base) / 2.0)))
            degenerate_var = pooled <= 1e-12
            d = 0.0 if degenerate_var else (t_mean - b_mean) / (pooled + 1e-12)
            effect_sizes.append(abs(d))

            # Bootstrapped 95% CI for Cohen's d (optional, controlled by config)
            d_ci_lower = np.nan
            d_ci_upper = np.nan
            if getattr(self.config, 'compute_bootstrap_ci', True) and not degenerate_var:
                try:
                    n_boot = getattr(self.config, 'bootstrap_ci_samples', 1000)
                    rng = self._get_rng()
                    _, d_ci_lower, d_ci_upper = self._bootstrap_cohens_d_ci(
                        task_block_vals, base_block_vals,
                        n_bootstrap=n_boot, ci_level=0.95, rng=rng
                    )
                except Exception:
                    pass  # Keep NaN on failure

            try:
                if degenerate_var:
                    t_stat, p_val = 0.0, 1.0
                else:
                    t_stat, p_val = self._welch_ttest(task_block_vals, base_block_vals)
            except Exception:
                t_stat, p_val = 0.0, 1.0

            z = (t_mean - b_mean) / (b_std + 1e-12)
            ratio = (t_mean / (abs(b_mean) + 1e-12)) if b_mean != 0 else np.inf
            pct = ((t_mean - b_mean) / (abs(b_mean) + 1e-12)) * 100.0

            effect_value = self._compute_effect_value(feature, t_mean, self.baseline_stats)
            discretized = self._discretize(feature, effect_value, baseline_df)

            result_entry = {
                'task_mean': t_mean,
                'task_std': t_std,
                'baseline_mean': b_mean,
                'baseline_std': b_std,
                'delta': t_mean - b_mean,
                'z_score': z,
                'effect_size_d': d,
                'd_ci_lower': d_ci_lower,  # 95% CI lower bound (bootstrap)
                'd_ci_upper': d_ci_upper,  # 95% CI upper bound (bootstrap)
                'effect_measure': effect_value,
                'percent_change': pct,
                'baseline_task_ratio': ratio,
                'p_value': p_val,
                'p_value_welch': p_val,
                't_stat': float(t_stat),
                'discrete_index': discretized['discrete_index'],
                'discretization_bins': discretized['bins'],
                'log2_ratio': float(np.log2(abs(ratio) + 1e-12)) if np.isfinite(ratio) else np.inf,
                'significant_change': False,  # updated post-FDR or heuristics
                'bin_sig': 0,
                'reason': None,  # Will be set if degenerate or guarded
                'gamma_evaluated': True,  # Default true; overridden for guarded gamma
                'n_blocks_task': int(task_block_vals.size),  # Log actual unit count
                'n_blocks_baseline': int(base_block_vals.size),
            }
            
            # Add reason if degenerate variance
            if degenerate_var:
                result_entry['reason'] = 'Degenerate variance (pooled ≈ 0)'

            self.analysis_results[feature] = result_entry
            combo_features.append(feature)
            p_for_combo.append(float(np.nan_to_num(p_val, nan=1.0)))
            composite_contrib.append(float(np.nan_to_num(p_val, nan=1.0)))
            per_feature_perm[feature] = (task_block_vals, base_block_vals)  # Use blocks for permutation too
            processed_features += 1
            # Feature-level progress strategy:
            #  - Always emit for the first 10 features to guarantee early visible motion even for huge datasets
            #  - After that, if large dataset (> 100 features), throttle to every 5; else every feature
            #  - Always emit on completion
            if self._feature_progress_callback is not None:
                emit = False
                if processed_features <= 10:
                    emit = True
                elif total_features <= 100:
                    emit = True
                elif (processed_features % 5) == 0:
                    emit = True
                if processed_features == total_features:
                    emit = True
                if emit:
                    try:
                        self._feature_progress_callback(self.current_task or 'task', processed_features, total_features)
                    except Exception:
                        pass

        if not self.analysis_results:
            print("❌ ERROR: No overlapping features between baseline and task for analysis")
            return None

        corr_guard_factor = self._correlation_guard_factor(baseline_df, combo_features)
        eff_feature_count = self._effective_feature_count(baseline_df, combo_features) if combo_features else 0.0
        local_alpha = max(1e-9, self.config.alpha * corr_guard_factor)
        fdr_alpha = max(1e-9, self.config.fdr_alpha * corr_guard_factor)
        if combo_features:
            rejected, q_vals = self._bh_fdr(p_for_combo, alpha=fdr_alpha)
        else:
            rejected, q_vals = [], []

        significant_flags: List[bool] = []
        for idx, feature in enumerate(combo_features):
            entry = self.analysis_results[feature]
            q_val = q_vals[idx] if idx < len(q_vals) else None
            entry['q_value'] = q_val
            p_two = entry.get('p_value')
            t_stat = float(entry.get('t_stat', 0.0))
            expected = self._expected_direction(self.current_task, feature)
            p_dir = p_two
            delta = float(entry.get('delta', 0.0))
            dir_ok = True
            if expected == 'up':
                p_dir = (p_two / 2.0) if p_two is not None and t_stat > 0 else (1.0 - (p_two or 1.0) / 2.0)
                dir_ok = delta > 0
            elif expected == 'down':
                p_dir = (p_two / 2.0) if p_two is not None and t_stat < 0 else (1.0 - (p_two or 1.0) / 2.0)
                dir_ok = delta < 0
            
            # Store one-sided p when directional prior exists
            entry['p_one_sided'] = p_dir if expected else p_two
            entry['expected_direction'] = expected
            
            d_thr, pct_thr = self._thresholds_for_feature(feature)
            effect_ok = (abs(entry.get('effect_size_d', 0.0)) >= d_thr) and dir_ok
            pct_ok = (abs(entry.get('percent_change', 0.0)) >= pct_thr) and dir_ok
            p_ok = (p_dir is not None) and (p_dir <= local_alpha) and dir_ok
            q_ok = (q_val is not None) and (q_val <= fdr_alpha)
            pass_rule = None
            decision = False
            if p_ok:
                decision = True
                pass_rule = 'p'
            if not decision and effect_ok:
                decision = True
                pass_rule = 'd'
            if not decision and pct_ok:
                decision = True
                pass_rule = 'pct'
            entry['significant_change'] = decision
            entry['bin_sig'] = 1 if decision else 0
            entry['decision_flags'] = {
                'p_pass': p_ok,
                'p_one_sided': p_dir,
                'q_pass': q_ok,
                'effect_pass': effect_ok,
                'percent_pass': pct_ok,
                'bh_rejected': rejected[idx] if idx < len(rejected) else False,
                'expected_direction': expected,
                'direction_ok': dir_ok,
                'pass_rule': pass_rule,
            }
            entry['thresholds'] = {
                'alpha': local_alpha,
                'fdr_alpha': fdr_alpha,
                'min_effect_size': d_thr,
                'min_percent_change': pct_thr,
                'correlation_guard_factor': corr_guard_factor,
            }
            significant_flags.append(decision)

        sig_feature_count = int(np.sum(significant_flags))
        sig_prop = sig_feature_count / max(1, len(combo_features)) if combo_features else 0.0

        fisher_stat, fisher_p_naive = self._fishers_method(p_for_combo)
        # Build non-overlapping blocks for KM correlation and block permutation
        try:
            base_timestamps = self.calibration_data.get(chosen_baseline_label, {}).get('timestamps', [])
            base_blocks = self._build_blocks(baseline_source_features, base_timestamps)
            task_timestamps = self.calibration_data.get('task', {}).get('timestamps', [])
            task_blocks = self._build_blocks(task_features, task_timestamps)
            # Equalize for correlation estimation
            eb, et = self._equalize_blocks(base_blocks, task_blocks)
            km_corr = self._block_spearman_corr(eb, et, combo_features)
        except Exception:
            km_corr = None
            eb, et = [], []
        km_stat, fisher_p_km, fisher_df, km_mean_r = self._km_from_corr(fisher_stat, km_corr)
        
        # Log KM correlation details (Task F)
        k = len(combo_features) if combo_features else 0
        km_df_ratio = float(fisher_df / max(1.0, 2.0 * k)) if k > 0 and fisher_df else None
        if km_mean_r is not None and k > 1:
            try:
                log_fn = getattr(self, 'log_message', None)
                msg = (
                    f"KM correlation: k={k}, mean_offdiag_r={km_mean_r:.4f}, "
                    f"df_KM={fisher_df:.2f}, df_KM/(2k)={km_df_ratio:.3f}"
                )
                if callable(log_fn):
                    log_fn(msg)
                else:
                    print(f"[ENGINE] {msg}")
            except Exception:
                pass
        
        fisher_sig = fisher_p_km < self.config.alpha if fisher_p_km is not None else False

        # Block-based SumP permutation (ALWAYS RUN if n_perm > 0, regardless of mode)
        observed_sum = None
        sum_p_perm_p = None
        perm_used = False
        ess_blocks = None
        perm_meta = {}
        try:
            # Build per-feature block means for permutation
            per_feature_blocks: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
            # Equalize to ensure matched exposure for permutation
            eb_eq, et_eq = self._equalize_blocks(base_blocks, task_blocks)
            ess_blocks = float(min(len(eb_eq), len(et_eq))) if eb_eq and et_eq else 0.0
            if ess_blocks and combo_features:
                for f in combo_features:
                    tb = np.asarray([blk.get(f) for blk in et_eq if f in blk and np.isfinite(blk.get(f))], dtype=float)
                    bb = np.asarray([blk.get(f) for blk in eb_eq if f in blk and np.isfinite(blk.get(f))], dtype=float)
                    if tb.size > 0 and bb.size > 0:
                        per_feature_blocks[f] = (tb, bb)
            # Run permutations if we have any valid features with blocks
            if per_feature_blocks and self.config.n_perm > 0:
                observed_sum, sum_p_perm_p, perm_used, _ess, perm_meta = self._permutation_sum_p_blocks(per_feature_blocks)
                if ess_blocks == 0.0:
                    ess_blocks = _ess
            elif self.config.n_perm > 0 and combo_features:
                # Log why permutations didn't run
                print(f"[SumP Skip] No valid blocks for permutation (ess_blocks={ess_blocks}, combo_features={len(combo_features)}, per_feature_blocks={len(per_feature_blocks)})")
        except Exception as e:
            print(f"[SumP Block Error] {e}")
            import traceback
            traceback.print_exc()
        sum_p_sig = (sum_p_perm_p is not None) and (sum_p_perm_p < self.config.alpha)
        sum_p_approx_flag = False
        if observed_sum is not None and sum_p_perm_p is None:
            k = len(p_for_combo)
            if k > 0:
                mean = k / 2.0
                var = k / 12.0
                if var > 0:
                    from math import erfc, sqrt
                    z = (observed_sum - mean) / np.sqrt(var)
                    sum_p_perm_p = 0.5 * erfc(z / np.sqrt(2.0))
                    sum_p_sig = sum_p_perm_p < self.config.alpha
                    sum_p_approx_flag = True

        composite_score = None
        if combo_features:
            # =====================================================================
            # COMPOSITE SCORE FORMULA (explicit per methodology review)
            # 
            # CompositeScore = Σ -log10(q_i)
            # 
            # Where q_i is the FDR-adjusted p-value (Benjamini-Hochberg) for feature i.
            # If q_value is not available, raw p_value is used.
            # Values are floored at 1e-12 to prevent infinity.
            #
            # This is a RANKING metric, not a formal test statistic. Use Fisher's
            # combined p-value (km_p) for statistical inference.
            # =====================================================================
            adjusted_values = []
            for feature in combo_features:
                entry = self.analysis_results[feature]
                val = entry['q_value'] if entry.get('q_value') is not None else entry['p_value']
                adjusted_values.append(max(val, 1e-12))
            composite_score = float(np.sum(-np.log10(adjusted_values)))

        mean_effect_size = float(np.mean(effect_sizes)) if effect_sizes else None

        cosine_sim = cosine_dist = cosine_p = None
        try:
            base_vec = np.array([self.baseline_stats[f]['mean'] for f in combo_features], dtype=float)
            task_vec = np.array([self.analysis_results[f]['task_mean'] for f in combo_features], dtype=float)
            base_norm = base_vec / (np.linalg.norm(base_vec) + 1e-12)
            task_norm = task_vec / (np.linalg.norm(task_vec) + 1e-12)
            cosine_sim = float(np.dot(base_norm, task_norm))
            cosine_dist = float(1.0 - cosine_sim)
            perms = int(max(1, min(getattr(self.config, 'n_perm', 1000), 5000)))
            rng = self._get_rng()
            exceed = 0
            for _ in range(perms):
                shuf = rng.permutation(base_vec)
                shuf_norm = shuf / (np.linalg.norm(shuf) + 1e-12)
                sim = float(np.dot(task_norm, shuf_norm))
                if (1.0 - sim) >= cosine_dist:
                    exceed += 1
            cosine_p = (exceed + 1.0) / (perms + 1.0) if perms > 0 else 1.0
        except Exception:
            pass

        decision_block = {
            'enabled': True,
            'sig_feature_count': sig_feature_count,
            'sig_prop': sig_prop,
            'alpha': local_alpha,
            'fdr_alpha': fdr_alpha,
            'correlation_guard_factor': corr_guard_factor,
            'correlation_guard_active': self.config.correlation_guard,
            'effective_feature_count': eff_feature_count,
            'nominal_feature_count': len(combo_features),
            'bh_rejections': int(np.sum(rejected)) if rejected else 0,
            'min_effect_size': self.config.min_effect_size,
            'min_percent_change': self.config.min_percent_change,
        }

        self.task_summary = {
            'fisher': {
                'stat': fisher_stat,
                'p_naive': fisher_p_naive,
                'km_stat': km_stat,
                'km_p': fisher_p_km,
                'km_df': fisher_df,
                'km_df_ratio': km_df_ratio,
                'km_mean_r': km_mean_r,
                'k_features': k,
                'significant': fisher_sig,
                'alpha': self.config.alpha,
            },
            'sum_p': {
                'value': observed_sum,
                'perm_p': sum_p_perm_p,
                'significant': sum_p_sig,
                'permutation_used': perm_used,
                'approximate': sum_p_approx_flag,
                'metadata': perm_meta,
            },
            'permutation': {
                'preset': getattr(self.config, 'runtime_preset', None),
                'n_perm': int(getattr(self.config, 'n_perm', 0)),
                'seed': getattr(self.config, 'seed', None),
            },
            'ess': {
                'block_seconds': float(self.block_seconds),
                'baseline_blocks': int(ess_blocks) if ess_blocks is not None else None,
                'task_blocks': int(ess_blocks) if ess_blocks is not None else None,
            },
            'feature_selection': decision_block,
            'composite': {
                'score': composite_score,
                'ranking_only': True,
            },
            'cosine': {
                'similarity': cosine_sim,
                'distance': cosine_dist,
                'p_value': cosine_p,
            },
            'effect_size_mean': mean_effect_size,
            'expectation': self._evaluate_expectation_alignment(self.current_task),
        }

        # =====================================================================
        # SANITY CHECK: Flag suspicious results that indicate data quality issues
        # =====================================================================
        # If >70% of features are "significant", the data is likely noise/garbage
        # Real cognitive tasks typically affect 5-30% of features
        SUSPICIOUS_SIG_THRESHOLD = 0.70  # 70% significant = likely garbage data
        WARNING_SIG_THRESHOLD = 0.50     # 50% significant = suspicious
        
        data_quality_warnings = []
        results_reliable = True
        
        if sig_prop > SUSPICIOUS_SIG_THRESHOLD:
            data_quality_warnings.append(
                f"CRITICAL: {sig_prop*100:.1f}% of features marked significant - "
                f"this exceeds the {SUSPICIOUS_SIG_THRESHOLD*100:.0f}% threshold and strongly suggests "
                "the data is noise/garbage, not real EEG. The headset may not have been worn."
            )
            results_reliable = False
        elif sig_prop > WARNING_SIG_THRESHOLD:
            data_quality_warnings.append(
                f"WARNING: {sig_prop*100:.1f}% of features marked significant - "
                f"this is unusually high (>{WARNING_SIG_THRESHOLD*100:.0f}%) and may indicate data quality issues."
            )
        
        # Check if data quality validation failed earlier
        if hasattr(self, '_data_quality_valid') and not self._data_quality_valid:
            data_quality_warnings.extend(getattr(self, '_data_quality_issues', []))
            results_reliable = False
        
        # Store in task_summary
        self.task_summary['data_quality'] = {
            'reliable': results_reliable,
            'warnings': data_quality_warnings,
            'sig_prop': sig_prop,
            'sig_count': sig_feature_count,
            'total_features': len(combo_features),
        }
        
        if data_quality_warnings:
            print("\n" + "="*70)
            print("⚠️  RESULTS RELIABILITY WARNING:")
            for warning in data_quality_warnings:
                print(f"    {warning}")
            if not results_reliable:
                print("\n    ❌ RESULTS MARKED AS UNRELIABLE")
                print("    These results should NOT be interpreted as valid EEG analysis.")
            print("="*70 + "\n")

        self.composite_summary = self.task_summary
        if getattr(self, '_analysis_cancelled', False):
            try:
                self.task_summary['partial'] = True
            except Exception:
                pass
        self._prepare_exports()
        return self.analysis_results

    def _prepare_exports(self) -> None:
        full_features = {}
        masked_features = {}
        integer_features = {}
        for feature, data in self.analysis_results.items():
            feature_entry = {
                'task_mean': data.get('task_mean'),
                'baseline_mean': data.get('baseline_mean'),
                'delta': data.get('delta'),
                'effect_measure': data.get('effect_measure'),
                'discrete_index': data.get('discrete_index'),
                'discretization_bins': data.get('discretization_bins'),
                'p_value': data.get('p_value'),
                'q_value': data.get('q_value'),
                'bin_sig': data.get('bin_sig'),
            }
            full_features[feature] = feature_entry
            if self.config.is_feature_selection and not data.get('bin_sig'):
                masked_features[feature] = {
                    'effect_measure': 0.0,
                    'discrete_index': 0,
                    'bin_sig': 0,
                }
            else:
                masked_features[feature] = {
                    'effect_measure': data.get('effect_measure'),
                    'discrete_index': data.get('discrete_index'),
                    'bin_sig': data.get('bin_sig'),
                }
            integer_features[feature] = {
                'discrete_index': data.get('discrete_index'),
                'bin_sig': data.get('bin_sig'),
            }
        summary_core = {
            'Fisher_KM_sig': self.task_summary['fisher']['significant'] if 'fisher' in self.task_summary else False,
            'SumP_sig': self.task_summary['sum_p']['significant'] if 'sum_p' in self.task_summary else False,
            'sig_feature_count': self.task_summary.get('feature_selection', {}).get('sig_feature_count') if self.task_summary.get('feature_selection') else None,
        }
        self.last_export_full = {
            'features': full_features,
            'masked_features': masked_features,
            'summary': self.task_summary,
            'summary_core': summary_core,
        }
        self.last_export_integer = {
            'features': integer_features,
            'summary_core': summary_core,
        }

    def analyze_all_tasks_data(self):
        """Analyze each recorded task separately and also combined across all tasks."""
        if not getattr(self, 'baseline_stats', None) or not self.baseline_stats:
            try:
                self.compute_baseline_statistics()
            except Exception:
                pass

        raw_tasks = self.calibration_data.get('tasks', {}) or {}
        log_fn = getattr(self, 'log_message', None)
        normalized_tasks: Dict[str, Dict[str, Any]] = {}
        skipped_tasks: List[Tuple[str, str]] = []
        for task_name, raw_data in raw_tasks.items():
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
                try:
                    if callable(log_fn):
                        log_fn(msg)
                    else:
                        print(f"[ENGINE] {msg}")
                except Exception:
                    print(f"[ENGINE] {msg}")
        tasks = normalized_tasks
        if not tasks:
            msg = "Multi-task analysis skipped: no tasks with valid feature data were recorded."
            try:
                if callable(log_fn):
                    log_fn(msg)
                else:
                    print(f"[ENGINE] {msg}")
            except Exception:
                print(f"[ENGINE] {msg}")
            self.multi_task_results = {
                'per_task': {},
                'combined': {
                    'analysis': {},
                    'summary': {},
                    'export_full': {},
                    'export_integer': {},
                },
                'across_task': {},
            }
            return self.multi_task_results

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
        # Total steps for general progress: each individual task + 1 combined step
        total_general_steps = len(tasks) + 1
        # Emit initial progress (0 completed) so UI can move off 0% immediately
        try:
            if self._general_progress_callback is not None:
                self._general_progress_callback(0, total_general_steps)
        except Exception:
            pass
        current_step = 0
        try:
            for task_name, data in tasks.items():
                task_bucket['features'] = list(data.get('features', []))
                task_bucket['timestamps'] = list(data.get('timestamps', []))
                self.current_task = task_name
                analysis = self.analyze_task_data() or {}
                summary = copy.deepcopy(getattr(self, 'task_summary', {}))
                exports_full = copy.deepcopy(getattr(self, 'last_export_full', {}))
                exports_int = copy.deepcopy(getattr(self, 'last_export_integer', {}))
                per_task_results[task_name] = {
                    'analysis': copy.deepcopy(analysis),
                    'summary': summary,
                    'export_full': exports_full,
                    'export_integer': exports_int,
                }
                current_step += 1
                # Emit general progress after each task
                try:
                    if self._general_progress_callback is not None:
                        self._general_progress_callback(current_step, total_general_steps)
                except Exception:
                    pass
        finally:
            task_bucket['features'] = original_task_features
            task_bucket['timestamps'] = original_task_timestamps
            self.current_task = None

        combined_features = []
        combined_timestamps = []
        for data in tasks.values():
            combined_features.extend(list(data.get('features', [])))
            combined_timestamps.extend(list(data.get('timestamps', [])))
        task_bucket['features'] = combined_features
        task_bucket['timestamps'] = combined_timestamps
        self.current_task = 'combined'
        combined_analysis = self.analyze_task_data() or {}
        combined_summary = copy.deepcopy(getattr(self, 'task_summary', {}))
        combined_exports_full = copy.deepcopy(getattr(self, 'last_export_full', {}))
        combined_exports_int = copy.deepcopy(getattr(self, 'last_export_integer', {}))

        # Emit final general progress step (combined)
        try:
            current_step = total_general_steps
            if self._general_progress_callback is not None:
                self._general_progress_callback(current_step, total_general_steps)
        except Exception:
            pass

        # Restore current task bucket after combined
        task_bucket['features'] = original_task_features
        task_bucket['timestamps'] = original_task_timestamps
        self.current_task = None

        across_task = self._analyze_across_tasks(tasks)

        # =====================================================================
        # CROSS-TASK FAMILY-WISE ERROR CORRECTION (Holm-Bonferroni)
        # Apply Holm-Bonferroni correction to per-task omnibus p-values to control
        # family-wise error rate when running multiple tasks.
        # =====================================================================
        cross_task_correction = {}
        if len(per_task_results) >= 2:
            task_names = list(per_task_results.keys())
            omnibus_pvals = []
            for t in task_names:
                summary = per_task_results[t].get('summary', {})
                fisher = summary.get('fisher', {})
                km_p = fisher.get('km_p')
                if km_p is not None and isinstance(km_p, (int, float)):
                    omnibus_pvals.append(float(km_p))
                else:
                    omnibus_pvals.append(1.0)  # Missing p-value treated as non-significant
            
            # Apply Holm-Bonferroni step-down correction
            rejected, adjusted_pvals = self._holm_bonferroni(omnibus_pvals, alpha=self.config.alpha)
            
            # Store corrected results
            for i, t in enumerate(task_names):
                per_task_results[t]['summary']['fisher']['km_p_fwer'] = adjusted_pvals[i]
                per_task_results[t]['summary']['fisher']['fwer_significant'] = rejected[i]
            
            cross_task_correction = {
                'method': 'Holm-Bonferroni',
                'n_tasks': len(task_names),
                'alpha': self.config.alpha,
                'raw_pvals': dict(zip(task_names, omnibus_pvals)),
                'adjusted_pvals': dict(zip(task_names, adjusted_pvals)),
                'significant_tasks': [t for t, sig in zip(task_names, rejected) if sig],
            }

        self.multi_task_results = {
            'per_task': per_task_results,
            'combined': {
                'analysis': copy.deepcopy(combined_analysis),
                'summary': combined_summary,
                'export_full': combined_exports_full,
                'export_integer': combined_exports_int,
            },
            'across_task': across_task,
            'cross_task_correction': cross_task_correction,
        }
        return self.multi_task_results

    def _analyze_across_tasks(self, tasks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        if not tasks or len(tasks) < 2:
            return {}
        if not self.baseline_stats:
            return {}

        log_fn = getattr(self, 'log_message', None)
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
            if valid_task_names:
                msg = "Cross-task analysis requires at least two tasks with valid feature data."
            else:
                msg = "Cross-task analysis skipped: no tasks contained valid feature data."
            try:
                if callable(log_fn):
                    log_fn(msg)
                else:
                    print(f"[ENGINE] {msg}")
            except Exception:
                print(f"[ENGINE] {msg}")
            return {}

        if skipped:
            skipped_msg = ", ".join(skipped)
            msg = f"Omitting task(s) without valid feature data from cross-task comparison: {skipped_msg}."
            try:
                if callable(log_fn):
                    log_fn(msg)
                else:
                    print(f"[ENGINE] {msg}")
            except Exception:
                print(f"[ENGINE] {msg}")

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
        # Determine min sessions across tasks (equalized block counts)
        # NOTE: Currently uses blocks (8s aggregates) not true session counts.
        # This means 1 task execution with 20 windows → ~2-3 blocks, bypassing Nmin guard.
        # TODO: Track session boundaries for true session-level omnibus.
        per_task_blocks: Dict[str, List[Dict[str, Any]]] = {}
        for task in task_names:
            flist = valid_tasks[task]['features']
            tlist = valid_tasks[task].get('timestamps', [])
            per_task_blocks[task] = self._build_blocks(flist, tlist)
        # Equalize sessions count by trimming to min length across tasks
        min_sessions = min(len(v) for v in per_task_blocks.values()) if per_task_blocks else 0
        
        # Log block counts per task for diagnosis
        print(f"[Across-Task] Tasks: {len(task_names)}, Block counts: {{{', '.join([f'{t}:{len(per_task_blocks[t])}' for t in task_names])}}}, min={min_sessions}")
        
        if min_sessions < self.nmin_sessions:
            # Ranking-only mode: insufficient sessions for significance testing
            msg = (
                f"⚠ Across-task significance testing disabled: "
                f"N={min_sessions} sessions < Nmin={self.nmin_sessions}. "
                f"Showing descriptive rankings only (median effect per task)."
            )
            try:
                if callable(log_fn):
                    log_fn(msg)
                else:
                    print(f"[ENGINE] {msg}")
            except Exception:
                print(f"[ENGINE] {msg}")
            
            ranking_only: Dict[str, Any] = {}
            for feature in sorted(common_features):
                arrays = []
                for task in task_names:
                    vals = [blk.get(feature) for blk in per_task_blocks[task] if feature in blk]
                    arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
                    stats = self.baseline_stats[feature]
                    mean = float(stats['mean'])
                    std = float(stats['std'])
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

        for feature in sorted(common_features):
            # Build per-task effect arrays for this feature; some tasks may have fewer
            # usable block values (e.g., EMG-guarded gamma removed). Equalize lengths
            # per-feature to avoid column_stack dimension mismatches.
            raw_arrays = []
            for task in task_names:
                vals = [blk.get(feature) for blk in per_task_blocks[task] if feature in blk]
                arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
                stats = self.baseline_stats[feature]
                mean = float(stats['mean'])
                std = float(stats['std'])
                eff = (arr - mean) / (std + 1e-12) if self.config.effect_measure == 'z' else (arr - mean)
                raw_arrays.append(eff)
            if not raw_arrays:
                continue
            # Determine equalized row count for this feature across tasks
            per_feature_rows = min((a.size for a in raw_arrays), default=0)
            # Also respect the global min_sessions cap
            n_rows = min(per_feature_rows, min_sessions)
            if n_rows < 2:
                # Not enough paired observations for omnibus
                continue
            per_task_arrays = [a[:n_rows] for a in raw_arrays]
            data_matrix = np.column_stack(per_task_arrays)

            method_used = self.config.omnibus
            if self.config.omnibus == 'RM-ANOVA' and _scipy_f_oneway is not None:
                try:
                    stat, p_val = _scipy_f_oneway(*[data_matrix[:, i] for i in range(data_matrix.shape[1])])
                    method_used = 'RM-ANOVA (approx)'
                except Exception:
                    stat, p_val = self._friedman_test(data_matrix)
                    method_used = 'Friedman (fallback)'
            else:
                stat, p_val = self._friedman_test(data_matrix)
                method_used = 'Friedman'

            omnibus_pvalues.append(p_val)

            pairwise_indices: List[Tuple[int, int]] = []
            pairwise_pvals: List[float] = []
            num_tasks = len(task_names)
            for i in range(num_tasks):
                for j in range(i + 1, num_tasks):
                    diff = data_matrix[:, i] - data_matrix[:, j]
                    if self.config.posthoc == 'Wilcoxon' and _scipy_wilcoxon is not None:
                        try:
                            _, p_pair = _scipy_wilcoxon(diff)
                        except Exception:
                            p_pair = self._sign_test_pvalue(diff)
                    else:
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
                'method': method_used,
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


class EnhancedBrainLinkAnalyzerWindow(BL.BrainLinkAnalyzerWindow):
    battery_update = QtCore.Signal(object, object)

    def __init__(self, user_os, parent=None, config: Optional[EnhancedAnalyzerConfig] = None):
        self.user_os = user_os
        self._normalized_os = (user_os or "").strip().lower()
        self.config = config or EnhancedAnalyzerConfig()
        # Provide fallback methods BEFORE base __init__ so signal connections succeed
        if not hasattr(self, 'manual_rescan_devices'):
            def _manual_rescan_devices_fallback():
                try:
                    base_method = getattr(super(EnhancedBrainLinkAnalyzerWindow, self), 'manual_rescan_devices', None)
                    if base_method:
                        return base_method()
                    self.log_message("Manual rescan not available in this build.")
                except Exception as e:
                    # Can't log yet (log_message not set); print fallback
                    try:
                        print(f"Manual rescan error (early): {e}")
                    except Exception:
                        pass
            self.manual_rescan_devices = _manual_rescan_devices_fallback  # type: ignore

        if not hasattr(self, 'prompt_for_device_identifiers'):
            def _prompt_for_device_identifiers_fallback():
                try:
                    self.log_message("Identifier prompt not available in this build.")
                except Exception:
                    pass
                return False
            self.prompt_for_device_identifiers = _prompt_for_device_identifiers_fallback  # type: ignore

        if not hasattr(self, 'manual_enter_port'):
            def _manual_enter_port_fallback():
                try:
                    self.log_message("Manual port entry not available in this build.")
                except Exception:
                    pass
            self.manual_enter_port = _manual_enter_port_fallback  # type: ignore

        # Initialize base window, then swap the engine
        super().__init__(user_os, parent)
        self._battery_level = None
        self._battery_version = None
        self._battery_warning_flag = False
        self._pending_battery_update = None
        self._battery_widget = None
        self.battery_status_label = None
        self.battery_progress = None
        self.battery_update.connect(self._apply_battery_update)
        self.feature_engine = EnhancedFeatureAnalysisEngine(config=self.config)
        # Re-link onRaw to the new engine
        BL.onRaw.feature_engine = self.feature_engine
        # Task UI state
        self._task_dialog = None
        self._task_timer = None
        self._task_seconds_remaining = 0
        self._modal_overlay = None
        self._overlay_refcount = 0
        self._modal_blur_effect = None
        self._battery_widgets: List[Dict[str, Any]] = []
        self._primary_battery_entry: Optional[Dict[str, Any]] = None
        self._task_overlay_active = False

        # ---- LED stimulator controller (for 40 Hz photic task) ----
        self._led_stimulator = None
        try:
            if _LEDStimulatorController is not None:
                self._led_stimulator = _LEDStimulatorController(
                    frequency=40.0, duration=150.0, task=1
                )
        except Exception as _led_err:
            print(f"[LED] Could not create LED stimulator controller: {_led_err}")

        try:
            self._setup_enhanced_multi_task_tab()
        except Exception:
            # Keep base tab if enhanced setup fails
            pass

        try:
            self._build_stage_header()
        except Exception:
            pass

        try:
            # Ensure the guided workflow starts from the connection tab every launch
            self._reset_workflow_progress()
        except Exception:
            pass
        
        # Apply modern styling & toolbar after base UI creation
        try:
            self._apply_modern_ui()
            self._create_toolbar()
        except Exception:
            pass
        # Also place a compact battery pill in the tab bar corner so it's always visible next to the tabs
        try:
            if hasattr(self, 'tabs') and self.tabs is not None:
                pill = self._build_battery_indicator()
                # Top-right corner of the tab bar
                self.tabs.setCornerWidget(pill, QtCore.Qt.TopRightCorner)
        except Exception:
            pass
        self._attach_extended_eeg_bridge()
        self._apply_battery_update(self._battery_level, self._battery_version)

        # CRITICAL: Ensure we have a real MindLink device connected
        if not BL.SERIAL_PORT:
            self.log_message("CRITICAL ERROR: No real MindLink device found!")
            self.log_message("This enhanced analyzer requires real EEG data - dummy data is NOT acceptable!")
            self.log_message("Please connect your MindLink device and restart the application.")
            # Keep UI visible but disable analysis-related controls until connected
            try:
                if hasattr(self, 'eyes_closed_button'):
                    self.eyes_closed_button.setEnabled(False)
                if hasattr(self, 'eyes_open_button'):
                    self.eyes_open_button.setEnabled(False)
                if hasattr(self, 'task_button'):
                    self.task_button.setEnabled(False)
                if hasattr(self, 'compute_baseline_button'):
                    self.compute_baseline_button.setEnabled(False)
                if hasattr(self, 'analyze_task_button'):
                    self.analyze_task_button.setEnabled(False)
                if hasattr(self, 'generate_report_button'):
                    self.generate_report_button.setEnabled(False)
            except Exception:
                pass
        else:
            self.log_message(f"SUCCESS: Connected to real MindLink device: {BL.SERIAL_PORT}")
            self.log_message("Real EEG data acquisition is active - no dummy data allowed!")
        
        self._fixation_dialog = None
        self._audio = AudioFeedback(user_os)
        # Video playback members
        self._video_player = None  # type: ignore
        self._video_audio = None  # type: ignore
        self._video_widget = None  # type: ignore
        self._current_video_phase = False

        # Protocol groups mapping (two protocol-specific tasks per group)
        self._protocol_groups = {
            'Personal Pathway': ['emotion_face', 'diverse_thinking'],
            'Connection': ['reappraisal', 'curiosity'],
            'Lifestyle': ['order_surprise', 'num_form'],
        }
        # Cognitive tasks (always included)
        # Restore full cognitive task set so all are available across match types
        self._cognitive_tasks = [
            'visual_imagery', 'attention_focus', 'mental_math', 'working_memory',
            'language_processing', 'motor_imagery', 'cognitive_load', '40hz_stimulation'
        ]
        self._selected_protocol = None
        # Preserve all available tasks so we can filter UI list later
        try:
            self._all_task_keys = list(getattr(BL, 'AVAILABLE_TASKS', {}).keys())
        except Exception:
            self._all_task_keys = []

        # Gate single-task analysis so it only runs when explicitly requested
        self._allow_immediate_task_analysis = False

        # Remove (hide) legacy manual device / port buttons if base created them
        for _btn_name in ("rescan_button", "manual_port_button"):
            try:
                _btn = getattr(self, _btn_name, None)
                if _btn is not None:
                    _btn.hide()
            except Exception:
                pass

        # change_protocol_button created in setup_analysis_tab override

        # FIX PLOTTING ISSUE: Replace standard curve with PlotCurveItem and strict ranges
        try:
            # First, remove any existing plot setup from base class
            if hasattr(self, 'live_curve') and self.live_curve is not None:
                try:
                    self.plot_widget.removeItem(self.live_curve)
                except Exception:
                    pass
            
            # Apply debug_plot.py EXACT working configuration
            self.plot_widget.setBackground('#000000')  # Black background like debug_plot
            
            # Get plot item directly (debug_plot approach)
            plot_item = self.plot_widget.getPlotItem()
            plot_item.showGrid(x=True, y=True, alpha=0.3)
            plot_item.setLabel('left', 'Amplitude (µV)')
            plot_item.setLabel('bottom', 'Sample Index')
            plot_item.setXRange(0, 1024, padding=0)
            plot_item.setYRange(-100, 100, padding=0)
            
            # Create a HIGH-CONTRAST pen (explicit QColor) to avoid any theme/aliasing invisibility
            try:
                from PySide6.QtGui import QColor as _QColor  # type: ignore
            except Exception:
                try:
                    from PyQt6.QtGui import QColor as _QColor  # type: ignore
                except Exception:
                    _QColor = None
            try:
                pen_color = _QColor(255, 255, 0) if _QColor else 'yellow'  # bright yellow
                # Non-cosmetic pen sometimes renders more reliably on some GPUs / scaling setups
                pen = pg.mkPen(color=pen_color, width=3, style=QtCore.Qt.PenStyle.SolidLine, cosmetic=False)
            except Exception:
                try:
                    pen = pg.mkPen(color='yellow', width=3)
                except Exception:
                    pen = pg.mkPen(width=3)
            
            # Create curve using plot item directly (debug_plot approach)  
            x_init = np.array([0, 512, 1024], dtype=float)
            y_init = np.array([0.0, 0.0, 0.0], dtype=float)
            self.live_curve = plot_item.plot(x_init, y_init, pen=pen)
            try:
                # Ensure on top of grid
                self.live_curve.setZValue(10)
            except Exception:
                pass
            
            # Disable autorange completely
            try:
                plot_item.enableAutoRange('x', False)
                plot_item.enableAutoRange('y', False)
                plot_item.setMouseEnabled(x=True, y=True)  # Keep zoom/pan enabled
                self.plot_widget.enableAutoRange(enable=False)
            except Exception:
                pass
                
            print("✅ Enhanced GUI plot setup complete using debug_plot.py approach")
            
        except Exception as e:
            print(f"❌ Enhanced GUI plot setup failed: {e}")
            # Keep the base plot if enhanced setup fails
            
            # Set fixed ranges like legacy code
            try:
                window_size = 1024
                if len(BL.live_data_buffer) >= 50:
                    # Always show the last 1024 samples (or fewer if not enough yet)
                    plot_size = min(window_size, len(BL.live_data_buffer))
                    data = np.array(BL.live_data_buffer[-plot_size:], dtype=np.float64)
                    # Pad with zeros if not enough data yet
                    if plot_size < window_size:
                        pad = np.zeros(window_size - plot_size)
                        data = np.concatenate([pad, data])
                    x_data = np.arange(window_size, dtype=float)
                    self.live_curve.setData(x_data, data)
                    # Set x range to always [0, 1024]
                    y_min, y_max = float(np.min(data)), float(np.max(data))
                    y_range = y_max - y_min
                    if y_range < 1e-6:
                        y_min -= 25.0
                        y_max += 25.0
                        y_range = y_max - y_min
                    padding = max(y_range * 0.1, 10.0)
                    try:
                        view_box = self.plot_widget.getPlotItem().vb
                        view_box.setRange(
                            xRange=[0, window_size],
                            yRange=[y_min - padding, y_max + padding],
                            padding=0,
                            update=True
                        )
                        self.plot_widget.setXRange(0, window_size, padding=0)
                        self.plot_widget.setYRange(y_min - padding, y_max + padding, padding=0)
                    except Exception:
                        try:
                            vb = self.plot_widget.getPlotItem().vb
                            vb.setYRange(y_min - padding, y_max + padding)
                            vb.setXRange(0, window_size)
                        except Exception:
                            pass
                    try:
                        if not self.plot_widget.isVisible():
                            self.plot_widget.setVisible(True)
                        if hasattr(self.live_curve, 'isVisible') and not self.live_curve.isVisible():
                            self.live_curve.setVisible(True)
                    except Exception:
                        pass
                    # Update status label
                    try:
                        self.status_label.setText(
                            f"Buffer: {len(BL.live_data_buffer)} samples | "
                            f"Latest: {data[-1]:.1f} µV")
                    except Exception:
                        pass
                else:
                    # Waiting for more data (following legacy pattern)
                    if len(BL.live_data_buffer) > 0:
                        self.status_label.setText(
                            f"Buffer: {len(BL.live_data_buffer)} samples | "
                            f"Latest: {BL.live_data_buffer[-1]:.1f} µV | "
                            f"Need {50 - len(BL.live_data_buffer)} more samples")
                    else:
                        self.status_label.setText("Waiting for data...")
            except Exception as e:
                try:
                    self.status_label.setText(f"Plot update issue: {e}")
                except Exception:
                    pass
        except Exception:
            pass

        task_n = len(self.feature_engine.calibration_data.get('task', {}).get('features', []))
        ec_n = len(self.feature_engine.calibration_data.get('eyes_closed', {}).get('features', []))
        eo_n = len(self.feature_engine.calibration_data.get('eyes_open', {}).get('features', []))

        lines: List[str] = []
        lines.append(f"Windows: EC={ec_n}, EO={eo_n}, Task={task_n}")

        # Baseline summary
        if getattr(self.feature_engine, 'baseline_stats', None):
            lines.append("")
            lines.append("Baseline Summary (key features)")
            lines.append("-" * 60)
            key_feats = [
                'alpha_relative', 'theta_relative', 'beta_relative', 'alpha_theta_ratio', 'beta_alpha_ratio', 'total_power'
            ]
            for feat in key_feats:
                stats = self.feature_engine.baseline_stats.get(feat)
                if stats:
                    lines.append(f"{feat:22} mean={stats['mean']:.6g}  std={stats['std']:.6g}")

        # Task-level decisions if an analysis already ran
        summary = getattr(self.feature_engine, 'task_summary', None)
        if summary:
            fisher = summary.get('fisher', {})
            sum_p = summary.get('sum_p', {})
            feature_sel = summary.get('feature_selection') or {}
            composite = summary.get('composite', {}) or {}
            cosine = summary.get('cosine', {}) or {}
            effect_mean = summary.get('effect_size_mean')
            lines.append("")
            lines.append("Task-Level Decisions")
            lines.append("-" * 60)
            lines.append(
                f"Fisher_KM_p={fisher.get('km_p')} sig={fisher.get('significant')} | naive={fisher.get('p_naive')}"
            )
            lines.append(
                f"SumP={sum_p.get('value')} | p={sum_p.get('perm_p')} sig={sum_p.get('significant')}"
            )
            if self.feature_engine.config.is_feature_selection:
                lines.append(
                    f"sig_feature_count={feature_sel.get('sig_feature_count')} | sig_prop={feature_sel.get('sig_prop')}"
                )
            lines.append(f"Composite score (ranking only)={composite.get('score')} | Mean |d|={effect_mean}")
            lines.append(
                f"Cosine similarity={cosine.get('similarity')} | distance={cosine.get('distance')} | p={cosine.get('p_value')}"
            )

        # Per-feature details
        results = getattr(self.feature_engine, 'analysis_results', {}) or {}
        if results:
            lines.append("")
            lines.append("Per-Feature Statistics")
            lines.append("-" * 60)
            items: List[Tuple[float, float, str, Dict[str, Any]]] = []
            for feat_name, vals in results.items():
                p_val = vals.get('p_value', vals.get('p_value_welch', 1.0))
                eff = float(abs(vals.get('effect_size_d', 0.0)))
                items.append((p_val, -eff, feat_name, vals))
            items.sort(key=lambda item: (item[0], item[1]))
            for p_val, _neg_eff, feat_name, vals in items:
                bm = vals.get('baseline_mean')
                bs = vals.get('baseline_std')
                tm = vals.get('task_mean')
                tsd = vals.get('task_std')
                pct = vals.get('percent_change')
                ratio = vals.get('baseline_task_ratio')
                log2r = vals.get('log2_ratio')
                z = vals.get('z_score')
                eff = vals.get('effect_size_d')
                sig = vals.get('significant_change')
                lines.append(
                    f"{feat_name:24} task={(tm if tm is not None else 0):.6g}±{(tsd if tsd is not None else 0):.6g} | "
                    f"base={(bm if bm is not None else 0):.6g}±{(bs if bs is not None else 0):.6g} | Δ%={(pct if pct is not None else 0):.3g} | "
                    f"ratio={(ratio if ratio is not None else 0):.3g} log2={(log2r if log2r is not None else 0):.3g} | z={(z if z is not None else 0):.3g} "
                    f"d={(eff if eff is not None else 0):.3g} | p={p_val:.3g} q={vals.get('q_value')} | sig={sig}"
                )
        else:
            lines.append("")
            lines.append("No task analysis yet. Collect a task and press Analyze to populate details.")

        text = "\n".join(lines)
        try:
            self.analysis_summary.setPlainText(text)
            self.analysis_summary.setVisible(True)
            self.log_message("✓ Report generated")
        except Exception:
            pass
        # NOTE: File save dialog removed from constructor - only show when user explicitly requests it

    def _attach_extended_eeg_bridge(self) -> None:
        """Route MindLink extended EEG packets into the enhanced UI."""
        try:
            current_cb = getattr(BL, 'onExtendEEG')
        except AttributeError:
            return
        if not callable(current_cb):
            return
        if hasattr(current_cb, '_enhanced_original'):
            try:
                current_cb._enhanced_window_ref = weakref.ref(self)  # type: ignore[attr-defined]
            except Exception:
                pass
            return

        original_cb = current_cb

        def _proxy(data, _orig=original_cb):
            window_ref = getattr(_proxy, '_enhanced_window_ref', None)
            window = window_ref() if window_ref else None
            if window is not None:
                try:
                    window._handle_extended_eeg(data)
                except Exception:
                    pass
            if _orig is not None:
                try:
                    _orig(data)
                except Exception:
                    pass

        _proxy._enhanced_original = original_cb  # type: ignore[attr-defined]
        _proxy._enhanced_window_ref = weakref.ref(self)  # type: ignore[attr-defined]
        BL.onExtendEEG = _proxy

    def _handle_extended_eeg(self, data: Any) -> None:
        battery_val = getattr(data, 'battery', None)
        firmware = getattr(data, 'version', None)
        try:
            if battery_val is not None:
                battery_val = int(float(battery_val))
        except Exception:
            battery_val = None
        self.battery_update.emit(battery_val, firmware)

    def _apply_battery_update(self, level: Optional[int], version: Optional[Any]) -> None:
        if level is not None:
            try:
                level = max(0, min(100, int(level)))
            except Exception:
                level = None
        if level is not None:
            self._battery_level = level
        if version is not None:
            self._battery_version = version
        entries = getattr(self, '_battery_widgets', [])
        if not entries:
            self._pending_battery_update = (self._battery_level, self._battery_version)
            return

        self._pending_battery_update = None

        active_level = self._battery_level
        tooltip_parts: List[str] = []
        if active_level is None:
            bar_value = 0
            bar_style = self._battery_stylesheet(None)
            label_text = "Battery --%"
            tooltip_parts.append("Battery level pending")
            self._battery_warning_flag = False
        else:
            bar_value = active_level
            bar_style = self._battery_stylesheet(active_level)
            label_text = f"Battery {active_level}%"
            tooltip_parts.append(f"{active_level}% remaining")
            if active_level <= 20:
                if not self._battery_warning_flag:
                    self._battery_warning_flag = True
                    try:
                        self.log_message("⚠ MindLink battery low – please recharge soon.")
                    except Exception:
                        pass
            else:
                self._battery_warning_flag = False

        if self._battery_version is not None:
            tooltip_parts.append(f"FW v{self._battery_version}")
        tooltip_text = " | ".join(tooltip_parts) if tooltip_parts else ""

        # Ensure backward compatibility helpers point at primary entry
        primary = getattr(self, '_primary_battery_entry', None)
        if primary is not None:
            self._battery_widget = primary.get('container')
            self.battery_status_label = primary.get('label')
            self.battery_progress = primary.get('progress')

        for entry in list(entries):
            bar = entry.get('progress')
            label = entry.get('label')
            container = entry.get('container')
            if bar is None or label is None:
                continue
            try:
                bar.setRange(0, 100)
                bar.setValue(bar_value)
                bar.setStyleSheet(bar_style)
                label.setText(label_text)
            except Exception:
                continue
            try:
                for widget in (container, label, bar):
                    if widget is not None:
                        widget.setToolTip(tooltip_text)
            except Exception:
                pass

    def _battery_stylesheet(self, level: Optional[int]) -> str:
        if level is None:
            chunk = "#94a3b8"
        elif level >= 60:
            chunk = "#16a34a"
        elif level >= 30:
            chunk = "#f59e0b"
        else:
            chunk = "#dc2626"
        return (
            "QProgressBar {"
            " background-color: #f1f5f9;"
            " border: 1px solid #d0d7de;"
            " border-radius: 6px;"
            " padding: 0;"
            " }"
            "QProgressBar::chunk {"
            f" background-color: {chunk};"
            " border-radius: 5px;"
            " }"
        )

    def _build_battery_indicator(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        container.setObjectName("BatteryIndicator")
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        label = QLabel("Battery --%")
        # Make battery text bold and high-contrast (black) so it's readable on status bars
        label.setStyleSheet("color: #000000; font-size: 10px; font-weight: 800;")
        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        bar.setFixedWidth(110)
        bar.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        bar.setStyleSheet(self._battery_stylesheet(None))

        layout.addWidget(label, alignment=QtCore.Qt.AlignLeft)
        layout.addWidget(bar)

        container.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)

        entry = {
            'container': container,
            'label': label,
            'progress': bar,
        }
        if not hasattr(self, '_battery_widgets'):
            self._battery_widgets = []
        self._battery_widgets.append(entry)

        if getattr(self, '_primary_battery_entry', None) is None:
            self._primary_battery_entry = entry
            self._battery_widget = container
            self.battery_status_label = label
            self.battery_progress = bar

        def _cleanup(_obj=None, entry_ref=entry):
            try:
                if entry_ref in self._battery_widgets:
                    self._battery_widgets.remove(entry_ref)
            except Exception:
                pass
            if getattr(self, '_primary_battery_entry', None) is entry_ref:
                self._primary_battery_entry = self._battery_widgets[0] if self._battery_widgets else None
                primary = self._primary_battery_entry
                if primary is not None:
                    self._battery_widget = primary.get('container')
                    self.battery_status_label = primary.get('label')
                    self.battery_progress = primary.get('progress')
                else:
                    self._battery_widget = None
                    self.battery_status_label = None
                    self.battery_progress = None

        try:
            container.destroyed.connect(_cleanup)
        except Exception:
            pass

        tooltip_default = "Battery level will appear once the headset streams telemetry."
        label.setToolTip(tooltip_default)
        bar.setToolTip(tooltip_default)
        container.setToolTip(tooltip_default)

        if self._pending_battery_update is not None:
            pending = self._pending_battery_update
            self._pending_battery_update = None
            self._apply_battery_update(*pending)
        else:
            self._apply_battery_update(self._battery_level, self._battery_version)

        return container

    def _push_modal_overlay(self) -> Optional[QtWidgets.QWidget]:
        """Dim the main window and apply a soft blur while a modal dialog is active.
        Mirrors the working workflow dialog overlay by using a child frame that
        stays stacked directly above the main window content.
        """
        try:
            count = getattr(self, '_overlay_refcount', 0)
            if count <= 0:
                overlay = QtWidgets.QFrame(self)
                overlay.setObjectName("ModalOverlay")
                overlay.setGeometry(self.rect())
                overlay.setStyleSheet("background-color: rgba(15, 23, 42, 200);")
                overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
                overlay.setFocusPolicy(QtCore.Qt.NoFocus)
                overlay.setFrameShape(QtWidgets.QFrame.NoFrame)
                overlay.show()
                overlay.raise_()
                self._modal_overlay = overlay
                central = self.centralWidget()
                if central is not None:
                    blur = QtWidgets.QGraphicsBlurEffect(self)
                    blur.setBlurRadius(11.0)
                    central.setGraphicsEffect(blur)
                    self._modal_blur_effect = blur
            self._overlay_refcount = count + 1
        except Exception:
            pass
        return getattr(self, '_modal_overlay', None)

    def _pop_modal_overlay(self) -> None:
        try:
            count = getattr(self, '_overlay_refcount', 0)
            if count <= 1:
                overlay = getattr(self, '_modal_overlay', None)
                if overlay is not None:
                    overlay.hide()
                    overlay.deleteLater()
                self._modal_overlay = None
                central = self.centralWidget()
                if central is not None and getattr(self, '_modal_blur_effect', None) is not None:
                    try:
                        central.setGraphicsEffect(None)
                    except Exception:
                        pass
                blur_effect = getattr(self, '_modal_blur_effect', None)
                if blur_effect is not None:
                    blur_effect.deleteLater()
                self._modal_blur_effect = None
                self._overlay_refcount = 0
            else:
                self._overlay_refcount = count - 1
        except Exception:
            pass

    def _register_task_dialog(self, dlg: QtWidgets.QDialog) -> None:
        """Ensure dimming overlay & cleanup hooks surround task dialog lifecycle."""
        if dlg is None:
            return
        try:
            self._task_overlay_active = True
        except Exception:
            pass
        try:
            dlg.finished.connect(self._on_task_dialog_finished)
        except Exception:
            pass
        try:
            dlg.destroyed.connect(lambda *_: self._on_task_dialog_finished())
        except Exception:
            pass

    def _release_task_overlay(self) -> None:
        if getattr(self, '_task_overlay_active', False):
            self._task_overlay_active = False
            try:
                self._pop_modal_overlay()
            except Exception:
                pass

    def _on_task_dialog_finished(self, *_args: Any) -> None:
        try:
            if self._task_dialog is not None:
                try:
                    self._task_dialog.deleteLater()
                except Exception:
                    pass
        finally:
            self._task_dialog = None
        self._release_task_overlay()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        try:
            super().resizeEvent(event)
        finally:
            overlay = getattr(self, '_modal_overlay', None)
            if overlay is not None:
                try:
                    overlay.setGeometry(self.rect())
                except Exception:
                    pass

    def _setup_enhanced_multi_task_tab(self) -> None:
        """Replace the base multi-task tab with the enhanced workflow scaffold."""

        def _clear_layout(layout_obj: Optional[QtWidgets.QLayout]) -> None:
            if layout_obj is None:
                return
            while layout_obj.count():
                item = layout_obj.takeAt(0)
                child_widget = item.widget()
                if child_widget is not None:
                    child_widget.setParent(None)
                child_layout = item.layout()
                if child_layout is not None:
                    _clear_layout(child_layout)

        try:
            tab = self.tabs.widget(self.multi_task_tab_index)
        except Exception:
            tab = None

        if tab is None:
            tab = QWidget()
            self.multi_task_tab_index = self.tabs.addTab(tab, "Multi-Task")

        layout = tab.layout()
        if layout is None:
            layout = QVBoxLayout(tab)
        else:
            _clear_layout(layout)

        layout.setSpacing(18)
        layout.setContentsMargins(20, 20, 20, 20)

        intro = QLabel("Run aggregated insights after completing the guided task flow.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#374151; font-weight:600;")
        layout.addWidget(intro)

        steps = QLabel(
            "1. Finish baseline and the tasks in the Analysis section.\n"
            "2. Press 'Analyze All Tasks' to compute the features.\n"
            "3. Generate the combined report for export."
        )
        steps.setWordWrap(True)
        steps.setStyleSheet("color:#4b5563;")
        layout.addWidget(steps)

        self.analyze_all_button = QPushButton("Analyze All Tasks")
        self.analyze_all_button.setEnabled(False)
        self.analyze_all_button.setFixedHeight(52)
        self.analyze_all_button.clicked.connect(self.analyze_all_tasks)
        layout.addWidget(self.analyze_all_button)

        self.generate_all_report_button = QPushButton("Generate Report (All Tasks)")
        self.generate_all_report_button.setEnabled(False)
        self.generate_all_report_button.setFixedHeight(52)
        self.generate_all_report_button.clicked.connect(self.generate_report_all_tasks)
        layout.addWidget(self.generate_all_report_button)

        self.multi_task_text = QTextEdit()
        self.multi_task_text.setReadOnly(True)
        self.multi_task_text.setVisible(False)
        self.multi_task_text.setPlaceholderText(
            "Run 'Analyze All Tasks' after completing individual analyses to see combined insights."
        )
        layout.addWidget(self.multi_task_text)

        layout.addStretch()

    def _build_stage_header(self) -> None:
        """Create a staged header so only the active workflow panel is presented."""
        if getattr(self, '_stage_widget', None) is not None:
            return

        central = self.centralWidget()
        if central is None:
            return
        layout = central.layout()
        if layout is None:
            return

        # Stage order mirrors the original tabs
        self._stage_order: List[Tuple[int, str]] = [
            (self.connection_tab_index, "Connect"),
            (self.analysis_tab_index, "Tasks"),
            (self.multi_task_tab_index, "Multi-Task"),
        ]
        self._stage_states: Dict[int, str] = {idx: "ready" for idx, _ in self._stage_order}
        self._stage_status_overrides: Dict[int, str] = {}
        self._stage_labels: List[Dict[str, Any]] = []

        stage_widget = QWidget()
        stage_widget.setObjectName("StageHeader")
        stage_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        stage_layout = QHBoxLayout(stage_widget)
        stage_layout.setContentsMargins(0, 0, 0, 12)
        stage_layout.setSpacing(12)

        for idx, (tab_idx, label_text) in enumerate(self._stage_order):
            card = QWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)

            title_lbl = QLabel(label_text)
            title_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#1f2937;")
            status_lbl = QLabel("In progress" if idx == 0 else "Ready")
            status_lbl.setStyleSheet("font-size:11px; color:#6b7280;")

            card_layout.addWidget(title_lbl)
            card_layout.addWidget(status_lbl)
            card_layout.addStretch()

            stage_layout.addWidget(card)
            self._stage_labels.append({
                "card": card,
                "title": title_lbl,
                "status": status_lbl,
            })

        stage_layout.addStretch()

        try:
            battery_widget = self._build_battery_indicator()
            stage_layout.addWidget(battery_widget, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        except Exception:
            pass

        # Insert the stage widget right beneath the main header label
        layout.insertWidget(1, stage_widget)
        self._stage_widget = stage_widget

        # Initial state: connection active, others marked ready
        self._stage_states[self.connection_tab_index] = "active"
        self._refresh_stage_header()

    def _refresh_stage_header(self) -> None:
        if not hasattr(self, '_stage_labels'):
            return

        for (tab_idx, _), label_dict in zip(self._stage_order, self._stage_labels):
            state = self._stage_states.get(tab_idx, "ready")
            status_override = self._stage_status_overrides.get(tab_idx)
            title_lbl = label_dict["title"]
            status_lbl = label_dict["status"]
            card_widget = label_dict["card"]

            if state == "active":
                status_lbl.setText(status_override or "In progress")
                card_widget.setStyleSheet("background:#eff6ff; border:1px solid #3b82f6; border-radius:10px;")
                title_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#1d4ed8;")
                status_lbl.setStyleSheet("font-size:11px; color:#1d4ed8;")
            elif state == "done":
                status_lbl.setText(status_override or "Complete")
                card_widget.setStyleSheet("background:#ecfdf5; border:1px solid #34d399; border-radius:10px;")
                title_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#047857;")
                status_lbl.setStyleSheet("font-size:11px; color:#047857;")
            else:
                status_lbl.setText(status_override or "Ready")
                card_widget.setStyleSheet("background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;")
                title_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#475569;")
                status_lbl.setStyleSheet("font-size:11px; color:#64748b;")

    def _set_stage(self, tab_index: int) -> None:
        if not hasattr(self, '_stage_order'):
            return
        try:
            order_index = next(i for i, (idx, _) in enumerate(self._stage_order) if idx == tab_index)
        except StopIteration:
            return

        for pos, (idx, _) in enumerate(self._stage_order):
            if pos < order_index:
                self._stage_states[idx] = "done"
            elif pos == order_index:
                self._stage_states[idx] = "active"
            else:
                if self._stage_states.get(idx) != "done":
                    self._stage_states[idx] = "ready"

        try:
            if self.tabs.currentIndex() != tab_index:
                self.tabs.setCurrentIndex(tab_index)
        except Exception:
            pass

        self._stage_status_overrides.pop(tab_index, None)
        self._refresh_stage_header()

    def _mark_stage_done(self, tab_index: int, status_text: Optional[str] = None) -> None:
        if not hasattr(self, '_stage_order'):
            return
        if tab_index not in dict(self._stage_order):
            return
        self._stage_states[tab_index] = "done"
        if status_text is not None:
            self._stage_status_overrides[tab_index] = status_text
        self._refresh_stage_header()

    def _reset_workflow_progress(self):
        super()._reset_workflow_progress()
        if not hasattr(self, '_stage_states'):
            return
        for idx in list(self._stage_states.keys()):
            self._stage_states[idx] = "ready"
        self._stage_status_overrides.clear()
        self._set_stage(self.connection_tab_index)

    def handle_proceed_to_analysis(self):
        super().handle_proceed_to_analysis()
        self._set_stage(self.analysis_tab_index)

    def update_results_display(self, results):
        """Extend base summary handling with enhanced multi-task gating."""
        super().update_results_display(results)
        self._set_stage(self.multi_task_tab_index)
        try:
            if getattr(self, "analyze_all_button", None):
                self.analyze_all_button.setEnabled(True)
            if getattr(self, "generate_all_report_button", None):
                # Enable after combined analysis runs
                self.generate_all_report_button.setEnabled(False)
            if getattr(self, "multi_task_text", None):
                self.multi_task_text.setVisible(True)
                self.multi_task_text.setPlainText(
                    "Press 'Analyze All Tasks' to compute combined insights across completed sessions."
                )
        except Exception:
            pass

    def _apply_modern_ui(self):
        """Apply a clean, modern white-background design for commercial-grade UX."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        try:
            app.setStyle('Fusion')
        except Exception:
            pass
        
        # High DPI scaling
        try:
            QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
        except Exception:
            pass
        
        # Modern white palette with professional accents
        pal = QPalette()
        white = QColor(255, 255, 255)
        off_white = QColor(250, 250, 250)
        light_gray = QColor(240, 240, 240)
        border_gray = QColor(220, 220, 220)
        text_dark = QColor(33, 33, 33)
        text_gray = QColor(117, 117, 117)
        accent_blue = QColor(0, 120, 212)  # Modern blue accent
        hover_blue = QColor(16, 137, 234)
        
        pal.setColor(QPalette.Window, white)
        pal.setColor(QPalette.Base, white)
        pal.setColor(QPalette.AlternateBase, off_white)
        pal.setColor(QPalette.WindowText, text_dark)
        pal.setColor(QPalette.Text, text_dark)
        pal.setColor(QPalette.Button, light_gray)
        pal.setColor(QPalette.ButtonText, text_dark)
        pal.setColor(QPalette.Highlight, accent_blue)
        pal.setColor(QPalette.HighlightedText, white)
        pal.setColor(QPalette.Disabled, QPalette.ButtonText, text_gray)
        pal.setColor(QPalette.Disabled, QPalette.WindowText, text_gray)
        pal.setColor(QPalette.Disabled, QPalette.Text, text_gray)
        
        try:
            app.setPalette(pal)
        except Exception:
            pass
        
        # Modern font
        try:
            target_os = getattr(self, '_normalized_os', '')
            font_family = 'Segoe UI'
            font_size = 10
            if 'mac' in target_os:
                font_family = 'SF Pro Text'
                font_size = 11
            elif 'linux' in target_os:
                font_family = 'Noto Sans'
            base_font = QFont(font_family, font_size)
            app.setFont(base_font)
        except Exception:
            pass
        
        # Clean modern stylesheet with white background
        qss = """
        QMainWindow { 
            background: #ffffff; 
        }
        QStatusBar { 
            background: #fafafa; 
            color: #333333; 
            border-top: 1px solid #dcdcdc; 
            padding: 4px;
        }
        QToolBar { 
            background: #ffffff; 
            border-bottom: 1px solid #e0e0e0; 
            spacing: 8px; 
            padding: 4px 8px;
        }
        QToolButton { 
            background: transparent; 
            border: 0; 
            padding: 8px 12px; 
            border-radius: 6px;
            color: #333333;
        }
        QToolButton:hover { 
            background: #f0f0f0; 
        }
        QToolButton:pressed { 
            background: #e0e0e0; 
        }
        QPushButton { 
            background: #0078d4; 
            color: white; 
            border: 0; 
            padding: 8px 20px; 
            border-radius: 6px; 
            font-weight: 600;
            font-size: 11px;
        }
        QPushButton:hover { 
            background: #1089e8; 
        }
        QPushButton:pressed { 
            background: #006cbe; 
        }
        QPushButton:disabled { 
            background: #f0f0f0; 
            color: #999999; 
        }
        QPushButton#secondary { 
            background: #ffffff; 
            color: #333333; 
            border: 1px solid #dcdcdc;
        }
        QPushButton#secondary:hover { 
            background: #f5f5f5; 
            border: 1px solid #c0c0c0;
        }
        QPushButton#danger {
            background: #d13438;
        }
        QPushButton#danger:hover {
            background: #e13438;
        }
        QGroupBox { 
            border: 1px solid #e0e0e0; 
            border-radius: 8px; 
            margin-top: 16px; 
            padding: 16px 12px 12px 12px; 
            font-weight: 600;
            color: #333333;
            background: #ffffff;
        }
        QGroupBox::title { 
            subcontrol-origin: margin; 
            left: 12px; 
            top: -8px; 
            padding: 0 8px; 
            background: #ffffff;
            color: #333333;
        }
        QTabWidget::pane { 
            border: 1px solid #e0e0e0; 
            border-radius: 8px; 
            top: -1px; 
            background: #ffffff;
        }
        QTabBar::tab { 
            background: #fafafa; 
            padding: 10px 20px; 
            border-top-left-radius: 6px; 
            border-top-right-radius: 6px; 
            margin-right: 4px; 
            color: #757575;
            border: 1px solid #e0e0e0;
            border-bottom: 0;
        }
        QTabBar::tab:selected { 
            background: #ffffff; 
            color: #0078d4;
            font-weight: 600;
            border-bottom: 2px solid #0078d4;
        }
        QTabBar::tab:hover { 
            background: #f5f5f5; 
        }
        QLabel#SectionHeader { 
            font-size: 16px; 
            font-weight: 700; 
            color: #333333;
            padding: 8px 0;
        }
        QLabel#MetricValue {
            font-size: 24px;
            font-weight: 700;
            color: #0078d4;
        }
        QLabel#StatusLabel {
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: 600;
        }
        QLabel#StatusSuccess {
            background: #f3f9f1;
            color: #107c10;
            border: 1px solid #bad5ba;
        }
        QLabel#StatusWarning {
            background: #fff9f5;
            color: #c27500;
            border: 1px solid #fbd7b4;
        }
        QTextEdit, QPlainTextEdit { 
            background: #fafafa; 
            border: 1px solid #e0e0e0; 
            border-radius: 6px; 
            selection-background-color: #0078d4; 
            selection-color: white;
            padding: 8px;
            color: #333333;
        }
        QComboBox { 
            background: #ffffff; 
            padding: 6px 36px 6px 12px; 
            border: 1px solid #dcdcdc; 
            border-radius: 6px;
            color: #333333;
        }
        QComboBox:hover { 
            border: 1px solid #0078d4; 
        }
        QComboBox::drop-down { 
            width: 32px; 
            background: #f2f4f7; 
            border-left: 1px solid #dcdcdc; 
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
            subcontrol-origin: padding;
            subcontrol-position: center right;
        }
        QComboBox::down-arrow {
            image: url(:/qt-project.org/styles/commonstyle/images/down-16.png);
            width: 12px;
            height: 12px;
            margin-right: 10px;
        }
        QComboBox::down-arrow:on {
            image: url(:/qt-project.org/styles/commonstyle/images/down-16.png);
            margin-top: 1px;
        }
        QComboBox::down-arrow:disabled {
            image: url(:/qt-project.org/styles/commonstyle/images/down-16.png);
        }
        QListView { 
            background: #ffffff; 
            border: 1px solid #e0e0e0;
            border-radius: 6px;
        }
        QLineEdit { 
            background: #ffffff; 
            border: 1px solid #dcdcdc; 
            border-radius: 6px; 
            padding: 6px 12px;
            color: #333333;
        }
        QLineEdit:focus {
            border: 1px solid #0078d4;
        }
        QProgressBar { 
            border: 1px solid #e0e0e0; 
            border-radius: 6px; 
            text-align: center; 
            background: #fafafa;
            color: #333333;
        }
        QProgressBar::chunk { 
            background: #0078d4; 
            border-radius: 6px; 
        }
        QScrollBar:vertical { 
            background: #fafafa; 
            width: 12px; 
            margin: 0; 
            border: none; 
        }
        QScrollBar::handle:vertical { 
            background: #c0c0c0; 
            min-height: 24px; 
            border-radius: 6px; 
        }
        QScrollBar::handle:vertical:hover { 
            background: #a0a0a0; 
        }
        QScrollBar:horizontal { 
            background: #fafafa; 
            height: 12px; 
            margin: 0; 
            border: none; 
        }
        QScrollBar::handle:horizontal { 
            background: #c0c0c0; 
            min-width: 24px; 
            border-radius: 6px; 
        }
        QScrollBar::handle:horizontal:hover { 
            background: #a0a0a0; 
        }
        QToolTip { 
            background: #333333; 
            color: white; 
            border: 0; 
            padding: 6px 10px;
            border-radius: 4px;
        }
        """
        try:
            app.setStyleSheet(qss)
        except Exception:
            pass
        
        # Remove window menu bar buttons (keep only essential tabs)
        try:
            self.menuBar().clear()
        except Exception:
            pass
        
        # Update window title
        try:
            self.setWindowTitle("MindLink Analyzer")
        except Exception:
            pass
        
        # Status message
        try:
            if self.statusBar():
                self.statusBar().showMessage("Ready • Modern UI Active", 3000)
        except Exception:
            pass

    def _create_toolbar(self):
        """Create a minimal, clean toolbar with only essential actions."""
        # Remove existing toolbars first
        try:
            for toolbar in self.findChildren(QtWidgets.QToolBar):
                self.removeToolBar(toolbar)
        except Exception:
            pass
        
        # Create main toolbar
        tb = QtWidgets.QToolBar("Main Actions")
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QtCore.QSize(20, 20))
        
        # Connection status indicator
        self.connection_status_label = QLabel("● Disconnected")
        self.connection_status_label.setStyleSheet("color: #d13438; font-weight: 600; padding: 4px 12px;")
        tb.addWidget(self.connection_status_label)
        
        tb.addSeparator()
        
        # Quick access to key functions
        connect_action = QtWidgets.QAction("Connect Device", self)
        connect_action.triggered.connect(self.on_connect_clicked)
        tb.addAction(connect_action)
        
        tb.addSeparator()
        
        # Protocol selector
        protocol_label = QLabel("Protocol:")
        protocol_label.setStyleSheet("padding: 0 8px; color: #757575; font-size: 10px;")
        tb.addWidget(protocol_label)
        
        # Add protocol combo if it exists
        try:
            if hasattr(self, 'protocol_combo'):
                tb.addWidget(self.protocol_combo)
        except Exception:
            pass
        
        # Add spacer to push items to the right
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        tb.addWidget(spacer)
        
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)
        def _act(text, slot, icon_name=None, tip=None):
            act = QtGui.QAction(text, self)
            if icon_name:
                try:
                    icon_path = os.path.join('assets', icon_name)
                    if os.path.exists(icon_path):
                        act.setIcon(QIcon(icon_path))
                except Exception:
                    pass
            if tip:
                act.setToolTip(tip)
                act.setStatusTip(tip)
            try:
                act.triggered.connect(slot)
            except Exception:
                pass
            tb.addAction(act)
            return act
        # Map to existing slots where possible
        if hasattr(self, 'on_connect_clicked'):
            _act('Connect', self.on_connect_clicked, 'connect.png', 'Connect')
        if hasattr(self, 'start_calibration_button') and hasattr(self, 'start_calibration'):
            # Provide generic start baseline action if button exists
            _act('Baseline', lambda: self.start_calibration('eyes_closed'), 'baseline.png', 'Start Eyes-Closed Baseline')
        if hasattr(self, 'start_task_button'):
            _act('Start Task', self.start_task, 'task_start.png', 'Begin selected task')
        if hasattr(self, 'analyze_task_button'):
            _act('Analyze Task', self.analyze_task, 'analyze.png', 'Analyze current task data')
        if hasattr(self, 'analyze_all_button'):
            _act('Analyze All', self.analyze_all_tasks, 'analyze_all.png', 'Analyze all recorded tasks')
        if hasattr(self, 'generate_all_report_button'):
            _act('Report', self.generate_report_all_tasks, 'report.png', 'Generate consolidated report')
        # Spacer stretch via QWidget
        try:
            spacer = QWidget()
            spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            tb.addWidget(spacer)
        except Exception:
            pass
        try:
            tb.addWidget(self._build_battery_indicator())
        except Exception:
            pass

        help_action = QtWidgets.QAction("Help", self)
        help_action.triggered.connect(lambda: QtWidgets.QMessageBox.information(
            self, "Help", "BrainLink Analyzer Professional\n\nConnect your device and follow the protocol steps."
        ))
        tb.addAction(help_action)
        # Protocol change action
        if hasattr(self, '_change_protocol_dialog'):
            _act('Protocol', self._change_protocol_dialog, 'protocol.png', 'Change protocol set')


    def setup_analysis_tab(self):
        """Rebuild analysis layout with task controls beside calibration buttons."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(18)

        cal_group = QtWidgets.QGroupBox()
        cal_group_layout = QtWidgets.QVBoxLayout()
        cal_group_layout.setContentsMargins(18, 16, 18, 16)
        cal_group_layout.setSpacing(14)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(16)

        baseline_col = QtWidgets.QVBoxLayout()
        baseline_col.setSpacing(10)

        eyes_closed_row = QtWidgets.QHBoxLayout()
        eyes_closed_row.setSpacing(8)
        self.eyes_closed_button = QtWidgets.QPushButton("Start Eyes Closed")
        self.eyes_closed_button.setFixedWidth(180)
        self.eyes_closed_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.eyes_closed_button.clicked.connect(lambda: self.start_calibration('eyes_closed'))
        self.eyes_closed_button.setEnabled(False)
        eyes_closed_row.addWidget(self.eyes_closed_button)
        self.eyes_closed_label = QtWidgets.QLabel("Status: Not started")
        eyes_closed_row.addWidget(self.eyes_closed_label)
        eyes_closed_row.addStretch()
        baseline_col.addLayout(eyes_closed_row)

        eyes_open_row = QtWidgets.QHBoxLayout()
        eyes_open_row.setSpacing(8)
        self.eyes_open_button = QtWidgets.QPushButton("Start Eyes Open")
        self.eyes_open_button.setFixedWidth(180)
        self.eyes_open_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.eyes_open_button.clicked.connect(lambda: self.start_calibration('eyes_open'))
        self.eyes_open_button.setEnabled(False)
        eyes_open_row.addWidget(self.eyes_open_button)
        self.eyes_open_label = QtWidgets.QLabel("Status: Not started")
        eyes_open_row.addWidget(self.eyes_open_label)
        eyes_open_row.addStretch()
        baseline_col.addLayout(eyes_open_row)

        task_row = QtWidgets.QHBoxLayout()
        task_row.setSpacing(12)
        task_label = QtWidgets.QLabel("Task:")
        task_row.addWidget(task_label)
        self.task_combo = QtWidgets.QComboBox()
        self.task_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        try:
            available_tasks = list(getattr(BL, 'AVAILABLE_TASKS', {}).keys())
        except Exception:
            available_tasks = []
        if available_tasks:
            self.task_combo.addItems(available_tasks)
        self.task_combo.currentTextChanged.connect(self.update_task_preview)
        task_row.addWidget(self.task_combo)
        self.task_button = QtWidgets.QPushButton("Start Task")
        self.task_button.setEnabled(False)
        self.task_button.clicked.connect(self.start_task)
        task_row.addWidget(self.task_button)
        task_row.addStretch()
        baseline_col.addLayout(task_row)

        top_row.addLayout(baseline_col, 3)

        actions_container = QtWidgets.QWidget()
        actions_container.setFixedWidth(220)
        actions_container.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        actions_col = QtWidgets.QVBoxLayout(actions_container)
        actions_col.setContentsMargins(0, 0, 0, 0)
        actions_col.setSpacing(10)
        self.task_label = QtWidgets.QLabel("Status: Not started")
        self.task_label.setAlignment(Qt.AlignLeft)
        self.task_label.setStyleSheet(
            "padding:6px 12px; border-radius:10px; background:#eef2ff; color:#1e3a8a; font-weight:600;"
        )
        actions_col.addWidget(self.task_label)

        self.stop_button = QtWidgets.QPushButton("Stop Current Phase")
        self.stop_button.setObjectName("secondary")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_calibration)
        actions_col.addWidget(self.stop_button)

        self.change_protocol_button = QtWidgets.QPushButton("Change Protocol")
        self.change_protocol_button.setObjectName("secondary")
        self.change_protocol_button.setToolTip(
            "Switch protocol group (cognitive tasks always retained). Disabled during an active task phase."
        )
        self.change_protocol_button.clicked.connect(self._change_protocol_dialog)  # type: ignore
        actions_col.addWidget(self.change_protocol_button)
        actions_col.addStretch()

        top_row.addWidget(actions_container, 0)

        cal_group_layout.addLayout(top_row)

        self.task_preview = QtWidgets.QTextEdit()
        self.task_preview.setReadOnly(True)
        self.task_preview.setMinimumHeight(320)
        self.task_preview.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.task_preview.setStyleSheet(
            "background-color:#f8fbff; border:1px solid #dbeafe; border-radius:12px;"
        )
        self.task_preview.setPlaceholderText("Select a task to view detailed instructions.")
        cal_group_layout.addWidget(self.task_preview)

        cal_group.setLayout(cal_group_layout)
        layout.addWidget(cal_group)

        status_row = QtWidgets.QHBoxLayout()
        status_row.setSpacing(10)
        status_title = QtWidgets.QLabel("Feature Pipeline:")
        status_title.setStyleSheet("font-weight:600; color:#4b5563;")
        status_row.addWidget(status_title)
        self.feature_status_label = QtWidgets.QLabel("Idle")
        self.feature_status_label.setStyleSheet(
            "padding:6px 14px; border-radius:999px; background:#f1f5f9; color:#475569; font-weight:600;"
        )
        status_row.addWidget(self.feature_status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        self.live_feature_hint = QtWidgets.QLabel("Awaiting live EEG features…")
        self.live_feature_hint.setStyleSheet("color:#64748b; font-size:11px; margin-left:4px;")
        layout.addWidget(self.live_feature_hint)

        layout.addStretch()

        # Hidden legacy widget retained for compatibility with single-task analysis hooks
    # Legacy summary sink retained for downstream calls; keep hidden and size zero
        self.analysis_summary = QtWidgets.QTextEdit(tab)
        self.analysis_summary.setReadOnly(True)
        self.analysis_summary.setMaximumSize(0, 0)
        self.analysis_summary.hide()
        self.analysis_summary.setPlaceholderText("Task insights will appear here once analysis completes.")

        self.analysis_tab_index = self.tabs.addTab(tab, "Analysis")


    def generate_report_all_tasks(self):
        """Generate a consolidated, detailed report across all recorded tasks inspired by protocol_full_test_enhanced.py format."""
        # Check if multi_task_results already exists (from analyze_all_tasks)
        res = getattr(self.feature_engine, 'multi_task_results', None)
        if not res:
            # DO NOT run analysis synchronously - it would block the GUI for seconds/minutes
            # User must run "Analyze All Tasks" first to populate results in background thread
            msg = "No analysis results available.\n\nPlease run 'Analyze All Tasks' first."
            self.multi_task_text.setPlainText(msg)
            self.log_message("⚠ Generate Report requires analysis to be run first")
            QtWidgets.QMessageBox.information(self, "Analysis Required", msg)
            return
        
        lines = []

        # Helper function for safe formatting with improved placeholders
        def _fmt(v, none="NA"):
            if v is None:
                return none
            if isinstance(v, float):
                if math.isnan(v):
                    return none
                return f"{v:.6g}"
            return str(v)
        # Header
        lines.append("MindLink Enhanced Multi-Task Analysis Report")
        lines.append("=" * 72)
        try:
            from datetime import datetime, UTC
            lines.append(f"UTC Timestamp: {datetime.now(UTC).isoformat()}")
        except Exception:
            lines.append(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Baseline info
        try:
            ec_features = self.feature_engine.calibration_data.get('eyes_closed', {}).get('features', [])
            eo_features = self.feature_engine.calibration_data.get('eyes_open', {}).get('features', [])
            tasks = self.feature_engine.calibration_data.get('tasks', {})
            lines.append(f"Baseline EC windows: {len(ec_features)} | EO windows: {len(eo_features)}")
            lines.append(f"Tasks executed: {len(tasks)}")
        except Exception:
            pass
        
        lines.append("")
        lines.append("Per-Task Statistical Summaries")
        lines.append("-" * 40)
        
        # Per-task results
        per_task = res.get('per_task', {})
        for tname in sorted(per_task.keys()):
            tinfo = per_task[tname] or {}
            summary = tinfo.get("summary", {}) if isinstance(tinfo, dict) else {}
            fisher = summary.get("fisher", {})
            sum_p = summary.get("sum_p", {})
            comp = summary.get("composite", {}) or {}
            effect_mean = summary.get("effect_size_mean")
            decision_info = summary.get("feature_selection") or {}
            
            lines.append(f"[{tname}]")
            
            # KM correlation details (Task F)
            km_mean_r = fisher.get('km_mean_r')
            k_features = fisher.get('k_features')
            km_df_ratio = fisher.get('km_df_ratio')
            if km_mean_r is not None and k_features:
                lines.append(f"  KM correlation: k={k_features}, mean_offdiag_r={_fmt(km_mean_r)}, df_KM/(2k)={_fmt(km_df_ratio)}")
            
            lines.append(f"  Fisher_KM_p={_fmt(fisher.get('km_p'))} sig={fisher.get('significant')} df={_fmt(fisher.get('km_df'))}")
            
            # ESS display (Task G)
            perm_meta = sum_p.get('metadata', {})
            ess_baseline = perm_meta.get('ess_baseline')
            ess_task = perm_meta.get('ess_task')
            n_blocks_used = perm_meta.get('n_blocks_used')
            if ess_baseline is not None or ess_task is not None or n_blocks_used is not None:
                lines.append(f"  ESS: baseline={_fmt(ess_baseline)}, task={_fmt(ess_task)}, n_blocks={_fmt(n_blocks_used)}")
            
            lines.append(f"  SumP={_fmt(sum_p.get('value'))} p={_fmt(sum_p.get('perm_p'))} sig={sum_p.get('significant')} perm={sum_p.get('permutation_used')}")
            
            # Consistency banner (Task G): if Fisher_KM~0 but SumP missing
            fisher_p = fisher.get('km_p')
            sump_p = sum_p.get('perm_p')
            if fisher_p is not None and fisher_p > 0.10 and (sump_p is None or sump_p == 0.0):
                lines.append("  ⚠ Consistency note: Fisher_KM~null but SumP not computed or zero")
            
            lines.append(f"  CompositeScore={_fmt(comp.get('score'))} Mean|d|={_fmt(effect_mean)}")
            if decision_info:
                lines.append(
                    "  Decision thresholds (band-specific): "
                    f"p≤{_fmt(decision_info.get('alpha'))}, "
                    f"q≤{_fmt(decision_info.get('fdr_alpha'))}"
                )
                lines.append(
                    "    Effect sizes: α≥0.25, β≥0.35, γ≥0.30, θ≥0.30, ratios≥0.30"
                )
                lines.append(
                    "    Percent change: relative features≥5%, absolute≥10%"
                )
                if decision_info.get('correlation_guard_active'):
                    lines.append(
                        f"  Correlation guard factor={_fmt(decision_info.get('correlation_guard_factor'))} "
                        f"(m_eff={_fmt(decision_info.get('effective_feature_count'))}/{decision_info.get('nominal_feature_count')})"
                    )
            
            # Per-feature detail
            analysis = tinfo.get("analysis", {}) or {}
            if analysis:
                # Build list with significance flag, filtering out gamma features not evaluated
                feat_rows = []
                for fname, data in analysis.items():
                    # Skip gamma features that were guarded out (gamma_evaluated=False)
                    if fname.startswith('gamma_') and not data.get('gamma_evaluated', True):
                        continue
                    
                    p = data.get("p_value")
                    q = data.get("q_value")
                    delta = data.get("delta")
                    eff_d = data.get("effect_size_d")
                    task_mean = data.get("task_mean")
                    base_mean = data.get("baseline_mean")
                    disc = data.get("discrete_index")
                    sig = bool(data.get("significant_change"))
                    feat_rows.append((p if p is not None else 1.0, fname, {
                        "p": p, "q": q, "delta": delta, "d": eff_d,
                        "task_mean": task_mean, "baseline_mean": base_mean,
                        "disc": disc, "sig": sig
                    }))
                feat_rows.sort(key=lambda r: r[0])
                sig_rows = [r for r in feat_rows if r[2]["sig"]]
                
                lines.append("  Significant Features (adjusted thresholds, top 5 shown):")
                if not sig_rows:
                    lines.append("    (none)")
                else:
                    for p, fname, d in sig_rows[:5]:
                        lines.append(
                            f"    {fname}: p={_fmt(d['p'])} q={_fmt(d.get('q'))} Δ={_fmt(d['delta'])} d={_fmt(d['d'])} "
                            f"task_mean={_fmt(d['task_mean'])} base_mean={_fmt(d['baseline_mean'])} bin={d['disc']}"
                        )
                
                # Always include top-5 table (by p-value)
                lines.append("  Top 5 Features (by p-value):")
                for p, fname, d in feat_rows[:5]:
                    ratio = (d['task_mean']/(abs(d['baseline_mean'])+1e-12)) if (d['task_mean'] is not None and d['baseline_mean']) else None
                    lines.append(
                        f"    {fname}: p={_fmt(d['p'])} q={_fmt(d.get('q'))} sig={d['sig']} Δ={_fmt(d['delta'])} d={_fmt(d['d'])} "
                        f"ratio={_fmt(ratio)}"
                    )
            
            # Expectation-alignment analysis (production display)
            exp_result = summary.get('expectation')
            if exp_result:
                lines.append("  ⎯⎯⎯ Expectation-Alignment Analysis ⎯⎯⎯")
                grade = exp_result.get('grade', 'N/A')
                passes = exp_result.get('passes', [])
                drivers = exp_result.get('top_drivers', [])
                counter = exp_result.get('counter_directional', False)
                notes = exp_result.get('notes', [])
                insufficient = exp_result.get('insufficient_metrics', False)
                
                lines.append(f"  Grade: {grade}")
                if insufficient:
                    lines.append("  ⚠ Insufficient metrics for full evaluation (missing d or p_dir on key features)")
                if counter:
                    lines.append("  ⚠ Counter-directional: ≥70% of features moved opposite to task expectations")
                
                lines.append(f"  Passed Features (n={len(passes)}):")
                if not passes:
                    lines.append("    (none)")
                else:
                    for pf in passes:
                        feat_name = pf.get('feature', 'unknown')
                        direction = pf.get('direction', '?')
                        p_dir = pf.get('p_dir')
                        d_val = pf.get('d')
                        pct_val = pf.get('pct')
                        rule = pf.get('rule', 'unknown')
                        d_meets = pf.get('d_meets_thr', False)
                        pct_meets = pf.get('pct_meets_thr', False)
                        
                        criteria_str = []
                        if d_meets:
                            criteria_str.append(f"d={_fmt(d_val)}")
                        if pct_meets:
                            criteria_str.append(f"Δ%={_fmt(pct_val)}")
                        criteria_str.append(f"p_dir={_fmt(p_dir)}")
                        
                        lines.append(f"    {feat_name} ({direction}): {', '.join(criteria_str)} | rule={rule}")
                
                lines.append("  Top Drivers (by |d|):")
                if not drivers:
                    lines.append("    (none)")
                else:
                    for drv in drivers:
                        lines.append(f"    {drv.get('feature', 'unknown')}: |d|={_fmt(drv.get('d'))}")
                
                if notes:
                    lines.append("  Notes:")
                    for note in notes:
                        lines.append(f"    • {note}")
            
            lines.append("")
        
        # Combined aggregate
        lines.append("Combined Task Aggregate")
        lines.append("-" * 30)
        combined = res.get('combined', {})
        comb_summary = combined.get("summary", {})
        combined_analysis = combined.get("analysis", {}) or {}
        fisher_c = comb_summary.get("fisher", {})
        sum_p_c = comb_summary.get("sum_p", {})
        comp_c = comb_summary.get("composite", {}) or {}
        effect_c = comb_summary.get("effect_size_mean")
        decision_c = comb_summary.get("feature_selection") or {}
        lines.append(f"Fisher_KM_p={_fmt(fisher_c.get('km_p'))} sig={fisher_c.get('significant')} df={_fmt(fisher_c.get('km_df'))}")
        lines.append(f"SumP={_fmt(sum_p_c.get('value'))} p={_fmt(sum_p_c.get('perm_p'))} sig={sum_p_c.get('significant')} perm={sum_p_c.get('permutation_used')}")
        lines.append(f"CompositeScore={_fmt(comp_c.get('score'))} Mean|d|={_fmt(effect_c)}")
        if decision_c:
            lines.append(
                "Decision thresholds (band-specific): "
                f"p≤{_fmt(decision_c.get('alpha'))}, "
                f"q≤{_fmt(decision_c.get('fdr_alpha'))}"
            )
            lines.append(
                "  Effect sizes: α≥0.25, β≥0.35, γ≥0.30, θ≥0.30, ratios≥0.30"
            )
            lines.append(
                "  Percent change: relative features≥5%, absolute≥10%"
            )
            if decision_c.get('correlation_guard_active'):
                lines.append(
                    f"Correlation guard factor={_fmt(decision_c.get('correlation_guard_factor'))} "
                    f"(m_eff={_fmt(decision_c.get('effective_feature_count'))}/{decision_c.get('nominal_feature_count')})"
                )
        lines.append("")
        
        # Across-task omnibus
        lines.append("Across-Task Omnibus (Feature Stability)")
        lines.append("-" * 40)
        across = res.get('across_task') or {}
        if across:
            # Check for ranking-only mode (Nmin guard)
            ranking_only = across.get('ranking_only', False)
            nmin = across.get('nmin_sessions')
            sessions_used = across.get('sessions_used')
            msg = across.get('message')
            
            if ranking_only:
                lines.append(f"⚠ Significance testing disabled: N={sessions_used} sessions < Nmin={nmin}")
                lines.append("Showing descriptive rankings only (median effect per task).")
                if msg:
                    lines.append(f"Note: {msg}")
                # Show ranking-only features
                feat_info = across.get("features", {}) or {}
                lines.append(f"Features ranked: {len(feat_info)}")
                # Show a few examples
                lines.append("Sample feature rankings (up to 5):")
                for i, (fname, data) in enumerate(sorted(feat_info.items())[:5]):
                    ranking = data.get('ranking', [])
                    ranking_str = " > ".join([f"{r['task']}({_fmt(r['median_effect'])})" for r in ranking])
                    lines.append(f"  {fname}: {ranking_str}")
            else:
                feat_info = across.get("features", {}) or {}
                sig_feats = [f for f, d in feat_info.items() if d.get("omnibus_sig")]
                lines.append(f"Features tested: {len(feat_info)} | Significant (FDR {self.feature_engine.config.fdr_alpha}): {len(sig_feats)}")
                if sig_feats:
                    lines.append("Significant features: " + ", ".join(sorted(sig_feats)))
                # Show top 5 by omnibus statistic
                scored = []
                for fname, data in feat_info.items():
                    stat = data.get("omnibus_stat")
                    pval = data.get("omnibus_p")
                    qval = data.get("omnibus_q")
                    scored.append((stat if stat is not None else -float('inf'), fname, pval, qval))
                scored.sort(reverse=True)
                lines.append("Top Feature Omnibus Stats (up to 5):")
                for stat, fname, pval, qval in scored[:5]:
                    lines.append(f"  {fname}: stat={_fmt(stat)} p={_fmt(pval)} q={_fmt(qval)}")
        else:
            lines.append("Across-task analysis unavailable (insufficient task diversity).")
        lines.append("")
        
        # Configuration provenance
        lines.append("Configuration & Provenance")
        lines.append("-" * 40)
        config = self.feature_engine.config
        lines.append(f"Mode={config.mode} | alpha={config.alpha} | dependence={config.dependence_correction}")
        lines.append(f"Permutation preset={config.runtime_preset} (n_perm={config.n_perm}) | effect_measure={config.effect_measure}")
        lines.append(f"Discretization bins={config.discretization_bins} | FDR alpha={config.fdr_alpha}")
        lines.append("Baseline: eyes-closed only (eyes-open retained for reference, not pooled).")
        lines.append("")
        lines.append("Glossary of Metrics")
        lines.append("-" * 40)
        glossary_entries = [
            ("Fisher_KM", "Fisher combined p-value adjusted with Kost–McDermott correlation correction"),
            ("SumP", "Sum of per-feature p-values; permutation p-value gauges deviation from baseline"),
            ("CompositeScore", "Sum of -log10 adjusted p-values as an aggregate strength indicator"),
            ("Mean|d|", "Mean absolute Cohen's d effect size across significant features"),
            ("perm_p", "Permutation-derived significance comparing observed statistic to shuffled baseline"),
            ("perm_used", "Indicates whether permutations (vs analytic approximation) were applied"),
            ("km_df", "Effective degrees of freedom used in Kost–McDermott chi-square approximation"),
            ("sig_feature_count", "Number of features passing the FDR threshold when feature selection enabled"),
            ("sig_prop", "Proportion of tested features that remained significant after FDR control"),
            ("omnibus_stat", "Across-task Friedman/Wilcoxon statistic measuring feature variation between tasks"),
            ("omnibus_p", "P-value for omnibus_stat before FDR adjustment"),
            ("omnibus_q", "FDR-adjusted p-value for the across-task omnibus test"),
            ("omnibus_sig", "True when omnibus_q is below the configured FDR alpha"),
            ("posthoc_q", "Pairwise task comparison FDR-adjusted q-values (matrix form in exports)"),
            ("Δ", "Absolute difference between task and baseline means for the feature"),
            ("d", "Cohen's d effect size comparing task vs baseline distributions"),
            ("ratio", "Task mean divided by baseline mean (signed) for quick proportional change"),
            ("bin", "Discretized effect bin index relative to baseline distribution quantiles"),
        ]
        seen_terms = set()
        for key, description in glossary_entries:
            if key in seen_terms:
                continue
            seen_terms.add(key)
            lines.append(f"{key}: {description}")
        
        text = "\n".join(lines)
        
        # Display in text widget
        try:
            self.multi_task_text.setPlainText(text)
            self.log_message("✓ Multi-task report generated")
        except Exception as e:
            self.log_message(f"Display error: {e}")
        
        # Prompt user to save report to file
        try:
            ts = time.strftime('%Y%m%d_%H%M%S')
            default_name = f"multi_task_report_{ts}.txt"
            
            # Use QFileDialog to let user choose save location
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Save Multi-Task Report",
                default_name,
                "Text Files (*.txt);;All Files (*)"
            )
            
            if path:
                # Ensure .txt extension
                if not path.lower().endswith('.txt'):
                    path = path + '.txt'
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(text)
                self.log_message(f"✓ Report saved: {path}")
            else:
                # User cancelled - still save a backup copy in current directory
                backup_filename = f"multi_task_report_{ts}.txt"
                with open(backup_filename, 'w', encoding='utf-8') as f:
                    f.write(text)
                self.log_message(f"✓ Backup report saved: {backup_filename}")
        except Exception as e:
            self.log_message(f"Save error: {e}")
            # Fallback: try to save in current directory
            try:
                ts = time.strftime('%Y%m%d_%H%M%S')
                fallback_filename = f"multi_task_report_{ts}.txt"
                with open(fallback_filename, 'w', encoding='utf-8') as f:
                    f.write(text)
                self.log_message(f"✓ Fallback report saved: {fallback_filename}")
            except Exception as e2:
                self.log_message(f"Fallback save error: {e2}")

    # Prevent automatic serial connection before login to avoid COM port being held
    def auto_connect_brainlink(self):
        try:
            # Ensure feature engine remains linked for any incoming callbacks
            BL.onRaw.feature_engine = self.feature_engine
        except Exception:
            pass
    # Adjust UI: enable Connect button, disable analysis until connected
        try:
            if hasattr(self, 'connect_button'):
                self.connect_button.setEnabled(True)
            if hasattr(self, 'disconnect_button'):
                self.disconnect_button.setEnabled(False)
            if hasattr(self, 'eyes_closed_button'):
                self.eyes_closed_button.setEnabled(False)
            if hasattr(self, 'eyes_open_button'):
                self.eyes_open_button.setEnabled(False)
            if hasattr(self, 'task_button'):
                self.task_button.setEnabled(False)
            if hasattr(self, 'compute_baseline_button'):
                self.compute_baseline_button.setEnabled(False)
            if hasattr(self, 'analyze_task_button'):
                self.analyze_task_button.setEnabled(False)
            if hasattr(self, 'generate_report_button'):
                self.generate_report_button.setEnabled(False)
        except Exception:
            pass
        # Inform user
        try:
            self.log_message("Auto-connect disabled in enhanced mode. Please use 'Connect'.")
        except Exception:
            pass

    def start_calibration(self, phase_name):
        # Play audio cue at the start of any baseline capture
        if phase_name in {'eyes_closed', 'eyes_open'}:
            try:
                self._audio.play_start_calibration()
            except Exception:
                pass
        if phase_name == 'eyes_closed':
            # Reset EC diagnostics counters at the start
            try:
                self.feature_engine.baseline_kept = 0
                self.feature_engine.baseline_rejected = 0
            except Exception:
                pass
        # No visual cue for eyes-closed baseline; just delegate to base
        super().start_calibration(phase_name)

    def stop_calibration(self):
        phase_ending = getattr(self.feature_engine, 'current_state', None)
        task_ui_present = bool(getattr(self, '_task_dialog', None) or getattr(self, '_task_overlay_active', False))
        if phase_ending == 'idle' and not task_ui_present:
            return

        # CRITICAL: Save task name BEFORE calling stop_calibration_phase (which sets current_task to None)
        task_name_to_save = None
        if phase_ending == 'task':
            task_name_to_save = getattr(self.feature_engine, 'current_task', None)

        try:
            try:
                self._calibration_timer.stop()
            except Exception:
                pass

            if phase_ending != 'idle':
                try:
                    self.feature_engine.stop_calibration_phase()
                except Exception:
                    phase_ending = None

            try:
                if hasattr(self, 'stop_button') and self.stop_button is not None:
                    self.stop_button.setEnabled(False)
            except Exception:
                pass

            try:
                if phase_ending == 'eyes_closed':
                    if hasattr(self, 'eyes_closed_label'):
                        self.eyes_closed_label.setText("Status: Completed")
                    if hasattr(self, 'eyes_closed_button'):
                        self.eyes_closed_button.setEnabled(True)
                elif phase_ending == 'eyes_open':
                    if hasattr(self, 'eyes_open_label'):
                        self.eyes_open_label.setText("Status: Completed")
                    if hasattr(self, 'eyes_open_button'):
                        self.eyes_open_button.setEnabled(True)
                elif phase_ending == 'task':
                    if hasattr(self, 'task_label'):
                        self.task_label.setText("Status: Completed")
                    if hasattr(self, 'task_button'):
                        self.task_button.setEnabled(True)
            except Exception:
                pass

            try:
                self.log_message(f"✓ Stopped {phase_ending} calibration")
            except Exception:
                pass

            try:
                ec_count = len(self.feature_engine.calibration_data.get('eyes_closed', {}).get('features', []))
                eo_count = len(self.feature_engine.calibration_data.get('eyes_open', {}).get('features', []))
                if ec_count > 0 and eo_count > 0:
                    self.compute_baseline()
            except Exception:
                pass

            if phase_ending == 'task':
                try:
                    task_windows = len(self.feature_engine.calibration_data.get('task', {}).get('features', []))
                except Exception:
                    task_windows = 0
                
                # CRITICAL FIX: Save task data to the 'tasks' dictionary with task name as key
                try:
                    if task_windows > 0 and task_name_to_save:
                        # Copy data from singular 'task' to plural 'tasks' dictionary
                        if 'tasks' not in self.feature_engine.calibration_data:
                            self.feature_engine.calibration_data['tasks'] = {}
                        
                        # Store the task data under the task name WITH timestamps list (matching expected format)
                        self.feature_engine.calibration_data['tasks'][task_name_to_save] = {
                            'features': self.feature_engine.calibration_data['task']['features'].copy(),
                            'timestamps': self.feature_engine.calibration_data['task']['timestamps'].copy()
                        }
                        
                        self.log_message(f"✓ Saved {task_windows} windows for task '{task_name_to_save}'")
                        print(f"DEBUG: Stored task data for '{task_name_to_save}': {task_windows} feature windows")
                    elif task_windows == 0:
                        self.log_message("Warning: No feature windows captured for this task")
                        print(f"DEBUG: Task had 0 windows - not saved")
                    elif not task_name_to_save:
                        self.log_message("Warning: Task name was not set")
                        print(f"DEBUG: current_task was None - cannot save")
                except Exception as e:
                    self.log_message(f"Warning: Failed to save task data: {e}")
                    print(f"ERROR saving task data: {e}")
                    import traceback
                    traceback.print_exc()
                
                try:
                    if task_windows > 0:
                        self._set_feature_status("Task captured", "ready")
                    else:
                        self._set_feature_status("Idle", "idle")
                except Exception:
                    pass
            else:
                try:
                    if getattr(self.feature_engine, 'current_state', None) == 'idle':
                        self._set_feature_status("Idle", "idle")
                except Exception:
                    pass
        finally:
            if getattr(self, '_task_dialog', None) is not None or getattr(self, '_task_overlay_active', False):
                try:
                    self.close_task_interface()
                except Exception:
                    pass

            try:
                if getattr(self, 'analyze_all_button', None):
                    self.analyze_all_button.setEnabled(True)
                if getattr(self, 'generate_all_report_button', None):
                    self.generate_all_report_button.setEnabled(False)
                if getattr(self, 'multi_task_text', None):
                    self.multi_task_text.setVisible(True)
                    self.multi_task_text.setPlainText(
                        "Press 'Analyze All Tasks' to compute combined insights across completed sessions."
                    )
            except Exception:
                pass

            try:
                if hasattr(self, '_stage_status_overrides'):
                    self._stage_status_overrides[self.analysis_tab_index] = "Tasks recorded"
                    self._refresh_stage_header()
            except Exception:
                pass
        try:
            if self._fixation_dialog is not None:
                self._fixation_dialog.close()
                self._fixation_dialog = None
        except Exception:
            pass

        try:
            if phase_ending in {'eyes_closed', 'eyes_open'}:
                self._audio.play_end_calibration()
            elif phase_ending == 'task':
                self._audio.play_end_task()
        except Exception:
            pass

    def compute_baseline(self):
        # Use enhanced EC-only baseline computation
        self.feature_engine.compute_baseline_statistics()
        try:
            self.analysis_summary.clear()
            self.analysis_summary.setVisible(False)
        except Exception:
            pass
        try:
            self._set_feature_status("Baseline ready", "ready")
        except Exception:
            pass
        self.log_message("✓ Baseline (eyes-closed only) computed")

    def update_features_display(self):
        """Extend base streaming update with an explicit live-feed confirmation."""
        try:
            super().update_features_display()
        except Exception:
            pass

        try:
            hint = getattr(self, "live_feature_hint", None)
            features = getattr(self.feature_engine, "latest_features", {}) or {}
            if hint is None:
                return
            if features:
                preview_keys = ", ".join(list(features.keys())[:3])
                if len(features) > 3:
                    preview_keys += ", …"
                hint.setStyleSheet("color:#047857; font-size:11px; margin-left:4px; font-weight:600;")
                hint.setText(f"Live feed active · {len(features)} features streaming ({preview_keys})")
            else:
                hint.setStyleSheet("color:#64748b; font-size:11px; margin-left:4px;")
                hint.setText("Awaiting live EEG features…")
        except Exception:
            pass

    def analyze_task(self):
        if not getattr(self, '_allow_immediate_task_analysis', False):
            try:
                self.log_message("Task stored for later multi-task analysis. Run 'Analyze All Tasks' when ready.")
            except Exception:
                pass
            try:
                self._set_feature_status("Task captured", "ready")
            except Exception:
                pass
            return

        self._allow_immediate_task_analysis = False
        if getattr(self, '_single_task_analysis_running', False):
            self.log_message("Task analysis already running")
            return
        task_features = self.feature_engine.calibration_data.get('task', {}).get('features', [])
        if not task_features:
            try:
                task_n = len(task_features)
                ec_n = len(self.feature_engine.calibration_data.get('eyes_closed', {}).get('features', []))
                eo_n = len(self.feature_engine.calibration_data.get('eyes_open', {}).get('features', []))
                cur = getattr(self.feature_engine, 'current_state', None)
                ec_kept = getattr(self.feature_engine, 'baseline_kept', 0)
                ec_rej = getattr(self.feature_engine, 'baseline_rejected', 0)
                msg = [
                    "No task data to analyze yet.",
                    f"Task windows collected: {task_n}",
                    f"Eyes-closed windows: {ec_n}",
                    f"  EC kept: {ec_kept} | rejected (blink): {ec_rej}",
                    f"Eyes-open windows: {eo_n}",
                    f"Current state: {cur}",
                    "Tip: Start a task, let it run for at least a few windows (2s each), then press Stop before Analyze."
                ]
                self.analysis_summary.setPlainText("\n".join(msg))
                self.analysis_summary.setVisible(True)
                self.log_message("No task windows collected yet—record a task and press Stop.")
            except Exception:
                self.analysis_summary.setPlainText("No task data available.")
                self.analysis_summary.setVisible(True)
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Analyzing Task")
        dlg.setModal(True)
        dlg.setMinimumSize(400, 120)
        vbox = QVBoxLayout(dlg)
        label = QLabel("Preparing analysis...")
        vbox.addWidget(label)
        progress = QtWidgets.QProgressBar(dlg)
        n_perm = self.feature_engine.config.n_perm
        feature_est = len(getattr(self.feature_engine, 'baseline_stats', {}) or {}) or 100
        total_units = feature_est + n_perm
        # Start indeterminate until first feature callback arrives
        progress.setRange(0, 0)  # Qt convention: 0,0 => busy (marquee on some styles)
        progress.setValue(0)
        vbox.addWidget(progress)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setEnabled(True)
        vbox.addWidget(btn_cancel)

        state = {'feature_total': feature_est, 'feature_done': 0, 'perm_done': 0, 'total_units': total_units}
        state['first_feature_callback'] = False
        state['first_perm_callback'] = False
        state['heartbeat_ticks'] = 0

        # Heartbeat: while no feature progress has arrived, update label so user sees activity
        heartbeat_timer = QtCore.QTimer(dlg)
        heartbeat_timer.setInterval(500)  # ms
        def _heartbeat():
            try:
                if state['first_feature_callback']:
                    heartbeat_timer.stop()
                    return
                state['heartbeat_ticks'] += 1
                dots = '.' * ((state['heartbeat_ticks'] % 6) + 1)
                label.setText(f"Preparing analysis{dots}")
            except Exception:
                pass
        heartbeat_timer.timeout.connect(_heartbeat)
        heartbeat_timer.start()

        def _recalc_max():
            state['total_units'] = state['feature_total'] + n_perm
            progress.setMaximum(max(1, state['total_units']))

        def _feature_cb(task_name: str, done: int, total: int):
            def _u():
                try:
                    # On first callback: switch progress to determinate mode
                    if not state['first_feature_callback']:
                        state['first_feature_callback'] = True
                        progress.setRange(0, max(1, state['total_units']))
                        label.setText("Starting feature analysis...")
                    if total > state['feature_total']:
                        state['feature_total'] = total
                        _recalc_max()
                    state['feature_done'] = done
                    overall = state['feature_done'] + state['perm_done']
                    progress.setValue(min(int(overall), int(state['total_units'])))
                    label.setText(f"Features: {done}/{total}")
                except Exception:
                    pass
            QtCore.QTimer.singleShot(0, _u)

        def _perm_cb(done: int, total: int):
            def _u2():
                try:
                    state['perm_done'] = done
                    if not state['first_perm_callback']:
                        state['first_perm_callback'] = True
                    overall = state['feature_done'] + state['perm_done']
                    progress.setValue(min(int(overall), int(state['total_units'])))
                    label.setText(f"Permutations: {done}/{total}")
                    if done == total:
                        label.setText("Finalizing...")
                except Exception:
                    pass
            QtCore.QTimer.singleShot(0, _u2)

        def _on_cancel():
            try:
                btn_cancel.setEnabled(False)
                label.setText("Cancelling...")
                self.feature_engine.cancel_analysis()
            except Exception:
                pass
        btn_cancel.clicked.connect(_on_cancel)

        def _worker():
            try:
                self._single_task_analysis_running = True
                self.feature_engine.reset_analysis_cancel()
                self.feature_engine.reset_permutation_cancel()
                self.feature_engine.set_feature_progress_callback(_feature_cb)
                self.feature_engine.set_permutation_progress_callback(_perm_cb)
                if not getattr(self.feature_engine, 'baseline_stats', None):
                    self.feature_engine.compute_baseline_statistics()
                    bs_count = len(getattr(self.feature_engine, 'baseline_stats', {}) or {})
                    if bs_count > 0:
                        state['feature_total'] = bs_count
                        _recalc_max()
                results = self.feature_engine.analyze_task_data()
            except Exception as e:
                results = {'_error': str(e)}
            finally:
                try:
                    self.feature_engine.clear_feature_progress_callback()
                except Exception:
                    pass
                try:
                    self.feature_engine.clear_permutation_progress_callback()
                except Exception:
                    pass
            def _on_done():
                self._single_task_analysis_running = False
                try:
                    if dlg.isVisible():
                        dlg.accept()
                except Exception:
                    pass
                if isinstance(results, dict) and results.get('_error'):
                    self.log_message(f"Task analysis failed: {results['_error']}")
                    self.analysis_summary.setPlainText("Task analysis failed. See logs for details.")
                    self.analysis_summary.setVisible(True)
                    return
                if results:
                    try:
                        self.update_results_display(results)
                    except Exception:
                        pass
                    self._update_composite_summary_text()
                    try:
                        self._set_feature_status("Insights ready", "insights")
                    except Exception:
                        pass
                    partial_flag = getattr(self.feature_engine, 'task_summary', {}).get('partial')
                    if partial_flag:
                        self.log_message("⚠️ Task analysis cancelled (partial results shown)")
                    else:
                        self.log_message("✓ Enhanced task analysis completed")
                else:
                    self.analysis_summary.setPlainText("No analyzable task features.")
                    self.analysis_summary.setVisible(True)
            QtCore.QTimer.singleShot(0, _on_done)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        self._push_modal_overlay()
        try:
            dlg.exec()
        finally:
            self._pop_modal_overlay()
        return

    def run_single_task_analysis_now(self) -> None:
        """Explicit hook to run the single-task analysis flow when desired."""
        self._allow_immediate_task_analysis = True
        try:
            EnhancedBrainLinkAnalyzerWindow.analyze_task(self)
        finally:
            self._allow_immediate_task_analysis = False

    def _update_composite_summary_text(self):
        summary = getattr(self.feature_engine, 'task_summary', None)
        if not summary:
            return
        fisher = summary.get('fisher', {})
        sum_p = summary.get('sum_p', {})
        feature_sel = summary.get('feature_selection') or {}
        composite = summary.get('composite', {}) or {}
        cosine = summary.get('cosine', {}) or {}
        effect_mean = summary.get('effect_size_mean')
        text = self.analysis_summary.toPlainText()
        text += "\n\nTask-Level Decisions\n" + ("-" * 30) + "\n"
        if fisher:
            text += f"Fisher (naive) p: {fisher.get('p_naive')}\n"
            ratio = fisher.get('km_df_ratio')
            text += f"Fisher (KM) p: {fisher.get('km_p')} (sig={fisher.get('significant')})"
            if ratio is not None:
                text += f" | df_KM ratio={ratio:.3f}"
            text += "\n"
        if sum_p:
            text += f"Sum p (blocks): {sum_p.get('value')} | p_perm={sum_p.get('perm_p')}"
            if sum_p.get('approximate'):
                text += " (approx)"
            text += f" | sig={sum_p.get('significant')}\n"
        ess = summary.get('ess') or {}
        if ess:
            text += f"ESS blocks: baseline={ess.get('baseline_blocks')} task={ess.get('task_blocks')} | block_len={ess.get('block_seconds')}s\n"
        # Seed and preset
        try:
            preset = getattr(self.feature_engine.config, 'runtime_preset', None)
            seed = getattr(self.feature_engine.config, 'seed', None)
            if preset or seed is not None:
                text += f"Permutation preset={preset} | seed={seed}\n"
        except Exception:
            pass
        if self.feature_engine.config.is_feature_selection and feature_sel:
            text += f"Significant features: {feature_sel.get('sig_feature_count')}"
            if feature_sel.get('sig_prop') is not None:
                text += f" (prop={feature_sel.get('sig_prop'):.3f})"
            text += "\n"
        if composite:
            text += f"Composite score (ranking only): {composite.get('score')}\n"
        if effect_mean is not None:
            text += f"Mean |d|: {effect_mean}\n"
        if cosine:
            text += f"Cosine similarity: {cosine.get('similarity')} | distance: {cosine.get('distance')} | p={cosine.get('p_value')}\n"
        self.analysis_summary.setPlainText(text)
        self.analysis_summary.setVisible(True)

    def generate_report(self):
        results = getattr(self.feature_engine, 'analysis_results', {}) or {}
        summary = getattr(self.feature_engine, 'task_summary', {}) or {}
        if not results:
            self.analysis_summary.setPlainText("No task analysis available. Record and analyze a task first.")
            self.analysis_summary.setVisible(True)
            return

        cfg = self.feature_engine.config
        fisher = summary.get('fisher', {})
        sum_p = summary.get('sum_p', {})
        feature_sel = summary.get('feature_selection') or {}
        composite = summary.get('composite', {}) or {}
        cosine = summary.get('cosine', {}) or {}
        effect_mean = summary.get('effect_size_mean')

        lines: List[str] = []
        lines.append("BrainLink Enhanced Task Report")
        lines.append("=" * 60)
        lines.append(f"Mode: {cfg.mode} | alpha={cfg.alpha} | dependence={cfg.dependence_correction}")
        lines.append(f"Effect measure: {cfg.effect_measure} | bins={cfg.discretization_bins} | export_profile={cfg.export_profile}")
        lines.append("")
        lines.append("Task-Level Decisions")
        lines.append("-" * 40)
        lines.append(f"Fisher_KM_p={fisher.get('km_p')} (sig={fisher.get('significant')}) | naive={fisher.get('p_naive')} | df={fisher.get('km_df')}")
        lines.append(f"SumP={sum_p.get('value')} | p={sum_p.get('perm_p')} (sig={sum_p.get('significant')} perm={sum_p.get('permutation_used')} approx={sum_p.get('approximate')})")
        if cfg.is_feature_selection:
            lines.append(f"sig_feature_count={feature_sel.get('sig_feature_count')} | sig_prop={feature_sel.get('sig_prop')}")
        lines.append(f"Composite score (ranking only)={composite.get('score')} | Mean |d|={effect_mean}")
        lines.append(f"Cosine similarity={cosine.get('similarity')} | distance={cosine.get('distance')} | p={cosine.get('p_value')}")

        if cfg.export_profile == 'integer_only':
            export_int = getattr(self.feature_engine, 'last_export_integer', {})
            lines.append("")
            lines.append("Discrete Feature Export (integer_only)")
            lines.append("-" * 40)
            for feat_name, vals in sorted((export_int.get('features') or {}).items()):
                lines.append(f"{feat_name}: bin={vals.get('discrete_index')} | sig={vals.get('bin_sig')}")
        else:
            lines.append("")
            lines.append("Feature Details")
            lines.append("-" * 40)
            items = []
            for feat_name, vals in results.items():
                items.append((vals.get('p_value', 1.0), feat_name, vals))
            items.sort(key=lambda item: item[0])
            for p_val, feat_name, vals in items:
                lines.append(
                    f"{feat_name}: p={p_val:.4g} q={vals.get('q_value')} bin={vals.get('discrete_index')} sig={vals.get('bin_sig')} Δ={vals.get('delta')} z={vals.get('z_score')} effect={vals.get('effect_measure')}"
                )

        lines.append("")
        lines.append("Provenance Notes")
        lines.append("-" * 40)
        lines.append("Fisher corrected for feature dependence via Kost–McDermott.")
        if sum_p.get('permutation_used'):
            lines.append(f"Summed-p significance via permutation (n={cfg.n_perm}).")
        else:
            lines.append("Summed-p significance via normal approximation (permutations disabled).")
        if cfg.is_feature_selection:
            lines.append("BH-FDR used only for feature selection.")
        else:
            lines.append("BH-FDR skipped (aggregate-only mode).")
        lines.append(f"Discrete export enabled (B={cfg.discretization_bins}).")

        export_full = getattr(self.feature_engine, 'last_export_full', {})
        if export_full:
            lines.append("")
            lines.append("Export Payload (summary)")
            lines.append("-" * 40)
            try:
                compact = {
                    'summary_core': export_full.get('summary_core'),
                    'features': {k: {
                        'effect_measure': v.get('effect_measure'),
                        'discrete_index': v.get('discrete_index'),
                        'bin_sig': v.get('bin_sig'),
                    } for k, v in (export_full.get('features') or {}).items()}
                }
                lines.append(json.dumps(compact, indent=2))
            except Exception:
                lines.append(str(export_full))

        report_text = "\n".join(lines)
        self.analysis_summary.setPlainText(report_text)
        self.analysis_summary.setVisible(True)
        self.log_message("✓ Report generated")

    def analyze_all_tasks(self):
        """Run per-task and combined analysis in a background thread, display a modal progress dialog and allow cancellation."""
        # Prevent re-entrancy
        if getattr(self, '_analysis_thread_running', False):
            self.log_message("Multi-task analysis already running")
            return

        analyze_btn = getattr(self, 'analyze_all_button', None)
        report_btn = getattr(self, 'generate_all_report_button', None)
        if analyze_btn is not None:
            analyze_btn.setEnabled(False)
        if report_btn is not None:
            report_btn.setEnabled(False)

        # Quick pre-check for tasks to avoid showing dialog unnecessarily
        tasks = self.feature_engine.calibration_data.get('tasks', {}) or {}
        task_n = len(self.feature_engine.calibration_data.get('task', {}).get('features', []))
        if not tasks and task_n == 0:
            lines = [
                "No task data available for multi-task analysis.",
                f"Per-task buckets recorded: {len(tasks)}",
                f"Task windows in default bucket: {task_n}",
                "Tip: Start a task from the Tasks tab, wait at least a few seconds (2s per window), then Stop and Analyze."
            ]
            if getattr(self, 'multi_task_text', None):
                self.multi_task_text.setPlainText("\n".join(lines))
                self.multi_task_text.setVisible(True)
            if analyze_btn is not None:
                analyze_btn.setEnabled(True)
            return

        # Create Qt Signals for thread-safe progress communication
        from PySide6.QtCore import QObject, Signal
        
        class ProgressSignals(QObject):
            feature_progress = Signal(str, int, int)  # task_name, done, total
            permutation_progress = Signal(int, int)  # completed, total
            general_progress = Signal(int, int)  # done, total
            baseline_tick = Signal(str)  # message
            recalc_max = Signal()  # trigger max recalculation
            analysis_complete = Signal(object)  # results dict
        
        signals = ProgressSignals()

        # Create modal progress dialog
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Running Multi-Task Analysis")
        dlg.setModal(True)
        dlg.setMinimumSize(400, 120)
        vbox = QVBoxLayout(dlg)
        label = QLabel("Preparing analysis...")
        vbox.addWidget(label)
        progress = QtWidgets.QProgressBar(dlg)
        # Aggregated multi-phase progress:
        # Phase A: Feature processing for each task (estimated by baseline feature count)
        # Phase B: Permutations for each task + combined
        # We compute an initial conservative estimate; will adjust once baseline stats known.
        tasks_count = len(tasks)  # individual tasks (exclude combined for per-task loops)
        n_perm = self.feature_engine.config.n_perm
        baseline_feature_est = len(getattr(self.feature_engine, 'baseline_stats', {}) or {}) or 100  # fallback estimate
    # total feature units = (tasks_count + 1) * baseline_feature_est (including combined)
    # total permutation units = (tasks_count + 1) * n_perm
    # Add a small synthetic baseline-preparation phase so the bar advances before first feature callback
        baseline_phase_units = 20
        # Switch to percentage-based progress so early increments are visible
        progress.setRange(0, 100)
        progress.setValue(1)  # move off 0% instantly
        label.setText("Computing baseline / preparing tasks...")
        vbox.addWidget(progress)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setEnabled(True)
        vbox.addWidget(btn_cancel)

        progress_trace_enabled = os.environ.get("BL_PROGRESS_TRACE", "0").lower() in {"1", "true", "yes"}
        def _trace(msg: str) -> None:
            if progress_trace_enabled:
                print(f"[PROGRESS TRACE] {msg}")

        if progress_trace_enabled:
            _trace(
                "enabled for analyze_all_tasks dialog"
            )
        else:
            print("[PROGRESS TRACE] disabled (set BL_PROGRESS_TRACE=1 before launching to enable detailed logging)")

        # Dynamic aggregation state (captured in closures)
        agg_state = {
            'baseline_features': baseline_feature_est,
            'tasks_count': tasks_count,
            'perm_phases_total': max(1, tasks_count + 1),
            'feature_units_done': 0,
            'perm_phase_index': 0,  # completed permutation phases
            'perm_iterations_in_phase': 0,
            'perm_phase_completed': False,
            'current_task_feature_total': baseline_feature_est,
            'task_index': 0,  # 0..tasks_count for individual tasks; last combined
            'completed_feature_units': 0,
            'first_feature_callback': False,
            'first_perm_callback': False,
            'heartbeat_ticks': 0,
            'baseline_phase_units': baseline_phase_units,
            'baseline_phase_done': 1,  # consumed first unit by setting value=1
            'total_feature_units': (tasks_count + 1) * baseline_feature_est,
            'total_perm_units': (tasks_count + 1) * n_perm,
            'last_logged_percent': None,
            'last_logged_message': None,
        }

        BASELINE_WEIGHT = 0.1
        FEATURE_WEIGHT = 0.55
        PERM_WEIGHT = 0.35

        _trace(
            "initial_state "
            f"tasks_count={tasks_count} baseline_feature_est={baseline_feature_est} "
            f"total_feature_units={(tasks_count + 1) * baseline_feature_est} "
            f"total_perm_units={(tasks_count + 1) * n_perm} "
            f"baseline_phase_units={baseline_phase_units}"
        )

        def _calc_percent() -> Tuple[int, float, float, float]:
            try:
                baseline_ratio = agg_state['baseline_phase_done'] / max(1, agg_state['baseline_phase_units'])
                feature_ratio = agg_state['feature_units_done'] / max(1, agg_state['total_feature_units'])
                perm_units_done = agg_state['perm_phase_index'] * n_perm + agg_state['perm_iterations_in_phase']
                perm_units_done = min(perm_units_done, agg_state['total_perm_units'])
                perm_ratio = perm_units_done / max(1, agg_state['total_perm_units'])
                baseline_ratio = min(1.0, baseline_ratio)
                feature_ratio = min(1.0, feature_ratio)
                perm_ratio = min(1.0, perm_ratio)
                pct = (
                    baseline_ratio * BASELINE_WEIGHT +
                    feature_ratio * FEATURE_WEIGHT +
                    perm_ratio * PERM_WEIGHT
                ) * 100.0
            except Exception:
                pct = 0.0
                baseline_ratio = feature_ratio = perm_ratio = 0.0
            percent = int(max(0.0, min(100.0, round(pct))))
            return percent, float(baseline_ratio), float(feature_ratio), float(perm_ratio)

        def _set_progress(message: str) -> None:
            try:
                percent, baseline_ratio, feature_ratio, perm_ratio = _calc_percent()
                progress.setValue(max(1, percent))
                if message:
                    label.setText(f"{message} [{percent}%]")
                else:
                    label.setText(f"{percent}%")
                if agg_state['last_logged_percent'] != percent or agg_state['last_logged_message'] != message:
                    _trace(
                        f"percent={percent} msg='{message}' baseline={agg_state['baseline_phase_done']}/{agg_state['baseline_phase_units']} ({baseline_ratio:.3f}) "
                        f"features={agg_state['feature_units_done']}/{agg_state['total_feature_units']} ({feature_ratio:.3f}) permutations="
                        f"{agg_state['perm_phase_index'] * n_perm + agg_state['perm_iterations_in_phase']}/{agg_state['total_perm_units']} ({perm_ratio:.3f})"
                    )
                    agg_state['last_logged_percent'] = percent
                    agg_state['last_logged_message'] = message
            except Exception:
                pass

        heartbeat_timer = QtCore.QTimer(dlg)
        heartbeat_timer.setInterval(500)
        def _heartbeat_multi():
            try:
                if agg_state['first_feature_callback']:
                    heartbeat_timer.stop()
                    return
                agg_state['heartbeat_ticks'] += 1
                dots = '.' * ((agg_state['heartbeat_ticks'] % 6) + 1)
                label.setText(f"Preparing multi-task analysis{dots}")
            except Exception:
                pass
        heartbeat_timer.timeout.connect(_heartbeat_multi)
        heartbeat_timer.start()

        def _recalc_max():
            core = (tasks_count + 1) * agg_state['baseline_features'] + (tasks_count + 1) * n_perm
            agg_state['total_feature_units'] = (tasks_count + 1) * agg_state['baseline_features']
            agg_state['total_perm_units'] = (tasks_count + 1) * n_perm

        # Connect signals to GUI thread slots (thread-safe communication)
        def _on_feature_progress(task_name: str, done: int, total: int):
            """GUI thread slot for feature progress updates."""
            try:
                print(f"[GUI THREAD] Feature progress: {task_name} {done}/{total}")  # DEBUG
                if not agg_state['first_feature_callback']:
                    agg_state['first_feature_callback'] = True
                    # Stop heartbeat once we get real feature progress
                    heartbeat_timer.stop()
                    label.setText("Starting feature analysis...")
                # On first emission for a task, update baseline feature count if larger
                if total > agg_state['baseline_features']:
                    agg_state['baseline_features'] = total
                    _recalc_max()
                agg_state['current_task_feature_total'] = total
                # Compute absolute units: previous tasks' features + current done
                offset_units = agg_state['completed_feature_units']
                current_abs_done = offset_units + done
                # Add baseline phase units to overall calculation
                agg_state['feature_units_done'] = max(agg_state['feature_units_done'], current_abs_done)
                _set_progress(f"Features ({task_name}): {done}/{total}")
                if progress_trace_enabled:
                    _trace(
                        f"feature_state task={task_name} done={done} total={total} completed_units={agg_state['completed_feature_units']} "
                        f"feature_units_done={agg_state['feature_units_done']} task_index={agg_state['task_index']}"
                    )
                # If finished features for this task, advance task_index and record completion
                if done == total:
                    agg_state['completed_feature_units'] += total
                    agg_state['task_index'] += 1
            except Exception as e:
                print(f"[GUI THREAD] Feature callback error: {e}")  # DEBUG
        
        def _on_permutation_progress(completed: int, total: int):
            """GUI thread slot for permutation progress updates."""
            try:
                if not agg_state['first_perm_callback']:
                    agg_state['first_perm_callback'] = True
                # Update permutation iterations for current phase
                agg_state['perm_iterations_in_phase'] = completed
                display_phase = min(agg_state['perm_phase_index'] + 1, agg_state['perm_phases_total'])
                _set_progress(f"Permutations (phase {display_phase}/{agg_state['perm_phases_total']}): {completed}/{total}")
                if progress_trace_enabled:
                    _trace(
                        f"perm_state phase={agg_state['perm_phase_index']} completed={completed} total={total} iterations_in_phase={agg_state['perm_iterations_in_phase']}"
                    )
                if completed == total:
                    if not agg_state['perm_phase_completed']:
                        if agg_state['perm_phase_index'] < agg_state['perm_phases_total']:
                            agg_state['perm_phase_index'] += 1
                        agg_state['perm_phase_completed'] = True
                    agg_state['perm_iterations_in_phase'] = 0
                    if agg_state['perm_phase_index'] >= agg_state['perm_phases_total']:
                        _set_progress("Finalizing multi-task results...")
                else:
                    agg_state['perm_phase_completed'] = False
            except Exception:
                pass
        
        def _on_general_progress(done: int, total: int):
            """GUI thread slot for general progress updates."""
            try:
                if agg_state['feature_units_done'] == 0:
                    # approximate feature units via done * baseline_features
                    agg_state['feature_units_done'] = done * agg_state['baseline_features']
                    _set_progress(f"Tasks analyzed: {done}/{total}")
                    if progress_trace_enabled:
                        _trace(f"general_state done={done} total={total} approx_feature_units={agg_state['feature_units_done']}")
            except Exception:
                pass
        
        def _on_baseline_tick(msg: str):
            """GUI thread slot for baseline phase ticks."""
            try:
                overall = (agg_state['baseline_phase_done'] +
                           agg_state['feature_units_done'] +
                           agg_state['perm_phase_index'] * n_perm +
                           agg_state['perm_iterations_in_phase'])
                _set_progress(msg)
                if progress_trace_enabled:
                    _trace(
                        f"baseline_tick msg='{msg}' baseline_done={agg_state['baseline_phase_done']} overall_units={overall}"
                    )
            except Exception:
                pass
        
        def _on_recalc_max():
            """GUI thread slot for recalculating max values."""
            try:
                _recalc_max()
            except Exception:
                pass

        # Connect all signals to their GUI thread slots
        signals.feature_progress.connect(_on_feature_progress)
        signals.permutation_progress.connect(_on_permutation_progress)
        signals.general_progress.connect(_on_general_progress)
        signals.baseline_tick.connect(_on_baseline_tick)
        signals.recalc_max.connect(_on_recalc_max)

        # Worker thread callback wrappers (emit signals instead of QTimer.singleShot)
        def _feature_cb(task_name: str, done: int, total: int):
            print(f"[WORKER] Emitting feature {done}/{total}")  # DEBUG
            signals.feature_progress.emit(task_name, done, total)

        def _perm_cb(completed: int, total: int):
            signals.permutation_progress.emit(completed, total)

        def _general_cb(done: int, total: int):
            signals.general_progress.emit(done, total)

        # Baseline tick helper (emit signal from worker thread)
        def _baseline_tick(msg: str):
            # Increment counter in worker thread (not GUI thread) to avoid race condition
            if agg_state['baseline_phase_done'] < agg_state['baseline_phase_units']:
                agg_state['baseline_phase_done'] += 1
            # Emit signal to update GUI
            signals.baseline_tick.emit(msg)

        # Worker
        def _worker():
            try:
                self._analysis_thread_running = True
                # install progress callback
                self.feature_engine.set_general_progress_callback(_general_cb)
                self.feature_engine.set_permutation_progress_callback(_perm_cb)
                self.feature_engine.set_feature_progress_callback(_feature_cb)
                
                # Schedule baseline ticks from worker (will emit signals to GUI thread)
                _baseline_tick("Checking baseline statistics...")
                need_baseline = not getattr(self.feature_engine, 'baseline_stats', None)
                if need_baseline:
                    _baseline_tick("Computing baseline statistics...")
                    try:
                        self.feature_engine.compute_baseline_statistics()
                    except Exception:
                        pass
                _baseline_tick("Preparing task feature sets...")
                bs_count = len(getattr(self.feature_engine, 'baseline_stats', {}) or {})
                if bs_count > 0:
                    agg_state['baseline_features'] = bs_count
                    # Emit signal to recalculate max on GUI thread
                    signals.recalc_max.emit()
                _baseline_tick("Initializing multi-task analysis engine...")
                
                # Consume remaining baseline phase units to show full baseline progress before heavy computation
                while agg_state['baseline_phase_done'] < agg_state['baseline_phase_units']:
                    _baseline_tick(f"Starting analysis... ({agg_state['baseline_phase_done']}/{agg_state['baseline_phase_units']})")
                    # No sleep - let GUI marshaling handle timing naturally
                
                # Run actual analysis
                res = self.feature_engine.analyze_all_tasks_data()
            except Exception as e:
                tb = None
                try:
                    import traceback
                    tb = traceback.format_exc()
                except Exception:
                    tb = None
                error_payload: Dict[str, Any] = {'_error': str(e)}
                if tb:
                    error_payload['_traceback'] = tb
                res = error_payload
            finally:
                # cleanup
                try:
                    self.feature_engine.clear_permutation_progress_callback()
                except Exception:
                    pass
                try:
                    self.feature_engine.clear_general_progress_callback()
                except Exception:
                    pass
                try:
                    self.feature_engine.clear_feature_progress_callback()
                except Exception:
                    pass
            
            # Emit completion signal with results
            signals.analysis_complete.emit(res)

        def _on_analysis_complete(res):
            """GUI thread slot for analysis completion."""
            self._analysis_thread_running = False
            try:
                heartbeat_timer.stop()
            except Exception:
                pass
            try:
                progress.setValue(100)
                label.setText("Analysis complete")
            except Exception:
                pass
            try:
                if dlg.isVisible():
                    QtCore.QTimer.singleShot(0, dlg.accept)
            except Exception:
                pass

            if analyze_btn is not None:
                analyze_btn.setEnabled(True)

            # Handle error
            if isinstance(res, dict) and res.get('_error'):
                err_msg = res.get('_error')
                self.log_message(f"Analysis failed: {err_msg}")
                tb_txt = res.get('_traceback')
                if tb_txt:
                    for line in tb_txt.strip().splitlines():
                        try:
                            self.log_message(line)
                        except Exception:
                            print(line)
                if getattr(self, 'multi_task_text', None):
                    self.multi_task_text.setPlainText("Analysis failed. See logs for details.")
                    self.multi_task_text.setVisible(True)
                return

            # Build summary text
            lines = ["Multi-Task Analysis Summary", "-" * 30]
            per_task = res.get('per_task', {})
            for task_name, data in sorted(per_task.items()):
                try:
                    summary = data.get('summary', {}) or {}
                    fisher = summary.get('fisher', {})
                    sum_p = summary.get('sum_p', {})
                    feature_sel = summary.get('feature_selection') or {}
                    lines.append(f"{task_name}:")
                    lines.append(f"  Fisher_KM_p={fisher.get('km_p')} sig={fisher.get('significant')}")
                    lines.append(f"  SumP_p={sum_p.get('perm_p')} sig={sum_p.get('significant')}")
                    if feature_sel:
                        lines.append(f"  sig_feature_count={feature_sel.get('sig_feature_count')} | sig_prop={feature_sel.get('sig_prop')}")
                except Exception:
                    lines.append(f"{task_name}: (error reading summary)")

            combined_summary = (res.get('combined') or {}).get('summary', {})
            fisher_c = combined_summary.get('fisher', {})
            sum_p_c = combined_summary.get('sum_p', {})
            lines.append("")
            lines.append("All Tasks Combined:")
            lines.append(f"  Fisher_KM_p={fisher_c.get('km_p')} sig={fisher_c.get('significant')} | SumP_p={sum_p_c.get('perm_p')} sig={sum_p_c.get('significant')}")
            across = res.get('across_task') or {}
            sig_features = [f for f, info in (across.get('features') or {}).items() if info.get('omnibus_sig')]
            if sig_features:
                lines.append("")
                lines.append("Across-task significant features:")
                lines.extend([f"  - {f}" for f in sig_features])

            if getattr(self, 'multi_task_text', None):
                self.multi_task_text.setPlainText("\n".join(lines))
                self.multi_task_text.setVisible(True)
            self._mark_stage_done(self.multi_task_tab_index, "Insights ready")
            if report_btn is not None:
                report_btn.setEnabled(True)

        # Connect completion signal
        signals.analysis_complete.connect(_on_analysis_complete)

        # Cancel handler
        def _on_cancel():
            try:
                btn_cancel.setEnabled(False)
                label.setText("Cancelling...")
                self.feature_engine.cancel_permutations()
            except Exception:
                pass

        btn_cancel.clicked.connect(_on_cancel)

        # Start worker thread
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

        # Show modal dialog (blocks UI but progress updates remain responsive)
        self._push_modal_overlay()
        try:
            dlg.exec()
        finally:
            self._pop_modal_overlay()
        return
    # PyQtGraph-only plot updater following BrainLinkRawEEG_Plot.py fix pattern
    def update_live_plot(self):
        """Update the live EEG plot with robust visibility diagnostics.

        Adds safeguards:
        - Re-create / re-add curve if it became detached
        - Explicit finite / NaN filtering (NaNs make curve vanish)
        - High-contrast pen enforcement if data appears flat
        - Force repaint occasionally
        """
        try:
            window_size = 1024
            # Snapshot buffer (avoid mutation mid-copy)
            buf = list(BL.live_data_buffer)
            n = len(buf)
            if n == 0:
                self.status_label.setText("Waiting for data...")
                return

            plot_size = min(window_size, n)
            data = np.array(buf[-plot_size:], dtype=np.float64)

            # Replace inf with finite values & guard against all-NaN
            if not np.all(np.isfinite(data)):
                finite_mask = np.isfinite(data)
                if finite_mask.any():
                    # Simple forward fill fallback
                    last_val = 0.0
                    for i in range(data.size):
                        if finite_mask[i]:
                            last_val = data[i]
                        else:
                            data[i] = last_val
                else:
                    data[:] = 0.0

            # Left-pad to fixed window
            if plot_size < window_size:
                pad = np.zeros(window_size - plot_size, dtype=data.dtype)
                data = np.concatenate([pad, data])

            x_data = np.arange(window_size, dtype=float)

            # Ensure curve exists & attached
            plot_item = self.plot_widget.getPlotItem()
            if not hasattr(self, 'live_curve') or self.live_curve is None:
                # Recreate with guaranteed visible pen
                try:
                    pen = pg.mkPen(color='yellow', width=3)
                except Exception:
                    pen = None
                self.live_curve = plot_item.plot(x_data, data, pen=pen)
            else:
                if self.live_curve not in plot_item.listDataItems():
                    try:
                        plot_item.addItem(self.live_curve)
                    except Exception:
                        pass
                try:
                    self.live_curve.setData(x_data, data)
                except Exception as _e_set:
                    # Attempt recreation if update failed
                    try:
                        plot_item.removeItem(self.live_curve)
                    except Exception:
                        pass
                    try:
                        self.live_curve = plot_item.plot(x_data, data, pen=pg.mkPen(color='yellow', width=3))
                    except Exception:
                        return

            # Dynamic y-range adjustment every 10 samples
            if n % 10 == 0:
                try:
                    y_min = float(np.min(data))
                    y_max = float(np.max(data))
                    if not np.isfinite(y_min) or not np.isfinite(y_max):
                        y_min, y_max = -50.0, 50.0
                    if abs(y_max - y_min) < 1e-6:
                        # Flat signal -> widen artificially so line is away from axes
                        mid = 0.5 * (y_min + y_max)
                        y_min = mid - 25.0
                        y_max = mid + 25.0
                    else:
                        pad = max((y_max - y_min) * 0.1, 10.0)
                        y_min -= pad
                        y_max += pad
                    plot_item.setXRange(0, window_size, padding=0)
                    plot_item.setYRange(y_min, y_max, padding=0)
                except Exception:
                    pass

            # Force a repaint occasionally (some platforms need this to reveal curve)
            if n % 50 == 0:
                try:
                    self.plot_widget.repaint()
                except Exception:
                    pass

            # Diagnostics: if line still invisible, enforce pen
            if n % 100 == 0:
                try:
                    # Heuristic: if variance tiny & centered, recolor pen for contrast
                    if np.var(data) < 1e-6:
                        self.live_curve.setPen(pg.mkPen(color='red', width=3))
                except Exception:
                    pass

            # Status update (throttled)
            if n % 25 == 0:
                try:
                    finite_points = int(np.isfinite(data).sum())
                    self.status_label.setText(
                        f"Buffer: {n} samples | Latest: {data[-1]:.1f} µV | Finite: {finite_points} | Plot: ✅ visible")
                except Exception:
                    pass
        except Exception as e:
            try:
                self.status_label.setText(f"Plot update error: {e}")
            except Exception:
                pass

    # Override to add auditory cue at task start
    def start_task(self):
        """Explicit task start override ensuring dialog always appears.

        Avoids relying on base implementation (which called an empty show_task_interface
        previously) and adds defensive logging + error handling so failures are visible.
        """
        # Prevent overlapping phases
        if getattr(self.feature_engine, 'current_state', None) != 'idle':
            try:
                self.log_message("Please stop current phase first")
            except Exception:
                pass
            return

        # Determine task type from combo (fallback safe)
        task_type = None
        try:
            if hasattr(self, 'task_combo'):
                task_type = self.task_combo.currentText()
        except Exception:
            task_type = None
        task_type = task_type or 'mental_math'

        # Audio cue (non-fatal)
        try:
            self._audio.play_start_task()
        except Exception:
            pass

        # Start calibration phase for task
        try:
            self.feature_engine.start_calibration_phase('task', task_type)
        except Exception as e:
            try:
                self.log_message(f"Failed to start task phase: {e}")
            except Exception:
                pass
            return

        # Update UI state controls if present
        try:
            if hasattr(self, 'task_label'):
                self.task_label.setText(f"Status: Recording {task_type}...")
            if hasattr(self, 'task_button'):
                self.task_button.setEnabled(False)
            if hasattr(self, 'stop_button'):
                self.stop_button.setEnabled(True)
        except Exception:
            pass

        # Log start
        try:
            self.log_message(f"✓ Started task: {task_type}")
        except Exception:
            pass

        # Launch the task dialog explicitly
        try:
            self.show_task_interface(task_type)
            try:
                self.log_message("Task interface launched")
            except Exception:
                pass
        except Exception as e:
            try:
                self.log_message(f"Task interface failed: {e}")
            except Exception:
                pass
            # Fail safe: stop phase so state machine not stuck
            try:
                self.feature_engine.stop_calibration_phase()
            except Exception:
                pass
            return

    # --- Task GUI (instructions + 60s auto-stop) ---
    def show_task_interface(self, task_type):
        try:
            self.close_task_interface()
        except Exception:
            pass

        tasks = getattr(BL, 'AVAILABLE_TASKS', {})
        task_cfg = tasks.get(task_type, {})
        phase_structure = task_cfg.get('phase_structure')
        duration = int(task_cfg.get('duration', 60))
        title = task_cfg.get('name', task_type.replace('_', ' ').title())
        general_instructions = task_cfg.get('instructions', 'Follow the on-screen instructions for this task.')

        # Build a per-condition instruction map from the multi-line instructions, e.g. "ORDER: ..."
        def _build_condition_instructions(instr_text: str):
            mapping = {}
            try:
                for line in (instr_text or '').splitlines():
                    if ':' in line:
                        key, val = line.split(':', 1)
                        k = key.strip().upper()
                        v = val.strip()
                        if k:
                            mapping[k] = f"{key.strip()}: {v}" if v else key.strip()
            except Exception:
                pass
            return mapping

        condition_instr_map = _build_condition_instructions(general_instructions)

        # Multi-phase protocol handling
        if phase_structure and isinstance(phase_structure, list) and len(phase_structure) > 0:
            dlg = QDialog(self)
            # Generic title without task name
            dlg.setWindowTitle("Task Session")
            
            # Set window icon
            try:
                icon_path = BL.resource_path(os.path.join('assets', 'favicon.ico'))
                if os.path.isfile(icon_path):
                    dlg.setWindowIcon(QIcon(icon_path))
            except Exception:
                pass
            
            try:
                dlg.setStyleSheet("background-color:#1e1e1e;color:#f0f0f0;")
            except Exception:
                pass
            layout = QVBoxLayout(dlg)
            # Improve spacing & padding
            try:
                layout.setContentsMargins(18, 18, 18, 18)
                layout.setSpacing(12)
            except Exception:
                pass

            # Large responsive sizing for better visibility (especially for emoface images)
            try:
                screen = QtWidgets.QApplication.primaryScreen()
                if screen:
                    avail = screen.availableGeometry()
                    # Use 85% of screen width and 90% of height for better image visibility
                    target_w = int(avail.width() * 0.85)
                    target_h = int(avail.height() * 0.90)
                    dlg.resize(target_w, target_h)
                    # Center the dialog on screen
                    dlg.move(
                        avail.left() + (avail.width() - target_w) // 2,
                        avail.top() + (avail.height() - target_h) // 2
                    )
                else:
                    dlg.resize(1200, 900)
            except Exception:
                # Fallback to large size
                dlg.resize(1200, 900)

            # (Task name hidden per user request; no header label added)

            phase_progress = QLabel("1 / ?")
            phase_progress.setAlignment(Qt.AlignCenter)
            phase_progress.setStyleSheet("font-size:12px;color:#99ccee;")
            layout.addWidget(phase_progress)

            # Check if task wants countdown timer hidden (for eyes-open tasks)
            hide_countdown = task_cfg.get('hide_countdown', False)
            
            timer_label = QLabel("..")
            timer_label.setAlignment(Qt.AlignCenter)
            timer_label.setStyleSheet("font-size:30px;font-weight:bold;color:#00FFAA;margin:4px 0;")
            
            # Hide timer for eyes-open tasks to avoid distraction
            if hide_countdown:
                timer_label.setVisible(False)
            else:
                layout.addWidget(timer_label)

            # Action banner (clearly tells user READ / THINK / LOOK / WRITE / WATCH / PREPARE)
            action_banner = QLabel("")
            action_banner.setAlignment(Qt.AlignCenter)
            action_banner.setStyleSheet("font-size:24px;font-weight:600;padding:10px;border-radius:6px;background:#333;color:#FFFFFF;margin:4px 0;")
            layout.addWidget(action_banner)

            # Removed explicit phase type label per user request (only phase count shown)
            phase_type_label = None  # keep variable for legacy references guarded below

            instruction_label = QLabel(general_instructions)
            instruction_label.setWordWrap(True)
            instruction_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            instruction_label.setStyleSheet("font-size:16px;line-height:1.4;")
            layout.addWidget(instruction_label)

            # Next phase preview (lets user know what's coming – EEG best practice reduces surprise / movement)
            next_phase_label = QLabel("")
            next_phase_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            next_phase_label.setStyleSheet("font-size:11px;color:#BBBBBB;font-style:italic;margin-top:2px;")
            layout.addWidget(next_phase_label)

            # Image placeholder (used for non-video media) with size constraints
            media_label = QLabel("")
            media_label.setAlignment(Qt.AlignCenter)
            media_label.setStyleSheet("background:#222;border:1px solid #333;padding:4px;")
            # Set maximum height to prevent overflow - images will be scaled to fit
            try:
                screen = QtWidgets.QApplication.primaryScreen()
                if screen:
                    avail = screen.availableGeometry()
                    # Use larger space for media (especially important for emoface images)
                    max_media_height = int(avail.height() * 0.60)  # 60% of screen for media
                    media_label.setMaximumHeight(max_media_height)
                    # CRITICAL: Set minimum size so label doesn't collapse when empty
                    media_label.setMinimumHeight(int(avail.height() * 0.40))  # 40% minimum
                    media_label.setMinimumWidth(600)  # Larger minimum width for better image display
                else:
                    media_label.setMaximumHeight(700)
                    media_label.setMinimumHeight(500)
                    media_label.setMinimumWidth(600)
            except Exception:
                media_label.setMaximumHeight(700)
                media_label.setMinimumHeight(500)
                media_label.setMinimumWidth(600)
            media_label.setScaledContents(False)  # Maintain aspect ratio
            layout.addWidget(media_label)

            # Optional video widget (only create if a video phase exists and embedding is allowed)
            has_video_phase = any(isinstance(p, dict) and p.get('type') == 'video' for p in (phase_structure or []))
            force_no_video = os.environ.get('BL_FORCE_NO_VIDEO') in ('1','true','True')
            if has_video_phase and not force_no_video and _allow_embedded_video():
                if _lazy_import_multimedia() and self._video_widget is None:
                    try:
                        self._video_widget = QVideoWidget(dlg)
                        self._video_widget.setVisible(False)
                        layout.addWidget(self._video_widget)
                    except Exception:
                        self._video_widget = None
            else:
                # Ensure any previous video widget stays hidden during pure image tasks
                try:
                    if self._video_widget:
                        self._video_widget.setVisible(False)
                except Exception:
                    pass
                # Also ensure we don't carry a stale player in non-embed mode
                try:
                    if not _allow_embedded_video():
                        self._video_player = None
                except Exception:
                    pass

            prompt_label = QLabel("")
            prompt_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            prompt_label.setWordWrap(True)
            prompt_label.setStyleSheet("font-size:13px;margin-top:6px;")
            # Constrain prompt label height to prevent excessive growth
            try:
                prompt_label.setMaximumHeight(150)
            except Exception:
                pass
            layout.addWidget(prompt_label)

            stop_btn = QPushButton("Stop Now")
            layout.addWidget(stop_btn)

            # Stretch factors to keep timer & header compact while preventing overflow
            try:
                layout.setStretchFactor(media_label, 3)  # Give media more priority
                layout.setStretchFactor(prompt_label, 1)  # Reduced from 2
            except Exception:
                pass

            self._task_dialog = dlg
            try:
                self._register_task_dialog(dlg)
            except Exception:
                pass
            self._phase_structure = phase_structure
            self._phase_index = 0
            self._phase_remaining = phase_structure[0].get('duration', 1)
            self._task_seconds_remaining = duration  # total remaining (optional)

            # Helper mappings for phase semantics
            def _phase_action(ptype: str) -> str:
                p = (ptype or '').lower()
                return {
                    'read': 'READ',
                    'viewing': 'LOOK',
                    'writing': 'WRITE',
                    'video': 'WATCH',
                    'cue': 'PREPARE',
                    'task': 'THINK',
                    'thinking': 'THINK'
                }.get(p, 'FOCUS')

            def _phase_banner_text(ptype: str) -> str:
                act = _phase_action(ptype)
                if act == 'PREPARE':
                    return 'GET READY'
                if act == 'FOCUS':
                    return 'FOCUS'
                # Imperative form for user clarity
                return f"{act} NOW"

            def _phase_banner_style(ptype: str) -> str:
                colors = {
                    'read': ('#2e86de', '#ffffff'),
                    'viewing': ('#f1c40f', '#000000'),
                    'writing': ('#9b59b6', '#ffffff'),
                    'video': ('#e67e22', '#000000'),
                    'cue': ('#7f8c8d', '#ffffff'),
                    'task': ('#16a085', '#ffffff'),
                    'thinking': ('#16a085', '#ffffff')
                }
                bg, fg = colors.get(ptype.lower(), ('#34495e', '#ffffff'))
                return f"font-size:24px;font-weight:600;padding:10px;border-radius:6px;background:{bg};color:{fg};margin:4px 0;"

            def _next_phase_preview(idx: int) -> str:
                if idx + 1 >= len(self._phase_structure):
                    return "Final phase."
                nxt = self._phase_structure[idx + 1]
                ntype = nxt.get('type', 'phase')
                act = _phase_action(ntype)
                dur = nxt.get('duration')
                if dur:
                    return f"Next: {act} for {dur}s"
                return f"Next: {act}"

            # Helper to load image
            def _ensure_player():
                # Only allow player if a video phase exists in this task and embedding is allowed
                if not any(p.get('type') == 'video' for p in (self._phase_structure or [])):
                    return False
                if not _allow_embedded_video():
                    return False
                if not _lazy_import_multimedia():
                    return False
                if self._video_player is None:
                    try:
                        self._video_player = QMediaPlayer(self)
                        self._video_audio = QAudioOutput(self)
                        self._video_player.setAudioOutput(self._video_audio)
                        if self._video_widget is not None:
                            try:
                                # Newer PySide6 API
                                self._video_player.setVideoOutput(self._video_widget)
                            except Exception:
                                pass
                    except Exception:
                        self._video_player = None
                        return False
                return self._video_player is not None

            def _stop_video():
                if self._video_player:
                    try:
                        # Graceful teardown to avoid native crashes
                        try:
                            # Clear media source first
                            try:
                                self._video_player.setSource(QMediaSource())  # type: ignore
                            except Exception:
                                try:
                                    self._video_player.setSource(QUrl())  # type: ignore
                                except Exception:
                                    pass
                            # Detach video output if API supports it
                            try:
                                self._video_player.setVideoOutput(None)  # type: ignore
                            except Exception:
                                pass
                            self._video_player.pause()
                        except Exception:
                            pass
                        self._video_player.stop()
                    except Exception:
                        pass
                if self._video_widget:
                    try:
                        self._video_widget.setVisible(False)
                    except Exception:
                        pass
                self._current_video_phase = False

            def _play_video(filename: str):
                # Attempt to play provided video file; fallback to common defaults
                print(f"DEBUG _play_video: filename={filename}")
                target_names = []
                if filename:
                    target_names.append(filename)
                # Accept simple name too
                if 'curiosity.mp4' not in target_names:
                    target_names.append('curiosity.mp4')
                if 'curiosity_clip_04.mp4' not in target_names:
                    target_names.append('curiosity_clip_04.mp4')
                if 'curiosity_clip_01.mp4' not in target_names:
                    target_names.append('curiosity_clip_01.mp4')

                print(f"DEBUG _play_video: searching for video files: {target_names}")
                
                # Resolve a file path
                found_path = None
                for name in target_names:
                    try:
                        p = BL.resource_path(os.path.join('assets', name))
                        print(f"DEBUG _play_video: checking {p}, exists={os.path.isfile(p)}")
                        if os.path.isfile(p):
                            found_path = p
                            print(f"DEBUG _play_video: FOUND video at: {found_path}")
                            break
                        if os.path.isfile(name):
                            found_path = name
                            print(f"DEBUG _play_video: FOUND video at: {found_path}")
                            break
                    except Exception as e:
                        print(f"DEBUG _play_video: error checking {name}: {e}")
                        continue
                
                if not found_path:
                    msg = f"[Missing video: {target_names[0]}]"
                    print(f"DEBUG _play_video: {msg}")
                    media_label.setText(msg)
                    return

                print(f"DEBUG _play_video: DISABLE_QT_MULTIMEDIA={DISABLE_QT_MULTIMEDIA}")
                print(f"DEBUG _play_video: _allow_embedded_video()={_allow_embedded_video()}")
                print(f"DEBUG _play_video: _ensure_player()={_ensure_player()}")
                
                # If Qt multimedia disabled/unavailable, or embedding not allowed, fallback to external player
                if DISABLE_QT_MULTIMEDIA or not _allow_embedded_video() or not _ensure_player():
                    try:
                        msg = f"[Opening external video player for: {os.path.basename(found_path)}]"
                        print(f"DEBUG _play_video: {msg}")
                        media_label.setText(msg)
                        
                        if platform.system() == 'Windows':
                            print(f"DEBUG _play_video: Using os.startfile() on Windows")
                            os.startfile(found_path)  # type: ignore[attr-defined]
                            print(f"DEBUG _play_video: os.startfile() returned successfully")
                        else:
                            # Non-Windows simple attempt
                            import subprocess, shlex
                            # Prefer xdg-open / open (mac) / fallback to vlc if installed
                            opener = 'open' if platform.system() == 'Darwin' else 'xdg-open'
                            cmd = [opener, found_path]
                            print(f"DEBUG _play_video: Using {opener} command: {cmd}")
                            try:
                                subprocess.Popen(cmd)
                                print(f"DEBUG _play_video: Popen returned successfully")
                            except Exception as e:
                                # Last resort: try vlc
                                print(f"DEBUG _play_video: {opener} failed, trying vlc: {e}")
                                subprocess.Popen(['vlc', '--play-and-exit', found_path])
                        self._current_video_phase = False  # Not an embedded phase
                        print(f"DEBUG _play_video: External video launched successfully")
                    except Exception as e:
                        msg = f"[External video launch failed: {e}]"
                        print(f"DEBUG _play_video: ERROR: {msg}")
                        media_label.setText(msg)
                    return

                # At this point we have Qt multimedia player (only if allow_embedded_video)
                try:
                    if not _allow_embedded_video():
                        raise RuntimeError('Embedding disabled by policy')
                    if self._video_player and self._current_video_phase:
                        self._video_player.stop()
                except Exception:
                    pass
                try:
                    if self._video_widget:
                        self._video_widget.setVisible(True)
                    media_label.setVisible(False)
                except Exception:
                    pass
                try:
                    try:
                        self._video_player.setSource(QMediaSource(QUrl.fromLocalFile(found_path)))  # type: ignore
                    except Exception:
                        self._video_player.setSource(QUrl.fromLocalFile(found_path))  # type: ignore
                    try:
                        if hasattr(self._video_player, 'errorOccurred') and not hasattr(self._video_player, '_enh_err_connected'):
                            self._video_player.errorOccurred.connect(lambda err: media_label.setText(f"[Video error: {err}]") if media_label.isVisible() else None)
                            self._video_player._enh_err_connected = True  # type: ignore
                    except Exception:
                        pass
                    try:
                        if hasattr(self._video_player, 'mediaStatusChanged') and not hasattr(self._video_player, '_enh_status_connected'):
                            def _st_chg(st):
                                if int(st) in (6, 7):
                                    try:
                                        if self._video_widget:
                                            self._video_widget.setVisible(False)
                                        media_label.setVisible(True)
                                        if int(st) == 7:
                                            media_label.setText('[Video invalid]')
                                    except Exception:
                                        pass
                            self._video_player.mediaStatusChanged.connect(_st_chg)
                            self._video_player._enh_status_connected = True  # type: ignore
                    except Exception:
                        pass
                    self._video_player.play()
                    self._current_video_phase = True
                except Exception:
                    # Fall back to external player
                    try:
                        media_label.setVisible(True)
                        media_label.setText('[Video playback failed; opening external player]')
                        if platform.system() == 'Windows':
                            os.startfile(found_path)  # type: ignore[attr-defined]
                        else:
                            import subprocess
                            opener = 'open' if platform.system() == 'Darwin' else 'xdg-open'
                            try:
                                subprocess.Popen([opener, found_path])
                            except Exception:
                                subprocess.Popen(['vlc', '--play-and-exit', found_path])
                        self._current_video_phase = False
                    except Exception:
                        pass

            def _set_image(img_name):
                if not img_name:
                    media_label.clear()
                    return
                try:
                    path = BL.resource_path(os.path.join('assets', img_name))
                    print(f"DEBUG _set_image: img_name={img_name}, path={path}, exists={os.path.isfile(path)}")
                    if os.path.isfile(path):
                        try:
                            pm = QPixmap(path)
                            print(f"DEBUG _set_image: QPixmap loaded, isNull={pm.isNull()}, size={pm.width()}x{pm.height()}")
                        except Exception as e:
                            print(f"DEBUG _set_image: QPixmap load error: {e}")
                            media_label.setText(f"[Image load error: {e}]")
                            return
                        if pm.isNull():
                            print(f"DEBUG _set_image: QPixmap is null!")
                            media_label.setText(f"[Invalid image: {img_name}]")
                            return
                        
                        # CRITICAL FIX: Get actual available size from the label
                        # The media_label has maximum constraints set, so use those
                        try:
                            # Get the label's current size (after layout has processed)
                            available_width = media_label.width()
                            available_height = media_label.height()
                            
                            # If label hasn't been sized yet by layout, use maximum constraints
                            if available_width < 100 or available_height < 100:
                                # Force the dialog and layout to update
                                if dlg.isVisible():
                                    dlg.update()
                                    QtWidgets.QApplication.processEvents()
                                # Get maximum constraints
                                max_width = media_label.maximumWidth()
                                max_height = media_label.maximumHeight()
                                # Use reasonable defaults if maximums are infinite
                                available_width = max_width if max_width < 16777215 else 640
                                available_height = max_height if max_height < 16777215 else 400
                            
                            print(f"DEBUG _set_image: available size = {available_width}x{available_height}")
                            print(f"DEBUG _set_image: original pixmap size = {pm.width()}x{pm.height()}")
                            
                            # Scale image to fit within available space, maintaining aspect ratio
                            # This ensures the ENTIRE image is visible without cropping
                            scaled_pm = pm.scaled(
                                available_width, 
                                available_height, 
                                Qt.KeepAspectRatio,  # Maintain aspect ratio - fits entire image
                                Qt.SmoothTransformation  # High quality scaling
                            )
                            print(f"DEBUG _set_image: scaled pixmap size = {scaled_pm.width()}x{scaled_pm.height()}")
                            
                            # Set the pixmap
                            media_label.setPixmap(scaled_pm)
                            print(f"DEBUG _set_image: setPixmap() called successfully")
                            
                            # Make label visible and force repaint
                            media_label.setVisible(True)
                            media_label.update()
                            print(f"DEBUG _set_image: image displayed")
                            
                        except Exception as e:
                            print(f"DEBUG _set_image: scaling error: {e}")
                            # Fallback: use a safe default size
                            scaled_pm = pm.scaled(640, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            media_label.setPixmap(scaled_pm)
                            media_label.setVisible(True)
                            print(f"DEBUG _set_image: fallback scaling used")
                        
                        # Cache original for fullscreen cover scaling
                        try:
                            self._fs_last_pm = pm
                        except Exception:
                            pass
                        # Also update fullscreen viewer if active
                        try:
                            if hasattr(self, '_fs_image_label') and self._fs_image_label is not None:
                                self._fs_image_label.setPixmap(pm.scaled(self._fs_image_label.width(), self._fs_image_label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
                media_label.setText(f"[Missing media: {img_name}]")

            # Fullscreen image support for IND tasks
            self._fs_image_window = None
            self._fs_image_label = None
            self._fs_last_pm = None  # store original pixmap for dynamic rescaling
            def _cover_scale(pm: QPixmap, target_w: int, target_h: int) -> QPixmap:
                try:
                    if pm is None or pm.isNull() or target_w <= 0 or target_h <= 0:
                        return pm
                    iw, ih = pm.width(), pm.height()
                    if iw <= 0 or ih <= 0:
                        return pm
                    # Compute cover scale (fill entire area, then center crop)
                    scale = max(target_w / iw, target_h / ih)
                    new_w = int(iw * scale)
                    new_h = int(ih * scale)
                    scaled = pm.scaled(new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    if scaled.isNull():
                        return pm
                    # Center crop to exact target size
                    x_off = max(0, (scaled.width() - target_w) // 2)
                    y_off = max(0, (scaled.height() - target_h) // 2)
                    return scaled.copy(x_off, y_off, min(target_w, scaled.width() - x_off), min(target_h, scaled.height() - y_off))
                except Exception:
                    return pm

            def _refresh_fullscreen_image_safe():
                """Attempt a cover-style rescale of the fullscreen image (robust first phase)."""
                try:
                    if self._fs_image_window is None or self._fs_image_label is None or self._fs_last_pm is None:
                        return
                    # Ensure we have up-to-date geometry (force a processEvents if size looks tiny)
                    win = self._fs_image_window
                    w = win.width()
                    h = win.height()
                    if w < 50 or h < 50:
                        try:
                            QtWidgets.QApplication.processEvents()
                            w = win.width(); h = win.height()
                        except Exception:
                            pass
                    pm = _cover_scale(self._fs_last_pm, w, h)
                    if pm and not pm.isNull():
                        self._fs_image_label.setPixmap(pm)
                except Exception:
                    pass

            # Expose for timer calls
            self._refresh_fullscreen_image_safe = _refresh_fullscreen_image_safe  # type: ignore
            def _open_fullscreen_image(img_name):
                """Show (or refresh) the fullscreen image window.

                Previous implementation used WA_DeleteOnClose which destroyed the widget;
                subsequent phases then attempted to reuse a deleted object and nothing
                appeared. We now keep a persistent hidden window and simply re‑show it.
                """
                try:
                    create_new = False
                    if self._fs_image_window is None:
                        create_new = True
                    else:
                        # If it was previously closed with close(), consider it unusable
                        try:
                            # isVisible() returns False when hidden; that's fine – we reuse.
                            # We only recreate if underlying C++ object was deleted (sip check)
                            import sip  # type: ignore
                            if sip.isdeleted(self._fs_image_window):
                                create_new = True
                        except Exception:
                            # Fallback: if accessing raises, recreate
                            create_new = False if self._fs_image_window is not None else True
                    if create_new:
                        self._fs_image_window = QtWidgets.QWidget()
                        self._fs_image_window.setWindowTitle("Focus Image")
                        self._fs_image_window.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
                        # Avoid DeleteOnClose so we can reuse between phases
                        lay = QVBoxLayout(self._fs_image_window)
                        lay.setContentsMargins(0,0,0,0)
                        self._fs_image_label = QLabel("")
                        self._fs_image_label.setAlignment(Qt.AlignCenter)
                        lay.addWidget(self._fs_image_label)
                        # Install event filter for dynamic rescale
                        try:
                            self._fs_image_window.installEventFilter(self)
                        except Exception:
                            pass
                    # Always (re)load image before showing
                    _set_image(img_name)
                    # If we have cached original pixmap, attempt immediate cover scale
                    try:
                        if self._fs_last_pm is not None:
                            QtCore.QTimer.singleShot(10, self._refresh_fullscreen_image_safe)
                    except Exception:
                        pass
                    try:
                        self._fs_image_window.showFullScreen()
                    except Exception:
                        self._fs_image_window.show()
                    # Post-show refresh once geometry settled
                    try:
                        QtCore.QTimer.singleShot(80, self._refresh_fullscreen_image_safe)
                    except Exception:
                        pass
                except Exception:
                    pass

            def _close_fullscreen_image():
                """Hide the fullscreen image window instead of destroying it."""
                try:
                    if self._fs_image_window is not None:
                        # Hide instead of close so we can reuse on next viewing phase
                        self._fs_image_window.hide()
                except Exception:
                    pass

            # Helper to set prompt
            def _set_prompt(phase):
                prompt_label.clear()
                if task_type in ('diverse_thinking', 'reappraisal') and 'prompt_index' in phase:
                    prompts = (task_cfg.get('media') or {}).get('prompts', [])
                    idx = phase.get('prompt_index')
                    if isinstance(prompts, list) and idx is not None and idx < len(prompts):
                        p = prompts[idx]
                        # Build HTML-like rich text
                        parts = []
                        title_txt = p.get('title') or ''
                        if title_txt:
                            parts.append(f"<b>{title_txt}</b>")
                        if task_type == 'diverse_thinking':
                            body = p.get('text', '')
                            if body:
                                parts.append(body.replace('\n', '<br>'))
                        elif task_type == 'reappraisal':
                            scenario = p.get('scenario', '')
                            instr = p.get('instruction', '')
                            if scenario:
                                parts.append(f"Scenario: {scenario}")
                            if instr:
                                parts.append(f"<i>{instr}</i>")
                        prompt_label.setText('<br><br>'.join(parts))
                elif task_type == 'curiosity' and phase.get('type') == 'video':
                    mf = phase.get('media_file', 'video')
                    prompt_label.setText(f"Video playing: {mf} (placeholder)")
                    idx = phase.get('media_index', 0)
                    prompt_label.setText(f"Face {idx+1} / {len((task_cfg.get('media') or {}).get('images', []))}")

            def _update_phase_ui():
                if self._phase_index >= len(self._phase_structure):
                    # Completed
                    # Stop LED stimulator if still running
                    try:
                        if (self._led_stimulator is not None
                                and self._led_stimulator.stimulating):
                            self._led_stimulator.stop_stimulation()
                            print("[LED] Stopped 40 Hz LED stimulation (task completed)")
                    except Exception:
                        pass
                    try:
                        self._audio.play_end_task()
                    except Exception:
                        pass
                    try:
                        _close_fullscreen_image()
                    except Exception:
                        pass
                    self.stop_calibration()
                    return
                phase = self._phase_structure[self._phase_index]
                ptype = phase.get('type', 'phase')
                
                # Start recording for this phase if it has record=True
                try:
                    should_record = phase.get('record', False)
                    if should_record:
                        if hasattr(self.feature_engine, 'start_phase'):
                            self.feature_engine.start_phase(
                                phase='task',
                                task_type=task_type,
                                phase_subtype=ptype,
                                should_record=True
                            )
                            print(f"[PHASE] Started recording: {ptype} (task: {task_type})")
                except Exception as e:
                    print(f"[PHASE] Error starting phase recording: {e}")

                # ---- 40 Hz LED stimulator: auto-trigger on task phase ----
                try:
                    if (task_type == '40hz_stimulation' and ptype == 'task'
                            and self._led_stimulator is not None):
                        # Connect if not already connected
                        if not self._led_stimulator.connected:
                            self._led_stimulator.connect()
                        if self._led_stimulator.connected:
                            stim_dur = phase.get('duration', 150)
                            self._led_stimulator.set_duration(float(stim_dur))
                            self._led_stimulator.start_stimulation()
                            print(f"[LED] Started 40 Hz LED stimulation for {stim_dur}s")
                        else:
                            print("[LED] WARNING: Could not connect to Arduino LED stimulator")
                except Exception as led_err:
                    print(f"[LED] Error starting LED stimulation: {led_err}")
                # Safety: if coming into a non-viewing/task phase, ensure any fullscreen image is closed
                try:
                    if task_type in ('order_surprise', 'num_form') and ptype not in ('viewing', 'task'):
                        _close_fullscreen_image()
                except Exception:
                    pass
                phase_progress.setText(f"{self._phase_index+1} / {len(self._phase_structure)}")
                # Instruction precedence: explicit phase instruction else generic
                instr_txt = phase.get('instruction') or general_instructions
                # Dynamic cue instructions for specific protocols
                if ptype == 'cue':
                    token = (phase.get('instruction') or '').strip().upper()
                    if task_type in ('order_surprise', 'num_form') and token:
                        instr_txt = condition_instr_map.get(token, instr_txt)
                # Filter out 'wait for the countdown' outside cue/read phases
                try:
                    if 'wait for the countdown' in instr_txt.lower() and ptype.lower() not in ('cue','read'):
                        lines = [ln for ln in instr_txt.splitlines() if 'wait for the countdown' not in ln.lower()]
                        instr_txt = '\n'.join(lines).strip()
                except Exception:
                    pass

                # For 40hz_stimulation: hide instruction text during rest/task phases (banner is sufficient)
                if task_type == '40hz_stimulation' and ptype in ('rest', 'task'):
                    instruction_label.hide()
                else:
                    instruction_label.show()
                    instruction_label.setText(instr_txt)

                # Action banner + color
                try:
                    action_banner.setText(_phase_banner_text(ptype))
                    action_banner.setStyleSheet(_phase_banner_style(ptype))
                except Exception:
                    pass

                # Next phase preview
                try:
                    # For 40hz_stimulation: only show next phase during cue phases, hide during rest/task
                    if task_type == '40hz_stimulation':
                        if ptype == 'cue':
                            next_phase_label.show()
                            next_phase_label.setText(_next_phase_preview(self._phase_index))
                        else:
                            next_phase_label.hide()
                    else:
                        next_phase_label.setText(_next_phase_preview(self._phase_index))
                except Exception:
                    pass

                # Lightweight audio cue per actionable phase (skip pure cue)
                try:
                    if ptype.lower() not in ('cue',):
                        if hasattr(self._audio, 'play_phase_transition'):
                            self._audio.play_phase_transition()
                except Exception:
                    pass

                # Stop any prior video if switching phases
                if self._current_video_phase and ptype != 'video':
                    _stop_video()
                    try:
                        media_label.setVisible(True)
                    except Exception:
                        pass

                # Media handling
                if ptype == 'video' and task_type == 'curiosity':
                    # Play integrated curiosity video (prefers curiosity_clip_04.mp4)
                    _play_video(phase.get('media_file', 'curiosity_clip_04.mp4'))
                elif task_type == 'emotion_face' and ptype in ('viewing','writing'):
                    imgs = (task_cfg.get('media') or {}).get('images', [])
                    idx = phase.get('media_index', 0)
                    _stop_video()
                    try:
                        if self._video_widget:
                            self._video_widget.setVisible(False)
                        media_label.setVisible(True)
                    except Exception:
                        pass
                    if 0 <= idx < len(imgs):
                        _set_image(imgs[idx])
                    else:
                        media_label.clear()
                elif 'media_file' in phase and ptype in ('task', 'viewing'):
                    _stop_video()
                    try:
                        if self._video_widget:
                            self._video_widget.setVisible(False)
                        media_label.setVisible(True)
                    except Exception:
                        pass
                    img_name = phase.get('media_file')
                    # For order_surprise / num_form always route through fullscreen helper
                    # so ORDER/NUMBERS first viewing uses identical scaling path as SURPRISE/FORMS.
                    if task_type in ('order_surprise','num_form') and ptype in ('viewing','task'):
                        try:
                            _open_fullscreen_image(img_name)
                        except Exception:
                            # Fallback still show inline
                            try:
                                _set_image(img_name)
                            except Exception:
                                pass
                    else:
                        # Standard inline display for other tasks
                        _set_image(img_name)
                        try:
                            _close_fullscreen_image()
                        except Exception:
                            pass
                else:
                    _stop_video()
                    try:
                        if self._video_widget:
                            self._video_widget.setVisible(False)
                        media_label.setVisible(True)
                        media_label.clear()
                    except Exception:
                        pass
                    try:
                        _close_fullscreen_image()
                    except Exception:
                        pass

                _set_prompt(phase)
                # Set remaining for this phase
                self._phase_remaining = int(phase.get('duration', 1))
                timer_label.setText(str(self._phase_remaining))

            # Timer per second
            t = QTimer(self)
            t.setInterval(1000)

            def tick():
                try:
                    self._phase_remaining -= 1
                    if self._phase_remaining <= 0:
                        # Advance
                        # Stop recording for current phase if it was being recorded
                        try:
                            current_phase_def = self._phase_structure[self._phase_index]
                            if current_phase_def.get('record', False):
                                # Stop the current recording phase
                                if hasattr(self.feature_engine, 'stop_phase'):
                                    self.feature_engine.stop_phase()
                        except Exception as e:
                            print(f"[PHASE] Error stopping phase recording: {e}")

                        # ---- 40 Hz LED stimulator: stop when task phase ends ----
                        try:
                            if (task_type == '40hz_stimulation'
                                    and current_phase_def.get('type') == 'task'
                                    and self._led_stimulator is not None
                                    and self._led_stimulator.stimulating):
                                self._led_stimulator.stop_stimulation()
                                print("[LED] Stopped 40 Hz LED stimulation (phase ended)")
                        except Exception as led_err:
                            print(f"[LED] Error stopping LED stimulation: {led_err}")
                        
                        # Before advancing, ensure fullscreen image (if any) is closed when leaving look phases
                        try:
                            prev_phase = self._phase_structure[self._phase_index]
                            prev_ptype = prev_phase.get('type', 'phase')
                            if task_type in ('order_surprise', 'num_form') and prev_ptype in ('viewing', 'task'):
                                _close_fullscreen_image()
                        except Exception:
                            pass
                        # Stop video if current phase was video before advancing
                        if self._current_video_phase:
                            _stop_video()
                        self._phase_index += 1
                        _update_phase_ui()
                        return
                    timer_label.setText(str(self._phase_remaining))
                except Exception:
                    try:
                        t.stop()
                        self.stop_calibration()
                    except Exception:
                        pass

            t.timeout.connect(tick)
            self._task_timer = t
            _update_phase_ui()
            self._task_timer.start()

            def manual_stop():
                try:
                    self._task_timer.stop()
                except Exception:
                    pass
                # Stop LED stimulator on manual abort
                try:
                    if (self._led_stimulator is not None
                            and self._led_stimulator.stimulating):
                        self._led_stimulator.stop_stimulation()
                        print("[LED] Stopped 40 Hz LED stimulation (manual stop)")
                except Exception:
                    pass
                try:
                    _stop_video()
                except Exception:
                    pass
                try:
                    _close_fullscreen_image()
                except Exception:
                    pass
                self.stop_calibration()

            stop_btn.clicked.connect(manual_stop)

            try:
                dlg.setModal(True)
                dlg.setWindowModality(QtCore.Qt.ApplicationModal)
            except Exception:
                pass

            # Use the same overlay semantics as the protocol dialog for consistent dimming
            overlay_widget = self._push_modal_overlay()
            if overlay_widget is None:
                try:
                    fallback = QtWidgets.QFrame(self)
                    fallback.setObjectName("ModalOverlay")
                    fallback.setGeometry(self.rect())
                    fallback.setStyleSheet("background-color: rgba(15, 23, 42, 200);")
                    fallback.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
                    fallback.show()
                    fallback.raise_()
                    self._modal_overlay = fallback
                    self._overlay_refcount = max(getattr(self, '_overlay_refcount', 0), 1)
                    overlay_widget = fallback
                except Exception:
                    overlay_widget = None
            if overlay_widget is not None:
                try:
                    overlay_widget.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

                    def _overlay_click(_event, dialog_ref=dlg):
                        try:
                            if dialog_ref is not None and dialog_ref.isVisible():
                                dialog_ref.raise_()
                        except Exception:
                            pass

                    overlay_widget.mousePressEvent = _overlay_click  # type: ignore[assignment]
                except Exception:
                    pass
            # Skip positioning since dialog is fullscreen
            # try:
            #     QtCore.QTimer.singleShot(0, lambda d=dlg: self._position_task_dialog(d))
            # except Exception:
            #     pass
            try:
                dlg.exec()
            finally:
                self._pop_modal_overlay()
            return

        # Fallback: single-phase (cognitive micro-task) dialog
        # --- (existing single-phase implementation retained) ---
        try:
            self.log_message(f"Launching single-phase task dialog: {task_type} ({duration}s)")
        except Exception:
            pass
        dlg = QDialog(self)
        dlg.setWindowTitle("Task Session")
        try:
            dlg.setStyleSheet("background-color: #1e1e1e;")
        except Exception:
            pass
        layout = QVBoxLayout(dlg)
        try:
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(14)
        except Exception:
            pass
        # Responsive width
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                target_w = min(max(int(avail.width() * 0.35), 520), min(780, avail.width()-100))
                target_h = min(max(int(avail.height() * 0.40), 420), int(avail.height()*0.75))
                dlg.resize(target_w, target_h)
                dlg.setMinimumWidth(int(target_w * 0.9))
        except Exception:
            dlg.resize(600, 480)
        instr = QLabel(general_instructions, dlg)
        instr.setWordWrap(True)
        instr.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        try:
            instr.setStyleSheet("font-size: 14px; color: #e0f7fa;")
        except Exception:
            pass
        layout.addWidget(instr)
        timer_label = QLabel(str(duration), dlg)
        timer_label.setAlignment(Qt.AlignCenter)
        try:
            timer_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #00FFAA;")
        except Exception:
            pass
        layout.addWidget(timer_label)
        stop_btn = QPushButton("Stop Now", dlg)
        layout.addWidget(stop_btn)
        self._task_dialog = dlg
        try:
            self._register_task_dialog(dlg)
        except Exception:
            pass
        self._task_seconds_remaining = duration
        t = QTimer(self)
        t.setInterval(1000)
        def tick_single():
            try:
                self._task_seconds_remaining -= 1
                if self._task_seconds_remaining <= 0:
                    t.stop()
                    try:
                        self._audio.play_end_task()
                    except Exception:
                        pass
                    self.stop_calibration()
                    return
                timer_label.setText(str(self._task_seconds_remaining))
            except Exception:
                try:
                    t.stop(); self.stop_calibration()
                except Exception:
                    pass
        t.timeout.connect(tick_single)
        self._task_timer = t
        self._task_timer.start()
        def manual_stop_single():
            try:
                self._task_timer.stop()
            except Exception:
                pass
            self.stop_calibration()
        stop_btn.clicked.connect(manual_stop_single)
        try:
            dlg.setModal(True)
            dlg.setWindowModality(QtCore.Qt.ApplicationModal)
        except Exception:
            pass
        # Use the same overlay semantics as the pathway selection dialog
        overlay_widget = self._push_modal_overlay()
        if overlay_widget is None:
            try:
                fallback = QtWidgets.QFrame(self)
                fallback.setObjectName("ModalOverlay")
                fallback.setGeometry(self.rect())
                fallback.setStyleSheet("background-color: rgba(15, 23, 42, 200);")
                fallback.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
                fallback.show()
                fallback.raise_()
                self._modal_overlay = fallback
                self._overlay_refcount = max(getattr(self, '_overlay_refcount', 0), 1)
                overlay_widget = fallback
            except Exception:
                overlay_widget = None
        if overlay_widget is not None:
            try:
                overlay_widget.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

                def _overlay_click_single(_event, dialog_ref=dlg):
                    try:
                        if dialog_ref is not None and dialog_ref.isVisible():
                            dialog_ref.raise_()
                    except Exception:
                        pass

                overlay_widget.mousePressEvent = _overlay_click_single  # type: ignore[assignment]
            except Exception:
                pass
        try:
            QtCore.QTimer.singleShot(0, lambda d=dlg: self._position_task_dialog(d))
        except Exception:
            pass
        try:
            dlg.exec()
        finally:
            self._pop_modal_overlay()

    def close_task_interface(self):
        # Stop timer and close dialog if present
        try:
            if self._task_timer is not None:
                self._task_timer.stop()
        except Exception:
            pass
        finally:
            self._task_timer = None

        try:
            if self._task_dialog is not None:
                self._task_dialog.close()
        except Exception:
            pass
        finally:
            self._task_dialog = None
        self._release_task_overlay()

    def _position_task_dialog(self, dlg: QtWidgets.QWidget) -> None:
        """Anchor the task dialog closer to the top of the main window for peripheral vision."""
        try:
            if dlg is None:
                return
            screen = QtWidgets.QApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else None
            target_rect = None
            try:
                if self is not None and self.isVisible():
                    target_rect = self.frameGeometry()
            except Exception:
                target_rect = None
            if target_rect is None:
                target_rect = avail
            if target_rect is None:
                return
            dlg_rect = dlg.frameGeometry()
            w = dlg_rect.width() or dlg.width()
            h = dlg_rect.height() or dlg.height()
            center_x = target_rect.center().x()
            # Position closer to the top (approx 12% from the top edge)
            top_y = target_rect.top() + int(target_rect.height() * 0.08)
            x = center_x - w // 2
            y = top_y
            if avail is not None:
                max_x = avail.right() - w
                max_y = avail.bottom() - h
                x = max(avail.left(), min(x, max_x))
                y = max(avail.top(), min(y, max_y))
            dlg.move(int(x), int(y))
        except Exception:
            pass

    # Guard: avoid reconnecting if already connected
    def on_connect_clicked(self):
        try:
            if getattr(self, 'serial_obj', None) and getattr(self.serial_obj, 'is_open', False):
                self.log_message("Already connected to device; skipping reconnect.")
                return
        except Exception:
            pass
        # Call base to perform login/connect
        res = super().on_connect_clicked()
        # After login completes, show protocol selection (baseline + cognitive are mandatory regardless)
        # Poll briefly for jwt_token to be set by base flow.
        def _poll_for_login():
            try:
                if getattr(self, 'jwt_token', None):
                    self._show_protocol_selection_dialog()
                    return  # stop polling
            except Exception:
                pass
            # keep polling until token appears or timeout
            self._protocol_poll_tries += 1
            if self._protocol_poll_tries < 50:  # ~5s at 100ms interval
                QtCore.QTimer.singleShot(100, _poll_for_login)

        self._protocol_poll_tries = 0
        QtCore.QTimer.singleShot(100, _poll_for_login)
        return res

    def _show_protocol_selection_dialog(self):
        # If already selected, do nothing
        if self._selected_protocol:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Select Protocol")
        dlg.setModal(True)
        dlg.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
        dlg.setMinimumWidth(420)

        title_label = QLabel("Choose your pathway")
        title_label.setObjectName("DialogTitle")

        subtitle_label = QLabel("Pick the protocol focus to tailor your task list. Baseline and core cognitive exercises stay included.")
        subtitle_label.setObjectName("DialogSubtitle")
        subtitle_label.setWordWrap(True)

        card = QtWidgets.QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        prompt_label = QLabel("Available pathways")
        prompt_label.setObjectName("DialogSectionTitle")
        card_layout.addWidget(prompt_label)

        button_group = QtWidgets.QButtonGroup(dlg)
        radios: Dict[str, QtWidgets.QRadioButton] = {}
        for name in ["Personal Pathway", "Connection", "Lifestyle"]:
            rb = QtWidgets.QRadioButton(name)
            button_group.addButton(rb)
            radios[name] = rb
            card_layout.addWidget(rb)

        radios["Personal Pathway"].setChecked(True)
        card_layout.addStretch()

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        ok_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        cancel_button = buttons.button(QtWidgets.QDialogButtonBox.Cancel)
        if ok_button is not None:
            ok_button.setText("Continue")
            ok_button.setDefault(True)
        if cancel_button is not None:
            cancel_button.setText("Cancel")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(card)
        layout.addWidget(buttons, alignment=QtCore.Qt.AlignRight)

        def _accept() -> None:
            checked = button_group.checkedButton()
            if checked is not None:
                self._selected_protocol = checked.text()
            try:
                self._apply_protocol_filter()
            except Exception:
                pass
            dlg.accept()

        buttons.accepted.connect(_accept)
        buttons.rejected.connect(dlg.reject)

        try:
            BL.apply_modern_dialog_theme(dlg)
        except Exception:
            pass

        self._push_modal_overlay()
        try:
            dlg.exec()
        finally:
            self._pop_modal_overlay()

    def _apply_protocol_filter(self):
        # Rebuild task combo to include cognitive tasks + selected protocol tasks
        if not hasattr(self, 'task_combo') or self.task_combo is None:
            return
        self.task_combo.blockSignals(True)
        self.task_combo.clear()
        
        # Check device type for multichannel filtering
        device_type = getattr(self, 'device_type', 'mindlink')
        is_multichannel = (device_type == 'antneuro')
        
        # Add cognitive tasks (present in AVAILABLE_TASKS)
        for key in self._cognitive_tasks:
            if key in getattr(BL, 'AVAILABLE_TASKS', {}):
                # Filter multichannel-only tasks for single-channel devices
                task_def = BL.AVAILABLE_TASKS[key]
                if task_def.get('multichannel_only', False) and not is_multichannel:
                    continue  # Skip multichannel-only tasks on single-channel devices
                self.task_combo.addItem(key)
        # Add protocol-specific tasks
        if self._selected_protocol and self._selected_protocol in self._protocol_groups:
            for key in self._protocol_groups[self._selected_protocol]:
                if key in getattr(BL, 'AVAILABLE_TASKS', {}):
                    # Filter multichannel-only tasks for single-channel devices
                    task_def = BL.AVAILABLE_TASKS[key]
                    if task_def.get('multichannel_only', False) and not is_multichannel:
                        continue  # Skip multichannel-only tasks on single-channel devices
                    self.task_combo.addItem(key)
        # Select first item if available
        if self.task_combo.count() > 0:
            self.task_combo.setCurrentIndex(0)
            try:
                self.update_task_preview(self.task_combo.currentText())
            except Exception:
                pass
        self.task_combo.blockSignals(False)

    def _change_protocol_dialog(self):
        """Allow user to change protocol at runtime.

        Safeguards: Disallow while a multi-phase task dialog is active to avoid mid-task mutation.
        Resets _selected_protocol and re-runs the selection dialog; afterwards applies filter.
        """
        try:
            # If a task dialog is active, block change to preserve data integrity
            if getattr(self, '_task_dialog', None):
                try:
                    self.log_message("Finish or close the current task before changing protocol.")
                except Exception:
                    pass
                return
            # Reset and show selection dialog again
            self._selected_protocol = None
            self._show_protocol_selection_dialog()
        except Exception:
            try:
                self.log_message("Protocol change failed (unexpected error).")
            except Exception:
                pass


class AudioFeedback:
    """Cross-platform auditory cues using pygame mixer."""
    def __init__(self, target_os: Optional[str] = None):
        self._audio_available = False
        try:
            import pygame.mixer
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self._audio_available = True
        except Exception as e:
            print(f"Warning: pygame not available, audio feedback disabled: {e}")
    
    def _play_beep(self, frequency=800, duration_ms=200):
        """Generate and play a single beep tone."""
        if not self._audio_available:
            return
        
        try:
            import pygame.mixer
            sample_rate = 22050
            duration_s = duration_ms / 1000.0
            num_samples = int(sample_rate * duration_s)
            
            # Generate sine wave
            samples = np.sin(2 * np.pi * frequency * np.linspace(0, duration_s, num_samples))
            samples = (samples * 32767).astype(np.int16)
            
            # Create stereo
            stereo_samples = np.column_stack((samples, samples))
            
            # Play
            sound = pygame.mixer.Sound(buffer=stereo_samples)
            sound.play()
        except Exception as e:
            print(f"Warning: Could not play beep: {e}")

    def _beep(self, pattern):
        """Play a pattern of beeps with delays."""
        if not self._audio_available:
            return
        
        def _run():
            for i, (freq, dur) in enumerate(pattern):
                try:
                    self._play_beep(int(freq), int(dur))
                    # Wait for beep to finish before next one
                    if i < len(pattern) - 1:
                        time.sleep(dur / 1000.0 + 0.1)  # Small gap between beeps
                except Exception as e:
                    print(f"Warning: Beep failed: {e}")
                    time.sleep(dur / 1000.0)
        
        t = threading.Thread(target=_run, daemon=True)
        t.start()

    # Public cues
    def play_start_calibration(self):
        # Single confirmation beep for calibration start
        self._beep([(900, 220)])

    def play_end_calibration(self):
        # Two short beeps to signal calibration end
        self._beep([(900, 180), (900, 180)])

    def play_phase_transition(self):
        # Single short confirmation beep
        self._beep([(950, 120)])

    def play_start_task(self):
        # Single confirmation beep for task start
        self._beep([(900, 220)])

    def play_end_task(self):
        # Two short beeps to signal task completion
        self._beep([(900, 180), (900, 180)])


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')

    os_dialog = BL.OSSelectionDialog()
    if os_dialog.exec() == QtWidgets.QDialog.Accepted:
        selected_os = os_dialog.get_selected_os()
        os.environ['BL_SELECTED_OS'] = selected_os or "unknown"
        chosen_qt_platform = _qt_platform_key(selected_os)
        host_qt_platform = _qt_platform_key(platform.system())
        if chosen_qt_platform and chosen_qt_platform == host_qt_platform:
            os.environ['QT_QPA_PLATFORM'] = chosen_qt_platform
        window = EnhancedBrainLinkAnalyzerWindow(selected_os)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)
