# Building Guide

Build and packaging guide for SecondBrain.

## Build System

### Setup Tools

```python
# pyproject.toml
[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"
```

### Install Build Tools

```bash
pip install build setuptools wheel
```

## Building

### Source Distribution

```bash
# Build source distribution
python -m build --sdist

# Output: dist/secondbrain-0.4.0.tar.gz
```

### Wheel Distribution

```bash
# Build wheel
python -m build --wheel

# Output: dist/secondbrain-0.4.0-py3-none-any.whl
```

### Complete Build

```bash
# Build both
python -m build

# Verify
twine check dist/*
```

## Packaging

### Package Structure

```
secondbrain/
├── pyproject.toml
├── README.md
├── LICENSE.md
├── src/
│   └── secondbrain/
│       ├── __init__.py
│       ├── core.py
│       └── ...
└── MANIFEST.in
```

### MANIFEST.in

```ini
include README.md
include LICENSE.md
include CHANGELOG.md
recursive-include secondbrain *.py *.json *.yaml
```

## Distribution

### PyPI Upload

```bash
# Install twine
pip install twine

# Upload to test PyPI
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

### Docker Image

```bash
# Build image
docker build -t secondbrain:latest .

# Push to registry
docker push secondbrain/secondbrain:latest
```

## CI/CD Build

### GitHub Actions

```yaml
name: Build

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install build tools
        run: pip install build
      
      - name: Build package
        run: python -m build
      
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: dist
          path: dist/
```

## Verification

### Install from Build

```bash
# Install wheel
pip install dist/secondbrain-0.4.0-py3-none-any.whl

# Test installation
secondbrain --version
```

### Test Distribution

```bash
# Create temp directory
mkdir /tmp/test-dist
cd /tmp/test-dist

# Create venv
python -m venv venv
source venv/bin/activate

# Install from dist
pip install /path/to/dist/secondbrain-0.4.0.tar.gz

# Run tests
pytest
```

## Release Process

### Version Bump

```bash
# Update version in pyproject.toml
# Then:

# Create release commit
git commit -am "release: v0.4.0"

# Create tag
git tag -a v0.4.0 -m "Release v0.4.0"

# Push
git push origin v0.4.0
```

### Changelog

```bash
# Generate changelog
github-changes -o your-org -r secondbrain --only-pulls --use-commit-body
```

## Artifacts

### Build Outputs

- `dist/secondbrain-0.4.0.tar.gz` - Source distribution
- `dist/secondbrain-0.4.0-py3-none-any.whl` - Wheel
- `build/` - Temporary build files

### Cleanup

```bash
# Clean build artifacts
rm -rf build/ dist/ *.egg-info

# Clean Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
```

## See Also

- [PyPI Packaging](https://packaging.python.org/)
- [Docker Guide](docker.md)
- [CI/CD](development.md)
