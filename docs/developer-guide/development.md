# Development Guide

This guide provides detailed information for developers working on the SecondBrain project.

## Table of Contents

- [Environment Setup](#environment-setup)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Performance Optimization](#performance-optimization)
- [Contributing](#contributing)

## Environment Setup

### Prerequisites

- Python 3.11 or higher
- MongoDB 7.0+ (for vector search)
- sentence-transformers (for embedding generation)
- Docker (optional, for containerized development)

### Local Development Setup

```bash
# 1. Clone the repository
git clone <repository-url>
cd secondbrain

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# 4. Install dependencies

# Option A: Install with dev dependencies (recommended for development)
pip install -e ".[dev]"

# Option B: Install from locked requirements (for reproducible builds)
pip install -r requirements.txt

# Option C: Install runtime dependencies only
pip install -e .

# 5. Install pre-commit hooks
pre-commit install

# 6. Create .env file
cp .env.example .env
# Edit .env with your configuration
```

### Docker Development Environment

#### macOS (sentence-transformers installed locally)

```bash
# Start MongoDB only
docker-compose up -d

# Start sentence-transformers locally
sentence-transformers serve

# Verify services are running
docker-compose ps
sentence-transformers list

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

#### Linux / Windows (sentence-transformers via Docker)

```bash
# Start all services
docker-compose up -d

# Or start them separately:
docker-compose up -d mongodb        # MongoDB only
docker-compose -f docker-compose.sentence-transformers.yml up -d  # sentence-transformers only

# Verify services are running
docker-compose ps

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Development Workflow

### Code Quality Checks

Run all checks before committing:

```bash
# Run all quality checks
ruff check . && ruff format --check . && mypy . && pytest

# Or use pre-commit
pre-commit run --all-files
```

Individual checks:

```bash
# Linting
ruff check .

# Formatting
ruff format .

# Type checking
mypy .

# Tests
pytest

# Security scanning
bandit -r src/secondbrain

# Dependency vulnerability check
safety check
```

### Git Workflow

1. Create a feature branch:
   ```bash
   git checkout -b feature/description
   ```

2. Make changes and commit with conventional commits:
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```

3. Push and create pull request:
   ```bash
   git push origin feature/description
   ```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=secondbrain --cov-report=html

# Run specific test file
pytest tests/test_storage/test_storage.py

# Run tests matching pattern
pytest -k "test_search"

# Run with verbose output
pytest -v

# Run with detailed failure output
pytest -vv
```

### Test Structure

```
tests/
├── test_cli/           # CLI command tests
├── test_config/        # Configuration tests
├── test_document/      # Document processing tests
├── test_embedding/     # Embedding generation tests
├── test_integration/   # Integration tests
├── test_logging/       # Logging tests
├── test_management/    # Management commands tests
├── test_search/        # Search functionality tests
├── test_storage/       # Storage layer tests
└── test_utils/         # Utility function tests
```

### Writing Tests

Follow these guidelines:

1. **Test behavior, not implementation**
   ```python
   # Good - tests outcome
   def test_search_returns_results():
       result = searcher.search("query")
       assert len(result) > 0
   
   # Avoid - tests implementation details
   def test_search_calls_method():
       with patch.object(searcher, '_method') as mock:
           searcher.search("query")
           mock.assert_called_once()
   ```

2. **Use parametrization for multiple test cases**
   ```python
   @pytest.mark.parametrize("input,expected", [
       ("test", "TEST"),
       ("hello", "HELLO"),
   ])
   def test_uppercase(input, expected):
       assert uppercase(input) == expected
   ```

3. **Use fixtures for setup**
   ```python
   @pytest.fixture
   def sample_document(tmp_path):
       doc = tmp_path / "test.pdf"
       # Create test document
       return doc
   ```

### Test Coverage

Target: 85%+ code coverage

```bash
# Check coverage
pytest --cov=secondbrain --cov-report=term-missing

# Generate HTML report
pytest --cov=secondbrain --cov-report=html
# Open htmlcov/index.html
```

## Troubleshooting

### Common Issues

#### MongoDB Connection Issues

**Problem**: Cannot connect to MongoDB

**Solutions**:
1. Verify MongoDB is running:
   ```bash
   docker-compose ps
   # or
   mongosh --eval "db.version()"
   ```

2. Check connection string in `.env`:
   ```
   SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
   ```

3. Ensure MongoDB version is 7.0+ (required for vector search)

#### sentence-transformers Connection Issues

**Problem**: Cannot connect to sentence-transformers

**Solutions**:
1. Verify sentence-transformers is running:
   ```bash
   curl http://localhost:114../api-reference/index.mdtags
   ```

2. Check sentence-transformers URL in `.env`:
   ```
   SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:local embedding
   ```

3. Pull the embedding model:
   ```bash
   sentence-transformers pull embeddinggemma:latest
   ```

#### Embedding Generation Failures

**Problem**: Embedding generation fails or times out

**Solutions**:
1. Check sentence-transformers model is loaded
2. Verify embedding dimensions match configuration
3. Check system resources (memory/CPU)

#### Test Failures

**Problem**: Tests fail intermittently

**Solutions**:
1. Run tests with more verbose output:
   ```bash
   pytest -vv
   ```

2. Check for race conditions in async tests
3. Ensure proper cleanup in fixtures
4. Run tests multiple times to identify flaky tests

#### Import Errors

**Problem**: Module import errors

**Solutions**:
1. Ensure you're in the project root directory
2. Verify virtual environment is activated
3. Reinstall dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

### Debugging Tips

1. **Use verbose logging**:
   ```bash
   secondbrain --verbose ingest document.pdf
   ```

2. **Enable Python debugger**:
   ```python
   import pdb; pdb.set_trace()
   ```

3. **Check logs**:
   ```bash
   # View application logs
   tail -f /path/to/logs
   ```

## Performance Optimization

### Batch Processing

Use batch processing for large file sets:

```bash
secondbrain ingest /path/to/documents/ --batch-size 20
```

### Chunk Size Optimization

Adjust chunk size based on document types:

```bash
# For long documents
secondbrain ingest document.pdf --chunk-size 2048 --chunk-overlap 100

# For short documents
secondbrain ingest document.txt --chunk-size 512 --chunk-overlap 50
```

### Connection Pooling

MongoDB connection pooling is configured automatically:

- maxPoolSize: 50
- minPoolSize: 10
- maxIdleTimeMS: 300000
- waitQueueTimeoutMS: 5000

### Rate Limiting

Rate limiting protects sentence-transformers API:

```bash
# Configure via environment
export SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=10
export SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0
```

## Contributing

### Code Review Process

1. Submit pull request
2. Ensure all checks pass (linting, testing, type checking)
3. Address review comments
4. Get approval from maintainers
5. Merge to main branch

### Pull Request Guidelines

- Use descriptive PR titles
- Include summary of changes
- Reference related issues
- Add tests for new features
- Update documentation as needed

### Code Standards

- Follow PEP 8 style guidelines
- Use type hints for all functions
- Write docstrings for public APIs
- Keep functions focused and small
- Prefer composition over inheritance

## Architecture Overview

### Component Interaction

```
┌─────────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────┐
│    CLI      │────▶│   Document   │────▶│Embedding │────▶│  MongoDB │
│             │     │   Ingestion  │     │ Generator│     │          │
└─────────────┘     └──────────────┘     └──────────┘     └──────────┘
                                                                    │
                                                                    ▼
                                                           ┌──────────────┐
                                                           │   Searcher   │
                                                           └──────────────┘
```

### Key Modules

- **cli**: Command-line interface using Click
- **document**: Document parsing and chunking using Docling
- **embedding**: Embedding generation using sentence-transformers
- **storage**: Vector storage in MongoDB
- **search**: Semantic search with cosine similarity
- **config**: Configuration management with Pydantic

## Additional Resources



- [Code Standards](./code-standards.md) - Code style guidelines
- [Contributing](./contributing.md) - Contribution guidelines
- [Security](./security.md) - Security policies

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues and discussions
- Review documentation
