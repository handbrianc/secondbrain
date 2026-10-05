# AGENTS.md - Agent Coding Guidelines

**Last Updated:** 2026-09-06  
**Commit:** 80fd894

SecondBrain is a local document intelligence CLI for semantic search using Qdrant vector search (with SQLite for
conversation storage) and OpenAI-compatible embedding APIs.

**Stack:** Python 3.14+, Click, Pydantic 2, Qdrant, OpenAI-compatible API, Docker

---

## STRUCTURE

```
secondbrain/
├── src/secondbrain/       # Main package (48 files, 13 modules)
├── tests/                 # Test suite (20+ directories)
├── scripts/               # Build/deployment utilities (14 scripts)
├── docs/                  # MkDocs documentation
├── docker-compose.yml     # Production services
└── docker-compose.test.yml # Test services (Qdrant + Ollama)
```

---

## WHERE TO LOOK

| Task | Location | Notes |
| ------ | ---------- | ------- |
| CLI commands | `src/secondbrain/cli/__init__.py` | Entry point: `secondbrain.cli:main` |
| Core logic | `src/secondbrain/` | 13 submodules (storage, search, utils, etc.) |
| Tests | `tests/` | 20+ specialized test directories |
| Scripts | `scripts/` | Build, security, migration utilities |
| Docs | `docs/` | MkDocs structure (developer-guide, user-guide, etc.) |
| Config | `pyproject.toml` | Single source of truth for all tooling |

---

## CODE MAP

**Entry Points**:

- `main()` in `src/secondbrain/cli/__init__.py:39-42`
- `cli` Click group in `src/secondbrain/cli/__init__.py:18-32`

**Core Modules**:

- `storage/` - Qdrant vector storage + SQLite conversation storage (5 files)
- `utils/` - Circuit breaker, connections, tracing (8 files)
- `rag/` - LLM providers, pipeline (5 files)
- `document/` - Ingestion, chunking (4 files)
- `search/` - Semantic search (3 files)
- `conversation/` - Session management (3 files)
- `domain/` - Entities, value objects (4 files)

---

## CONVENTIONS

**Only deviations from standard Python CLI patterns:**

1. **Entry point in `__init__.py`**: `main()` in `src/secondbrain/cli/__init__.py` instead of dedicated `cli.py`
2. **No `__main__.py`**: Cannot run via `python -m secondbrain`
3. **Inline Python in shell scripts**: `scripts/generate-sbom.sh` contains 60+ lines of embedded Python

**Standard patterns followed:**

- `src/` organization ✓
- `pyproject.toml` as single config source ✓
- GitHub Actions CI/CD supported ✓
- Pre-commit hooks for quality ✓
- Docker Compose for services ✓

---

## ANTI-PATTERNS (THIS PROJECT)

**Explicitly forbidden:**

1. **Hard-coded credentials** - Use environment variables or `.env` files
2. **Inline Python in shell scripts** - Extract to separate `.py` modules
3. **Auto-installing dependencies in scripts** - Require virtual environment setup
4. **Relative paths in scripts** - Use absolute paths or Python orchestration
5. **Duplicate integration tests** - ✅ RESOLVED: Consolidated `tests/test_integration/`
   into `tests/integration/mocked/` (May 2026)

---

## UNIQUE STYLES

**Testing:**

- Parallel execution with `pytest-xdist` (`--dist=loadfile`)
- 120s timeout per test
- Extensive test markers: `integration`, `unit`, `slow`, `fast`, `qualitative`, `safety`, `factual`, `hallucination`
- Property-based testing with Hypothesis (100 examples, 500ms deadline)

**Security:**

- Comprehensive scanning: pip-audit, safety, bandit, SBOM generation
- Pre-commit hooks include security checks
- CI/CD automation supported (GitHub Actions, local workflows)

**Documentation:**

- MkDocs with comprehensive structure (api/, architecture/, developer-guide/, user-guide/)
- NumPy-style docstrings required
- Extensive examples in `docs/examples/`

---

## COMMANDS

```bash
# Development
pip install -e ".[dev]"
pre-commit install

# Quality checks
ruff check . && ruff format .
mypy .
pytest -m "not integration"  # Fast tests
pytest                         # All tests

# Security
./scripts/security_scan.sh all
./scripts/security_scan.sh audit
./scripts/security_scan.sh bandit

# Test environment
docker-compose -f docker-compose.test.yml up -d
pytest
```

---

## TECHNICAL DEBT

**High Priority:**

- **Inline Python** in `scripts/generate-sbom.sh` - ✅ RESOLVED: extracted to `scripts/sbom_converter.py` (SBOM conversion module)
- **Duplicate tests** - ✅ RESOLVED: Removed `tests/test_integration/` directory (consolidated into `tests/integration/mocked/`)

**No TODO or FIXME markers** remain in `src/` (the `element_type-migration` marker was completed in PR #114).

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE
grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant
  symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow.
  Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load
  it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->
