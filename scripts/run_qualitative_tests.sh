#!/bin/bash
# Run qualitative tests for SecondBrain

set -e

echo "================================"
echo "Qualitative Test Runner"
echo "================================"

# Fast tests (no services required)
echo ""
echo "Running fast qualitative tests (no services)..."
pytest tests/test_qualitative/test_safety_privacy.py -m "not integration" -v

echo ""
echo "Running hallucination detection tests..."
pytest tests/test_qualitative/test_hallucination_detection.py -v

# Integration tests (require MongoDB)
echo ""
echo "Running integration tests (requires MongoDB)..."
if pgrep -x "mongo" > /dev/null; then
    pytest tests/test_qualitative/ -m "integration" -v
else
    echo "Skipping integration tests (MongoDB not running)"
    echo "Start services with: docker-compose up -d"
fi

echo ""
echo "================================"
echo "Qualitative tests complete!"
echo "================================"
