"""
ANT Neuro 64-Channel EEG Analyzer Package
==========================================

This package provides a complete 64-channel EEG analysis system for
ANT Neuro eego amplifiers, designed to integrate with the MindSpeller
platform.

ARCHITECTURE (Three-Layer Stack):
    
    Layer 1 - Base (AntNeuroAnalyzer_GUI.py)
    ----------------------------------------
    Core functionality:
    - eego SDK connection and device management
    - Authentication with MindSpeller backend
    - Basic EEG streaming and visualization
    - Signal processing utilities
    - Data recording and export
    
    Layer 2 - Enhanced (AntNeuroAnalyzer_GUI_Enhanced.py)
    -----------------------------------------------------
    Inherits from Layer 1, adds:
    - Advanced multi-channel feature extraction
    - Spatial features (coherence, PLI, asymmetry)
    - ROI-based analysis
    - Artifact rejection
    - Statistical testing (Kost-McDermott FDR)
    - Topographic visualization
    
    Layer 3 - Sequential (AntNeuroAnalyzer_GUI_Sequential.py)
    ---------------------------------------------------------
    Inherits from Layer 2, adds:
    - Guided workflow wizard
    - Session management
    - Task recording
    - Comprehensive export

USAGE:
    # Run the main application
    python -m antNeuro.AntNeuroAnalyzer_GUI_Sequential
    
    # Or import components
    from antNeuro import AntNeuroAnalyzer_GUI as Base
    from antNeuro import AntNeuroAnalyzer_GUI_Enhanced as Enhanced

REQUIREMENTS:
    - Python 3.13+ (required for eego SDK)
    - eego SDK (compiled in eego_sdk_toolbox/)
    - PySide6
    - PyQtGraph
    - NumPy, SciPy, Pandas

Author: BrainLink Companion Team
Date: February 2026
"""

# Version
__version__ = "1.0.0"

# Package metadata
__author__ = "BrainLink Companion Team"
__email__ = ""
__description__ = "ANT Neuro 64-Channel EEG Analyzer"

# Default imports
try:
    from . import AntNeuroAnalyzer_GUI
    from . import AntNeuroAnalyzer_GUI_Enhanced
    from . import AntNeuroAnalyzer_GUI_Sequential
except ImportError:
    # May fail if running individual module directly
    pass

# Expose key classes at package level
try:
    from .AntNeuroAnalyzer_GUI import (
        AntNeuroDeviceManager,
        DemoDeviceManager,
        AntNeuroAnalyzerWindow,
        FeatureAnalysisEngine,
        DeviceState,
        SessionState,
        EEGO_SDK_AVAILABLE,
        DEFAULT_CHANNEL_NAMES,
        FREQUENCY_BANDS,
        ROI_DEFINITIONS,
    )
    
    from .AntNeuroAnalyzer_GUI_Enhanced import (
        EnhancedAntNeuroAnalyzerWindow,
        EnhancedFeatureEngine,
        StatisticalEngine,
        EnhancedAnalyzerConfig,
        AnalysisConfidence,
        TopographicWidget,
    )
    
    from .AntNeuroAnalyzer_GUI_Sequential import (
        SequentialAntNeuroAnalyzerWindow,
        SessionWizard,
        WorkflowState,
        TaskDefinition,
        RecordingSession,
    )
except ImportError:
    pass

# Convenience function to run the application
def run():
    """Run the ANT Neuro 64-Channel EEG Analyzer."""
    from .AntNeuroAnalyzer_GUI_Sequential import main
    main()
