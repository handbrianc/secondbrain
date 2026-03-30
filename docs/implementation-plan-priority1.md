# Priority 1 Implementation Plan

**Target**: Increase SecondBrain score from 8.8 to 9.0+  
**Timeline**: Week 1-2 (Critical Sprint)  
**Status**: Ready for Implementation

---

## Executive Summary

This document provides a detailed, step-by-step implementation plan for all Priority 1 items from the roadmap. Each item includes:
- Specific files to modify
- Test cases to add
- Content to create
- Effort estimates
- Verification criteria

---

## Item 1.1: Increase Branch Coverage from 88% to 90%

### Impact
- **Category**: Testing (8.8 → 9.0)
- **Score Impact**: +0.2
- **Effort**: M (1-2 days)

### Current State Analysis

**Low Coverage Modules**:
- `utils/tracing.py`: 78% branch coverage
- `rag/interfaces.py`: 62% branch coverage  
- `utils/memory_utils.py`: 35% branch coverage

**Coverage Gap**: 2% (need ~17 additional branches covered)

### Files to Modify

#### Test Files to Create/Update:
1. **`tests/test_utils/test_memory_utils.py`** (NEW - doesn't exist)
   - Must cover all platform-specific code paths
   - Must test error handling and edge cases

2. **`tests/test_utils/test_tracing.py`** (EXISTING - needs expansion)
   - Add tests for error paths in `setup_tracing()`
   - Add tests for `trace_decorator()` function
   - Add tests for `shutdown_tracing()` edge cases

3. **`tests/test_rag/test_interfaces.py`** (NEW - may not exist)
   - Test protocol implementations
   - Test error conditions

### Specific Test Cases to Add

#### For `memory_utils.py` (Priority: HIGH - 35% coverage)

**File**: `tests/test_utils/test_memory_utils.py` (CREATE)

```python
"""Tests for memory management utilities."""

import pytest
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

from secondbrain.utils.memory_utils import (
    get_available_memory_gb,
    get_memory_limit_gb,
    calculate_safe_worker_count,
    get_current_memory_usage_mb,
    set_memory_limit_mb,
    check_memory_sufficient,
    MemoryMonitor,
)


class TestGetAvailableMemory:
    """Tests for get_available_memory_gb."""

    def test_linux_proc_meminfo_exists(self):
        """Should read from /proc/meminfo on Linux when available."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open_read_data('MemTotal: 16384000 kB\n')):
                with patch('sys.platform', 'linux'):
                    mem_gb = get_available_memory_gb()
                    assert mem_gb == pytest.approx(15.0, rel=0.1)

    def test_linux_proc_meminfo_not_exists(self):
        """Should fallback on Linux when /proc/meminfo doesn't exist."""
        with patch('pathlib.Path.exists', return_value=False):
            with patch('sys.platform', 'linux'):
                with patch('psutil.virtual_memory') as mock_psutil:
                    mock_psutil.return_value.total = 8 * 1024 * 1024 * 1024
                    mem_gb = get_available_memory_gb()
                    assert mem_gb == pytest.approx(8.0, rel=0.1)

    def test_darwin_sysctl_success(self):
        """Should use sysctl on macOS when successful."""
        with patch('sys.platform', 'darwin'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value.stdout = "17179869184\n"  # 16GB
                mem_gb = get_available_memory_gb()
                assert mem_gb == pytest.approx(16.0, rel=0.1)

    def test_darwin_sysctl_failure_fallback(self):
        """Should fallback when sysctl fails on macOS."""
        with patch('sys.platform', 'darwin'):
            with patch('subprocess.run', side_effect=Exception("Failed")):
                with patch('psutil.virtual_memory') as mock_psutil:
                    mock_psutil.return_value.total = 8 * 1024 * 1024 * 1024
                    mem_gb = get_available_memory_gb()
                    assert mem_gb == pytest.approx(8.0, rel=0.1)

    def test_psutil_not_available_fallback(self):
        """Should return default 8GB when psutil not available."""
        with patch('sys.platform', 'linux'):
            with patch('pathlib.Path.exists', return_value=False):
                with patch('importlib.import_module', side_effect=ImportError):
                    mem_gb = get_available_memory_gb()
                    assert mem_gb == 8.0


class TestGetMemoryLimit:
    """Tests for get_memory_limit_gb."""

    def test_default_80_percent(self):
        """Should use 80% by default."""
        with patch('secondbrain.utils.memory_utils.get_available_memory_gb', return_value=16.0):
            limit = get_memory_limit_gb()
            assert limit == 12.8

    def test_custom_percentage(self):
        """Should use custom percentage."""
        with patch('secondbrain.utils.memory_utils.get_available_memory_gb', return_value=16.0):
            limit = get_memory_limit_gb(percentage=0.5)
            assert limit == 8.0

    def test_zero_percentage(self):
        """Should handle zero percentage."""
        with patch('secondbrain.utils.memory_utils.get_available_memory_gb', return_value=16.0):
            limit = get_memory_limit_gb(percentage=0.0)
            assert limit == 0.0


class TestCalculateSafeWorkerCount:
    """Tests for calculate_safe_worker_count."""

    def test_calculates_by_memory(self):
        """Should calculate workers based on memory limit."""
        workers = calculate_safe_worker_count(
            memory_limit_gb=4.0,
            estimated_memory_per_worker_gb=0.5
        )
        assert workers == 8

    def test_enforces_min_workers(self):
        """Should enforce minimum workers."""
        workers = calculate_safe_worker_count(
            memory_limit_gb=0.1,
            estimated_memory_per_worker_gb=0.5,
            min_workers=2
        )
        assert workers >= 2

    def test_enforces_max_workers(self):
        """Should enforce maximum workers."""
        workers = calculate_safe_worker_count(
            memory_limit_gb=100.0,
            estimated_memory_per_worker_gb=0.5,
            max_workers=4
        )
        assert workers == 4

    def test_zero_memory_limit_fallback(self):
        """Should use fallback when memory limit is zero."""
        workers = calculate_safe_worker_count(
            memory_limit_gb=0,
            estimated_memory_per_worker_gb=0.5
        )
        assert workers >= 1

    def test_negative_memory_limit_fallback(self):
        """Should use fallback when memory limit is negative."""
        workers = calculate_safe_worker_count(
            memory_limit_gb=-1.0,
            estimated_memory_per_worker_gb=0.5
        )
        assert workers >= 1


class TestGetCurrentMemoryUsage:
    """Tests for get_current_memory_usage_mb."""

    def test_linux_macos_success(self):
        """Should get memory usage on Linux/macOS."""
        with patch('sys.platform', 'linux'):
            with patch('resource.getrusage') as mock_usage:
                mock_usage.return_value.ru_maxrss = 102400  # 100MB in KB
                usage_mb = get_current_memory_usage_mb()
                assert usage_mb == 100.0

    def test_platform_not_supported_fallback(self):
        """Should fallback when platform not supported."""
        with patch('sys.platform', 'win32'):
            with patch('psutil.Process') as mock_process:
                mock_process.return_value.memory_info.return_value.rss = 104857600
                usage_mb = get_current_memory_usage_mb()
                assert usage_mb == 100.0

    def test_psutil_not_available_returns_zero(self):
        """Should return 0.0 when psutil not available."""
        with patch('sys.platform', 'win32'):
            with patch('importlib.import_module', side_effect=ImportError):
                usage_mb = get_current_memory_usage_mb()
                assert usage_mb == 0.0


class TestSetMemoryLimit:
    """Tests for set_memory_limit_mb."""

    def test_sets_limit_successfully(self):
        """Should set memory limit successfully on Linux/macOS."""
        with patch('sys.platform', 'linux'):
            with patch('resource.getrlimit', return_value=(1024, 2048)):
                with patch('resource.setrlimit', return_value=None):
                    result = set_memory_limit_mb(1024.0)
                    assert result is True

    def test_returns_false_on_windows(self):
        """Should return False on Windows."""
        with patch('sys.platform', 'win32'):
            result = set_memory_limit_mb(1024.0)
            assert result is False

    def test_returns_false_on_exception(self):
        """Should return False when exception occurs."""
        with patch('sys.platform', 'linux'):
            with patch('resource.getrlimit', side_effect=Exception("Failed")):
                result = set_memory_limit_mb(1024.0)
                assert result is False


class TestCheckMemorySufficient:
    """Tests for check_memory_sufficient."""

    def test_memory_sufficient(self):
        """Should return True when memory is sufficient."""
        result = check_memory_sufficient(
            required_gb=4.0,
            memory_limit_gb=10.0,
            safety_margin=1.2
        )
        assert result is True

    def test_memory_insufficient(self):
        """Should return False when memory is insufficient."""
        result = check_memory_sufficient(
            required_gb=10.0,
            memory_limit_gb=10.0,
            safety_margin=1.2
        )
        assert result is False

    def test_exactly_at_limit_with_margin(self):
        """Should handle exact limit with safety margin."""
        result = check_memory_sufficient(
            required_gb=8.33,  # 10 / 1.2
            memory_limit_gb=10.0,
            safety_margin=1.2
        )
        assert result is True


class TestMemoryMonitor:
    """Tests for MemoryMonitor class."""

    def test_init_sets_attributes(self):
        """Should initialize with correct attributes."""
        monitor = MemoryMonitor(memory_limit_gb=8.0, warning_threshold=0.9)
        assert monitor.memory_limit_gb == 8.0
        assert monitor.warning_threshold == 0.9
        assert monitor._peak_usage_mb == 0.0

    def test_check_and_warn_returns_true_when_safe(self):
        """Should return True when memory usage is safe."""
        with patch('secondbrain.utils.memory_utils.get_current_memory_usage_mb', return_value=1024):
            monitor = MemoryMonitor(memory_limit_gb=8.0)
            result = monitor.check_and_warn()
            assert result is True

    def test_check_and_warn_returns_false_when_warning(self):
        """Should return False and warn when approaching limit."""
        with patch('secondbrain.utils.memory_utils.get_current_memory_usage_mb', return_value=7000):
            monitor = MemoryMonitor(memory_limit_gb=8.0, warning_threshold=0.8)
            result = monitor.check_and_warn()
            assert result is False

    def test_tracks_peak_usage(self):
        """Should track peak memory usage."""
        with patch('secondbrain.utils.memory_utils.get_current_memory_usage_mb') as mock_usage:
            mock_usage.side_effect = [1000, 2000, 1500]
            monitor = MemoryMonitor(memory_limit_gb=8.0)
            
            monitor.check_and_warn()
            monitor.check_and_warn()
            monitor.check_and_warn()
            
            assert monitor._peak_usage_mb == 2000

    def test_get_usage_stats_returns_dict(self):
        """Should return dictionary with usage statistics."""
        with patch('secondbrain.utils.memory_utils.get_current_memory_usage_mb', return_value=4096):
            monitor = MemoryMonitor(memory_limit_gb=8.0)
            stats = monitor.get_usage_stats()
            
            assert 'current_mb' in stats
            assert 'current_gb' in stats
            assert 'limit_gb' in stats
            assert 'usage_ratio' in stats
            assert 'usage_percent' in stats
            assert 'peak_mb' in stats
            assert stats['current_mb'] == 4096
            assert stats['limit_gb'] == 8.0
```

#### For `tracing.py` (Priority: MEDIUM - 78% coverage)

**File**: `tests/test_utils/test_tracing.py` (EXPAND)

Add these test classes to existing file:

```python
class TestTraceDecorator:
    """Tests for trace_decorator."""

    def test_decorator_when_opentelemetry_not_available(self):
        """Should call function normally when OpenTelemetry not available."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            from secondbrain.utils.tracing import trace_decorator
            
            @trace_decorator("test_op")
            def test_func():
                return "result"
            
            result = test_func()
            assert result == "test_func"

    def test_decorator_when_tracing_disabled(self):
        """Should call function normally when tracing disabled."""
        os.environ.pop("OTEL_TRACING_ENABLED", None)
        from secondbrain.utils import tracing
        tracing._tracing_enabled = False
        
        from secondbrain.utils.tracing import trace_decorator
        
        @trace_decorator("test_op")
        def test_func():
            return "result"
        
        result = test_func()
        assert result == "result"

    def test_decorator_sets_span_attribute(self):
        """Should set function name attribute on span when enabled."""
        os.environ["OTEL_TRACING_ENABLED"] = "true"
        from secondbrain.utils import tracing
        tracing._tracer = None
        tracing._tracing_enabled = False
        
        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace") as mock_trace,
        ):
            mock_span_instance = MagicMock()
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span_instance)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_trace.get_tracer.return_value.start_as_current_span.return_value = mock_span
            
            from secondbrain.utils.tracing import trace_decorator
            
            @trace_decorator("test_operation")
            def test_func():
                return "result"
            
            result = test_func()
            assert result == "result"


class TestShutdownTracingEdgeCases:
    """Additional tests for shutdown_tracing edge cases."""

    def test_noop_when_tracer_is_none(self):
        """Should be a no-op when tracer is None."""
        from secondbrain.utils import tracing
        tracing._tracer = None
        tracing._tracing_enabled = True
        
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True):
            shutdown_tracing()
            assert tracing._tracing_enabled is False

    def test_handles_otel_trace_none(self):
        """Should handle when otel_trace is None."""
        from secondbrain.utils import tracing
        tracing._tracer = "test"
        tracing._tracing_enabled = True
        
        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace", None),
        ):
            shutdown_tracing()

    def test_catches_exception_during_shutdown(self, caplog):
        """Should log warning on exception during shutdown."""
        from secondbrain.utils import tracing
        tracing._tracer = "test"
        tracing._tracing_enabled = True
        
        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace") as mock_trace,
            patch("secondbrain.utils.tracing.TracerProvider") as mock_provider,
        ):
            mock_provider.return_value.shutdown.side_effect = Exception("Shutdown failed")
            
            with caplog.at_level("WARNING"):
                shutdown_tracing()
                assert any("Error during OpenTelemetry shutdown" in msg for msg in caplog.messages)
```

#### For `interfaces.py` (Priority: LOW - Protocol, minimal testing needed)

**File**: `tests/test_rag/test_interfaces.py` (CREATE)

```python
"""Tests for LLM provider interfaces."""

import pytest
from unittest.mock import MagicMock, patch

from secondbrain.rag.interfaces import LocalLLMProvider


class TestLocalLLMProviderProtocol:
    """Tests for LocalLLMProvider protocol."""

    def test_protocol_requires_generate(self):
        """Protocol should require generate method."""
        assert hasattr(LocalLLMProvider, 'generate')

    def test_protocol_requires_agenerate(self):
        """Protocol should require agenerate method."""
        assert hasattr(LocalLLMProvider, 'agenerate')

    def test_protocol_requires_health_check(self):
        """Protocol should require health_check method."""
        assert hasattr(LocalLLMProvider, 'health_check')

    def test_generate_signature(self):
        """Should verify generate method signature."""
        import inspect
        sig = inspect.signature(LocalLLMProvider.generate)
        params = list(sig.parameters.keys())
        assert 'prompt' in params
        assert 'temperature' in params
        assert 'max_tokens' in params

    def test_agenerate_signature(self):
        """Should verify agenerate method signature."""
        import inspect
        sig = inspect.signature(LocalLLMProvider.agenerate)
        params = list(sig.parameters.keys())
        assert 'prompt' in params
        assert 'temperature' in params
        assert 'max_tokens' in params

    def test_health_check_signature(self):
        """Should verify health_check method signature."""
        import inspect
        sig = inspect.signature(LocalLLMProvider.health_check)
        params = list(sig.parameters.keys())
        assert len(params) == 1  # Only self


class TestProviderImplementation:
    """Tests for provider implementations."""

    def test_mock_provider_implementation(self):
        """Should verify a mock provider implements the protocol."""
        from secondbrain.rag.interfaces import LocalLLMProvider
        
        class MockProvider:
            def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
                return "mock response"
            
            async def agenerate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
                return "mock async response"
            
            def health_check(self) -> bool:
                return True
        
        provider = MockProvider()
        
        # Check protocol conformance
        assert isinstance(provider, LocalLLMProvider)
        assert provider.generate("test") == "mock response"
        assert provider.health_check() is True
```

### Verification Criteria

1. **Run branch coverage check**:
   ```bash
   pytest tests/ --cov=src/secondbrain --cov-report=term-missing --cov-branch -q
   ```

2. **Target**: Branch coverage ≥ 90%

3. **Specific modules**:
   - `utils/tracing.py`: ≥ 85%
   - `rag/interfaces.py`: ≥ 80%
   - `utils/memory_utils.py`: ≥ 80%

4. **All tests passing**: `pytest -q` should show 1207+ tests passing

---

## Item 1.2: Security Vulnerability Documentation (Threat Model)

### Impact
- **Category**: Security/Performance (8.5 → 8.8)
- **Score Impact**: +0.3
- **Effort**: S (2-4 hours)

### Files to Create

**`docs/security/THREAT_MODEL.md`** (NEW)

Content to be generated by background agent (see `bg_e6a2cf19`).

### Files to Update

1. **`docs/security/index.md`** - Add link to threat model
2. **`SECURITY.md`** - Reference threat model

### Verification Criteria

1. Threat model document exists at `docs/security/THREAT_MODEL.md`
2. Document covers all OWASP Top 10 categories
3. Document includes attack vectors for document processing
4. Document defines security boundaries and trust models
5. Link added to security index

---

## Item 1.3: Performance Regression CI Automation

### Impact
- **Category**: Security/Performance (8.5 → 8.7)
- **Score Impact**: +0.2
- **Effort**: S (2-4 hours)

### Files to Create/Modify

1. **`.pre-commit-config.yaml`** (MODIFY - add benchmark hook)
2. **`scripts/run_benchmarks.sh`** (NEW - benchmark runner script)
3. **`scripts/compare_benchmarks.py`** (NEW - regression comparator)
4. **`docs/user-guide/performance-testing.md`** (NEW - documentation)

### Implementation Details

#### Pre-commit Hook Configuration

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  # ... existing hooks ...
  
  - repo: local
    hooks:
      - id: benchmark-regression
        name: Check Benchmark Regression
        entry: bash scripts/run_benchmarks.sh
        language: system
        pass_filenames: false
        stages: [manual]  # Run manually before PR
        description: "Run benchmarks and check for >10% regression"
```

#### Benchmark Runner Script

Create `scripts/run_benchmarks.sh`:

```bash
#!/bin/bash
# Run benchmarks and compare against baseline

set -e

BASELINE_FILE=".benchmarks/baseline.json"
CURRENT_FILE=".benchmarks/current.json"
REGRESSION_THRESHOLD=10  # 10%

echo "🏃 Running benchmarks..."

# Run benchmarks and save results
pytest benchmarks/ \
  --benchmark-only \
  --benchmark-save=current \
  --benchmark-storage=file://./.benchmarks

# Check if baseline exists
if [ ! -f "$BASELINE_FILE" ]; then
    echo "⚠️  No baseline found. Creating initial baseline."
    mv .benchmarks/current_*.json "$BASELINE_FILE"
    echo "✅ Baseline created at $BASELINE_FILE"
    exit 0
fi

# Compare against baseline
echo "📊 Comparing against baseline..."
python scripts/compare_benchmarks.py \
  --baseline "$BASELINE_FILE" \
  --current ".benchmarks/current_*.json" \
  --threshold "$REGRESSION_THRESHOLD"

if [ $? -eq 0 ]; then
    echo "✅ No significant regression detected"
else
    echo "❌ Performance regression detected! Check output above."
    exit 1
fi
```

#### Benchmark Comparator Script

Create `scripts/compare_benchmarks.py`:

```python
#!/usr/bin/env python3
"""Compare benchmark results and detect regressions."""

import argparse
import json
import glob
import sys
from pathlib import Path


def load_benchmark_results(pattern: str) -> dict:
    """Load benchmark results from file pattern."""
    results = {}
    
    for file_path in glob.glob(pattern):
        with open(file_path, 'r') as f:
            data = json.load(f)
            for bench in data.get('benchmarks', []):
                name = bench['name']
                results[name] = {
                    'mean': bench['stats']['mean'],
                    'stddev': bench['stats']['stddev'],
                    'iterations': bench['stats']['iterations'],
                }
    
    return results


def compare_results(
    baseline: dict,
    current: dict,
    threshold: float
) -> tuple[bool, list[str]]:
    """Compare current results against baseline.
    
    Returns:
        Tuple of (passed, list of regression messages)
    """
    regressions = []
    
    for name, current_stats in current.items():
        if name not in baseline:
            continue
        
        baseline_stats = baseline[name]
        baseline_mean = baseline_stats['mean']
        current_mean = current_stats['mean']
        
        if baseline_mean == 0:
            continue
        
        regression_pct = ((current_mean - baseline_mean) / baseline_mean) * 100
        
        if regression_pct > threshold:
            regressions.append(
                f"⚠️  {name}: {regression_pct:.1f}% slower "
                f"({baseline_mean*1000:.2f}ms → {current_mean*1000:.2f}ms)"
            )
    
    return len(regressions) == 0, regressions


def main():
    parser = argparse.ArgumentParser(description='Compare benchmark results')
    parser.add_argument('--baseline', required=True, help='Baseline results file')
    parser.add_argument('--current', required=True, help='Current results pattern')
    parser.add_argument('--threshold', type=float, default=10.0,
                        help='Regression threshold (percent)')
    parser.add_argument('--verbose', action='store_true',
                        help='Show all comparisons')
    
    args = parser.parse_args()
    
    # Load results
    baseline = load_benchmark_results(args.baseline)
    current = load_benchmark_results(args.current)
    
    if not baseline:
        print("❌ No baseline results found")
        sys.exit(1)
    
    if not current:
        print("❌ No current results found")
        sys.exit(1)
    
    # Compare
    passed, regressions = compare_results(baseline, current, args.threshold)
    
    if args.verbose:
        print(f"\nBaseline benchmarks: {len(baseline)}")
        print(f"Current benchmarks: {len(current)}")
        print(f"Regression threshold: {args.threshold}%")
        print("-" * 60)
    
    if regressions:
        print("\n📉 Performance Regressions Detected:\n")
        for reg in regressions:
            print(reg)
        print()
        sys.exit(1)
    else:
        print("✅ No performance regressions detected")
        sys.exit(0)


if __name__ == '__main__':
    main()
```

### Verification Criteria

1. **Benchmark script exists**: `scripts/run_benchmarks.sh` is executable
2. **Comparator script exists**: `scripts/compare_benchmarks.py` works correctly
3. **Baseline can be created**: First run creates baseline
4. **Regression detection works**: Simulate regression and verify detection
5. **Documentation complete**: `docs/user-guide/performance-testing.md` exists

---

## Item 1.4: Complete Remaining Documentation (10 Functions)

### Impact
- **Category**: Documentation (8.5 → 8.7)
- **Score Impact**: +0.2
- **Effort**: S (2-4 hours)

### Files to Modify

Background agent (`bg_f4743c42`) will identify specific functions.

Expected pattern - add numpy-style docstrings to public functions missing them:

```python
def function_name(
    param1: type,
    param2: type = default
) -> return_type:
    """Short description.

    Long description.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ExceptionType: When exception occurs.

    Example:
        >>> result = function_name(arg1)
        >>> print(result)
    """
```

### Verification Criteria

1. **Docstring coverage check**:
   ```bash
   python -c "
   import ast
   from pathlib import Path
   total = documented = 0
   for py_file in Path('src/secondbrain').rglob('*.py'):
       if 'test' in str(py_file) or '__pycache__' in str(py_file): continue
       tree = ast.parse(py_file.read_text())
       for node in ast.walk(tree):
           if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
               if node.name.startswith('_') or node.name.startswith('test_'): continue
               total += 1
               docstring = ast.get_docstring(node)
               if docstring:
                   documented += 1
   print(f'Total: {total}, Documented: {documented}, Coverage: {documented/total*100:.1f}%')
   "
   ```

2. **Target**: 100% docstring coverage for public functions

3. **All docstrings follow numpy style** (verified by ruff D rules)

---

## Summary of Effort Estimates

| Item | Effort | Duration | Files Modified | Files Created |
|------|--------|----------|----------------|---------------|
| 1.1 Branch Coverage | M | 1-2 days | 1 | 2 |
| 1.2 Threat Model | S | 2-4 hours | 2 | 1 |
| 1.3 Benchmark CI | S | 2-4 hours | 1 | 3 |
| 1.4 Documentation | S | 2-4 hours | ~10 | 0 |
| **TOTAL** | **M** | **2-3 days** | **~14** | **6** |

---

## Verification Checklist

After implementing all Priority 1 items:

- [ ] Branch coverage ≥ 90% (run: `pytest --cov-branch`)
- [ ] All 1207+ tests passing (run: `pytest -q`)
- [ ] Threat model exists at `docs/security/THREAT_MODEL.md`
- [ ] Benchmark scripts executable and working
- [ ] Docstring coverage ≥ 98% for public functions
- [ ] No linting errors (run: `ruff check .`)
- [ ] No type errors (run: `mypy .`)
- [ ] Security scans clean (run: `bandit -r src/`)

---

## Next Steps

1. **Start with Item 1.1** - Create test files for memory_utils.py
2. **Run coverage check** - Verify branch coverage improvement
3. **Create threat model** - Document security considerations
4. **Setup benchmark automation** - Scripts and pre-commit hook
5. **Add missing docstrings** - Complete documentation
6. **Final verification** - All checks pass

---

**Document Owner**: Development Team  
**Created**: March 29, 2026  
**Last Updated**: March 29, 2026
