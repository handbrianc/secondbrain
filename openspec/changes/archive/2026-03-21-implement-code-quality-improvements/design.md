## Context

The SecondBrain CLI tool currently has excellent code quality but lacks several production-grade features. The codebase uses synchronous MongoDB operations wrapped with `asyncio.to_thread()`, has minimal resilience patterns, and lacks comprehensive documentation for its 30+ configuration options. Type checking fails due to missing mypy overrides for third-party packages.

**Current State:**
- Synchronous `pymongo` with `asyncio.to_thread()` wrapper for async operations
- Basic retry logic in `ValidatableService` without circuit breaker pattern
- Rich text logging with optional JSON formatter (not fully implemented)
- No distributed tracing or observability instrumentation
- Limited test coverage for edge cases and failure scenarios

**Constraints:**
- Must maintain backward compatibility with existing sync API
- Python 3.11+ requirement
- MongoDB 8.0+ with Atlas Vector Search
- sentence-transformers API for embeddings
- Minimal dependency bloat

## Goals / Non-Goals

**Goals:**
1. Fix type checking errors with proper mypy configuration
2. Create comprehensive, centralized configuration documentation
3. Implement circuit breaker pattern for service resilience
4. Provide true async API using `motor` (async MongoDB driver)
5. Add structured JSON logging with request correlation
6. Document complex algorithms with "why" comments
7. Add property-based testing for critical paths
8. Integrate OpenTelemetry for observability
9. Add chaos and concurrency testing
10. Improve dependency security scanning

**Non-Goals:**
- Rewrite existing sync API (keep for backward compatibility)
- Replace MongoDB (stay with Atlas Vector Search)
- Add GraphQL or REST API (stay CLI-focused)
- Implement full microservices architecture
- Add Kubernetes deployment automation

## Decisions

### 1. Circuit Breaker Pattern Implementation

**Decision:** Create `utils/circuit_breaker.py` with state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)

**Rationale:**
- Existing `RateLimitedRetry` only handles retries, not cascading failures
- Circuit breaker prevents overwhelming failing services
- State machine pattern is well-understood and testable
- Allows gradual recovery with half-open state

**Alternatives Considered:**
- Use `pybreaker` library: Would add external dependency, less control
- Extend `RateLimitedRetry`: Would blur responsibilities, less clear semantics

**State Machine:**
```
CLOSED (normal) --failures≥threshold--> OPEN (fail fast)
OPEN --timeout elapsed--> HALF_OPEN (test recovery)
HALF_OPEN --success--> CLOSED
HALF_OPEN --failure--> OPEN
```

### 2. Async MongoDB Driver

**Decision:** Use `motor` (official async MongoDB driver) instead of `aio-pymongo` or `asyncio.to_thread()`

**Rationale:**
- Motor is officially supported by MongoDB
- Native async/await API (no thread blocking)
- Better performance than `asyncio.to_thread()` wrapper
- Maintains pymongo API familiarity

**Alternatives Considered:**
- Keep `asyncio.to_thread()`: Simple but blocks event loop
- `aio-pymongo`: Less mature, smaller community

**Migration Strategy:**
- Create `AsyncVectorStorage` class alongside existing `VectorStorage`
- Use `motor.motor_asyncio.AsyncIOMotorClient`
- Keep sync API for backward compatibility
- Deprecate `asyncio.to_thread()` wrappers over time

### 3. Structured Logging

**Decision:** Extend existing `logging/__init__.py` with JSON formatter, add request ID via context vars

**Rationale:**
- Already have `setup_json_logging()` (partially implemented)
- Context vars work with async (unlike thread locals)
- Rich library already in dependencies
- Minimal new dependencies

**Implementation:**
- Use `logging.Formatter` subclass for JSON output
- Add `request_id` to all log records via context var
- Configurable via `SECONDBRAIN_LOG_FORMAT=json|rich`
- Standardize log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### 4. OpenTelemetry Integration

**Decision:** Use `opentelemetry-api` and `opentelemetry-sdk` with OTLP exporter

**Rationale:**
- Industry standard for distributed tracing
- Vendor-neutral (can export to Jaeger, Zipkin, Datadog, etc.)
- Minimal overhead when disabled
- Auto-instrumentation available for HTTP, MongoDB

**Instrumentation Points:**
- Document ingestion pipeline (timing per file)
- Search queries (embedding generation, MongoDB aggregation)
- Storage operations (insert, delete, batch operations)
- External service calls (sentence-transformers API)

**Alternatives Considered:**
- Custom tracing: Would reinvent wheel, vendor lock-in
- Prometheus only: Good for metrics, no distributed tracing

### 5. Property-Based Testing

**Decision:** Use `hypothesis` library for property-based tests

**Rationale:**
- Industry standard for property-based testing in Python
- Integrates with pytest
- Automatic test case minimization
- Good for testing edge cases in chunking, sanitization

**Test Targets:**
- Query sanitization (no injection attacks)
- Chunking logic (no text loss, proper overlap)
- Config validation (boundary conditions)
- Embedding cache behavior

### 6. Documentation Structure

**Decision:** Centralize config docs in `docs/getting-started/configuration.md` with auto-generated API docs via mkdocstrings

**Rationale:**
- Pydantic models already have Field descriptions
- mkdocstrings can extract from docstrings
- Single source of truth for config options
- Easier to maintain than scattered docs

**Structure:**
```
docs/
├── getting-started/
│   └── configuration.md  # Central config reference
├── api/                  # Auto-generated API docs
│   ├── circuit_breaker.md
│   ├── document.md
│   ├── storage.md
│   └── ...
└── developer-guide/
    └── async-api.md      # Updated with AsyncDocumentIngestor
```

## Risks / Trade-offs

**Risk:** Motor async driver may have compatibility issues with existing pymongo code

→ **Mitigation:** Maintain both sync and async APIs side-by-side, thorough integration testing

**Risk:** Circuit breaker adds complexity to connection handling

→ **Mitigation:** Clear state machine diagrams, comprehensive unit tests for all states

**Risk:** OpenTelemetry adds dependencies and potential performance overhead

→ **Mitigation:** Make tracing opt-in via config, benchmark overhead, lazy initialization

**Risk:** Property-based tests may generate unrealistic test cases

→ **Mitigation:** Carefully define constraints in Hypothesis strategies, review generated examples

**Risk:** Documentation maintenance burden

→ **Mitigation:** Auto-generate API docs from docstrings, CI check to ensure docs stay in sync

## Migration Plan

**Phase 1: Foundation (Week 1)**
1. Fix mypy configuration
2. Add comprehensive config documentation
3. Document complex algorithms with "why" comments

**Phase 2: Resilience (Week 2)**
1. Implement circuit breaker pattern
2. Wire into `ValidatableService`
3. Add unit and integration tests

**Phase 3: Async API (Week 3)**
1. Create `AsyncVectorStorage` with Motor
2. Create `AsyncDocumentIngestor`
3. Update async-api.md documentation

**Phase 4: Observability (Week 4)**
1. Implement structured JSON logging
2. Add OpenTelemetry integration
3. Instrument key paths

**Phase 5: Testing (Week 5)**
1. Add property-based tests
2. Add chaos and concurrency tests
3. Update CI/CD with security scanning

**Rollback Strategy:**
- All changes are additive (no breaking changes)
- Feature flags for new functionality
- Can disable circuit breaker, tracing via config
- Async API is opt-in

## Open Questions

1. Should we use `motor` or explore `pymongo-async` (newer async support in pymongo 4.7+)?
2. What's the default circuit breaker threshold? (Suggest: 5 failures, 30s timeout)
3. Which OpenTelemetry exporter to recommend by default? (OTLP is most flexible)
4. Should property-based tests run in CI or only locally? (Suggest: local only, too slow for CI)
