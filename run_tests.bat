@echo off
REM Run the automated test suite and the live cloud-provider check.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "PY=python"
if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
echo === Unit + WebSocket tests (offline, mock providers) ===
"%PY%" -m pytest
echo.
echo === LIVE provider check (real Azure / Google / MyMemory calls) ===
"%PY%" scripts\stage1_probe.py --translator-diagnose
pause
