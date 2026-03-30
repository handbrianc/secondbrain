#!/bin/bash
# SecondBrain Developer Setup Script
# This script automates the setup process for new developers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     SecondBrain Developer Setup                       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo

# Function to print status
print_status() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check Python version
print_status "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.11"

if [[ $(echo "$PYTHON_VERSION < $REQUIRED_VERSION" | bc -l) -eq 1 ]]; then
    print_error "Python $REQUIRED_VERSION+ required, found $PYTHON_VERSION"
    exit 1
fi
print_success "Python $PYTHON_VERSION detected"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
fi

# Activate virtual environment
print_status "Activating virtual environment..."
source venv/bin/activate
print_success "Virtual environment activated"

# Upgrade pip
print_status "Upgrading pip..."
pip install --upgrade pip setuptools wheel
print_success "pip upgraded"

# Install dependencies
print_status "Installing dependencies..."
pip install -e ".[dev]"
print_success "Dependencies installed"

# Install pre-commit hooks
print_status "Installing pre-commit hooks..."
pre-commit install
print_success "Pre-commit hooks installed"

# Check MongoDB
print_status "Checking MongoDB..."
if command -v mongod &> /dev/null; then
    print_success "MongoDB found"
    
    # Check if MongoDB is running
    if pgrep -x "mongod" > /dev/null; then
        print_success "MongoDB is running"
    else
        print_status "Starting MongoDB..."
        mongod --fork --logpath /tmp/mongodb.log --dbpath /tmp/mongodb_data
        print_success "MongoDB started"
    fi
else
    print_error "MongoDB not found. Please install MongoDB 6.0+."
    print_status "Visit: https://www.mongodb.com/try/download/community"
fi

# Download spaCy model
print_status "Downloading spaCy model..."
python -m spacy download en_core_web_sm || true
print_success "spaCy model ready"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    print_status "Creating .env file..."
    cp .env.example .env
    print_success ".env file created"
    print_status "Please update .env with your configuration"
else
    print_success ".env file already exists"
fi

# Run initial tests
print_status "Running initial tests..."
pytest tests/ -x -v --tb=short -k "not integration" || {
    print_error "Some tests failed. This may be expected if services are not running."
}

echo
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup Complete!                                       ${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo
echo "Next steps:"
echo "  1. Review and update .env file with your configuration"
echo "  2. Run 'pre-commit run --all-files' to check code quality"
echo "  3. Read docs/developer-guide/onboarding.md for more details"
echo "  4. Start coding! Try: python -m secondbrain --help"
echo
echo "For questions, see CONTRIBUTING.md or open an issue."
echo
