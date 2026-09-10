# Portable PyInstaller specification; build on Windows with Python 3.12 x64.
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'gitlab_push_tool_v2.py')], pathex=[str(root)],
             binaries=[], datas=[], hiddenimports=[], hookspath=[],
             hooksconfig={}, runtime_hooks=[], excludes=['PySide6.QtWebEngineCore',
             'PySide6.QtWebEngineWidgets', 'tkinter'], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Git-Repository-Pusher',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
