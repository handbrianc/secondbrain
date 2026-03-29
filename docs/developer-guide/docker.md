# Docker Guide

Container deployment guide for SecondBrain.

## Quick Start

### Run with Docker

```bash
# Pull image
docker pull secondbrain/secondbrain:latest

# Run container
docker run -it \
  -e MONGODB_URI=mongodb://mongo:27017 \
  secondbrain/secondbrain:latest
```

## Docker Compose

### Development Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  secondbrain:
    build: .
    volumes:
      - ./documents:/app/documents
      - .env:/app/.env:ro
    depends_on:
      - mongo
    environment:
      - MONGODB_URI=mongodb://mongo:27017

  mongo:
    image: mongo:6.0
    volumes:
      - mongo-data:/data/db
    ports:
      - "27017:27017"

volumes:
  mongo-data:
```

### Production Setup

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  secondbrain:
    image: secondbrain/secondbrain:latest
    restart: unless-stopped
    environment:
      - MONGODB_URI=mongodb://mongo:27017
    depends_on:
      - mongo

  mongo:
    image: mongo:6.0
    restart: unless-stopped
    volumes:
      - mongo-data:/data/db
    environment:
      - MONGO_INITDB_ROOT_USERNAME=admin
      - MONGO_INITDB_ROOT_PASSWORD=${MONGO_PASSWORD}

volumes:
  mongo-data:
```

## Dockerfile

### Multi-stage Build

```dockerfile
# Build stage
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages
COPY --from=builder /root/.local /root/.local

# Copy application
COPY . .

# Set environment
ENV PATH=/root/.local/bin:$PATH

# Run as non-root
RUN useradd -m -u 1000 secondbrain
USER secondbrain

# Run
CMD ["secondbrain"]
```

## Configuration

### Environment Variables

```dockerfile
ENV MONGODB_URI=mongodb://mongo:27017
ENV MONGODB_DB=secondbrain
ENV EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### Volume Mounts

```bash
# Mount documents
-v /path/to/documents:/app/documents

# Mount config
-v /path/to/.env:/app/.env:ro

# Mount data
-v secondbrain-data:/app/data
```

## GPU Support

### NVIDIA Docker

```bash
# Install NVIDIA Container Toolkit
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

# Run with GPU
docker run --gpus all \
  secondbrain/secondbrain:latest
```

### Docker Compose GPU

```yaml
services:
  secondbrain:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## Security

### Non-root User

```dockerfile
RUN useradd -m -u 1000 secondbrain
USER secondbrain
```

### Read-only Filesystem

```bash
docker run --read-only \
  --tmpfs /tmp \
  secondbrain/secondbrain:latest
```

### Secrets Management

```bash
docker secret create mongo_password mongo_password.txt

docker run --secret mongo_password \
  secondbrain/secondbrain:latest
```

## Monitoring

### Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import secondbrain; secondbrain.health_check()"
```

### Logging

```yaml
services:
  secondbrain:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Scaling

### Horizontal Scaling

```bash
# Run multiple instances
docker-compose up -d --scale secondbrain=3
```

### Load Balancing

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - secondbrain
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs secondbrain

# Check environment
docker exec secondbrain env

# Inspect container
docker inspect secondbrain
```

### MongoDB Connection Issues

```bash
# Check MongoDB is running
docker ps | grep mongo

# Test connection
docker exec secondbrain mongosh mongodb://mongo:27017
```

## See Also

- [Deployment](../getting-started/installation.md)
- [Configuration](configuration.md)
- [Security](security.md)
