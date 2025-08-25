#!/bin/bash
# Local GitHub Actions workflow test

set -e

echo "🧪 Local GitHub Actions workflow testing"
echo "=================================================="

# Activate virtual environment
source venv/bin/activate

echo "✅ Virtual environment activated"

# Install dependencies
echo "📦 Installing dependencies..."
python -m pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    pip install rich click swebench docker
fi

echo "✅ Dependencies installed"

# Simulate getting changed files
echo "🔍 Looking for changed data point files..."

# Get changed files (git diff simulation)
if [ "$1" = "all" ]; then
    # Test all files
    CHANGED_FILES=$(find data_points -name "*.json" | head -3)
else
    # Test only new/changed files
    CHANGED_FILES=$(git status --porcelain | grep "^[AM].*data_points.*\.json$" | cut -c4- || true)
    
    # If no changed files, use test file
    if [ -z "$CHANGED_FILES" ]; then
        CHANGED_FILES="data_points/astropy__astropy-11693.json"
        echo "⚠️  No changed files, using test file: $CHANGED_FILES"
    fi
fi

if [ -n "$CHANGED_FILES" ]; then
    echo "📁 Found files for validation:"
    echo "$CHANGED_FILES"
    
    # Export environment variable
    export CHANGED_FILES
    
    echo "🚀 Starting validation..."
    python scripts/validate_changed.py
    
    # Check result
    if [ $? -eq 0 ]; then
        echo "✅ Validation passed successfully!"
        echo "🎉 Workflow completed without errors"
    else
        echo "❌ Validation failed!"
        echo "💥 Workflow completed with errors"
        exit 1
    fi
else
    echo "ℹ️  No data point files to validate"
    echo "✅ Workflow completed (nothing to validate)"
fi

echo "=================================================="
echo "🏁 Local testing completed"
