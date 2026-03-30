# Complete Implementation Plan - Roadmap to 9.5+ Score

**Created**: March 29, 2026  
**Status**: Ready for Execution  
**Target**: 9.5+/10 quality score  
**Estimated Duration**: 2-3 weeks

---

## Executive Summary

This plan addresses ALL remaining work to achieve 9.5+ quality score:

1. **Priority 3.1-3.5**: Complete implementation (0% → 100%)
2. **Priority 1.1**: Verification (branch coverage 90%+ - already achieved)
3. **Priority 1.4**: Verification (100% docstrings - already achieved)
4. **Priority 2.5**: Bug fixes (5 failing tests in dependency scripts)

### Current State Assessment

| Category | Status | Evidence |
|----------|--------|----------|
| **Priority 1.1** | ✅ Complete | 90.42% branch coverage achieved |
| **Priority 1.4** | ✅ Complete | 236/236 = 100% docstrings |
| **Priority 2.1** | ✅ Complete | `docs/user-guide/error-handling.md` exists |
| **Priority 2.2** | ✅ Complete | `tests/test_coverage_gaps.py` created |
| **Priority 2.3** | ✅ Complete | `src/secondbrain/config/validator.py` exists |
| **Priority 2.4** | ✅ Complete | 21/21 observability tests passing |
| **Priority 2.5** | ⚠️ 85% Complete | 28/33 tests passing (5 failing) |
| **Priority 3.1** | ⏳ 0% | ADRs exist but need expansion |
| **Priority 3.2** | ⏳ 0% | Performance guide missing |
| **Priority 3.3** | ⏳ 0% | Integration tests need expansion |
| **Priority 3.4** | ⏳ 0% | Onboarding docs missing |
| **Priority 3.5** | ⏳ 0% | Release automation missing |

---

## Wave 1: Foundation Fixes (Days 1-2)

### Goal: Fix Priority 2.5 failing tests

**Parallel Execution**: All 5 tests can be fixed independently

#### Task 1.1: Fix `test_sbom_generation_cyclonedx`
- **Effort**: 30 minutes
- **Dependencies**: None
- **Success Criteria**: Test passes with valid CycloneDX SBOM
- **Agent**: `explore` (investigate failure)
- **Skill**: None required

**Sub-tasks**:
1. Run failing test to see error
2. Check if `cyclonedx-bom` tool is installed
3. Fix script or test expectations
4. Verify test passes

#### Task 1.2: Fix `test_sbom_validation`
- **Effort**: 30 minutes
- **Dependencies**: Task 1.1 (SBOM generation)
- **Success Criteria**: SBOM validates against schema
- **Agent**: `explore` (investigate failure)
- **Skill**: None required

**Sub-tasks**:
1. Run failing test
2. Validate SBOM output format
3. Fix schema validation logic
4. Verify test passes

#### Task 1.3: Fix `test_sbom_full_workflow`
- **Effort**: 30 minutes
- **Dependencies**: Tasks 1.1, 1.2
- **Success Criteria**: Full workflow completes successfully
- **Agent**: `explore` (investigate failure)
- **Skill**: None required

**Sub-tasks**:
1. Run integration test
2. Check workflow steps
3. Fix any orchestration issues
4. Verify end-to-end flow

#### Task 1.4: Fix `test_json_output_format`
- **Effort**: 30 minutes
- **Dependencies**: None
- **Success Criteria**: JSON output is valid and complete
- **Agent**: `explore` (investigate failure)
- **Skill**: None required

**Sub-tasks**:
1. Run failing test
2. Check JSON serialization
3. Fix output formatting
4. Verify JSON validity

#### Task 1.5: Fix `test_check_command`
- **Effort**: 30 minutes
- **Dependencies**: None
- **Success Criteria**: Check command runs without errors
- **Agent**: `explore` (investigate failure)
- **Skill**: None required

**Sub-tasks**:
1. Run failing test
2. Check command execution
3. Fix any script issues
4. Verify command works

### Wave 1 Deliverables:
- ✅ All 5 Priority 2.5 tests passing
- ✅ Dependency automation fully functional
- ✅ `ROADMAP-PROGRESS.md` updated

---

## Wave 2: Architecture Documentation (Days 3-5)

### Goal: Complete Priority 3.1 - Architecture Decision Records

**Parallel Execution**: ADRs can be written independently

#### Task 2.1: Create ADR Template
- **Effort**: 30 minutes
- **Dependencies**: None
- **Success Criteria**: Template in `docs/architecture/ADRs/ADR-000-template.md`
- **Agent**: `explore` (research ADR best practices)
- **Skill**: None required

**Content**:
```markdown
# ADR-XXX: Decision Title

## Status
Proposed | Accepted | Deprecated | Superseded

## Context
[Problem statement, constraints, requirements]

## Options Considered
1. Option A - Pros/Cons
2. Option B - Pros/Cons  
3. Option C - Pros/Cons

## Decision
[Chosen option with rationale]

## Consequences
### Positive
- Benefit 1
- Benefit 2

### Negative
- Drawback 1
- Mitigation strategy

## References
- Related ADRs
- External resources
```

#### Task 2.2: Write ADR-002 - MongoDB for Vector Storage
- **Effort**: 2 hours
- **Dependencies**: Task 2.1
- **Success Criteria**: Comprehensive ADR documenting MongoDB choice
- **Agent**: `explore` (analyze current implementation)
- **Skill**: None required

**Content Outline**:
- Context: Need for vector storage with async support
- Options: Pinecone, Weaviate, MongoDB, pgvector
- Decision: MongoDB with Atlas Vector Search
- Consequences: Local-first, async support, cost-effective

#### Task 2.3: Write ADR-003 - Async Architecture
- **Effort**: 2 hours
- **Dependencies**: Task 2.1
- **Success Criteria**: ADR documenting async design decisions
- **Agent**: `explore` (analyze async patterns)
- **Skill**: None required

**Content Outline**:
- Context: High-throughput document processing
- Options: Sync-only, Async-only, Hybrid
- Decision: Full async with Motor
- Consequences: Better throughput, complexity trade-off

#### Task 2.4: Write ADR-004 - Embedding Model Selection
- **Effort**: 2 hours
- **Dependencies**: Task 2.1
- **Success Criteria**: ADR documenting model choices
- **Agent**: `explore` (research embedding models)
- **Skill**: None required

**Content Outline**:
- Context: Need for quality embeddings, local processing
- Options: Sentence Transformers, OpenAI, Cohere
- Decision: Sentence Transformers (all-MiniLM-L6-v2 default)
- Consequences: Offline-first, GPU acceleration possible

#### Task 2.5: Write ADR-005 - Local-First Architecture
- **Effort**: 2 hours
- **Dependencies**: Task 2.1
- **Success Criteria**: ADR documenting privacy-first design
- **Agent**: `explore` (analyze privacy requirements)
- **Skill**: None required

**Content Outline**:
- Context: Privacy requirements, data sovereignty
- Options: Cloud-only, Hybrid, Local-first
- Decision: Local-first with optional remote MongoDB
- Consequences: Privacy, no external API calls

#### Task 2.6: Write ADR-006 - Circuit Breaker Pattern
- **Effort**: 2 hours
- **Dependencies**: Task 2.1
- **Success Criteria**: ADR documenting resilience patterns
- **Agent**: `explore` (analyze circuit breaker implementation)
- **Skill**: None required

**Content Outline**:
- Context: Service reliability, failure handling
- Options: Retry-only, Circuit breaker, Bulkhead
- Decision: Circuit breaker with fallback
- Consequences: Better resilience, complexity

#### Task 2.7: Write ADR-007 - OpenTelemetry Integration
- **Effort**: 2 hours
- **Dependencies**: Task 2.1
- **Success Criteria**: ADR documenting observability strategy
- **Agent**: `explore` (analyze tracing implementation)
- **Skill**: None required

**Content Outline**:
- Context: Need for distributed tracing, metrics
- Options: Custom logging, Prometheus, OpenTelemetry
- Decision: OpenTelemetry with OTLP export
- Consequences: Industry standard, vendor flexibility

#### Task 2.8: Update Architecture Index
- **Effort**: 30 minutes
- **Dependencies**: Tasks 2.2-2.7
- **Success Criteria**: `docs/architecture/index.md` references all ADRs
- **Agent**: None
- **Skill**: None required

### Wave 2 Deliverables:
- ✅ ADR template created
- ✅ 6 new ADRs (002-007)
- ✅ Architecture index updated
- ✅ Total: 7 ADRs (including existing ADR-001)

---

## Wave 3: Performance Guide (Days 6-10)

### Goal: Complete Priority 3.2 - Performance Optimization Guide

**Parallel Execution**: Some sections can be written independently

#### Task 3.1: Benchmark Baseline Analysis
- **Effort**: 4 hours
- **Dependencies**: Wave 1 complete
- **Success Criteria**: Baseline metrics documented
- **Agent**: `explore` (run benchmarks, analyze results)
- **Skill**: None required

**Sub-tasks**:
1. Run existing benchmarks: `./scripts/run_benchmarks.sh`
2. Analyze ingestion performance
3. Analyze search performance
4. Document baseline metrics

#### Task 3.2: Write Ingestion Optimization Section
- **Effort**: 4 hours
- **Dependencies**: Task 3.1
- **Success Criteria**: Comprehensive ingestion guide
- **Agent**: None
- **Skill**: None required

**Content**:
- Batch size tuning
- Parallel workers configuration
- GPU acceleration setup
- Memory management
- Streaming vs batch processing

#### Task 3.3: Write Search Optimization Section
- **Effort**: 4 hours
- **Dependencies**: Task 3.1
- **Success Criteria**: Comprehensive search guide
- **Agent**: None
- **Skill**: None required

**Content**:
- Index tuning (MongoDB indexes)
- Query optimization patterns
- Result limiting strategies
- Vector search configuration
- Caching strategies

#### Task 3.4: Write Memory Management Section
- **Effort**: 3 hours
- **Dependencies**: Task 3.1
- **Success Criteria**: Memory optimization guide
- **Agent**: None
- **Skill**: None required

**Content**:
- Embedding cache configuration
- Streaming processing patterns
- Compression techniques
- Memory profiling tools

#### Task 3.5: Write GPU Acceleration Section
- **Effort**: 3 hours
- **Dependencies**: Task 3.1
- **Success Criteria**: GPU setup guide
- **Agent**: None
- **Skill**: None required

**Content**:
- Model selection for GPU
- Memory allocation
- Batch sizing for GPU
- CUDA configuration
- Performance comparisons

#### Task 3.6: Write Monitoring Section
- **Effort**: 3 hours
- **Dependencies**: Wave 2 (observability docs)
- **Success Criteria**: Monitoring guide complete
- **Agent**: None
- **Skill**: None required

**Content**:
- Key metrics to track
- Profiling tools usage
- Bottleneck identification
- Performance alerting

#### Task 3.7: Create Tuning Reference
- **Effort**: 2 hours
- **Dependencies**: Tasks 3.2-3.6
- **Success Criteria**: Configuration parameter reference
- **Agent**: None
- **Skill**: None required

**Content**:
- All tunable parameters
- Recommended values by scenario
- Trade-off analysis
- Scenario-based recommendations

#### Task 3.8: Create Performance Profiling Script
- **Effort**: 3 hours
- **Dependencies**: Task 3.1
- **Success Criteria**: `scripts/performance-profile.sh` created
- **Agent**: `explore` (research profiling tools)
- **Skill**: None required

**Features**:
- Memory profiling
- CPU profiling
- I/O profiling
- Visualization output

### Wave 3 Deliverables:
- ✅ Performance optimization guide (6 sections)
- ✅ Tuning reference document
- ✅ Performance profiling script
- ✅ Baseline benchmarks documented

---

## Wave 4: Integration Tests (Days 11-15)

### Goal: Complete Priority 3.3 - Integration Test Suite Expansion

**Parallel Execution**: Test suites can be developed independently

#### Task 4.1: Large Document Tests
- **Effort**: 1 day
- **Dependencies**: Wave 1 complete
- **Success Criteria**: `tests/integration/test_large_docs.py` with 10+ tests
- **Agent**: `explore` (design test scenarios)
- **Skill**: None required

**Test Cases**:
- Documents > 100MB
- Thousands of pages
- Memory pressure scenarios
- Streaming validation
- Chunk boundary handling

#### Task 4.2: Network Partition Tests
- **Effort**: 1 day
- **Dependencies**: Wave 1 complete
- **Success Criteria**: `tests/integration/test_network_partitions.py` with 8+ tests
- **Agent**: `explore` (design failure scenarios)
- **Skill**: None required

**Test Cases**:
- MongoDB disconnection
- Embedding service failure
- Retry mechanisms
- Circuit breaker activation
- Recovery validation

#### Task 4.3: Circuit Breaker Tests
- **Effort**: 1 day
- **Dependencies**: Wave 1 complete
- **Success Criteria**: `tests/integration/test_circuit_breaker.py` with 10+ tests
- **Agent**: `explore` (analyze circuit breaker states)
- **Skill**: None required

**Test Cases**:
- Failure threshold triggers
- Recovery behavior
- Fallback mechanisms
- State transitions
- Concurrent failure handling

#### Task 4.4: End-to-End Workflow Tests
- **Effort**: 1.5 days
- **Dependencies**: Tasks 4.1-4.3
- **Success Criteria**: `tests/integration/test_end_to_end.py` with 15+ tests
- **Agent**: `explore` (design workflows)
- **Skill**: None required

**Test Cases**:
- Complete ingestion pipeline
- Search and retrieval
- Export/import cycles
- Document lifecycle
- Multi-user scenarios

#### Task 4.5: Chaos Engineering Tests
- **Effort**: 1 day
- **Dependencies**: Tasks 4.1-4.4
- **Success Criteria**: `tests/integration/test_chaos.py` with 8+ tests
- **Agent**: `explore` (design chaos scenarios)
- **Skill**: None required

**Test Cases**:
- Random service failures
- Resource exhaustion
- Network latency injection
- Concurrent stress tests

#### Task 4.6: Integration Test Infrastructure
- **Effort**: 0.5 day
- **Dependencies**: Tasks 4.1-4.5
- **Success Criteria**: Enhanced `tests/conftest.py` with integration fixtures
- **Agent**: None
- **Skill**: None required

**Features**:
- Docker Compose for test services
- Test service lifecycle management
- Cleanup fixtures
- Parallel test support

### Wave 4 Deliverables:
- ✅ 5 new integration test files
- ✅ 50+ new integration tests
- ✅ Enhanced test infrastructure
- ✅ Integration test documentation

---

## Wave 5: Developer Onboarding (Days 16-18)

### Goal: Complete Priority 3.4 - Developer Onboarding Enhancement

**Parallel Execution**: Some tasks independent

#### Task 5.1: Create Devcontainer Configuration
- **Effort**: 2 hours
- **Dependencies**: None
- **Success Criteria**: `.devcontainer/devcontainer.json` and `Dockerfile`
- **Agent**: `explore` (research devcontainer best practices)
- **Skill**: None required

**Content**:
```json
{
  "name": "SecondBrain Development",
  "image": "mcr.microsoft.com/devcontainers/python:3.11",
  "features": {
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},
    "ghcr.io/devcontainers/features/node:1": {}
  },
  "forwardPorts": [27017],
  "postCreateCommand": "pip install -e '.[dev]'",
  "customizations": {
    "vscode": {
      "extensions": ["ms-python.python", "ms-python.vscode-pylance"]
    }
  }
}
```

#### Task 5.2: Create Dev Setup Wizard
- **Effort**: 3 hours
- **Dependencies**: Task 5.1
- **Success Criteria**: `scripts/dev-setup.sh` interactive wizard
- **Agent**: `explore` (research setup automation)
- **Skill**: None required

**Features**:
- Python version detection
- MongoDB availability check
- Dependency installation
- Pre-commit hooks setup
- Initial test run
- Next steps guidance

#### Task 5.3: Write Onboarding Guide
- **Effort**: 3 hours
- **Dependencies**: Tasks 5.1-5.2
- **Success Criteria**: `docs/developer-guide/onboarding.md` complete
- **Agent**: None
- **Skill**: None required

**Content**:
- Quick start guide
- Environment setup options
- First contribution workflow
- Common issues and solutions
- Development best practices
- Code review process

#### Task 5.4: Create First Contributor Template
- **Effort**: 2 hours
- **Dependencies**: Task 5.3
- **Success Criteria**: `.github/ISSUE_TEMPLATE/first-contributor.md`
- **Agent**: None
- **Skill**: None required

**Content**:
- Beginner-friendly issue labels
- Step-by-step contribution guide
- Code examples
- Common pitfalls

#### Task 5.5: Enhance CONTRIBUTING.md
- **Effort**: 2 hours
- **Dependencies**: Task 5.3
- **Success Criteria**: CONTRIBUTING.md includes onboarding flow
- **Agent**: None
- **Skill**: None required

**Updates**:
- Add onboarding section
- Link to new guides
- Add setup wizard instructions
- Add first PR workflow

### Wave 5 Deliverables:
- ✅ Devcontainer configuration
- ✅ Interactive setup wizard
- ✅ Comprehensive onboarding guide
- ✅ First contributor template
- ✅ Enhanced CONTRIBUTING.md

---

## Wave 6: Release Management (Days 19-21)

### Goal: Complete Priority 3.5 - Release Management Automation

**Parallel Execution**: Some tasks independent

#### Task 6.1: Create Release Script
- **Effort**: 3 hours
- **Dependencies**: None
- **Success Criteria**: `scripts/release.sh` with semantic versioning
- **Agent**: `explore` (research release automation)
- **Skill**: None required

**Features**:
- Version validation (semver)
- Version update in pyproject.toml
- Git commit creation
- Tag creation
- Push to remote
- Pre-release checks

#### Task 6.2: Create Changelog Generator
- **Effort**: 3 hours
- **Dependencies**: Task 6.1
- **Success Criteria**: `scripts/changelog-generator.py` working
- **Agent**: `explore` (research changelog formats)
- **Skill**: None required

**Features**:
- Parse git history
- Categorize commits (feat, fix, docs, etc.)
- Format with conventional commits
- Generate markdown output
- Append to CHANGELOG.md

#### Task 6.3: Write Release Process Documentation
- **Effort**: 2 hours
- **Dependencies**: Tasks 6.1-6.2
- **Success Criteria**: `RELEASE_PROCESS.md` complete
- **Agent**: None
- **Skill**: None required

**Content**:
- Version numbering scheme
- Release checklist
- Pre-release tasks
- Release execution
- Post-release tasks
- Rollback procedure

#### Task 6.4: Create Release Issue Template
- **Effort**: 1 hour
- **Dependencies**: Task 6.3
- **Success Criteria**: `.github/ISSUE_TEMPLATE/release.md`
- **Agent**: None
- **Skill**: None required

**Content**:
- Release checklist
- Version info
- Contributors list
- Breaking changes section

#### Task 6.5: Update CHANGELOG.md
- **Effort**: 1 hour
- **Dependencies**: Task 6.2
- **Success Criteria**: CHANGELOG.md formatted for automation
- **Agent**: None
- **Skill**: None required

**Updates**:
- Add header template
- Add version sections
- Add contributor credits format

### Wave 6 Deliverables:
- ✅ Release automation script
- ✅ Changelog generator
- ✅ Release process documentation
- ✅ Release issue template
- ✅ Formatted CHANGELOG.md

---

## Verification & Final Polish (Days 22-23)

### Goal: Verify all work and update documentation

#### Task 7.1: Run Full Test Suite
- **Effort**: 2 hours
- **Dependencies**: All waves complete
- **Success Criteria**: All tests passing
- **Agent**: None
- **Skill**: None required

```bash
pytest -xvs --cov=src/secondbrain --cov-branch
```

#### Task 7.2: Run Linting & Type Checking
- **Effort**: 1 hour
- **Dependencies**: All waves complete
- **Success Criteria**: No linting or type errors
- **Agent**: None
- **Skill**: None required

```bash
ruff check .
ruff format .
mypy .
```

#### Task 7.3: Update ROADMAP-PROGRESS.md
- **Effort**: 1 hour
- **Dependencies**: All waves complete
- **Success Criteria**: Progress document reflects 100% completion
- **Agent**: None
- **Skill**: None required

#### Task 7.4: Final Documentation Review
- **Effort**: 2 hours
- **Dependencies**: All waves complete
- **Success Criteria**: All documentation complete and consistent
- **Agent**: None
- **Skill**: None required

---

## Dependencies Matrix

| Task | Depends On | Can Run Parallel With |
|------|------------|----------------------|
| **Wave 1** (2.5 fixes) | None | All tasks within Wave 1 |
| **Wave 2** (ADRs) | Wave 1 | All ADRs (2.2-2.7) |
| **Wave 3** (Performance) | Wave 2 | Tasks 3.2-3.6 |
| **Wave 4** (Integration Tests) | Wave 1 | Tasks 4.1-4.5 |
| **Wave 5** (Onboarding) | None | All Wave 5 tasks |
| **Wave 6** (Release) | None | All Wave 6 tasks |
| **Wave 7** (Verification) | All waves | None |

---

## Effort Summary

| Wave | Items | Effort | Person-Days |
|------|-------|--------|-------------|
| Wave 1 | 5 fixes | 2.5 hours | 0.3 |
| Wave 2 | 8 ADR tasks | 12.5 hours | 1.6 |
| Wave 3 | 8 performance tasks | 26 hours | 3.3 |
| Wave 4 | 6 test tasks | 18 hours | 2.3 |
| Wave 5 | 5 onboarding tasks | 12 hours | 1.5 |
| Wave 6 | 5 release tasks | 10 hours | 1.3 |
| Wave 7 | 4 verification tasks | 6 hours | 0.8 |
| **TOTAL** | **41 tasks** | **87 hours** | **11 person-days** |

---

## Recommended Agent Strategy

### For Exploration Tasks (use `explore` agent):
- Task 1.1-1.5: Investigate test failures
- Task 2.2-2.7: Research ADR topics
- Task 3.1: Benchmark analysis
- Task 3.8: Profiling tools research
- Task 4.1-4.5: Test scenario design
- Task 5.1-5.2: Devcontainer/setup research
- Task 6.1-6.2: Release automation research

### For Implementation Tasks (no agent needed):
- All documentation writing (Tasks 2.8, 3.2-3.7, 5.3-5.5, 6.3-6.5)
- All test implementation (Tasks 4.1-4.6)
- All verification tasks (Wave 7)

### Skills to Use:
- **None required** - all tasks are straightforward implementation
- Optional: `openspec-apply-change` if using OpenSpec workflow

---

## Success Criteria by Wave

### Wave 1 Success:
- ✅ 33/33 dependency script tests passing
- ✅ All scripts functional and documented

### Wave 2 Success:
- ✅ 7 ADRs created (ADR-001 to ADR-007)
- ✅ Architecture index updated
- ✅ All decisions properly documented

### Wave 3 Success:
- ✅ Performance guide complete (6 sections)
- ✅ Tuning reference with 20+ parameters
- ✅ Profiling script working
- ✅ Baseline benchmarks documented

### Wave 4 Success:
- ✅ 50+ new integration tests
- ✅ All integration tests passing
- ✅ Test infrastructure enhanced
- ✅ Integration test guide complete

### Wave 5 Success:
- ✅ Devcontainer ready
- ✅ Setup wizard working
- ✅ Onboarding guide complete
- ✅ New contributor can setup in <30 min

### Wave 6 Success:
- ✅ Release script working
- ✅ Changelog generator working
- ✅ Release process documented
- ✅ Release tested end-to-end

### Wave 7 Success:
- ✅ All tests passing (1300+)
- ✅ No linting errors
- ✅ No type errors
- ✅ ROADMAP-PROGRESS.md updated to 100%

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Test failures require refactoring | Medium | Medium | Identify early, allocate buffer time |
| Performance benchmarks need GPU | Medium | Low | Document CPU baseline, note GPU improvements |
| Integration tests need services | High | Medium | Use Docker Compose for test services |
| Release script conflicts | Low | Low | Test in feature branch first |
| Documentation scope creep | Medium | Low | Stick to outlined content, defer extras |

---

## Parallel Execution Strategy

### Day 1-2: Wave 1 (Foundation)
- All 5 test fixes can run in parallel
- Assign to 5 developers or run sequentially (2.5 hours total)

### Day 3-5: Wave 2 (ADRs) + Wave 5 (Onboarding) + Wave 6 (Release)
- **Track A**: ADRs (Tasks 2.2-2.7) - 6 parallel tasks
- **Track B**: Onboarding (Tasks 5.1-5.5) - 5 parallel tasks  
- **Track C**: Release (Tasks 6.1-6.5) - 5 parallel tasks
- These 3 tracks are independent and can run simultaneously

### Day 6-10: Wave 3 (Performance)
- Tasks 3.2-3.6 can run in parallel (5 sections)
- Task 3.1 must complete first (baseline analysis)
- Task 3.7-3.8 can run after sections complete

### Day 11-15: Wave 4 (Integration Tests)
- Tasks 4.1-4.3 can run in parallel (3 test suites)
- Task 4.4 depends on 4.1-4.3
- Task 4.5-4.6 can run after 4.4

### Day 16-21: Waves 5 & 6 (if not done in parallel)
- Execute remaining tracks

### Day 22-23: Wave 7 (Verification)
- Final testing and documentation

---

## Recommended Execution Order

### Option A: Sequential (Single Developer)
1. Wave 1 (Day 1)
2. Wave 2 (Days 2-3)
3. Wave 3 (Days 4-8)
4. Wave 4 (Days 9-13)
5. Wave 5 (Days 14-16)
6. Wave 6 (Days 17-19)
7. Wave 7 (Days 20-21)

**Total**: 21 days (3 weeks)

### Option B: Parallel (Multiple Developers)
**Week 1**:
- Developer A: Wave 1 + Wave 2
- Developer B: Wave 5 + Wave 6
- Developer C: Wave 3 (Tasks 3.1, 3.8)

**Week 2**:
- Developer A: Wave 3 (Tasks 3.2-3.7)
- Developer B: Wave 4 (Tasks 4.1-4.3)
- Developer C: Wave 4 (Tasks 4.4-4.6)

**Week 3**:
- All: Wave 7 verification
- Documentation polish
- Final testing

**Total**: 15 days (2+ weeks)

---

## Final Score Impact

| Category | Before | After | Change |
|----------|--------|-------|--------|
| **Overall** | **9.0** | **9.5+** | **+0.5** |
| Testing | 9.0 | 9.2 | +0.2 (50+ integration tests) |
| Documentation | 8.7 | 9.3 | +0.6 (7 ADRs, performance guide) |
| Security/Performance | 8.8 | 9.2 | +0.4 (performance optimization) |
| Code Quality | 9.0 | 9.0 | ✅ Maintained |
| CLI Design | 9.0 | 9.0 | ✅ Maintained |
| DX | 9.0 | 9.4 | +0.4 (onboarding, release automation) |

---

## Appendix: Task Templates

### ADR Template
See Wave 2, Task 2.1

### Performance Guide Template
See Wave 3, Task 3.2-3.6

### Integration Test Template
```python
"""Integration test for [feature]."""

import pytest
from pathlib import Path


@pytest.mark.integration
@pytest.mark.slow
class TestFeature:
    """Test suite for [feature]."""
    
    @pytest.fixture
    async def setup(self, tmp_path: Path):
        """Set up test fixtures."""
        # Setup code
        yield
        # Cleanup code
    
    async def test_scenario(self, setup):
        """Test specific scenario."""
        # Test code
        assert result == expected
```

### Release Script Template
See Wave 6, Task 6.1

---

**Document Version**: 1.0  
**Last Updated**: March 29, 2026  
**Ready for**: Immediate Execution
