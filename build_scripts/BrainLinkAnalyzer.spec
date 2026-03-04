# -*- mode: python ; coding: utf-8 -*-


import os
import sys

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

datas = [
    (os.path.join(ROOT_DIR, 'assets'), 'assets'),
    (os.path.join(ROOT_DIR, 'BrainLinkParser'), 'BrainLinkParser'),
    (os.path.join(ROOT_DIR, 'docs', 'TroubleshootingGuide.md'), '.'),
    (os.path.join(ROOT_DIR, 'config', 'MindLink_User_Manual.txt'), '.'),
]
datas += pyside_datas
datas += shiboken_datas
datas += pyqtgraph_datas
datas += scipy_datas
datas += numpy_datas
datas += pandas_datas

binaries = []
binaries += pyside_binaries
binaries += shiboken_binaries
binaries += pyqtgraph_binaries
binaries += scipy_binaries
binaries += numpy_binaries
binaries += pandas_binaries

hiddenimports = [
    # Data processing and scientific computing
    'pandas',
    'numpy',
    'scipy',
    'scipy.signal',
    'scipy.integrate',
    'scipy.stats',
    
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
]
hiddenimports += pyside_hiddenimports
hiddenimports += shiboken_hiddenimports
hiddenimports += pyqtgraph_hiddenimports
hiddenimports += scipy_hiddenimports
hiddenimports += numpy_hiddenimports
hiddenimports += pandas_hiddenimports

excludes = [
    'PyQt5', 'PyQt6',
    'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
    'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
]


a = Analysis(
    [os.path.join(ROOT_DIR, 'BrainLinkAnalyzer_GUI_Sequential_Integrated.py')],
    pathex=[ROOT_DIR],
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
    os.path.join(ROOT_DIR, 'assets', 'splash.png'),
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
    icon=[os.path.join(ROOT_DIR, 'assets', 'favicon.ico')],
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
