#!/bin/bash
# run.sh — Setup virtual environment, install dependencies, and run the pipeline

set -e

VENV_DIR=".venv"
PYTHON=python3

echo "========================================"
echo "  ClearCase → GitHub Migration Pipeline"
echo "========================================"

# Check Python is available
if ! command -v $PYTHON &> /dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1)
echo "[INFO] Using $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creating virtual environment at $VENV_DIR ..."
    $PYTHON -m venv "$VENV_DIR"
    echo "[INFO] Virtual environment created."
else
    echo "[INFO] Virtual environment already exists at $VENV_DIR"
fi

# Activate virtual environment
echo "[INFO] Activating virtual environment ..."
source "$VENV_DIR/bin/activate"

# Upgrade pip silently
echo "[INFO] Upgrading pip ..."
pip install --upgrade pip --quiet

# Install requirements
echo "[INFO] Installing requirements from requirements.txt ..."
pip install -r requirements.txt

echo "[INFO] All dependencies installed successfully."
echo "========================================"

# Parse arguments and pass them through to main.py
# Usage examples:
#   ./run.sh                          (uses default config.yaml)
#   ./run.sh --dry-run                (plan only, no writes)
#   ./run.sh --config custom.yaml     (use a different config)
#   ./run.sh --no-resume              (start fresh)
#   ./run.sh --debug                  (verbose logging)

echo "[INFO] Starting migration pipeline ..."
echo ""

$PYTHON main.py "$@"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "[SUCCESS] Migration pipeline completed successfully."
else
    echo "[FAILED] Migration pipeline exited with errors. Check logs/ for details."
fi

deactivate
exit $EXIT_CODE
