@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "SCRIPT=%~dp0gitlab_push_tool_v2.py"
if not exist "%SCRIPT%" (
  echo FEHLER: gitlab_push_tool_v2.py wurde nicht gefunden.
  pause
  exit /b 1
)
where py >nul 2>&1
if %errorlevel%==0 (set "PYTHON=py -3") else (set "PYTHON=python")
%PYTHON% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo FEHLER: PyInstaller ist nicht installiert.
  echo Bitte PyInstaller in der Python-Umgebung bereitstellen und erneut starten.
  pause
  exit /b 1
)
if exist "%~dp0build" rmdir /s /q "%~dp0build"
if exist "%~dp0dist" rmdir /s /q "%~dp0dist"
echo EXE wird gebaut...
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed --name Git-Repository-Pusher "%SCRIPT%"
if errorlevel 1 (
  echo FEHLER: Die EXE konnte nicht erstellt werden.
  pause
  exit /b 1
)
echo Fertig: %~dp0dist\Git-Repository-Pusher.exe
pause
endlocal
