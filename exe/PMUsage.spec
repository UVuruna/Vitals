# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['U:\\Coding\\UVuruna (git)\\Gadgets\\ProcessMemoryUsage\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('U:\\Coding\\UVuruna (git)\\Gadgets\\ProcessMemoryUsage\\assets', 'assets'), ('U:\\Coding\\UVuruna (git)\\Gadgets\\ProcessMemoryUsage\\config', 'config')],
    hiddenimports=['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PMUsage',
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
    icon=['U:\\Coding\\UVuruna (git)\\Gadgets\\ProcessMemoryUsage\\assets\\icon.ico'],
)
