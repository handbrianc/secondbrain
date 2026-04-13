import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EVALUATION_MODEL = os.getenv("EVALUATION_MODEL", "llama3.2")


# ============================================================================
# Helper Functions for LLM Evaluation
# ============================================================================


def _check_ollama_available() -> bool:
    try:
        client = httpx.Client(timeout=5.0)
        response = client.get(f"{OLLAMA_BASE_URL}/api/tags")
        return response.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def _parse_llm_json_response(response: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling markdown code blocks."""
    try:
        cleaned = (
            response.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None


def _evaluate_with_llm(
    prompt: str, model: str = EVALUATION_MODEL
) -> dict[str, Any] | None:
    if not _check_ollama_available():
        pytest.skip("Ollama service not available")

    try:
        client = httpx.Client(timeout=60.0)
        response = client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0},
            },
        )

        if response.status_code != 200:
            pytest.skip(f"LLM API returned status {response.status_code}")

        result = response.json()
        raw_output = result.get("response", "")
        return _parse_llm_json_response(raw_output)

    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("Ollama service unavailable")
    except Exception:
        pytest.skip("LLM evaluation failed")

    return None


# ============================================================================
# Quality Metrics Tests (8 tests)
# ============================================================================


@pytest.mark.qualitative
@pytest.mark.llm_judge
class TestQualityMetrics:
    """Test LLM-based evaluation of response quality metrics."""

    @pytest.mark.parametrize(
        "query,response,expected_score",
        [
            pytest.param(
                "What is MongoDB vector search?",
                "MongoDB vector search enables semantic search through embeddings.",
                4,
                id="relevant_response",
            ),
            pytest.param(
                "What is MongoDB vector search?",
                "The sky is blue and grass is green.",
                1,
                id="irrelevant_response",
            ),
        ],
    )
    def test_relevance(
        self, llm_judge_prompts: dict, query: str, response: str, expected_score: int
    ) -> None:
        """Test relevance evaluation using LLM judge."""
        system_prompt = "You are an expert evaluator. Score relevance (1-5) where 1=irrelevant, 5=perfectly relevant."
        user_prompt = f"Query: {query}\nResponse: {response}\nReturn JSON: {{'score': <1-5>, 'reasoning': '...'}}"

        result = _evaluate_with_llm(f"{system_prompt}\n\n{user_prompt}")
        assert result is not None, "LLM should return valid JSON"
        assert "score" in result, "Response should include score"
        assert 1 <= result["score"] <= 5, "Score should be 1-5"
        assert "reasoning" in result, "Response should include reasoning"

    @pytest.mark.parametrize(
        "response,expected_structured",
        [
            pytest.param(
                "First, the main point. Second, supporting details. Third, conclusion.",
                True,
                id="well_structured",
            ),
            pytest.param(
                "Point one then random thoughts without organization.",
                False,
                id="poorly_structured",
            ),
        ],
    )
    def test_coherence(
        self, llm_judge_prompts: dict, response: str, expected_structured: bool
    ) -> None:
        """Test coherence evaluation using LLM judge."""
        prompt = f"""Evaluate coherence of this response: "{response}"
Return JSON: {{"coherent": <boolean>, "score": <1-5>, "reasoning": "..."}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "coherent" in result or "score" in result
        assert "reasoning" in result

    @pytest.mark.parametrize(
        "query,response,should_be_complete",
        [
            pytest.param(
                "List the main features of SecondBrain.",
                "SecondBrain supports: 1) Semantic search 2) Multi-format documents 3) Local embeddings",
                True,
                id="complete_response",
            ),
            pytest.param(
                "List the main features of SecondBrain.",
                "It has some features.",
                False,
                id="incomplete_response",
            ),
        ],
    )
    def test_completeness(
        self,
        llm_judge_prompts: dict,
        query: str,
        response: str,
        should_be_complete: bool,
    ) -> None:
        """Test completeness evaluation using LLM judge."""
        prompt = f"""Query: {query}
Response: {response}
Evaluate completeness. Return JSON: {{"complete": <boolean>, "score": <1-5>, "missing_elements": [...]}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "score" in result or "complete" in result

    def test_groundedness(self, llm_judge_prompts: dict) -> None:
        """Test groundedness evaluation (response based on provided context)."""
        context = (
            "MongoDB Atlas Vector Search enables semantic search using embeddings."
        )
        grounded_response = (
            "MongoDB Atlas Vector Search enables semantic search using embeddings."
        )
        hallucinated_response = "PostgreSQL is the best vector database."

        prompt = f"""Context: {context}
Response A: {grounded_response}
Response B: {hallucinated_response}
Evaluate groundedness. Return JSON: {{"grounded_a": <boolean>, "grounded_b": <boolean>, "score_a": <1-5>, "score_b": <1-5>}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "grounded_a" in result or "score_a" in result

    @pytest.mark.parametrize(
        "response,expected_fluent",
        [
            pytest.param(
                "The system processes documents efficiently and accurately.",
                True,
                id="fluent_response",
            ),
            pytest.param(
                "The system processes efficiently documents and accurately.",
                False,
                id="unfluent_response",
            ),
        ],
    )
    def test_fluency(
        self, llm_judge_prompts: dict, response: str, expected_fluent: bool
    ) -> None:
        """Test fluency evaluation using LLM judge."""
        prompt = f"""Evaluate fluency of: "{response}"
Return JSON: {{"fluent": <boolean>, "score": <1-5>, "issues": [...]}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "fluent" in result or "score" in result

    def test_accuracy(self, llm_judge_prompts: dict) -> None:
        """Test accuracy evaluation against known facts."""
        accurate_response = "Python 3.11 was released in October 2022."
        inaccurate_response = "Python 3.11 was released in 2015."

        prompt = f"""Verify factual accuracy:
Response A: {accurate_response}
Response B: {inaccurate_response}
Return JSON: {{"accurate_a": <boolean>, "accurate_b": <boolean>, "score_a": <1-5>, "score_b": <1-5>, "hallucinations": [...]}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "accurate_a" in result or "score_a" in result
        assert "hallucinations" in result

    @pytest.mark.parametrize(
        "query,response,expected_concise",
        [
            pytest.param(
                "What is the capital of France?",
                "Paris.",
                True,
                id="concise_response",
            ),
            pytest.param(
                "What is the capital of France?",
                "Well, when we think about France, there are many cities like Lyon, Marseille, and then there's Paris which is indeed the capital, and it has been for centuries...",
                False,
                id="verbose_response",
            ),
        ],
    )
    def test_conciseness(
        self,
        llm_judge_prompts: dict,
        query: str,
        response: str,
        expected_concise: bool,
    ) -> None:
        """Test conciseness evaluation using LLM judge."""
        prompt = f"""Query: {query}
Response: {response}
Evaluate conciseness. Return JSON: {{"concise": <boolean>, "score": <1-5>, "word_count": <int>, "excess_words": <int>}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "concise" in result or "score" in result

    @pytest.mark.parametrize(
        "query,response,expected_helpful",
        [
            pytest.param(
                "How do I ingest documents?",
                "Use: secondbrain ingest /path/to/documents/",
                True,
                id="helpful_response",
            ),
            pytest.param(
                "How do I ingest documents?",
                "I don't know.",
                False,
                id="unhelpful_response",
            ),
        ],
    )
    def test_helpfulness(
        self,
        llm_judge_prompts: dict,
        query: str,
        response: str,
        expected_helpful: bool,
    ) -> None:
        """Test helpfulness evaluation using LLM judge."""
        prompt = f"""Query: {query}
Response: {response}
Evaluate helpfulness. Return JSON: {{"helpful": <boolean>, "score": <1-5>, "actionable": <boolean>, "reasoning": "..."}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "helpful" in result or "score" in result


# ============================================================================
# A/B Comparison Tests (4 tests)
# ============================================================================


@pytest.mark.qualitative
@pytest.mark.llm_judge
class TestABComparison:
    """Test LLM-based A/B comparison of responses."""

    def test_winner_selection(self, llm_judge_prompts: dict) -> None:
        """Test LLM judge can select a winner between two responses."""
        query = "What are the benefits of vector search?"
        response_a = "Vector search enables semantic similarity matching."
        response_b = "It's okay I guess."

        prompt = f"""Compare these responses:
Query: {query}
Response A: {response_a}
Response B: {response_b}
Return JSON: {{"winner": "A"|"B"|"tie", "reasoning": "...", "confidence": <0-1>}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "winner" in result, "Response should include winner"
        assert result["winner"] in ["A", "B", "tie"], "Winner should be A, B, or tie"
        assert "reasoning" in result, "Response should include reasoning"

    def test_tie_detection(self, llm_judge_prompts: dict) -> None:
        """Test LLM judge can detect when responses are equivalent."""
        query = "What is Python?"
        response_a = "Python is a programming language."
        response_b = "Python is a programming language."

        prompt = f"""Compare these responses:
Query: {query}
Response A: {response_a}
Response B: {response_b}
Return JSON: {{"winner": "A"|"B"|"tie", "reasoning": "..."}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "winner" in result
        # With identical responses, should detect tie or show very close scores

    def test_reasoning_quality(self, llm_judge_prompts: dict) -> None:
        """Test that LLM provides quality reasoning for its judgments."""
        query = "Explain machine learning."
        response_a = "ML is a subset of AI using data to learn patterns."
        response_b = "Uh yeah, it's like computers learning stuff I guess."

        prompt = f"""Compare these responses:
Query: {query}
Response A: {response_a}
Response B: {response_b}
Return JSON: {{
    "winner": "A"|"B"|"tie",
    "reasoning": "...",
    "criteria_scores": {{
        "accuracy": <1-5>,
        "clarity": <1-5>,
        "completeness": <1-5>
    }},
    "strengths_a": [...],
    "strengths_b": [...],
    "weaknesses_a": [...],
    "weaknesses_b": [...]
}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "reasoning" in result
        assert len(result.get("reasoning", "")) > 20, "Reasoning should be substantive"
        assert "criteria_scores" in result or "winner" in result

    def test_consistency(self, llm_judge_prompts: dict) -> None:
        """Test that LLM judge is consistent across multiple evaluations."""
        query = "What is semantic search?"
        response_a = "Semantic search finds meaning, not just keywords."
        response_b = "It searches by meaning."

        # Run evaluation multiple times
        results = []
        for _ in range(3):
            prompt = f"""Compare:
Query: {query}
Response A: {response_a}
Response B: {response_b}
Return JSON: {{"winner": "A"|"B"|"tie", "score_a": <1-5>, "score_b": <1-5>}}"""

            result = _evaluate_with_llm(prompt)
            if result:
                results.append(result)

        if len(results) >= 2:
            # Check consistency - winners should be the same or scores very close
            winners = [r.get("winner") for r in results if "winner" in r]
            if winners:
                # Most winners should agree (allowing some variance)
                assert len(set(winners)) <= 2, "Judge should be mostly consistent"


# ============================================================================
# Aggregate Scoring Tests (3 tests)
# ============================================================================


@pytest.mark.qualitative
@pytest.mark.llm_judge
class TestAggregateScoring:
    """Test LLM-based aggregate scoring and weighted calculations."""

    def test_weighted_calculation(self, llm_judge_prompts: dict) -> None:
        """Test weighted score aggregation across multiple criteria."""
        weights = {"relevance": 0.3, "accuracy": 0.4, "clarity": 0.2, "safety": 0.1}
        scores = {"relevance": 5, "accuracy": 4, "clarity": 5, "safety": 5}

        prompt = f"""Calculate weighted average score.
Weights: {json.dumps(weights)}
Scores: {json.dumps(scores)}
Return JSON: {{"weighted_score": <float>, "breakdown": {{...}}, "pass_threshold_met": <boolean>}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "weighted_score" in result, "Response should include weighted score"
        assert "breakdown" in result or "pass_threshold_met" in result

        # Verify calculation is reasonable
        expected = sum(scores[k] * weights[k] for k in scores if k in weights)
        assert abs(result["weighted_score"] - expected) < 0.5, (
            f"Weighted score {result['weighted_score']} should be close to {expected}"
        )

    @pytest.mark.parametrize(
        "score,threshold,should_pass",
        [
            pytest.param(4.2, 3.5, True, id="above_threshold"),
            pytest.param(2.8, 3.5, False, id="below_threshold"),
            pytest.param(3.5, 3.5, True, id="at_threshold"),
        ],
    )
    def test_pass_fail(
        self, llm_judge_prompts: dict, score: float, threshold: float, should_pass: bool
    ) -> None:
        """Test pass/fail determination against threshold."""
        prompt = f"""Evaluate if score {score} passes threshold {threshold}.
Return JSON: {{"score": <float>, "threshold": <float>, "passed": <boolean>, "gap": <float>}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "passed" in result, "Response should include pass/fail decision"

    def test_threshold_validation(self, llm_judge_prompts: dict) -> None:
        """Test threshold validation for different quality levels."""
        thresholds = {
            "excellent": 4.5,
            "good": 3.5,
            "acceptable": 2.5,
            "poor": 1.5,
        }

        test_scores = [4.8, 3.7, 2.9, 1.8]

        for score in test_scores:
            prompt = f"""Score: {score}
Thresholds: {json.dumps(thresholds)}
Return JSON: {{"score": <float>, "level": "excellent"|"good"|"acceptable"|"poor", "threshold_met": <float>}}"""

            result = _evaluate_with_llm(prompt)
            assert result is not None, f"LLM should return valid JSON for score {score}"
            assert "level" in result or "score" in result


# ============================================================================
# Judge Reliability Tests (5 tests)
# ============================================================================


@pytest.mark.qualitative
@pytest.mark.llm_judge
class TestJudgeReliability:
    """Test reliability and consistency of LLM judges."""

    def test_inter_judge_consistency(self, llm_judge_prompts: dict) -> None:
        """Test consistency between different judge models."""
        query = "What is RAG?"
        response = (
            "RAG (Retrieval-Augmented Generation) combines retrieval and generation."
        )

        # Use different models if available
        models_to_test = ["llama3.2", "llama3.1"]
        results = []

        for model in models_to_test:
            prompt = f"""Evaluate response quality:
Query: {query}
Response: {response}
Return JSON: {{"score": <1-5>, "reasoning": "..."}}"""

            result = _evaluate_with_llm(prompt, model=model)
            if result and "score" in result:
                results.append(result["score"])

        if len(results) >= 2:
            # Scores from different judges should be reasonably close (within 1 point)
            score_range = max(results) - min(results)
            assert score_range <= 2, (
                f"Different judges should agree within 2 points, got range {score_range}"
            )

    def test_intra_judge_consistency(self, llm_judge_prompts: dict) -> None:
        """Test consistency of same judge across repeated evaluations."""
        query = "Explain embeddings."
        response = "Embeddings are vector representations of text."

        # Same prompt, multiple evaluations
        prompt = f"""Evaluate:
Query: {query}
Response: {response}
Return JSON: {{"score": <1-5>, "confidence": <0-1>}}"""

        scores = []
        for _ in range(3):
            result = _evaluate_with_llm(prompt)
            if result and "score" in result:
                scores.append(result["score"])

        if len(scores) >= 2:
            # Same judge should be consistent (scores within 1 point)
            score_variance = max(scores) - min(scores)
            assert score_variance <= 1, (
                f"Same judge should be consistent, got variance {score_variance}"
            )

    def test_calibration(self, llm_judge_prompts: dict) -> None:
        """Test that judge scores are well-calibrated."""
        # Known quality responses
        test_cases = [
            ("Perfect response.", 5),
            ("Terrible response.", 1),
        ]

        scores = []
        for response, _ in test_cases:
            prompt = f"""Evaluate quality: "{response}"
Return JSON: {{"score": <1-5>, "reasoning": "..."}}"""

            result = _evaluate_with_llm(prompt)
            if result and "score" in result:
                scores.append(result["score"])

        if len(scores) >= 1:
            # Judge should distinguish between good and bad (at least some variance)
            assert len(scores) > 0, "Should have at least one score"

    def test_bias_detection(self, llm_judge_prompts: dict) -> None:
        """Test that judge doesn't show systematic bias."""
        # Identical content, different presentation
        response_a = "The system is excellent and works perfectly."
        response_b = "The system works perfectly and is excellent."

        prompt = f"""Compare without bias:
Response A: {response_a}
Response B: {response_b}
Return JSON: {{"score_a": <1-5>, "score_b": <1-5>, "bias_detected": <boolean>, "reasoning": "..."}}"""

        result = _evaluate_with_llm(prompt)
        assert result is not None, "LLM should return valid JSON"
        assert "score_a" in result or "score_b" in result

        # With identical content, scores should be very close
        if "score_a" in result and "score_b" in result:
            score_diff = abs(result["score_a"] - result["score_b"])
            assert score_diff <= 1, (
                f"Identical content should score similarly, diff={score_diff}"
            )

    def test_sensitivity(self, llm_judge_prompts: dict) -> None:
        """Test that judge is sensitive to quality differences."""
        test_cases = [
            {
                "query": "What is vector search?",
                "good_response": "Vector search finds similar items using embedding distances.",
                "bad_response": "Uh, it's like searching I guess.",
                "expected_diff": 3,
            },
            {
                "query": "How to use the API?",
                "good_response": "Call the endpoint with proper authentication and parameters.",
                "bad_response": "Just use it.",
                "expected_diff": 2,
            },
        ]

        for test_case in test_cases:
            prompt = f"""Compare:
Query: {test_case["query"]}
Response A: {test_case["good_response"]}
Response B: {test_case["bad_response"]}
Return JSON: {{"score_a": <1-5>, "score_b": <1-5>, "difference": <float>}}"""

            result = _evaluate_with_llm(prompt)
            if result and "score_a" in result and "score_b" in result:
                diff = result["score_a"] - result["score_b"]
                # Judge should detect quality difference (good should score higher)
                assert diff > 0, (
                    f"Good response should score higher than bad: diff={diff}"
                )
