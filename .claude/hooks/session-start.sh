#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "Upgrading pip and setuptools..."
pip install --upgrade pip setuptools --quiet --ignore-installed

echo "Installing Python dependencies..."
PROJ_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
pip install -r "$PROJ_DIR/requirements.txt" --quiet
pip install pytest pytest-asyncio --quiet

echo "Session start hook complete."
