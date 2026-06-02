# Ollama Removal & OpenAI-Compatible API Migration - Implementation Plan

**Status**: Planning Complete  
**Impact**: HIGH - Breaking change requiring migration  
**Estimated Effort**: 4-6 hours (core changes) + 2-3 hours (tests/docs)

---

## Executive Summary

This plan details the complete removal of Ollama from SecondBrain and migration to a configurable OpenAI-compatible API backend. The existing `OpenAILLMProvider` implementation will become the default, with support for any OpenAI-compatible endpoint (OpenAI, Azure, Groq, Anthropic Claude API, self-hosted vLLM, etc.).

**Key Decision**: Use OpenAI SDK's `base_url` parameter for maximum compatibility with OpenAI-compatible APIs.

---

## Design Decisions

### 1. Default Provider
**Decision**: `llm_provider` default changes from `"ollama"` to `"openai"`

**Rationale**:
- OpenAI API is more reliable for production use
- Already has a working implementation (`OpenAILLMProvider`)
- OpenAI-compatible APIs cover 95% of use cases
- Users can still use Anthropic via existing provider

### 2. Configuration Schema
**Decision**: Use `openai_*` prefix for OpenAI-compatible API configuration

**New Fields**:
```python
llm_provider: str = "openai"  # Changed default
openai_base_url: str | None = None  # Optional, defaults to OpenAI
openai_api_key: str | None = None  # Optional for self-hosted endpoints
openai_model: str = "gpt-4o-mini"  # Default model
```

**Rationale**:
- Clear namespace for OpenAI-specific settings
- Aligns with existing `SECONDBRAIN_OPENAI_API_KEY` env var
- `openai_base_url` enables any OpenAI-compatible endpoint
- Optional API key supports self-hosted endpoints without auth

### 3. Model Configuration
**Decision**: Keep generic `llm_model` field, alias to provider-specific model

**Mapping**:
- `llm_model` → used by all providers (backward compatible)
- `openai_model` → optional override for OpenAI provider
- If both set, provider-specific takes precedence

**Rationale**:
- Maintains backward compatibility
- Allows provider-specific model naming
- Factory layer handles mapping transparently

### 4. API Key Handling
**Decision**: API key optional (for self-hosted endpoints without auth)

**Priority Order**:
1. Constructor parameter
2. `SECONDBRAIN_OPENAI_API_KEY` env var
3. None (for endpoints without auth)

**Rationale**:
- Supports self-hosted vLLM, LM Studio, etc.
- Maintains security for cloud APIs
- Follows existing OpenAI provider pattern

### 5. Backward Compatibility
**Decision**: No migration path for Ollama configs (breaking change)

**Migration Required**:
- Users must update `llm_provider` from "ollama" to "openai"
- Users must set `SECONDBRAIN_OPENAI_API_KEY` for OpenAI
- Self-hosted users set `openai_base_url` and optionally `openai_api_key`

**Rationale**:
- Ollama removal is intentional breaking change
- Migration guide provided (see Section 12)
- Clear error messages guide users

---

## Impact Analysis

### Symbols Affected (Direct - d=1)

| Symbol | File | Impact |
|--------|------|--------|
| `OllamaLLMProvider` | `src/secondbrain/rag/providers/ollama.py` | DELETE |
| `create_ollama()` | `src/secondbrain/rag/providers/factory.py:66-92` | DELETE |
| `_get_default_ollama_host()` | `src/secondbrain/config/__init__.py:82-94` | DELETE |
| `ollama_host` config field | `src/secondbrain/config/__init__.py:199-201` | DELETE |
| `OllamaLLMProvider` import in CLI | `src/secondbrain/cli/commands.py:573` | UPDATE |
| Ollama health check | `src/secondbrain/cli/commands.py:504-515` | UPDATE |

### Execution Flows Affected

1. **Chat Flow** (`proc_0_chat`, `proc_34_chat`, `proc_70_chat`, `proc_71_chat`, `proc_72_chat`, `proc_127_chat`)
   - Currently uses `OllamaLLMProvider` directly
   - Must use `LLMProviderFactory.create_from_config()` instead

2. **Provider Creation** (`proc_166_create_ollama`)
   - Currently creates Ollama provider
   - Will create based on `config.llm_provider`

### Risk Assessment

| Component | Risk Level | Mitigation |
|-----------|-----------|------------|
| Provider Factory | MEDIUM | Update all provider creation paths |
| CLI Commands | MEDIUM | Replace direct Ollama instantiation |
| Tests | HIGH | Comprehensive test updates required |
| Documentation | MEDIUM | Systematic update of all docs |
| Docker Services | LOW | Remove Ollama service definition |
| Dependencies | LOW | Remove ollama package |

**Overall Risk**: **MEDIUM-HIGH**

---

## Implementation Phases

### PHASE 1: ANALYSIS ✅ COMPLETE

**Status**: Completed via GitNexus exploration

**Findings**:
- 38 files reference "ollama"
- 3 core Ollama-specific files exist
- Factory pattern already supports multiple providers
- OpenAI provider already implemented

---

### PHASE 2: DESIGN ✅ COMPLETE

**Status**: Design decisions finalized above

**Deliverables**:
- Configuration schema defined
- Provider interface verified (already compatible)
- Migration strategy documented

---

### PHASE 3: CORE CODE CHANGES

#### Task 3.1: Remove Ollama Provider
**Files to Modify**:
1. **DELETE**: `src/secondbrain/rag/providers/ollama.py` (250 lines)
2. **UPDATE**: `src/secondbrain/rag/providers/__init__.py`
   - Remove `OllamaLLMProvider` from `__all__`
   - Remove import statement
3. **UPDATE**: `src/secondbrain/rag/__init__.py`
   - Remove Ollama exports if present

**Expected Changes**: ~10 lines removed from exports

#### Task 3.2: Update Factory
**File**: `src/secondbrain/rag/providers/factory.py`

**Changes**:
1. Delete `create_ollama()` method (lines 66-92)
2. Remove Ollama case from `create_from_config()` (lines 32-40)
3. Update error message in ValueError (line 62)
   - From: "Supported providers: ollama, openai, anthropic"
   - To: "Supported providers: openai, anthropic"

**Expected Changes**: ~30 lines removed

#### Task 3.3: Update Configuration
**File**: `src/secondbrain/config/__init__.py`

**Changes**:
1. Delete `_get_default_ollama_host()` function (lines 82-94)
2. Update `llm_provider` Field default (line 195-198)
   - From: `default="ollama"`
   - To: `default="openai"`
3. Delete `ollama_host` Field (lines 199-201)
4. Add new OpenAI-compatible API fields after `llm_provider`:
   ```python
   openai_base_url: str | None = Field(
       default=None,
       description="OpenAI-compatible API base URL (optional, defaults to OpenAI). Use for self-hosted endpoints like vLLM, LM Studio, Azure OpenAI, Groq, etc.",
   )
   openai_api_key: str | None = Field(
       default=None,
       description="OpenAI-compatible API key (optional for self-hosted endpoints without auth). Defaults to SECONDBRAIN_OPENAI_API_KEY env var.",
   )
   ```

**Expected Changes**: +15 lines, -25 lines (net -10 lines)

#### Task 3.4: Update OpenAI Provider
**File**: `src/secondbrain/rag/providers/openai.py`

**Changes**:
1. Update `__init__()` to accept `base_url` and `api_key` parameters
2. Initialize client with `base_url` if provided:
   ```python
   self._client = OpenAI(
       api_key=self._api_key,
       base_url=self._base_url,  # Optional
       timeout=httpx.Timeout(timeout),
   )
   ```
3. Store `base_url` as attribute

**Expected Changes**: +20 lines

---

### PHASE 4: CLI UPDATES

#### Task 4.1: Update Chat Command
**File**: `src/secondbrain/cli/commands.py`

**Changes**:
1. **Lines 504-515**: Update health check
   - Remove Ollama-specific health check
   - Add generic provider health check using factory
   - Update messages to reflect configurable provider

2. **Line 573**: Update import
   - From: `from secondbrain.rag.providers import OllamaLLMProvider`
   - To: `from secondbrain.rag.providers import LLMProviderFactory`

3. **Lines 594-597**: Update provider instantiation
   - From: Direct `OllamaLLMProvider()` instantiation
   - To: `LLMProviderFactory.create_from_config(config)`

4. **Line 595**: Update model selection
   - Use `cfg.llm_model` (factory handles provider-specific mapping)

**Expected Changes**: ~30 lines modified

#### Task 4.2: Update Health Command
**File**: `src/secondbrain/cli/commands.py`

**Changes**:
1. Add provider-agnostic health check
2. Check MongoDB, embedding service, and LLM provider
3. Display current provider configuration

**Expected Changes**: ~20 lines

---

### PHASE 5: INFRASTRUCTURE CHANGES

#### Task 5.1: Remove Ollama Docker Service
**File**: `docker-compose.test.yml`

**Changes**:
1. Delete lines 28-49 (ollama service definition)
2. Delete `ollama_data` volume (line 55)
3. Update comment on lines 2-3 (remove Ollama memory requirements)
4. Update health checks that depend on Ollama (if any)

**Expected Changes**: -25 lines

#### Task 5.2: Remove Ollama Scripts
**Files to DELETE**:
1. `scripts/ollama-startup.sh` (entire file)

**Files to UPDATE**:
1. `scripts/start_test_services.sh`
   - Remove Ollama startup commands
   - Update service list comments
2. `scripts/stop_test_services.sh`
   - Remove Ollama stop commands
3. `scripts/run_qualitative_tests.sh`
   - Remove Ollama availability checks

**Expected Changes**: -50 lines across 3 files

---

### PHASE 6: DEPENDENCY CHANGES

#### Task 6.1: Update pyproject.toml
**File**: `pyproject.toml`

**Changes**:
1. **Line 37**: Remove `"ollama>=0.1.0",` from dependencies
2. Verify `openai>=2.38.0` is present (line 38) - already there

**Expected Changes**: -1 line

#### Task 6.2: Update requirements.in
**File**: `requirements.in`

**Changes**:
1. Remove `ollama>=0.1.0` (line 18)

**Expected Changes**: -1 line

#### Task 6.3: Update requirements.txt
**File**: `requirements.txt`

**Changes**:
1. Remove all `ollama==0.6.2` entries (lines 90, 162, 218)
2. Run `pip-compile` to regenerate if needed

**Expected Changes**: -3 lines

---

### PHASE 7: TEST UPDATES

#### Task 7.1: Delete Ollama Tests
**Files to DELETE**:
1. `tests/test_rag/test_ollama_provider.py` (entire file, ~200 lines)

#### Task 7.2: Update Factory Tests
**File**: `tests/test_rag/test_factory.py`

**Changes**:
1. Remove `test_create_ollama_default()` (lines 21-28)
2. Remove `test_create_ollama_custom()` (lines 30-43)
3. Update `TestLLMProviderFactory` class docstring
4. Add tests for OpenAI provider creation
5. Add tests for Anthropic provider creation

**Expected Changes**: -30 lines, +20 lines (net -10 lines)

#### Task 7.3: Update Integration Tests
**File**: `tests/test_rag/test_integration.py`

**Changes**:
1. Remove `ollama_provider` fixture (lines 26-32)
2. Remove `test_rag_pipeline_with_real_ollama()` (lines 185-221)
3. Add `openai_provider` fixture with mocked OpenAI
4. Add `test_rag_pipeline_with_openai()` using mocked provider

**Expected Changes**: -40 lines, +30 lines (net -10 lines)

#### Task 7.4: Update Config Tests
**File**: `tests/test_config/test_config.py`

**Changes**:
1. Remove `TestGetDefaultOllamaHost` class (lines 420-454)
2. Remove `test_get_default_ollama_host_macos()` (lines 421-430)
3. Remove `test_get_default_ollama_host_linux()` (lines 433-442)
4. Remove `test_get_default_ollama_host_windows()` (lines 445-454)
5. Add tests for `openai_base_url` field
6. Add tests for `openai_api_key` field
7. Update `test_llm_provider_default()` to expect "openai"

**Expected Changes**: -40 lines, +25 lines (net -15 lines)

#### Task 7.5: Update Test Environment
**File**: `.env.test`

**Changes**:
1. Delete lines 20-30 (Ollama host configuration section)
2. Add OpenAI-compatible API section:
   ```ini
   # ============================================================================
   # OpenAI-Compatible API Test Configuration
   # ============================================================================
   # For testing, use mocked endpoint or set actual API key
   # SECONDBRAIN_LLM_PROVIDER=openai
   # SECONDBRAIN_OPENAI_BASE_URL=http://localhost:8080/v1  # Self-hosted
   # SECONDBRAIN_OPENAI_API_KEY=test-key-for-mocked-api
   # SECONDBRAIN_OPENAI_MODEL=gpt-4o-mini
   ```

**Expected Changes**: -10 lines, +8 lines (net -2 lines)

#### Task 7.6: Update Provider Switching Tests
**File**: `tests/test_provider_switching.py`

**Changes**:
1. Remove `test_ollama_provider_selection()` (lines 63-78)
2. Update `TestProviderSwitching` class to test OpenAI/Anthropic only
3. Add tests for provider switching between OpenAI and Anthropic

**Expected Changes**: -20 lines, +15 lines (net -5 lines)

#### Task 7.7: Update Integration Conftest
**File**: `tests/integration/conftest.py`

**Changes**:
1. Remove Ollama-specific setup (if any)
2. Update comments to reflect OpenAI-compatible API

**Expected Changes**: ~5 lines

#### Task 7.8: Update Mocked Integration Conftest
**File**: `tests/integration/mocked/conftest.py`

**Changes**:
1. Remove Ollama host save/restore (lines 131-141, 176-179)
2. Update provider mocking to use OpenAI mock

**Expected Changes**: -15 lines

#### Task 7.9: Update Example Tests Conftest
**File**: `tests/test_examples/conftest.py`

**Changes**:
1. Remove Ollama env setup (line 83)
2. Update to use OpenAI provider in examples

**Expected Changes**: -5 lines

#### Task 7.10: Update Qualitative Tests
**File**: `tests/test_qualitative/test_llm_as_judge.py`

**Changes**:
1. Remove Ollama availability checks (lines 17, 29-32, 130)
2. Update to use mocked OpenAI provider
3. Update fixture setup to use OpenAI provider

**Expected Changes**: -10 lines, +5 lines (net -5 lines)

#### Task 7.11: Update RAG Conversation Tests
**File**: `tests/test_rag/test_conversation.py`

**Changes**:
1. Check for Ollama references
2. Update to use factory pattern or mocked OpenAI

**Expected Changes**: ~5 lines

#### Task 7.12: Update RAG Pipeline Error Handling Tests
**File**: `tests/test_rag/test_pipeline_error_handling.py`

**Changes**:
1. Check for Ollama references
2. Update error handling tests for OpenAI provider

**Expected Changes**: ~5 lines

---

### PHASE 8: DOCUMENTATION UPDATES

#### Task 8.1: Update Dependencies Doc
**File**: `docs/getting-started/DEPENDENCIES.md`

**Changes**:
1. Remove Ollama dependency section (~15 lines)
2. Add OpenAI-compatible API requirements:
   - OpenAI API key (for OpenAI)
   - Optional: Self-hosted endpoint setup
   - Supported providers list

**Expected Changes**: -15 lines, +20 lines

#### Task 8.2: Update RAG Quickstart
**File**: `docs/getting-started/rag-quickstart.md`

**Changes**:
1. Replace Ollama setup with OpenAI setup
2. Update model configuration instructions
3. Add API key setup guide
4. Add self-hosted endpoint examples

**Expected Changes**: -20 lines, +30 lines

#### Task 8.3: Update Conversational Q&A Doc
**File**: `docs/user-guide/conversational-qa.md`

**Changes**:
1. Remove Ollama installation instructions
2. Add API configuration guide
3. Update examples to use OpenAI provider
4. Add self-hosted endpoint section

**Expected Changes**: -15 lines, +25 lines

#### Task 8.4: Update Testing Doc
**File**: `docs/developer-guide/TESTING.md`

**Changes**:
1. Remove Ollama test setup section
2. Update test environment variables
3. Add OpenAI API key setup for tests
4. Update docker-compose test instructions

**Expected Changes**: -20 lines, +15 lines

#### Task 8.5: Update Configuration Doc
**File**: `docs/getting-started/configuration.md`

**Changes**:
1. Remove `SECONDBRAIN_OLLAMA_HOST` documentation
2. Add OpenAI-compatible API configuration options:
   - `SECONDBRAIN_LLM_PROVIDER`
   - `SECONDBRAIN_OPENAI_BASE_URL`
   - `SECONDBRAIN_OPENAI_API_KEY`
   - `SECONDBRAIN_OPENAI_MODEL`
3. Add provider comparison table
4. Add self-hosted endpoint examples

**Expected Changes**: -10 lines, +40 lines

#### Task 8.6: Update README
**File**: `README.md`

**Changes**:
1. Remove Ollama reference (line 198)
2. Add OpenAI setup in quick start
3. Update features list if needed
4. Add API key setup note

**Expected Changes**: -5 lines, +10 lines

#### Task 8.7: Update Installation Doc
**File**: `docs/getting-started/installation.md`

**Changes**:
1. Remove Ollama installation steps
2. Add API key setup instructions
3. Add self-hosted endpoint setup guide

**Expected Changes**: -20 lines, +25 lines

#### Task 8.8: Update Troubleshooting Doc
**File**: `docs/getting-started/troubleshooting.md`

**Changes**:
1. Remove Ollama troubleshooting section
2. Add API connectivity troubleshooting
3. Add authentication error guide
4. Add self-hosted endpoint debugging

**Expected Changes**: -15 lines, +20 lines

#### Task 8.9: Update Architecture Docs
**Files**: `docs/architecture/*.md`

**Changes**:
1. Update diagrams to remove Ollama
2. Update provider architecture docs
3. Update data flow diagrams

**Expected Changes**: Varies by file

**Files to Check**:
- `docs/architecture/index.md`
- `docs/architecture/rag-pipeline.md`
- `docs/architecture/providers.md` (if exists)

---

### PHASE 9: ENVIRONMENT FILES

#### Task 9.1: Update .env.example
**File**: `.env.example`

**Changes**:
1. Remove Ollama host lines (20-21)
2. Add OpenAI-compatible API configuration:
   ```ini
   # ============================================================================
   # LLM Provider Configuration
   # ============================================================================
   # Choose provider: openai, anthropic
   # SECONDBRAIN_LLM_PROVIDER=openai
   
   # OpenAI-compatible API configuration
   # SECONDBRAIN_OPENAI_BASE_URL=https://api.openai.com/v1  # Optional (default: OpenAI)
   # SECONDBRAIN_OPENAI_API_KEY=your-api-key-here  # Required for OpenAI
   # SECONDBRAIN_OPENAI_MODEL=gpt-4o-mini  # Default model
   
   # For self-hosted endpoints (vLLM, LM Studio, etc.):
   # SECONDBRAIN_OPENAI_BASE_URL=http://localhost:8080/v1
   # SECONDBRAIN_OPENAI_API_KEY=  # Leave empty if no auth
   ```

**Expected Changes**: -2 lines, +15 lines

#### Task 9.2: Update .env.test
**Already handled in Task 7.5**

---

### PHASE 10: VERIFICATION

#### Task 10.1: Run Unit Tests
**Command**: `pytest -m "not integration" -v`

**Expected**: All unit tests pass

#### Task 10.2: Run Integration Tests (Mocked)
**Command**: `pytest -m integration -v`

**Expected**: All mocked integration tests pass

#### Task 10.3: Verify CLI Commands
**Commands to Test**:
```bash
secondbrain health
secondbrain --help
secondbrain chat --help
```

**Expected**: No errors, proper help text

#### Task 10.4: Verify Provider Factory
**Test**: Create providers via factory with different configs

**Expected**: All providers create successfully

#### Task 10.5: Run Security Scan
**Command**: `./scripts/security_scan.sh all`

**Expected**: No new vulnerabilities introduced

#### Task 10.6: Run Type Checking
**Command**: `mypy .`

**Expected**: No type errors

#### Task 10.7: Run Linting
**Command**: `ruff check . && ruff format .`

**Expected**: No linting errors

---

### PHASE 11: MIGRATION GUIDE

#### Task 11.1: Create Migration Guide
**File**: `docs/MIGRATION_OLLAMA_TO_OPENAI.md` (new file)

**Content**:
1. **Overview**: What changed and why
2. **Breaking Changes**: List of removed features
3. **Migration Steps**:
   - Update `llm_provider` to "openai"
   - Set `SECONDBRAIN_OPENAI_API_KEY`
   - Optional: Configure `openai_base_url` for self-hosted
4. **Provider Comparison**: Ollama vs OpenAI vs Self-hosted
5. **Troubleshooting**: Common migration issues
6. **Examples**: Configuration examples for different use cases

**Use Cases to Cover**:
- OpenAI API (default)
- Azure OpenAI
- Groq
- Anthropic Claude API
- Self-hosted vLLM
- Self-hosted LM Studio
- Self-hosted Ollama (via OpenAI-compatible endpoint)

---

## Parallel Execution Opportunities

### Can Run in Parallel (Independent):

1. **Core Code Changes** (Phase 3) + **Infrastructure Changes** (Phase 5)
   - No dependencies between them
   - Different teams can work simultaneously

2. **Test Updates** (Phase 7) can start after Phase 3 completes
   - Tests depend on code changes

3. **Documentation Updates** (Phase 8) can run in parallel with Tests
   - Docs don't depend on test updates
   - Can be done by technical writer team

4. **Environment Files** (Phase 9) can run with Documentation
   - Simple file updates

### Must Run Sequentially:

1. **Phase 3** (Core) → **Phase 4** (CLI)
   - CLI depends on factory updates

2. **Phase 3** (Core) → **Phase 7** (Tests)
   - Tests depend on code structure

3. **Phase 7** (Tests) → **Phase 10** (Verification)
   - Verification runs the tests

---

## Risk Mitigation

### High-Risk Areas:

1. **CLI Health Check** (Task 4.1)
   - **Risk**: Breaking existing health check functionality
   - **Mitigation**: Test all health check modes thoroughly
   - **Rollback**: Keep Ollama provider temporarily

2. **Provider Factory** (Task 3.2)
   - **Risk**: Breaking all provider creation
   - **Mitigation**: Comprehensive unit tests for factory
   - **Rollback**: Factory is additive, not destructive

3. **Test Suite** (Phase 7)
   - **Risk**: Missing test coverage after updates
   - **Mitigation**: Maintain test count, verify coverage %
   - **Rollback**: Tests are version-controlled

### Rollback Plan:

1. **Quick Rollback**: Revert git commit, re-install ollama package
2. **Partial Rollback**: Keep OpenAI provider, re-add Ollama provider
3. **Migration Delay**: Delay docs updates, ship code first

---

## Success Criteria

### Functional:
- [ ] Ollama provider completely removed
- [ ] OpenAI provider works as default
- [ ] Anthropic provider still works
- [ ] Self-hosted OpenAI-compatible endpoints work
- [ ] CLI commands function correctly
- [ ] Health checks work for all providers

### Testing:
- [ ] All unit tests pass (>75% coverage maintained)
- [ ] All integration tests pass (mocked)
- [ ] No test coverage regression
- [ ] Type checking passes (mypy)
- [ ] Linting passes (ruff)

### Documentation:
- [ ] All Ollama references removed from docs
- [ ] OpenAI-compatible API guide complete
- [ ] Migration guide published
- [ ] Examples updated

### Dependencies:
- [ ] ollama package removed from all dependency files
- [ ] No orphaned dependencies
- [ ] requirements.txt regenerated

### Infrastructure:
- [ ] Ollama Docker service removed
- [ ] Ollama scripts removed
- [ ] Test services start successfully

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Analysis | ✅ Complete | None |
| Phase 2: Design | ✅ Complete | Phase 1 |
| Phase 3: Core Code | 1-2 hours | Phase 2 |
| Phase 4: CLI | 30 min | Phase 3 |
| Phase 5: Infrastructure | 30 min | None (parallel) |
| Phase 6: Dependencies | 15 min | None (parallel) |
| Phase 7: Tests | 2-3 hours | Phase 3 |
| Phase 8: Documentation | 2-3 hours | None (parallel with 7) |
| Phase 9: Environment | 15 min | None (parallel with 8) |
| Phase 10: Verification | 1 hour | Phase 7, 8 |
| Phase 11: Migration Guide | 1 hour | Phase 3, 8 |

**Total**: 8-12 hours (can be parallelized to 4-6 hours)

---

## Delegated Task Breakdown

### Delegate to Implementation Agent:

**Task Bundle A: Core Implementation** (Phase 3 + 4 + 6)
- Remove Ollama provider
- Update factory
- Update configuration
- Update CLI commands
- Remove dependencies

**Task Bundle B: Infrastructure & Tests** (Phase 5 + 7)
- Remove Docker Ollama service
- Remove Ollama scripts
- Update all test files
- Update test fixtures

**Task Bundle C: Documentation** (Phase 8 + 9 + 11)
- Update all documentation files
- Update environment file templates
- Create migration guide

**Task Bundle D: Verification** (Phase 10)
- Run test suite
- Verify CLI commands
- Run quality checks (mypy, ruff, security)

---

## Notes for Implementation Agent

1. **Order of Operations**:
   - Start with Phase 3 (Core) - this is the foundation
   - Then Phase 4 (CLI) - depends on Core
   - Then Phase 7 (Tests) - depends on Core + CLI
   - Run Phase 5, 6, 8, 9 in parallel if possible

2. **Testing Strategy**:
   - Run `pytest -m "not integration"` after Phase 3+4
   - Run full test suite after Phase 7
   - Use `pytest -x` to fail fast on errors

3. **Git Strategy**:
   - Consider atomic commits per phase
   - Or single large commit with clear message
   - Run `gitnexus_detect_changes()` before committing

4. **Error Handling**:
   - If tests fail, check if it's expected (test updates needed)
   - If code errors, check imports and factory logic
   - Use `gitnexus_impact()` before major changes

5. **Quality Gates**:
   - Coverage must stay >= 75%
   - No mypy errors
   - No ruff errors
   - Security scan must pass

---

## Appendix: File List Summary

### Files to DELETE (7 files):
1. `src/secondbrain/rag/providers/ollama.py`
2. `tests/test_rag/test_ollama_provider.py`
3. `scripts/ollama-startup.sh`
4. `docs/architecture/ollama-architecture.md` (if exists)
5. `docs/getting-started/ollama-setup.md` (if exists)

### Files to MODIFY (38 files):
**Core Code (4 files)**:
- `src/secondbrain/rag/providers/__init__.py`
- `src/secondbrain/rag/providers/factory.py`
- `src/secondbrain/rag/providers/openai.py`
- `src/secondbrain/config/__init__.py`

**CLI (1 file)**:
- `src/secondbrain/cli/commands.py`

**Infrastructure (4 files)**:
- `docker-compose.test.yml`
- `scripts/start_test_services.sh`
- `scripts/stop_test_services.sh`
- `scripts/run_qualitative_tests.sh`

**Dependencies (3 files)**:
- `pyproject.toml`
- `requirements.in`
- `requirements.txt`

**Tests (12 files)**:
- `tests/test_rag/test_factory.py`
- `tests/test_rag/test_integration.py`
- `tests/test_config/test_config.py`
- `tests/test_provider_switching.py`
- `tests/integration/conftest.py`
- `tests/integration/mocked/conftest.py`
- `tests/test_examples/conftest.py`
- `tests/test_qualitative/test_llm_as_judge.py`
- `tests/test_rag/test_conversation.py`
- `tests/test_rag/test_pipeline_error_handling.py`
- `.env.test`

**Documentation (10 files)**:
- `docs/getting-started/DEPENDENCIES.md`
- `docs/getting-started/rag-quickstart.md`
- `docs/user-guide/conversational-qa.md`
- `docs/developer-guide/TESTING.md`
- `docs/getting-started/configuration.md`
- `README.md`
- `docs/getting-started/installation.md`
- `docs/getting-started/troubleshooting.md`
- `docs/architecture/*.md` (multiple files)

**Environment (1 file)**:
- `.env.example`

### Files to CREATE (1 file):
1. `docs/MIGRATION_OLLAMA_TO_OPENAI.md`

---

**END OF PLAN**
