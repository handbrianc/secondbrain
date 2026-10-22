# Dockerfile for the Secondbrain container image.
#
# Multi-stage build:
#   1. `mcp-builder` (rust:1-slim)  — compiles the `secondbrain-mcp` MCP server binary
#   2. `runtime` (python:3.14-slim) — installs the `secondbrain` CLI from the repository
#      source and copies the server binary on top. The MCP server is the image's
#      primary function; the CLI tooling it drives ships alongside it.
#
# The image bakes no endpoint addresses, API keys, or model names: every
# SECONDBRAIN_* variable is settable at docker run / compose time (the compose
# contract lives in .env.docker).

# --- Stage 1: build the secondbrain-mcp server binary -------------------------
FROM rust:1-slim AS mcp-builder

# aws-lc-sys — the rustls crypto provider pulled in by axum-server's
# `tls-rustls` feature — builds AWS-LC through CMake, and the base image ships
# only gcc/libc-dev. CMake is the only extra native tool needed (aws-lc-sys
# uses AWS-LC's pregenerated build files, so Perl/Go are not required).
RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Manifests first, so the locked dependency graph compiles once and is cached
# between source edits. `--locked` refuses to build against a stale Cargo.lock.
COPY mcp-server/Cargo.toml mcp-server/Cargo.lock ./
RUN mkdir -p src && echo "fn main() {}" > src/main.rs
RUN cargo build --release --locked

# Real sources: only the crate itself recompiles from here.
COPY mcp-server/src ./src
RUN touch src/main.rs && cargo build --release --locked

# --- Stage 2: runtime (MCP server default + secondbrain CLI) -------------------
FROM python:3.14-slim AS runtime

# README.md backs pyproject.toml's `readme` field for the wheel build.
COPY README.md pyproject.toml ./
COPY src/ ./src/
# Runtime dependencies only — the dev extras (lint/test tooling) stay out.
#
# torch (and torchvision) come from the CPU wheel index: the container has no
# GPU access (the compose contract passes no devices through), so the CUDA
# runtime wheels that PyPI's torch pulls in on Linux (~2.5 GB download, ~10 GB
# unpacked) are dead weight — and on small hosts they alone can exhaust the
# build disk. Pre-installing the CPU builds satisfies docling-slim's
# `torch>=2.2.2,<3` / `torchvision<1,>=0` pins, so the install below leaves
# them untouched.
#
# The constraints file pins the docling family to the versions uv.lock
# resolves, so the image parses PDFs exactly like the locked development
# environment instead of floating to whatever docling PyPI serves today.
# Keep the pins in sync when uv.lock is regenerated.
RUN printf 'docling==2.141.0\ndocling-core==2.101.1\ndocling-slim==2.141.0\ndocling-parse==7.22.3\npypdfium2==5.14.0\n' > /tmp/constraints.txt \
    && pip install --no-cache-dir torch torchvision \
      --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -c /tmp/constraints.txt .

# gosu: the entrypoint starts as root only to hand writable staging
# directories to the runtime user (see scripts/docker_entrypoint.sh), then
# re-execs the command as that user — the server and CLI never run as root.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# The MCP server binary, on PATH next to the `secondbrain` CLI script that pip
# installs into /usr/local/bin.
COPY --from=mcp-builder /build/target/release/secondbrain-mcp /usr/local/bin/secondbrain-mcp

# Startup wrapper (see scripts/docker_entrypoint.sh): hands writable staging
# directories to the runtime user, then drops privileges before exec'ing.
COPY scripts/docker_entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

# Non-root runtime user.
RUN useradd --create-home app

# Data directories, pre-created and owned by the runtime user: when a fresh
# named volume is mounted at /data/secondbrain (as the compose stack does for
# SQLite storage), Docker copies the image directory — including its
# ownership — into the empty volume, so the non-root server can create its
# database file there.
RUN mkdir -p /data/secondbrain /data/workspace/uploads \
    && chown -R app:app /data

WORKDIR /data/workspace

# Image defaults for the server's own settings; every value remains
# overridable at run time (the compose contract lives in .env.docker).
ENV SECONDBRAIN_MCP_HTTP_BIND_ADDR=0.0.0.0:8080 \
    SECONDBRAIN_MCP_WORKSPACE_ROOT=/data/workspace \
    SECONDBRAIN_SQLITE_PATH=/data/secondbrain/secondbrain.db

EXPOSE 8080

# HEALTHCHECK against the server's own health endpoint, via the Python stdlib
# (the slim base ships no curl/wget). Probes plaintext HTTP by design;
# deployments that enable SECONDBRAIN_MCP_HTTP_TLS_ENABLED should override the
# healthcheck in compose to match (e.g. an https probe that skips local
# certificate verification).
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"

# The container may start as root only for the entrypoint's ownership
# handover (scripts/docker_entrypoint.sh), which re-execs the command as the
# non-root runtime user before the server or CLI runs. Rootless launches
# (`docker run --user`, Kubernetes runAsNonRoot) skip the handover.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# The MCP server by default; the CLI via `docker run --rm <image> secondbrain ...`.
CMD ["secondbrain-mcp"]
