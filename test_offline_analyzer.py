#!/usr/bin/env python3
"""
Test script for BrainLink Offline Analyzer

This script validates that all dependencies are installed and the analyzer
can run basic operations.
"""

import sys
import os
from pathlib import Path

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    required = [
        ('numpy', 'NumPy'),
        ('pandas', 'Pandas'),
        ('scipy', 'SciPy'),
    ]
    
    optional = [
        ('reportlab', 'ReportLab (for PDF generation)'),
    ]
    
    missing_required = []
    missing_optional = []
    
    for module_name, display_name in required:
        try:
            __import__(module_name)
            print(f"  ✓ {display_name}")
        except ImportError:
            print(f"  ✗ {display_name} - MISSING")
            missing_required.append(module_name)
    
    for module_name, display_name in optional:
        try:
            __import__(module_name)
            print(f"  ✓ {display_name}")
        except ImportError:
            print(f"  ⚠ {display_name} - MISSING (optional)")
            missing_optional.append(module_name)
    
    if missing_required:
        print(f"\n❌ Missing required packages: {', '.join(missing_required)}")
        print(f"Install with: pip install {' '.join(missing_required)}")
        return False
    
    if missing_optional:
        print(f"\n⚠ Missing optional packages: {', '.join(missing_optional)}")
        print(f"Install with: pip install {' '.join(missing_optional)}")
    
    print("\n✓ All required imports successful\n")
    return True


def test_analyzer_class():
    """Test that OfflineEEGAnalyzer can be imported."""
    print("Testing analyzer class import...")
    
    try:
        from BrainLink_Offline_Analyzer import OfflineEEGAnalyzer
        print("  ✓ OfflineEEGAnalyzer class imported\n")
        return True
    except ImportError as e:
        print(f"  ✗ Failed to import OfflineEEGAnalyzer: {e}\n")
        return False


def test_dependencies():
    """Test that required files are present."""
    print("Testing file dependencies...")
    
    required_files = [
        'BrainLink_Offline_Analyzer.py',
        'BrainLinkAnalyzer_GUI_Enhanced.py',
        'antNeuro/offline_multichannel_analysis.py',
    ]
    
    missing = []
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} - MISSING")
            missing.append(file_path)
    
    if missing:
        print(f"\n❌ Missing files: {', '.join(missing)}")
        return False
    
    print("\n✓ All required files present\n")
    return True


def test_help_message():
    """Test that help message can be displayed."""
    print("Testing help message...")
    
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, 'BrainLink_Offline_Analyzer.py', '--help'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and 'BrainLink Offline' in result.stdout:
            print("  ✓ Help message displays correctly\n")
            return True
        else:
            print(f"  ✗ Help message failed\n")
            return False
    except Exception as e:
        print(f"  ✗ Failed to run help: {e}\n")
        return False


def create_sample_data():
    """Create sample CSV and markers files for testing."""
    print("Creating sample test data...")
    
    try:
        import numpy as np
        import pandas as pd
        import json
        
        # Create sample CSV
        n_samples = 1000
        n_channels = 64
        sample_rate = 500
        
        channel_names = [f"Ch{i+1}" for i in range(n_channels)]
        
        # Generate random EEG-like data
        timestamps = np.arange(n_samples) / sample_rate
        sample_indices = np.arange(n_samples)
        
        # Random data with some structure
        data = {}
        data['timestamp'] = timestamps
        data['sample_index'] = sample_indices
        
        for ch in channel_names:
            # Random walk with EEG-like properties
            signal = np.random.randn(n_samples) * 5  # µV scale
            data[ch] = signal
        
        df = pd.DataFrame(data)
        
        csv_file = Path('test_data_sample.csv')
        df.to_csv(csv_file, index=False)
        print(f"  ✓ Created {csv_file}")
        
        # Create sample markers
        markers = {
            'session_id': 'test_session',
            'user_email': 'test@example.com',
            'sample_rate': sample_rate,
            'channel_count': n_channels,
            'channel_names': channel_names,
            'phase_markers': [
                {
                    'phase': 'baseline',
                    'task': None,
                    'start': 0.0,
                    'end': 1.0
                },
                {
                    'phase': 'task',
                    'task': 'test_task',
                    'start': 1.0,
                    'end': 2.0
                }
            ]
        }
        
        markers_file = Path('test_data_sample_markers.json')
        with open(markers_file, 'w') as f:
            json.dump(markers, f, indent=2)
        print(f"  ✓ Created {markers_file}")
        
        print("\n✓ Sample test data created\n")
        return True, csv_file, markers_file
        
    except Exception as e:
        print(f"  ✗ Failed to create sample data: {e}\n")
        return False, None, None


def run_quick_test(csv_file, markers_file):
    """Run a quick analysis test."""
    print("Running quick analysis test (this may take 30-60 seconds)...")
    
    try:
        from BrainLink_Offline_Analyzer import OfflineEEGAnalyzer
        
        # Create analyzer
        analyzer = OfflineEEGAnalyzer(
            csv_file=str(csv_file),
            markers_file=str(markers_file),
            fast_mode=True,
            n_permutations=50
        )
        
        print("  → Loading data...")
        df, markers = analyzer.load_data()
        
        print(f"  → Loaded {len(df)} samples, {len(markers.get('phase_markers', []))} phases")
        
        # Don't run full analysis in test (too slow)
        # Just verify the class structure works
        
        print("  ✓ Analyzer initialized and data loaded successfully\n")
        return True
        
    except Exception as e:
        print(f"  ✗ Analysis test failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def cleanup_test_data():
    """Remove test data files."""
    print("Cleaning up test data...")
    
    test_files = [
        'test_data_sample.csv',
        'test_data_sample_markers.json',
    ]
    
    for file_path in test_files:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            print(f"  ✓ Removed {file_path}")
    
    print()


def main():
    """Run all tests."""
    print("="*70)
    print("BrainLink Offline Analyzer - Installation Test")
    print("="*70)
    print()
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Imports
    tests_total += 1
    if test_imports():
        tests_passed += 1
    
    # Test 2: File dependencies
    tests_total += 1
    if test_dependencies():
        tests_passed += 1
    
    # Test 3: Analyzer class
    tests_total += 1
    if test_analyzer_class():
        tests_passed += 1
    
    # Test 4: Help message
    tests_total += 1
    if test_help_message():
        tests_passed += 1
    
    # Test 5: Create and analyze sample data
    tests_total += 1
    success, csv_file, markers_file = create_sample_data()
    if success:
        if run_quick_test(csv_file, markers_file):
            tests_passed += 1
        cleanup_test_data()
    
    # Summary
    print("="*70)
    print(f"Test Results: {tests_passed}/{tests_total} passed")
    print("="*70)
    
    if tests_passed == tests_total:
        print("\n✅ ALL TESTS PASSED - Analyzer is ready to use!")
        print("\nTry it with your data:")
        print("  python BrainLink_Offline_Analyzer.py your_session.csv --fast")
        return 0
    else:
        print(f"\n❌ {tests_total - tests_passed} test(s) failed")
        print("\nPlease check:")
        print("  1. All required packages are installed")
        print("  2. All required files are present")
        print("  3. Python version is 3.8 or higher")
        return 1


if __name__ == '__main__':
    sys.exit(main())
