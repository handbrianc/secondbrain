#!/usr/bin/env python3
"""Benchmark the ``secondbrain ingest`` command across a range of worker cores.

This module measures wall-clock time and peak resident memory of the
``secondbrain ingest`` subprocess for each core count, using a corpus of
plain-text files and an isolated MongoDB database/collection so that every run
starts from a cold, fresh state.

The benchmark is driven entirely from the CLI::

    python scripts/bench_ingest_scaling.py --corpus /tmp/corpus --cores 1,2,4

If ``--corpus`` is omitted a plain-text corpus is generated into a temporary
directory (and cleaned up automatically via :mod:`tempfile`).

.. note::
    MongoDB must be reachable before running; see ``--uri`` and the pre-check
    performed at startup. The local test stack can be started with
    ``docker-compose -f docker-compose.test.yml up -d``.

Attributes:
    CORPUS_PARAGRAPH (str): The exact paragraph of text used to build the
        generated corpus when ``--corpus`` is not supplied.
"""

from __future__ import annotations

import argparse
import os
import re
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:  # pragma: no cover - dependency should be installed
    MongoClient = None  # type: ignore[assignment,misc]

#: The exact paragraph reused verbatim for generated corpus files.
CORPUS_PARAGRAPH = (
    "Experiments with neural information retrieval show that dense semantic "
    "retrieval reliably outperforms lexical term matching for open-domain "
    "question answering. Modern retrieval systems embed both queries and "
    "documents into a shared, high-dimensional vector space where cosine "
    "similarity approximates the semantic relatedness of the underlying text. "
    "This approach underpins retrieval-augmented generation, a strategy that "
    "first recalls the most relevant passages from a large corpus and then "
    "passes them to a generative language model to compose the final answer. "
    "The quality of the retrieved evidence is usually the strongest predictor "
    "of the quality of the generated response."
)

#: Default URI for the local test MongoDB stack.
DEFAULT_URI = (
    "mongodb://testuser:testpass@localhost:27018"
    "/secondbrain_test?authSource=admin"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate the benchmark command-line arguments.

    Parameters
    ----------
    argv : list of str, optional
        Argument list to parse; defaults to ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
        The parsed namespace with ``corpus``, ``cores``, ``uri``, ``db``,
        ``collection`` and ``repeat`` attributes.
    """
    parser = argparse.ArgumentParser(
        description="Benchmark secondbrain ingest across worker core counts."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="Directory of files to ingest. If omitted, a plain-text corpus is "
        "generated into a temporary directory.",
    )
    parser.add_argument(
        "--cores",
        type=str,
        default=",".join([str(n) for n in (1, 2, 4, 8)] + [str(os.cpu_count())]),
        help="Comma-separated list of core counts to benchmark. "
        "Default: 1,2,4,8,<os.cpu_count()>.",
    )
    parser.add_argument(
        "--uri",
        type=str,
        default=DEFAULT_URI,
        help="MongoDB connection URI. Default: %(default)s",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="secondbrain_bench_scale",
        help="Database name. Default: %(default)s",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="embeddings_bench_scale",
        help="Collection name. Default: %(default)s",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of repetitions per core count. Default: %(default)s",
    )
    return parser.parse_args(argv)


def mongo_client(uri: str, timeout_ms: int):
    """Return a configured :class:`MongoClient`, raising if pymongo missing.

    Parameters
    ----------
    uri : str
        MongoDB connection URI.
    timeout_ms : int
        Server selection timeout in milliseconds.

    Returns
    -------
    MongoClient
        A client configured with the given server-selection timeout.

    Raises
    ------
    RuntimeError
        If ``pymongo`` is not installed.
    """
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed")
    return MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)


def check_mongo(uri: str) -> None:
    """Verify MongoDB is reachable, exiting with code 2 on failure.

    Parameters
    ----------
    uri : str
        MongoDB connection URI to ping.

    Raises
    ------
    SystemExit
        Exits with status code 2 if the server cannot be reached, printing a
        short startup hint to stderr.
    """
    try:
        mongo_client(uri, 2000).admin.command("ping")
    except Exception:
        print(
            "MongoDB unreachable — start via: "
            "docker-compose -f docker-compose.test.yml up -d",
            file=sys.stderr,
        )
        sys.exit(2)


def generate_corpus(root: Path, count: int = 8) -> None:
    """Generate a plain-text corpus of ``count`` files into ``root``.

    Parameters
    ----------
    root : Path
        Destination directory; must already exist.
    count : int, optional
        Number of ``d<i>.txt`` files to create (default 8).
    """
    for i in range(1, count + 1):
        repetitions = 2 + (i % 3)
        content = (CORPUS_PARAGRAPH + "\n") * repetitions
        (root / f"d{i}.txt").write_text(content, encoding="utf-8")


def ingest_once(
    corpus: Path,
    cores: int,
    uri: str,
    db: str,
    collection: str,
) -> tuple[float, float, int]:
    """Run a single ``secondbrain ingest`` across ``corpus`` with ``cores``.

    Parameters
    ----------
    corpus : Path
        Corpus directory to ingest.
    cores : int
        Number of worker cores for this run.
    uri : str
        MongoDB connection URI.
    db : str
        Target database name.
    collection : str
        Target collection name.

    Returns
    -------
    tuple of (float, float, int)
        A 3-tuple of ``(wall_seconds, peak_rss_mb, success_count)``. Peak RSS
        is taken from ``RUUSAGE_CHILDREN`` (bytes on macOS) converted to MB,
        and ``success_count`` is parsed from the ingested-file count reported
        on the subprocess stdout.
    """
    # Fresh cold start: drop the collection before every run.
    mongo_client(uri, 3000)[db][collection].drop()

    env = dict(os.environ)
    env["SECONDBRAIN_MONGO_URI"] = uri
    env["SECONDBRAIN_MONGO_DB"] = db
    env["SECONDBRAIN_MONGO_COLLECTION"] = collection

    cmd = [
        "secondbrain",
        "ingest",
        str(corpus),
        "--recursive",
        "--cores",
        str(cores),
        "--pool",
        "process",
        "--no-skip-existing",
    ]

    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )
    wall = time.perf_counter() - start

    peak_rss_bytes = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    peak_rss_mb = peak_rss_bytes / (1024**2)

    success = parse_success_count(proc.stdout)
    if success == 0:
        print(
            f"[bench] warning: no 'Successfully ingested N files' found on "
            f"stderr for cores={cores}; treating success as 0",
            file=sys.stderr,
        )
    return wall, peak_rss_mb, success


def parse_success_count(stdout: str) -> int:
    """Extract the number of successfully ingested files from CLI output.

    Parameters
    ----------
    stdout : str
        Captured stdout of the ``secondbrain ingest`` subprocess.

    Returns
    -------
    int
        The ingested-file count parsed from a ``Successfully ingested N
        files`` line, or 0 when the pattern is not found.
    """
    # Strip ANSI escape sequences so Rich-formatted output parses cleanly.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
    match = re.search(r"Successfully ingested (\d+) file", plain)
    return int(match.group(1)) if match else 0


def main(argv: list[str] | None = None) -> int:
    """Run the scaling benchmark and print a Markdown results table.

    Parameters
    ----------
    argv : list of str, optional
        Argument list; defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        Process exit code (0 on success).
    """
    args = parse_args(argv)

    check_mongo(args.uri)

    cores_list = [int(c) for c in args.cores.split(",") if c.strip()]

    corpus = args.corpus
    cleanup: tempfile.TemporaryDirectory[str] | None = None
    if corpus is None:
        cleanup = tempfile.TemporaryDirectory(prefix="sb_bench_corpus_")
        corpus = Path(cleanup.name)
        generate_corpus(corpus, count=8)

    # Count supported corpus files.
    file_count = sum(1 for p in corpus.iterdir() if p.is_file())

    print("| cores | wall_s | files/s | peak_rss_MB | success |")
    print("|-------|--------|---------|-------------|---------|")
    for cores in cores_list:
        for _ in range(max(1, args.repeat)):
            wall, peak_rss_mb, success = ingest_once(
                corpus, cores, args.uri, args.db, args.collection
            )
            files_per_s = (file_count / wall) if wall > 0 else 0.0
            print(
                f"| {cores} | {wall:.2f} | {files_per_s:.2f} | "
                f"{peak_rss_mb:.2f} | {success} |"
            )

    if cleanup is not None:
        cleanup.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
