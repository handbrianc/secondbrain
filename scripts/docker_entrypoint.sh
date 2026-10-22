#!/bin/sh
# Container entrypoint: hand writable staging directories to the runtime
# user, then re-exec the command as that user — the server and CLI never
# run as root.
#
# Why: compose (and `docker run`) auto-create missing bind-mount sources as
# root-owned directories, which the non-root runtime user cannot write to.
# The upload staging directory (add-mcp-upload-tool) is the one writable
# workspace surface, so when this script starts as root it creates and
# chowns the configured staging directory before dropping privileges.
# Started as a non-root user (e.g. `docker run --user`, Kubernetes
# runAsNonRoot), it skips the handover — ownership is the operator's then.

set -eu

RUNTIME_USER=app

if [ "$(id -u)" != "0" ]; then
  exec "$@"
fi

# Resolve the staging directory exactly like the server's config does:
# SECONDBRAIN_MCP_UPLOAD_DIR defaults to `uploads`; a relative value anchors
# at SECONDBRAIN_MCP_WORKSPACE_ROOT.
workspace=${SECONDBRAIN_MCP_WORKSPACE_ROOT:-/data/workspace}
staging=${SECONDBRAIN_MCP_UPLOAD_DIR:-uploads}
case $staging in
  /*) ;;
  *) staging=$workspace/$staging ;;
esac

# The staging mount layer is read-write, so both steps succeed for the
# compose layout. A staging directory configured elsewhere in the
# (read-only) workspace cannot be created or chowned — leave the failure to
# the server, which reports it naming the variable.
mkdir -p "$staging" 2>/dev/null || true
chown -R "$RUNTIME_USER:$RUNTIME_USER" "$staging" 2>/dev/null \
  || echo "warning: could not hand $staging to $RUNTIME_USER; uploads may fail" >&2

exec gosu "$RUNTIME_USER" "$@"
