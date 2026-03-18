# Developer Guide

Welcome to the SecondBrain developer documentation. This guide covers everything you need to contribute to the project.

## Overview

SecondBrain is a local document intelligence CLI built with:
- **Python 3.11+** with async support
- **Click** for CLI interface
- **Pydantic** for configuration validation
- **MongoDB** for vector storage
- **sentence-transformers** for embedding generation
- **Docling** for document parsing

## Getting Started

### Quick Setup

```bash
# Clone and setup
git clone <repository-url>
cd secondbrain
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### Development Environment

- [Environment Setup](./development.md) - Prerequisites and installation
- [Docker Setup](./docker.md) - Containerized development
- [Testing](./development.md) - Running and writing tests
- [Code Standards](./code-standards.md) - Coding guidelines

## Examples

For practical usage examples, see the [examples directory](https://github.com/your-repo/examples) on GitHub.

### Setup & Configuration
- [Development Setup](./development.md) - Full development workflow
- [Docker Setup](./docker.md) - Containerized development and deployment
- [Configuration](./configuration.md) - Environment variables and settings
- [Building & Distribution](./building.md) - Create distributable binaries

### Development Practices
- [Code Standards](./code-standards.md) - Coding guidelines and best practices
- [Async API Guide](./async-api.md) - Asynchronous programming patterns
- [Testing](./development.md) - Test structure and coverage
- [Contributing](./contributing.md) - How to contribute to the project

### Architecture & Design
- [Architecture Overview](../architecture/index.md) - System design and data flow
- [Schema Reference](../architecture/SCHEMA.md) - Database schema
- [Data Flow](../architecture/DATA_FLOW.md) - Component interactions

### Maintenance
- [Migrations](./migrations.md) - Schema migration strategies
- [Security](./security.md) - Security guidelines and practices
- [Changelog](./changelog.md) - Version history and changes

## API Documentation

- [API Reference](../api-reference/index.md) - Auto-generated API documentation
- [CLI Reference](../api-reference/cli.md) - Command-line interface
- [Types](../api-reference/types.md) - Type definitions and data models

## Examples

Check the [examples directory](https://github.com/your-repo/examples) on GitHub for:
- Basic CLI usage
- Advanced async workflows
- REST API integrations (Flask, FastAPI)
- Utility scripts

## Contributing

Interested in contributing? Read our [Contributing Guide](./contributing.md) to get started.

## Support

- [Open an Issue](#) - Bug reports and feature requests
- [Discussions](#) - Community discussions (coming soon)
