#!/bin/bash
# Start test services (MongoDB and sentence-transformers)
# Usage: ./scripts/start_test_services.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.test.yml"

echo "=========================================="
echo "Starting Test Services"
echo "=========================================="

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "ERROR: docker-compose is not installed"
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
echo "Starting services with: docker-compose -f $COMPOSE_FILE up -d"
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

MAX_WAIT=120  # seconds
WAIT_INTERVAL=5
ELAPSED=0

# Function to check MongoDB health
check_mongodb() {
    docker exec secondbrain-mongodb-test mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1
}

# Function to check sentence-transformers health
check_embeddings() {
    curl -sf http://localhost:11435/health > /dev/null 2>&1
}

# Wait for MongoDB
echo "Checking MongoDB (localhost:27018)..."
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if check_mongodb; then
        echo "✓ MongoDB is healthy"
        break
    fi
    echo -n "."
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo ""
    echo "ERROR: MongoDB failed to become healthy within ${MAX_WAIT}s"
    echo ""
    echo "Service logs:"
    docker logs secondbrain-mongodb-test --tail 20
    ./scripts/stop_test_services.sh
    exit 1
fi

ELAPSED=0

# Wait for sentence-transformers
echo "Checking sentence-transformers (localhost:11435)..."
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if check_embeddings; then
        echo "✓ Sentence-transformers is healthy"
        break
    fi
    echo -n "."
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo ""
    echo "ERROR: Sentence-transformers failed to become healthy within ${MAX_WAIT}s"
    echo ""
    echo "Service logs:"
    docker logs secondbrain-embeddings-test --tail 20
    ./scripts/stop_test_services.sh
    exit 1
fi

echo ""
echo "=========================================="
echo "All Services Started Successfully"
echo "=========================================="
echo ""
echo "Connection Info:"
echo "  MongoDB:      mongodb://testuser:testpass@localhost:27018/secondbrain_test"
echo "  Embeddings:   http://localhost:11435"
echo ""
echo "Run integration tests with:"
echo "  pytest tests/integration/ -v"
echo ""
echo "Stop services with:"
echo "  ./scripts/stop_test_services.sh"
echo ""

exit 0
