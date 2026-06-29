# Getting Started with SecondBrain

This section guides you through installing, configuring, and running SecondBrain for the first time.

## Getting Started Steps

1. **[Installation](installation.md)** — Install SecondBrain and its dependencies
2. **[Quick Start](quick-start.md)** — Get up and running in under 5 minutes
3. **[Configuration](configuration.md)** — Customize behavior via environment variables
4. **[Troubleshooting](troubleshooting.md)** — Solutions for common issues

## Prerequisites

Before installing SecondBrain, ensure your system meets these requirements:

### Minimum Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.11 or higher |
| MongoDB | 4.4+ (local or Docker) |
| Memory | 4GB RAM minimum |
| Disk Space | 500MB for installation |

### Optional Dependencies

| Component | Purpose |
|-----------|---------|
| Docker | Containerized MongoDB and service management |
| Tesseract OCR | Image optical character recognition |
| FFmpeg | Audio transcription preprocessing |

## Installation Methods

SecondBrain can be installed via multiple methods:

### pip Installation (Recommended)

```bash
pip install -e .
```

### Development Installation

```bash
pip install -e ".[dev]"
```

### With Documentation Tools

```bash
pip install -e ".[docs]"
```

## Next Steps

After installation, proceed to the [Quick Start guide](quick-start.md) to ingest your first documents and perform your first semantic search.