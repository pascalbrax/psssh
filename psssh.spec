# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Pascal Simple SSH.

Build (one-folder distribution):
    pip install pyinstaller
    pyinstaller psssh.spec

Output goes to dist/PascalSimpleSSH/PascalSimpleSSH.exe
"""
from PyInstaller.utils.hooks import collect_submodules

hidden_imports = (
    collect_submodules("paramiko")
    + collect_submodules("pyte")
    + collect_submodules("keyring.backends")
)

a = Analysis(
    ["psssh/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[("psssh/assets", "psssh/assets")],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PascalSimpleSSH",
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
    icon="psssh/assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PascalSimpleSSH",
)
