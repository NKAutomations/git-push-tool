@echo off
setlocal EnableExtensions
pushd "%~dp0" || exit /b 1
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo FEHLER: .venv fehlt. Siehe README, Abschnitt Installation und Build.
  popd
  exit /b 1
)
"%PYTHON%" -m pip check
if errorlevel 1 goto :fail
"%PYTHON%" -c "import sys; assert sys.platform == 'win32'; assert sys.version_info[:2] == (3,12)"
if errorlevel 1 goto :fail
"%PYTHON%" -m unittest discover -s tests -v
if errorlevel 1 goto :fail
"%PYTHON%" -m PyInstaller --noconfirm --clean Git-Repository-Pusher.spec
if errorlevel 1 goto :fail
"%PYTHON%" -m pip freeze > dist\build-environment.txt
"%PYTHON%" -c "import hashlib,pathlib; p=pathlib.Path('dist/Git-Repository-Pusher.exe'); pathlib.Path('dist/SHA256SUMS.txt').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n',encoding='utf-8')"
if errorlevel 1 goto :fail
echo Fertig: dist\Git-Repository-Pusher.exe
popd
exit /b 0
:fail
echo FEHLER: Test oder Build fehlgeschlagen. Keine neue EXE freigeben.
popd
exit /b 1
