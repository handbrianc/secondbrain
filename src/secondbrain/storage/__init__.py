"""Vector storage module for MongoDB integration."""

import logging
import time
from datetime import UTC, datetime
from typing import Any, TypedDict

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from secondbrain.config import Config, get_config

logger = logging.getLogger(__name__)


class StorageConnectionError(Exception):
    """Cannot connect to MongoDB."""

    pass


class SearchResult(TypedDict):
    chunk_id: str
    source_file: str
    page_number: int | None
    chunk_text: str
    score: float


class ChunkInfo(TypedDict):
    chunk_id: str
    source_file: str
    page_number: int | None
    chunk_text: str


class VectorStorage:
    """Handles vector storage in MongoDB."""

    def __init__(
        self,
        mongo_uri: str | None = None,
        db_name: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Initialize vector storage.

        Args:
            mongo_uri: Override MongoDB URI
            db_name: Override database name
            collection_name: Override collection name
        """
        config = get_config()
        self.mongo_uri: str = mongo_uri or config.mongo_uri
        self.db_name: str = db_name or config.mongo_db
        self.collection_name: str = collection_name or config.mongo_collection
        self._config: Config = config
        self._client: MongoClient[Any] | None = None
        self._db: Database[Any] | None = None
        self._collection: Collection[Any] | None = None
        self._index_created = False

    @property
    def client(self) -> MongoClient[Any]:
        """Get MongoDB client."""
        if self._client is None:
            self._client = MongoClient(self.mongo_uri, directConnection=True)
        return self._client

    @property
    def db(self) -> Database[Any]:
        """Get database instance."""
        if self._db is None:
            self._db = self.client[self.db_name]
        return self._db

    @property
    def collection(self) -> Collection[Any]:
        """Get collection instance."""
        if self._collection is None:
            self._collection = self.db[self.collection_name]
        return self._collection

    def validate_connection(self) -> bool:
        """Validate connection to MongoDB.

        Returns:
            bool: True if connection is valid
        """
        try:
            _ = self.client.admin.command("ping")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError):
            return False

    def ensure_index(self) -> None:
        """Create vector index if not exists."""
        if self._index_created:
            return

        try:
            from pymongo.operations import SearchIndexModel

            search_index_model = SearchIndexModel(
                definition={
                    "fields": [
                        {
                            "type": "vector",
                            "path": "embedding",
                            "numDimensions": self._config.embedding_dimensions,
                            "similarity": "cosine",
                        }
                    ]
                },
                name="embedding_index",
                type="vectorSearch",
            )
            _ = self.collection.create_search_index(model=search_index_model)
            self._index_created = True
            logger.info("Created vector index")
        except Exception as e:
            logger.warning(f"Could not create index: {e}")
            self._index_created = True

    def store(self, document: dict[str, Any]) -> str:
        """Store a document with embedding.

        Args:
            document: Document with chunk_id, text, embedding, metadata

        Returns:
            str: Stored document ID
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}"
            )

        # Add timestamp
        doc = document.copy()
        if "metadata" in doc and "ingested_at" in doc["metadata"]:
            doc["metadata"]["ingested_at"] = datetime.now(UTC).isoformat()

        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def store_batch(self, documents: list[dict[str, Any]]) -> int:
        """Store multiple documents.

        Args:
            documents: List of documents

        Returns:
            int: Number of documents stored
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}"
            )

        # Add timestamps
        now = datetime.now(UTC).isoformat()
        for doc in documents:
            if "metadata" in doc and "ingested_at" in doc["metadata"]:
                doc["metadata"]["ingested_at"] = now

        result = self.collection.insert_many(documents)
        return len(result.inserted_ids)

    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> list[SearchResult]:
        """Search for similar embeddings.

        Args:
            embedding: Query embedding vector
            top_k: Number of results
            source_filter: Filter by source file
            file_type_filter: Filter by file type

        Returns:
            list: Search results
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}"
            )

        # Ensure index exists and wait for it to be ready
        self.ensure_index()
        for _ in range(15):
            try:
                for idx in self.collection.list_search_indexes():
                    if (
                        idx.get("name") == "embedding_index"
                        and idx.get("status") == "READY"
                    ):
                        break
            except Exception:
                pass
            time.sleep(1)

        # Build filter
        query_filter: dict[str, Any] = {}
        if source_filter:
            query_filter["source_file"] = {"$regex": source_filter}
        if file_type_filter:
            query_filter["metadata.file_type"] = file_type_filter

        # Cosine similarity search
        # $vectorSearch must be the FIRST stage in the pipeline
        pipeline: list[dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "queryVector": embedding,
                    "path": "embedding",
                    "numCandidates": top_k * 10,
                    "limit": top_k,
                    "index": "embedding_index",
                }
            },
        ]

        # Apply filters AFTER vector search (cannot be in vectorSearch stage)
        if query_filter:
            pipeline.append({"$match": query_filter})

        pipeline.extend(
            [
                {
                    "$project": {
                        "chunk_id": 1,
                        "source_file": 1,
                        "page_number": 1,
                        "chunk_text": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]
        )

        results: list[SearchResult] = list(self.collection.aggregate(pipeline))
        return results

    def list_chunks(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChunkInfo]:
        """List chunks with optional filters.

        Args:
            source_filter: Filter by source file
            chunk_id: Filter by specific chunk ID
            limit: Max results
            offset: Pagination offset

        Returns:
            list: List of chunks
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}"
            )

        query: dict[str, Any] = {}
        if source_filter:
            query["source_file"] = {"$regex": source_filter}
        if chunk_id:
            query["chunk_id"] = chunk_id

        cursor = (
            self.collection.find(
                query,
                {
                    "_id": 0,
                    "chunk_id": 1,
                    "source_file": 1,
                    "page_number": 1,
                    "chunk_text": 1,
                },
            )
            .skip(offset)
            .limit(limit)
        )

        chunks: list[ChunkInfo] = list(cursor)
        return chunks

    def delete_by_source(self, source: str) -> int:
        """Delete all chunks from a source file.

        Args:
            source: Source file path

        Returns:
            int: Number of deleted documents
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}"
            )

        result = self.collection.delete_many({"source_file": source})
        return result.deleted_count

    def delete_by_chunk_id(self, chunk_id: str) -> int:
        """Delete a specific chunk.

        Args:
            chunk_id: Chunk ID

        Returns:
            int: Number of deleted documents
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}"
            )

        result = self.collection.delete_one({"chunk_id": chunk_id})
        return result.deleted_count

    def delete_all(self) -> int:
        """Delete all documents.

        Returns:
            int: Number of deleted documents
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}"
            )

        result = self.collection.delete_many({})
        return result.deleted_count

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            dict: Statistics
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}"
            )

        total = self.collection.count_documents({})
        unique_sources = len(self.collection.distinct("source_file"))

        return {
            "total_chunks": total,
            "unique_sources": unique_sources,
            "database": self.db_name,
            "collection": self.collection_name,
        }
