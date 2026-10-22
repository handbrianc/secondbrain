#!/bin/sh
# Stub CLI for the upload tool tests: like stub_ingest.sh (spawn log,
# BOOM.txt failure sentinel, canned summary echoing the argv), plus a check
# that the received path is inside the workspace root passed down through
# the server's inherited environment (SECONDBRAIN_MCP_WORKSPACE_ROOT) — so a
# successful upload proves the stored path reached the CLI through the
# confined ingest flow. No Python or Qdrant required.
#
# Sentinels, matched on the stored file's name:
# - BOOM.txt  the ingest fails (exit 1, diagnostic on stderr)
# - STUCK.txt the ingest succeeds but replaces the stored file with a
#             same-named directory, so the server's post-ingest cleanup
#             fails deterministically
# - *SLOW*    the ingest sleeps ~2s before the canned success, so a poll can
#             observe a job in its running state
if [ -n "${STUB_INGEST_SPAWN_LOG:-}" ]; then
    echo "spawn: $*" >>"$STUB_INGEST_SPAWN_LOG" 2>/dev/null || :
fi
path="$2"
case "$path" in
    */BOOM.txt)
        echo "stub-ingest-upload: ingest of $path exploded" >&2
        exit 1
        ;;
    */STUCK.txt)
        # Delete-failure sentinel: replace the stored file with a same-named
        # directory and exit 0. The server's post-ingest cleanup then fails
        # deterministically on every platform and user (remove_file refuses
        # directories), and the tool must report that inside an
        # otherwise-successful result.
        rm -f "$path" && mkdir "$path"
        ;;
    *SLOW*)
        # Slow-ingest sentinel: sleep briefly before the canned success so
        # the asynchronous job's running state is observable by a poll.
        sleep 2
        ;;
esac
ws="${SECONDBRAIN_MCP_WORKSPACE_ROOT:-}"
if [ -n "$ws" ]; then
    case "$path" in
        "$ws"/*) ;;
        *)
            echo "stub-ingest-upload: path outside the workspace root: $path" >&2
            exit 9
            ;;
    esac
fi
if [ -e "$path" ]; then
    echo "stub-ingest-upload: ingested $path"
    echo "stub-ingest-upload: argv: $*"
    echo "stub-ingest-upload: 1 documents, 3 chunks, 0 skipped"
    exit 0
fi
echo "stub-ingest-upload: no such file or directory: $path" >&2
exit 1
