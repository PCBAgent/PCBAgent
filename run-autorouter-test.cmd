@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run_freerouting_test.ps1"
if errorlevel 1 (
  echo.
  echo Autorouter test failed. See the error above.
  pause
)
