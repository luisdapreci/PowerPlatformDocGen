@echo off
setlocal enabledelayedexpansion
REM Quick start script for Power Platform Documentation Generator (Windows)

echo ================================================
echo Power Platform Documentation Generator
echo ================================================
echo.

REM Check .NET SDK
echo [1/10] Checking .NET SDK installation...
dotnet --version >nul 2>nul
if %errorlevel% equ 0 (
    echo .NET SDK is available.
    goto :dotnet_done
)
echo .NET SDK is not installed. Attempting to install via winget...
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo WARNING: winget is not available. Cannot auto-install .NET SDK.
    echo To install manually, visit: https://dotnet.microsoft.com/download
    goto :dotnet_warn
)
winget install --id Microsoft.DotNet.SDK.9 --accept-source-agreements --accept-package-agreements
if %errorlevel% equ 0 (
    echo .NET SDK installed successfully.
    echo NOTE: You may need to restart this script for dotnet to be in PATH.
    goto :dotnet_done
)
echo WARNING: Failed to install .NET SDK via winget.
echo To install manually, visit: https://dotnet.microsoft.com/download
:dotnet_warn
echo.
echo .NET 10+ is required for Power Platform CLI (dnx^).
echo Continuing with setup...
:dotnet_done
echo.

REM Check Git
echo [2/10] Checking Git installation...
git --version >nul 2>nul
if %errorlevel% equ 0 (
    echo Git is available.
    goto :git_done
)
echo Git is not installed. Attempting to install via winget...
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo WARNING: winget is not available. Cannot auto-install Git.
    echo To install manually, visit: https://git-scm.com/download/win
    goto :git_warn
)
winget install --id Git.Git --accept-source-agreements --accept-package-agreements
if %errorlevel% equ 0 (
    echo Git installed successfully.
    echo NOTE: You may need to restart this script for git to be in PATH.
    goto :git_done
)
echo WARNING: Failed to install Git via winget.
echo To install manually, visit: https://git-scm.com/download/win
:git_warn
echo.
echo Git is recommended for version control.
echo Continuing with setup...
:git_done
echo.

REM Check Python
echo [3/10] Checking Python installation...
python --version >nul 2>nul
if %errorlevel% equ 0 (
    python --version
    goto :python_done
)
echo Python is not installed. Attempting to install via winget...
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: winget is not available. Cannot auto-install Python.
    echo To install manually, visit: https://www.python.org/downloads/
    echo Python 3.10 or higher is required.
    pause
    exit /b 1
)
winget install --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
if %errorlevel% equ 0 (
    echo Python installed successfully.
    echo NOTE: Please restart this script for python to be in PATH.
    pause
    exit /b 0
)
echo ERROR: Failed to install Python via winget.
echo To install manually, visit: https://www.python.org/downloads/
echo Python 3.10 or higher is required.
pause
exit /b 1
:python_done
echo.

REM Check Power Platform CLI (pac or dnx)
echo [4/10] Checking Power Platform CLI...
where pac >nul 2>nul
if %errorlevel% equ 0 (
    echo Power Platform CLI - pac - is available.
    goto :pac_done
)
dotnet --version >nul 2>nul
if %errorlevel% equ 0 (
    echo pac not found, but .NET is installed - dnx will be used at runtime.
    echo   dnx runs Power Platform CLI without a separate install.
    goto :pac_done
)
echo WARNING: Power Platform CLI is not available.
echo Install .NET SDK first, then dnx will work automatically.
echo Canvas app unpacking will not work without Power Platform CLI.
echo Continuing with setup...
:pac_done
echo.

REM Check Pandoc
echo [5/10] Checking Pandoc installation...
where pandoc >nul 2>nul
if %errorlevel% equ 0 (
    echo Pandoc is available
    goto :pandoc_done
)
echo Pandoc is not installed. Attempting to install via winget...
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo WARNING: winget is not available. Cannot auto-install Pandoc.
    echo To install manually, visit: https://pandoc.org/installing.html
    goto :pandoc_warn
)
winget install --id JohnMacFarlane.Pandoc --accept-source-agreements --accept-package-agreements
if %errorlevel% equ 0 (
    echo Pandoc installed successfully.
    echo NOTE: You may need to restart this script for Pandoc to be in PATH.
    goto :pandoc_done
)
echo WARNING: Failed to install Pandoc via winget.
echo To install manually, visit: https://pandoc.org/installing.html
echo Or use winget: winget install --id JohnMacFarlane.Pandoc
:pandoc_warn
echo.
echo Pandoc is required for Word document (.docx) generation.
echo Continuing with setup...
:pandoc_done
echo.

REM Check GitHub CLI
echo [6/10] Checking GitHub CLI...
where gh >nul 2>nul
if %errorlevel% equ 0 (
    echo GitHub CLI is available.
    goto :ghcli_done
)
echo GitHub CLI is not installed. Attempting to install via winget...
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo WARNING: winget is not available. Cannot auto-install GitHub CLI.
    echo To install manually, visit: https://cli.github.com/
    goto :ghcli_warn
)
winget install --id GitHub.cli --accept-source-agreements --accept-package-agreements
if %errorlevel% equ 0 (
    echo GitHub CLI installed successfully.
    echo NOTE: You may need to restart this script for gh to be in PATH.
    goto :ghcli_done
)
echo WARNING: Failed to install GitHub CLI via winget.
echo To install manually, visit: https://cli.github.com/
echo Or use winget: winget install --id GitHub.cli
:ghcli_warn
echo.
echo GitHub Copilot CLI integration will not work without GitHub CLI.
echo Continuing with setup...
:ghcli_done
echo.

REM Check GitHub CLI authentication
echo [7/10] Checking GitHub CLI authentication...
where gh >nul 2>nul
if %errorlevel% neq 0 (
    echo Skipping authentication check - GitHub CLI is not installed.
    goto :ghauth_done
)
gh auth status >nul 2>nul
if %errorlevel% equ 0 (
    echo GitHub CLI is authenticated.
    goto :ghauth_done
)
echo You are not logged in to GitHub CLI.
echo Starting GitHub CLI login...
echo.
gh auth login
if %errorlevel% equ 0 (
    echo GitHub CLI login successful.
    goto :ghauth_done
)
echo WARNING: GitHub CLI login failed or was cancelled.
echo You can log in later with: gh auth login
echo Continuing with setup...
:ghauth_done
echo.

REM Check GitHub Copilot CLI
echo [8/10] Checking GitHub Copilot CLI...
where copilot >nul 2>nul
if %errorlevel% equ 0 (
    echo GitHub Copilot CLI is available.
    goto :copilot_done
)
echo GitHub Copilot CLI is not installed. Attempting to install via winget...
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo WARNING: winget is not available. Cannot auto-install GitHub Copilot CLI.
    echo To install manually: winget install GitHub.Copilot
    goto :copilot_warn
)
winget install --id GitHub.Copilot --accept-source-agreements --accept-package-agreements
if %errorlevel% equ 0 (
    echo GitHub Copilot CLI installed successfully.
    echo NOTE: You may need to restart this script for it to be in PATH.
    goto :copilot_done
)
echo WARNING: Failed to install GitHub Copilot CLI via winget.
echo To install manually: winget install GitHub.Copilot
:copilot_warn
echo.
echo GitHub Copilot CLI is required for AI-powered documentation generation.
echo Continuing with setup...
:copilot_done
echo.

REM Create virtual environment if it doesn't exist
echo [9/10] Setting up Python virtual environment...
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
echo [10/10] Installing Python dependencies...
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
