# SecondBrain Documentation

Welcome to the comprehensive documentation for SecondBrain - your local document intelligence CLI.

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
│   ├── index.md             # User guide overview
│   ├── cli-reference.md     # CLI commands reference
│   ├── document-ingestion.md # Document ingestion guide
│   ├── search-guide.md      # Search guide
│   └── document-management.md # Document management
├── developer-guide/         # Developer documentation
│   ├── index.md             # Developer guide overview
│   ├── development.md       # Development setup and workflow
│   ├── docker.md            # Docker setup and deployment
│   ├── configuration.md     # Full configuration reference
│   ├── building.md          # Create distributable binaries
│   ├── async-api.md         # Asynchronous API usage
│   ├── code-standards.md    # Coding standards and best practices
│   ├── TESTING.md           # Testing guide
│   ├── TEST_PERFORMANCE_OPTIMIZATION.md # Test performance
│   ├── python-cli-best-practices-checklist.md # CLI best practices
│   ├── contributing.md      # How to contribute to the project
│   ├── migrations.md        # Schema migration strategies
│   ├── security.md          # Security guidelines
│   └── changelog.md         # Version history and changes
├── architecture/            # Architecture documentation
│   ├── index.md             # Architecture overview
│   ├── DATA_FLOW.md         # Data flow and component interactions
│   ├── SCHEMA.md            # Database schema reference
│   ├── INTEGRATION_TEST_EVALUATION.md # Integration testing
│   ├── LICENSE-RISK-REPORT.md # License risk analysis
│   └── SBOM_ANALYSIS.md     # SBOM analysis
├── api/                     # Auto-generated API docs
│   └── index.md             # API reference overview
├── security/                # Security reports
│   └── index.md             # Security guide
├── examples/                # Code examples
│   └── README.md            # Examples overview
├── LICENSE.md               # License information
└── migration.md             # Migration guide
```

## Quick Navigation

### For New Users

| Guide | Description |
|-------|-------------|
| [Getting Started](getting-started/index.md) | Installation and setup overview |
| [Quick Start](getting-started/quick-start.md) | Get running in 5 minutes |
| [Installation Guide](getting-started/installation.md) | Detailed installation steps |
| [Configuration](getting-started/configuration.md) | Essential configuration options |

### For Users

| Guide | Description |
|-------|-------------|
| [User Guide](user-guide/index.md) | Complete usage reference |
| [CLI Reference](user-guide/cli-reference.md) | All commands and options |
| [Document Ingestion](user-guide/document-ingestion.md) | Adding documents |
| [Semantic Search](user-guide/search-guide.md) | Finding documents |
| [Document Management](user-guide/document-management.md) | List and delete |
| [Conversational Q&A](user-guide/conversational-qa.md) | Multi-turn chat |

### For Developers

| Guide | Description |
|-------|-------------|
| [Developer Guide](developer-guide/index.md) | Development setup and workflows |
| [Development Setup](developer-guide/development.md) | Get started with code |
| [Testing Guide](developer-guide/TESTING.md) | Test structure and strategies |
| [Code Standards](developer-guide/code-standards.md) | Coding guidelines |
| [Contributing](developer-guide/contributing.md) | How to contribute |
| [Async API](developer-guide/async-api.md) | Asynchronous programming |
| [Docker Setup](developer-guide/docker.md) | Containerized deployment |
| [Building](developer-guide/building.md) | Create distributable binaries |

### Architecture & Technical

| Guide | Description |
|-------|-------------|
| [Architecture Overview](architecture/index.md) | System design and components |
| [Data Flow](architecture/DATA_FLOW.md) | Processing pipelines |
| [Schema Reference](architecture/SCHEMA.md) | Database structure |
| [SBOM Analysis](architecture/SBOM_ANALYSIS.md) | Dependency inventory |
| [License Risk Report](architecture/LICENSE-RISK-REPORT.md) | License compliance |

### Examples & Reference

| Resource | Description |
|----------|-------------|
| [Examples Overview](examples/README.md) | All code examples |
| [Troubleshooting](getting-started/troubleshooting.md) | Common issues and solutions |
| [Migration Guide](migration.md) | Schema migration strategies |
| [Security Guide](developer-guide/security.md) | Security best practices |
| [Changelog](developer-guide/changelog.md) | Version history |

## Contributing to Documentation

We welcome documentation improvements! See [Contributing Guide](developer-guide/contributing.md) for details.

### Quick Documentation Contributions

- Fix typos or broken links
- Improve clarity or add examples
- Add missing commands or options
- Update outdated information

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE.md) for details.

## Documentation Standards

- All documentation is written in Markdown
- Use clear, concise language
- Include code examples where appropriate
- Keep information up-to-date with code changes
- Link to related documentation when relevant
