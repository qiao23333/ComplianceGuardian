@echo off
REM ============================================================
REM Compliance Guardian - one-time environment setup
REM Creates .venv with Python 3.11 (required: tkinter support)
REM and installs all dependencies.
REM No admin rights needed.
REM ============================================================
setlocal
cd /d "%~dp0.."

echo [1/3] Looking for Python 3.11 (tkinter required)...
where py >nul 2>nul
if errorlevel 1 (
    echo     ERROR: Python launcher "py" not found. Install Python 3.11 first.
    pause
    exit /b 1
)

py -3.11 -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo     ERROR: Python 3.11 found but tkinter is missing.
    echo     Please install official Python 3.11 from python.org.
    pause
    exit /b 1
)
echo     Found: 
py -3.11 -V

echo [2/3] Creating virtual environment (.venv)...
py -3.11 -m venv .venv
if errorlevel 1 (
    echo     ERROR: Failed to create venv.
    pause
    exit /b 1
)

echo [3/3] Installing dependencies (may take a few minutes)...
".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-dev.txt -r requirements-desktop.txt
if errorlevel 1 (
    echo     ERROR: pip install failed. Check network and retry.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Setup complete!
echo   - Start desktop app: double-click  启动桌面端.bat
echo   - Build Windows exe: double-click  packaging\build_windows.bat
echo ============================================================
pause
