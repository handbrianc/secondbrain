# Execution Task Breakdown - Code Quality Gap Closure

## Wave 1: Independent High-Impact Tasks (Phase 1)

### Task W1.1: CLI Commands - Ingest Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_cli/test_ingest_commands.py` (new)
- **Specific Tests**:
  - `test_ingest_progress_callback`
  - `test_ingest_cores_validation`
  - `test_ingest_streaming_enabled`
  - `test_ingest_file_validation`
  - `test_ingest_empty_directory`
  - `test_ingest_mixed_success_failure`
- **Success Criteria**: 6 new test functions, all pass
- **Verification Command**: `pytest tests/test_cli/test_ingest_commands.py -v`
- **Coverage Impact**: +15% on commands.py
- **Effort**: 2 hours
- **Dependencies**: None

### Task W1.2: CLI Commands - Search Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_cli/test_search_commands.py` (new)
- **Specific Tests**:
  - `test_search_filters`
  - `test_search_json_output`
  - `test_search_no_results`
  - `test_search_timeout_handling`
- **Success Criteria**: 4 new test functions, all pass
- **Verification Command**: `pytest tests/test_cli/test_search_commands.py -v`
- **Coverage Impact**: +8% on commands.py
- **Effort**: 1.5 hours
- **Dependencies**: None

### Task W1.3: CLI Commands - List/Delete Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_cli/test_list_delete_commands.py` (new)
- **Specific Tests**:
  - `test_list_pagination`
  - `test_list_all_flag`
  - `test_list_validation`
  - `test_delete_confirmation_flow`
  - `test_delete_validation`
  - `test_delete_by_chunk_id`
- **Success Criteria**: 6 new test functions, all pass
- **Verification Command**: `pytest tests/test_cli/test_list_delete_commands.py -v`
- **Coverage Impact**: +10% on commands.py
- **Effort**: 2 hours
- **Dependencies**: None

### Task W1.4: CLI Commands - Status/Health/Metrics Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_cli/test_status_health_metrics.py` (new)
- **Specific Tests**:
  - `test_status_display`
  - `test_health_json_output`
  - `test_metrics_reset`
  - `test_metrics_no_data`
- **Success Criteria**: 4 new test functions, all pass
- **Verification Command**: `pytest tests/test_cli/test_status_health_metrics.py -v`
- **Coverage Impact**: +5% on commands.py
- **Effort**: 1 hour
- **Dependencies**: None

### Task W1.5: CLI Commands - Chat Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_cli/test_chat_commands.py` (new)
- **Specific Tests**:
  - `test_single_turn_chat`
  - `test_interactive_chat_commands`
  - `test_interactive_chat_error_handling`
  - `test_list_sessions`
  - `test_delete_session`
  - `test_check_llm`
- **Success Criteria**: 6 new test functions, all pass
- **Verification Command**: `pytest tests/test_cli/test_chat_commands.py -v`
- **Coverage Impact**: +12% on commands.py
- **Effort**: 2 hours
- **Dependencies**: None

### Task W1.6: Display Module Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_cli/test_display.py` (new)
- **Specific Tests**:
  - `test_display_search_results`
  - `test_display_list_results`
  - `test_display_status`
  - `test_display_health_status`
- **Success Criteria**: 4 new test functions, all pass
- **Verification Command**: `pytest tests/test_cli/test_display.py -v`
- **Coverage Impact**: 85% → 100% on display.py
- **Effort**: 1 hour
- **Dependencies**: None

### Task W1.7: Document - Chunk Segmentation Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_document/test_chunking.py` (new)
- **Specific Tests**:
  - `test_chunk_segments_boundary_cases`
  - `test_chunk_segments_overlap_validation`
  - `test_chunk_segments_large_documents`
  - `test_chunk_segments_multiline_handling`
  - `test_chunk_segments_unicode`
  - `test_deduplicate_and_chunk_segments`
  - `test_deduplicate_whitespace_variations`
- **Success Criteria**: 7 new test functions, all pass
- **Verification Command**: `pytest tests/test_document/test_chunking.py -v`
- **Coverage Impact**: +15% on document/__init__.py
- **Effort**: 2.5 hours
- **Dependencies**: None

### Task W1.8: Document - Text Extraction Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_document/test_extraction.py` (new)
- **Specific Tests**:
  - `test_extract_text_pdf_pages`
  - `test_extract_text_image_fallback`
  - `test_extract_text_empty_file`
  - `test_extract_text_corrupted_pdf`
- **Success Criteria**: 4 new test functions, all pass
- **Verification Command**: `pytest tests/test_document/test_extraction.py -v`
- **Coverage Impact**: +10% on document/__init__.py
- **Effort**: 2 hours
- **Dependencies**: None

### Task W1.9: Document - Validation Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_document/test_validation.py` (new)
- **Specific Tests**:
  - `test_validate_file_path_traversal`
  - `test_validate_file_path_encoded`
  - `test_validate_file_size_exceeds`
  - `test_validate_file_size_within_limit`
  - `test_resolve_core_count_auto`
  - `test_resolve_core_count_clamped`
  - `test_resolve_core_count_invalid`
- **Success Criteria**: 7 new test functions, all pass
- **Verification Command**: `pytest tests/test_document/test_validation.py -v`
- **Coverage Impact**: +8% on document/__init__.py
- **Effort**: 1.5 hours
- **Dependencies**: None

### Task W1.10: Document - Streaming/Processing Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_document/test_streaming.py` (new)
- **Specific Tests**:
  - `test_stream_process_chunks_batch_full`
  - `test_stream_process_chunks_remaining`
  - `test_store_embedding_batch_cache_hit`
  - `test_store_embedding_batch_cache_miss`
  - `test_store_embedding_batch_partial_failure`
  - `test_process_parallel_with_progress_queue`
  - `test_process_parallel_timeout`
  - `test_process_parallel_worker_initialization`
- **Success Criteria**: 8 new test functions, all pass
- **Verification Command**: `pytest tests/test_document/test_streaming.py -v`
- **Coverage Impact**: +12% on document/__init__.py
- **Effort**: 3 hours
- **Dependencies**: None

### Task W1.11: Document - Utility Functions Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_document/test_utils.py` (new)
- **Specific Tests**:
  - `test_is_supported_all_extensions`
  - `test_get_file_type_mapping`
- **Success Criteria**: 2 new test functions, all pass
- **Verification Command**: `pytest tests/test_document/test_utils.py -v`
- **Coverage Impact**: +3% on document/__init__.py
- **Effort**: 0.5 hours
- **Dependencies**: None

### Task W1.12: Domain - Document Metadata Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_domain/test_entities.py` (new)
- **Specific Tests**:
  - `test_document_metadata_validation`
  - `test_document_metadata_defaults`
  - `test_document_metadata_immutability`
  - `test_document_chunk_validation`
  - `test_document_chunk_properties`
  - `test_document_chunk_embedding_status`
  - `test_document_chunk_to_dict`
  - `test_document_chunk_page_none`
- **Success Criteria**: 8 new test functions, all pass
- **Verification Command**: `pytest tests/test_domain/test_entities.py -v`
- **Coverage Impact**: 0% → 95%+ on domain/entities.py
- **Effort**: 2 hours
- **Dependencies**: None

### Task W1.13: Domain - Value Objects Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_domain/test_value_objects.py` (new)
- **Specific Tests**:
  - `test_source_path_validation`
  - `test_source_path_normalization`
  - `test_source_path_equality`
  - `test_embedding_vector_validation`
  - `test_embedding_vector_norm`
  - `test_embedding_vector_similarity`
  - `test_chunk_id_generation`
  - `test_chunk_id_validation`
- **Success Criteria**: 8 new test functions, all pass
- **Verification Command**: `pytest tests/test_domain/test_value_objects.py -v`
- **Coverage Impact**: 0% → 95%+ on domain/value_objects.py
- **Effort**: 2 hours
- **Dependencies**: None

## Wave 2: Circuit Breaker Hardening (Phase 3, Parallel)

### Task W2.1: Circuit Breaker - State Transition Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_utils/test_circuit_breaker_extended.py` (new)
- **Specific Tests**:
  - `test_half_open_exceeds_max_calls`
  - `test_half_open_partial_success`
  - `test_concurrent_state_transitions`
  - `test_recovery_timeout_precision`
  - `test_success_threshold_requirement`
- **Success Criteria**: 5 new test functions, all pass
- **Verification Command**: `pytest tests/test_utils/test_circuit_breaker_extended.py -v`
- **Coverage Impact**: +10% on circuit_breaker.py
- **Effort**: 2 hours
- **Dependencies**: None

### Task W2.2: Circuit Breaker - Edge Cases Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_utils/test_circuit_breaker_edge_cases.py` (new)
- **Specific Tests**:
  - `test_circuit_breaker_reset_manual`
  - `test_circuit_breaker_state_persistence`
  - `test_circuit_breaker_callable_exception`
  - `test_circuit_breaker_callable_return_value`
  - `test_circuit_breaker_logging_transitions`
  - `test_circuit_breaker_config_validation`
  - `test_circuit_breaker_service_name_context`
  - `test_circuit_breaker_failure_rate_calculation`
  - `test_circuit_breaker_half_open_timeout_edge`
  - `test_circuit_breaker_rapid_state_flapping`
- **Success Criteria**: 10 new test functions, all pass
- **Verification Command**: `pytest tests/test_utils/test_circuit_breaker_edge_cases.py -v`
- **Coverage Impact**: +14% on circuit_breaker.py
- **Effort**: 2.5 hours
- **Dependencies**: None

## Wave 3: Async API Coverage (Phase 3, Parallel)

### Task W3.1: Async Storage - Validation Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_storage/test_async_validation.py` (new)
- **Specific Tests**:
  - `test_async_store_validation`
  - `test_async_store_empty_batch`
  - `test_async_store_large_batch`
  - `test_async_search_timeout`
  - `test_async_search_empty_results`
  - `test_async_delete_by_source_empty`
  - `test_async_delete_all_empty_db`
  - `test_async_get_stats_empty_db`
- **Success Criteria**: 8 new test functions, all pass
- **Verification Command**: `pytest tests/test_storage/test_async_validation.py -v`
- **Coverage Impact**: +15% on storage.py (async paths)
- **Effort**: 2 hours
- **Dependencies**: None

### Task W3.2: Async Storage - Connection Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_storage/test_async_connection.py` (new)
- **Specific Tests**:
  - `test_async_validate_connection_timeout`
  - `test_async_validate_connection_failure`
  - `test_async_close_idempotent`
  - `test_async_context_manager_exception`
  - `test_async_batch_order_preservation`
  - `test_async_concurrent_searches`
  - `test_async_memory_leak_detection`
- **Success Criteria**: 7 new test functions, all pass
- **Verification Command**: `pytest tests/test_storage/test_async_connection.py -v`
- **Coverage Impact**: +10% on storage.py (async paths)
- **Effort**: 2 hours
- **Dependencies**: None

### Task W3.3: Embedding Cache Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_utils/test_embedding_cache.py` (existing, extend)
- **Specific Tests**: Add tests for uncovered lines 56, 61, 66, 94-96, 116, 119-120, 123, 142-148, 165-171, 175-178, 188-191, 209-211, 220-221
- **Success Criteria**: Coverage 53% → 90%+
- **Verification Command**: `pytest tests/test_utils/test_embedding_cache.py --cov=secondbrain.utils.embedding_cache --cov-report=term-missing`
- **Coverage Impact**: 53% → 90%+
- **Effort**: 2 hours
- **Dependencies**: None

## Wave 4: Integration Infrastructure (Phase 2)

### Task W4.1: Docker Compose Test Setup
- **Category**: deep
- **Skills**: []
- **Files**: `docker-compose.test.yml` (new), `tests/integration/conftest.py` (new)
- **Specific Deliverables**:
  - Docker Compose file with MongoDB 8.0 (port 27018)
  - Docker Compose with sentence-transformers (port 11435)
  - Health check utilities
  - Test fixtures for real services
  - Cleanup utilities
- **Success Criteria**: `docker-compose -f docker-compose.test.yml up -d` starts all services, health checks pass
- **Verification Command**: `docker-compose -f docker-compose.test.yml ps`
- **Effort**: 4 hours
- **Dependencies**: None

### Task W4.2: MongoDB Integration Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/integration/test_mongo_real.py` (new)
- **Specific Tests**:
  - `test_storage_real_mongo_connection`
  - `test_storage_real_store_and_retrieve`
  - `test_storage_real_batch_operations`
  - `test_storage_real_search_similarity`
  - `test_storage_real_filter_by_source`
  - `test_storage_real_filter_by_file_type`
  - `test_storage_real_delete_operations`
  - `test_storage_real_pagination`
  - `test_storage_real_concurrent_writes`
  - `test_storage_real_connection_recovery`
- **Success Criteria**: 10 integration tests pass with real MongoDB
- **Verification Command**: `pytest tests/integration/test_mongo_real.py -m integration -v`
- **Effort**: 5 hours
- **Dependencies**: Task W4.1

### Task W4.3: Embedding Service Integration Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/integration/test_embedding_real.py` (new)
- **Specific Tests**:
  - `test_embedding_generator_real_connection`
  - `test_embedding_generate_real_model`
  - `test_embedding_generate_batch_real`
  - `test_embedding_dimensions_validation`
  - `test_embedding_consistency`
  - `test_embedding_batch_order`
- **Success Criteria**: 6 integration tests pass with real sentence-transformers
- **Verification Command**: `pytest tests/integration/test_embedding_real.py -m integration -v`
- **Effort**: 4 hours
- **Dependencies**: Task W4.1

### Task W4.4: E2E Ingestion Pipeline Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/integration/test_ingestion_e2e.py` (new)
- **Specific Tests**:
  - `test_ingestion_e2e_pdf`
  - `test_ingestion_e2e_docx`
  - `test_ingestion_e2e_markdown`
  - `test_ingestion_e2e_multidoc`
  - `test_ingestion_e2e_multicore`
  - `test_search_e2e_semantic`
  - `test_search_e2e_filters`
- **Success Criteria**: 7 end-to-end tests pass
- **Verification Command**: `pytest tests/integration/test_ingestion_e2e.py -m integration --slow -v`
- **Effort**: 5 hours
- **Dependencies**: Task W4.1, Task W4.2, Task W4.3

### Task W4.5: Async Integration Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/integration/test_async_integration.py` (new)
- **Specific Tests**:
  - `test_async_store_real`
  - `test_async_store_batch_real`
  - `test_async_search_real`
  - `test_async_concurrent_operations`
  - `test_async_error_propagation`
  - `test_async_connection_pooling`
  - `test_async_circuit_breaker_integration`
  - `test_async_timeout_handling`
  - `test_async_memory_management`
  - `test_async_real_full_pipeline`
- **Success Criteria**: 10 async integration tests pass
- **Verification Command**: `pytest tests/integration/test_async_integration.py -m integration -v`
- **Effort**: 5 hours
- **Dependencies**: Task W4.1, Task W4.2

## Wave 5: RAG Pipeline Tests (Phase 3)

### Task W5.1: RAG Pipeline - Core Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_rag/test_pipeline.py` (new)
- **Specific Tests**:
  - `test_rag_pipeline_initialization`
  - `test_rag_pipeline_query_single_turn`
  - `test_rag_pipeline_query_no_results`
  - `test_rag_pipeline_query_error_handling`
  - `test_rag_pipeline_format_context_truncation`
  - `test_rag_pipeline_format_context_empty`
  - `test_rag_pipeline_build_prompt_system`
  - `test_rag_pipeline_build_prompt_history`
  - `test_rag_pipeline_build_prompt_no_context`
  - `test_rag_pipeline_show_sources`
- **Success Criteria**: 10 test functions, all pass
- **Verification Command**: `pytest tests/test_rag/test_pipeline.py -v`
- **Coverage Impact**: 0% → 70% on rag/pipeline.py
- **Effort**: 3 hours
- **Dependencies**: None

### Task W5.2: RAG Pipeline - Conversation Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_rag/test_conversation.py` (new)
- **Specific Tests**:
  - `test_rag_pipeline_chat_multi_turn`
  - `test_rag_pipeline_chat_context_window`
  - `test_rag_pipeline_chat_session_persistence`
  - `test_rag_pipeline_query_rewriting`
  - `test_rag_pipeline_query_rewriting_failure`
  - `test_rag_pipeline_session_creation`
  - `test_rag_pipeline_session_load`
  - `test_rag_pipeline_session_history`
  - `test_rag_pipeline_session_clear`
- **Success Criteria**: 9 test functions, all pass
- **Verification Command**: `pytest tests/test_rag/test_conversation.py -v`
- **Coverage Impact**: 0% → 85% on conversation/
- **Effort**: 3 hours
- **Dependencies**: None

### Task W5.3: RAG Pipeline - Integration Tests
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_rag/test_integration.py` (new)
- **Specific Tests**:
  - `test_rag_pipeline_query_rewriter_integration`
  - `test_rag_pipeline_ollama_health_check`
  - `test_rag_pipeline_ollama_generation`
- **Success Criteria**: 3 integration tests pass (requires Ollama)
- **Verification Command**: `pytest tests/test_rag/test_integration.py -m integration -v`
- **Coverage Impact**: 0% → 90% on rag/providers/ollama.py
- **Effort**: 2 hours
- **Dependencies**: Ollama running

## Wave 6: Example Validation (Phase 3)

### Task W6.1: Example Test Infrastructure
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_examples/__init__.py` (new), `tests/test_examples/conftest.py` (new), `tests/test_examples/test_examples.py` (new)
- **Specific Deliverables**:
  - Example runner fixture
  - Validation utilities
  - Timeout handling
  - Output capture
- **Success Criteria**: Test infrastructure works, can run examples
- **Verification Command**: `pytest tests/test_examples/ --collect-only`
- **Effort**: 2 hours
- **Dependencies**: Task W4.1 (Docker setup)

### Task W6.2: Example Tests - Basic Usage
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_examples/test_examples.py` (extend)
- **Specific Tests**:
  - `test_example_basic_usage_ingest`
  - `test_example_basic_usage_search`
  - `test_example_basic_usage_list`
  - `test_example_circuit_breaker`
  - `test_example_tracing`
- **Success Criteria**: 5 examples validated
- **Verification Command**: `pytest tests/test_examples/test_examples.py -k "basic_usage or circuit_breaker or tracing" -v`
- **Effort**: 2 hours
- **Dependencies**: Task W6.1

### Task W6.3: Example Tests - Advanced
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_examples/test_examples.py` (extend)
- **Specific Tests**:
  - `test_example_async_workflow`
  - `test_example_batch_ingestion`
  - `test_example_custom_chunking`
- **Success Criteria**: 3 examples validated
- **Verification Command**: `pytest tests/test_examples/test_examples.py -k "advanced" -v`
- **Effort**: 1.5 hours
- **Dependencies**: Task W6.1

### Task W6.4: Example Tests - Integrations
- **Category**: deep
- **Skills**: []
- **Files**: `tests/test_examples/test_examples.py` (extend)
- **Specific Tests**:
  - `test_example_flask_api`
  - `test_example_fastapi_endpoint`
- **Success Criteria**: 2 examples validated
- **Verification Command**: `pytest tests/test_examples/test_examples.py -k "integration" -v`
- **Effort**: 1.5 hours
- **Dependencies**: Task W6.1

## Wave 7: Polish (Phase 4)

### Task W7.1: Coverage Gap Analysis
- **Category**: deep
- **Skills**: []
- **Files**: All modules with <85% coverage
- **Activity**:
  - Run: `pytest --cov=secondbrain --cov-report=html`
  - Review htmlcov/ for remaining gaps
  - Add targeted tests for uncovered lines
- **Success Criteria**: Overall coverage ≥85%, critical paths ≥95%
- **Verification Command**: `pytest --cov=secondbrain --cov-report=term-missing --cov-fail-under=85`
- **Effort**: 3-5 hours
- **Dependencies**: All previous waves complete

### Task W7.2: Test Performance Optimization
- **Category**: deep
- **Skills**: []
- **Files**: `tests/conftest.py`, test fixtures
- **Optimizations**:
  - Add session-scoped fixtures
  - Optimize fixture teardown
  - Add test markers for slow tests
- **Success Criteria**: Unit tests <40s with 8 workers
- **Verification Command**: `pytest -m "not integration" -n 8 --no-cov`
- **Effort**: 2 hours
- **Dependencies**: All test files created

### Task W7.3: CI Scripts
- **Category**: deep
- **Skills**: []
- **Files**: `scripts/run_tests.sh`, `scripts/validate_examples.sh`, `scripts/run_integration_tests.sh`
- **Success Criteria**: Scripts executable, work correctly
- **Verification Command**: `./scripts/run_tests.sh fast`, `./scripts/validate_examples.sh`
- **Effort**: 1-2 hours
- **Dependencies**: All tests created

---

## Execution Strategy

**Recommended Parallel Execution**:
- **Wave 1**: 12 tasks can run in parallel (4 developers × 3 tasks each)
- **Wave 2**: 2 tasks in parallel
- **Wave 3**: 3 tasks in parallel
- **Wave 4**: Task W4.1 first, then W4.2, W4.3, W4.5 in parallel
- **Wave 5**: 3 tasks (W5.1, W5.2 parallel, W5.3 depends on Ollama)
- **Wave 6**: Task W6.1 first, then W6.2, W6.3, W6.4 in parallel
- **Wave 7**: Sequential (depends on all previous)

**Total Effort**: ~65 hours
**With 4 Developers**: ~16 hours (2 days)
**With 2 Developers**: ~32 hours (4 days)

**Success Metrics**:
- Coverage: 85%+ overall, 95%+ on CLI/Document/Domain
- Integration Tests: 25+ real service tests
- Examples Validated: 10/10
- Performance: Unit tests <40s, Integration tests <60s
