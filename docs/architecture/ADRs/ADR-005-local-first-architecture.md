# ADR-005: Local-First Architecture

**Status**: Accepted  
**Created**: 2026-03-30  
**Authors**: SecondBrain Team  
**Deciders**: Architecture Team

## Context

SecondBrain is designed for users who prioritize data privacy and control. Requirements include:

- All data must remain on user's machine
- No external API calls for core functionality
- No telemetry or analytics without explicit consent
- Offline operation must be fully functional
- Users control where data is stored

## Decision

**Adopt a strict local-first architecture** with the following principles:

### Core Principles

1. **Everything Local**: All processing happens on user's machine:
   - Document parsing (Docling)
   - Embedding generation (sentence-transformers)
   - Vector storage (MongoDB)
   - Search and retrieval

2. **No Cloud Dependencies**: No external API calls for:
   - Document processing
   - Embedding generation
   - Search operations
   - Data storage

3. **Optional Cloud Features**: Any cloud features are:
   - Explicitly opt-in
   - Clearly documented
   - Never required for core functionality

4. **Data Ownership**: Users have full control:
   - Choose storage location
   - Export data in standard formats
   - Delete data completely
   - No vendor lock-in

### Architecture Boundaries

```
┌─────────────────────────────────────┐
│         User's Machine              │
│  ┌─────────────────────────────┐   │
│  │  Document Processing        │   │
│  │  - PDF/DOCX Parsing         │   │
│  │  - Text Extraction          │   │
│  │  - Chunking                 │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │  Embedding Generation       │   │
│  │  - Sentence Transformers    │   │
│  │  - Local GPU/CPU            │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │  Vector Database            │   │
│  │  - MongoDB (local)          │   │
│  │  - Data files on disk       │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │  Search & Retrieval         │   │
│  │  - Semantic Search          │   │
│  │  - RAG Pipeline             │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
           NO EXTERNAL CALLS
```

### Network Isolation

The application can run in a completely air-gapped environment:

```bash
# Verify no network calls
sudo tcpdump -i any port 80 or port 443 &
python -m secondbrain ingest document.pdf
python -m secondbrain search "query"
# No network traffic observed
```

### Configuration

```python
# All data paths are local
MONGODB_URI=mongodb://localhost:27017  # Local MongoDB
DATA_DIR=~/.secondbrain                # Local storage
EMBEDDING_MODEL=sentence-transformers/...  # Local model
```

## Consequences

### Positive

- **Privacy**: No data leaves user's machine
- **Security**: Reduced attack surface (no network exposure)
- **Reliability**: Works offline, no service dependency
- **Cost**: No API fees or cloud costs
- **Control**: Full ownership of data and infrastructure

### Negative

- **Resource Requirements**: User must provide compute/storage
- **Setup Complexity**: Requires local MongoDB, Python environment
- **No Managed Service**: User responsible for maintenance
- **Scalability Limits**: Limited by local hardware

### Risks

- **Data Loss**: User responsible for backups
- **Hardware Failure**: No cloud redundancy
- **Version Updates**: User must manually update

## Data Flow

```
User Document
    ↓
[Local File System]
    ↓
[Local Document Parser]
    ↓
[Local Embedding Model]
    ↓
[Local MongoDB]
    ↓
[Local Search Results]
    ↓
User Terminal
```

## Compliance

This architecture supports:

- **GDPR**: Data stays in user's jurisdiction
- **HIPAA**: No data transmission over networks
- **SOC 2**: Full control over data access
- **Enterprise**: Can run in isolated networks

## Alternatives Considered

### 1. Hybrid (Local + Cloud)
**Pros**: Scalability, managed backups  
**Cons**: Data leaves machine, privacy concerns, ongoing costs

### 2. Cloud-Only
**Pros**: Zero setup, automatic scaling  
**Cons**: No data control, privacy issues, vendor lock-in

### 3. Peer-to-Peer Sync
**Pros**: Decentralized, user control  
**Cons**: Complexity, security risks, inconsistent state

## Testing

To verify local-only operation:

```bash
# 1. Disconnect network
sudo ifconfig en0 down

# 2. Run SecondBrain
python -m secondbrain ingest document.pdf
python -m secondbrain search "query"

# 3. Verify success
# Should work without network
```

## References

- [Local-First Software Principles](https://www.localfirstweb.dev/)
- ADR-002: MongoDB Vector Storage
- ADR-003: Async Architecture
