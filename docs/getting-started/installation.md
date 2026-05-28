# Installation Guide

This guide covers installing SecondBrain on your system.

## Prerequisites

Before installing SecondBrain, ensure you have:

- **Python 3.11+** - Check with `python --version`
- **MongoDB 8.0+** - Can run via Docker or local installation
- **sentence-transformers** - For embedding generation (can run via Docker or local)

## Option 1: Docker (Recommended)

The easiest way to get started is using Docker Compose:

```bash
# Clone the repository
git clone https://github.com/your-username/secondbrain.git
cd secondbrain

# Start MongoDB and sentence-transformers services
docker-compose up -d

# Choose your installation profile:
# - For production use: pip install -e "."
# - For development: pip install -e ".[dev]"
pip install -e ".[dev]"

# Verify installation
secondbrain --help
```

### Choose Your Installation Profile

SecondBrain offers different installation profiles based on your needs:

| Profile | Command | Use Case |
|---------|---------|----------|
| **Runtime** | `pip install -e "."` | Just use SecondBrain |
| **Development** | `pip install -e ".[dev]"` | Develop/contribute to SecondBrain |
| **Qualitative Testing** | `pip install -e ".[qualitative]"` | Safety/accuracy evaluation |
| **Observability** | `pip install -e ".[opentelemetry]"` | Distributed tracing |

**Most users**: Use **Runtime** for production or **Development** for contributing.

> **See [Dependency Installation Guide](DEPENDENCIES.md) for complete details** on all dependency types, external service requirements, and troubleshooting.

### Docker Setup Details

See [Docker Guide](../developer-guide/docker.md) for advanced Docker configuration.

## Option 2: Local Installation

### 1. Install Prerequisites

You'll need these external services before installing SecondBrain:

#### MongoDB 8.0+

**macOS:**
```bash
brew install mongodb-community
brew services start mongodb-community
```

**Linux:**
```bash
# Follow MongoDB official installation guide for your distribution
# https://www.mongodb.com/docs/manual/administration/install-community/
```

**Windows:**
Download from [MongoDB Download Center](https://www.mongodb.com/try/download/community)

#### Sentence-Transformers Service

**Docker (Recommended):**
```bash
docker-compose up -d sentence-transformers
```

**Local Installation:**
```bash
# Install the service
pip install sentence-transformers

# Start the service
sentence-transformers serve
```

> **See [Dependency Installation Guide](DEPENDENCIES.md#external-service-dependencies) for detailed installation instructions** for all external services.

### 2. Install SecondBrain

Choose the installation profile that matches your needs:

**For Production Use (Runtime Only):**
```bash
# Clone repository
git clone https://github.com/your-username/secondbrain.git
cd secondbrain

# Install runtime dependencies only
pip install -e "."

# This installs only the 19 core packages needed to run SecondBrain
```

**For Development:**
```bash
# Clone repository
git clone https://github.com/your-username/secondbrain.git
cd secondbrain

# Install with all development dependencies
pip install -e ".[dev]"

# This includes runtime + testing, linting, security tools, and more
```

**For Qualitative Testing:**
```bash
# Start with dev installation
pip install -e ".[dev]"

# Add qualitative testing dependencies
pip install -e ".[qualitative]"
```

> **See [Dependency Installation Guide](DEPENDENCIES.md#installation-profiles) for complete installation profiles** with use cases and disk space requirements.

## Verify Installation

```bash
# Check SecondBrain version
secondbrain --version

# Check MongoDB connection
secondbrain health

# Check sentence-transformers connection
curl http://localhost:11434/api/tags
```

## Configuration

After installation, create a `.env` file:

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
# See [Configuration Guide](configuration.md) for details
```

## Troubleshooting

For common dependency and installation issues, see the [Dependency Troubleshooting Section](DEPENDENCIES.md#troubleshooting).

### MongoDB Connection Failed

```bash
# Check if MongoDB is running
docker ps | grep mongo  # If using Docker
brew services list | grep mongodb  # macOS with Homebrew

# Start MongoDB
docker-compose up -d  # Docker
brew services start mongodb-community  # macOS
```

### sentence-transformers Not Responding

```bash
# Check sentence-transformers status
curl http://localhost:11434/api/tags  # API check

# Start sentence-transformers
docker-compose up -d sentence-transformers  # Docker
sentence-transformers serve  # Local

# Pull required model
sentence-transformers pull all-MiniLM-L6-v2
```

### Python Version Issues

```bash
# Check Python version
python --version  # Should be 3.11+

# If needed, install Python 3.11+
brew install python@3.11  # macOS
```

### Dependency Conflicts

```bash
# Create fresh virtual environment
python -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Reinstall
pip install -e ".[dev]" --force-reinstall
```

> **More troubleshooting tips**: [Dependency Troubleshooting Guide](DEPENDENCIES.md#troubleshooting)

## Next Steps

- [Quick Start Guide](quick-start.md) - Get started in 5 minutes
- [Configuration Guide](configuration.md) - Configure your environment
- [User Guide](../user-guide/index.md) - Learn how to use SecondBrain
