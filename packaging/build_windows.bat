@echo off
REM ============================================================
REM Compliance Guardian - Windows build script
REM Usage: double-click, or run packaging\build_windows.bat
REM Output: dist\ComplianceGuardian\ComplianceGuardian.exe
REM ============================================================
setlocal
cd /d "%~dp0.."

echo [1/3] Checking venv...
if not exist ".venv\Scripts\python.exe" (
    echo     .venv not found. Please run scripts\setup_venv.bat first.
    pause
    exit /b 1
)

echo [2/3] Running tests...
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 (
    echo     Tests failed. Build aborted.
    pause
    exit /b 1
)

echo [3/3] Building (1-3 minutes)...
".venv\Scripts\pyinstaller.exe" packaging\desktop.spec --clean --noconfirm
if errorlevel 1 (
    echo     Build failed. See errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Build OK: dist\ComplianceGuardian\ComplianceGuardian.exe
echo ============================================================
pause
