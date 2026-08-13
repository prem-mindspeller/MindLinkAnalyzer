# -*- mode: python ; coding: utf-8 -*-

import os

# Get workspace root - SPECPATH is the directory containing this spec file
WORKSPACE_ROOT = os.path.dirname(SPECPATH)

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT_DIR = os.path.abspath(os.getcwd())


pyside_datas, pyside_binaries, pyside_hiddenimports = collect_all('PySide6')

# CRITICAL: Collect Shiboken6 - the binding generator that PySide6 depends on
shiboken_datas, shiboken_binaries, shiboken_hiddenimports = collect_all('shiboken6')

# Collect pyqtgraph data files only (avoid collect_all which crashes on examples/opengl modules)
pyqtgraph_datas = collect_data_files('pyqtgraph', excludes=['examples', 'opengl'])
pyqtgraph_binaries = []
pyqtgraph_hiddenimports = [
    'pyqtgraph',
    'pyqtgraph.Qt',
    'pyqtgraph.graphicsItems',
    'pyqtgraph.widgets',
    'pyqtgraph.exporters',
    'pyqtgraph.colors',
    'pyqtgraph.colormap',
]

# Collect scipy, numpy, and pandas data files to ensure all submodules are included
scipy_datas, scipy_binaries, scipy_hiddenimports = collect_all('scipy')
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all('numpy')
pandas_datas, pandas_binaries, pandas_hiddenimports = collect_all('pandas')

# Collect grpcio for EDI2 client (ANT Neuro communication)
try:
    grpc_datas, grpc_binaries, grpc_hiddenimports = collect_all('grpc')
except Exception:
    grpc_datas, grpc_binaries, grpc_hiddenimports = [], [], []

datas = [
    (os.path.join(WORKSPACE_ROOT, 'assets'), 'assets'),
    (os.path.join(WORKSPACE_ROOT, 'BrainLinkParser'), 'BrainLinkParser'),
    (os.path.join(WORKSPACE_ROOT, 'docs', 'TroubleshootingGuide.md'), '.'),
    (os.path.join(WORKSPACE_ROOT, 'config', 'MindLink_User_Manual.txt'), '.'),
    # === MULTICHANNEL ANALYSIS PACKAGES ===
    # antNeuro package - 64-channel EEG analysis engine (gRPC/EDI2 based)
    (os.path.join(WORKSPACE_ROOT, 'antNeuro', '__init__.py'), 'antNeuro'),
    (os.path.join(WORKSPACE_ROOT, 'antNeuro', 'enhanced_multichannel_analysis.py'), 'antNeuro'),
    (os.path.join(WORKSPACE_ROOT, 'antNeuro', 'offline_multichannel_analysis.py'), 'antNeuro'),
    (os.path.join(WORKSPACE_ROOT, 'antNeuro', 'edi2_client.py'), 'antNeuro'),
    (os.path.join(WORKSPACE_ROOT, 'antNeuro', 'EdigRPC_pb2.py'), 'antNeuro'),
    (os.path.join(WORKSPACE_ROOT, 'antNeuro', 'EdigRPC_pb2_grpc.py'), 'antNeuro'),
    # ANT Neuro EDI DLL directories (gRPC server binaries)
    (os.path.join(WORKSPACE_ROOT, 'antNeuro', 'edi_dlls'), 'antNeuro/edi_dlls'),
    (os.path.join(WORKSPACE_ROOT, 'antNeuro', 'edi_dlls_impl'), 'antNeuro/edi_dlls_impl'),
    # utils package - report generator, LED stimulator, etc.
    (os.path.join(WORKSPACE_ROOT, 'utils', '__init__.py'), 'utils'),
    (os.path.join(WORKSPACE_ROOT, 'utils', 'enhanced_report_generator.py'), 'utils'),
    (os.path.join(WORKSPACE_ROOT, 'utils', 'led_stimulator.py'), 'utils'),
    (os.path.join(WORKSPACE_ROOT, 'utils', 'prompttask.py'), 'utils'),
    (os.path.join(WORKSPACE_ROOT, 'utils', 'splash_screen.py'), 'utils'),
    # Main GUI scripts (needed for imports)
    (os.path.join(WORKSPACE_ROOT, 'BrainLinkAnalyzer_GUI.py'), '.'),
    (os.path.join(WORKSPACE_ROOT, 'BrainLinkAnalyzer_GUI_Enhanced.py'), '.'),
]
datas += pyside_datas
datas += shiboken_datas
datas += pyqtgraph_datas
datas += scipy_datas
datas += numpy_datas
datas += pandas_datas
datas += grpc_datas

binaries = []
binaries += pyside_binaries
binaries += shiboken_binaries
binaries += pyqtgraph_binaries
binaries += scipy_binaries
binaries += numpy_binaries
binaries += pandas_binaries
binaries += grpc_binaries

hiddenimports = [
    # Data processing and scientific computing
    'pandas',
    'numpy',
    'scipy',
    'scipy.signal',
    'scipy.integrate',
    'scipy.stats',
    'scipy.stats.mstats',
    
    # Plotting and visualization
    'pyqtgraph',
    'pyqtgraph.Qt',
    
    # Serial communication
    'serial',
    'serial.tools',
    'serial.tools.list_ports',
    'cushy_serial',
    
    # Network and HTTP
    'requests',
    'urllib3',
    'certifi',
    'ssl',
    
    # gRPC for ANT Neuro EDI2 communication
    'grpc',
    'grpc._cython',
    'grpc._cython.cygrpc',
    'google.protobuf',
    
    # Progress bars (optional, has fallback)
    'tqdm',
    
    # Standard library modules that might need explicit inclusion
    'json',
    'threading',
    'weakref',
    'collections',
    'datetime',
    'platform',
    'getpass',
    'argparse',
    'dataclasses',
    'typing',
    'copy',
    'math',
    'random',
    'warnings',
    'logging',
    'subprocess',
    'atexit',
    
    # === MULTICHANNEL ANALYSIS MODULES ===
    # antNeuro package modules (gRPC/EDI2 based)
    'antNeuro',
    'antNeuro.enhanced_multichannel_analysis',
    'antNeuro.offline_multichannel_analysis',
    'antNeuro.edi2_client',
    'antNeuro.EdigRPC_pb2',
    'antNeuro.EdigRPC_pb2_grpc',
    # utils package modules
    'utils',
    'utils.enhanced_report_generator',
    'utils.led_stimulator',
    'utils.prompttask',
    'utils.splash_screen',
    # Main GUI modules (imported by Sequential_Integrated)
    'BrainLinkAnalyzer_GUI',
    'BrainLinkAnalyzer_GUI_Enhanced',
]
hiddenimports += pyside_hiddenimports
hiddenimports += shiboken_hiddenimports
hiddenimports += pyqtgraph_hiddenimports
hiddenimports += scipy_hiddenimports
hiddenimports += numpy_hiddenimports
hiddenimports += pandas_hiddenimports
hiddenimports += grpc_hiddenimports

excludes = [
    'PyQt5', 'PyQt6',
    'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
    'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
]


a = Analysis(
    [os.path.join(WORKSPACE_ROOT, 'BrainLinkAnalyzer_GUI_Sequential_Integrated.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

splash = Splash(
    os.path.join(WORKSPACE_ROOT, 'assets', 'splash.png'),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,  # Disable text overlay - image already has "Starting..." text
    text_size=11,
    text_color='white',
    text_default='',  # Empty default since we're not showing text
    minify_script=True,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name='MindLinkAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(WORKSPACE_ROOT, 'assets', 'favicon.ico')],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MindLinkAnalyzer'
)
