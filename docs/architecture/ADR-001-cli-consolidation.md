# Architecture Decision Record: CLI Consolidation

## Status

Accepted

## Date

2026-03-29

## Context

The SecondBrain project had a dual CLI architecture with two nearly identical CLI modules:

- `src/secondbrain/cli/` - Core CLI module
- `src/secondbrain_cli/cli/` - Duplicate CLI module

Both modules contained:
- Identical Click group definitions
- Duplicate command implementations
- Same entry points in pyproject.toml

This architecture caused:
- Confusion about which module to use
- Maintenance burden (changes needed in two places)
- Code duplication risk
- Violation of single responsibility principle

## Decision

Consolidate to a single CLI structure under `src/secondbrain/cli/`:

1. Remove `src/secondbrain_cli/` directory entirely
2. Update `pyproject.toml` entry point from `secondbrain_cli.cli:main` to `secondbrain.cli:main`
3. Preserve any unique features from `secondbrain_cli/` (e.g., `--memory-limit` option)
4. Update all imports across the codebase
5. Update tests to reference new structure

## Consequences

### Positive

- **Single source of truth**: One CLI module to maintain
- **Clearer structure**: Package structure matches import structure
- **Reduced confusion**: Developers know where CLI code lives
- **Easier testing**: Single code path to test
- **Better alignment**: Follows Python packaging best practices

### Negative

- **Breaking change**: Existing installations need reinstallation
- **Migration effort**: All imports updating from `secondbrain_cli` to `secondbrain.cli`
- **Potential regression risk**: Changes to consolidated code affect all functionality

### Neutral

- **Entry point name**: CLI command remains `secondbrain` (user-facing unchanged)
- **Backward compatibility**: No public API changes (internal reorganization only)

## Alternatives Considered

### Alternative 1: Keep Both Modules

**Pros**:
- No migration effort
- Backward compatible

**Cons**:
- Perpetuates architectural debt
- Ongoing maintenance burden
- Confusion continues

**Verdict**: Rejected - doesn't solve the problem

### Alternative 2: Merge into `secondbrain_cli`

**Pros**:
- Keeps "cli" in package name explicit

**Cons**:
- Less clean package structure
- `secondbrain_cli` suggests separate package
- Inconsistent with other modules

**Verdict**: Rejected - `secondbrain.cli` is cleaner

### Alternative 3: Create New Unified Module

**Pros**:
- Fresh start with best practices

**Cons**:
- More migration effort
- Unnecessary refactoring
- Risk of introducing new issues

**Verdict**: Rejected - incremental consolidation is safer

## Implementation Details

### Files Modified

1. `pyproject.toml` - Updated entry point
2. Removed `src/secondbrain_cli/` directory
3. Updated `src/secondbrain/cli/commands.py` - Added `--memory-limit` option
4. Updated all imports in tests and documentation

### Migration Steps

1. Backup existing installation
2. Uninstall: `pip uninstall secondbrain`
3. Remove old package: `rm -rf src/secondbrain_cli`
4. Install: `pip install -e .`
5. Verify: `secondbrain --version`

### Testing

- All existing CLI tests pass
- Manual verification of all commands
- Integration tests with MongoDB
- End-to-end ingestion and search workflows

## References

- [Python Packaging User Guide](https://packaging.python.org/)
- [Click Documentation](https://click.palletsprojects.com/)
- Issue: CLI Architecture Debt Tracking

## Notes

This decision aligns the project with top-tier Python CLI standards used by projects like Click, httpie, and Typer, which all use single, clear CLI entry points.
