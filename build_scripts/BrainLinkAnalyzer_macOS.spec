# -*- mode: python ; coding: utf-8 -*-
# macOS-specific PyInstaller spec file for MindLink Analyzer

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules


pyside_datas, pyside_binaries, pyside_hiddenimports = collect_all('PySide6')

# Collect scipy, numpy, and pandas data files to ensure all submodules are included
scipy_datas, scipy_binaries, scipy_hiddenimports = collect_all('scipy')
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all('numpy')
pandas_datas, pandas_binaries, pandas_hiddenimports = collect_all('pandas')

datas = [
    ('assets', 'assets'),
    ('BrainLinkParser', 'BrainLinkParser'),
    ('TroubleshootingGuide.md', '.'),
    ('MindLink_User_Manual.txt', '.'),
]
datas += pyside_datas
datas += scipy_datas
datas += numpy_datas
datas += pandas_datas

binaries = []
binaries += pyside_binaries
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
hiddenimports += scipy_hiddenimports
hiddenimports += numpy_hiddenimports
hiddenimports += pandas_hiddenimports

excludes = [
    'PyQt5', 'PyQt6',
    'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
    'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'winreg',  # Windows-specific module
]


a = Analysis(
    ['BrainLinkAnalyzer_GUI_Sequential_Integrated.py'],
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MindLinkAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
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

app = BUNDLE(
    coll,
    name='MindLinkAnalyzer.app',
    icon='assets/favicon.icns',
    bundle_identifier='com.mindspeller.mindlinkanalyzer',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '1.2.0',
        'CFBundleVersion': '1.2.0',
        'NSHumanReadableCopyright': 'Copyright © 2025 MindSpeller',
        'LSMinimumSystemVersion': '10.13.0',
        'NSRequiresAquaSystemAppearance': 'False',
        # Serial port access permissions
        'NSBluetoothAlwaysUsageDescription': 'This app needs Bluetooth access to connect to BrainLink device',
        'NSBluetoothPeripheralUsageDescription': 'This app needs Bluetooth access to connect to BrainLink device',
    },
)
