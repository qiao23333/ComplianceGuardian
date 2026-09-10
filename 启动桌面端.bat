@echo off
REM ============================================================
REM Compliance Guardian - start desktop app
REM No admin rights needed.
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv not found. Please run scripts\setup_venv.bat first.
    pause
    exit /b 1
)

".venv\Scripts\pythonw.exe" -m apps.desktop.main
if errorlevel 1 (
    echo Failed to start. Try: .venv\Scripts\python.exe -m apps.desktop.main
    pause
)
