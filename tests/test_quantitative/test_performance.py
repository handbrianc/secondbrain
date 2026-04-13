import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pytest
from sentence_transformers import SentenceTransformer

from secondbrain.embedding import LocalEmbeddingGenerator
from secondbrain.rag import RAGPipeline
from secondbrain.rag.providers.ollama import OllamaLLMProvider
from secondbrain.search import Searcher

THRESHOLD_MEAN_RESPONSE_TIME = 5.0
THRESHOLD_P95_RESPONSE_TIME = 8.0
THRESHOLD_MEAN_EMBEDDING_TIME = 1.0
THRESHOLD_P95_EMBEDDING_TIME = 2.0
THRESHOLD_MEAN_SEARCH_TIME = 0.5
THRESHOLD_P95_SEARCH_TIME = 1.0
THRESHOLD_MEAN_LLM_TIME = 3.0
THRESHOLD_P95_LLM_TIME = 5.0
THRESHOLD_MIN_THROUGHPUT = 2.0
NUM_RUNS = 10
WARM_UP_RUNS = 2
NUM_CONCURRENT_QUERIES = 5


@pytest.fixture(scope="function")
def rag_pipeline() -> RAGPipeline:
    searcher = Searcher()
    llm_provider = OllamaLLMProvider()
    pipeline = RAGPipeline(searcher=searcher, llm_provider=llm_provider, top_k=3)
    yield pipeline
    searcher.close()
    llm_provider.close()


@pytest.fixture(scope="function")
def embedding_generator() -> LocalEmbeddingGenerator:
    gen = LocalEmbeddingGenerator()
    yield gen
    gen.close()


@pytest.fixture(scope="function")
def searcher() -> Searcher:
    searcher = Searcher()
    yield searcher
    searcher.close()


@pytest.fixture(scope="function")
def llm_provider() -> OllamaLLMProvider:
    provider = OllamaLLMProvider()
    yield provider
    provider.close()


@pytest.fixture(scope="session")
def embedding_model() -> SentenceTransformer:
    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture
def test_queries() -> list[str]:
    return [
        "What is the default chunk size in SecondBrain?",
        "How do I configure MongoDB connection URI?",
        "What document formats are supported?",
        "How to enable circuit breaker?",
        "What is the purpose of the Ingestor class?",
    ]


def calculate_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0

    sorted_values = sorted(values)
    index = (percentile / 100) * (len(sorted_values) - 1)
    lower = int(index)
    upper = lower + 1

    if upper >= len(sorted_values):
        return sorted_values[-1]

    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def run_warm_up(pipeline: RAGPipeline, queries: list[str], num_warm_up: int) -> None:
    for _ in range(num_warm_up):
        for query in queries[:3]:
            pipeline.query(query, top_k=2)


class TestPerformance:
    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_query_response_time(
        self,
        rag_pipeline: RAGPipeline,
        test_queries: list[str],
        benchmark: Any,
    ) -> None:
        run_warm_up(rag_pipeline, test_queries, WARM_UP_RUNS)

        def run_query() -> dict[str, Any]:
            query = test_queries[0]
            return rag_pipeline.query(query, top_k=3)

        benchmark(run_query)

        stats = benchmark.stats
        all_times = stats.get("data", [])
        p95_latency = calculate_percentile(all_times, 95) if all_times else 0.0
        mean_time = stats.get("mean", 0.0) if stats else 0.0

        failure_msg = (
            f"Performance thresholds exceeded:\n"
            f"  Mean response time: {mean_time:.3f}s (threshold: {THRESHOLD_MEAN_RESPONSE_TIME}s)\n"
            f"  P95 latency: {p95_latency:.3f}s (threshold: {THRESHOLD_P95_RESPONSE_TIME}s)\n"
            f"  Total samples: {len(all_times)}"
        )

        assert mean_time < THRESHOLD_MEAN_RESPONSE_TIME, failure_msg
        assert p95_latency < THRESHOLD_P95_RESPONSE_TIME, failure_msg

    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_embedding_generation_time(
        self,
        embedding_generator: LocalEmbeddingGenerator,
        test_queries: list[str],
        benchmark: Any,
    ) -> None:
        for _ in range(WARM_UP_RUNS):
            for query in test_queries[:3]:
                embedding_generator.generate(query)

        def run_embedding() -> list[float]:
            query = test_queries[0]
            return embedding_generator.generate(query)

        benchmark(run_embedding)

        stats = benchmark.stats
        all_times = stats.get("data", [])
        p95_latency = calculate_percentile(all_times, 95) if all_times else 0.0
        mean_time = stats.get("mean", 0.0) if stats else 0.0

        failure_msg = (
            f"Embedding generation performance thresholds exceeded:\n"
            f"  Mean time: {mean_time:.3f}s (threshold: {THRESHOLD_MEAN_EMBEDDING_TIME}s)\n"
            f"  P95 latency: {p95_latency:.3f}s (threshold: {THRESHOLD_P95_EMBEDDING_TIME}s)\n"
            f"  Total samples: {len(all_times)}"
        )

        assert mean_time < THRESHOLD_MEAN_EMBEDDING_TIME, failure_msg
        assert p95_latency < THRESHOLD_P95_EMBEDDING_TIME, failure_msg

    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_search_latency(
        self,
        searcher: Searcher,
        test_queries: list[str],
        benchmark: Any,
    ) -> None:
        for _ in range(WARM_UP_RUNS):
            for query in test_queries[:3]:
                searcher.search(query, top_k=2)

        def run_search() -> list[dict[str, Any]]:
            query = test_queries[0]
            return searcher.search(query, top_k=3)

        benchmark(run_search)

        stats = benchmark.stats
        all_times = stats.get("data", [])
        p95_latency = calculate_percentile(all_times, 95) if all_times else 0.0
        mean_time = stats.get("mean", 0.0) if stats else 0.0

        failure_msg = (
            f"Search latency thresholds exceeded:\n"
            f"  Mean time: {mean_time:.3f}s (threshold: {THRESHOLD_MEAN_SEARCH_TIME}s)\n"
            f"  P95 latency: {p95_latency:.3f}s (threshold: {THRESHOLD_P95_SEARCH_TIME}s)\n"
            f"  Total samples: {len(all_times)}"
        )

        assert mean_time < THRESHOLD_MEAN_SEARCH_TIME, failure_msg
        assert p95_latency < THRESHOLD_P95_SEARCH_TIME, failure_msg

    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_llm_generation_time(
        self,
        llm_provider: OllamaLLMProvider,
        benchmark: Any,
    ) -> None:
        test_context = """Source: test.pdf (page 1)
        SecondBrain is a local document intelligence CLI tool.
        The default chunk size is 4096 tokens."""

        test_prompt = f"""You are a helpful assistant. Answer based on the provided context.

Context:
{test_context}

Question: What is the default chunk size?

Answer:"""

        for _ in range(WARM_UP_RUNS):
            llm_provider.generate(test_prompt, temperature=0.7, max_tokens=100)

        def run_llm() -> str:
            return llm_provider.generate(test_prompt, temperature=0.7, max_tokens=100)

        benchmark(run_llm)

        stats = benchmark.stats
        all_times = stats.get("data", [])
        p95_latency = calculate_percentile(all_times, 95) if all_times else 0.0
        mean_time = stats.get("mean", 0.0) if stats else 0.0

        failure_msg = (
            f"LLM generation performance thresholds exceeded:\n"
            f"  Mean time: {mean_time:.3f}s (threshold: {THRESHOLD_MEAN_LLM_TIME}s)\n"
            f"  P95 latency: {p95_latency:.3f}s (threshold: {THRESHOLD_P95_LLM_TIME}s)\n"
            f"  Total samples: {len(all_times)}"
        )

        assert mean_time < THRESHOLD_MEAN_LLM_TIME, failure_msg
        assert p95_latency < THRESHOLD_P95_LLM_TIME, failure_msg

    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_throughput_queries_per_second(
        self,
        rag_pipeline: RAGPipeline,
        test_queries: list[str],
        benchmark: Any,
    ) -> None:
        run_warm_up(rag_pipeline, test_queries, WARM_UP_RUNS)

        def run_concurrent_queries() -> float:
            queries_to_run = test_queries[:NUM_CONCURRENT_QUERIES]
            start_time = time.perf_counter()

            with ThreadPoolExecutor(max_workers=NUM_CONCURRENT_QUERIES) as executor:
                futures = [
                    executor.submit(rag_pipeline.query, query, top_k=2)
                    for query in queries_to_run
                ]

                for future in as_completed(futures):
                    future.result()

            end_time = time.perf_counter()
            elapsed = end_time - start_time
            throughput = len(queries_to_run) / elapsed if elapsed > 0 else 0.0

            return throughput

        throughput_values = []

        def benchmark_wrapper() -> float:
            throughput = run_concurrent_queries()
            throughput_values.append(throughput)
            return throughput

        for _ in range(NUM_RUNS):
            benchmark_wrapper()

        avg_throughput = (
            sum(throughput_values) / len(throughput_values)
            if throughput_values
            else 0.0
        )

        failure_msg = (
            f"Throughput threshold not met:\n"
            f"  Average throughput: {avg_throughput:.2f} queries/second (threshold: {THRESHOLD_MIN_THROUGHPUT} queries/second)\n"
            f"  Total samples: {len(throughput_values)}"
        )

        assert avg_throughput >= THRESHOLD_MIN_THROUGHPUT, failure_msg

    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_warm_up_effect(
        self,
        rag_pipeline: RAGPipeline,
        test_queries: list[str],
        benchmark: Any,
    ) -> None:
        run_warm_up(rag_pipeline, test_queries, WARM_UP_RUNS)

        timing_data = []

        def run_and_time() -> dict[str, Any]:
            start = time.perf_counter()
            result = rag_pipeline.query(test_queries[0], top_k=2)
            elapsed = time.perf_counter() - start
            timing_data.append(elapsed)
            return result

        for _ in range(NUM_RUNS):
            run_and_time()

        assert len(timing_data) >= 2, "Not enough timing samples collected"

        first_run_time = timing_data[0]

        subsequent_times = timing_data[1:]
        avg_subsequent = sum(subsequent_times) / len(subsequent_times)

        ratio = first_run_time / avg_subsequent if avg_subsequent > 0 else float("inf")

        max_warm_up_ratio = 1.5

        failure_msg = (
            f"Warm-up effect detected - first run significantly slower:\n"
            f"  First run time: {first_run_time:.3f}s\n"
            f"  Average subsequent: {avg_subsequent:.3f}s\n"
            f"  Ratio: {ratio:.2f}x (max allowed: {max_warm_up_ratio}x)\n"
            f"  This suggests warm-up may not be fully effective."
        )

        assert ratio <= max_warm_up_ratio, failure_msg

        if len(subsequent_times) > 1:
            variance = sum((t - avg_subsequent) ** 2 for t in subsequent_times) / len(
                subsequent_times
            )
            std_dev = variance**0.5
            cv = std_dev / avg_subsequent if avg_subsequent > 0 else float("inf")

            max_cv = 0.5
            cv_failure_msg = (
                f"High performance variance in subsequent runs:\n"
                f"  Coefficient of variation: {cv:.2%} (max allowed: {max_cv:.2%})\n"
                f"  This suggests inconsistent performance."
            )
            assert cv <= max_cv, cv_failure_msg

    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_p95_p99_latency(
        self,
        rag_pipeline: RAGPipeline,
        test_queries: list[str],
        benchmark: Any,
    ) -> None:
        run_warm_up(rag_pipeline, test_queries, WARM_UP_RUNS)

        def run_query() -> dict[str, Any]:
            query = test_queries[0]
            return rag_pipeline.query(query, top_k=3)

        benchmark(run_query)

        stats = benchmark.stats
        all_times = stats.get("data", [])

        assert len(all_times) >= NUM_RUNS, (
            f"Need at least {NUM_RUNS} samples for percentile analysis"
        )

        p95_latency = calculate_percentile(all_times, 95)
        p99_latency = calculate_percentile(all_times, 99)

        threshold_p99 = 10.0

        failure_msg = (
            f"Latency percentile thresholds exceeded:\n"
            f"  P95 latency: {p95_latency:.3f}s (threshold: {THRESHOLD_P95_RESPONSE_TIME}s)\n"
            f"  P99 latency: {p99_latency:.3f}s (threshold: {threshold_p99}s)\n"
            f"  Min latency: {min(all_times):.3f}s\n"
            f"  Max latency: {max(all_times):.3f}s\n"
            f"  Total samples: {len(all_times)}"
        )

        assert p95_latency < THRESHOLD_P95_RESPONSE_TIME, failure_msg
        assert p99_latency < threshold_p99, failure_msg
