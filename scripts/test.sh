#!/bin/bash

# Test runner script for Journiv backend
# Usage: ./scripts/test.sh [OPTIONS]

set -e

# Default values
ENVIRONMENT="test"
COVERAGE=true
VERBOSE=false
MARKERS=""
PARALLEL=false
FAIL_FAST=false
HELP=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show help
show_help() {
    echo "Journiv Backend Test Runner"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -e, --env ENVIRONMENT    Set test environment (test|development) [default: test]"
    echo "  -c, --coverage          Enable coverage reporting [default: true]"
    echo "  -v, --verbose           Enable verbose output [default: false]"
    echo "  -m, --markers MARKERS   Run tests with specific markers (e.g., 'unit', 'integration')"
    echo "  -p, --parallel          Run tests in parallel [default: false]"
    echo "  -x, --fail-fast         Stop on first failure [default: false]"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                      # Run all tests with coverage"
    echo "  $0 --markers unit       # Run only unit tests"
    echo "  $0 --markers integration # Run only integration tests"
    echo "  $0 --markers 'unit and not slow' # Run unit tests excluding slow ones"
    echo "  $0 --parallel --fail-fast # Run tests in parallel, stop on first failure"
    echo "  $0 --no-coverage --verbose # Run tests without coverage, verbose output"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        --no-coverage)
            COVERAGE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -m|--markers)
            MARKERS="$2"
            shift 2
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        -x|--fail-fast)
            FAIL_FAST=true
            shift
            ;;
        -h|--help)
            HELP=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Show help if requested
if [ "$HELP" = true ]; then
    show_help
    exit 0
fi

# Validate environment
if [ "$ENVIRONMENT" != "test" ] && [ "$ENVIRONMENT" != "development" ]; then
    print_error "Invalid environment: $ENVIRONMENT. Must be 'test' or 'development'"
    exit 1
fi

uv sync --group test --locked

print_status "Starting Journiv backend tests..."
print_status "Environment: $ENVIRONMENT"
print_status "Coverage: $COVERAGE"
print_status "Verbose: $VERBOSE"
print_status "Markers: ${MARKERS:-'all'}"
print_status "Parallel: $PARALLEL"
print_status "Fail Fast: $FAIL_FAST"

# Set environment variables
export ENVIRONMENT=$ENVIRONMENT
export DATABASE_URL="sqlite:///:memory:"
export SECRET_KEY="test-secret-key-change-in-production"
export DEBUG=true
export LOG_LEVEL=WARNING

# Build pytest command
PYTEST_CMD="uv run pytest"

# Add test directory
PYTEST_CMD="$PYTEST_CMD tests/"

# Add markers if specified
if [ -n "$MARKERS" ]; then
    PYTEST_CMD="$PYTEST_CMD -m '$MARKERS'"
fi

# Add coverage if enabled
if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=app --cov-report=term-missing --cov-report=html:htmlcov --cov-report=xml:coverage.xml"
    print_status "Coverage reporting enabled"
fi

# Add verbose if enabled
if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

# Add parallel if enabled (requires pytest-xdist)
if [ "$PARALLEL" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -n auto"
    print_status "Parallel execution enabled (pytest-xdist)"
fi

# Add fail fast if enabled
if [ "$FAIL_FAST" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -x"
fi

# Add other options
PYTEST_CMD="$PYTEST_CMD --tb=short --strict-markers"

print_status "Running command: $PYTEST_CMD"

# Run tests
if eval $PYTEST_CMD; then
    print_success "All tests passed!"

    # Show coverage summary if enabled
    if [ "$COVERAGE" = true ]; then
        print_status "Coverage report generated in htmlcov/index.html"
        print_status "Coverage XML report generated in coverage.xml"
        print_status "Open coverage report: open htmlcov/index.html"
    fi

    exit 0
else
    print_error "Tests failed!"
    exit 1
fi
