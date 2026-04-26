"""Mock Searcher for testing without MongoDB."""

from typing import Any



class MockSearcher:
    """Mock searcher that returns predefined test chunks without MongoDB.

    This allows quantitative tests to run without requiring MongoDB to be running.
    The mock searcher returns hardcoded test chunks that match common test queries.
    """

    def __init__(self, verbose: bool = False) -> None:
        """Initialize mock searcher.

        Args:
            verbose: Enable verbose logging (ignored in mock mode).
        """
        self.verbose = verbose
        # Predefined test chunks that match common test queries
        self._test_chunks = [
            {
                "chunk_id": "chunk-001",
                "source_file": "tests/config.md",
                "page_number": 1,
                "chunk_text": "The default chunk size in SecondBrain is 4096 tokens. This is the standard configuration for document processing. You can configure the chunk size using the SECONDBRAIN_CHUNK_SIZE environment variable.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.95,
            },
            {
                "chunk_id": "chunk-010",
                "source_file": "tests/config.md",
                "page_number": 2,
                "chunk_text": "MongoDB connection URI is configured via the SECONDBRAIN_MONGO_URI environment variable. The default for local development is mongodb://localhost:27017.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.92,
            },
            {
                "chunk_id": "chunk-060",
                "source_file": "tests/embedding.md",
                "page_number": 1,
                "chunk_text": "Default model is all-MiniLM-L6-v2 from sentence-transformers library. This model provides a good balance of speed and accuracy for most use cases.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.90,
            },
            {
                "chunk_id": "chunk-020",
                "source_file": "tests/features.md",
                "page_number": 1,
                "chunk_text": "SecondBrain supports PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio files. The Ingestor class uses Docling for multi-format document parsing.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.88,
            },
            {
                "chunk_id": "chunk-030",
                "source_file": "tests/config.md",
                "page_number": 3,
                "chunk_text": "Enable circuit breaker by setting SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true. It provides automatic failure handling with recovery mechanisms.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.85,
            },
            {
                "chunk_id": "chunk-070",
                "source_file": "tests/config.md",
                "page_number": 3,
                "chunk_text": "Use SECONDBRAIN_CHUNK_SIZE and SECONDBRAIN_CHUNK_OVERLAP environment variables to configure chunk size and overlap. Default chunk size is 4096 tokens with 256 token overlap.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.82,
            },
            {
                "chunk_id": "chunk-080",
                "source_file": "tests/features.md",
                "page_number": 2,
                "chunk_text": "Semantic search works by converting queries and documents into embedding vectors using sentence-transformers, then performing vector similarity search in MongoDB using cosine similarity to find the most relevant results.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.95,
            },
            {
                "chunk_id": "chunk-090",
                "source_file": "tests/config.md",
                "page_number": 4,
                "chunk_text": "Logging is controlled by two environment variables: SECONDBRAIN_LOG_LEVEL for verbosity (DEBUG, INFO, WARNING, ERROR) and SECONDBRAIN_LOG_FORMAT for output format (pretty, json).",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.90,
            },
            {
                "chunk_id": "chunk-091",
                "source_file": "tests/config.md",
                "page_number": 4,
                "chunk_text": "Enable circuit breaker protection by setting the SECONDBRAIN_CIRCUIT_BREAKER_ENABLED environment variable to true. The circuit breaker automatically monitors service health and handles failures.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.88,
            },
            {
                "chunk_id": "chunk-092",
                "source_file": "tests/config.md",
                "page_number": 5,
                "chunk_text": "The default top-k value is 5, meaning the search returns the 5 most relevant results by default. This can be configured using the top_k parameter in search queries.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.87,
            },
            {
                "chunk_id": "chunk-093",
                "source_file": "tests/features.md",
                "page_number": 3,
                "chunk_text": "The circuit breaker automatically monitors service health and handles failures. When errors exceed a threshold, it opens the circuit and returns fallback responses until the service recovers.",
                "file_type": "markdown",
                "metadata": {},
                "similarity": 0.86,
            },
        ]

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search for relevant chunks based on query.

        Args:
            query: Search query string.
            top_k: Maximum number of results to return.

        Returns:
            List of chunk dicts with similarity scores.
        """
        query_lower = query.lower()
        
        scored_chunks = []
        for chunk in self._test_chunks:
            chunk_text = chunk.get("chunk_text", "").lower()
            score = chunk.get("similarity", 0.5)
            
            words = [w for w in query_lower.split() if len(w) > 3]
            matches = sum(1 for w in words if w in chunk_text)
            
            boost = min(matches * 0.1, 0.3)
            scored_chunks.append((score + boost, chunk))
        
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        results = [chunk for _, chunk in scored_chunks[:top_k]]

        for result in results:
            if "similarity" not in result:
                result["similarity"] = 0.8

        return results

    def close(self) -> None:
        """Close resources (no-op for mock)."""
        pass

    def __enter__(self) -> "MockSearcher":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
