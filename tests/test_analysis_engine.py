#!/usr/bin/env python3
"""
Test script for BrainLink analysis engine.

Runs the same analysis as both the offline CLI analyzer and the GUI engine
on the same input data, then compares results to ensure consistency.

Usage:
    python tests/test_analysis_engine.py <csv_file> <markers_file> [--fast] [--verbose]
    
Examples:
    # Test with cap-not-worn data (should show CRITICAL):
    python tests/test_analysis_engine.py "C:/Users/conta/BrainLink_Recordings/session_20260213_104724_SUB2610_00_johndoe_mindspeller_com.csv" \
        "C:/Users/conta/BrainLink_Recordings/markers_20260213_104724_SUB2610_00_johndoe_mindspeller_com.json" --fast
    
    # Test with good cap data (should NOT show CRITICAL):
    python tests/test_analysis_engine.py "C:/Users/conta/BrainLink_Recordings/prem_first_recording_test_data.csv" \
        "C:/Users/conta/BrainLink_Recordings/markers_prem_first_recording_test.json" --fast
"""

import sys
import os
import json
import time
import argparse
import traceback
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────
# Configuration (mirrored from BrainLink_Offline_Analyzer.py)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class StandaloneAnalyzerConfig:
    """Mirrors the offline analyzer's config exactly."""
    alpha: float = 0.05
    mode: str = "aggregate_only"
    dependence_correction: str = "Kost-McDermott"
    use_permutation_for_sumP: bool = True
    n_perm: int = 1000
    n_perm_fast: int = 100
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
    block_seconds: float = 4.0
    mt_tapers: int = 3
    fast_mode: bool = True
    nmin_sessions: int = 2
    min_blocks_per_condition: int = 8
    line_noise_freq: float = 60.0
    apply_notch_filter: bool = True
    emg_adaptive_threshold: bool = True
    emg_fixed_ratio: float = 1.5
    compute_bootstrap_ci: bool = True
    bootstrap_ci_samples: int = 1000
    n_boot: int = 100


# ─────────────────────────────────────────────────────────────────────
# Data loading (shared by both paths)
# ─────────────────────────────────────────────────────────────────────

def load_data(csv_path: str, markers_path: str) -> Tuple[pd.DataFrame, Dict, Dict]:
    """Load CSV and markers, return (df, markers, session_info)."""
    csv_path = Path(csv_path)
    markers_path = Path(markers_path)
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not markers_path.exists():
        raise FileNotFoundError(f"Markers not found: {markers_path}")
    
    df = pd.read_csv(csv_path)
    with open(markers_path, 'r') as f:
        markers = json.load(f)
    
    channel_cols = [c for c in df.columns if c not in ['timestamp', 'sample_index']]
    
    session_info = {
        'n_samples': len(df),
        'n_channels': len(channel_cols),
        'channel_names': channel_cols,
        'duration': df['timestamp'].max(),
        'session_id': markers.get('session_id', csv_path.stem),
        'sample_rate': markers.get('sample_rate', 500),
        'user_email': markers.get('user_email', 'unknown'),
    }
    
    return df, markers, session_info


def filter_recording_markers(all_markers):
    """Filter phase markers to recording-only phases."""
    has_record_flags = any('record' in m for m in all_markers)
    
    if has_record_flags:
        return [m for m in all_markers if m.get('record', False)]
    
    # Fallback heuristics
    recording_phase_types = {'task', 'thinking', 'viewing', 'video', 'wait', 'eyes_closed', 'eyes_open', 'baseline'}
    recording_markers = []
    for marker in all_markers:
        phase_type = marker.get('phase_type')
        phase_name = marker.get('phase', '')
        if not phase_type and phase_name:
            if phase_name in recording_phase_types or phase_name in ('full_recording', 'recording'):
                recording_markers.append(marker)
            elif phase_name == 'task' and marker.get('task'):
                recording_markers.append(marker)
            continue
        if phase_type in recording_phase_types:
            recording_markers.append(marker)
    return recording_markers


def inject_data_into_engine(engine, df, session_info, recording_markers):
    """Populate engine with CSV data and markers (shared logic)."""
    timestamps = df['timestamp'].values
    channel_data = df[session_info['channel_names']].values
    
    engine.raw_data = [(t, sample) for t, sample in zip(timestamps, channel_data)]
    engine.recording_start_time = 0
    engine.phase_markers = recording_markers


# ─────────────────────────────────────────────────────────────────────
# Offline Analyzer path (CLI)
# ─────────────────────────────────────────────────────────────────────

def run_offline_analyzer_path(df, markers, session_info, fast_mode=True, n_perm=200):
    """
    Run analysis exactly as BrainLink_Offline_Analyzer.py does.
    Returns (results_data, report_lines, timing).
    """
    from antNeuro.offline_multichannel_analysis import OfflineMultichannelEngine
    
    print(f"\n{'='*70}")
    print(f"[OFFLINE PATH] Starting analysis (n_perm={n_perm}, n_boot={'100' if fast_mode else '1000'})")
    print(f"{'='*70}\n")
    
    t0 = time.time()
    
    # Create config exactly as offline analyzer does
    config = StandaloneAnalyzerConfig()
    config.fast_mode = fast_mode
    config.n_perm = n_perm
    config.use_permutation_for_sumP = not fast_mode
    config.n_boot = 100 if fast_mode else config.bootstrap_ci_samples
    
    # Create engine exactly as offline analyzer does
    engine = OfflineMultichannelEngine(
        sample_rate=session_info['sample_rate'],
        channel_count=session_info['n_channels'],
        channel_names=session_info['channel_names'],
        user_email=session_info['user_email']
    )
    
    # Replace config (offline analyzer replaces the whole config object)
    engine.config = config
    
    # Load data
    all_markers = markers.get('phase_markers', [])
    recording_markers = filter_recording_markers(all_markers)
    inject_data_into_engine(engine, df, session_info, recording_markers)
    
    print(f"[OFFLINE PATH] {len(all_markers)} markers, {len(recording_markers)} recording phases")
    
    # Step 1: Feature extraction
    analysis_results = engine.analyze_offline()
    
    # Step 2: Baseline statistics (offline analyzer does this explicitly)
    if hasattr(engine, 'compute_baseline_statistics'):
        engine.compute_baseline_statistics()
    baseline_stats = getattr(engine, 'baseline_stats', {})
    
    # Step 3: Multi-task analysis
    multi_task_results = engine.analyze_all_tasks_data()
    
    t_elapsed = time.time() - t0
    
    # Collect calibration info
    calibration_data = getattr(engine, 'calibration_data', {})
    ec_windows = len(calibration_data.get('eyes_closed', {}).get('features', []))
    eo_windows = len(calibration_data.get('eyes_open', {}).get('features', []))
    tasks = calibration_data.get('tasks', {})
    artifact_summary = getattr(engine, 'artifact_summary', {})
    
    # Build results_data just as offline analyzer does
    results_data = {
        'session_info': {
            'session_id': session_info.get('session_id', 'N/A'),
            'user_email': session_info.get('user_email', 'N/A'),
            'duration': session_info.get('duration', 0),
            'n_samples': session_info.get('n_samples', 0),
            'n_channels': session_info.get('n_channels', 64),
            'sample_rate': session_info.get('sample_rate', 500),
            'baseline_ec_windows': ec_windows,
            'baseline_eo_windows': eo_windows,
            'tasks_executed': len(tasks),
        },
        'artifact_summary': artifact_summary,
        'analysis_results': analysis_results,
        'multi_task_results': multi_task_results,
        'baseline_stats': baseline_stats,
    }
    
    # Generate report
    from utils.enhanced_report_generator import Enhanced64ChannelReportGenerator
    report_lines = Enhanced64ChannelReportGenerator.generate_text_report(
        results=results_data,
        fast_mode=fast_mode,
        n_permutations=n_perm,
        config=config
    )
    
    return results_data, report_lines, t_elapsed


# ─────────────────────────────────────────────────────────────────────
# GUI Engine path (simulates what BrainLinkAnalyzer_GUI does)
# ─────────────────────────────────────────────────────────────────────

def run_gui_engine_path(df, markers, session_info, fast_mode=True):
    """
    Run analysis exactly as the GUI does (via create_offline_engine + config overrides).
    Returns (results_data, report_lines, timing).
    """
    from antNeuro.offline_multichannel_analysis import create_offline_engine
    
    print(f"\n{'='*70}")
    print(f"[GUI PATH] Starting analysis (GUI config overrides)")
    print(f"{'='*70}\n")
    
    t0 = time.time()
    
    # Create engine exactly as the GUI does (create_offline_engine factory)
    engine = create_offline_engine(
        sample_rate=500,  # GUI hardcodes these
        channel_count=64,
        user_email=session_info.get('user_email', 'unknown')
    )
    
    # Override config exactly as GUI does
    if hasattr(engine, 'config'):
        engine.config.fast_mode = True
        engine.config.n_perm = 500
        engine.config.n_boot = 500
        engine.config.use_permutation_for_sumP = False
    
    # Load data
    all_markers = markers.get('phase_markers', [])
    recording_markers = filter_recording_markers(all_markers)
    inject_data_into_engine(engine, df, session_info, recording_markers)
    
    print(f"[GUI PATH] {len(all_markers)} markers, {len(recording_markers)} recording phases")
    
    # Step 1: Feature extraction (same as GUI: just analyze_offline)
    engine.analyze_offline()
    
    # Step 2: GUI does NOT call compute_baseline_statistics() explicitly
    # (it relies on analyze_all_tasks_data to do it internally)
    
    # Step 3: Multi-task analysis 
    results = engine.analyze_all_tasks_data()
    engine.multi_task_results = results
    
    t_elapsed = time.time() - t0
    
    # Build results_data exactly as the GUI does in _display_results()
    multi_task_results = engine.multi_task_results or {}
    per_task = multi_task_results.get('per_task', {})
    
    calibration_data = getattr(engine, 'calibration_data', {}) or {}
    baseline_ec_windows = len(calibration_data.get('eyes_closed', {}).get('features', []))
    baseline_eo_windows = len(calibration_data.get('eyes_open', {}).get('features', []))
    
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
            'subject_metadata': {}
        },
        'artifact_summary': getattr(engine, 'artifact_summary', {}),
        'analysis_results': getattr(engine, 'analysis_results', {}),
        'multi_task_results': multi_task_results,
        'baseline_stats': getattr(engine, 'baseline_stats', {})
    }
    
    # Generate report (same call as GUI's _display_results)
    from utils.enhanced_report_generator import Enhanced64ChannelReportGenerator
    config = getattr(engine, 'config', None)
    gui_fast = getattr(config, 'fast_mode', True) if config else True
    gui_n_perm = getattr(config, 'n_perm', 100) if config else 100
    
    report_lines = Enhanced64ChannelReportGenerator.generate_text_report(
        results=results_data,
        fast_mode=gui_fast,
        n_permutations=gui_n_perm,
        config=config
    )
    
    return results_data, report_lines, t_elapsed


# ─────────────────────────────────────────────────────────────────────
# Comparison logic
# ─────────────────────────────────────────────────────────────────────

def extract_summary(results_data: Dict) -> Dict:
    """Extract key comparable metrics from results."""
    summary = {}
    
    multi = results_data.get('multi_task_results', {})
    per_task = multi.get('per_task', {})
    
    summary['task_names'] = sorted(per_task.keys())
    summary['n_tasks'] = len(per_task)
    
    # Per-task metrics
    for task_name, task_data in per_task.items():
        ts = task_data.get('summary', {})
        prefix = f"task:{task_name}"
        summary[f"{prefix}:sig_features"] = ts.get('significant_features', -1)
        summary[f"{prefix}:total_features"] = ts.get('total_features', -1)
        summary[f"{prefix}:effect_size_mean"] = ts.get('effect_size_mean', -1)
        summary[f"{prefix}:effect_size_median"] = ts.get('effect_size_median', -1)
        summary[f"{prefix}:composite_score"] = ts.get('composite', {}).get('score', -1)
        summary[f"{prefix}:fisher_p"] = ts.get('fisher', {}).get('km_p', -1)
        summary[f"{prefix}:sum_p"] = ts.get('sum_p', {}).get('value', -1)
        summary[f"{prefix}:baseline_windows"] = ts.get('baseline_windows', -1)
        summary[f"{prefix}:task_windows"] = ts.get('task_windows', -1)
        
        # Data quality
        dq = ts.get('data_quality', {})
        summary[f"{prefix}:dq_reliable"] = dq.get('reliable', None)
    
    # Artifact summary
    artifact = results_data.get('artifact_summary', {})
    summary['bad_channels'] = sorted(artifact.get('bad_channels', []))
    summary['n_bad_channels'] = len(artifact.get('bad_channels', []))
    
    # Session info
    si = results_data.get('session_info', {})
    summary['ec_windows'] = si.get('baseline_ec_windows', -1)
    summary['eo_windows'] = si.get('baseline_eo_windows', -1)
    
    return summary


def check_report_for_critical(report_lines):
    """Check if report contains a CRITICAL data quality alert."""
    report_text = '\n'.join(report_lines)
    has_critical_banner = 'CRITICAL DATA QUALITY ALERT' in report_text
    has_suppressed = '[SUPPRESSED' in report_text
    has_cap_not_worn = 'CAP LIKELY NOT WORN' in report_text
    
    critical_lines = [l.strip() for l in report_lines if 'CRITICAL' in l and l.strip()]
    
    return {
        'has_critical_banner': has_critical_banner,
        'has_suppressed': has_suppressed, 
        'has_cap_not_worn': has_cap_not_worn,
        'critical_lines': critical_lines,
    }


def compare_results(offline_summary, gui_summary, offline_critical, gui_critical, verbose=False):
    """Compare the two engine outputs and report differences."""
    
    print(f"\n{'='*70}")
    print(f"COMPARISON RESULTS")
    print(f"{'='*70}\n")
    
    all_pass = True
    checks = []
    
    # 1. Same tasks detected
    ok = offline_summary['task_names'] == gui_summary['task_names']
    checks.append(('Task names match', ok,
                    f"Offline={offline_summary['task_names']}, GUI={gui_summary['task_names']}"))
    if not ok:
        all_pass = False
    
    # 2. Same baseline windows
    ok = offline_summary['ec_windows'] == gui_summary['ec_windows']
    checks.append(('EC baseline windows match', ok,
                    f"Offline={offline_summary['ec_windows']}, GUI={gui_summary['ec_windows']}"))
    if not ok:
        all_pass = False
    
    ok = offline_summary['eo_windows'] == gui_summary['eo_windows']
    checks.append(('EO baseline windows match', ok,
                    f"Offline={offline_summary['eo_windows']}, GUI={gui_summary['eo_windows']}"))
    if not ok:
        all_pass = False
    
    # 3. Same bad channels
    ok = offline_summary['bad_channels'] == gui_summary['bad_channels']
    checks.append(('Bad channels match', ok,
                    f"Offline={offline_summary['bad_channels']}, GUI={gui_summary['bad_channels']}"))
    if not ok:
        all_pass = False
    
    # 4. Per-task: same window counts, similar feature counts
    for task_name in offline_summary['task_names']:
        prefix = f"task:{task_name}"
        
        # Task windows must match exactly (same data)
        off_tw = offline_summary.get(f"{prefix}:task_windows", -1)
        gui_tw = gui_summary.get(f"{prefix}:task_windows", -1)
        ok = off_tw == gui_tw
        checks.append((f'{task_name}: task windows match', ok,
                        f"Offline={off_tw}, GUI={gui_tw}"))
        if not ok:
            all_pass = False
        
        # Total features must match (same extraction)
        off_tf = offline_summary.get(f"{prefix}:total_features", -1)
        gui_tf = gui_summary.get(f"{prefix}:total_features", -1)
        ok = off_tf == gui_tf
        checks.append((f'{task_name}: total features match', ok,
                        f"Offline={off_tf}, GUI={gui_tf}"))
        if not ok:
            all_pass = False
        
        # Significant features: may differ slightly due to n_perm/n_boot differences
        # Allow ±10% tolerance
        off_sf = offline_summary.get(f"{prefix}:sig_features", 0)
        gui_sf = gui_summary.get(f"{prefix}:sig_features", 0)
        tolerance = max(off_sf, gui_sf, 1) * 0.10
        diff = abs(off_sf - gui_sf)
        ok = diff <= tolerance
        checks.append((f'{task_name}: sig features similar (±10%)', ok,
                        f"Offline={off_sf}, GUI={gui_sf}, diff={diff}"))
        if not ok:
            all_pass = False
        
        # Effect sizes: should be identical (same computation, no randomness)
        off_med = offline_summary.get(f"{prefix}:effect_size_median", 0)
        gui_med = gui_summary.get(f"{prefix}:effect_size_median", 0)
        if off_med > 0 and gui_med > 0:
            pct_diff = abs(off_med - gui_med) / max(off_med, 1e-10) * 100
            ok = pct_diff < 5.0  # <5% difference
            checks.append((f'{task_name}: median|d| match (<5%)', ok,
                            f"Offline={off_med:.4f}, GUI={gui_med:.4f}, diff={pct_diff:.1f}%"))
            if not ok:
                all_pass = False
        
        # Data quality reliable flag
        off_dq = offline_summary.get(f"{prefix}:dq_reliable")
        gui_dq = gui_summary.get(f"{prefix}:dq_reliable")
        if off_dq is not None and gui_dq is not None:
            ok = off_dq == gui_dq
            checks.append((f'{task_name}: data quality flag match', ok,
                            f"Offline={off_dq}, GUI={gui_dq}"))
            if not ok:
                all_pass = False
    
    # 5. CRITICAL detection must agree
    ok = offline_critical['has_critical_banner'] == gui_critical['has_critical_banner']
    checks.append(('CRITICAL banner agrees', ok,
                    f"Offline={offline_critical['has_critical_banner']}, GUI={gui_critical['has_critical_banner']}"))
    if not ok:
        all_pass = False
    
    ok = offline_critical['has_suppressed'] == gui_critical['has_suppressed']
    checks.append(('Result suppression agrees', ok,
                    f"Offline={offline_critical['has_suppressed']}, GUI={gui_critical['has_suppressed']}"))
    if not ok:
        all_pass = False
    
    # Print results
    for check_name, passed, detail in checks:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status}  {check_name}")
        if verbose or not passed:
            print(f"           {detail}")
    
    print()
    if all_pass:
        print(f"  [PASS] ALL {len(checks)} CHECKS PASSED — Engines produce consistent results")
    else:
        n_fail = sum(1 for _, ok, _ in checks if not ok)
        print(f"  [FAIL] {n_fail}/{len(checks)} CHECKS FAILED — See details above")
    
    return all_pass


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Test BrainLink analysis engine consistency (offline CLI vs GUI path)")
    parser.add_argument('csv_file', help='Path to CSV file with raw EEG data')
    parser.add_argument('markers_file', help='Path to JSON markers file')
    parser.add_argument('--fast', action='store_true', default=True, 
                        help='Use fast mode (default)')
    parser.add_argument('--full', action='store_true',
                        help='Use full permutation mode')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show all check details, not just failures')
    parser.add_argument('--save-reports', action='store_true',
                        help='Save generated reports to disk for manual inspection')
    args = parser.parse_args()
    
    fast_mode = not args.full
    n_perm = 200 if fast_mode else 1000
    
    print(f"\n{'='*70}")
    print(f"BrainLink Analysis Engine Test")
    print(f"{'='*70}")
    print(f"CSV:     {args.csv_file}")
    print(f"Markers: {args.markers_file}")
    print(f"Mode:    {'FAST' if fast_mode else 'FULL'}")
    print(f"{'='*70}\n")
    
    # Load data once (shared by both paths)
    print("[LOADING] Reading CSV and markers...")
    t0 = time.time()
    df, markers, session_info = load_data(args.csv_file, args.markers_file)
    t_load = time.time() - t0
    print(f"[LOADING] {session_info['n_samples']} samples, {session_info['n_channels']} channels ({t_load:.1f}s)")
    
    # ──── Run offline analyzer path ────
    try:
        offline_results, offline_report, offline_time = run_offline_analyzer_path(
            df, markers, session_info, fast_mode=fast_mode, n_perm=n_perm
        )
        print(f"\n[OFFLINE PATH] Completed in {offline_time:.1f}s")
    except Exception as e:
        print(f"\n❌ OFFLINE PATH FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # ──── Run GUI engine path ────
    try:
        gui_results, gui_report, gui_time = run_gui_engine_path(
            df, markers, session_info, fast_mode=fast_mode
        )
        print(f"\n[GUI PATH] Completed in {gui_time:.1f}s")
    except Exception as e:
        print(f"\n❌ GUI PATH FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # ──── Extract & Compare ────
    offline_summary = extract_summary(offline_results)
    gui_summary = extract_summary(gui_results)
    offline_critical = check_report_for_critical(offline_report)
    gui_critical = check_report_for_critical(gui_report)
    
    print(f"\n{'─'*70}")
    print(f"TIMING: Offline={offline_time:.1f}s, GUI={gui_time:.1f}s")
    print(f"{'─'*70}")
    
    all_pass = compare_results(
        offline_summary, gui_summary,
        offline_critical, gui_critical,
        verbose=args.verbose
    )
    
    # Save reports if requested
    if args.save_reports:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        offline_path = PROJECT_ROOT / f"test_report_offline_{ts}.txt"
        gui_path = PROJECT_ROOT / f"test_report_gui_{ts}.txt"
        
        with open(offline_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(offline_report))
        with open(gui_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(gui_report))
        
        print(f"\n[SAVED] Offline report: {offline_path}")
        print(f"[SAVED] GUI report:     {gui_path}")
    
    # Exit code
    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
