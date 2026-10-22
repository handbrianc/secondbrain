#!/bin/bash
# MCP end-to-end smoke (add-mcp-e2e-smoke): drive a real MCP client flow over
# HTTP(S) against either compose stack:
#
#   health -> tools/list -> ingest_documents (fixture document) -> search
#   (assert the fixture document comes back) -> chat_send (only when a usable
#   LLM is configured in the stack env), with the stack torn down on exit,
#   including failure.
#
# Usage: ./scripts/mcp_e2e_smoke.sh --stack <test|prod>
#         [SMOKE_PROJECT_ROOT=/path/to/other/checkout]
#
# Service assumptions (documented, not configured by this script):
#   - Ingest and search drive the REAL secondbrain CLI, which embeds through
#     an OpenAI-compatible API (SECONDBRAIN_EMBEDDING_*). The mock embedding
#     provider is pytest-fixture-only and cannot be selected via environment,
#     so the stack under test must have a usable embedding endpoint
#     configured (test stack: the SECONDBRAIN_EMBEDDING_* entries in
#     docker-compose.test.yml; prod: .env.docker). Without one, the smoke
#     warns up front and the ingest/search steps then fail with the CLI's
#     cause in the tool result.
#   - chat_send runs only when a usable LLM is configured in the stack env
#     (an OpenAI-compatible key or base URL, or an Anthropic key when
#     SECONDBRAIN_LLM_PROVIDER=anthropic); otherwise the step is skipped with
#     an explicit warning and the rest of the smoke still validates.
#   - Scheme follows the stack's configuration: https when the container env
#     has SECONDBRAIN_MCP_HTTP_TLS_ENABLED=true (self-signed certs are
#     accepted with curl -k), plaintext http otherwise.
#   - Host allowlist: when the stack env sets SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS,
#     the MCP endpoint rejects requests whose Host header is not allowlisted
#     (a plain 127.0.0.1 request gets 403); the MCP calls then carry the first
#     allowlisted host as the Host header while the TCP target stays local.
#   - Teardown runs `docker compose down` on exit (failure included) but
#     KEEPS the named volumes, so smoke runs are idempotent (ingest skips
#     already-ingested chunks) and the shared test data survives.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# Optional cross-checkout override: drive ANOTHER checkout's stack (e.g. the
# deployed production checkout) with this script's logic. The compose files,
# env, and project identity come from SMOKE_PROJECT_ROOT; the driver code
# (health wait, gates, JSON-RPC calls) comes from this script.
PROJECT_ROOT="${SMOKE_PROJECT_ROOT:-$PROJECT_ROOT}"

STACK=""
SMOKE_TIMEOUT_SECONDS=120   # wait-for-health budget after compose up returns
MCP_CALL_TIMEOUT=180        # per-call curl budget (ingest/chat embed remotely)

# Test stack: test qdrant + test MCP server on host 8081, fixture workspace.
# Prod stack: bundled qdrant + production MCP server on host 8080. The stack
# runs only the MCP server and qdrant (there is no `cli` service); `up` of
# the named service brings qdrant along via depends_on.
STACK_TEST_COMPOSE="docker-compose.test.yml"
STACK_PROD_COMPOSE="docker-compose.yml"
MCP_SERVICE="mcp-server"

log() { echo "[mcp-e2e-smoke] $*"; }
warn() { echo "[mcp-e2e-smoke] WARNING: $*" >&2; }
fail() { echo "[mcp-e2e-smoke] ERROR: $*" >&2; exit 1; }

usage() {
    echo "Usage: $0 --stack <test|prod>" >&2
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --stack)
            [ $# -ge 2 ] || usage
            STACK="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done
[ -n "$STACK" ] || usage

case "$STACK" in
    test) COMPOSE_FILE="$STACK_TEST_COMPOSE"; HOST_PORT=8081 ;;
    prod) COMPOSE_FILE="$STACK_PROD_COMPOSE"; HOST_PORT=8080 ;;
    *) usage ;;
esac

command -v docker >/dev/null 2>&1 || fail "docker is not installed"
command -v curl >/dev/null 2>&1 || fail "curl is not installed"
[ -f "$PROJECT_ROOT/$COMPOSE_FILE" ] || fail "$COMPOSE_FILE not found at $PROJECT_ROOT"

STACK_UP=false
cleanup() {
    if [ "$STACK_UP" = true ]; then
        log "Tearing down the $STACK stack (named volumes are kept)..."
        docker compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

cd "$PROJECT_ROOT"

# --- Bring up: the named service and its healthy qdrant dependency ------------
log "Bringing up the $STACK stack ($COMPOSE_FILE; building if needed)..."
docker compose -f "$COMPOSE_FILE" up -d --build "$MCP_SERVICE" >/dev/null
STACK_UP=true

# --- Scheme: follow the stack's TLS configuration ------------------------------
tls_value="$(docker compose -f "$COMPOSE_FILE" exec -T "$MCP_SERVICE" printenv SECONDBRAIN_MCP_HTTP_TLS_ENABLED 2>/dev/null || true)"
if [ "$tls_value" = "true" ]; then
    SCHEME="https"
    # Self-signed stack certs: accept without verification (local smoke only).
    TLS_CURL_FLAG="-k"
else
    SCHEME="http"
    TLS_CURL_FLAG=""
fi
BASE_URL="${SCHEME}://127.0.0.1:${HOST_PORT}"
log "Probing ${BASE_URL}/healthz ..."

ELAPSED=0
until curl -fsS $TLS_CURL_FLAG -o /dev/null --max-time 2 "${BASE_URL}/healthz"; do
    if [ "$ELAPSED" -ge "$SMOKE_TIMEOUT_SECONDS" ]; then
        docker compose -f "$COMPOSE_FILE" logs "$MCP_SERVICE" --tail 50 || true
        fail "the mcp-server service did not become healthy within ${SMOKE_TIMEOUT_SECONDS}s"
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
log "Server is healthy."

# --- Environment gates ---------------------------------------------------------
# Read the server container's effective environment (the CLI subprocesses
# inherit it), then decide: chat gate (skip when no LLM) and the embedding
# pre-flight warning.
env_value() {
    docker compose -f "$COMPOSE_FILE" exec -T "$MCP_SERVICE" printenv "$1" 2>/dev/null || true
}

openai_key="$(env_value SECONDBRAIN_OPENAI_API_KEY)"
openai_base="$(env_value SECONDBRAIN_OPENAI_BASE_URL)"
anthropic_key="$(env_value SECONDBRAIN_ANTHROPIC_API_KEY)"
llm_provider="$(env_value SECONDBRAIN_LLM_PROVIDER)"
llm_provider="${llm_provider:-openai}"

if [ "$llm_provider" = "anthropic" ]; then
    LLM_USABLE=false
    [ -n "$anthropic_key" ] && LLM_USABLE=true
else
    LLM_USABLE=false
    # OpenAI-compatible: a key, or a self-hosted base URL that needs none.
    { [ -n "$openai_key" ] || [ -n "$openai_base" ]; } && LLM_USABLE=true
fi

embed_key="$(env_value SECONDBRAIN_EMBEDDING_API_KEY)"
embed_base="$(env_value SECONDBRAIN_EMBEDDING_API_BASE)"
if [ -z "$embed_key" ] && [ -z "$embed_base" ]; then
    warn "no embedding endpoint is configured in the stack env (SECONDBRAIN_EMBEDDING_API_KEY/API_BASE both unset)."
    warn "the real CLI only supports the OpenAI-compatible embedding provider (the pytest-only mock cannot be selected via env),"
    warn "so the ingest/search steps will fail with the CLI's cause. Configure the SECONDBRAIN_EMBEDDING_* entries of"
    warn "$COMPOSE_FILE to run the full cycle."
fi

# --- Host allowlist: follow the stack's allowed-hosts configuration ------------
# SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS gates the MCP endpoint (not /healthz): a
# 127.0.0.1 request against a stack that sets it is rejected with 403. When
# set, send the first allowlisted host as the Host header; the TCP target
# stays 127.0.0.1:PORT.
allowed_hosts_value="$(env_value SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS)"
HOST_CURL_FLAG=()
if [ -n "$allowed_hosts_value" ]; then
    first_allowed=""
    IFS=, read -r -a allowed_hosts <<< "$allowed_hosts_value"
    for allowed_host in "${allowed_hosts[@]}"; do
        allowed_host="${allowed_host#"${allowed_host%%[![:space:]]*}"}"
        allowed_host="${allowed_host%"${allowed_host##*[![:space:]]}"}"
        if [ -n "$allowed_host" ]; then
            first_allowed="$allowed_host"
            break
        fi
    done
    [ -n "$first_allowed" ] || fail "SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS contains no non-empty host"
    log "Stack allowlists MCP hosts ('${allowed_hosts_value}'); sending Host: ${first_allowed}"
    HOST_CURL_FLAG=(-H "Host: ${first_allowed}")
fi

# --- MCP JSON-RPC driver (curl; stateless mode, no initialize needed) ----------
mcp_post() { # <id> <method> <params-json>
    local body
    body="$(printf '{"jsonrpc":"2.0","id":%s,"method":"%s","params":%s}' "$1" "$2" "$3")"
    curl -fsS $TLS_CURL_FLAG "${HOST_CURL_FLAG[@]}" --max-time "$MCP_CALL_TIMEOUT" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -d "$body" "${BASE_URL}/mcp"
}

assert_contains() { # <label> <response> <needle>
    if ! printf '%s' "$2" | grep -qF -- "$3"; then
        echo "[mcp-e2e-smoke] ERROR: $1 — response does not contain: $3" >&2
        echo "[mcp-e2e-smoke] Response was: $2" >&2
        exit 1
    fi
    log "OK: $1"
}

# --- 1. tools/list --------------------------------------------------------------
TOOLS_RESPONSE="$(mcp_post 1 "tools/list" "{}")" \
    || fail "tools/list request failed"
assert_contains "tools/list returned a tool list" "$TOOLS_RESPONSE" '"tools"'

# --- 2. ingest_documents (fixture document) -------------------------------------
log "Ingesting the fixture document via ingest_documents..."
INGEST_RESPONSE="$(mcp_post 2 "tools/call" '{"name":"ingest_documents","arguments":{"path":"sample-document.md"}}')" \
    || fail "ingest_documents request failed"
assert_contains "ingest_documents returned the CLI ingest summary" "$INGEST_RESPONSE" 'ingest summary'

# --- 3. search (assert the fixture document comes back) --------------------------
log "Searching for the fixture content via search..."
SEARCH_RESPONSE="$(mcp_post 3 "tools/call" '{"name":"search","arguments":{"query":"Secondbrain semantic search embedding vectors Qdrant ingestion"}}')" \
    || fail "search request failed"
# Search results carry the source file and the chunk text of the fixture.
assert_contains "search returned chunks from the fixture document" "$SEARCH_RESPONSE" 'sample-document.md'
assert_contains "search returned chunk content" "$SEARCH_RESPONSE" 'chunk_text'

# --- 4. chat_send (gated) --------------------------------------------------------
if [ "$LLM_USABLE" = true ]; then
    log "LLM is configured; running the chat_send step..."
    CHAT_RESPONSE="$(mcp_post 4 "tools/call" '{"name":"chat_send","arguments":{"query":"What does the sample document say about semantic search?"}}')" \
        || fail "chat_send request failed"
    # Tool results are wrapped as a JSON string inside content[].text, so the
    # payload's quotes arrive escaped (\"session_id\"); normalize before the
    # assertions so both raw and wrapped forms match.
    CHAT_TEXT="$(printf '%s' "$CHAT_RESPONSE" | sed 's/\\"/"/g')"
    assert_contains "chat_send returned a session id" "$CHAT_TEXT" '"session_id"'
    # A non-empty answer: at least one character inside the JSON string value.
    if ! printf '%s' "$CHAT_TEXT" | grep -qE '"answer":"[^"]+"'; then
        echo "[mcp-e2e-smoke] ERROR: chat_send answer is empty" >&2
        echo "[mcp-e2e-smoke] Response was: $CHAT_RESPONSE" >&2
        exit 1
    fi
    log "OK: chat_send returned a non-empty answer bound to a session id"
else
    warn "no usable LLM configuration detected in the stack env (SECONDBRAIN_OPENAI_API_KEY/SECONDBRAIN_OPENAI_BASE_URL, or SECONDBRAIN_ANTHROPIC_API_KEY with SECONDBRAIN_LLM_PROVIDER=anthropic); skipping the chat_send step."
    warn "the rest of the smoke (health, tools/list, ingest, search) still validates."
fi

log "MCP end-to-end smoke passed for the $STACK stack."
