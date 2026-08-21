#!/bin/bash
# Start test services (Qdrant)
# Usage: ./scripts/start_test_services.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.test.yml"
# Test Qdrant publishes on port 6334 (host) -> 6333 (container)
QDRANT_HEALTH_URL="${QDRANT_HEALTH_URL:-http://localhost:6334/healthz}"

echo "=========================================="
echo "Starting Test Services"
echo "=========================================="

# Check if docker compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "ERROR: docker compose is not installed"
    echo "Install it with: sudo apt-get install docker-compose (Ubuntu) or via Docker Desktop"
    exit 1
fi

# Check if compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: docker-compose.test.yml not found at $COMPOSE_FILE"
    exit 1
fi

# Start services
echo ""
echo "Starting services with: docker compose -f $COMPOSE_FILE up -d"
echo ""

if command -v docker-compose &> /dev/null; then
    docker-compose -f "$COMPOSE_FILE" up -d
else
    docker compose -f "$COMPOSE_FILE" up -d
fi

# Wait for services to be healthy
echo ""
echo "Waiting for services to be healthy..."
echo ""

MAX_WAIT=60  # seconds
WAIT_INTERVAL=2
ELAPSED=0

# Function to check Qdrant health via its HTTP readiness endpoint
check_qdrant() {
    curl -s -o /dev/null --max-time 2 "$QDRANT_HEALTH_URL"
}

# Wait for Qdrant
echo "Checking Qdrant (http://localhost:6334)..."
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if check_qdrant; then
        echo "✓ Qdrant is healthy"
        break
    fi
    echo -n "."
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo ""
    echo "ERROR: Qdrant failed to become healthy within ${MAX_WAIT}s"
    echo ""
    echo "Service logs:"
    docker logs secondbrain-qdrant-test --tail 20
    ./scripts/stop_test_services.sh
    exit 1
fi

echo ""
echo "=========================================="
echo "All Services Started Successfully"
echo "=========================================="
echo ""
echo "Connection Info:"
echo "  Qdrant:      http://localhost:6334"
echo ""
echo "Run integration tests with:"
echo "  SECONDBRAIN_QDRANT_URL=http://localhost:6334 pytest tests/integration/ -v"
echo ""
echo "Stop services with:"
echo "  ./scripts/stop_test_services.sh"
echo ""

exit 0
