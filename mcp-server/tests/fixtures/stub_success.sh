#!/bin/sh
# Stub CLI: successful invocation. Prints known stdout, writes to stderr,
# exits 0. Used by the CLI adapter tests (no Python or Qdrant required).
echo "stub-success-stdout line 1"
echo "stub-success-stdout line 2"
echo "stub-success-stderr diagnostics" >&2
exit 0
