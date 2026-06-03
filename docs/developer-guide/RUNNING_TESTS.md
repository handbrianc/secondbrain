# Running Tests

## Quick Start

### Option 1: Run All Tests (Fast - No Services Needed)

Most unit tests don't require external services:

```bash
# Run fast tests only (excludes integration/slow tests)
pytest

# This runs 1,498 tests in ~10 minutes with parallel execution
```

### Option 2: Run Full Test Suite (Requires Docker Services)

For integration tests:

```bash
# 1. Start test services
./scripts/start_test_services.sh

# 2. Wait for services to be healthy (MongoDB)
# This takes ~2-5 minutes

# 3. Run all tests
pytest -m ""  # Run ALL tests including slow/integration

# 4. Stop services when done
./scripts/stop_test_services.sh
```

## Test Profiles

| Profile | Command | Time | Services Needed |
|---------|---------|------|-----------------|
| Fast (Default) | `pytest` | ~10 min | None |
| Integration | `pytest -m "integration"` | ~20 min | MongoDB |
| Full Suite | `pytest -m ""` | ~30 min | MongoDB |
| Slow Tests | `pytest -m "slow"` | ~25 min | MongoDB |

## Troubleshooting

### Issue: Tests Connecting to MongoDB

**Symptom**: Tests try to connect to `localhost:27018`

**Solution**: 
- For fast tests: This is normal, tests will skip if MongoDB unavailable
- For integration tests: Start services with `./scripts/start_test_services.sh`

### Issue: MongoDB Connection Errors

```
RuntimeError: Cannot connect to MongoDB
```

**Solution**:
```bash
# Check if MongoDB is running
docker ps | grep secondbrain-mongodb-test

# If not running, start services
./scripts/start_test_services.sh

# Or check logs
docker logs secondbrain-mongodb-test
```

### Issue: LLM Provider Unavailable

```
pytest.skip("LLM unavailable")
```

**Solution**:
```bash
# Configure LLM provider in .env
# Set SECONDBRAIN_LLM_PROVIDER, SECONDBRAIN_OPENAI_BASE_URL, etc.

# Or skip LLM-dependent tests
pytest -m "not integration"
```

### Issue: OpenTelemetry Errors

```
ValueError: I/O operation on closed file.
```

**Status**: Already fixed in configuration. These warnings are now suppressed.

### Issue: Tests Hanging on Shutdown

**Symptom**: Tests don't exit cleanly after Ctrl+C

**Solution**:
```bash
# Force kill all test workers
pkill -9 pytest

# Or restart services
./scripts/stop_test_services.sh
```

### Issue: Many Test Failures (R, F, s markers)

**Cause**: Services not running or unavailable

**Solution**:
```bash
# Start services first
./scripts/start_test_services.sh

# Verify services are healthy
docker ps | grep secondbrain

# Run tests again
pytest
```

## Test Markers

Tests are categorized with markers:

- `fast` - Fast unit tests (<50ms)
- `medium` - Medium speed tests (<500ms)
- `slow` - Slow tests (>1s)
- `integration` - Require external services
- `performance` - Benchmark tests
- `chaos` - Failure injection tests

## Running Specific Tests

```bash
# Run a single test file
pytest tests/test_domain/test_entities.py -v

# Run tests matching a pattern
pytest -k "test_document" -v

# Run only unit tests (no integration)
pytest -m "not integration" -v

# Run with detailed output
pytest -v -s

# Run with test timing
pytest --durations=20

# Run with coverage
pytest --cov=secondbrain --cov-report=html
```

## Parallel Execution

Tests run in parallel by default (16 workers):

```bash
# Use specific number of workers
pytest -n 4  # Use 4 workers

# Disable parallel execution
pytest -n 0

# Show worker distribution
pytest -v --dist=loadscope
```

## Test Data

### MongoDB Test Database

- **Database**: `secondbrain_test`
- **Collection**: `test_embeddings`
- **URI**: `mongodb://testuser:testpass@localhost:27018/secondbrain_test`
- **Data**: Auto-seeded with 70+ test chunks

### Test Data Isolation

Each test run:
- Uses isolated test database
- Seeds fresh test data
- Cleans up after completion

## Performance Tips

1. **Use fast tests for development**: `pytest` (excludes slow tests)
2. **Run specific test files**: `pytest tests/test_domain/ -v`
3. **Use test selection**: `pytest -k "test_name" -v`
4. **Cache results**: pytest caches test collection automatically
5. **Skip unnecessary markers**: `-m "not integration and not slow"`

## CI/CD

For CI environments:

```bash
# Fast validation
pytest -m "not integration and not slow"

# Full validation (requires services)
docker-compose -f docker-compose.test.yml up -d
pytest -m ""
docker-compose -f docker-compose.test.yml down
```

## Environment Variables

```bash
# Override test database
export SECONDBRAIN_MONGO_URI="mongodb://localhost:27018/secondbrain_test"
export SECONDBRAIN_MONGO_DB="secondbrain_test"

# Disable specific test types
export SECONDBRAIN_TEST_SKIP_INTEGRATION=true

# Enable verbose logging
export SECONDBRAIN_LOG_LEVEL=DEBUG
```

## Common Workflows

### Development Workflow

```bash
# 1. Make code changes
# 2. Run fast tests
pytest -m "not integration"

# 3. Fix any failures
# 4. Run linting
ruff check . && ruff format .
mypy .
```

### Pre-Commit Workflow

```bash
# Run all checks before committing
pytest -m "not slow"
ruff check .
mypy .
```

### Pre-Release Workflow

```bash
# Start services
./scripts/start_test_services.sh

# Run full test suite
pytest -m ""

# Check coverage
pytest --cov=secondbrain --cov-report=term-missing

# Stop services
./scripts/stop_test_services.sh
```

## Support

- **Test Framework Issues**: See `tests/README.md`
- **Service Issues**: Check `docker-compose.test.yml`
- **Configuration**: See `pyproject.toml` [tool.pytest.ini_options]
