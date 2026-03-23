# Implementation Plan: Code Quality Gap Closure

**Project**: SecondBrain Document Intelligence CLI
**Goal**: Close critical code quality gaps identified in code assessment
**Timeline**: ~65-85 hours total effort
**Strategy**: Phased approach with parallel execution opportunities

---

## Executive Summary

This plan addresses 6 critical gaps identified in the codebase assessment:

1. **Test Coverage**: 70% → 85%+ overall (95%+ on critical paths)
2. **Integration Tests**: 0 → Real service tests with Docker/TestContainers
3. **Example Validation**: Unvalidated → Automated example testing
4. **Async API Coverage**: 53% → 90%+
5. **Circuit Breaker Edge Cases**: 71% → 95%+
6. **RAG Pipeline**: Unvalidated → End-to-end validation

---

## Phase 1: Critical Coverage Gaps (Priority: HIGH)
**Duration**: 25-30 hours
**Goal**: Achieve 80% overall coverage, focus on CLI and Document Ingestion

### Task 1.1: CLI Command Coverage Enhancement
- **Files**: `src/secondbrain/cli/commands.py`, `src/secondbrain/cli/display.py`, `tests/test_cli/`
- **Current Coverage**: 46%
- **Target Coverage**: 90%+
- **Tests to Add**:
  - `test_ingest_progress_callback`: Validate Rich progress bar updates
  - `test_ingest_cores_validation`: Test core count validation (zero, negative, exceeds available)
  - `test_ingest_streaming_enabled`: Test with streaming config enabled
  - `test_ingest_file_validation`: Test path traversal and file size validation
  - `test_search_filters`: Test source, file-type, min-score filters
  - `test_search_json_output`: Test JSON format output
  - `test_list_pagination`: Test limit/offset pagination logic
  - `test_list_all_flag`: Test --all flag bypasses limit
  - `test_list_validation`: Test negative limit/offset validation
  - `test_delete_confirmation_flow`: Test interactive confirmation prompts
  - `test_delete_validation`: Test mutually exclusive option validation
  - `test_status_display`: Test status command output formatting
  - `test_health_json_output`: Test health command JSON format
  - `test_single_turn_chat`: Test non-interactive chat flow
  - `test_interactive_chat_commands`: Test /quit, /clear, /help commands
  - `test_interactive_chat_error_handling`: Test error recovery in REPL
  - `test_metrics_reset`: Test metrics reset functionality
  - `test_metrics_no_data`: Test metrics with no collected data
- **Effort**: 6-8 hours
- **Verification**: `pytest tests/test_cli/ --cov=secondbrain.cli --cov-report=term-missing` shows 90%+ coverage
- **Dependencies**: None (can run in parallel)

### Task 1.2: Document Ingestion Module Coverage
- **Files**: `src/secondbrain/document/__init__.py`, `tests/test_document/` (new directory)
- **Current Coverage**: 43%
- **Target Coverage**: 90%+
- **Tests to Add**:
  - `test_chunk_segments_boundary_cases`: Test chunking at exact boundaries, empty text, single word
  - `test_chunk_segments_overlap_validation`: Verify overlap preserves context
  - `test_chunk_segments_large_documents`: Test with 100K+ character documents
  - `test_chunk_segments_multiline_handling`: Test handling of paragraphs, newlines
  - `test_chunk_segments_unicode`: Test Unicode characters, emojis, CJK text
  - `test_deduplicate_and_chunk_segments`: Test hash-based deduplication
  - `test_deduplicate_whitespace_variations`: Test normalization (spaces, case)
  - `test_extract_text_pdf_pages`: Test multi-page PDF extraction
  - `test_extract_text_image_fallback`: Test image file text extraction
  - `test_extract_text_empty_file`: Test empty file handling
  - `test_extract_text_corrupted_pdf`: Test corrupted file error handling
  - `test_validate_file_path_traversal`: Test ".." path rejection
  - `test_validate_file_path_encoded`: Test URL-encoded traversal rejection
  - `test_validate_file_size_exceeds`: Test file size limit enforcement
  - `test_validate_file_size_within_limit`: Test files at boundary
  - `test_resolve_core_count_auto`: Test auto-detection when cores=None
  - `test_resolve_core_count_clamped`: Test clamping to available cores
  - `test_resolve_core_count_invalid`: Test negative/zero rejection
  - `test_stream_process_chunks_batch_full`: Test batch trigger at exactly batch_size
  - `test_stream_process_chunks_remaining`: Test handling of remaining chunks < batch_size
  - `test_store_embedding_batch_cache_hit`: Test cache hit path
  - `test_store_embedding_batch_cache_miss`: Test cache miss and batch generation
  - `test_store_embedding_batch_partial_failure`: Test batch with some failed embeddings
  - `test_process_parallel_with_progress_queue`: Test progress queue integration
  - `test_process_parallel_timeout`: Test timeout handling for slow files
  - `test_process_parallel_worker_initialization`: Test worker process setup
  - `test_is_supported_all_extensions`: Test all 27 supported extensions
  - `test_get_file_type_mapping`: Test file type categorization (image, audio, etc.)
  - `test_ingest_empty_directory`: Test directory with no supported files
  - `test_ingest_mixed_success_failure`: Test batch with some failures
- **Effort**: 8-10 hours
- **Verification**: `pytest tests/test_document/ --cov=secondbrain.document --cov-report=term-missing` shows 90%+ coverage
- **Dependencies**: None (can run in parallel)

### Task 1.3: Domain Layer Test Suite (New)
- **Files**: `src/secondbrain/domain/entities.py`, `src/secondbrain/domain/value_objects.py`, `tests/test_domain/` (new)
- **Current Coverage**: 0%
- **Target Coverage**: 95%+
- **Tests to Add**:
  - `test_document_metadata_validation`: Test source_file and file_type validation
  - `test_document_metadata_defaults`: Test default values for optional fields
  - `test_document_metadata_immutability`: Test frozen dataclass behavior
  - `test_document_chunk_validation`: Test chunk text and ID validation
  - `test_document_chunk_properties`: Test char_count, word_count calculations
  - `test_document_chunk_embedding_status`: Test has_embedding() method
  - `test_document_chunk_to_dict`: Test serialization to storage format
  - `test_document_chunk_page_none`: Test chunk without page number
  - `test_source_path_validation`: Test SourcePath value object validation
  - `test_source_path_normalization`: Test path normalization behavior
  - `test_source_path_equality`: Test equality comparison
  - `test_embedding_vector_validation`: Test EmbeddingVector dimension validation
  - `test_embedding_vector_norm`: Test vector normalization
  - `test_embedding_vector_similarity`: Test cosine similarity calculation
  - `test_chunk_id_generation`: Test ChunkId uniqueness and format
  - `test_chunk_id_validation`: Test ChunkId format validation
- **Effort**: 4-5 hours
- **Verification**: `pytest tests/test_domain/ --cov=secondbrain.domain --cov-report=term-missing` shows 95%+ coverage
- **Dependencies**: None (can run in parallel)

---

## Phase 2: Integration Infrastructure (Priority: HIGH)
**Duration**: 20-25 hours
**Goal**: Real service tests with Docker/TestContainers

### Task 2.1: Docker Compose Integration Setup
- **Files**: `docker-compose.test.yml`, `tests/integration/conftest.py`, `tests/integration/` (new)
- **Infrastructure to Build**:
  - Docker Compose file with MongoDB 8.0 and sentence-transformers services
  - Test fixtures for real MongoDB connections
  - Test fixtures for real embedding generator
  - Service health check utilities
  - Test data seeding scripts
  - Cleanup utilities for test databases
- **Configuration**:
  ```yaml
  # docker-compose.test.yml
  version: '3.8'
  services:
    mongodb:
      image: mongo:8.0
      ports:
        - "27018:27017"  # Different port to avoid conflicts
      environment:
        MONGO_INITDB_DATABASE: secondbrain_test
      volumes:
        - mongo_test_data:/data/db

    sentence-transformers:
      image: sentence-transformers/server:latest
      ports:
        - "11435:11434"  # Different port
      environment:
        MODEL: all-MiniLM-L6-v2
      volumes:
        - model_cache:/root/.cache

  volumes:
    mongo_test_data:
    model_cache:
  ```
- **Effort**: 4-5 hours
- **Verification**: `docker-compose -f docker-compose.test.yml up -d` starts all services, health checks pass
- **Dependencies**: Docker installed, Docker Compose v2+

### Task 2.2: Real MongoDB Integration Tests
- **Files**: `tests/integration/test_mongo_integration.py`, `tests/integration/test_storage_real.py`
- **Tests to Add**:
  - `test_storage_real_mongo_connection`: Test VectorStorage with real MongoDB
  - `test_storage_real_store_and_retrieve`: Store and query single document
  - `test_storage_real_batch_operations`: Test batch store with 100+ documents
  - `test_storage_real_search_similarity`: Test semantic search with real embeddings
  - `test_storage_real_filter_by_source`: Test source file filtering
  - `test_storage_real_filter_by_file_type`: Test file type filtering
  - `test_storage_real_delete_operations`: Test delete by source/chunk_id
  - `test_storage_real_pagination`: Test limit/offset pagination
  - `test_storage_real_concurrent_writes`: Test concurrent batch operations
  - `test_storage_real_connection_recovery`: Test reconnection after MongoDB restart
  - `test_ingest_real_mongo`: Full ingestion pipeline with real storage
  - `test_search_real_mongo`: Full search pipeline with real storage
  - `test_list_real_mongo`: Full list pipeline with real storage
  - `test_status_real_mongo`: Real database statistics
- **Effort**: 5-6 hours
- **Verification**: `pytest tests/integration/test_storage_real.py -m integration` passes with real MongoDB
- **Dependencies**: Task 2.1 (Docker setup), MongoDB running

### Task 2.3: Real Embedding Service Integration Tests
- **Files**: `tests/integration/test_embedding_real.py`, `tests/integration/test_ingestion_e2e.py`
- **Tests to Add**:
  - `test_embedding_generator_real_connection`: Test LocalEmbeddingGenerator connection
  - `test_embedding_generate_real_model`: Test single embedding generation
  - `test_embedding_generate_batch_real`: Test batch generation with 50+ texts
  - `test_embedding_dimensions_validation`: Verify output dimensions match config
  - `test_embedding_consistency`: Same text produces same embedding
  - `test_embedding_batch_order`: Batch maintains text order
  - `test_ingestion_e2e_pdf`: Full PDF ingestion → embedding → storage → search
  - `test_ingestion_e2e_docx`: Full DOCX ingestion pipeline
  - `test_ingestion_e2e_markdown`: Full Markdown ingestion pipeline
  - `test_ingestion_e2e_multidoc`: Batch ingestion of 10+ documents
  - `test_ingestion_e2e_multicore`: Test with cores=4, verify parallelism
  - `test_search_e2e_semantic`: Semantic search returns relevant results
  - `test_search_e2e_filters`: Filter combinations work correctly
- **Effort**: 6-8 hours
- **Verification**: `pytest tests/integration/test_ingestion_e2e.py -m integration --slow` passes
- **Dependencies**: Task 2.1 (Docker setup), sentence-transformers running

### Task 2.4: Async API Integration Tests
- **Files**: `tests/integration/test_async_integration.py`
- **Current Coverage**: 53%
- **Target Coverage**: 90%+
- **Tests to Add**:
  - `test_async_store_real`: Test async store with real MongoDB
  - `test_async_store_batch_real`: Test async batch store with 100+ docs
  - `test_async_search_real`: Test async search with real embeddings
  - `test_async_concurrent_operations`: Test 10 concurrent async operations
  - `test_async_error_propagation`: Test async exception handling
  - `test_async_connection_pooling`: Test connection pool reuse
  - `test_async_circuit_breaker_integration`: Test circuit breaker with async
  - `test_async_timeout_handling`: Test async timeout behavior
  - `test_async_memory_management`: Test async with streaming enabled
  - `test_async_real_full_pipeline`: Full async ingestion → search pipeline
- **Effort**: 5-6 hours
- **Verification**: `pytest tests/integration/test_async_integration.py -m integration --cov=secondbrain.storage --cov-report=term-missing` shows 90%+ coverage
- **Dependencies**: Task 2.1, Task 2.2

---

## Phase 3: Hardening (Priority: MEDIUM)
**Duration**: 15-20 hours
**Goal**: Edge cases, async coverage, circuit breaker hardening

### Task 3.1: Circuit Breaker Edge Cases
- **Files**: `src/secondbrain/utils/circuit_breaker.py`, `tests/test_utils/test_circuit_breaker.py`
- **Current Coverage**: 71%
- **Target Coverage**: 95%+
- **Tests to Add**:
  - `test_half_open_exceeds_max_calls`: Test exceeding half_open_max_calls
  - `test_half_open_partial_success`: Test some success, some failure in half-open
  - `test_concurrent_state_transitions`: Test thread safety with 100 concurrent calls
  - `test_recovery_timeout_precision`: Test timeout timing accuracy
  - `test_success_threshold_requirement`: Test exact success count needed
  - `test_circuit_breaker_reset_manual`: Test manual reset functionality
  - `test_circuit_breaker_state_persistence`: Test state across restarts
  - `test_circuit_breaker_callable_exception`: Test with exception-raising callables
  - `test_circuit_breaker_callable_return_value`: Test with various return types
  - `test_circuit_breaker_logging_transitions`: Test all state transition logs
  - `test_circuit_breaker_config_validation`: Test invalid config values
  - `test_circuit_breaker_service_name_context`: Test service name in errors
  - `test_circuit_breaker_failure_rate_calculation`: Test failure rate tracking
  - `test_circuit_breaker_half_open_timeout_edge`: Test timeout at exact boundary
  - `test_circuit_breaker_rapid_state_flapping`: Test rapid open/close cycles
- **Effort**: 4-5 hours
- **Verification**: `pytest tests/test_utils/test_circuit_breaker.py --cov=secondbrain.utils.circuit_breaker --cov-report=term-missing` shows 95%+ coverage
- **Dependencies**: None (can run in parallel)

### Task 3.2: Async API Full Coverage
- **Files**: `src/secondbrain/storage/storage.py`, `src/secondbrain/embedding/local.py`, `tests/test_storage/test_async_storage.py`
- **Current Coverage**: 53%
- **Target Coverage**: 90%+
- **Tests to Add**:
  - `test_async_store_validation`: Test input validation in async store
  - `test_async_store_empty_batch`: Test empty batch handling
  - `test_async_store_large_batch`: Test batch with 1000+ documents
  - `test_async_search_timeout`: Test search with timeout
  - `test_async_search_empty_results`: Test search with no results
  - `test_async_delete_by_source_empty`: Test delete with no matches
  - `test_async_delete_all_empty_db`: Test delete_all on empty database
  - `test_async_get_stats_empty_db`: Test get_stats on empty database
  - `test_async_validate_connection_timeout`: Test connection validation timeout
  - `test_async_validate_connection_failure`: Test connection validation failure
  - `test_async_close_idempotent`: Test multiple close() calls
  - `test_async_context_manager_exception`: Test context manager with exception
  - `test_async_batch_order_preservation`: Test batch operation order
  - `test_async_concurrent_searches`: Test 10 concurrent searches
  - `test_async_memory_leak_detection`: Test for memory leaks in long-running async
- **Effort**: 4-5 hours
- **Verification**: `pytest tests/test_storage/test_async_storage.py --cov=secondbrain.storage.storage --cov-report=term-missing -k async` shows 90%+ coverage
- **Dependencies**: None (can run in parallel)

### Task 3.3: RAG Pipeline End-to-End Validation
- **Files**: `src/secondbrain/rag/pipeline.py`, `src/secondbrain/conversation/`, `tests/test_rag/` (new)
- **Current Coverage**: 0% (RAG not validated)
- **Target Coverage**: 85%+
- **Tests to Add**:
  - `test_rag_pipeline_initialization`: Test pipeline component injection
  - `test_rag_pipeline_query_single_turn`: Test basic single-turn query
  - `test_rag_pipeline_query_no_results`: Test query with no matching docs
  - `test_rag_pipeline_query_error_handling`: Test query with LLM failure
  - `test_rag_pipeline_chat_multi_turn`: Test multi-turn conversation
  - `test_rag_pipeline_chat_context_window`: Test context window limiting
  - `test_rag_pipeline_chat_session_persistence`: Test session save/load
  - `test_rag_pipeline_query_rewriting`: Test query rewriting with history
  - `test_rag_pipeline_query_rewriting_failure`: Test rewriting fallback
  - `test_rag_pipeline_format_context_truncation`: Test context length limit
  - `test_rag_pipeline_format_context_empty`: Test empty context formatting
  - `test_rag_pipeline_build_prompt_system`: Test system instruction inclusion
  - `test_rag_pipeline_build_prompt_history`: Test history inclusion
  - `test_rag_pipeline_build_prompt_no_context`: Test no context prompt
  - `test_rag_pipeline_show_sources`: Test source display functionality
  - `test_rag_pipeline_session_creation`: Test ConversationSession.create()
  - `test_rag_pipeline_session_load`: Test ConversationSession.load()
  - `test_rag_pipeline_session_history`: Test session history retrieval
  - `test_rag_pipeline_session_clear`: Test session history clearing
  - `test_rag_pipeline_query_rewriter_integration`: Test QueryRewriter integration
  - `test_rag_pipeline_ollama_health_check`: Test Ollama health validation
  - `test_rag_pipeline_ollama_generation`: Test Ollama generate() integration
- **Effort**: 5-6 hours
- **Verification**: `pytest tests/test_rag/ --cov=secondbrain.rag --cov=secondbrain.conversation --cov-report=term-missing` shows 85%+ coverage
- **Dependencies**: None (can run in parallel, but needs Ollama for integration tests)

### Task 3.4: Example Code Validation
- **Files**: `docs/examples/**/*.py`, `tests/test_examples/` (new)
- **Infrastructure**: Example runner with validation
- **Tests to Add**:
  - `test_example_basic_usage_ingest`: Validate `docs/examples/basic_usage/ingest_documents.py`
  - `test_example_basic_usage_search`: Validate `docs/examples/basic_usage/semantic_search.py`
  - `test_example_basic_usage_list`: Validate `docs/examples/basic_usage/list_documents.py`
  - `test_example_circuit_breaker`: Validate `docs/examples/circuit_breaker_usage.py`
  - `test_example_async_workflow`: Validate `docs/examples/advanced/async_workflow.py`
  - `test_example_batch_ingestion`: Validate `docs/examples/advanced/batch_ingestion.py`
  - `test_example_custom_chunking`: Validate `docs/examples/advanced/custom_chunking.py`
  - `test_example_flask_api`: Validate `docs/examples/integrations/flask_api.py`
  - `test_example_fastapi_endpoint`: Validate `docs/examples/integrations/fastapi_endpoint.py`
  - `test_example_tracing`: Validate `docs/examples/tracing_example.py`
- **Validation Strategy**:
  - Each example must run without errors
  - Each example must produce expected output
  - Examples using services must work with test Docker setup
  - Examples must complete within timeout (30s)
- **Effort**: 3-4 hours
- **Verification**: `pytest tests/test_examples/ -v` all examples pass
- **Dependencies**: Task 2.1 (Docker setup), example files exist

---

## Phase 4: Polish (Priority: LOW)
**Duration**: 5-10 hours
**Goal**: Final coverage push, documentation, CI integration

### Task 4.1: Coverage Gap Analysis and Final Push
- **Files**: All modules with <85% coverage
- **Activity**:
  - Run coverage report: `pytest --cov=secondbrain --cov-report=html`
  - Identify remaining gaps in htmlcov/
  - Add targeted tests for uncovered lines
  - Focus on: error paths, edge cases, validation logic
- **Target**: 85%+ overall, 95%+ on critical paths (CLI, Document, Storage)
- **Effort**: 3-5 hours
- **Verification**: `pytest --cov=secondbrain --cov-report=term-missing` shows overall 85%+

### Task 4.2: Test Performance Optimization
- **Files**: `tests/conftest.py`, test fixtures
- **Optimizations**:
  - Add session-scoped fixtures for expensive setup (MongoDB client, embedding model)
  - Implement test parallelization with pytest-xdist (-n 8)
  - Add caching for test data generation
  - Optimize fixture teardown to reduce cleanup time
  - Add test markers for slow tests to exclude from fast profile
- **Target**: Maintain ~38s for unit tests, ~60s for integration tests
- **Effort**: 2-3 hours
- **Verification**: `pytest -m "not integration" -n 8 --no-cov` completes in <40s

### Task 4.3: CI/CD Integration (Local Only)
- **Files**: `scripts/run_tests.sh`, `scripts/validate_examples.sh`
- **Scripts to Create**:
  - `scripts/run_tests.sh`: Unified test runner with profiles
  - `scripts/validate_examples.sh`: Example validation script
  - `scripts/run_integration_tests.sh`: Integration test runner
  - Update `pre-commit` config to include example validation
- **Effort**: 1-2 hours
- **Verification**: Scripts run successfully, can be used in pre-commit hooks

---

## Parallel Execution Strategy

### Wave 1: Independent Tasks (Can Run Simultaneously)
**Duration**: 10-12 hours with 3-4 developers

| Task | Owner | Dependencies |
|------|-------|--------------|
| Task 1.1: CLI Coverage | Developer A | None |
| Task 1.2: Document Coverage | Developer B | None |
| Task 1.3: Domain Layer | Developer C | None |
| Task 3.1: Circuit Breaker | Developer D | None |

### Wave 2: Infrastructure Setup
**Duration**: 4-5 hours

| Task | Owner | Dependencies |
|------|-------|--------------|
| Task 2.1: Docker Setup | Developer A | Wave 1 complete |

### Wave 3: Integration Tests (Parallel within Wave)
**Duration**: 10-12 hours with 3 developers

| Task | Owner | Dependencies |
|------|-------|--------------|
| Task 2.2: MongoDB Integration | Developer A | Task 2.1 |
| Task 2.3: Embedding Integration | Developer B | Task 2.1 |
| Task 2.4: Async Integration | Developer C | Task 2.1, Task 2.2 |
| Task 3.2: Async Coverage | Developer D | None (can overlap) |

### Wave 4: RAG and Examples
**Duration**: 8-10 hours

| Task | Owner | Dependencies |
|------|-------|--------------|
| Task 3.3: RAG Pipeline | Developer A | None |
| Task 3.4: Example Validation | Developer B | Task 2.1 |

### Wave 5: Polish
**Duration**: 5-10 hours

| Task | Owner | Dependencies |
|------|-------|--------------|
| Task 4.1: Coverage Push | All | Wave 3-4 complete |
| Task 4.2: Performance | Developer C | Wave 3-4 complete |
| Task 4.3: CI Scripts | Developer D | All previous |

---

## Success Metrics

### Coverage Targets

| Module | Current | Target | Critical Path Target |
|--------|---------|--------|---------------------|
| Overall | 70% | 85%+ | 95%+ |
| CLI | 46% | 90%+ | 95%+ |
| Document Ingestion | 43% | 90%+ | 95%+ |
| Domain Layer | 0% | 95%+ | 95%+ |
| Storage | 78% | 85%+ | 90%+ |
| Async API | 53% | 90%+ | 95%+ |
| Circuit Breaker | 71% | 95%+ | 95%+ |
| RAG Pipeline | 0% | 85%+ | 90%+ |
| Conversation | 0% | 85%+ | 90%+ |

### Integration Test Targets

| Metric | Current | Target |
|--------|---------|--------|
| Integration Tests | 0 | 25+ |
| Real MongoDB Tests | 0 | 15+ |
| Real Embedding Tests | 0 | 10+ |
| E2E Pipeline Tests | 0 | 8+ |
| Async Integration Tests | 0 | 10+ |

### Example Validation

| Metric | Current | Target |
|--------|---------|--------|
| Validated Examples | 0 | 10/10 |
| Example Test Coverage | 0% | 100% |

### Performance Targets

| Metric | Current | Target |
|--------|---------|--------|
| Unit Test Time | ~38s | <40s |
| Integration Test Time | N/A | <60s |
| Test Parallelism | 4 workers | 8 workers |
| Example Test Time | N/A | <30s each |

---

## Risk Mitigation

### Risk 1: Docker Service Startup Failures
**Mitigation**:
- Add health check retries (5 attempts, 10s interval)
- Provide fallback to local MongoDB if Docker unavailable
- Document setup requirements clearly

### Risk 2: Test Flakiness with Real Services
**Mitigation**:
- Implement retry logic for flaky tests (max 2 retries)
- Use transactional test databases
- Add test isolation fixtures
- Mark flaky tests with `@pytest.mark.flaky`

### Risk 3: Example Drift (Examples Become Outdated)
**Mitigation**:
- Make example validation part of CI pipeline
- Run example tests on every PR
- Pin example dependencies to specific versions

### Risk 4: Performance Degradation from Integration Tests
**Mitigation**:
- Keep integration tests in separate profile (`-m integration`)
- Run integration tests only on nightly builds or manual trigger
- Optimize test data setup/teardown

---

## Implementation Checklist

### Phase 1: Critical Coverage
- [ ] Task 1.1: CLI Command Coverage (6-8h)
- [ ] Task 1.2: Document Ingestion Coverage (8-10h)
- [ ] Task 1.3: Domain Layer Tests (4-5h)

### Phase 2: Integration Infrastructure
- [ ] Task 2.1: Docker Compose Setup (4-5h)
- [ ] Task 2.2: MongoDB Integration Tests (5-6h)
- [ ] Task 2.3: Embedding Integration Tests (6-8h)
- [ ] Task 2.4: Async Integration Tests (5-6h)

### Phase 3: Hardening
- [ ] Task 3.1: Circuit Breaker Edge Cases (4-5h)
- [ ] Task 3.2: Async API Full Coverage (4-5h)
- [ ] Task 3.3: RAG Pipeline E2E (5-6h)
- [ ] Task 3.4: Example Validation (3-4h)

### Phase 4: Polish
- [ ] Task 4.1: Coverage Gap Analysis (3-5h)
- [ ] Task 4.2: Performance Optimization (2-3h)
- [ ] Task 4.3: CI Scripts (1-2h)

---

## Total Effort Estimate

| Phase | Minimum Hours | Maximum Hours |
|-------|--------------|---------------|
| Phase 1: Critical Coverage | 18 | 23 |
| Phase 2: Integration | 20 | 25 |
| Phase 3: Hardening | 15 | 20 |
| Phase 4: Polish | 6 | 10 |
| **TOTAL** | **59** | **78** |

**Recommended Timeline**:
- 1 developer: 2-3 weeks (full-time)
- 2 developers: 1-1.5 weeks (parallel execution)
- 3-4 developers: 3-5 days (optimized parallel execution)

---

## Appendix: Test Command Reference

### Running Specific Test Suites
```bash
# Fast unit tests (no integration)
pytest -m "not integration" -n 4 --no-cov

# Integration tests only
pytest -m integration -n 4

# Coverage report for specific module
pytest tests/test_cli/ --cov=secondbrain.cli --cov-report=term-missing

# HTML coverage report
pytest --cov=secondbrain --cov-report=html
open htmlcov/index.html

# Run specific test file
pytest tests/test_cli/test_cli.py -v

# Run tests with timeout
pytest --timeout=60

# Run slow tests only
pytest -m slow

# Example validation
pytest tests/test_examples/ -v
```

### Docker Setup for Integration Tests
```bash
# Start test services
docker-compose -f docker-compose.test.yml up -d

# Check health
docker-compose -f docker-compose.test.yml ps

# Stop services
docker-compose -f docker-compose.test.yml down

# Clean volumes
docker-compose -f docker-compose.test.yml down -v
```

### Coverage Thresholds
```bash
# Fail if coverage < 85%
pytest --cov=secondbrain --cov-report=term-missing --cov-fail-under=85

# Per-module coverage
pytest --cov=secondbrain.cli --cov=secondbrain.document \
       --cov-report=term-missing \
       --cov-fail-under=85
```
