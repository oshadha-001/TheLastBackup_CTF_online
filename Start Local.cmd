@echo off
cd /d "%~dp0"
if not exist "..\Local-Only\.venv\Scripts\python.exe" (
  echo Follow README.md to create the local Python environment first.
  pause
  exit /b 1
)
"..\Local-Only\.venv\Scripts\python.exe" tools\run_local.py
pause
