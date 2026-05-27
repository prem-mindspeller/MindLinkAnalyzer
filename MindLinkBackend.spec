# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

# Paths relative to this spec file - works regardless of who builds it or where
_SPEC_DIR    = os.path.dirname(os.path.abspath(SPEC))
_BACKEND_DIR = os.path.join(_SPEC_DIR, 'newBackend')
_PARSER_DIR  = os.path.join(_SPEC_DIR, 'BrainLinkParser')

datas = [(_PARSER_DIR, 'BrainLinkParser')]
binaries = []
hiddenimports = ['serial.tools.list_ports', 'serial.tools.list_ports_windows']
for _pkg in ('serial', 'fastapi', 'uvicorn', 'starlette', 'anyio',
             'pydantic', 'numpy', 'scipy', 'cushy_serial', 'mindrove'):
    _r = collect_all(_pkg)
    datas += _r[0]; binaries += _r[1]; hiddenimports += _r[2]


a = Analysis(
    [os.path.join(_BACKEND_DIR, 'main.py')],
    pathex=[_BACKEND_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6', 'PySide6', 'PyQt5', 'PySide2', 'tkinter', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MindlinkBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MindlinkBackend',
)
