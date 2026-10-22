#!/bin/sh
# Stub CLI: failing chat session listing. Prints diagnostics to both streams
# and exits 1, like the real CLI does when the session store is unreadable.
# Used by the chat list tool tests (no Python or Qdrant required).
echo "stub-chat-sessions-failure: partial stdout before the crash"
echo "stub-chat-sessions-failure: the session store is unreadable" >&2
exit 1
