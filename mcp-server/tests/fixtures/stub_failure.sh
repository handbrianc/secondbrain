#!/bin/sh
# Stub CLI: failing invocation. Prints diagnostics to stdout/stderr and
# exits 3. Used by the CLI adapter tests (no Python or Qdrant required).
echo "stub-failure-stdout diagnostics"
echo "stub-failure-stderr diagnostics" >&2
exit 3
