# Top 20 Uncovered Code Paths - Prioritized by Business Criticality

**Current Coverage**: 83.98% (3910/4656 statements)
**Target**: 90% | **Gap**: 6.0%

---

## 🔴 CRITICAL - Core Infrastructure (Immediate Priority)

### 1. `src/secondbrain/utils/failure_injector.py`

- **Coverage**: 28.5%
- **Statements**: 253
- **Missing Lines**: 181 lines
- **Missing**: `[38, 39, 40, 95, 96, 103, 110, 151, 152, 153]`...

**Recommended Tests**:
- Latency injection tests (lines 38-40)
- Error injection tests (lines 95-110)
- Timeout handling tests (lines 151-175)
- Circuit breaker integration tests (lines 198-237)
- Resource exhaustion tests (lines 248-300)

---

### 2. `src/secondbrain/utils/circuit_breaker.py`

- **Coverage**: 79.7%
- **Statements**: 158
- **Missing Lines**: 32 lines
- **Missing**: `[165, 166, 179, 180, 182, 183, 189, 190, 191, 192]`...

**Recommended Tests**:
- State transition tests: open→half-open (lines 165-166)
- Failure threshold tests (lines 179-195)
- Recovery logic tests (lines 223-236)
- Timeout handling tests (lines 245-258)
- Concurrent request tests (lines 273, 281)

---

### 3. `src/secondbrain/rag/pipeline.py`

- **Coverage**: 86.1%
- **Statements**: 273
- **Missing Lines**: 38 lines
- **Missing**: `[134, 135, 138, 163, 164, 165, 172, 227, 228, 229]`...

**Recommended Tests**:
- Fallback provider chain tests
- Context building error tests
- Query rewriting failure tests

---

### 4. `src/secondbrain/conversation/storage.py`

- **Coverage**: 97.9%
- **Statements**: 94
- **Missing Lines**: 2 lines
- **Missing**: `[191, 192]`


---

## ⚠️ HIGH - Low Coverage Modules (<50%)

### 1. `src/secondbrain/utils/mps_patch.py` - 35.5% coverage, 20 missing lines
**Missing**: `[33, 34, 66, 67, 69, 71, 72, 74, 75, 76]`...

## 🟡 MEDIUM - Moderate Coverage Gaps (50-99%)

### 1. `src/secondbrain/rag/interfaces.py` - 62.5% coverage, 3 missing lines
### 2. `src/secondbrain/domain/interfaces.py` - 67.7% coverage, 10 missing lines
### 3. `src/secondbrain/utils/tracing.py` - 72.0% coverage, 72 missing lines
### 4. `src/secondbrain/search/__init__.py` - 72.9% coverage, 23 missing lines
### 5. `src/secondbrain/document/__init__.py` - 73.7% coverage, 220 missing lines
### 6. `src/secondbrain/rag/providers/anthropic.py` - 80.0% coverage, 12 missing lines
### 7. `src/secondbrain/utils/docker_manager.py` - 81.4% coverage, 24 missing lines

---

## Summary & Effort Estimation

- **Total files with gaps**: 23
- **Critical priority**: 4 files
- **High priority (<50%)**: 1 files
- **Medium priority (50-90%)**: 8 files

### Estimated Effort to Reach 90%

| Priority | Effort | Impact |
|----------|--------|--------|
| Critical | 8-12h | Core reliability |
| High | 15-20h | Edge case coverage |
| Medium | 20-30h | Comprehensive coverage |
| **Total** | **43-62h** | **+6% coverage** |
