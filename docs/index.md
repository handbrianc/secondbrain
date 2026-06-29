# SecondBrain Documentation

Welcome to SecondBrain, a privacy-first local document intelligence CLI that enables semantic search over your documents using MongoDB and OpenAI-compatible embedding services.

## Overview

SecondBrain is designed for developers and power users who want to maintain complete control over their data while enjoying powerful document search capabilities. All document parsing, chunking, and storage happen locally on your machine.

## Key Features

- **Privacy-First Architecture**: All processing occurs locally — no data leaves your machine
- **Multi-Format Support**: Ingest PDFs, DOCX, PPTX, XLSX, HTML, Markdown, images, audio files, and more
- **Semantic Search**: Natural language queries with relevance-ranked results using vector similarity
- **High Performance**: Multicore ingestion processing and async API for efficient batch operations
- **Production-Ready**: Includes circuit breakers, rate limiting, structured logging, and OpenTelemetry tracing
- **Conversational Q&A**: Chat with your documents using RAG-powered conversational interfaces

## Quick Links

| Section | Description |
|---------|-------------|
| [Getting Started](getting-started/index.md) | Installation, setup, and first steps |
| [User Guide](user-guide/index.md) | Complete usage guide for day-to-day operations |
| [CLI Reference](user-guide/cli-reference.md) | Detailed command-line interface documentation |
| [Configuration](getting-started/configuration.md) | Environment variable configuration reference |
| [Developer Guide](developer-guide/index.md) | Development setup and contribution guidelines |
| [Architecture](architecture/index.md) | System design and technical architecture |
| [Security](security/index.md) | Security considerations and best practices |

## System Requirements

- **Python**: 3.11 or higher
- **MongoDB**: Local installation or Docker container
- **Docker**: Optional, for containerized setup and service management

## Supported File Types

SecondBrain supports a wide variety of document formats:

| Category | Formats |
|----------|---------|
| Documents | PDF, DOCX, PPTX, XLSX, HTML, MD, TXT, ASCII_DOC, ADOC, TEX |
| Data | CSV, XML, JSON |
| Images | PNG, JPG, JPEG, TIFF, TIF, BMP, WEBP |
| Media | WAV, MP3, VTT |

## Package Information

- **Package Version**: 0.4.0
- **Package Manager**: pip
- **Entry Point**: `secondbrain` command

## License

SecondBrain is released under the MIT License. See the [license](../LICENSE.md) page for full terms and conditions.