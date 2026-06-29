# Building & Distribution

Packaging and distributing SecondBrain as a release artifact.

## Package Metadata

Defined in `pyproject.toml`:

```toml
[project]
name = "secondbrain"
version = "0.4.0"
description = "A local document intelligence CLI tool for semantic search"
requires-python = ">=3.11"
authors = [
    {name = "Bishal Chand", email = "bishal.chand@gmail.com"}
]
license = {text = "MIT"}
```

## Build Backends

SecondBrain uses setuptools as the build backend:

```toml
[build-system]
requires = ["setuptools>=60.0.0", "wheel"]
build-backend = "setuptools.build_meta"
```

## Installing in Development Mode

For local development:

```bash
pip install -e .
```

Editable install links the package to the source directory.

## Dependency Groups

### Core

Runtime dependencies only:

```toml
dependencies = [
    "click>=8.4.1",
    "pymongo>=4.17.0",
    "motor>=3.0.0",
    ...
]
```

### Optional Dependencies

Grouped extras for specific use cases:

| Group | Purpose |
|-------|---------|
| `lint` | Ruff and MyPy |
| `test` | Pytest and testing utilities |
| `docs` | MkDocs and plugins |
| `security` | Bandit and Safety |
| `web` | FastAPI and Flask |
| `mutation` | Mutmut testing |
| `precommit` | Pre-commit hooks |
| `bundled` | All development tools |
| `dev` | Alias for bundled |
| `rag` | Local LLM inference |

## Creating a Distribution

### Wheel (Binary Package)

```bash
pip wheel . --wheel-dir dist/
```

Creates `dist/secondbrain-0.4.0-py3-none-any.whl`

### Source Distribution

```bash
python -m build --sdist
```

Creates `dist/secondbrain-0.4.0.tar.gz`

## Publishing to PyPI

### Prerequisites

```bash
pip install build twine
```

### Build Artifacts

```bash
python -m build
```

Artifacts appear in `dist/`.

### Upload

```bash
# Test PyPI (recommended first)
twine upload --repository testpypi dist/*

# Production PyPI
twine upload dist/*
```

Requires PyPI credentials in `~/.pypirc` or token authentication.

## Standalone Executable

Build a single-file executable using PyInstaller:

```bash
pip install -e ".[bundled]"
pyinstaller secondbrain.spec
```

The resulting executable is in `dist/`.

## Distribution Checklist

Before releasing a new version:

- [ ] Update version in `pyproject.toml`
- [ ] Update changelog in `CHANGELOG.md`
- [ ] Run full test suite: `pytest`
- [ ] Run type checker: `mypy src/`
- [ ] Run linter: `ruff check src/`
- [ ] Verify build artifacts: `python -m build`
- [ ] Test installation from distribution
- [ ] Tag release in git

## Versioning Scheme

SecondBrain uses semantic versioning (SemVer):

```
MAJOR.MINOR.PATCH
0.4.0
│ │ └─ Patch: Bug fixes
│ └─── Minor: New features, backward compatible
└───── Major: Breaking changes
```

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install build twine
          
      - name: Build
        run: python -m build
        
      - name: Publish
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: twine upload dist/*
```

## Distribution Formats Comparison

| Format | Pros | Cons |
|--------|------|------|
| Wheel (.whl) | Fast install, reproducible | Platform-specific wheels needed |
| Source (.tar.gz) | Universal | Compilation required |
| Executable | No Python needed | Large file, platform-specific |
| Docker image | Consistent environment | Container runtime required |