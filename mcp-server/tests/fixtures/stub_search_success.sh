#!/bin/sh
# Stub CLI: successful search. Emits the canned CLI JSON payload for
# `search --format json` (mixed scores, the CLI's full field set plus one
# unknown field, to prove field preservation). A query mentioning __empty__
# yields an empty array instead. Used by the search tool tests (no Python or
# Qdrant required).
case "$*" in
    *"__empty__"*)
        echo "[]"
        ;;
    *)
        cat <<'EOF'
[
  {
    "chunk_id": "chunk-001",
    "source_file": "docs/config.md",
    "page_number": 1,
    "printed_page": "1",
    "page_pos": 0,
    "chunk_text": "The Qdrant vector store connection URL is configured via the SECONDBRAIN_QDRANT_URL environment variable.",
    "element_type": "paragraph",
    "chunk_role": "body",
    "section_label": "Configuration",
    "score": 0.95,
    "future_field": {"nested": [1, 2]}
  },
  {
    "chunk_id": "chunk-002",
    "source_file": "docs/architecture.md",
    "page_number": 2,
    "printed_page": "2",
    "page_pos": 1,
    "chunk_text": "The main components include the Ingestor, CLI Interface, Embedding Engine, Search Engine, and Storage Layer.",
    "element_type": "paragraph",
    "chunk_role": "body",
    "section_label": "Architecture",
    "score": 0.5,
    "future_field": {"nested": [3]}
  },
  {
    "chunk_id": "chunk-003",
    "source_file": "docs/operations.md",
    "page_number": 3,
    "printed_page": "3",
    "page_pos": 0,
    "chunk_text": "Low-scoring chunk that the server-side threshold must filter out.",
    "element_type": "paragraph",
    "chunk_role": "body",
    "section_label": "Operations",
    "score": 0.3
  }
]
EOF
        ;;
esac
exit 0
