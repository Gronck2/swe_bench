#!/bin/bash
set -e

# SWE-bench Validator Docker Entrypoint
# This script runs inside the SWE-bench Docker environment

echo "🐋 Starting SWE-bench Validator in Docker environment"
echo "Working directory: $(pwd)"
echo "User: $(whoami)"
echo "Python version: $(python --version)"

# Check if Docker socket is available (for Docker-in-Docker)
if [ -S /var/run/docker.sock ]; then
    echo "✅ Docker socket available for nested container execution"
else
    echo "⚠️  No Docker socket - nested containers not available"
fi

# Check SWE-bench installation
echo "🔍 Checking SWE-bench installation..."
python -c "import swebench; print(f'SWE-bench version: {swebench.__version__}')" || {
    echo "❌ SWE-bench not properly installed"
    exit 1
}

# Check validator installation
echo "🔍 Checking validator installation..."
python -c "from swe_bench_validator import SWEBenchValidator; print('✅ Validator available')" || {
    echo "❌ SWE-bench validator not properly installed"
    exit 1
}

# If no arguments provided, show help
if [ $# -eq 0 ]; then
    echo "📚 Available commands:"
    echo "  validate       - Run validation on data points"
    echo "  basic          - Run basic validation (no Docker)"
    echo "  lightweight    - Run lightweight validation (minimal Docker)"
    echo "  full           - Run full SWE-bench validation"
    echo ""
    echo "Examples:"
    echo "  docker run swe-bench-validator validate --instance astropy__astropy-11693"
    echo "  docker run swe-bench-validator basic --data-points-dir /data"
    echo ""
    python -m swe_bench_validator --help
    exit 0
fi

# Handle --help explicitly
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    python -m swe_bench_validator --help
    exit 0
fi

# Handle different validation modes
case "$1" in
    "validate"|"basic"|"lightweight"|"full")
        MODE="$1"
        shift
        echo "🚀 Running $MODE validation..."
        exec python -m swe_bench_validator --validation-mode "$MODE" "$@"
        ;;
    *)
        echo "🔧 Running custom command: $*"
        exec "$@"
        ;;
esac
