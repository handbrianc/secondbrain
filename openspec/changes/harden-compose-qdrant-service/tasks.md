# Harden Compose Qdrant Service — Tasks

## 1. Service changes

- [x] 1.1 In `docker-compose.yml` qdrant block: add `healthcheck` (Qdrant native health endpoint via its own binary/wget, per the image's tooling), keep the named volume `qdrant-data:/qdrant/storage`, keep the bridge network, move `ports: ["6333:6333"]` into a commented block with an explanatory note

## 2. Tests proving the unit of work

- [x] 2.1 `docker compose config --quiet` passes
- [x] 2.2 Bring-up check: `docker compose up -d qdrant` → healthcheck reaches healthy; `docker compose port qdrant 6333` prints nothing (no publish); recreate the container and confirm volume data persists
