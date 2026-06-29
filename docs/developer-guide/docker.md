# Docker Setup

Running SecondBrain and its services with Docker.

## Docker Architecture

SecondBrain uses Docker primarily for MongoDB deployment. The application itself runs natively on your host Python installation.

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

- MongoDB container on port 27017
- Networking configured for localhost access

### Wait for Readiness

Block until services are ready:

```bash
secondbrain start --wait
```

Displays progress and confirms when MongoDB accepts connections.

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
    This permanently deletes all ingested documents and configuration stored in MongoDB volumes.

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
MongoDB: ✓ Connected
Embedding API: ✓ Responding
```

## Dockerfile Reference

For custom deployments, here's a minimal Dockerfile:

```dockerfile
FROM python:3.11-slim

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
  mongodb:
    image: mongo:7.0
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    restart: unless-stopped

volumes:
  mongodb_data:
```

### Production Stack

```yaml
# docker-compose.prod.yml
services:
  mongodb:
    image: mongo:7.0
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    deploy:
      resources:
        limits:
          memory: 2G
    restart: unless-stopped
    healthcheck:
      test: ["cmd", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  mongodb_data:
```

## Connecting to Remote MongoDB

For cloud MongoDB deployments, configure without Docker:

```bash
export SECONDBRAIN_MONGO_URI="mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority"
```

No `secondbrain start` needed — connects remotely.

## Troubleshooting

### Docker Not Found

Install Docker Desktop or Engine:

- macOS/Windows: [Docker Desktop](https://docs.docker.com/desktop/)
- Linux: [Docker Engine](https://docs.docker.com/engine/install/)

### Port Already in Use

```bash
# Find process on port 27017
lsof -ti:27017

# Kill it
kill -9 $(lsof -ti:27017)

# Or use a different port mapping in docker-compose.yml
ports:
  - "27018:27017"
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
docker logs secondbrain-mongodb --tail 100
```

### Volume Permissions

Fix MongoDB data directory ownership:

```bash
docker exec -it secondbrain-mongo mongosh
# Then in mongosh:
db.adminCommand({getLog: "global"})
```