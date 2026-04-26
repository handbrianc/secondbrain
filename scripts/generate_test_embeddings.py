#!/usr/bin/env python3
"""Generate pre-computed embeddings for test data.

This script generates embeddings once and saves them to a JSON file,
eliminating the need to regenerate embeddings on every test run.

Usage:
    python scripts/generate_test_embeddings.py
"""

import json
import re
from pathlib import Path

from secondbrain.config import get_config
from secondbrain.embedding.local import LocalEmbeddingGenerator

# Extract test chunks from conftest.py
CONTFEST_PATH = (
    Path(__file__).parent.parent / "tests" / "test_quantitative" / "conftest.py"
)

with open(CONTFEST_PATH) as f:
    content = f.read()

# Extract chunk_id and chunk_text pairs
pattern = r'"chunk_id":\s*"([^"]+)",\s*"source_file":\s*"([^"]+)",\s*"page_number":\s*(\d+),\s*"chunk_text":\s*"([^"]+)"'
matches = re.findall(pattern, content)

TEST_CHUNKS = [
    {
        "chunk_id": m[0],
        "source_file": m[1],
        "page_number": int(m[2]),
        "chunk_text": m[3],
        "file_type": "markdown",
        "metadata": {},
    }
    for m in matches
]


def main():
    """Generate embeddings for all test chunks and save to JSON."""
    print("Loading embedding model...")
    cfg = get_config()
    embed_gen = LocalEmbeddingGenerator(model_name=cfg.local_embedding_model)

    print(f"Generating embeddings for {len(TEST_CHUNKS)} test chunks...")
    output = {"model": cfg.local_embedding_model, "chunks": []}

    for i, chunk in enumerate(TEST_CHUNKS, 1):
        text = chunk["chunk_text"]
        print(f"  [{i}/{len(TEST_CHUNKS)}] {chunk['chunk_id']}: {text[:50]}...")

        embedding = embed_gen.generate(text)

        chunk_with_embedding = {**chunk, "embedding": embedding}
        output["chunks"].append(chunk_with_embedding)

    # Save to JSON
    output_path = Path("tests/data/precomputed_embeddings.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\nSaving to {output_path}...")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Generated {len(output['chunks'])} embeddings")
    print(f"   Model: {output['model']}")
    print(f"   Output: {output_path}")
    print(f"   Size: {output_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
