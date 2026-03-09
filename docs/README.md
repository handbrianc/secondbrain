# SecondBrain Documentation

Welcome to the SecondBrain documentation. This folder contains comprehensive guides, architecture documentation, and reference materials.

## Documentation Structure

```
docs/
├── index.md                 # Main documentation index
├── README.md                # This file - Documentation overview
├── getting-started/         # New user guides
│   ├── index.md             # Getting started overview
│   ├── installation.md      # Installation guide
│   ├── quick-start.md       # Quick start tutorial
│   └── configuration.md     # Essential configuration
├── user-guide/              # User-facing documentation
│   └── index.md             # User guide overview
├── developer-guide/         # Developer documentation
│   ├── index.md             # Developer guide overview
│   ├── development.md       # Development setup and workflow
│   ├── docker.md            # Docker setup and deployment
│   ├── configuration.md     # Full configuration reference
│   ├── building.md          # Create distributable binaries
│   ├── async-api.md         # Asynchronous API usage
│   ├── code-standards.md    # Coding standards and best practices
│   ├── contributing.md      # How to contribute to the project
│   ├── migrations.md        # Schema migration strategies
│   ├── security.md          # Security guidelines
│   └── changelog.md         # Version history and changes
├── architecture/            # Architecture documentation
│   ├── index.md             # Architecture overview
│   ├── data-flow.md         # Data flow and component interactions
│   └── schema.md            # Database schema reference
├── api-reference/           # Auto-generated API docs
│   ├── index.md             # API reference overview
│   ├── cli.md               # CLI module
│   ├── config.md            # Configuration module
│   ├── document.md          # Document ingestion
│   ├── storage.md           # Storage layer
│   ├── search.md            # Search functionality
│   ├── embedding.md         # Embedding generation
│   ├── logging.md           # Logging utilities
│   ├── exceptions.md        # Exception classes
│   └── types.md             # Type definitions
├── security/                # Security reports
│   ├── bandit_report.json   # Security scan results
│   └── bom.json             # Software bill of materials
└── LICENSE.md               # License information
```

## Quick Links

### For New Users
- [Getting Started](index.md) - Main documentation index
- [Installation Guide](getting-started/installation.md) - Detailed installation steps
- [Quick Start](getting-started/quick-start.md) - Get started in 5 minutes
- [Configuration](getting-started/configuration.md) - Essential configuration

### For Users
- [User Guide](user-guide/) - Complete usage guide
- [CLI Reference](api-reference/cli.md) - All CLI commands
- [Examples](examples/) - Practical code examples

### For Developers
- [Developer Guide](developer-guide/) - Development setup and workflows
- [Docker Setup](developer-guide/docker.md) - Containerized deployment
- [Configuration Reference](developer-guide/configuration.md) - Full config guide
- [Async API Guide](developer-guide/async-api.md) - Asynchronous programming
- [Building & Distribution](developer-guide/building.md) - Create binaries
- [Code Standards](developer-guide/code-standards.md) - Coding guidelines
- [Contributing](developer-guide/contributing.md) - How to contribute
- [Schema Reference](architecture/schema.md) - Database schema
- [Data Flow](architecture/data-flow.md) - Component interactions
- [Migration Guide](developer-guide/migrations.md) - Schema migration strategies
- [Security Guidelines](developer-guide/security.md) - Security best practices

### Project Information
- [Changelog](developer-guide/changelog.md) - Version history
- [Architecture Overview](architecture/) - System design
- [API Reference](api-reference/) - Code-level documentation

## OpenSpec Documentation

Technical specifications and design documents are maintained separately in the `openspec/` directory:

- [Design Documents](../openspec/changes/archive/2026-03-06-secondbrain/design.md)
- [Specifications](../openspec/changes/archive/2026-03-06-secondbrain/specs/)
- [Task Tracking](../openspec/changes/archive/2026-03-06-secondbrain/tasks.md)

## Getting Started

1. **New to SecondBrain?** Start with the [Quick Start](getting-started/quick-start.md)
2. **Want to contribute?** Read [CONTRIBUTING.md](developer-guide/contributing.md)
3. **Setting up development?** Follow [DEVELOPMENT.md](developer-guide/development.md)
4. **Need Docker setup?** Check [DOCKER.md](developer-guide/docker.md)
5. **Need schema info?** Check [SCHEMA.md](architecture/schema.md)
6. **Need data flow docs?** See [DATA_FLOW.md](architecture/data-flow.md)

## Documentation Standards

- All documentation is written in Markdown
- Use clear, concise language
- Include code examples where appropriate
- Keep information up-to-date with code changes
- Link to related documentation when relevant
