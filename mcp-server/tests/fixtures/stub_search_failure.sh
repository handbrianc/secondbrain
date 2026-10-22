#!/bin/sh
# Stub CLI: failing search. Prints partial diagnostics to both streams and
# exits 1, like the real CLI does when Qdrant is unreachable. Used by the
# search tool tests (no Python or Qdrant required).
echo "stub-search-failure: partial stdout before the crash"
echo "stub-search-failure: SECONDBRAIN_QDRANT_URL unreachable" >&2
exit 1
