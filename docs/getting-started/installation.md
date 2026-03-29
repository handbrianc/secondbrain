# Installation Guide

Complete installation guide for SecondBrain.

## System Requirements

### Minimum Requirements

- **Python**: 3.11 or higher
- **RAM**: 4GB
- **Storage**: 2GB free space
- **MongoDB**: 6.0 or higher

### Recommended

- **RAM**: 8GB+
- **GPU**: NVIDIA GPU (for faster embeddings)
- **Storage**: SSD

## Installation Methods

### pip Installation

```bash
# Install from PyPI
pip install secondbrain

# Install with dev dependencies
pip install secondbrain[dev]
```

### From Source

```bash
# Clone repository
git clone https://github.com/your-org/secondbrain.git
cd secondbrain

# Install
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### Docker Installation

```bash
# Pull image
docker pull secondbrain/secondbrain:latest

# Run
docker run -it secondbrain/secondbrain:latest
```

## MongoDB Setup

### Option 1: Local MongoDB

**macOS:**
```bash
brew install mongodb-community
brew services start mongodb-community
```

**Ubuntu/Debian:**
```bash
wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl start mongod
```

**Windows:**
1. Download MongoDB Community Server
2. Run installer
3. Start MongoDB service

### Option 2: MongoDB Atlas (Cloud)

1. Create account at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create free cluster
3. Get connection string
4. Add to `.env`:
   ```env
   MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net
   ```

### Option 3: Docker MongoDB

```bash
docker run -d -p 27017:27017 --name secondbrain-mongo mongo:6.0
```

## Verification

### Check Installation

```bash
# Check version
secondbrain --version

# Check MongoDB connection
secondbrain health-check
```

### Run Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Troubleshooting

### Installation Fails

**Issue**: pip install fails

**Solution**:
```bash
# Upgrade pip
python -m pip install --upgrade pip

# Clear cache
pip cache purge

# Try again
pip install secondbrain
```

### MongoDB Connection Failed

**Issue**: Can't connect to MongoDB

**Solution**:
1. Verify MongoDB is running
2. Check connection string
3. Test connection: `mongosh`

### Import Errors

**Issue**: ModuleNotFoundError

**Solution**:
```bash
pip install -e . --force-reinstall
```

## Uninstallation

```bash
# Remove package
pip uninstall secondbrain

# Remove MongoDB data (optional)
rm -rf ~/.mongodb
```

## Next Steps

- [Quick Start](quick-start.md)
- [Configuration](configuration.md)
- [User Guide](../user-guide/index.md)
