@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run_ipc_demo.ps1"
if errorlevel 1 (
  echo.
  echo Demo could not start. See the error above.
  pause
)
