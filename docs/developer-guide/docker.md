# Docker Setup Guide

Complete Docker setup instructions for SecondBrain development and production environments.

## Quick Start

### macOS (sentence-transformers Installed Locally)

If you have sentence-transformers installed locally via `brew install sentence-transformers`, only start MongoDB:

```bash
# Start MongoDB only
docker-compose up -d

# Start sentence-transformers locally
sentence-transformers serve

# Verify services
docker-compose ps
sentence-transformers list

# View logs
docker-compose logs -f mongodb

# Stop services
docker-compose down
```

### Linux / Windows (sentence-transformers via Docker)

```bash
# Start MongoDB and sentence-transformers
docker-compose up -d

# Or start them separately:
docker-compose up -d mongodb        # MongoDB only
docker-compose -f docker-compose.sentence-transformers.yml up -d  # sentence-transformers only

# Verify sentence-transformers is running
curl http://localhost:114../api-reference/index.mdtags

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Manual Docker Setup

### Run MongoDB

MongoDB 8.0+ is required for vector search capabilities:

```bash
# MongoDB 8.0 (recommended)
docker run -d --name mongodb -p 27017:27017 mongo:8.0

# MongoDB 7.0 (minimum supported)
docker run -d --name mongodb -p 27017:27017 mongo:7.0
```

### Run sentence-transformers

```bash
# Start sentence-transformers container
docker run -d --name sentence-transformers -p local embedding:local embedding sentence-transformers/sentence-transformers

# Pull the embedding model (first time only)
docker exec sentence-transformers sentence-transformers pull embeddinggemma:latest

# Verify model is available
docker exec sentence-transformers sentence-transformers list
```

### Verify Setup

```bash
# Check MongoDB is running
docker exec mongodb mongosh --eval "db.version()"

# Check sentence-transformers is responding
curl http://localhost:114../api-reference/index.mdtags

# Check both services
docker-compose ps
```

## Docker Compose Configuration

### docker-compose.yml

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:8.0
    container_name: secondbrain-mongodb
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    restart: unless-stopped

volumes:
  mongodb_data:
```

### docker-compose.sentence-transformers.yml

```yaml
version: '3.8'

services:
  sentence-transformers:
    image: sentence-transformers/sentence-transformers:latest
    container_name: secondbrain-sentence-transformers
    ports:
      - "local embedding:local embedding"
    volumes:
      - sentence-transformers_data:/root/.sentence-transformers
    restart: unless-stopped

volumes:
  sentence-transformers_data:
```

## Persistent Storage

### MongoDB Data

MongoDB data is persisted in Docker volumes:

```bash
# List MongoDB volume
docker volume ls | grep mongodb

# Backup MongoDB data
docker run --rm -v secondbrain_mongodb_data:/data mongo:8.0 mongodump --out /backup

# Restore MongoDB data
docker run --rm -v secondbrain_mongodb_data:/data -v $(pwd)/backup:/backup mongo:8.0 mongorestore /backup
```

### sentence-transformers Models

sentence-transformers models are persisted in Docker volumes:

```bash
# List sentence-transformers volume
docker volume ls | grep sentence-transformers

# Backup sentence-transformers models
docker run --rm -v secondbrain_sentence-transformers_data:/root/.sentence-transformers busybox tar czf /backup/sentence-transformers.tar.gz /root/.sentence-transformers

# Restore sentence-transformers models
docker run --rm -v secondbrain_sentence-transformers_data:/root/.sentence-transformers -v $(pwd)/backup:/backup busybox tar xzf /backup/sentence-transformers.tar.gz -C /
```

## Troubleshooting

### MongoDB Connection Issues

**Problem**: Cannot connect to MongoDB

**Solutions**:
1. Verify MongoDB is running:
   ```bash
   docker-compose ps
   docker logs secondbrain-mongodb
   ```

2. Check connection string in `.env`:
   ```
   SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
   ```

3. Ensure MongoDB version is 8.0+ (required for vector search):
   ```bash
   docker exec secondbrain-mongodb mongosh --eval "db.version()"
   ```

### sentence-transformers Connection Issues

**Problem**: Cannot connect to sentence-transformers

**Solutions**:
1. Verify sentence-transformers is running:
   ```bash
   curl http://localhost:114../api-reference/index.mdtags
   ```

2. Check sentence-transformers URL in `.env`:
   ```
   SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:local embedding
   ```

3. Pull the embedding model:
   ```bash
   docker exec secondbrain-sentence-transformers sentence-transformers pull embeddinggemma:latest
   ```

4. Check sentence-transformers logs:
   ```bash
   docker logs secondbrain-sentence-transformers
   ```

### Port Conflicts

**Problem**: Port already in use

**Solutions**:
1. Check what's using the port:
   ```bash
   # MongoDB port
   lsof -i :27017  # macOS/Linux
   netstat -ano | findstr :27017  # Windows

   # sentence-transformers port
   lsof -i :local embedding  # macOS/Linux
   netstat -ano | findstr :local embedding  # Windows
   ```

2. Change port mapping in docker-compose.yml:
   ```yaml
   ports:
     - "27018:27017"  # Use different host port
   ```

3. Update `.env` to match new port:
   ```
   SECONDBRAIN_MONGO_URI=mongodb://localhost:27018
   ```

### Memory Issues

**Problem**: Containers running out of memory

**Solutions**:
1. Increase Docker memory limit (Docker Desktop):
   - Settings → Resources → Memory: 4GB+ recommended

2. Limit MongoDB memory usage:
   ```yaml
   services:
     mongodb:
       mem_limit: 2g
   ```

3. Monitor container resource usage:
   ```bash
   docker stats secondbrain-mongodb secondbrain-sentence-transformers
   ```

## Development Workflow

### Hot Reload with Docker

For development, you can mount the source code:

```yaml
services:
  app:
    build: .
    volumes:
      - ./src:/app/src
      - ./tests:/app/tests
    environment:
      - SECONDBRAIN_MONGO_URI=mongodb://mongodb:27017
      - SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://sentence-transformers:local embedding
    depends_on:
      - mongodb
      - sentence-transformers
```

### Running Tests in Docker

```bash
# Build test image
docker build -t secondbrain-test .

# Run tests
docker run --rm secondbrain-test pytest

# Run tests with coverage
docker run --rm secondbrain-test pytest --cov=secondbrain --cov-report=html

# View coverage report
open htmlcov/index.html
```

## Production Deployment

### Security Hardening

1. **Use environment variables for secrets**:
   ```bash
   docker run -e MONGO_INITDB_ROOT_USERNAME=admin -e MONGO_INITDB_ROOT_PASSWORD=secret mongo:8.0
   ```

2. **Enable authentication**:
   ```yaml
   services:
     mongodb:
       command: mongod --auth
       environment:
         - MONGO_INITDB_ROOT_USERNAME=admin
         - MONGO_INITDB_ROOT_PASSWORD=${MONGO_PASSWORD}
   ```

3. **Network isolation**:
   ```yaml
   networks:
     secondbrain_net:
       driver: bridge
   ```

### Resource Limits

```yaml
services:
  mongodb:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

## Next Steps

- [Configuration Guide](./configuration.md) - Environment variables and settings
- [Development Setup](./development.md) - Local development workflow
- [Architecture Overview](../architecture/SCHEMA.md) - Database schema
