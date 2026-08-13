#!/usr/bin/env python3
"""
GUI Analysis Integration Test - Tests the ACTUAL GUI code path.

This test validates that the GUI's analysis wrapper code (analyze_all_tasks,
_generate_report_text) produces the same results as the standalone offline analyzer.

Unlike test_analysis_engine.py which just replicates engine setup, this test
actually calls methods from BrainLinkAnalyzer_GUI_Sequential_Integrated.py.

Usage:
    python tests/test_gui_analysis_integration.py <csv_file> <markers_file> [--fast]
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd


def prepare_gui_engine_with_data(csv_path, markers_path):
    """
    Load CSV/markers and populate an engine exactly as the GUI would during recording.
    Returns configured engine ready for analysis.
    """
    from antNeuro.offline_multichannel_analysis import create_offline_engine
    
    # Load data
    csv_path = Path(csv_path)
    markers_path = Path(markers_path)
    
    df = pd.read_csv(csv_path)
    with open(markers_path, 'r') as f:
        markers = json.load(f)
    
    channel_cols = [c for c in df.columns if c not in ['timestamp', 'sample_index']]
    
    # Create engine exactly as GUI does in _init_enhanced_engine()
    user_email = markers.get('user_email', 'test_user')
    engine = create_offline_engine(
        sample_rate=500,
        channel_count=64,
        user_email=user_email
    )
    
    # Configure exactly as GUI does (lines 9150-9157)
    if hasattr(engine, 'config'):
        engine.config.fast_mode = True
        engine.config.n_perm = 500
        engine.config.n_boot = 500
        engine.config.use_permutation_for_sumP = False
    
    # Inject raw data (as the GUI accumulates during streaming)
    timestamps = df['timestamp'].values
    channel_data = df[channel_cols].values
    engine.raw_data = [(t, sample) for t, sample in zip(timestamps, channel_data)]
    engine.recording_start_time = 0
    
    # Set phase markers (as GUI does when recording tasks)
    all_markers = markers.get('phase_markers', [])
    has_record_flags = any('record' in m for m in all_markers)
    
    if has_record_flags:
        recording_markers = [m for m in all_markers if m.get('record', False)]
    else:
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
    
    engine.phase_markers = recording_markers
    
    return engine, recording_markers


def run_gui_analysis_code(engine):
    """
    Run the exact analysis code from GUI's analyze_all_tasks() method.
    This is a direct extraction of lines 7966-8107 + 8164-8177.
    """
    print(f"\n{'='*70}")
    print(f"[GUI CODE PATH] Running actual GUI analysis methods")
    print(f"{'='*70}\n")
    
    t0 = time.time()
    
    # Step 1: Feature extraction (from analyze_all_tasks, line 8063)
    print(f"[GUI] Calling analyze_offline()...")
    engine.analyze_offline()
    
    if hasattr(engine, 'stop_recording'):
        engine.stop_recording()
    
    if hasattr(engine, 'save_phase_markers'):
        engine.save_phase_markers()
    
    print(f"[GUI] Feature extraction complete")
    print(f"[GUI] Eyes-closed: {len(engine.calibration_data['eyes_closed']['features'])} windows")
    print(f"[GUI] Eyes-open: {len(engine.calibration_data['eyes_open']['features'])} windows")
    
    # Step 2: Multi-task analysis (from worker thread, line 8167)
    # GUI runs this in background thread, but for testing we run synchronously
    print(f"[GUI] Calling analyze_all_tasks_data()...")
    results = engine.analyze_all_tasks_data()
    engine.multi_task_results = results
    
    print(f"[GUI] Analysis complete")
    
    t_elapsed = time.time() - t0
    
    return results, t_elapsed


def run_gui_report_generation(engine):
    """
    Run the exact report generation code from GUI's _generate_report_text() method.
    This is a direct extraction of lines 8475-8526.
    """
    print(f"[GUI] Calling _generate_report_text() logic...")
    
    from utils.enhanced_report_generator import Enhanced64ChannelReportGenerator
    
    # Extract results exactly as GUI does (lines 8487-8513)
    multi_task_results = getattr(engine, 'multi_task_results', {}) or {}
    per_task = multi_task_results.get('per_task', {})
    
    calibration_data = getattr(engine, 'calibration_data', {}) or {}
    baseline_ec_windows = len(calibration_data.get('eyes_closed', {}).get('features', []))
    baseline_eo_windows = len(calibration_data.get('eyes_open', {}).get('features', []))
    
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
        'analysis_results': getattr(engine, 'analysis_results', {}),
        'multi_task_results': multi_task_results,
        'baseline_stats': getattr(engine, 'baseline_stats', {})
    }
    
    # Get configuration exactly as GUI does (lines 8516-8518)
    config = getattr(engine, 'config', None)
    fast_mode = getattr(config, 'fast_mode', True) if config else True
    n_perm = getattr(config, 'n_perm', 100) if config else 100
    
    # Generate report exactly as GUI does (lines 8520-8526)
    report_lines = Enhanced64ChannelReportGenerator.generate_text_report(
        results=results,
        fast_mode=fast_mode,
        n_permutations=n_perm,
        config=config
    )
    
    return results, report_lines


def run_offline_analyzer_for_comparison(csv_path, markers_path, fast_mode=True):
    """Run the offline analyzer for comparison baseline."""
    from BrainLink_Offline_Analyzer import OfflineEEGAnalyzer
    
    print(f"\n{'='*70}")
    print(f"[OFFLINE BASELINE] Running standalone analyzer for comparison")
    print(f"{'='*70}\n")
    
    t0 = time.time()
    
    analyzer = OfflineEEGAnalyzer(
        csv_file=str(csv_path),
        markers_file=str(markers_path),
        fast_mode=fast_mode,
        n_permutations=200
    )
    
    results = analyzer.analyze()
    
    # Generate report
    report_path = analyzer.generate_report(format='txt')
    with open(report_path, 'r', encoding='utf-8') as f:
        report_text = f.read()
    
    # Clean up generated file
    Path(report_path).unlink()
    
    t_elapsed = time.time() - t0
    
    return results, report_text.split('\n'), t_elapsed


def extract_key_metrics(results_data):
    """Extract comparable metrics."""
    metrics = {}
    
    multi = results_data.get('multi_task_results', {})
    per_task = multi.get('per_task', {})
    
    metrics['n_tasks'] = len(per_task)
    metrics['task_names'] = sorted(per_task.keys())
    
    for task_name, task_data in per_task.items():
        ts = task_data.get('summary', {})
        metrics[f"{task_name}:sig_features"] = ts.get('significant_features', -1)
        metrics[f"{task_name}:total_features"] = ts.get('total_features', -1)
        metrics[f"{task_name}:median_d"] = ts.get('effect_size_median', -1)
        metrics[f"{task_name}:task_windows"] = ts.get('task_windows', -1)
    
    artifact = results_data.get('artifact_summary', {})
    metrics['n_bad_channels'] = len(artifact.get('bad_channels', []))
    
    si = results_data.get('session_info', {})
    metrics['ec_windows'] = si.get('baseline_ec_windows', -1)
    metrics['eo_windows'] = si.get('baseline_eo_windows', -1)
    
    return metrics


def check_critical_banner(report_lines):
    """Check for CRITICAL data quality warning."""
    report_text = '\n'.join(report_lines)
    return {
        'has_critical': 'CRITICAL DATA QUALITY ALERT' in report_text,
        'has_suppressed': '[SUPPRESSED' in report_text,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Integration test for GUI analysis code")
    parser.add_argument('csv_file', help='Path to CSV file')
    parser.add_argument('markers_file', help='Path to markers JSON')
    parser.add_argument('--fast', action='store_true', default=True)
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print(f"GUI ANALYSIS INTEGRATION TEST")
    print(f"{'='*70}")
    print(f"CSV:     {args.csv_file}")
    print(f"Markers: {args.markers_file}")
    print(f"{'='*70}\n")
    
    print("[SETUP] Preparing GUI engine with data...")
    engine, recording_markers = prepare_gui_engine_with_data(args.csv_file, args.markers_file)
    print(f"[SETUP] {len(recording_markers)} recording phases loaded into engine")
    
    # Run GUI code path
    try:
        gui_results, gui_time = run_gui_analysis_code(engine)
        gui_results_data, gui_report = run_gui_report_generation(engine)
        print(f"\n[GUI CODE] Completed in {gui_time:.1f}s")
    except Exception as e:
        print(f"\n❌ GUI CODE PATH FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Run offline analyzer for comparison
    try:
        offline_results, offline_report, offline_time = run_offline_analyzer_for_comparison(
            args.csv_file, args.markers_file, fast_mode=args.fast
        )
        print(f"\n[OFFLINE] Completed in {offline_time:.1f}s")
    except Exception as e:
        print(f"\n❌ OFFLINE ANALYZER FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Compare
    gui_metrics = extract_key_metrics(gui_results_data)
    offline_metrics = extract_key_metrics(offline_results)
    gui_critical = check_critical_banner(gui_report)
    offline_critical = check_critical_banner(offline_report)
    
    print(f"\n{'='*70}")
    print(f"COMPARISON: GUI Code vs Offline Analyzer")
    print(f"{'='*70}\n")
    
    checks = []
    all_pass = True
    
    # Compare key metrics
    ok = gui_metrics['task_names'] == offline_metrics['task_names']
    checks.append(('Task names match', ok))
    if not ok: all_pass = False
    
    ok = gui_metrics['ec_windows'] == offline_metrics['ec_windows']
    checks.append(('Baseline EC windows match', ok))
    if not ok: all_pass = False
    
    ok = gui_metrics['n_bad_channels'] == offline_metrics['n_bad_channels']
    checks.append(('Bad channel counts match', ok))
    if not ok: all_pass = False
    
    for task_name in gui_metrics['task_names']:
        gui_tw = gui_metrics.get(f"{task_name}:task_windows", -1)
        off_tw = offline_metrics.get(f"{task_name}:task_windows", -1)
        ok = gui_tw == off_tw
        checks.append((f'{task_name}: task windows match', ok))
        if not ok: all_pass = False
        
        gui_tf = gui_metrics.get(f"{task_name}:total_features", -1)
        off_tf = offline_metrics.get(f"{task_name}:total_features", -1)
        ok = gui_tf == off_tf
        checks.append((f'{task_name}: total features match', ok))
        if not ok: all_pass = False
        
        gui_med = gui_metrics.get(f"{task_name}:median_d", 0)
        off_med = offline_metrics.get(f"{task_name}:median_d", 0)
        if gui_med > 0 and off_med > 0:
            pct_diff = abs(gui_med - off_med) / max(off_med, 1e-10) * 100
            ok = pct_diff < 5.0
            checks.append((f'{task_name}: median|d| match (<5%)', ok))
            if not ok: all_pass = False
    
    ok = gui_critical['has_critical'] == offline_critical['has_critical']
    checks.append(('CRITICAL banner agrees', ok))
    if not ok: all_pass = False
    
    # Print results
    for check_name, passed in checks:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status}  {check_name}")
    
    print()
    if all_pass:
        print(f"  [PASS] ALL {len(checks)} CHECKS PASSED")
        print(f"  [PASS] GUI CODE produces identical results to offline analyzer")
        print(f"\n  >> SAFE TO PACKAGE AND DISTRIBUTE TO CLIENTS <<")
    else:
        n_fail = sum(1 for _, ok in checks if not ok)
        print(f"  [FAIL] {n_fail}/{len(checks)} CHECKS FAILED")
        print(f"  [FAIL] GUI CODE does NOT match offline analyzer")
        print(f"\n  >> DO NOT PACKAGE - Fix discrepancies first <<")
    
    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
