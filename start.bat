@echo off
REM Start the Telugu <-> English interpreter (double-click this file).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "PY=python"
if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"

"%PY%" -c "import fastapi, uvicorn, websockets, cryptography, edge_tts" 1>nul 2>nul
if errorlevel 1 (
  echo Installing required packages...
  "%PY%" -m pip install -r requirements.txt
)
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example - add your Azure keys there if you have them.
)
"%PY%" run.py %*
pause
