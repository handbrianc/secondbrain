# Technical Configuration Guide

## MongoDB Configuration

### Connection URI
The MongoDB connection URI should be configured using the `SECONDBRAIN_MONGO_URI` environment variable.

Default value: `mongodb://localhost:27017`

Example configurations:
```bash
# Local MongoDB
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017

# MongoDB with authentication
SECONDBRAIN_MONGO_URI=mongodb://username:password@localhost:27017

# MongoDB Replica Set
SECONDBRAIN_MONGO_URI=mongodb://host1:27017,host2:27017,host3:27017/?replicaSet=rs0

# MongoDB Atlas
SECONDBRAIN_MONGO_URI=mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/
```

### Database and Collection
```bash
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=chunks
```

### Connection Timeout Settings
```bash
# Connection timeout in milliseconds
SECONDBRAIN_MONGO_CONNECT_TIMEOUT=5000

# Socket timeout in milliseconds
SECONDBRAIN_MONGO_SOCKET_TIMEOUT=10000

# Server selection timeout
SECONDBRAIN_MONGO_SERVER_SELECTION_TIMEOUT=30000
```

## Chunk Configuration

### Chunk Size
The default chunk size is 4096 tokens. This can be configured:

```bash
SECONDBRAIN_CHUNK_SIZE=4096
```

Recommended values:
- **2048** - For fine-grained search
- **4096** - Default, balanced
- **8192** - For broader context

### Chunk Overlap
Overlap between chunks to preserve context:

```bash
SECONDBRAIN_CHUNK_OVERLAP=200
```

Recommended values:
- **100** - Minimal overlap
- **200** - Default, good balance
- **500** - High overlap for better context

## Embedding Model Configuration

### Local Models
```bash
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
```

Supported models:
- `all-MiniLM-L6-v2` - Fast, good quality (default)
- `all-mpnet-base-v2` - Higher quality, slower
- `paraphrase-multilingual-MiniLM-L12-v2` - Multilingual support

### Embedding Cache
```bash
SECONDBRAIN_EMBEDDING_CACHE_ENABLED=true
SECONDBRAIN_EMBEDDING_CACHE_TTL=86400
```

## LLM Configuration

### Local LLM Server Configuration
```bash
SECONDBRAIN_LLM_PROVIDER=openai
SECONDBRAIN_OPENAI_BASE_URL=http://localhost:8080/v1
SECONDBRAIN_OPENAI_API_KEY=your-local-key
SECONDBRAIN_LLM_MODEL=local-model
SECONDBRAIN_LLM_TEMPERATURE=0.7
SECONDBRAIN_LLM_MAX_TOKENS=1024
```

### OpenAI Configuration
```bash
SECONDBRAIN_OPENAI_API_KEY=sk-...
SECONDBRAIN_OPENAI_MODEL=gpt-4
SECONDBRAIN_OPENAI_TEMPERATURE=0.7
```

## Security Configuration

### Circuit Breaker
```bash
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_THRESHOLD=5
SECONDBRAIN_CIRCUIT_BREAKER_RESET_TIMEOUT=60
```

### Rate Limiting
```bash
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_RATE_LIMIT_RPS=10
SECONDBRAIN_RATE_LIMIT_BURST=20
```

### Security Filter
The security filter blocks injection attacks:
- SQL injection patterns
- XSS injection patterns
- Command injection patterns
- Prototype pollution patterns

## Performance Tuning

### Worker Configuration
```bash
SECONDBRAIN_MAX_WORKERS=4
SECONDBRAIN_INGESTION_BATCH_SIZE=100
```

### Search Configuration
```bash
SECONDBRAIN_SEARCH_TOP_K=10
SECONDBRAIN_SEARCH_THRESHOLD=0.5
```

### Index Configuration
```bash
SECONDBRAIN_INDEX_READY_RETRY_COUNT=5
SECONDBRAIN_INDEX_READY_RETRY_DELAY=2.0
```

## Logging Configuration

### Log Level
```bash
SECONDBRAIN_LOG_LEVEL=INFO
```

Supported levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Log Format
```bash
SECONDBRAIN_LOG_FORMAT=pretty
```

Supported formats: pretty, json

### Log File
```bash
SECONDBRAIN_LOG_FILE=secondbrain.log
SECONDBRAIN_LOG_MAX_BYTES=10485760
SECONDBRAIN_LOG_BACKUP_COUNT=5
```

## Troubleshooting

### MongoDB Connection Issues
1. Verify MongoDB is running: `mongosh` or `docker ps`
2. Check connection URI format
3. Verify network connectivity
4. Check authentication credentials

### Index Not Found
1. Wait for index creation to complete
2. Check retry settings
3. Manually create index if needed

### Performance Issues
1. Increase worker count
2. Optimize chunk size
3. Enable embedding cache
4. Check MongoDB indexes
