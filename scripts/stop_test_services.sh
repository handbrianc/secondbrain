#!/bin/bash
# Stop test services and optionally clean volumes
# Usage: ./scripts/stop_test_services.sh [--clean]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.test.yml"

CLEAN_VOLUMES=false

# Parse arguments
if [ "$1" == "--clean" ] || [ "$1" == "-c" ]; then
    CLEAN_VOLUMES=true
fi

echo "=========================================="
echo "Stopping Test Services"
echo "=========================================="

# Check if compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "WARNING: docker-compose.test.yml not found at $COMPOSE_FILE"
    echo "Attempting to stop by container names anyway..."
fi

# Stop services
echo ""
echo "Stopping services..."

if command -v docker-compose &> /dev/null; then
    if [ -f "$COMPOSE_FILE" ]; then
        docker-compose -f "$COMPOSE_FILE" down
    else
        docker stop secondbrain-mongodb-test secondbrain-embeddings-test 2>/dev/null || true
    fi
else
    if [ -f "$COMPOSE_FILE" ]; then
        docker compose -f "$COMPOSE_FILE" down
    else
        docker stop secondbrain-mongodb-test secondbrain-embeddings-test 2>/dev/null || true
    fi
fi

# Clean volumes if requested
if [ "$CLEAN_VOLUMES" = true ]; then
    echo ""
    echo "Cleaning up volumes..."
    
    if command -v docker-compose &> /dev/null; then
        if [ -f "$COMPOSE_FILE" ]; then
            docker-compose -f "$COMPOSE_FILE" down -v
        fi
    else
        if [ -f "$COMPOSE_FILE" ]; then
            docker compose -f "$COMPOSE_FILE" down -v
        fi
    fi
    
    # Also try to remove volumes by name directly
    docker volume rm secondbrain-test-mongo_test_data 2>/dev/null || true
    docker volume rm secondbrain-test-model_cache 2>/dev/null || true
    
    echo "Volumes cleaned"
fi

echo ""
echo "Test services stopped"
echo ""

# Show status
echo "Current service status:"
if command -v docker-compose &> /dev/null && [ -f "$COMPOSE_FILE" ]; then
    docker-compose -f "$COMPOSE_FILE" ps 2>/dev/null || echo "No running services"
else
    docker ps --filter "name=secondbrain-mongodb-test" --filter "name=secondbrain-embeddings-test" 2>/dev/null || echo "No running services"
fi

echo ""
echo "=========================================="

exit 0
