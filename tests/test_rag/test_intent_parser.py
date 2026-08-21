"""Tests for StructuralIntentParser intent classification.

Covers the refined BROAD_COVERAGE_TRIGGERS list: specific factual questions
("what is X", "explain X", "describe X", ...) must NOT classify as
BROAD_COVERAGE. They fall through to the UNKNOWN / semantic single-shot path,
which has the relevance gate and the LLM-knowledge fallback, instead of the
heavy structural chapter dump.
"""

from secondbrain.rag.intent_parser import QueryIntent, StructuralIntentParser


class TestIntentClassification:
    """StructuralIntentParser broad-coverage classification."""

    def parse(self, query: str):
        return StructuralIntentParser().parse(query)

    def test_specific_factual_questions_are_unknown(self) -> None:
        """Specific factual questions no longer classify as BROAD_COVERAGE.

        These route to the UNKNOWN / semantic single-shot path (which has the
        relevance gate + LLM-knowledge fallback), not the structural dump.
        """
        for q in [
            "what is the speed of light",
            "what is proxmox",
            "what are the main features",
            "explain the storage layer",
            "describe the routing logic",
            "how does replication work",
            "how do I configure it",
            "why is this happening",
            "why does it fail",
            "tell me about machine learning",
            "tell me more about this",
        ]:
            decision = self.parse(q)
            assert decision.intent is QueryIntent.UNKNOWN, f"{q!r} -> {decision.intent}"
            assert decision.suggested_pipeline == "semantic", (
                f"{q!r} -> {decision.suggested_pipeline}"
            )

    def test_specific_factual_query_unknown(self) -> None:
        """A bare specific factual question is UNKNOWN."""
        decision = self.parse("what is X")
        assert decision.intent is QueryIntent.UNKNOWN

    def test_summarize_book_is_broad_coverage(self) -> None:
        """A kept comprehensive trigger still classifies as BROAD_COVERAGE."""
        decision = self.parse("summarize the book")
        assert decision.intent is QueryIntent.BROAD_COVERAGE

    def test_comprehensive_phrases_still_broad_coverage(self) -> None:
        """Kept structural/comprehensive triggers are unaffected."""
        for q in [
            "summarize the book",
            "give me an overview of the guide",
            "everything about the platform",
            "comprehensive guide to storage",
            "tell me everything about proxmox",
            "summary of the main topics",
        ]:
            decision = self.parse(q)
            assert decision.intent is QueryIntent.BROAD_COVERAGE, (
                f"{q!r} -> {decision.intent}"
            )


class TestListSourcesIntent:
    """StructuralIntentParser source-enumeration classification."""

    def parse(self, query: str):
        return StructuralIntentParser().parse(query)

    def test_list_sources_phrases_classify(self) -> None:
        """Queries that ask to enumerate stored sources classify as LIST_SOURCES."""
        for q in [
            "list all unique sources that you have stored",
            "list all sources",
            "list sources",
            "what sources do you have",
            "list unique sources",
            "which documents are stored",
            "list all documents",
            "what documents do you have",
            "list your sources",
        ]:
            decision = self.parse(q)
            assert decision.intent is QueryIntent.LIST_SOURCES, (
                f"{q!r} -> {decision.intent}"
            )
            assert decision.suggested_pipeline == "structural", (
                f"{q!r} -> {decision.suggested_pipeline}"
            )

    def test_list_sources_does_not_collide_with_coverage(self) -> None:
        """Coverage/summary queries are not hijacked by LIST_SOURCES."""
        for q in [
            "summarize the book",
            "tell me everything about proxmox",
            "give me an overview of the guide",
        ]:
            decision = self.parse(q)
            assert decision.intent is not QueryIntent.LIST_SOURCES, (
                f"{q!r} -> {decision.intent}"
            )
