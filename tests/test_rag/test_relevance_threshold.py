"""Relevance-threshold gating tests for RAGPipeline.

Verifies the ``_has_relevant_chunks`` helper and that retrieval paths route
"retrieved-but-irrelevant" results (chunks whose ``score`` is below
``rag_min_similarity_threshold``) through the ``_handle_no_results`` /
``_handle_no_results_async`` LLM-knowledge fallback, the same as the zero-chunk
case. Also locks in backward compatibility: score-less chunks are treated as
relevant so existing RAG/chat flows are unchanged.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from secondbrain.conversation import ConversationSession
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.pipeline import RAGPipeline

NOTICE_PREFIX = "I couldn't find relevant documents for your query:"


@pytest.fixture
def mock_searcher() -> MagicMock:
    """Create a mock Searcher instance."""
    return MagicMock()


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create a mock LocalLLMProvider instance."""
    mock = MagicMock(spec=LocalLLMProvider)
    mock.generate.return_value = "Generated answer"
    mock.agenerate = AsyncMock(return_value="Generated answer")
    return mock


@pytest.fixture
def pipeline(
    mock_searcher: MagicMock,
    mock_llm_provider: MagicMock,
) -> RAGPipeline:
    """Create a RAGPipeline with mocked dependencies and default config."""
    return RAGPipeline(
        searcher=mock_searcher,
        llm_provider=mock_llm_provider,
        top_k=5,
    )


class TestHasRelevantChunks:
    """Unit tests for the ``_has_relevant_chunks`` relevance gate."""

    def test_all_above_threshold(self, pipeline: RAGPipeline) -> None:
        chunks = [
            {"chunk_text": "a", "score": 0.51},
            {"chunk_text": "b", "score": 0.7},
        ]
        assert pipeline._has_relevant_chunks(chunks) is True

    def test_all_below_threshold(self, pipeline: RAGPipeline) -> None:
        chunks = [
            {"chunk_text": "a", "score": 0.3},
            {"chunk_text": "b", "score": 0.37},
        ]
        assert pipeline._has_relevant_chunks(chunks) is False

    def test_no_score_field_returns_true(self, pipeline: RAGPipeline) -> None:
        # Score-less chunks are treated as relevant (backward compatibility).
        chunks = [{"chunk_text": "test context", "source_file": "test.pdf", "page": 1}]
        assert pipeline._has_relevant_chunks(chunks) is True

    def test_empty_list_returns_false(self, pipeline: RAGPipeline) -> None:
        assert pipeline._has_relevant_chunks([]) is False

    def test_mixed_scores_returns_true(self, pipeline: RAGPipeline) -> None:
        chunks = [
            {"chunk_text": "a", "score": 0.3},
            {"chunk_text": "b", "score": 0.55},
        ]
        assert pipeline._has_relevant_chunks(chunks) is True

    def test_scoreless_among_below_threshold_scored_is_not_relevant(
        self, pipeline: RAGPipeline
    ) -> None:
        """Score-less chunk must not bypass the gate on a below-threshold batch.

        Regression test: previously any single score-less chunk disabled the
        gate entirely, treating the whole batch as relevant.
        """
        chunks = [
            {"chunk_text": "a", "score": 0.3},
            {"chunk_text": "b", "source_file": "test.pdf", "page": 1},
        ]
        assert pipeline._has_relevant_chunks(chunks) is False

    def test_scoreless_among_above_threshold_scored_is_relevant(
        self, pipeline: RAGPipeline
    ) -> None:
        """Score-less chunk alongside an above-threshold scored chunk is relevant.

        The high score carries the batch regardless of the score-less chunk.
        """
        chunks = [
            {"chunk_text": "a", "score": 0.6},
            {"chunk_text": "b", "source_file": "test.pdf", "page": 1},
        ]
        assert pipeline._has_relevant_chunks(chunks) is True


class TestRelevanceGateInQuery:
    """The query() path routes below-threshold chunks through the fallback."""

    def test_query_below_threshold_uses_fallback(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All chunks below threshold -> static notice, LLM not asked for context."""
        from secondbrain.config import get_config

        monkeypatch.setenv("SECONDBRAIN_RAG_LLM_FALLBACK_ENABLED", "false")
        get_config.cache_clear()
        try:
            mock_searcher.search.return_value = [
                {
                    "chunk_text": "irrelevant",
                    "source_file": "ai.pdf",
                    "page": 1,
                    "score": 0.3,
                },
                {
                    "chunk_text": "more",
                    "source_file": "ai.pdf",
                    "page": 2,
                    "score": 0.37,
                },
            ]
            pipeline = RAGPipeline(
                searcher=mock_searcher,
                llm_provider=mock_llm_provider,
                top_k=5,
            )

            result = pipeline.query("what is the speed of light")

            assert result["answer"] == f"{NOTICE_PREFIX} what is the speed of light"
            mock_llm_provider.generate.assert_not_called()
        finally:
            get_config.cache_clear()

    def test_query_above_threshold_generates_normal_answer(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """At least one chunk above threshold -> normal RAG generation path."""
        mock_searcher.search.return_value = [
            {"chunk_text": "low", "source_file": "ai.pdf", "page": 1, "score": 0.3},
            {
                "chunk_text": "relevant",
                "source_file": "proxmox.pdf",
                "page": 1,
                "score": 0.6,
            },
        ]
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.query("proxmox configuration")

        assert result["answer"] == "Generated answer"
        mock_llm_provider.generate.assert_called_once()


class TestRelevanceGateAsync:
    """The query_async() path routes below-threshold chunks through the fallback."""

    @pytest.mark.asyncio
    async def test_query_async_below_threshold_uses_fallback(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All chunks below threshold -> notice even for the async path."""
        from secondbrain.config import get_config

        monkeypatch.setenv("SECONDBRAIN_RAG_LLM_FALLBACK_ENABLED", "false")
        get_config.cache_clear()
        try:
            mock_searcher.search_async = AsyncMock(
                return_value=[
                    {
                        "chunk_text": "irrelevant",
                        "source_file": "ai.pdf",
                        "page": 1,
                        "score": 0.3,
                    },
                ]
            )
            pipeline = RAGPipeline(
                searcher=mock_searcher,
                llm_provider=mock_llm_provider,
                top_k=5,
            )

            result = await pipeline.query_async("what is the speed of light")

            assert result["answer"] == f"{NOTICE_PREFIX} what is the speed of light"
            mock_llm_provider.agenerate.assert_not_awaited()
        finally:
            get_config.cache_clear()


class TestRelevanceGateGeneric:
    """The _generic_one_shot() fallback routes below-threshold chunks through _handle_no_results."""

    def test_generic_one_shot_below_threshold_uses_fallback(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Below-threshold chunks -> _handle_no_results notice in the answer."""
        mock_searcher.search.return_value = [
            {
                "chunk_text": "irrelevant",
                "source_file": "x.pdf",
                "page": 1,
                "score": 0.3,
            },
        ]
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline._generic_one_shot("q", 5, False)

        assert NOTICE_PREFIX in result["answer"]


class TestKnowledgeFallbackPrompt:
    """Tests for the stateless/context-aware LLM knowledge fallback prompt."""

    def test_build_knowledge_fallback_prompt_with_history(
        self,
        pipeline: RAGPipeline,
    ) -> None:
        """History is threaded into the prompt as a conversation context section."""
        history = [
            {"role": "user", "content": "is brian autistic?"},
            {
                "role": "assistant",
                "content": "Yes. According to the ADOS-2 report, Brian Hand...",
            },
        ]

        prompt = pipeline._build_knowledge_fallback_prompt(
            "what challenges will brian face as a vice president?",
            conversation_history=history,
        )

        assert "what challenges will brian face as a vice president?" in prompt
        assert "Brian" in prompt
        assert "ADOS-2" in prompt
        assert "is brian autistic?" in prompt
        assert "Relevant conversation context" in prompt
        assert "conversation context above" in prompt
        assert "information on it" in prompt

    def test_build_knowledge_fallback_prompt_without_history_is_stateless(
        self,
        pipeline: RAGPipeline,
    ) -> None:
        """Omitting history yields the original stateless prompt (no context section)."""
        prompt = pipeline._build_knowledge_fallback_prompt("some query")

        assert "some query" in prompt
        assert "Relevant conversation context" not in prompt
        assert "User: " not in prompt

    def test_build_knowledge_fallback_prompt_empty_history_is_stateless(
        self,
        pipeline: RAGPipeline,
    ) -> None:
        """An empty history list yields the original stateless prompt."""
        prompt = pipeline._build_knowledge_fallback_prompt("some query", [])

        assert "some query" in prompt
        assert "Relevant conversation context" not in prompt


class TestChatFallbackThreadsHistory:
    """chat() threads conversation history into the no-results LLM fallback."""

    def test_chat_no_results_fallback_prompt_includes_history(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """A below-threshold follow-up passes prior turns into the fallback prompt."""
        from secondbrain.conversation import QueryRewriter

        # Prior turns identify who "Brian" is (ADOS-2 autism evaluation).
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        session.add_message("user", "is brian autistic?")
        session.add_message(
            "assistant", "Yes. According to the ADOS-2 report, Brian Hand..."
        )

        mock_searcher.search.return_value = [
            {
                "chunk_text": "irrelevant",
                "source_file": "x.pdf",
                "page": 1,
                "score": 0.3,
            },
        ]
        rewriter = MagicMock(spec=QueryRewriter)
        rewriter.rewrite_query.return_value = (
            "what challenges will brian face as a vice president?"
        )
        rewriter.should_rewrite.return_value = True
        rewriter.context_window = 10

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            rewriter=rewriter,
            top_k=5,
        )

        result = pipeline.chat(
            "what challenges will brian face as a vice president?", session
        )

        assert NOTICE_PREFIX in result["answer"]
        # Fallback prompt passed to the LLM must contain the prior turns.
        call = mock_llm_provider.generate.call_args
        assert call is not None
        prompt = call.kwargs["prompt"]
        assert "is brian autistic?" in prompt
        assert "ADOS-2" in prompt
        assert "Brian Hand" in prompt
        assert "Relevant conversation context" in prompt
        # And it should reference the rewritten query.
        assert "vice president" in prompt


class TestBuildContextualSearchQuery:
    """Unit tests for the deterministic context-augmented query builder."""

    def _history(self) -> list[dict]:
        return [
            {"role": "user", "content": "is brian autistic?"},
            {
                "role": "assistant",
                "content": (
                    "Yes. According to the ADOS-2 report, Brian Hand scored under "
                    "the Autism Spectrum Disorder classification."
                ),
            },
        ]

    def test_empty_history_returns_query_unchanged(self, pipeline: RAGPipeline) -> None:
        assert pipeline._build_contextual_search_query("some query", []) == "some query"

    def test_none_history_returns_query_unchanged(self, pipeline: RAGPipeline) -> None:
        assert (
            pipeline._build_contextual_search_query("some query", None) == "some query"
        )

    def test_history_augments_query_with_terms(self, pipeline: RAGPipeline) -> None:
        result = pipeline._build_contextual_search_query(
            "what challenges will brian face", self._history()
        )
        assert result.startswith("what challenges will brian face")
        assert "Brian Hand" in result
        assert "ADOS-2" in result

    def test_extract_contextual_terms_dedupes(self, pipeline: RAGPipeline) -> None:
        terms = pipeline._extract_contextual_terms(self._history())
        assert "ADOS-2" in terms
        assert "Brian Hand" in terms
        assert len(terms) == len(set(terms))

    def test_extract_contextual_terms_empty(self, pipeline: RAGPipeline) -> None:
        assert pipeline._extract_contextual_terms([]) == []
        assert pipeline._extract_contextual_terms(None) == []


class TestGroundedContextRetry:
    """Unit tests for the grounded re-retrieval helper."""

    def _history(self) -> list[dict]:
        return [
            {"role": "user", "content": "is brian autistic?"},
            {
                "role": "assistant",
                "content": "Yes, per the ADOS-2 report Brian Hand...",
            },
        ]

    def test_returns_grounded_dict_when_relevant_chunk_found(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        pipeline: RAGPipeline,
    ) -> None:
        mock_llm_provider.generate.return_value = "Grounded answer from source"
        mock_searcher.search.return_value = [
            {
                "chunk_text": "ADOS-2 autism evaluation of Brian Hand...",
                "source_file": "BH ADOS Report (1).pdf",
                "page": 1,
                "score": 0.62,
            },
        ]
        result = pipeline._grounded_context_retry(
            "what challenges will brian face as a vice president?",
            self._history(),
            top_k=5,
            show_sources=True,
        )
        assert result is not None
        assert result["answer"] == "Grounded answer from source"
        assert result["grounded_retry"] is True
        assert NOTICE_PREFIX not in result["answer"]
        assert result["sources"][0]["score"] == 0.62
        # Query building is local (no LLM); the only LLM call is the answer.
        assert mock_llm_provider.generate.call_count == 1

    def test_returns_none_when_only_below_threshold_chunks(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        pipeline: RAGPipeline,
    ) -> None:
        mock_llm_provider.generate.return_value = "Brian Hand ADOS-2 autism report"
        mock_searcher.search.return_value = [
            {
                "chunk_text": "irrelevant",
                "source_file": "x.pdf",
                "page": 1,
                "score": 0.3,
            },
        ]
        result = pipeline._grounded_context_retry(
            "what challenges will brian face as a vice president?",
            self._history(),
            top_k=5,
            show_sources=False,
        )
        assert result is None

    def test_returns_none_when_search_raises(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        pipeline: RAGPipeline,
    ) -> None:
        mock_llm_provider.generate.return_value = "Brian Hand ADOS-2 autism report"
        mock_searcher.search.side_effect = RuntimeError("mongo down")
        result = pipeline._grounded_context_retry(
            "what challenges will brian face as a vice president?",
            self._history(),
            top_k=5,
            show_sources=False,
        )
        assert result is None


class TestChatGroundedRetry:
    """chat() re-retrieves a disambiguated query and grounds the answer."""

    def _session(self) -> ConversationSession:
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        session.add_message("user", "is brian autistic?")
        session.add_message(
            "assistant", "Yes. According to the ADOS-2 report, Brian Hand..."
        )
        return session

    def test_chat_grounds_followup_via_contextual_requery(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Below-threshold first search, then contextual re-query finds the report."""

        def smart_generate(*, prompt: str, **_: object) -> str:
            if "You are disambiguating" in prompt:
                return "Brian Hand ADOS-2 autism report"
            return "Grounded answer"

        mock_llm_provider.generate.side_effect = smart_generate
        mock_searcher.search.side_effect = [
            # First retrieval (original rewritten query): only irrelevant chunks.
            [
                {
                    "chunk_text": "irrelevant",
                    "source_file": "x.pdf",
                    "page": 1,
                    "score": 0.3,
                }
            ],
            # Contextual re-retrieval: the actual ADOS report.
            [
                {
                    "chunk_text": "ADOS-2 autism evaluation of Brian Hand...",
                    "source_file": "BH ADOS Report (1).pdf",
                    "page": 1,
                    "score": 0.62,
                }
            ],
        ]
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.chat(
            "what challenges will brian face as a vice president?", self._session()
        )

        assert result["answer"] == "Grounded answer"
        assert NOTICE_PREFIX not in result["answer"]
        assert result["grounded_retry"] is True
        # The search must have been called twice: original + contextual re-query.
        assert mock_searcher.search.call_count == 2

    def test_chat_falls_back_to_notice_when_requery_finds_nothing(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Contextual re-query finds nothing relevant -> knowledge-fallback notice."""
        from secondbrain.config import get_config

        monkeypatch.setenv("SECONDBRAIN_RAG_LLM_FALLBACK_ENABLED", "false")
        get_config.cache_clear()
        try:
            mock_searcher.search.return_value = [
                {
                    "chunk_text": "irrelevant",
                    "source_file": "x.pdf",
                    "page": 1,
                    "score": 0.3,
                },
            ]
            pipeline = RAGPipeline(
                searcher=mock_searcher,
                llm_provider=mock_llm_provider,
                top_k=5,
            )
            result = pipeline.chat(
                "what challenges will brian face as a vice president?", self._session()
            )
            assert result["answer"].startswith(NOTICE_PREFIX)
        finally:
            get_config.cache_clear()

    @pytest.mark.asyncio
    async def test_chat_async_grounds_followup_via_contextual_requery(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """chat_async grounds a follow-up via contextual re-query."""

        def smart_agenerate(*, prompt: str, **_: object) -> str:
            if "You are disambiguating" in prompt:
                return "Brian Hand ADOS-2 autism report"
            return "Grounded async answer"

        mock_llm_provider.agenerate = AsyncMock(side_effect=smart_agenerate)
        mock_searcher.search_async = AsyncMock(
            side_effect=[
                [
                    {
                        "chunk_text": "irrelevant",
                        "source_file": "x.pdf",
                        "page": 1,
                        "score": 0.3,
                    }
                ],
                [
                    {
                        "chunk_text": "ADOS-2 autism evaluation of Brian Hand...",
                        "source_file": "BH ADOS Report (1).pdf",
                        "page": 1,
                        "score": 0.62,
                    }
                ],
            ]
        )
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = await pipeline.chat_async(
            "what challenges will brian face as a vice president?", self._session()
        )

        assert result["answer"] == "Grounded async answer"
        assert NOTICE_PREFIX not in result["answer"]
        assert result["grounded_retry"] is True
        assert mock_searcher.search_async.await_count == 2


class TestGroundedRetryRequiresFollowUp:
    """Fresh self-contained questions must skip the context-augmented re-query so.

    they are not polluted by unrelated conversation topics.
    """

    def _session(self) -> ConversationSession:
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        session.add_message("user", "is brian autistic?")
        session.add_message(
            "assistant", "Yes. According to the ADOS-2 report, Brian Hand..."
        )
        return session

    def test_fresh_question_does_not_reference_context(
        self, pipeline: RAGPipeline
    ) -> None:
        assert not pipeline._query_references_context(
            "what is the speed of light",
            ["ADOS-2", "Brian Hand", "Autism Spectrum"],
        )

    def test_followup_references_context(self, pipeline: RAGPipeline) -> None:
        assert pipeline._query_references_context(
            "what challenges will brian face as a vice president?",
            ["ADOS-2", "Brian Hand", "Autism Spectrum"],
        )

    def test_fresh_question_skips_grounded_retry_before_search(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        pipeline: RAGPipeline,
    ) -> None:
        mock_searcher.search.return_value = [
            {
                "chunk_text": "ADOS-2 Brian Hand report",
                "source_file": "BH ADOS Report (1).pdf",
                "page": 1,
                "score": 0.62,
            },
        ]
        result = pipeline._grounded_context_retry(
            "what is the speed of light",
            self._session().get_history(),
            top_k=5,
            show_sources=False,
        )
        assert result is None
        mock_searcher.search.assert_not_called()

    def test_fresh_question_in_noisy_history_not_grounded(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """A self-contained question amid unrelated history is not grounded via.

        the topic-polluted re-query; it uses the knowledge-fallback notice.
        """
        mock_searcher.search.return_value = [
            {
                "chunk_text": "irrelevant",
                "source_file": "x.pdf",
                "page": 1,
                "score": 0.3,
            },
        ]
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        result = pipeline.chat("what is the speed of light", self._session())
        assert result.get("grounded_retry") is None
        assert result["answer"].startswith(NOTICE_PREFIX)
        # Only the initial (irrelevant) retrieval happened; the follow-up gate
        # short-circuited the context-augmented re-query before a second search.
        assert mock_searcher.search.call_count == 1
