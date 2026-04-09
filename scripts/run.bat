@echo off
REM Journiv Windows Launcher
REM This batch script starts Journiv with sensible defaults for Windows users

setlocal enabledelayedexpansion

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set APP_ROOT=%SCRIPT_DIR%..

REM Colors for output (using ANSI escape codes - requires Windows 10+)
set GREEN=[92m
set YELLOW=[93m
set RED=[91m
set RESET=[0m
set BOLD=[1m

echo.
echo %BOLD%╔════════════════════════════════════════════════════════════════╗%RESET%
echo %BOLD%║           Journiv - Private Journal (Windows)                  ║%RESET%
echo %BOLD%╚════════════════════════════════════════════════════════════════╝%RESET%
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%✗ Error: Python is not installed or not in PATH%RESET%
    echo.
    echo Please ensure Python 3.12 or higher is installed and added to PATH.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo %GREEN%✓ Python %PYTHON_VERSION% found%RESET%

REM Create data directory if it doesn't exist
if not exist "%APP_ROOT%\data" mkdir "%APP_ROOT%\data"
if not exist "%APP_ROOT%\data\media" mkdir "%APP_ROOT%\data\media"
echo %GREEN%✓ Data directories ready%RESET%

REM Check if .env exists, if not run setup
if not exist "%APP_ROOT%\.env" (
    echo.
    echo %YELLOW%→ First run detected. Setting up configuration...%RESET%
    echo.
    
    cd /d "%APP_ROOT%"
    python scripts\setup_defaults.py
    
    if errorlevel 1 (
        echo %RED%✗ Setup failed%RESET%
        pause
        exit /b 1
    )
    echo %GREEN%✓ Configuration setup complete%RESET%
)

echo.
echo %YELLOW%→ Checking for available port...%RESET%

REM Find an available port (starting from 8000)
for /l %%P in (8000,1,8100) do (
    netstat -ano | find ":%%P " >nul 2>&1
    if errorlevel 1 (
        set PORT=%%P
        goto :port_found
    )
)

:port_found
if "%PORT%"=="" (
    echo %RED%✗ Could not find an available port%RESET%
    pause
    exit /b 1
)

echo %GREEN%✓ Using port %PORT%%RESET%
echo.

REM Set environment variables
set DOMAIN_NAME=localhost:%PORT%

REM Install/upgrade dependencies if needed
echo %YELLOW%→ Checking dependencies...%RESET%
cd /d "%APP_ROOT%"
pip install -q --upgrade pip >nul 2>&1
pip install -e . >nul 2>&1

if errorlevel 1 (
    echo %YELLOW%→ Installing dependencies... This may take a few minutes%RESET%
    pip install -e .
    if errorlevel 1 (
        echo %RED%✗ Dependency installation failed%RESET%
        pause
        exit /b 1
    )
)
echo %GREEN%✓ Dependencies ready%RESET%

REM Start the server
echo.
echo %GREEN%════════════════════════════════════════════════════════════════%RESET%
echo %GREEN%Starting Journiv on http://localhost:%PORT%%RESET%
echo %GREEN%Press Ctrl+C to stop the server%RESET%
echo %GREEN%════════════════════════════════════════════════════════════════%RESET%
echo.

REM Launch browser after a short delay (in background)
timeout /t 2 /nobreak >nul 2>&1
start http://localhost:%PORT% >nul 2>&1

REM Start the application
cd /d "%APP_ROOT%"
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload

if errorlevel 1 (
    echo.
    echo %RED%✗ Server exited with error%RESET%
    pause
)

endlocal
