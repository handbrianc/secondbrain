# Docker Setup

Running SecondBrain and its services with Docker.

## Docker Architecture

SecondBrain uses Docker primarily for Qdrant deployment. The application itself runs natively on your host Python installation.

## Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- Docker Compose plugin (v2)

Verify installations:

```bash
docker --version
docker compose version
```

## Starting Services

### Quick Start

Start the default Docker Compose stack:

```bash
secondbrain start
```

This launches:

- The `secondbrain-qdrant` Qdrant vector database container on port 6333
- Networking configured for localhost access

### Wait for Readiness

Block until services are ready:

```bash
secondbrain start --wait
```

Displays progress and confirms when Qdrant accepts connections.

### Custom Compose File

Use project-specific configurations:

```bash
secondbrain start --compose-file ./deployments/production.yml
```

### Custom Project Name

Isolate multiple deployments:

```bash
secondbrain start --project-name secondbrain-staging
```

## Stopping Services

### Graceful Shutdown

```bash
secondbrain stop
```

Prompts for confirmation before stopping containers.

### Immediate Stop

Skip confirmation prompts:

```bash
secondbrain stop --force
```

### Remove Volumes

Delete persistent data:

```bash
secondbrain stop --remove-volumes
```

!!! Warning
    This permanently deletes all ingested vector data stored in the Qdrant volume.

## Checking Service Status

### Docker PS

View running containers:

```bash
docker ps
```

### Health Check

Verify SecondBrain can reach services:

```bash
secondbrain health
```

Sample healthy output:

```
Qdrant: ✓ Connected
Embedding API: ✓ Responding
```

## Dockerfile Reference

For custom deployments, here's a minimal Dockerfile:

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install SecondBrain
COPY pyproject.toml ./
RUN pip install -e .

ENTRYPOINT ["secondbrain"]
CMD ["--help"]
```

## Docker Compose Examples

### Local Development

```yaml
# docker-compose.dev.yml
services:
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

volumes:
  qdrant_data:
```

### Production Stack

```yaml
# docker-compose.prod.yml
services:
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    deploy:
      resources:
        limits:
          memory: 2G
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:6333/ || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  qdrant_data:
```

## Connecting to a Remote Qdrant

For a remote Qdrant deployment, configure without Docker:

```bash
export SECONDBRAIN_QDRANT_URL="https://qdrant.example.com:6333"
```

No `secondbrain start` needed — connects remotely.

## Troubleshooting

### Docker Not Found

Install Docker Desktop or Engine:

- macOS/Windows: [Docker Desktop](https://docs.docker.com/desktop/)
- Linux: [Docker Engine](https://docs.docker.com/engine/install/)

### Port Already in Use

```bash
# Find process on port 6333
lsof -ti:6333

# Kill it
kill -9 $(lsof -ti:6333)

# Or use a different port mapping in docker-compose.yml
ports:
  - "6334:6333"
```

### Permission Denied (Linux)

Add your user to the docker group:

```bash
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### Container Crash Logs

Debug startup failures:

```bash
docker logs secondbrain-qdrant --tail 100
```

### Volume Permissions

Fix Qdrant data directory ownership:

```bash
docker exec -it secondbrain-qdrant sh
```
