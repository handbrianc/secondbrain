# Development Setup

Complete guide to setting up your SecondBrain development environment.

## Prerequisites

### Required Software

- **Python**: 3.11 or higher
- **MongoDB**: 6.0 or higher
- **Git**: Latest version
- **Docker**: (Optional) For containerized MongoDB

### System Requirements

- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 2GB free space
- **GPU**: (Optional) For faster embeddings

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/your-org/secondbrain.git
cd secondbrain
```

### 2. Create Virtual Environment

```bash
# Create venv
python -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Install runtime only
pip install -e .
```

### 4. Set Up Pre-commit Hooks

```bash
pre-commit install
```

### 5. Configure Environment

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=secondbrain_dev
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

## MongoDB Setup

### Option 1: Local MongoDB

```bash
# Install MongoDB (macOS)
brew install mongodb-community

# Start MongoDB
brew services start mongodb-community
```

### Option 2: Docker MongoDB

```bash
# Run MongoDB container
docker run -d -p 27017:27017 --name secondbrain-mongo mongo:6.0
```

### Option 3: MongoDB Atlas

1. Create free cluster at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Get connection string
3. Update `.env` with connection string

## Verify Installation

```bash
# Check Python version
python --version  # Should be 3.11+

# Check MongoDB connection
python -c "from pymongo import MongoClient; print(MongoClient().list_database_names())"

# Run tests
pytest

# Run linter
ruff check .
```

## Development Tools

### VS Code Extensions

- Python
- Pylance
- Ruff
- MongoDB for VS Code

### Recommended Settings

```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "ruff",
    "editor.formatOnSave": true
}
```

## Common Issues

### Dependency Installation Fails

**Issue**: `pip install` fails with errors

**Solution**:
```bash
# Upgrade pip
python -m pip install --upgrade pip

# Clear cache
pip cache purge

# Try again
pip install -e ".[dev]"
```

### MongoDB Connection Failed

**Issue**: Can't connect to MongoDB

**Solution**:
1. Check MongoDB is running
2. Verify connection string in `.env`
3. Check firewall settings
4. Try connecting manually: `mongosh`

### Import Errors

**Issue**: `ModuleNotFoundError`

**Solution**:
```bash
# Reinstall in development mode
pip install -e ".[dev]" --force-reinstall
```

## Next Steps

- Read [Contributing Guide](contributing.md)
- Review [Code Standards](code-standards.md)
- Set up [Testing](TESTING.md)
- Explore [Async API](async-api.md)

## Support

- 📧 Email: [INSERT EMAIL]
- 💬 GitHub Discussions
- 🐛 Issue Tracker
