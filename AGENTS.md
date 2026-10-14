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
├── src/secondbrain/       # Main package (101 files, 12 packages)
├── tests/                 # Test suite (20+ directories)
├── scripts/               # Build/deployment utilities (16: 10 sh + 6 py)
├── docs/                  # MkDocs documentation
├── docker-compose.yml     # Production services
└── docker-compose.test.yml # Test services (Qdrant + Ollama)
```

---

## WHERE TO LOOK

| Task | Location | Notes |
| ------ | ---------- | ------- |
| CLI commands | `src/secondbrain/cli/__init__.py` | Entry point: `secondbrain.cli:main` |
| Core logic | `src/secondbrain/` | 12 packages (storage, search, utils, etc.) |
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

- `storage/` - Qdrant vector storage + SQLite conversation storage (7 files)
- `utils/` - Circuit breaker, connections, tracing (15 files)
- `rag/` - LLM providers + pipeline modules (24 files)
- `document/` - Ingestion, chunking (14 files)
- `search/` - Semantic search (2 files)
- `conversation/` - Session management (4 files)
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
./scripts/libyear.sh all

# Test environment
docker-compose -f docker-compose.test.yml up -d
pytest
```

---

## TECHNICAL DEBT

**Resolved (2026-10):**

- **Inline Python** in `scripts/generate-sbom.sh` - ✅ RESOLVED: the script is now a bash wrapper
  delegating to `scripts/sbom_converter.py`
- **Duplicate tests** - ✅ RESOLVED: Removed `tests/test_integration/` directory (consolidated
  into `tests/integration/mocked/`)
- **RAG pipeline monoliths** - ✅ RESOLVED: the 4560-line `_mixins.py` was split into focused
  modules under `src/secondbrain/rag/pipeline/` (`_fallback_mixin`, `_structure_mixin`,
  `_routing_mixin`, `_text_quality`, `_leak_scrub`, `_streaming`, `_formatting_mixin`), and the
  2451-line `pipeline/__init__.py` was split into `_pipeline.py` + `_orchestration.py` behind a
  thin facade. `_iterative_query` (~1400 lines) remains the largest single function by design.

**Markers:** 0 TODO/FIXME/HACK/XXX/WORKAROUND markers in `src/` and `scripts/`. The former
`chunker.py:33` marker is now the `_LABEL_TO_ELEMENT_TYPE` dict; the only `XXX` grep hit is
`mktemp`'s required template in `scripts/install.sh`.

**Intentional non-adoption - strict complexity/arg-count ruff rules:** `C901`, `PLR0911`,
`PLR0912`, `PLR0913`, `PLR0915` are deliberately not enabled in `[tool.ruff]`. At the audit
threshold (>15 cyclomatic complexity) only two functions exceeded and were refactored; at ruff
defaults these rules flag 105 sites, dominated by `PLR0913` (>5 args), which conflicts with this
codebase's CLI/config surface. Complexity is enforced by periodic audit review instead.
Re-evaluate before adding new long-branch business logic.

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
