#!/bin/sh
set -e

echo "Starting Ollama service..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
for i in 1 2 3 4 5; do
    if curl -s http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready"
        break
    fi
    sleep 2
done

echo "Checking if models exist..."
if ! ollama list 2>/dev/null | grep -q embeddinggemma || ! ollama list 2>/dev/null | grep -q llama3.1; then
    echo "Models not found. Pulling required models..."
    echo "Pulling embeddinggemma:latest..."
    ollama pull embeddinggemma:latest
    echo "Pulling llama3.1:latest..."
    ollama pull llama3.1:latest
    echo "All models pulled successfully!"
else
    echo "Models already exist, skipping pull"
fi

echo "Ollama ready with models. Waiting for process..."
wait $OLLAMA_PID
