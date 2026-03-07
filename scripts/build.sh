#!/bin/bash
# Build script for secondbrain CLI using PyInstaller
# Produces a single executable binary

set -e

echo "🔨 Building secondbrain CLI executable..."

# Ensure we're in the project root
cd "$(dirname "$0")/.."

# Activate virtual environment if not already active
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Install PyInstaller if not already installed
pip install -q pyinstaller

# Clean previous builds
rm -rf dist/ build/ "*.spec"

# Build single executable
echo "📦 Creating single executable..."
pyinstaller --onefile \
    --name secondbrain \
    --add-data "src/secondbrain:secondbrain" \
    --hidden-import click \
    --hidden-import docling \
    --hidden-import pymongo \
    --hidden-import httpx \
    --hidden-import pydantic \
    --hidden-import pydantic_settings \
    --hidden-import rich \
    --hidden-import dotenv \
    --clean \
    src/secondbrain/cli/__init__.py

echo "✅ Build complete!"
echo "📍 Executable location: dist/secondbrain"
echo ""
echo "To test the executable:"
echo "  ./dist/secondbrain --help"
echo ""
echo "To install globally:"
echo "  sudo cp dist/secondbrain /usr/local/bin/"
