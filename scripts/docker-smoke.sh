#!/bin/bash
# Smoke-verify the Secondbrain container image (revise-dockerfile-for-mcp):
#   1. build the multi-stage image (MCP server + Python CLI),
#   2. start a container on an ephemeral host port and poll /healthz until healthy,
#   3. POST tools/list to the MCP endpoint and require a JSON tool list,
#   4. run the packaged secondbrain CLI (--help must exit 0),
#   5. assert the container runs as the non-root app user,
# tearing everything down on exit (trap).
#
# Usage: ./scripts/docker-smoke.sh [IMAGE_NAME]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
IMAGE_NAME="${1:-secondbrain-smoke:local}"
CONTAINER_NAME="secondbrain-smoke-container"
SMOKE_TIMEOUT_SECONDS=120

log() { echo "[docker-smoke] $*"; }
fail() { echo "[docker-smoke] ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "docker is not installed"
command -v curl >/dev/null 2>&1 || fail "curl is not installed"

CONTAINER_CREATED=false

cleanup() {
    if [ "$CONTAINER_CREATED" = true ]; then
        log "Tearing down smoke container..."
        docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

cd "$PROJECT_ROOT"

log "Building image ${IMAGE_NAME}..."
docker build -t "$IMAGE_NAME" .

log "Starting container on an ephemeral host port..."
docker run -d --name "$CONTAINER_NAME" -P "$IMAGE_NAME" >/dev/null
CONTAINER_CREATED=true

HOST_PORT="$(docker port "$CONTAINER_NAME" 8080/tcp | awk -F':' '{print $NF}' | head -n 1)"
[ -n "$HOST_PORT" ] || fail "container did not publish port 8080"
BASE_URL="http://127.0.0.1:${HOST_PORT}"
log "Polling ${BASE_URL}/healthz until healthy..."

ELAPSED=0
until curl -fsS -o /dev/null --max-time 2 "${BASE_URL}/healthz"; do
    if [ "$ELAPSED" -ge "$SMOKE_TIMEOUT_SECONDS" ]; then
        docker logs "$CONTAINER_NAME" --tail 50 || true
        fail "container failed to become healthy within ${SMOKE_TIMEOUT_SECONDS}s"
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
log "Container is healthy."

log "POSTing tools/list to the MCP endpoint..."
# The server runs rmcp in stateless mode: tools/list needs no initialize
# handshake or session id, but its content-negotiation gate requires both
# media types (same request shape as mcp-server/tests/transport.rs).
TOOLS_RESPONSE="$(curl -fsS --max-time 5 \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
    "${BASE_URL}/mcp")"
echo "$TOOLS_RESPONSE" | grep -q '"tools"' \
    || fail "tools/list response missing a tool list: ${TOOLS_RESPONSE}"
log "MCP endpoint answered with a JSON tool list."

log "Checking the packaged CLI..."
docker run --rm "$IMAGE_NAME" secondbrain --help >/dev/null 2>&1 \
    || fail "docker run --rm <image> secondbrain --help did not exit 0"
log "secondbrain --help exits 0."

log "Checking non-root execution..."
# NOTE: the image carries CMD ["secondbrain-mcp"], and `docker run
# --entrypoint id <image>` would append that CMD as id operands (breaking the
# check), so the command is overridden instead — equivalent intent: run `id`
# as the image's default user.
USER_OUT="$(docker run --rm "$IMAGE_NAME" id)"
echo "$USER_OUT" | grep -q "app" \
    || fail "container does not run as the non-root app user: ${USER_OUT}"
log "Container runs as the non-root app user (${USER_OUT})."

log "Smoke passed."
