"""MCP chat tool implementation."""

import logging

logger = logging.getLogger(__name__)


async def handle_chat(arguments: dict) -> str:
    """Handle chat tool call.

    Args:
        arguments: Tool arguments with query, session_id, top_k, temperature.

    Returns:
        Chat response with optional sources.
    """
    from secondbrain_common.config import get_config
    from secondbrain_common.conversation import ConversationSession, ConversationStorage
    from secondbrain_common.rag import RAGPipeline
    from secondbrain_common.rag.providers import OllamaLLMProvider
    from secondbrain_common.search import Searcher

    query = arguments.get("query")
    session_id = arguments.get("session_id", "default")
    top_k = arguments.get("top_k", 5)
    temperature = arguments.get("temperature", 0.7)
    show_sources = arguments.get("show_sources", False)

    try:
        config = get_config()

        # Load or create session
        with ConversationStorage() as storage:
            session = ConversationSession.load(session_id, storage)
            if session is None:
                session = ConversationSession.create(session_id, storage)

        searcher = Searcher(verbose=False)
        llm_model = config.llm_model
        llm_provider = OllamaLLMProvider(
            host=config.ollama_host,
            model=llm_model,
            temperature=temperature,
        )

        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=llm_provider,
            top_k=top_k,
            context_window=config.rag_context_window,
        )

        result = pipeline.chat(
            query,
            session,
            top_k=top_k,
            show_sources=show_sources,
        )

        output = f"Answer: {result['answer']}\n"

        if show_sources and result.get("sources"):
            output += "\nSources:\n"
            for i, chunk in enumerate(result["sources"], 1):
                source_file = chunk.get("source_file", chunk.get("source", "unknown"))
                page = chunk.get("page", chunk.get("page_number", "unknown"))
                chunk_text = chunk.get("chunk_text", chunk.get("text", ""))
                if len(chunk_text) > 200:
                    chunk_text = chunk_text[:200] + "..."
                output += f"  [{i}] {source_file} (page {page}): {chunk_text}\n"

        return output
    except Exception as e:
        logger.exception(f"Chat failed: {e}")
        return f"Error: {e!s}"
