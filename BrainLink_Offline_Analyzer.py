#!/usr/bin/env python3
"""
MindLink Offline EEG Analysis Tool
====================================

Standalone application for offline analysis of 64-channel EEG data.

Usage:
    python MindLink_Offline_Analyzer.py <csv_file> [options]
    
    Options:
        --markers <json_file>    Path to phase markers JSON file
        --fast                   Use fast mode (parametric tests, ~30s)
        --full                   Use full mode (permutation tests, ~10-20min)
        --output <file>          Output report file (default: auto-generated)
        --format <fmt>           Output format: txt, pdf, html (default: txt)
        --permutations <n>       Number of permutations for full mode (default: 200)
        --help                   Show this help message

Examples:
    # Fast mode (default)
    python MindLink_Offline_Analyzer.py session_20260206_user.csv
    
    # Full mode with custom permutations
    python MindLink_Offline_Analyzer.py session_20260206_user.csv --full --permutations 500
    
    # With markers file
    python MindLink_Offline_Analyzer.py session.csv --markers markers.json --fast

Author: MindLink Companion Team
Version: 1.0.0
Date: February 2026
"""

import sys
import os
import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
import traceback

import numpy as np
import pandas as pd

# CRITICAL: Import antNeuro module components BEFORE any BrainLink imports
# This prevents circular dependency issues with the GUI modules
try:
    # Pre-import base engine dependencies to establish import order
    from antNeuro.offline_multichannel_analysis import OfflineMultichannelEngine
    OFFLINE_ENGINE_AVAILABLE = True
except ImportError as e:
    print(f"ERROR: Could not import offline engine: {e}")
    print("Make sure you're running this from the BrainLinkCompanion directory")
    OFFLINE_ENGINE_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class StandaloneAnalyzerConfig:
    """
    Lightweight configuration for offline analysis.
    Mirrors EnhancedAnalyzerConfig without GUI dependencies.
    """
    alpha: float = 0.05
    mode: str = "aggregate_only"
    dependence_correction: str = "independence_approximation"
    use_permutation_for_sumP: bool = True
    n_perm: int = 1000  # Updated from 100 for publication-grade p-value resolution
    n_perm_fast: int = 100  # Fast mode permutation count
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
    block_seconds: float = 4.0  # Updated from 8.0 for better power
    mt_tapers: int = 3
    fast_mode: bool = True
    nmin_sessions: int = 2
    min_blocks_per_condition: int = 8
    # Preprocessing config
    line_noise_freq: float = 50.0  # 50 Hz (EU/Asia/Africa/Australia); 60 Hz (Americas/Korea)
    apply_notch_filter: bool = True
    bandpass_low: float = 0.5      # High-pass cutoff (drift removal)
    bandpass_high: float = 45.0    # Low-pass cutoff (below mains)
    bandpass_order: int = 4
    apply_average_reference: bool = True  # Common average reference for surface EEG
    apply_hf_artifact_rejection: bool = True
    hf_artifact_low: float = 30.0
    hf_artifact_high: float = 45.0
    hf_broadband_low: float = 1.0
    hf_broadband_high: float = 45.0
    hf_global_ratio_floor: float = 0.35
    hf_frontotemporal_ratio_floor: float = 0.30
    hf_artifact_mad_z: float = 6.0
    hf_min_retained_windows: int = 3
    hf_max_reject_fraction: float = 0.80
    apply_ica_emg_cleaning: bool = False
    apply_csd_transform: bool = False
    apply_cca_emg_cleaning: bool = False
    emg_adaptive_threshold: bool = True
    emg_fixed_ratio: float = 1.5
    # Bootstrap CI
    compute_bootstrap_ci: bool = True
    bootstrap_ci_samples: int = 1000
    n_boot: int = 100  # Fast mode bootstrap (use bootstrap_ci_samples for publication)


class OfflineEEGAnalyzer:
    """
    Standalone offline EEG analyzer for 64-channel data.
    
    Processes raw CSV files and generates comprehensive analysis reports.
    """
    
    def __init__(self, csv_file: str, markers_file: Optional[str] = None, 
                 fast_mode: bool = True, n_permutations: int = 200,
                 force_analysis: bool = False):
        """
        Initialize the analyzer.
        
        Args:
            csv_file: Path to CSV file with raw EEG data
            markers_file: Optional path to JSON file with phase markers
            fast_mode: Use fast parametric mode vs full permutation mode
            n_permutations: Number of permutations for full mode
            force_analysis: Show results even when data quality flags would
                normally suppress them (e.g. known high-impedance recordings)
        """
        self.csv_file = Path(csv_file)
        self.markers_file = Path(markers_file) if markers_file else None
        self.fast_mode = fast_mode
        self.n_permutations = n_permutations
        self.force_analysis = force_analysis
        
        # Validate files exist
        if not self.csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        if self.markers_file and not self.markers_file.exists():
            raise FileNotFoundError(f"Markers file not found: {markers_file}")
        
        logger.info(f"Initialized analyzer for: {self.csv_file.name}")
        logger.info(f"Mode: {'FAST' if fast_mode else 'FULL'} "
                   f"({n_permutations} permutations)")
        
        self.results = None
        self.session_info = {}
        
        # Create config for report generation
        self.config = StandaloneAnalyzerConfig(
            fast_mode=fast_mode,
            n_perm=n_permutations
        )
        
    def load_data(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Load CSV data and markers.
        
        Returns:
            Tuple of (dataframe, markers_dict)
        """
        logger.info("Loading CSV data...")
        
        try:
            # Load CSV
            df = pd.read_csv(self.csv_file)
            logger.info(f"Loaded {len(df)} samples")
            
            # Validate CSV structure
            if 'timestamp' not in df.columns or 'sample_index' not in df.columns:
                raise ValueError("CSV must contain 'timestamp' and 'sample_index' columns")
            
            # Extract channel columns (all except timestamp and sample_index)
            channel_cols = [c for c in df.columns if c not in ['timestamp', 'sample_index']]
            logger.info(f"Detected {len(channel_cols)} EEG channels")
            
            self.session_info['n_samples'] = len(df)
            self.session_info['n_channels'] = len(channel_cols)
            self.session_info['channel_names'] = channel_cols
            self.session_info['duration'] = df['timestamp'].max()
            
            # Load markers
            markers = {}
            if self.markers_file:
                logger.info(f"Loading markers from: {self.markers_file.name}")
                with open(self.markers_file, 'r') as f:
                    markers = json.load(f)
            else:
                # Try to find markers file automatically
                markers_auto = self.csv_file.parent / f"markers_{self.csv_file.stem}.json"
                if markers_auto.exists():
                    logger.info(f"Auto-detected markers file: {markers_auto.name}")
                    with open(markers_auto, 'r') as f:
                        markers = json.load(f)
                else:
                    logger.warning("No markers file found - will analyze entire recording")
                    # Create default markers for full recording
                    markers = {
                        'session_id': self.csv_file.stem,
                        'sample_rate': self._estimate_sample_rate(df),
                        'channel_count': len(channel_cols),
                        'channel_names': channel_cols,
                        'phase_markers': [
                            {
                                'phase': 'full_recording',
                                'task': None,
                                'start': df['timestamp'].min(),
                                'end': df['timestamp'].max()
                            }
                        ]
                    }
            
            # Extract subject metadata from markers if available
            subject_metadata = markers.get('subject_metadata', {})
            
            self.session_info.update({
                'session_id': markers.get('session_id', self.csv_file.stem),
                'sample_rate': markers.get('sample_rate', 500),
                'user_email': markers.get('user_email', 'unknown'),
                'subject_metadata': subject_metadata
            })
            
            return df, markers
            
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            raise
    
    def _estimate_sample_rate(self, df: pd.DataFrame) -> int:
        """Estimate sample rate from timestamp differences."""
        if len(df) < 2:
            return 500  # Default
        dt = df['timestamp'].diff().median()
        if dt > 0:
            return int(round(1.0 / dt))
        return 500
    
    def analyze(self) -> Dict[str, Any]:
        """
        Run complete offline analysis.
        
        Returns:
            Dictionary with analysis results
        """
        logger.info("="*70)
        logger.info("Starting Offline EEG Analysis")
        logger.info("="*70)
        
        try:
            # Load data
            df, markers = self.load_data()
            
            # Check if offline engine is available
            if not OFFLINE_ENGINE_AVAILABLE:
                raise RuntimeError("Offline engine not available - import failed at module load")
            
            # Use pre-imported engine
            logger.info("Initializing analysis engine...")
            
            # Use the analyzer's config (allows CLI overrides set after __init__)
            config = self.config
            config.fast_mode = self.fast_mode
            config.n_perm = self.n_permutations
            config.use_permutation_for_sumP = not self.fast_mode
            # Set bootstrap iterations: 100 for fast mode, 1000 for publication
            config.n_boot = 100 if self.fast_mode else config.bootstrap_ci_samples
            
            # Create engine
            engine = OfflineMultichannelEngine(
                sample_rate=self.session_info['sample_rate'],
                channel_count=self.session_info['n_channels'],
                channel_names=self.session_info['channel_names'],
                user_email=self.session_info['user_email']
            )
            
            # Set config
            if hasattr(engine, 'config'):
                engine.config = config
            
            # Load raw data into engine
            logger.info("Converting data to numpy arrays...")
            timestamps = df['timestamp'].values
            channel_data = df[self.session_info['channel_names']].values

            # Auto-detect amplitude scale and normalize to µV.
            # ANT Neuro SDK may export in nV (median std ~500-5000) or µV (median std ~10-200).
            # Threshold: if median per-channel std > 200, assume nV and divide by 1000.
            import numpy as _np
            _ch_stds = _np.std(channel_data, axis=0)
            _median_std = float(_np.median(_ch_stds[_ch_stds > 0.1]))  # exclude flat channels
            if _median_std > 200.0:
                scale_factor = 1000.0
                logger.info(f"Amplitude scale auto-detected: median channel std={_median_std:.1f} → likely nV. Normalizing by ÷{scale_factor:.0f} to µV.")
                channel_data = channel_data / scale_factor
            else:
                logger.info(f"Amplitude scale: median channel std={_median_std:.1f} µV — normal range, no normalization needed.")

            # Populate engine's raw data
            engine.raw_data = [(t, sample) for t, sample in zip(timestamps, channel_data)]
            engine.recording_start_time = 0  # Already relative in CSV
            
            # Load phase markers and filter to recording phases only
            all_markers = markers.get('phase_markers', [])
            
            # If no markers provided, create a default "full recording" marker
            if not all_markers:
                logger.warning("No phase markers - will analyze entire recording as single phase")
                engine.phase_markers = []
            else:
                # Filter markers to only include phases where recording should happen
                # Check if markers have explicit 'record' flag (new format)
                has_record_flags = any('record' in m for m in all_markers)
                
                if has_record_flags:
                    # New format: use explicit 'record' flag
                    recording_markers = [m for m in all_markers if m.get('record', False)]
                    logger.info(f"Using explicit 'record' flags from markers")
                else:
                    # Old format: use fallback heuristics
                    # Try to import task definitions, but have fallback for standalone mode
                    try:
                        from BrainLinkAnalyzer_GUI import AVAILABLE_TASKS
                        has_task_defs = True
                    except (ImportError, ModuleNotFoundError):
                        # Standalone mode - define minimal phase recording rules
                        logger.warning("Using standalone phase filtering rules")
                        has_task_defs = False
                        # Phases that typically indicate recording
                        recording_phase_types = {'task', 'thinking', 'viewing', 'video', 'wait'}
                    
                    recording_markers = []
                    for marker in all_markers:
                        task_id = marker.get('task')
                        phase_type = marker.get('phase_type')
                        phase_name = marker.get('phase', '')  # Fallback for old format
                        
                        # If no phase_type but has 'phase', use that (e.g., 'full_recording')
                        if not phase_type and phase_name:
                            # Default "full_recording" or other non-specific phases should be included
                            if phase_name in ('full_recording', 'baseline', 'recording', 'eyes_closed', 'eyes_open'):
                                recording_markers.append(marker)
                            # Old-style task markers (phase='task' without phase_type)
                            elif phase_name == 'task' and task_id:
                                recording_markers.append(marker)
                            continue
                        
                        # Check if this phase should be recorded
                        should_record = False
                        
                        if has_task_defs and task_id and task_id in AVAILABLE_TASKS:
                            task_def = AVAILABLE_TASKS[task_id]
                            phase_structure = task_def.get('phase_structure', [])
                            
                            # Find matching phase in structure
                            for phase in phase_structure:
                                if phase.get('type') == phase_type and phase.get('record', False):
                                    should_record = True
                                    break
                            
                            # For continuous_recording tasks, keep all phases
                            if task_def.get('continuous_recording', False):
                                should_record = True
                        elif not has_task_defs:
                            # Fallback: use phase type heuristics
                            if phase_type in recording_phase_types:
                                should_record = True
                        else:
                            # Unknown task, keep marker if it looks like it should be recorded
                            if phase_type in ('task', 'thinking', 'viewing', 'baseline'):
                                should_record = True
                        
                        if should_record:
                            recording_markers.append(marker)
                
                engine.phase_markers = recording_markers
                logger.info(f"Loaded {len(all_markers)} markers, {len(recording_markers)} are recording phases")
                
                # Show details of filtered phases
                if recording_markers:
                    logger.info("Recording phases:")
                    for rm in recording_markers:
                        phase_desc = rm.get('phase', 'unknown')
                        if rm.get('phase_type'):
                            phase_desc += f" ({rm['phase_type']})"
                        if rm.get('task'):
                            phase_desc += f" - {rm['task']}"
                        duration = rm['end'] - rm['start']
                        logger.info(f"  • {phase_desc}: {duration:.1f}s")
            
            # Run offline analysis
            logger.info("Extracting features from raw data...")
            logger.info("This may take 30 seconds to several minutes...")
            
            def progress_callback(pct):
                if pct % 10 == 0:  # Log every 10%
                    logger.info(f"Feature extraction progress: {pct}%")
            
            analysis_results = engine.analyze_offline(progress_callback=progress_callback)
            
            if analysis_results is None:
                raise RuntimeError("Analysis failed - no results returned")
            
            # Compute baseline (if method exists)
            baseline_stats = {}
            if hasattr(engine, 'compute_baseline_statistics'):
                logger.info("Computing baseline statistics...")
                engine.compute_baseline_statistics()
                baseline_stats = getattr(engine, 'baseline_stats', {})
            
            # Run multi-task analysis (if method exists)
            multi_task_results = {}
            if hasattr(engine, 'analyze_all_tasks_data'):
                logger.info("Running statistical analysis...")
                multi_task_results = engine.analyze_all_tasks_data()
            else:
                logger.warning("Statistical analysis not available in standalone mode")
                logger.info("Feature extraction completed successfully")
                # Create basic summary from analysis results
                multi_task_results = {
                    'per_task': {},
                    'note': 'Full statistical analysis requires GUI engine components'
                }
            
            # Update session_info with baseline and task counts for report
            calibration_data = getattr(engine, 'calibration_data', {})
            ec_windows = len(calibration_data.get('eyes_closed', {}).get('features', []))
            eo_windows = len(calibration_data.get('eyes_open', {}).get('features', []))
            tasks = calibration_data.get('tasks', {})
            
            self.session_info.update({
                'baseline_ec_windows': ec_windows,
                'baseline_eo_windows': eo_windows,
                'tasks_executed': len(tasks)
            })
            
            logger.info(f"Session info updated: EC={ec_windows}, EO={eo_windows}, tasks={len(tasks)}")
            
            # Store results
            self.results = {
                'session_info': self.session_info,
                'analysis_results': analysis_results,
                'multi_task_results': multi_task_results,
                'baseline_stats': baseline_stats,
                'artifact_summary': getattr(engine, 'artifact_summary', {}),
                'config': {
                    'fast_mode': self.fast_mode,
                    'n_permutations': self.n_permutations
                }
            }
            
            logger.info("="*70)
            logger.info("Analysis Complete!")
            logger.info("="*70)
            
            return self.results
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def generate_report(self, output_file: Optional[str] = None, 
                       format: str = 'txt') -> str:
        """
        Generate analysis report.
        
        Args:
            output_file: Output file path (auto-generated if None)
            format: Output format (txt, pdf, html)
        
        Returns:
            Path to generated report file
        """
        if self.results is None:
            raise RuntimeError("No results available - run analyze() first")
        
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            mode = "fast" if self.fast_mode else "full"
            output_file = f"analysis_report_{mode}_{timestamp}.{format}"
        
        output_path = Path(output_file)
        
        logger.info(f"Generating {format.upper()} report: {output_path.name}")
        
        if format == 'txt':
            self._generate_text_report(output_path)
        elif format == 'html':
            self._generate_html_report(output_path)
        elif format == 'pdf':
            self._generate_pdf_report(output_path)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        logger.info(f"Report saved: {output_path.absolute()}")
        return str(output_path.absolute())
    
    def _generate_text_report(self, output_path: Path):
        """Generate plain text report using enhanced generator."""
        # Try to use enhanced report generator if available
        try:
            from utils.enhanced_report_generator import Enhanced64ChannelReportGenerator
            
            # Construct proper results structure matching what GUI passes
            multi_task_results = self.results.get('multi_task_results', {})
            per_task = multi_task_results.get('per_task', {})
            
            # Get baseline/task counts from updated session_info
            baseline_ec_windows = self.results['session_info'].get('baseline_ec_windows', 0)
            baseline_eo_windows = self.results['session_info'].get('baseline_eo_windows', 0)
            tasks_executed = self.results['session_info'].get('tasks_executed', len(per_task))
            
            results_for_report = {
                'session_info': {
                    'session_id': self.results['session_info'].get('session_id', 'N/A'),
                    'user_email': self.results['session_info'].get('user_email', 'N/A'),
                    'duration': self.results['session_info'].get('duration', 0),
                    'n_samples': self.results['session_info'].get('n_samples', 0),
                    'n_channels': self.results['session_info'].get('n_channels', 64),
                    'sample_rate': self.results['session_info'].get('sample_rate', 250),
                    'baseline_ec_windows': baseline_ec_windows,
                    'baseline_eo_windows': baseline_eo_windows,
                    'tasks_executed': tasks_executed
                },
                'artifact_summary': self.results.get('artifact_summary', {}),
                'analysis_results': self.results.get('analysis_results', {}),
                'multi_task_results': multi_task_results,
                'baseline_stats': self.results.get('baseline_stats', {})
            }
            
            lines = Enhanced64ChannelReportGenerator.generate_text_report(
                results=results_for_report,
                fast_mode=self.fast_mode,
                n_permutations=self.n_permutations,
                config=self.config,
                force_analysis=self.force_analysis
            )
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            logger.info(f"Enhanced report generated successfully: {output_path}")
            return
        except Exception as e:
            logger.warning(f"Enhanced report generator failed: {e}")
            logger.warning("Falling back to basic format")
            import traceback
            logger.debug(traceback.format_exc())
        
        # Fallback to basic report
        lines = []
        
        # Header
        lines.append("="*80)
        lines.append("MindLink OFFLINE 64-CHANNEL EEG ANALYSIS REPORT")
        lines.append("="*80)
        lines.append("")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Analysis Mode: {'FAST (Parametric Tests)' if self.fast_mode else f'FULL (Permutation Tests, n={self.n_permutations})'}")
        lines.append("")
        
        # Session Info
        info = self.results['session_info']
        lines.append("SESSION INFORMATION")
        lines.append("-"*40)
        lines.append(f"Session ID: {info.get('session_id', 'N/A')}")
        lines.append(f"User: {info.get('user_email', 'N/A')}")
        lines.append(f"Recording Duration: {info.get('duration', 0):.1f} seconds")
        lines.append(f"Samples: {info.get('n_samples', 0):,}")
        lines.append(f"Channels: {info.get('n_channels', 0)}")
        lines.append(f"Sample Rate: {info.get('sample_rate', 0)} Hz")
        lines.append("")
        
        # Artifact Detection Summary
        artifact_info = self.results.get('artifact_summary', {})
        if artifact_info:
            lines.append("ARTIFACT DETECTION SUMMARY")
            lines.append("-"*40)
            lines.append(f"Bad channels detected: {len(artifact_info.get('bad_channels', []))}")
            lines.append(f"Flat channels: {len(artifact_info.get('flat_channels', []))}")
            lines.append(f"Noisy channels: {len(artifact_info.get('noisy_channels', []))}")
            lines.append(f"Artifact windows removed: {len(artifact_info.get('artifact_windows', []))}")
            
            channel_quality = artifact_info.get('channel_quality', {})
            if channel_quality:
                avg_quality = np.mean(list(channel_quality.values()))
                good_channels = sum(1 for q in channel_quality.values() if q >= 0.7)
                lines.append(f"Average channel quality: {avg_quality:.2f}")
                lines.append(f"Good channels (quality ≥ 0.7): {good_channels}/{len(channel_quality)}")
            lines.append("")
        
        # Feature Extraction Summary
        lines.append("FEATURE EXTRACTION SUMMARY")
        lines.append("-"*40)
        lines.append("Per-Channel Features: 64 channels × 17 features = 1,088 features")
        lines.append("  - Band powers (delta, theta, alpha, beta, gamma)")
        lines.append("  - Relative powers, peak frequencies")
        lines.append("  - Cross-band ratios (alpha/theta, beta/alpha)")
        lines.append("")
        lines.append("Regional Features: 5 regions × 12 features = 60 features")
        lines.append("  - Frontal, Central, Temporal, Parietal, Occipital")
        lines.append("")
        lines.append("Spatial Features: ~140 features")
        lines.append("  - Hemispheric asymmetry (27 pairs × 5 bands)")
        lines.append("  - Frontal alpha asymmetry (FAA)")
        lines.append("  - Inter-regional coherence")
        lines.append("  - Global field power (GFP)")
        lines.append("")
        lines.append("Total Features per Window: ~1,400 features")
        lines.append("")
        
        # Multi-Task Results
        multi_task = self.results.get('multi_task_results', {})
        if multi_task and multi_task.get('per_task'):
            per_task = multi_task.get('per_task', {})
            if per_task:
                lines.append("TASK ANALYSIS RESULTS")
                lines.append("="*80)
                
                for task_name, task_data in per_task.items():
                    lines.append("")
                    lines.append(f"Task: {task_name}")
                    lines.append("-"*40)
                    
                    summary = task_data.get('summary', {})
                    fisher = summary.get('fisher', {})
                    sum_p = summary.get('sum_p', {})
                    feature_sel = summary.get('feature_selection', {})
                    
                    # ==========================================================
                    # DATA QUALITY CHECK - Alert user to unreliable results
                    # ==========================================================
                    data_quality = summary.get('data_quality', {})
                    if data_quality:
                        if not data_quality.get('reliable', True):
                            lines.append("")
                            lines.append("⚠️  DATA QUALITY WARNING ⚠️")
                            lines.append("━" * 40)
                            for warning in data_quality.get('warnings', []):
                                lines.append(f"  {warning}")
                            lines.append("")
                            lines.append("  ❌ RESULTS MARKED AS UNRELIABLE")
                            lines.append("  These results should NOT be interpreted as valid EEG analysis.")
                            lines.append("━" * 40)
                            lines.append("")
                        elif data_quality.get('warnings'):
                            lines.append("")
                            lines.append("⚠️  DATA QUALITY NOTICE:")
                            for warning in data_quality.get('warnings', []):
                                lines.append(f"  {warning}")
                            lines.append("")
                    
                    lines.append(f"Fisher KM p-value: {fisher.get('km_p', 'N/A')}")
                    lines.append(f"Fisher significant: {fisher.get('significant', False)}")
                    lines.append(f"SumP p-value: {sum_p.get('perm_p', 'N/A')}")
                    lines.append(f"SumP significant: {sum_p.get('significant', False)}")
                    lines.append(f"Significant features: {feature_sel.get('sig_feature_count', 0)}")
                    
                    # Top significant features
                    analysis = task_data.get('analysis', {})
                    if analysis:
                        sig_features = [(k, v) for k, v in analysis.items() 
                                       if v.get('significant_change')]
                        
                        if sig_features:
                            lines.append("")
                            lines.append("Top 10 Significant Features:")
                            for i, (feat_name, feat_data) in enumerate(sig_features[:10], 1):
                                delta = feat_data.get('delta', 0)
                                p_val = feat_data.get('p_value', 1)
                                effect = feat_data.get('effect_size_d', 0)
                                lines.append(f"  {i}. {feat_name}")
                                lines.append(f"     Δ={delta:.3f}, p={p_val:.4f}, d={effect:.3f}")
        else:
            # No statistical analysis available
            lines.append("FEATURE EXTRACTION RESULTS")
            lines.append("="*80)
            analysis_results = self.results.get('analysis_results', {})
            if analysis_results:
                lines.append("")
                lines.append(f"Successfully extracted features for {len(analysis_results)} analysis windows")
                lines.append("")
                lines.append("Note: Statistical significance testing requires full GUI engine.")
                lines.append("      Features have been extracted and saved for later analysis.")
                
                # Show sample features from first window if available
                if analysis_results:
                    first_key = list(analysis_results.keys())[0]
                    first_window = analysis_results[first_key]
                    features = first_window.get('features', {})
                    if features:
                        lines.append("")
                        lines.append(f"Total features extracted: {len(features)}")
                        lines.append("")
                        lines.append("Sample features (first 10):")
                        for i, (feat_name, feat_value) in enumerate(list(features.items())[:10], 1):
                            lines.append(f"  {i}. {feat_name}: {feat_value:.4f}")

        
        # Footer
        lines.append("")
        lines.append("="*80)
        lines.append("END OF REPORT")
        lines.append("="*80)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    
    def _generate_html_report(self, output_path: Path):
        """Generate HTML report."""
        # First generate text report
        text_lines = []
        with open(output_path.with_suffix('.txt'), 'w') as f:
            self._generate_text_report(output_path.with_suffix('.txt'))
        
        with open(output_path.with_suffix('.txt'), 'r') as f:
            text_content = f.read()
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MindLink Offline Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        pre {{ background: #f8f9fa; padding: 15px; border-left: 4px solid #3498db; overflow-x: auto; }}
        .info {{ background: #e3f2fd; padding: 15px; border-radius: 4px; margin: 20px 0; }}
        .success {{ color: #27ae60; font-weight: bold; }}
        .warning {{ color: #e67e22; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>MindLink Offline 64-Channel EEG Analysis Report</h1>
        <div class="info">
            <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
            <strong>Mode:</strong> {'FAST MODE' if self.fast_mode else 'FULL MODE'}<br>
            <strong>Session:</strong> {self.results['session_info'].get('session_id', 'N/A')}
        </div>
        <pre>{text_content}</pre>
    </div>
</body>
</html>"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Clean up temp text file
        output_path.with_suffix('.txt').unlink()
    
    def _generate_pdf_report(self, output_path: Path):
        """Generate PDF report (requires reportlab)."""
        try:
            from reportlab.lib.pagesizes import letter  # type: ignore
            from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted  # type: ignore
            from reportlab.lib.units import inch  # type: ignore
        except ImportError:
            logger.error("reportlab not installed. Generating text report instead.")
            self._generate_text_report(output_path.with_suffix('.txt'))
            logger.info(f"Text report saved as: {output_path.with_suffix('.txt')}")
            return
        
        # Create PDF
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        
        # Generate content similar to text report
        # (This would need full implementation with reportlab)
        logger.warning("PDF generation not fully implemented. Generating text report instead.")
        self._generate_text_report(output_path.with_suffix('.txt'))


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='BrainLink Offline / MindLink Offline 64-Channel EEG Analysis Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fast mode (default)
  python MindLink_Offline_Analyzer.py session_data.csv
  
  # Full mode with 500 permutations
  python MindLink_Offline_Analyzer.py session_data.csv --full --permutations 500
  
  # With markers file and HTML output
  python MindLink_Offline_Analyzer.py session.csv --markers markers.json --format html
        """
    )
    
    parser.add_argument('csv_file', help='Path to CSV file with raw EEG data')
    parser.add_argument('--markers', help='Path to phase markers JSON file')
    parser.add_argument('--fast', action='store_true', default=True,
                       help='Use fast mode (parametric tests, ~30s) [DEFAULT]')
    parser.add_argument('--full', action='store_true',
                       help='Use full mode (permutation tests, ~10-20min)')
    parser.add_argument('--output', help='Output report file path')
    parser.add_argument('--format', choices=['txt', 'html', 'pdf'], default='txt',
                       help='Output format (default: txt)')
    parser.add_argument('--permutations', type=int, default=200,
                       help='Number of permutations for full mode (default: 200)')
    parser.add_argument('--force', action='store_true', default=False,
                       help='Show analysis results even when data quality checks fail '
                            '(use for known high-impedance or partial-contact recordings)')
    parser.add_argument('--line-freq', type=float, default=50.0, choices=[50.0, 60.0],
                       help='Power line frequency in Hz: 50 (EU/Asia/Africa/Australia, default) '
                            'or 60 (Americas/Korea)')
    parser.add_argument('--no-car', action='store_true', default=False,
                       help='Disable common average reference (CAR is on by default)')
    parser.add_argument('--no-hf-reject', action='store_true', default=False,
                       help='Disable high-frequency EMG/artifact epoch rejection')
    parser.add_argument('--ica-emg', action='store_true', default=False,
                       help='Request ICA-based EMG cleaning when optional dependencies are available')
    parser.add_argument('--csd', action='store_true', default=False,
                       help='Request surface Laplacian/CSD transform when optional dependencies are available')
    parser.add_argument('--cca-emg', action='store_true', default=False,
                       help='Request CCA-based EMG cleaning when optional dependencies are available')
    parser.add_argument('--version', action='version', version='MindLink Offline Analyzer 1.0.0')
    
    args = parser.parse_args()
    
    # Determine mode
    fast_mode = not args.full  # Default to fast unless --full specified
    
    try:
        # Create analyzer
        analyzer = OfflineEEGAnalyzer(
            csv_file=args.csv_file,
            markers_file=args.markers,
            fast_mode=fast_mode,
            n_permutations=args.permutations,
            force_analysis=args.force
        )
        # Apply preprocessing CLI overrides
        analyzer.config.line_noise_freq = args.line_freq
        analyzer.config.apply_average_reference = not args.no_car
        analyzer.config.apply_hf_artifact_rejection = not args.no_hf_reject
        analyzer.config.apply_ica_emg_cleaning = args.ica_emg
        analyzer.config.apply_csd_transform = args.csd
        analyzer.config.apply_cca_emg_cleaning = args.cca_emg
        
        # Run analysis
        results = analyzer.analyze()
        
        # Generate report
        report_file = analyzer.generate_report(
            output_file=args.output,
            format=args.format
        )
        
        logger.info("="*70)
        logger.info("SUCCESS!")
        logger.info(f"Report available at: {report_file}")
        logger.info("="*70)
        
        return 0
        
    except KeyboardInterrupt:
        logger.warning("\nAnalysis interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\nFATAL ERROR: {e}")
        logger.error(traceback.format_exc())
        return 1


if __name__ == '__main__':
    sys.exit(main())
