# Capability Spec Archive

These 8 capability specs were archived on **2026-10-14** after a two-axis compliance
verification (code evidence + test proof, per requirement). The ratings below distinguish
implemented requirements from incomplete proof and missing required behavior. Archiving
preserves the specs as historical records; it does not imply full compliance. To restore one,
move it back: `git mv openspec/archive/<name> openspec/specs/<name>`.

## Verification dashboard (2026-10-14)

| Spec | Reqs | Fully compliant | Partial | Non-compliant |
|---|---|---|---|---|
| async-ingestor | 7 | 5 | 2 | 0 |
| chaos-testing | 6 | 2 | 3 | 1 |
| circuit-breaker | 6 | 6 | 0 | 0 |
| dependency-security | 6 | 1 | 4 | 1 |
| multicore-ingestion | 11 | 6 | 5 | 0 |
| opentelemetry-integration | 8 | 6 | 2 | 0 |
| property-testing | 5 | 4 | 1 | 0 |
| structured-logging | 6 | 4 | 2 | 0 |
| **Total** | **55** | **34 (62%)** | **19** | **2** |

“Partial” means the required behavior is implemented, but test proof is incomplete or there
is a minor drift item. “Non-compliant” means at least one required behavior is missing.
Verification note: 7 of 8 files used OpenSpec change-delta format
(`## ADDED Requirements`, no `## Purpose`) and did not pass `openspec validate`; only
`multicore-ingestion` was properly formatted. This is a historical format artifact, not a
compliance problem.

## Non-compliant requirements at retirement

1. **dependency-security — CycloneDX SBOM generation**: pre-commit generates an SBOM, but
   there is no comparison step for unexpected changes, so the second scenario's SHALL is unmet.
2. **chaos-testing — Chaos test reporting**: `register_chaos_result`
   (`tests/test_chaos/conftest.py`) is never called by any chaos test, so the aggregated report
   is never emitted and the report scenario's SHALLs are unmet.

## Other residual findings at retirement

### MEDIUM

1. **chaos-testing**: `TestChaosResilienceMetrics` (`tests/test_chaos/test_chaos_advanced.py:182`)
   lacks `@pytest.mark.chaos`, so `-m chaos` deselects it while the default run includes it.
2. **chaos-testing**: search-unavailability test (`tests/test_search/test_searcher.py:139-142`)
   asserts inside a try/except and can pass vacuously if the call stops raising.
3. **async-ingestor**: drift — `__aenter__` initializes nothing and `__aexit__` is a no-op
   (`document/ingestor/_async.py:63-74`); cleanup actually lives in `ingest_async.finally`,
   so exiting `async with` does not close connections.
4. **multicore-ingestion**: `ProcessPoolExecutor` never instantiated for real in tests —
   every pool test monkeypatches a fake executor, so real OS-process concurrency
   (MI-R3/R4) is proven only via pool-selection and worker-count assertions.
5. **multicore-ingestion**: pickling test (`test_multicore_edge_cases.py:53-65`) pickles the
   thread-pool worker `_extract_and_chunk_file`, not the process-pool worker
   `_extract_chunk_and_embed_file` actually submitted to the pool.
6. **opentelemetry-integration**: no test asserts the TracerProvider resource carries
   `service.name` or that export is asynchronous (BatchSpanProcessor);
   `test_tracing.py:101-113` calls real `setup_tracing` but asserts nothing.
7. **structured-logging**: amended default level (WARNING, `logging/__init__.py:142`) is
   untested — no assertion of default WARNING or INFO-recorded-but-hidden.

### LOW

1. **dependency-security**: spec note drift — note says `-w fail`, script uses
   `-w silence` + `python -m pip check` (`scripts/security_scan.sh:131-132`).
2. **dependency-security**: stale Dependabot group patterns (pymongo, motor,
   python-dotenv, sentence-transformers, torch) absent from current pyproject deps.
3. **dependency-security**: `security_scan.sh:97` mislabels CycloneDX output as "SPDX JSON".
4. **async-ingestor**: async result hardwires `skipped=0` (no re-ingest skip detection).
5. **multicore-ingestion**: "serialization errors caught" sub-scenario untested directly.
6. **multicore-ingestion**: "identical to previous versions" scenario untestable by design.
7. **opentelemetry-integration**: async-context propagation proven only against raw OTel
   SDK, not secondbrain's contextvar path (`test_otel_integration.py:364-410`).
8. **opentelemetry-integration**: `test_otel_metrics.py` is simulated with different
   instrument names; real proof is `test_otel_integration.py:412-499`.
9. **structured-logging**: request_id appears only in JSON transport, not Rich output.
10. **structured-logging**: CLI `--verbose → DEBUG` wiring not asserted through click.
11. **property-testing**: chunking property tests use `max_examples` values of 30, 10, and
    30, below the spec's 100-per-property requirement. The overlap property also skips cases
    where either chunk is too short or the detected overlap is more than 10 characters below
    the configured value, so it does not prove exact configured overlap.
