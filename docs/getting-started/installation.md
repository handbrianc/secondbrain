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
git clone https://github.com/your-org/secondbrain.git
cd secondbrain

# Start MongoDB and sentence-transformers services
docker-compose up -d

# Install SecondBrain
pip install -e ".[dev]"

# Verify installation
secondbrain --help
```

### Docker Setup Details

See [Docker Guide](../developer-guide/docker.md) for advanced Docker configuration.

## Option 2: Local Installation

### 1. Install MongoDB

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

### 2. Install sentence-transformers

**macOS/Linux:**
```bash
curl -fsSL https://sentence-transformers.ai/install.sh | sh
sentence-transformers serve
```

**Windows:**
Download from [sentence-transformers Website](https://sentence-transformers.ai)

### 3. Install SecondBrain

```bash
# Clone repository
git clone https://github.com/your-org/secondbrain.git
cd secondbrain

# Install with dev dependencies
pip install -e ".[dev]"

# Install sentence-transformers model
sentence-transformers pull embeddinggemma:latest
```

## Verify Installation

```bash
# Check SecondBrain version
secondbrain --version

# Check MongoDB connection
secondbrain health

# Check sentence-transformers connection
curl http://localhost:local embedding/api/tags
```

## Configuration

After installation, create a `.env` file:

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
# See [Configuration Guide](./configuration.md) for details
```

## Troubleshooting

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
sentence-transformers list

# Start sentence-transformers
sentence-transformers serve

# Pull required model
sentence-transformers pull embeddinggemma:latest
```

### Python Version Issues

```bash
# Check Python version
python --version  # Should be 3.11+

# If needed, install Python 3.11+
brew install python@3.11  # macOS
```

## Next Steps

- [Quick Start Guide](./quick-start.md) - Get started in 5 minutes
- [Configuration Guide](./configuration.md) - Configure your environment
- [User Guide](../user-guide/index.md) - Learn how to use SecondBrain
