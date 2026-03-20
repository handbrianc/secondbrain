# Docker Setup

Containerized development and deployment with SecondBrain.

## Docker Compose Setup

### Start Services

```bash
# Start MongoDB and sentence-transformers
docker-compose up -d
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| mongo | 27017 | MongoDB database |
| sentence-transformers | 11434 | Embedding API |

### Check Status

```bash
# View running containers
docker-compose ps

# View logs
docker-compose logs -f
```

### Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## Building the Docker Image

```bash
# Build the image
docker build -t secondbrain:latest .

# Build with build args
docker build --build-arg VERSION=0.1.0 -t secondbrain:0.1.0 .
```

## Running in Docker

```bash
# Run with mounted volume
docker run -it \
  -v $(pwd)/documents:/data \
  -v $(pwd)/.env:/app/.env \
  secondbrain:latest \
  ingest /data/
```

## Development with Docker

### Mount Source Code

```bash
docker run -it \
  -v $(pwd)/src:/app/src \
  -v $(pwd)/tests:/app/tests \
  secondbrain:latest
```

### Run Tests in Container

```bash
docker-compose run --rm app pytest
```

## Configuration

### Environment Variables

```yaml
# docker-compose.yml
services:
  mongo:
    environment:
      - MONGO_INITDB_ROOT_USERNAME=admin
      - MONGO_INITDB_ROOT_PASSWORD=secret
  
  sentence-transformers:
    environment:
      - MODEL=all-MiniLM-L6-v2
```

### Volume Mounts

```yaml
volumes:
  - mongo_data:/data/db
  - ./documents:/documents:ro
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs mongo
docker-compose logs sentence-transformers

# Restart services
docker-compose restart
```

### Port Conflicts

```bash
# Check what's using the port
lsof -i :27017
lsof -i :11434

# Change ports in docker-compose.yml
```

### Permission Issues

```bash
# Run as current user
docker run -u $(id -u):$(id -g) secondbrain:latest
```

## Production Deployment

### Build for Production

```bash
# Multi-stage build
docker build -f Dockerfile.prod -t secondbrain-prod .
```

### Security Best Practices

- Use non-root user
- Scan for vulnerabilities
- Use specific versions
- Enable TLS for MongoDB

## Next Steps

- [Development Setup](development.md) - Local development
- [Building Guide](building.md) - Create distributables
- [Configuration](configuration.md) - Environment settings
