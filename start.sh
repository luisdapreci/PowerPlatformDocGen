#!/bin/bash
# Quick start script for Power Platform Documentation Generator (Unix/Linux/Mac)

echo "================================================"
echo "Power Platform Documentation Generator"
echo "================================================"
echo ""

# Check Python
echo "[1/4] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed or not in PATH"
    echo "Please install Python 3.10 or higher"
    exit 1
fi
python3 --version
echo ""

# Check pac CLI
echo "[2/4] Checking Power Platform CLI..."
if ! command -v pac &> /dev/null; then
    echo "Traditional pac command not found, checking dnx alternative..."
    if dnx Microsoft.PowerApps.CLI.Tool --yes help &> /dev/null; then
        echo "Power Platform CLI available via dnx (no installation mode)"
    else
        echo "WARNING: Power Platform CLI is not available"
        echo ""
        echo "Option 1 (Recommended): Use dnx (no installation required, needs .NET 10+)"
        echo "  dnx Microsoft.PowerApps.CLI.Tool --yes help"
        echo ""
        echo "Option 2: Install pac CLI from https://aka.ms/PowerAppsCLI"
        echo ""
        echo "Canvas app unpacking will not work without Power Platform CLI."
        echo ""
    fi
else
    if pac help &> /dev/null; then
        echo "Power Platform CLI is installed and working"
    else
        echo "WARNING: Power Platform CLI found but not working properly"
    fi
fi
echo ""

# Install dependencies
echo "[3/3] Installing Python dependencies..."
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing packages from requirements.txt..."
pip install -r requirements.txt --quiet

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    exit 1
fi

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Starting the application..."
echo "Open your browser to: http://localhost:8000/static/index.html"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the application
python3 src/main.py
