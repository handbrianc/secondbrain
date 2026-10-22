#!/bin/sh
# Stub CLI: successful chat session listing. Prints the CLI's session-table
# format, one line per session. Used by the chat list tool tests (no Python
# or Qdrant required).
cat <<'EOF'
ab12cd34: 3 messages (created: 2026-10-14T10:00:00)
ef56ab78: 1 message (created: 2026-10-15T08:30:00)
EOF
exit 0
