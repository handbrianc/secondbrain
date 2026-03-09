#!/bin/bash
# Bulk document ingestion script
# Usage: ./ingest_entire_directory.sh /path/to/docs

set -e

PATH_TO_INGEST="${1:-.}"
BATCH_SIZE="${2:-10}"

echo "=========================================="
echo "SecondBrain Bulk Ingestion Script"
echo "=========================================="
echo "Path: $PATH_TO_INGEST"
echo "Batch size: $BATCH_SIZE"
echo ""

# Check if path exists
if [ ! -d "$PATH_TO_INGEST" ]; then
    echo "Error: Directory not found: $PATH_TO_INGEST"
    exit 1
fi

# Count files
FILE_COUNT=$(find "$PATH_TO_INGEST" -type f | wc -l)
echo "Found $FILE_COUNT files to process"
echo ""

# Run ingestion
python examples/advanced/batch_ingestion.py \
    "$PATH_TO_INGEST" \
    --batch-size "$BATCH_SIZE" \
    --max-workers 4

echo ""
echo "=========================================="
echo "Ingestion complete!"
echo "=========================================="
