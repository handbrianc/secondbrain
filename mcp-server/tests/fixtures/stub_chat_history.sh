#!/bin/sh
# Stub CLI: chat history. Prints a canned history block for any requested
# session except the sentinel `unknown-session`; exits 1 for the sentinel or
# when --session is absent, like the real CLI does for unknown sessions and
# missing arguments. Used by the chat history tool tests (no Python, SQLite,
# or Qdrant required).
case "$*" in
    *"--session unknown-session"*)
        echo "stub-chat-history: session not found: unknown-session" >&2
        exit 1
        ;;
    *"--session "*)
        cat <<'EOF'
Session existing-session-42 (3 messages):

[user] What is secondbrain?
[assistant] A local document intelligence CLI for semantic search.
[user] What storage does it use?
[assistant] Qdrant for vectors, SQLite for conversations.
EOF
        exit 0
        ;;
    *)
        echo "stub-chat-history: --session is required" >&2
        exit 1
        ;;
esac
