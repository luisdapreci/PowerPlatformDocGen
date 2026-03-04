@echo off
setlocal enabledelayedexpansion
REM Quick start script for Power Platform Documentation Generator (Windows)

echo ================================================
echo Power Platform Documentation Generator
echo ================================================
echo.

REM Check .NET SDK
echo [1/7] Checking .NET SDK installation...
dotnet --version >nul 2>nul
if %errorlevel% equ 0 (
    echo .NET SDK is available
) else (
    echo WARNING: .NET SDK is not available
    echo.
    echo To install, visit: https://dotnet.microsoft.com/download
    echo Or use winget: winget install Microsoft.DotNet.SDK.10
    echo.
    echo .NET 10+ is required for Power Platform CLI (pac or dnx^).
    echo Continuing with setup...
)
echo.

REM Check Git
echo [2/7] Checking Git installation...
git --version >nul 2>nul
if %errorlevel% equ 0 (
    echo Git is available
) else (
    echo WARNING: Git is not available
    echo.
    echo To install, visit: https://git-scm.com/download/win
    echo Or use winget: winget install --id Git.Git
    echo.
    echo Git is recommended for version control.
    echo Continuing with setup...
)
echo.

REM Check Python
echo [3/7] Checking Python installation...
python --version 2>nul
if errorlevel 1 (
    echo ERROR: Python 3 is not installed or not in PATH
    echo Please install Python 3.10 or higher
    pause
    exit /b 1
)
echo.

REM Check pac CLI
echo [4/7] Checking Power Platform CLI...
set PAC_FOUND=0
where pac >nul 2>nul
if %errorlevel% equ 0 set PAC_FOUND=1

where dnx >nul 2>nul
if %errorlevel% equ 0 set PAC_FOUND=1

if !PAC_FOUND! equ 1 (
    echo Power Platform CLI is available
) else (
    echo WARNING: Power Platform CLI is not available
    echo.
    echo To install, run one of these commands:
    echo   dotnet tool install --global Microsoft.PowerApps.CLI.Tool
    echo   dnx Microsoft.PowerApps.CLI.Tool --yes help
    echo.
    echo Canvas app unpacking will not work without Power Platform CLI.
    echo Continuing with setup...
)
echo.

REM Check GitHub CLI
echo [5/7] Checking GitHub CLI...
where gh >nul 2>nul
if %errorlevel% equ 0 (
    echo GitHub CLI is available
) else (
    echo WARNING: GitHub CLI is not available
    echo.
    echo To install, visit: https://cli.github.com/
    echo Or use winget: winget install --id GitHub.cli
    echo.
    echo GitHub Copilot CLI integration will not work without GitHub CLI.
    echo Continuing with setup...
)
echo.

REM Create virtual environment if it doesn't exist
echo [6/7] Setting up Python virtual environment...
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
call venv\Scripts\activate.bat
echo.

REM Install dependencies
echo [7/7] Installing Python dependencies...
echo Installing packages from requirements.txt...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo ================================================
echo Setup Complete!
echo ================================================
echo.
echo Starting the application...
echo Open your browser to: http://localhost:8000/static/index.html
echo.
echo Press Ctrl+C to stop the server
echo.

REM Open browser after a short delay to let the server start
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000/static/index.html"

REM Start the application
python src\main.py
