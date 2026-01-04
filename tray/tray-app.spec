# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# Paths
project_root = os.path.abspath(os.path.join(SPECPATH, '..'))
icons_dir = os.path.join(project_root, 'icons')

a = Analysis(
    ['main.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        # Include icons for tray
        (icons_dir, 'icons'),
    ],
    hiddenimports=[
        'pystray',
        'pystray._appindicator',
        'PIL',
        'PIL.Image',
        'gi',
        'gi.repository.Gtk',
        'gi.repository.GLib',
        'gi.repository.AppIndicator3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='website-blocker-tray',
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
    icon=os.path.join(icons_dir, 'icon-tray-24.png'),
)
