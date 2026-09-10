@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist .venv\Scripts\python.exe (
  echo FEHLER: Python-Umgebung fehlt. Installation laut README ausfuehren.
  popd
  exit /b 1
)
.venv\Scripts\python.exe gitlab_push_tool_v2.py
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
