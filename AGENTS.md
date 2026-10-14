# AGENTS.md - Agent Coding Guidelines

**Last Updated:** 2026-10-14  
**Commit:** 386ddc8

SecondBrain is a local document intelligence CLI for semantic search using Qdrant vector search (with SQLite for
conversation storage) and OpenAI-compatible embedding APIs.

**Stack:** Python 3.14+, Click, Pydantic 2, Qdrant, OpenAI-compatible API, Docker

---

## STRUCTURE

```
secondbrain/
├── src/secondbrain/       # Main package (102 files, 12 packages)
├── tests/                 # Test suite (23 directories)
├── scripts/               # Build/deployment utilities (16: 10 sh + 6 py)
├── docs/                  # MkDocs documentation
├── openspec/              # Capability specs; verification archived 2026-10 (55/55 implemented)
├── docker-compose.yml     # Production services
└── docker-compose.test.yml # Test services (Qdrant + Ollama)
```

---

## WHERE TO LOOK

| Task | Location | Notes |
| ------ | ---------- | ------- |
| CLI commands | `src/secondbrain/cli/__init__.py` | Entry point: `secondbrain.cli:main` |
| Core logic | `src/secondbrain/` | 12 packages (storage, search, utils, config, etc.) |
| Tests | `tests/` | 23 specialized test directories |
| Scripts | `scripts/` | Build, security, migration utilities |
| Docs | `docs/` | MkDocs structure (developer-guide, user-guide, etc.) |
| Specs | `openspec/` | Capability specs + archived change proposals (see `spec-compliance` skill) |
| Config | `pyproject.toml` | Single source of truth for all tooling |

---

## CODE MAP

**Entry Points**:

- `main()` in `src/secondbrain/cli/__init__.py:55-57`
- `cli` Click group in `src/secondbrain/cli/__init__.py:26-48`

**Core Modules**:

- `storage/` - Qdrant vector storage + SQLite conversation storage (7 files)
- `utils/` - Circuit breaker, connections, tracing (15 files)
- `rag/` - LLM providers + pipeline modules (24 files; split pipeline lives in `rag/pipeline/`)
- `document/` - Ingestion, chunking (14 files)
- `config/` - Typed settings per concern: chunking, embedding, llm, processing, qdrant, rag, resilience, sqlite (9 files)
- `embedding/` - Provider interfaces + OpenAI/mock providers (5 files)
- `search/` - Semantic search (2 files)
- `conversation/` - Session management (4 files)
- `domain/` - Entities, value objects (4 files)
- `logging/`, `management/` - Single-module placeholder packages
- `cli/` also carries the interactive chat surface: `chat.py` + `chat_helpers.py`

---

## CONVENTIONS

**Only deviations from standard Python CLI patterns:**

1. **Entry point in `__init__.py`**: `main()` in `src/secondbrain/cli/__init__.py` instead of dedicated `cli.py`
2. **No `__main__.py`**: Cannot run via `python -m secondbrain`

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

- Parallel execution with `pytest-xdist` (`-n auto --dist=loadfile`, 120s timeout per test)
- Extensive test markers (21 registered): `integration`, `unit`, `slow`, `fast`, `medium`, `chaos`, `qualitative`, `safety`, `factual`, `hallucination`, `robustness`, `llm_judge`, `performance`, `flaky`, `xdist_group`, ...
- Chaos tests are opt-in: default addopts carry `-m 'not chaos'`; a CLI `-m` overrides it (run `pytest -m chaos`)
- Coverage is intentionally NOT in addopts — it is a CI gate (`test-quality-gates.yml` supplies `--cov*` flags); pass `--cov` explicitly when needed
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
pytest -m "not integration"      # Fast tests (chaos still excluded via default addopts)
pytest -m "chaos or not chaos"   # Everything (CLI -m overrides the default 'not chaos')

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
  `_routing_mixin`, `_text_quality`, `_leak_scrub`, `_streaming`, `_formatting_mixin`, plus
  `_attributes` and `_constants`), and the 2451-line `pipeline/__init__.py` was split into
  `_pipeline.py` + `_orchestration.py` behind a thin 17-line facade. `_mixins.py` remains only
  as a 194-line compatibility shim re-exporting the historical surface. `_iterative_query`
  (~1400 lines, `_pipeline.py:92`) remains the largest single function by design.

**Markers:** 0 TODO/FIXME/HACK/XXX/WORKAROUND markers in `src/` and `scripts/`. The former
`chunker.py:33` marker is now the `_LABEL_TO_ELEMENT_TYPE` dict; the only `XXX` grep hit is
`mktemp`'s required template in `scripts/install.sh`.

**Intentional non-adoption - strict complexity/arg-count ruff rules:** `C901`, `PLR0911`,
`PLR0912`, `PLR0913`, `PLR0915` are deliberately not enabled in `[tool.ruff]`. At ruff
defaults these rules flag 99 sites (C901: 35, PLR0913: 30, PLR0912: 16, PLR0915: 13,
PLR0911: 5). C901 concentrates in the RAG pipeline / document-ingestor hot paths —
headlined by `_iterative_query` (complexity 167), `_derive_chapter_numbers` (66),
`_extract_chunk_and_embed_file` (34), `_process_parallel_with_progress` (33), and
`Orchestrator.chat` (31), with a long tail just over the default threshold (11-20);
`PLR0913` (>5 args) conflicts with this codebase's CLI/config surface. Complexity is
enforced by periodic audit review instead. Re-evaluate before adding new long-branch
business logic.

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
