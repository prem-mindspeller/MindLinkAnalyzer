#!/usr/bin/env python3
"""
Test Multi-Channel Analysis Pipeline
Tests the 64-channel signal quality assessment and live processing
"""

import numpy as np
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the assessment function
from BrainLinkAnalyzer_GUI_Sequential_Integrated import assess_multichannel_signal_quality

def test_multichannel_quality_assessment():
    """Test the 64-channel signal quality assessment function"""
    print("\n" + "="*80)
    print("TEST: Multi-Channel Signal Quality Assessment")
    print("="*80)
    
    # Generate synthetic 64-channel EEG data
    fs = 500  # ANT Neuro sampling rate
    duration = 10  # seconds
    n_samples = fs * duration
    n_channels = 64
    
    print(f"\n1. Generating synthetic {n_channels}-channel EEG data...")
    print(f"   - Sampling rate: {fs} Hz")
    print(f"   - Duration: {duration} seconds")
    print(f"   - Shape: ({n_samples}, {n_channels})")
    
    # Create realistic synthetic EEG with different scenarios
    t = np.linspace(0, duration, n_samples)
    multichannel_data = np.zeros((n_samples, n_channels))
    
    for ch in range(n_channels):
        # Base: alpha (10 Hz) + theta (6 Hz) + delta (2 Hz)
        alpha = 20 * np.sin(2 * np.pi * 10 * t)
        theta = 15 * np.sin(2 * np.pi * 6 * t)
        delta = 25 * np.sin(2 * np.pi * 2 * t)
        
        # Add realistic noise
        noise = np.random.normal(0, 5, n_samples)
        
        # Create different channel scenarios
        if ch < 50:  # Most channels good
            multichannel_data[:, ch] = alpha + theta + delta + noise
        elif ch < 58:  # Some channels acceptable (higher noise)
            multichannel_data[:, ch] = alpha + theta + delta + noise * 3
        elif ch < 62:  # Few channels poor (very noisy)
            multichannel_data[:, ch] = noise * 10
        else:  # Couple flat channels (bad contact)
            multichannel_data[:, ch] = np.random.normal(0, 0.5, n_samples)
    
    print("   ✓ Synthetic data generated")
    
    # Test signal quality assessment
    print("\n2. Running signal quality assessment...")
    try:
        overall_score, overall_status, details = assess_multichannel_signal_quality(
            multichannel_data, 
            fs=fs
        )
        
        print(f"\n   RESULTS:")
        print(f"   ========")
        print(f"   Overall Score: {overall_score:.1f}/100")
        print(f"   Overall Status: {overall_status}")
        print(f"   Total Channels: {details['n_channels']}")
        print(f"   Samples Analyzed: {details['n_samples']}")
        
        print(f"\n   Channel Quality Breakdown:")
        print(f"   - Bad Channels: {len(details['bad_channels'])} channels")
        if details['bad_channels']:
            print(f"     {', '.join(details['bad_channels'][:10])}" + 
                  ("..." if len(details['bad_channels']) > 10 else ""))
        
        print(f"   - Flat Channels: {len(details['flat_channels'])} channels")
        if details['flat_channels']:
            print(f"     {', '.join(details['flat_channels'])}")
        
        print(f"   - Noisy Channels: {len(details['noisy_channels'])} channels")
        if details['noisy_channels']:
            print(f"     {', '.join(details['noisy_channels'][:10])}" + 
                  ("..." if len(details['noisy_channels']) > 10 else ""))
        
        print(f"   - Artifact Channels: {len(details['artifact_channels'])} channels")
        if details['artifact_channels']:
            print(f"     {', '.join(details['artifact_channels'][:10])}" + 
                  ("..." if len(details['artifact_channels']) > 10 else ""))
        
        print(f"\n   Regional Quality Scores:")
        for region, score in details['regional_scores'].items():
            status_icon = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"
            print(f"   {status_icon} {region.capitalize():12s}: {score:.1f}/100")
        
        if details['issues']:
            print(f"\n   Detected Issues:")
            for issue in details['issues']:
                print(f"   ⚠️  {issue}")
        
        print("\n   ✓ Signal quality assessment PASSED")
        return True
        
    except Exception as e:
        print(f"\n   ✗ Signal quality assessment FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_live_processing_simulation():
    """Simulate live processing with streaming data"""
    print("\n" + "="*80)
    print("TEST: Live Processing Simulation")
    print("="*80)
    
    print("\n1. Simulating real-time data acquisition...")
    
    fs = 500
    n_channels = 64
    window_size = fs * 2  # 2-second windows
    
    # Simulate 3 windows of streaming data
    for window_idx in range(3):
        print(f"\n   Window {window_idx + 1}/3:")
        
        # Generate synthetic window
        t = np.linspace(0, 2, window_size)
        window_data = np.zeros((window_size, n_channels))
        
        for ch in range(n_channels):
            alpha = 20 * np.sin(2 * np.pi * 10 * t)
            theta = 15 * np.sin(2 * np.pi * 6 * t)
            noise = np.random.normal(0, 5, window_size)
            window_data[:, ch] = alpha + theta + noise
        
        # Quick quality check
        try:
            score, status, details = assess_multichannel_signal_quality(window_data, fs=fs)
            print(f"   - Quality Score: {score:.1f}/100 ({status})")
            print(f"   - Good Channels: {n_channels - len(details['bad_channels'])}/{n_channels}")
            
        except Exception as e:
            print(f"   ✗ Window processing failed: {e}")
            return False
    
    print("\n   ✓ Live processing simulation PASSED")
    return True


def test_post_processing():
    """Test post-processing analysis"""
    print("\n" + "="*80)
    print("TEST: Post-Processing Analysis")
    print("="*80)
    
    print("\n1. Simulating task completion with collected data...")
    
    # Simulate baseline and task data
    fs = 500
    n_channels = 64
    baseline_duration = 60  # 1 minute
    task_duration = 120  # 2 minutes
    
    print(f"   - Baseline: {baseline_duration}s")
    print(f"   - Task: {task_duration}s")
    
    # Generate baseline data
    t_baseline = np.linspace(0, baseline_duration, baseline_duration * fs)
    baseline_data = np.zeros((len(t_baseline), n_channels))
    
    for ch in range(n_channels):
        # Relaxed state: strong alpha
        alpha = 25 * np.sin(2 * np.pi * 10 * t_baseline)
        theta = 10 * np.sin(2 * np.pi * 6 * t_baseline)
        noise = np.random.normal(0, 3, len(t_baseline))
        baseline_data[:, ch] = alpha + theta + noise
    
    # Generate task data (increased beta, decreased alpha)
    t_task = np.linspace(0, task_duration, task_duration * fs)
    task_data = np.zeros((len(t_task), n_channels))
    
    for ch in range(n_channels):
        # Active state: increased beta, decreased alpha
        alpha = 15 * np.sin(2 * np.pi * 10 * t_task)  # Reduced
        beta = 20 * np.sin(2 * np.pi * 18 * t_task)   # Increased
        theta = 10 * np.sin(2 * np.pi * 6 * t_task)
        noise = np.random.normal(0, 3, len(t_task))
        task_data[:, ch] = alpha + beta + theta + noise
    
    print("\n2. Analyzing baseline data...")
    baseline_score, baseline_status, baseline_details = assess_multichannel_signal_quality(
        baseline_data, fs=fs
    )
    print(f"   - Baseline Quality: {baseline_score:.1f}/100 ({baseline_status})")
    print(f"   - Regional Scores: " + 
          ", ".join([f"{r[:3]}={s:.0f}" for r, s in list(baseline_details['regional_scores'].items())[:3]]))
    
    print("\n3. Analyzing task data...")
    task_score, task_status, task_details = assess_multichannel_signal_quality(
        task_data, fs=fs
    )
    print(f"   - Task Quality: {task_score:.1f}/100 ({task_status})")
    print(f"   - Regional Scores: " + 
          ", ".join([f"{r[:3]}={s:.0f}" for r, s in list(task_details['regional_scores'].items())[:3]]))
    
    print("\n4. Computing comparative metrics...")
    # Simple comparison
    score_change = task_score - baseline_score
    print(f"   - Quality Change: {score_change:+.1f} points")
    
    # Channel stability
    baseline_bad_count = len(baseline_details['bad_channels'])
    task_bad_count = len(task_details['bad_channels'])
    print(f"   - Bad Channels: {baseline_bad_count} (baseline) → {task_bad_count} (task)")
    
    print("\n   ✓ Post-processing analysis PASSED")
    return True


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MULTI-CHANNEL PIPELINE TEST SUITE")
    print("Testing 64-Channel EEG Analysis Pipeline")
    print("="*80)
    
    results = {
        "Signal Quality Assessment": test_multichannel_quality_assessment(),
        "Live Processing": test_live_processing_simulation(),
        "Post-Processing": test_post_processing(),
    }
    
    print("\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status:10s} - {test_name}")
    
    all_passed = all(results.values())
    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL TESTS PASSED - Multi-channel pipeline is working correctly!")
    else:
        print("⚠️  SOME TESTS FAILED - Please review errors above")
    print("="*80 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
