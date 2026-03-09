# Building and Distribution

Guide to building single executables and distributing SecondBrain.

## Overview

SecondBrain can be distributed as:
- Python package (pip install)
- Single executable binary
- Docker container

## Building Single Executable

### Using PyInstaller

PyInstaller creates standalone executables for Windows, macOS, and Linux.

#### Installation

```bash
# Install PyInstaller
pip install pyinstaller

# Or with dev dependencies
pip install -e ".[dev]"
```

#### Basic Build

```bash
# Build for current platform
pyinstaller --onefile src/secondbrain/cli/__init__.py

# Output: dist/cli
```

#### Advanced Build Options

```bash
# Build with custom name
pyinstaller --onefile --name secondbrain src/secondbrain/cli/__init__.py

# Include data files
pyinstaller --onefile \
    --add-data "src/secondbrain/config/default.env:secondbrain/config" \
    src/secondbrain/cli/__init__.py

# Hide console window (Windows/macOS GUI)
pyinstaller --onefile --noconsole src/secondbrain/cli/__init__.py

# Add icon (Windows/macOS)
pyinstaller --onefile --icon=icon.ico src/secondbrain/cli/__init__.py
```

#### Build for Multiple Platforms

Use `pyinstaller` with Docker for cross-platform builds:

```dockerfile
# Dockerfile.pyinstaller
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install -e ".[dev]"
RUN pyinstaller --onefile src/secondbrain/cli/__init__.py

# Output: /app/dist/secondbrain
```

Build for different platforms:

```bash
# Linux
docker build -t secondbrain-linux -f Dockerfile.pyinstaller .
docker run --rm -v $(pwd)/dist:/app/dist secondbrain-linux

# macOS (using osx-cross)
docker run --rm -v $(pwd):/src osxcross/target/bin/pyinstaller \
    --onefile /src/src/secondbrain/cli/__init__.py

# Windows (using wine)
docker run --rm -v $(pwd):/src wine pyinstaller \
    --onefile /src/src/secondbrain/cli/__init__.py
```

### Build Configuration File

Create `secondbrain.spec` for advanced configuration:

```python
# secondbrain.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

a = Analysis(
    ['src/secondbrain/cli/__init__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/secondbrain/config', 'secondbrain/config'),
    ],
    hiddenimports=[
        'pymongo',
        'httpx',
        'pydantic',
        'rich',
        'click',
        'docling',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='secondbrain',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='secondbrain',
)
```

Build with spec file:

```bash
pyinstaller secondbrain.spec
```

## Docker Build

### Development Image

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies from pyproject.toml
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source code
COPY src/ ./src/

# Set entrypoint
ENTRYPOINT ["secondbrain"]
```

Build:

```bash
docker build -t secondbrain:latest .

# Run
docker run --rm -v $(pwd):/data secondbrain:latest --help
```

### Production Image

```dockerfile
# Dockerfile.production
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --user --no-cache-dir -e ".[dev]"

FROM python:3.12-slim

WORKDIR /app

# Copy installed packages
COPY --from=builder /root/.local /root/.local

# Copy application
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# Non-root user
RUN useradd -m secondbrain
USER secondbrain

ENTRYPOINT ["secondbrain"]
```

Build:

```bash
docker build -f Dockerfile.production -t secondbrain:prod .
```

## Distribution

### PyPI Package

#### Prepare for PyPI

```bash
# Install build tools
pip install build twine

# Build distribution
python -m build

# Output:
# dist/
#   secondbrain-0.1.0-py3-none-any.whl
#   secondbrain-0.1.0.tar.gz
```

#### Test on TestPyPI

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ secondbrain
```

#### Upload to PyPI

```bash
# Upload to PyPI
twine upload dist/*

# Install from PyPI
pip install secondbrain
```

#### pyproject.toml Configuration

```toml
[project]
name = "secondbrain"
version = "0.1.0"
description = "A local document intelligence CLI tool"
authors = [{name = "Your Name", email = "your.email@example.com"}]
license = {text = "MIT"}
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "click>=8.1.0",
    "pymongo>=4.6.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "rich>=14.0.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.4.0",
    "mypy>=1.8.0",
    "pytest>=8.0.0",
]

[project.scripts]
secondbrain = "secondbrain.cli:main"

[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"
```

### GitHub Releases

#### Create Release

```bash
# Tag release
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0

# Build binaries
pyinstaller --onefile --name secondbrain src/secondbrain/cli/__init__.py

# Create release artifacts
cp dist/secondbrain secondbrain-macos-arm64
# Repeat for other platforms

# Upload to GitHub Releases
gh release create v0.1.0 \
    secondbrain-macos-arm64 \
    secondbrain-linux-amd64 \
    secondbrain-windows-amd64.exe
```

#### GitHub Actions (Optional)

Note: Per project policy, GitHub Actions is prohibited. Use local builds instead.

## Installation Methods

### From Source

```bash
# Clone repository
git clone https://github.com/your-org/secondbrain.git
cd secondbrain

# Install in editable mode
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### From PyPI

```bash
# Latest release
pip install secondbrain

# Specific version
pip install secondbrain==0.1.0

# Pre-release
pip install secondbrain==0.2.0a1
```

### From Binary

```bash
# macOS (Apple Silicon)
curl -L https://github.com/your-org/secondbrain/releases/download/v0.1.0/secondbrain-macos-arm64 -o /usr/local/bin/secondbrain
chmod +x /usr/local/bin/secondbrain

# macOS (Intel)
curl -L https://github.com/your-org/secondbrain/releases/download/v0.1.0/secondbrain-macos-x64 -o /usr/local/bin/secondbrain
chmod +x /usr/local/bin/secondbrain

# Linux
curl -L https://github.com/your-org/secondbrain/releases/download/v0.1.0/secondbrain-linux-amd64 -o /usr/local/bin/secondbrain
chmod +x /usr/local/bin/secondbrain

# Windows
# Download secondbrain-windows-amd64.exe from releases
# Add to PATH or run directly
```

### From Docker

```bash
# Pull from Docker Hub
docker pull your-org/secondbrain:latest

# Run
docker run --rm -v $(pwd):/data your-org/secondbrain:latest --help
```

## Platform-Specific Instructions

### macOS

#### Install via Homebrew (if published)

```bash
brew install your-org/tap/secondbrain
```

#### Code Signing (for distribution)

```bash
# Sign the executable
codesign --sign - dist/secondbrain

# Notarize for macOS (requires Apple Developer account)
xcrun notarytool submit dist/secondbrain --apple-id ... --team-id ... --password ...
```

### Linux

#### AppImage

```bash
# Create AppImage
pip install appimagebuilder
appimage-builder --recipe AppImage.yml

# Distribute
secondbrain-x86_64.AppImage
```

#### Snap

```bash
# Create snap package
snapcraft

# Publish
snapcraft push secondbrain_0.1.0_amd64.snap --release stable
```

### Windows

#### NSIS Installer

```bash
# Install NSIS
choco install nsis

# Create installer
makensis secondbrain.nsis

# Output: secondbrain-installer.exe
```

#### MSIX

```bash
# Create MSIX package
python -m pip install msixsdk
# Follow Microsoft MSIX packaging guide
```

## Troubleshooting

### PyInstaller Issues

**Problem**: Missing modules in executable

**Solution**: Add to hidden imports in spec file:
```python
hiddenimports=[
    'pymongo',
    'httpx',
    # Add missing modules
]
```

**Problem**: Large executable size

**Solution**: Enable UPX compression:
```bash
pyinstaller --onefile --upx-dir=/path/to/upx src/secondbrain/cli/__init__.py
```

### Docker Build Issues

**Problem**: Build fails with memory error

**Solution**: Increase Docker memory limit:
```bash
docker build --build-arg BUILDKIT_STEP_LOG_MAX_SIZE=-1 -t secondbrain .
```

### Distribution Issues

**Problem**: Executable won't run on target system

**Solution**: 
1. Check glibc version compatibility
2. Use statically linked build (musl)
3. Provide Docker container as alternative

## Versioning

### Semantic Versioning

SecondBrain uses semantic versioning:

- **MAJOR** (0.x.y): Breaking changes
- **MINOR** (x.0.y): New features, backward-compatible
- **PATCH** (x.y.0): Bug fixes, backward-compatible

### Changelog

Update `do../developer-guide/index.mdCHANGELOG.md` for each release:

```markdown
## [0.2.0] - 2026-03-15

### Added
- Async search API
- JSON output format

### Changed
- Improved error messages

### Fixed
- Connection timeout handling
```

## Next Steps

- [Deployment Guide](./docker.md#production-deployment) - Production deployment
- [Configuration](./configuration.md) - Environment configuration
- [Contributing](./contributing.md) - How to contribute

## Related Documentation

- [Deployment Guide](./docker.md#production-deployment) - Production deployment
- [Configuration](./configuration.md) - Environment configuration
- [Contributing](./contributing.md) - How to contribute
