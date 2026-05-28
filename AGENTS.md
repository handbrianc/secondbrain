# AGENTS.md - Agent Coding Guidelines

**Last Updated:** 2026-05-03  
**Commit:** 80fd894

SecondBrain is a local document intelligence CLI for semantic search using MongoDB vector search and sentence-transformers.

**Stack:** Python 3.11+, Click, Pydantic 2, Motor, sentence-transformers, Docker

---

## STRUCTURE

```
secondbrain/
├── src/secondbrain/       # Main package (48 files, 13 modules)
├── tests/                 # Test suite (20+ directories)
├── scripts/               # Build/deployment utilities (9 scripts)
├── docs/                  # MkDocs documentation
├── docker-compose.yml     # Production services
└── docker-compose.test.yml # Test services (MongoDB + Ollama)
```

**Note**: Dual package structure - `src/secondbrain/` (core) + `src/secondbrain_cli/` (CLI, orphaned)

---

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
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
- `storage/` - MongoDB vector storage (5 files)
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
2. **Dual package structure**: `secondbrain_cli/` package exists but is orphaned/unused
3. **No `__main__.py`**: Cannot run via `python -m secondbrain`
4. **Inline Python in shell scripts**: `scripts/generate-sbom.sh` contains 60+ lines of embedded Python
5. **Pre-commit runs full test suite**: `pytest` with `always_run: true` (slow)
6. **Hard-coded credentials**: `scripts/init-mongo.js` contains `pwd: 'supersecretpassword123'` ⚠️

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
3. **Full test suite in pre-commit** - Use `pytest -m "not integration"` instead
4. **Auto-installing dependencies in scripts** - Require virtual environment setup
5. **Relative paths in scripts** - Use absolute paths or Python orchestration
6. **Duplicate integration tests** - `tests/integration/` and `tests/test_integration/` have overlapping content

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
- **Hard-coded password** in `scripts/init-mongo.js` - use env vars
- **Inline Python** in `scripts/generate-sbom.sh` - extract to `.py` module
- **Duplicate tests** in `tests/integration/` vs `tests/test_integration/`
- **Orphaned package** `src/secondbrain_cli/` - safe to remove

**No TODO/FIXME markers** - clean codebase with excellent hygiene.

### graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **secondbrain** (8400 symbols, 12799 relationships, 60 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/secondbrain/context` | Codebase overview, check index freshness |
| `gitnexus://repo/secondbrain/clusters` | All functional areas |
| `gitnexus://repo/secondbrain/processes` | All execution flows |
| `gitnexus://repo/secondbrain/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
