# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['client.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['web', 'tls_cert', 'discovery', 'audit', 'stickers', 'bots', 'widgets.thread_window', 'widgets.sticker_shop', 'widgets.fingerprint', 'widgets.server_tray', 'pystray', 'PIL.Image', 'PIL.ImageDraw', 'voice_api', 'video_api', 'cryptography.hazmat.primitives.asymmetric.x25519', 'cryptography.hazmat.primitives.kdf.hkdf', 'cryptography.hazmat.primitives.ciphers.aead'],
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
    name='client',
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
    icon=['C:/Users/Administrator/Documents/trae_projects/AI/learn_demos/321_局域网摸鱼助手_聊天文件游戏/app.ico'],
)
