# Developer Guide

This guide covers development setup, contribution guidelines, and technical documentation for SecondBrain contributors.

## Sections

| Section | Description |
|---------|-------------|
| [Development Setup](development.md) | Setting up a local dev environment |
| [Docker Setup](docker.md) | Running services with Docker |
| [Configuration Reference](configuration.md) | Environment variable configuration |
| [Building & Distribution](building.md) | Packaging and distribution |
| [Async API Guide](async-api.md) | Async programming patterns |
| [Code Standards](code-standards.md) | Style guidelines and conventions |
| [Testing Guide](testing.md) | Writing and running tests |
| [CLI Best Practices](python-cli-best-practices-checklist.md) | CLI design patterns |
| [Contributing](contributing.md) | Contribution guidelines |
| [Migrations](migrations.md) | Database migration procedures |
| [Security](security.md) | Security considerations |

## Repository Structure

```
secondbrain/
├── src/secondbrain/           # Main package
│   ├── cli/                   # CLI commands
│   ├── config/                # Configuration
│   ├── document/              # Document processing
│   ├── embed/                 # Embedding generation
│   ├── search/                # Vector search
│   ├── storage/               # MongoDB storage
│   └── utils/                 # Utilities
├── tests/                     # Test suite
├── docs/                      # Documentation
└── docker-compose.yml         # Service definitions
```

## Getting Started

1. Fork and clone the repository
2. Create a virtual environment
3. Install development dependencies
4. Run the test suite to verify setup

See the [Development Setup](development.md) page for detailed instructions.