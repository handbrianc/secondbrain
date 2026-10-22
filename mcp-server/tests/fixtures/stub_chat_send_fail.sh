#!/bin/sh
# Stub CLI: failing chat send. Prints diagnostics to both streams and exits
# 1, like the real CLI does when the LLM endpoint is unreachable. Used by
# the chat send tool tests (no Python or Qdrant required).
echo "stub-chat-send-failure: partial stdout before the crash"
echo "stub-chat-send-failure: the LLM endpoint is unreachable" >&2
exit 1
