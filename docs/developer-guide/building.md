# Building & Distribution

Create distributable binaries and packages for SecondBrain.

## Building Options

### Install from Source

```bash
# Development installation
pip install -e ".[dev]"

# Production installation
pip install -e "."
```

### Build Wheel

```bash
# Build wheel distribution
python -m build --wheel

# Output: dist/secondbrain-0.1.0-py3-none-any.whl
```

### Build Source Distribution

```bash
# Build source distribution
python -m build --sdist

# Output: dist/secondbrain-0.1.0.tar.gz
```

### Build Both

```bash
# Build wheel and sdist
python -m build

# Output: dist/
#   secondbrain-0.1.0-py3-none-any.whl
#   secondbrain-0.1.0.tar.gz
```

## Installation Methods

### From PyPI

```bash
pip install secondbrain
```

### From Wheel

```bash
pip install dist/secondbrain-0.1.0-py3-none-any.whl
```

### From Source

```bash
pip install .
```

### Development Mode

```bash
pip install -e ".[dev]"
```

## Distribution Channels

### PyPI (Recommended)

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

### GitHub Releases

```bash
# Create GitHub release
gh release create v0.1.0 dist/*
```

## Build Configuration

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "secondbrain"
version = "0.1.0"
description = "Local document intelligence CLI"
requires-python = ">=3.11"
dependencies = [
    "click>=8.0.0",
    "pydantic>=2.0.0",
    "pymongo>=4.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
secondbrain = "secondbrain.cli:cli"
```

## Docker Distribution

```bash
# Build Docker image
docker build -t secondbrain:latest .

# Push to registry
docker push your-registry/secondbrain:latest
```

## Verification

### Check Package

```bash
# Verify wheel
python -m pip install --upgrade pip
pip install dist/secondbrain-0.1.0-py3-none-any.whl --force-reinstall

# Test installation
secondbrain --help
```

### Test Distribution

```bash
# Create test environment
python -m venv test-env
source test-env/bin/activate

# Install from distribution
pip install dist/secondbrain-0.1.0-py3-none-any.whl

# Run tests
pytest
```

## Release Checklist

- [ ] Update version in pyproject.toml
- [ ] Update CHANGELOG.md
- [ ] Run all tests
- [ ] Build distributions
- [ ] Test installation from wheel
- [ ] Upload to TestPyPI
- [ ] Test from TestPyPI
- [ ] Upload to PyPI
- [ ] Create GitHub release
- [ ] Update documentation

## Troubleshooting

### Build Failures

```bash
# Clean build artifacts
rm -rf dist/ build/ *.egg-info

# Rebuild
python -m build
```

### Dependency Issues

```bash
# Upgrade build tools
pip install --upgrade build twine setuptools wheel
```

## Next Steps

- [Development Setup](development.md) - Development workflow
- [Testing Guide](TESTING.md) - Test before release
