"""RAG pipeline settings fragment."""

from pydantic import Field, field_validator


class RagMixin:
    """RAG pipeline configuration."""

    rag_context_window: int = Field(
        default=5,
        description="Number of recent messages to keep in context (default: 5 per spec)",
    )

    @field_validator("rag_context_window")
    @classmethod
    def validate_rag_context_window(cls, v: int) -> int:
        """Validate RAG context window is positive."""
        if v <= 0:
            raise ValueError("rag_context_window must be positive")
        return v

    rag_max_retries: int = Field(
        default=3,
        ge=1,
        description="Maximum retry attempts for LLM generation in RAG chat (default: 3)",
    )
    rag_llm_fallback_enabled: bool = Field(
        default=True,
        description=(
            "When no documents are found in the vector DB, allow the LLM to answer "
            "from its own knowledge if it has any (default: true)"
        ),
    )
    rag_min_similarity_threshold: float = Field(
        default=0.46,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum cosine-similarity score for a retrieved chunk to count as "
            "relevant context in the RAG/chat path; chunks below trigger the "
            "LLM-knowledge fallback (default: 0.46, same as the search CLI)"
        ),
    )
    rag_max_context_chars: int = Field(
        default=16000,
        ge=1000,
        le=500000,
        description="Maximum total context length in characters for RAG prompt construction",
    )

    @field_validator("rag_max_context_chars")
    @classmethod
    def validate_rag_max_context_chars(cls, v: int) -> int:
        """Validate rag_max_context_chars is between 1000 and 500000."""
        if v < 1000 or v > 500000:
            raise ValueError("rag_max_context_chars must be between 1000 and 500000")
        return v

    rag_chunk_preview_chars: int = Field(
        default=1200,
        ge=100,
        le=10000,
        description="Maximum character length of each individual chunk's text in the RAG context",
    )

    @field_validator("rag_chunk_preview_chars")
    @classmethod
    def validate_rag_chunk_preview_chars(cls, v: int) -> int:
        """Validate rag_chunk_preview_chars is between 100 and 10000."""
        if v < 100 or v > 10000:
            raise ValueError("rag_chunk_preview_chars must be between 100 and 10000")
        return v

    rag_system_prompt: str = Field(
        default=(
            "You are a helpful assistant. You MUST answer based ONLY on the provided context below.\n"
            "\n"
            "IMPORTANT RULES:\n"
            "1. The context contains information from documents. Read it carefully.\n"
            "2. Extract and synthesize the answer from the context - do NOT say you 'cannot find' information that IS in the context.\n"
            "3. If you see the answer in the context, state it clearly and confidently.\n"
            "4. Only say 'I cannot find the answer' if you have thoroughly searched the entire context and the information is genuinely absent.\n"
            "5. Do not hallucinate or make up information - stick to what's in the context.\n"
            "6. When the question asks for a list (formats, features, components, options, etc.), extract ALL items from the context - don't miss any.\n"
            "7. Read ALL chunks in the context - important information might be in any of them.\n"
            "8. For questions about system architecture or components, list the SPECIFIC component names mentioned in the context (e.g., 'CLI Interface', 'Ingestor', 'Embedding Engine', not just 'Components').\n"
            "9. When the question asks for a SPECIFIC VALUE (like a model name, version number, configuration value, etc.), you MUST include the exact value from the context in your answer.\n"
            "10. NEVER generalize or omit specific values - if the context says 'all-MiniLM-L6-v2', your answer must include 'all-MiniLM-L6-v2'.\n"
            "11. Format your answer concisely and directly, matching the style of the question.\n"
            "12. When the question asks to summarize or list chapters, sections, or parts\n"
            "    (e.g. 'summarize by chapter', 'list all sections'), you MUST enumerate\n"
            "    EVERY distinct chapter/section number and title present in the context —\n"
            "    do not stop early, combine related items, or omit chapters because the\n"
            "    answer feels 'long enough'. If the context contains 21 chapters, your\n"
            "    answer must name all 21.\n"
            "    IMPORTANT: Your answer will be judged a FAILURE if it omits any chapter\n"
            "    numbers or substitutes summaries for chapter names. Enumerate all 21.\n"
            "13. MULTI-DOCUMENT HANDLING: The context may contain content from more than\n"
            "    one document. When answering, clearly indicate which document each piece\n"
            "    of information comes from (e.g., 'According to the VirtualBox manual...')\n"
            "    or 'The Proxmox VE guide states...'). Do NOT mix information from\n"
            "    different documents without attribution. If the user asked about a\n"
            "    specific document, prioritize information from that document and note\n"
            "    if other documents also contain relevant information.\n"
            "\n"
            "When the answer is in the context:\n"
            "- State the answer directly in 1-2 sentences\n"
            "- For lists: include ALL items mentioned in the context with their full names\n"
            "- For specific values: include the EXACT value from the context\n"
            "- Be concise - avoid unnecessary elaboration\n"
            "- Cite the source if helpful (e.g., 'According to the document...')\n"
            "\n"
            "The context from documents follows:\n"
        ),
        description="System prompt for RAG chat (supports environment variable SECONDBRAIN_RAG_SYSTEM_PROMPT)",
    )
