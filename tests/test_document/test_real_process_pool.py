"""Real OS-process proof for the multicore-ingestion pool.

The archived multicore-ingestion spec requires text extraction and chunking to
run through a real ``ProcessPoolExecutor`` (spec requirements at spec.md:41 and
spec.md:58). Every other pool test in this directory monkeypatches the
executor class with fakes; this module is the missing real-process slice:

- a REAL ``ProcessPoolExecutor(max_workers=1)`` (real OS processes, real
  pickle round trip of worker arguments and of the returned documents),
- the ACTUAL production worker ``processor._extract_chunk_and_embed_file``,
- real PDF text extraction through the pypdfium2 fast path (a tiny generated
  in-repo PDF, so the child never needs docling),
- real chunking (``chunk_segments``) honoring chunk_size/chunk_overlap,
- real embedding generation by the production ``OpenAIEmbeddingProvider``
  against a local OpenAI-compatible embeddings HTTP server, configured through
  ``SECONDBRAIN_EMBEDDING_*`` environment variables that the spawned process
  inherits (the provider factory builds the provider from config inside the
  child, so the local server is the only way to keep that slice real).

The only test shim is pid capture: the submitted function is a module-level
wrapper that calls the real worker untouched and adds ``os.getpid()`` to its
result, so the test can assert the work happened in a different process
(the worker's own return contract is unchanged).

Tests are marked ``xdist_group("process_pool")`` so xdist never runs them
concurrently with the other process-pool tests.
"""

import itertools
import json
import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from secondbrain.config import config
from secondbrain.document import DocumentIngestor
from secondbrain.document.chunker import chunk_segments
from secondbrain.document.fast_text import try_fast_pdf_extraction
from secondbrain.document.processor import _extract_chunk_and_embed_file

CHUNK_SIZE = 200
CHUNK_OVERLAP = 30
EMBEDDING_DIM = 8

# Long enough to clear the fast path's PDF_FAST_TEXT_MIN_CHARS (200) gate and
# to produce several chunks at chunk_size=200. Every sentence carries its own
# index, so no two chunk texts normalize to the same hash — the worker's
# chunk-level dedup must not drop anything here, or the overlap property
# asserted below would compare non-adjacent chunks.
_PDF_TEXT = " ".join(
    f"Probe paragraph {index} explains how the real multicore ingestion pool "
    f"worker extracts text layer {index}, splits chunk boundary {index}, and "
    f"embeds vector {index} inside a separate child process for the test."
    for index in range(1, 13)
)

_TESTS = ["second", "brain", "pool", "worker", "child", "process", "vector", "store"]


def _worker_with_pid(*args: Any) -> dict[str, Any]:
    """Module-level shim: run the REAL pool worker, tag the result with its pid.

    Must stay module-level (pickled by reference into the child process).
    """
    result = _extract_chunk_and_embed_file(*args)
    result["pid"] = os.getpid()
    return result


def _build_minimal_pdf(path: Path) -> Path:
    """Write a minimal one-page PDF whose text layer carries ``_PDF_TEXT``."""
    stream = f"BT /F1 12 Tf 72 720 Td ({_PDF_TEXT}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (num, body)
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_pos,
    )
    path.write_bytes(bytes(out))
    return path


def _worker_args(pdf: Path) -> tuple[Any, ...]:
    """The exact positional args the sync pool loop builds per file."""
    return (
        str(pdf),
        CHUNK_SIZE,
        CHUNK_OVERLAP,
        None,  # progress_queue: no progress consumer in this test
        config().embedding_model,
        None,  # embedding_cache: the process pool always passes None
        False,  # skip_existing: no storage in the child process
        False,  # scrape_docling_pages: no docling conversion happens here
    )


@pytest.fixture(autouse=True)
def _spawn_pool_children(monkeypatch: pytest.MonkeyPatch):
    """Force pools created in these tests to spawn their workers.

    CPython 3.14's Linux default start method is forkserver, and a forkserver
    captures ``os.environ`` exactly once — when whatever test in this xdist
    worker first creates a process pool starts it — and every later forked
    child inherits that stale snapshot. These tests point the child's
    ``config()`` at a per-test local server through monkeypatched env vars,
    so a stale forkserver (started by an earlier test file, or by an earlier
    test here, holding a now-dead port) would silently break them. Spawn
    execs a fresh interpreter per worker with the *current* environment,
    which keeps each test hermetic; it is still a real ``ProcessPoolExecutor``
    with real OS processes and a real pickle round trip.
    """
    spawn_context = multiprocessing.get_context("spawn")
    monkeypatch.setattr(multiprocessing, "get_context", lambda *_: spawn_context)


@pytest.fixture
def embeddings_server(monkeypatch: pytest.MonkeyPatch):
    """Serve OpenAI-compatible embeddings locally and point config at it.

    The child process builds its own ``OpenAIEmbeddingProvider`` from
    ``config()``, which reads ``SECONDBRAIN_EMBEDDING_API_BASE``; monkeypatched
    env vars are set via ``os.environ`` and therefore inherited by the spawned
    processes. Responses are deterministic per input index so the test can
    prove the production embedding provider actually ran in the child.
    """

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
            )
            texts = body.get("input", [])
            payload = json.dumps(
                {
                    "object": "list",
                    "data": [
                        {
                            "object": "embedding",
                            "index": index,
                            "embedding": [float((index + 1) % 7 + 0.5)] * EMBEDDING_DIM,
                        }
                        for index in range(len(texts))
                    ],
                    "model": body.get("model", "test-model"),
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: Any) -> None:
            """Silence per-request logging."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "SECONDBRAIN_EMBEDDING_API_BASE", f"http://127.0.0.1:{server.server_port}"
    )
    monkeypatch.setenv("SECONDBRAIN_EMBEDDING_API_KEY", "local-test-key")
    monkeypatch.setenv("SECONDBRAIN_EMBEDDING_TIMEOUT", "60")
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _expected_worker_texts(segments: list[dict[str, Any]]) -> list[str]:
    """The chunk texts the worker stores, derived in this process.

    Mirrors the worker's normalization (``processor.py``): ``chunk_segments``
    output, each chunk ``strip()``ed, then deduplicated by normalized-text
    hash in first-occurrence order.
    """
    expected: list[str] = []
    seen: set[str] = set()
    for chunk in chunk_segments(segments, CHUNK_SIZE, CHUNK_OVERLAP):
        cleaned = chunk["text"].strip()
        normalized = " ".join(cleaned.lower().split())
        if normalized not in seen:
            seen.add(normalized)
            expected.append(cleaned)
    return expected


def _assert_real_chunked_documents(documents: list[dict[str, Any]], pdf: Path) -> None:
    """Shared assertions: real extraction, chunking, and embedding results."""
    assert documents, "the real worker must produce chunked, embedded documents"

    # Real extraction: the pypdfium2 fast path reads the PDF's real text
    # layer (the child has no other text source).
    extracted = try_fast_pdf_extraction(pdf)
    assert extracted, "expected the fast path to extract the probe PDF"
    ground_truth = "".join(seg["text"] for seg in extracted)

    # Real chunking: the production chunker, run on the same extraction in
    # this process, produces exactly what the child stored. Its raw output
    # carries the overlap invariant (chunk n+1 re-states the last
    # chunk_overlap characters of chunk n); the worker additionally strips
    # each chunk and drops normalized duplicates before storing.
    raw_chunks = chunk_segments(extracted, CHUNK_SIZE, CHUNK_OVERLAP)
    assert len(raw_chunks) >= 3, "the probe PDF must produce several chunks"
    for previous, following in itertools.pairwise(raw_chunks):
        assert following["text"][:CHUNK_OVERLAP] == previous["text"][-CHUNK_OVERLAP:], (
            "chunk_segments must keep the configured overlap between chunks"
        )

    texts = [doc["chunk_text"] for doc in documents]
    assert texts == _expected_worker_texts(extracted), texts
    assert all(text in ground_truth for text in texts), texts
    assert all(len(text) <= CHUNK_SIZE for text in texts)

    # Real embedding round trip through the local OpenAI-compatible server:
    # deterministic per-index vectors prove the production provider ran in
    # the child (a mock or a failed provider could not produce them).
    for index, doc in enumerate(documents):
        embedding = np.asarray(doc["embedding"])
        assert embedding.dtype == np.float32
        assert embedding.shape == (EMBEDDING_DIM,)
        assert np.allclose(embedding, float((index + 1) % 7 + 0.5))

    assert documents[0]["file_type"] == "pdf"
    assert documents[0]["page_number"] == 1


class TestRealProcessPool:
    """The spec's ProcessPoolExecutor requirement, proven with a real pool."""

    @pytest.mark.xdist_group("process_pool")
    @pytest.mark.medium
    def test_real_pool_worker_runs_in_another_process(
        self, tmp_path: Path, embeddings_server
    ) -> None:
        """The actual pool worker executes in a different OS process.

        It returns the expected chunked + embedded result.
        """
        pdf = _build_minimal_pdf(tmp_path / "real_pool_probe.pdf")

        with ProcessPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_worker_with_pid, *_worker_args(pdf))
            result = future.result(timeout=90)

        assert result["success"] is True, result.get("error")
        # The work happened in a child process, not the pytest worker.
        assert result["pid"] != os.getpid()
        _assert_real_chunked_documents(result["documents"], pdf)

    @pytest.mark.xdist_group("process_pool")
    @pytest.mark.medium
    def test_production_pool_loop_drives_real_worker(
        self, tmp_path: Path, embeddings_server
    ) -> None:
        """The production pool loop drives the real worker on a real pool.

        ``_process_parallel_with_progress`` runs the real worker on a real
        pool and stores what it returns.
        """
        pdf = _build_minimal_pdf(tmp_path / "real_loop_probe.pdf")

        ingestor = DocumentIngestor.__new__(DocumentIngestor)
        ingestor.chunk_size = CHUNK_SIZE
        ingestor.chunk_overlap = CHUNK_OVERLAP
        ingestor.embedding_cache = object()  # process pool passes None anyway
        ingestor.progress_callback = None
        ingestor.on_chunk_progress = None
        ingestor.on_phase_progress = None

        storage_calls: list[list[dict[str, Any]]] = []
        storage = type(
            "_RecordingStorage",
            (),
            {"store_batch": staticmethod(lambda batch: storage_calls.append(batch))},
        )()

        successful, failed, reasons, skipped = ingestor._process_parallel_with_progress(
            [pdf], object(), storage, 1, "process", skip_existing=False
        )

        assert (successful, failed, reasons, skipped) == (1, 0, [], 0)
        assert len(storage_calls) == 1
        _assert_real_chunked_documents(storage_calls[0], pdf)
