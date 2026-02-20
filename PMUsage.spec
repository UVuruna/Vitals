# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['U:\\Coding\\UVuruna (git)\\Gadgets\\PMUsage\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('U:\\Coding\\UVuruna (git)\\Gadgets\\PMUsage\\assets', 'assets'), ('U:\\Coding\\UVuruna (git)\\Gadgets\\PMUsage\\config', 'config')],
    hiddenimports=['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'setuptools', 'pkg_resources', 'charset_normalizer', 'unittest', 'xmlrpc', 'pydoc', 'tkinter', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'PySide6.QtWebChannel', 'PySide6.QtWebEngineQuick'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PMUsage',
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
    icon=['U:\\Coding\\UVuruna (git)\\Gadgets\\PMUsage\\assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PMUsage',
)
