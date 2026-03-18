# User Guide

Comprehensive usage guide for SecondBrain.

## Overview

This section covers how to use SecondBrain for common tasks:

- [CLI Commands](./cli-reference.md) - All available commands
- [Document Ingestion](./document-ingestion.md) - Adding documents
- [Semantic Search](./search-guide.md) - Finding documents
- [Document Management](./document-management.md) - Listing and deleting

## Quick Navigation

### Common Tasks

| Task | Command | Guide |
|------|---------|-------|
| Add documents | `secondbrain ingest` | [Ingestion Guide](./document-ingestion.md) |
| Search | `secondbrain search` | [Search Guide](./search-guide.md) |
| List documents | `secondbrain list` | [Document Management](./document-management.md) |
| Delete documents | `secondbrain delete` | [Document Management](./document-management.md) |
| Check health | `secondbrain health` | [CLI Reference](./cli-reference.md) |

### Document Formats

SecondBrain supports:
- **Documents**: PDF, DOCX, PPTX, XLSX
- **Web**: HTML, Markdown, Text
- **Media**: Images (OCR), Audio (transcription)

See [Document Ingestion](./document-ingestion.md) for details.

## Advanced Topics

- [Async API](../developer-guide/async-api.md) - Programmatic usage
- [REST API](https://example.com) - HTTP interfaces (coming soon)

## Examples

Practical examples are available in the [examples directory](../examples/README.md).

## Related Documentation

- [Getting Started](../getting-started/index.md) - New users
- [CLI Reference](../api-reference/cli.md) - Command details
- [Configuration](../getting-started/configuration.md) - Setup options
- [Developer Guide](../developer-guide/index.md) - For contributors
