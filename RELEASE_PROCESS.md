# Release Process

This document describes the release process for SecondBrain.

## Overview

Releases are automated using the `scripts/release.sh` script. The process includes:

1. Version bumping
2. Changelog generation
3. Testing
4. Tagging
5. Publishing

## Prerequisites

- Python 3.11+
- Node.js (for some tools)
- Git
- Access to PyPI (for publishing)
- GitHub access (for releases)

## Release Steps

### 1. Prepare for Release

Ensure all work is complete and tested:

```bash
# Run all tests
pytest

# Run linting
ruff check .
ruff format .

# Type checking
mypy .

# Fix any issues before proceeding
```

### 2. Bump Version

Choose the appropriate version bump:

```bash
# Patch release (bug fixes only)
./scripts/release.sh bump patch

# Minor release (new features, backward compatible)
./scripts/release.sh bump minor

# Major release (breaking changes)
./scripts/release.sh bump major
```

This will:
- Update version in `__init__.py` and `pyproject.toml`
- Create git commit
- Create git tag

### 3. Generate Changelog

Automatically generate changelog from git history:

```bash
./scripts/release.sh changelog
```

Or manually edit `CHANGELOG.md` to add details.

### 4. Full Release Workflow

Run the complete release process:

```bash
./scripts/release.sh release patch
```

This will:
1. Check for uncommitted changes
2. Ensure you're on main branch
3. Pull latest changes
4. Bump version
5. Generate changelog
6. Run tests
7. Run linting
8. Push changes and tags

### 5. Create GitHub Release

After the script completes:

1. Go to [GitHub Releases](https://github.com/your-org/secondbrain/releases)
2. Click "Draft a new release"
3. Select the tag created by the script
4. Copy changelog entries to release notes
5. Publish release

### 6. Publish to PyPI

Build and publish to PyPI:

```bash
# Install build tools
pip install build twine

# Build distribution
python -m build

# Test upload (TestPyPI)
twine upload --repository testpypi dist/*

# Production upload
twine upload dist/*
```

### 7. Update Documentation

- Update version references in documentation
- Deploy updated documentation
- Announce release (if applicable)

## Version Selection

### Patch (x.x.1 → x.x.2)
- Bug fixes
- Documentation updates
- No API changes

### Minor (x.1.0 → x.2.0)
- New features
- Backward-compatible API additions
- Deprecation warnings

### Major (1.x.0 → 2.x.0)
- Breaking API changes
- Removed features
- Incompatible behavior changes

## Rollback Procedure

If a release has issues:

```bash
# Revert to previous version
git revert <commit-hash>
git tag -d v<version>
git push origin :refs/tags/v<version>

# Fix issues and re-release
```

## Release Checklist

- [ ] All tests passing
- [ ] Linting clean
- [ ] Type checking clean
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Version bumped
- [ ] Tag created
- [ ] GitHub release published
- [ ] PyPI package published
- [ ] Announcement sent (if applicable)

## Troubleshooting

### Tests Fail During Release

Abort the release and fix issues:

```bash
# Fix failing tests
# Then re-run release
./scripts/release.sh release patch
```

### Version Already Exists

```bash
# Delete existing tag
git tag -d v<version>
git push origin :refs/tags/v<version>

# Re-run bump
./scripts/release.sh bump <type>
```

### PyPI Upload Fails

```bash
# Check credentials
twine check dist/*

# Ensure package name is unique
# Check PyPI for existing packages
```

## Release Schedule

- **Patch releases**: As needed for critical fixes
- **Minor releases**: Monthly (typically first week)
- **Major releases**: Quarterly or as needed

## Contact

For release questions or issues:
- Open an issue on GitHub
- Contact maintainers
- Check [Contributing Guide](../CONTRIBUTING.md)
