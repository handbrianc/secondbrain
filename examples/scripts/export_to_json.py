#!/usr/bin/env python3
"""Export ingested documents to JSON format.

Usage:
    python export_to_json.py --output documents.json --limit 100
"""

import argparse
import json

from rich.console import Console

from secondbrain.logging import setup_logging
from secondbrain.storage import VectorStorage

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Export documents to JSON")
    parser.add_argument("--output", "-o", required=True, help="Output JSON file")
    parser.add_argument("--limit", "-l", type=int, default=1000, help="Max documents")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    console.print(f"[blue]Exporting up to {args.limit} documents...[/blue]")

    storage = VectorStorage()
    chunks = storage.list_chunks(limit=args.limit)

    export_data = {
        "total_exported": len(chunks),
        "documents": [
            {
                "source": c.source_file,
                "page": c.page_number,
                "text": c.chunk_text,
                "metadata": c.metadata or {},
            }
            for c in chunks
        ],
    }

    from pathlib import Path

    output_path = Path(args.output)
    with output_path.open("w") as f:
        json.dump(export_data, f, indent=2)

    console.print(f"[green]✓ Exported {len(chunks)} documents to {args.output}[/green]")


if __name__ == "__main__":
    main()
