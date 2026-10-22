#!/bin/sh
# Stub CLI: ingest. $1 is the tool's `ingest` subcommand; $2 is the resolved
# path the tool passed. Validates it: an existing file or directory prints a
# canned summary (exit 0); a missing path exits 1 like the real CLI
# (click.Path(exists=True)); the sentinel BOOM.txt exists but makes the stub
# fail, for the CLI-failure test. The summary echoes the received argv so
# tests can assert the resolved path and mapped flags. When
# STUB_INGEST_SPAWN_LOG is set, every spawn appends a line there, so tests
# can assert whether the CLI ran at all. No Python or Qdrant required.
if [ -n "${STUB_INGEST_SPAWN_LOG:-}" ]; then
    echo "spawn: $*" >>"$STUB_INGEST_SPAWN_LOG" 2>/dev/null || :
fi
path="$2"
case "$path" in
    */BOOM.txt)
        echo "stub-ingest: ingest of $path exploded" >&2
        exit 1
        ;;
esac
if [ -e "$path" ]; then
    echo "stub-ingest: ingested $path"
    echo "stub-ingest: argv: $*"
    echo "stub-ingest: 2 documents, 5 chunks, 0 skipped"
    exit 0
fi
echo "stub-ingest: no such file or directory: $path" >&2
exit 1
