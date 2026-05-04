# Configuration Reference

Complete configuration guide for SecondBrain CLI. All settings are environment variables prefixed with `SECONDBRAIN_`.

## Quick Start

Create a `.env` file in your project root:

```bash
# Essential settings
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_CHUNK_SIZE=4096
```

## Configuration Loading

SecondBrain uses Pydantic Settings to load configuration:

1. **Environment variables** (highest priority)
2. **`.env` file** in working directory
3. **Default values** (lowest priority)

Settings are case-insensitive and prefixed with `SECONDBRAIN_`.

---

## MongoDB Settings

### MongoDB Authentication (Required for Production)

For production deployments, MongoDB authentication should be enabled. See [MongoDB Authentication Setup](mongodb-authentication.md) for complete setup instructions.

### `SECONDBRAIN_MONGO_URI`
- **Type**: `str`
- **Default**: `mongodb://localhost:27017`
- **Required**: No (but MongoDB connection required for functionality)
- **Validation**: Must start with `mongodb://` or `mongodb+srv://`
- **Examples**:
  ```bash
  # Local MongoDB (no authentication - development only)
  SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
  
  # Local MongoDB (with authentication - recommended)
  SECONDBRAIN_MONGO_URI=mongodb://username:password@localhost:27017
  
  # MongoDB Atlas (cloud)
  SECONDBRAIN_MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true
  
  # With authentication database
  SECONDBRAIN_MONGO_URI=mongodb://user:pass@host:27017,host:27017/?authSource=admin
  ```

**⚠️ Special Characters in Passwords**: If your password contains `@`, `:`, `/`, `#`, `?`, or `&`, URL-encode them:
- `@` → `%40`
- `:` → `%3A`
- `/` → `%2F`
- `#` → `%23`
- `?` → `%3F`
- `&` → `%26`

Or use a `.env` file to avoid shell escaping issues.

### `SECONDBRAIN_MONGO_DB`
- **Type**: `str`
- **Default**: `secondbrain`
- **Description**: Database name for storing embeddings
- **Example**: `SECONDBRAIN_MONGO_DB=my_vector_db`

### `SECONDBRAIN_MONGO_COLLECTION`
- **Type**: `str`
- **Default**: `embeddings`
- **Description**: Collection name within the database
- **Example**: `SECONDBRAIN_MONGO_COLLECTION=document_chunks`

### Docker Environment Variables (for MongoDB Container)

These variables configure the MongoDB container in `docker-compose.yml`:

### `MONGODB_INITDB_ROOT_USERNAME`
- **Type**: `str`
- **Default**: `admin`
- **Description**: MongoDB admin username (set in `.env` file)
- **Required**: Yes, for new MongoDB installations with authentication
- **Example**: `MONGODB_INITDB_ROOT_USERNAME=secondbrain_admin`

### `MONGODB_INITDB_ROOT_PASSWORD`
- **Type**: `str`
- **Default**: `password`
- **Description**: MongoDB admin password (set in `.env` file)
- **Required**: Yes, for new MongoDB installations with authentication
- **Security**: Use strong passwords (16+ characters, mixed case, numbers, symbols)
- **Example**: `MONGODB_INITDB_ROOT_PASSWORD=SuperSecureP@ssw0rd123!`

**⚠️ Never commit `.env` files with credentials to version control!** Add `.env` to `.gitignore`.

---

## Embedding Settings

### `SECONDBRAIN_LOCAL_EMBEDDING_MODEL`
- **Type**: `str`
- **Default**: `all-MiniLM-L6-v2`
- **Description**: Sentence-transformers model for local embedding generation
- **Common Models**:
  | Model | Dimensions | Speed | Quality | Use Case |
  |-------|-----------|-------|---------|----------|
  | `all-MiniLM-L6-v2` | 384 | Fast | Good | General purpose, recommended |
  | `all-mpnet-base-v2` | 768 | Medium | Better | Higher quality |
  | `multi-qa-mpnet-base-dot-v1` | 768 | Medium | Better | QA tasks |

### `SECONDBRAIN_EMBEDDING_DIMENSIONS`
- **Type**: `int`
- **Default**: `384`
- **Description**: Vector dimensionality (must match selected model)
- **Note**: Must match the model's output dimensions

### `SECONDBRAIN_EMBEDDING_CACHE_SIZE`
- **Type**: `int`
- **Default**: `1000`
- **Description**: Maximum embeddings to cache in memory
- **Performance**: Reduces API calls for duplicate text

### `SECONDBRAIN_SENTENCE_TRANSFORMERS_URL`
- **Type**: `str`
- **Default**: `http://localhost:11434`
- **Description**: URL of the sentence-transformers API

---

## Processing Settings

### `SECONDBRAIN_CHUNK_SIZE`
- **Type**: `int`
- **Default**: `4096`
- **Description**: Size of text chunks for embedding
- **Range**: 512-8192 recommended
- **Trade-off**: Larger chunks = fewer embeddings but less precision

### `SECONDBRAIN_CHUNK_OVERLAP`
- **Type**: `int`
- **Default**: `200`
- **Description**: Overlap between consecutive chunks
- **Purpose**: Maintains context across chunk boundaries

### `SECONDBRAIN_MAX_WORKERS`
- **Type**: `int`
- **Default**: `4`
- **Description**: Number of parallel workers for ingestion
- **Performance**: Higher values = faster ingestion but more resources

---

## Rate Limiting & Resilience

### `SECONDBRAIN_RATE_LIMIT_ENABLED`
- **Type**: `bool`
- **Default**: `true`
- **Description**: Enable rate limiting for sentence-transformers API

### `SECONDBRAIN_RATE_LIMIT_REQUESTS_PER_SECOND`
- **Type**: `float`
- **Default**: `10.0`
- **Description**: Maximum requests per second

### `SECONDBRAIN_CIRCUIT_BREAKER_ENABLED`
- **Type**: `bool`
- **Default**: `true`
- **Description**: Enable circuit breaker pattern

### `SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD`
- **Type**: `int`
- **Default**: `5`
- **Description**: Failures before opening circuit

### `SECONDBRAIN_CIRCUIT_BREAKER_RECOVERY_TIMEOUT`
- **Type**: `float`
- **Default**: `60.0`
- **Description**: Seconds before attempting recovery (half-open state)

---

## Logging & Debugging

### `SECONDBRAIN_LOG_LEVEL`
- **Type**: `str`
- **Default**: `INFO`
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Description**: Logging verbosity level

### `SECONDBRAIN_LOG_FORMAT`
- **Type**: `str`
- **Default**: `pretty`
- **Options**: `pretty`, `json`
- **Description**: Log output format

### `SECONDBRAIN_VERBOSE`
- **Type**: `bool`
- **Default**: `false`
- **Description**: Enable verbose output (CLI flag alternative)

---

## Example .env File

```bash
# MongoDB Authentication (REQUIRED for production)
MONGODB_INITDB_ROOT_USERNAME=secondbrain_admin
MONGODB_INITDB_ROOT_PASSWORD=SuperSecureP@ssw0rd123!

# MongoDB Connection (must match credentials above)
SECONDBRAIN_MONGO_URI=mongodb://secondbrain_admin:SuperSecureP@ssw0rd123!@localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=embeddings

# Embedding Configuration
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_EMBEDDING_DIMENSIONS=384
SECONDBRAIN_EMBEDDING_CACHE_SIZE=1000
SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:11434

# Processing Configuration
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=200
SECONDBRAIN_MAX_WORKERS=4

# Rate Limiting
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_RATE_LIMIT_REQUESTS_PER_SECOND=10.0

# Circuit Breaker
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
SECONDBRAIN_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60.0

# Logging
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=pretty
SECONDBRAIN_VERBOSE=false
```

## Next Steps

- [Quick Start](quick-start.md) - Get started quickly
- [MongoDB Authentication Setup](mongodb-authentication.md) - Configure MongoDB authentication
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [Developer Guide](../developer-guide/configuration.md) - Advanced configuration
