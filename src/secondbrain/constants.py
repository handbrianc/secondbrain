"""Constants for secondbrain CLI.

This module defines all magic numbers and configuration defaults
to improve maintainability and clarity.
"""

# CLI Constants
MAX_LIST_LIMIT = 100000  # Maximum number of results for list command

# Search Constants
DEFAULT_MIN_SIMILARITY_THRESHOLD = (
    0.46  # Minimum score for search results (lowered for better recall)
)
DEFAULT_TOP_K = 5  # Default number of search results

# Document Processing Constants
DEFAULT_CHUNK_SIZE = 4096  # Default chunk size in characters
DEFAULT_CHUNK_OVERLAP = 50  # Default chunk overlap in characters
DEFAULT_BATCH_SIZE = 10  # Default batch size for ThreadPoolExecutor
MAX_MEMORY_BATCH_SIZE = 100  # Maximum chunks to process in memory (~150MB RAM)

# Embedding Constants
DEFAULT_EMBEDDING_DIMENSIONS = 384  # Default embedding dimensions (all-MiniLM-L6-v2)
DEFAULT_EMBEDDING_CACHE_SIZE = 1000  # Default embedding cache size
DEFAULT_EMBEDDING_BATCH_SIZE = 20  # Default batch size for embedding generation
MIN_EMBEDDING_BATCH_SIZE = 1  # Minimum embedding batch size
MAX_EMBEDDING_BATCH_SIZE = 100  # Maximum embedding batch size

# Streaming Constants
DEFAULT_STREAMING_CHUNK_BATCH_SIZE = 50  # Default streaming chunk batch size
MIN_STREAMING_CHUNK_BATCH_SIZE = 1  # Minimum streaming batch size
MAX_STREAMING_CHUNK_BATCH_SIZE = 200  # Maximum streaming batch size

# Rate Limiting Constants
DEFAULT_RATE_LIMIT_MAX_REQUESTS = 10  # Default max requests per window
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 1.0  # Default rate limit window

# Connection Constants
DEFAULT_CONNECTION_CACHE_TTL = 60.0  # Default connection cache TTL in seconds
DEFAULT_INDEX_READY_RETRY_COUNT = 15  # Default retry count for index ready check
DEFAULT_INDEX_READY_RETRY_DELAY = 1.0  # Default initial retry delay

# File Processing Constants
DEFAULT_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # Default max file size (100MB)
DEFAULT_FILE_PROCESSING_TIMEOUT = 3600  # Default file processing timeout (1 hour)
DEFAULT_RESULT_RETRIEVAL_TIMEOUT = 300  # Default result retrieval timeout (5 minutes)

# Pooling Constants
DEFAULT_MAX_POOL_SIZE = 50  # Default MongoDB max pool size
DEFAULT_MIN_POOL_SIZE = 10  # Default MongoDB min pool size
DEFAULT_MAX_IDLE_TIME_MS = 300000  # Default max idle time (5 minutes)
DEFAULT_WAIT_QUEUE_TIMEOUT_MS = 5000  # Default wait queue timeout (5 seconds)
DEFAULT_SERVER_SELECTION_TIMEOUT_MS = (
    5000  # Default server selection timeout (5 seconds)
)

# Circuit Breaker Constants
DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5  # Default failure threshold
DEFAULT_CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2  # Default success threshold
DEFAULT_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30.0  # Default recovery timeout (seconds)
DEFAULT_CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS = 3  # Default half-open max calls
