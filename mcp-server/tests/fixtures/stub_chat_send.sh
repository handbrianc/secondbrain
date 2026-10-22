#!/bin/sh
# Stub CLI: successful chat send. Prints the CLI's reasoning-indicator line
# then a known answer. Records, to the file named by STUB_CHAT_SEND_ENV_LOG,
# the observed SECONDBRAIN_SHOW_THINKING value (first line) and the received
# argv (second line), for the env and argv assertions. No Python or Qdrant
# required.
if [ -n "${STUB_CHAT_SEND_ENV_LOG:-}" ]; then
    {
        echo "${SECONDBRAIN_SHOW_THINKING-<unset>}"
        echo "argv: $*"
    } >"$STUB_CHAT_SEND_ENV_LOG" 2>/dev/null || :
fi
echo "▸ Thinking: 123 chars (collapsed)"
echo "The capital of France is Paris."
exit 0
