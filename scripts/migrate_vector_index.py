#!/usr/bin/env python3
"""Migration script to fix MongoDB vector index dimension mismatch.

This script drops the old 768-dimension vector index and recreates it
with the correct 384 dimensions to match the all-MiniLM-L6-v2 model.

Usage:
    python scripts/migrate_vector_index.py

Prerequisites:
    - MongoDB must be running and accessible
    - SECONDBRAIN_MONGO_URI environment variable should be set (or use default)
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pymongo import MongoClient
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_mongo_client(uri: str):
    """Create MongoDB client."""
    logger.info("Connecting to MongoDB at %s", uri)
    try:
        # Use directConnection=True to avoid replica set discovery issues
        client = MongoClient(uri, serverSelectionTimeoutMS=5000, directConnection=True)
        # Test connection
        client.admin.command("ping")
        logger.info("Successfully connected to MongoDB")
        return client
    except Exception as e:
        logger.error("Failed to connect to MongoDB: %s", e)
        raise


def check_index_dimensions(collection, index_name: str = "embedding_index"):
    """Check the dimensions of the existing vector index."""
    try:
        indexes = list(collection.list_search_indexes(index_name))
        if not indexes:
            logger.info("No existing vector index found")
            return None

        index = indexes[0]
        dimensions = (
            index.get("definition", {}).get("fields", [{}])[0].get("numDimensions")
        )
        status = index.get("status", "UNKNOWN")

        logger.info(
            "Found index '%s': dimensions=%s, status=%s",
            index_name,
            dimensions,
            status,
        )

        if dimensions is None:
            logger.warning(
                "Index exists but dimensions could not be read. Assuming mismatch."
            )
            return None

        return dimensions
    except Exception as e:
        logger.warning("Could not check index: %s", e)
        return None


def drop_index(collection, index_name: str = "embedding_index"):
    """Drop the existing vector index."""
    try:
        logger.info("Dropping index '%s'...", index_name)
        collection.drop_search_index(index_name)
        logger.info("Successfully dropped index '%s'", index_name)
        return True
    except OperationFailure as e:
        if "ns not found" in str(e) or "index not found" in str(e):
            logger.info("Index '%s' does not exist, skipping drop", index_name)
            return True
        logger.error("Failed to drop index: %s", e)
        raise
    except Exception as e:
        logger.error("Unexpected error dropping index: %s", e)
        raise


def create_index(
    collection, dimensions: int = 384, index_name: str = "embedding_index"
):
    """Create a new vector index with specified dimensions."""
    from pymongo.operations import SearchIndexModel

    search_index_model = SearchIndexModel(
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": dimensions,
                    "similarity": "cosine",
                }
            ]
        },
        name=index_name,
        type="vectorSearch",
    )

    logger.info("Creating new vector index with %d dimensions...", dimensions)
    try:
        index_id = collection.create_search_index(model=search_index_model)
        logger.info("Successfully created index with ID: %s", index_id)
        return True
    except Exception as e:
        logger.error("Failed to create index: %s", e)
        raise


def wait_for_index_ready(
    collection, index_name: str = "embedding_index", timeout: int = 60
):
    """Wait for the index to be ready."""
    import time

    logger.info("Waiting for index '%s' to be ready...", index_name)
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            indexes = list(collection.list_search_indexes(index_name))
            if indexes and indexes[0].get("status") == "READY":
                logger.info("Index '%s' is ready", index_name)
                return True
        except Exception:
            pass

        time.sleep(2)
        logger.debug("Index not ready yet...")

    logger.warning("Index may not be ready after %d seconds", timeout)
    return False


def count_documents(collection):
    """Count documents in the collection."""
    count = collection.count_documents({})
    logger.info("Collection contains %d documents", count)
    return count


def migrate_vector_index(
    mongo_uri: str,
    db_name: str = "secondbrain",
    collection_name: str = "embeddings",
    target_dimensions: int = 384,
    index_name: str = "embedding_index",
    force: bool = False,
    verbose: bool = False,
):
    """Run the migration to fix vector index dimensions.

    Args:
        mongo_uri: MongoDB connection URI
        db_name: Database name
        collection_name: Collection name
        target_dimensions: Target embedding dimensions (default: 384)
        index_name: Name of the vector index
        force: If True, drop and recreate even if dimensions match
        verbose: Enable debug logging
    """
    setup_logging(verbose)

    logger.info("=" * 60)
    logger.info("Vector Index Dimension Migration")
    logger.info("=" * 60)
    logger.info("Target dimensions: %d", target_dimensions)

    # Connect to MongoDB
    client = get_mongo_client(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]

    # Check document count
    doc_count = count_documents(collection)

    # Check existing index
    current_dims = check_index_dimensions(collection, index_name)

    if current_dims is None:
        # Index doesn't exist OR dimensions couldn't be read (likely mismatch)
        if not force:
            logger.info(
                "Index exists but dimensions unreadable. Use --force to recreate."
            )
            return
        logger.info("Dropping unreadable index and creating new one...")
        drop_index(collection, index_name)
        create_index(collection, target_dimensions, index_name)
        wait_for_index_ready(collection, index_name)
        logger.info("Migration complete!")
        return

    if current_dims == target_dimensions:
        if force:
            logger.info("Dimensions match but --force specified. Recreating index...")
            drop_index(collection, index_name)
            create_index(collection, target_dimensions, index_name)
            wait_for_index_ready(collection, index_name)
            logger.info("Migration complete!")
        else:
            logger.info(
                "Index already has correct dimensions (%d). Nothing to do.",
                target_dimensions,
            )
            logger.info("Use --force to recreate anyway.")
        return

    # Dimensions mismatch
    logger.error("DIMENSION MISMATCH DETECTED!")
    logger.error("Current index: %d dimensions", current_dims)
    logger.error("Target index: %d dimensions", target_dimensions)

    if doc_count > 0:
        logger.warning("Collection contains %d documents", doc_count)
        logger.warning(
            "WARNING: Dropping and recreating index will NOT affect documents"
        )
        logger.warning(
            "However, existing documents have embeddings with %d dimensions",
            current_dims,
        )
        logger.warning(
            "You may need to re-ingest documents to regenerate embeddings with %d dimensions",
            target_dimensions,
        )
        logger.warning("")
        logger.warning("Options:")
        logger.warning("1. Re-ingest all documents: secondbrain ingest <path>")
        logger.warning("2. Delete and re-add documents individually")
        logger.warning("")

    if not force:
        logger.info("Run with --force to proceed with index recreation")
        return

    # Proceed with migration
    logger.info("Dropping old index...")
    drop_index(collection, index_name)

    logger.info("Creating new index with %d dimensions...", target_dimensions)
    create_index(collection, target_dimensions, index_name)

    logger.info("Waiting for index to be ready...")
    wait_for_index_ready(collection, index_name)

    logger.info("=" * 60)
    logger.info("Migration complete!")
    logger.info("=" * 60)

    if doc_count > 0:
        logger.warning(
            "IMPORTANT: You have %d documents with old embeddings", doc_count
        )
        logger.warning("Consider re-ingesting documents to regenerate embeddings")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate MongoDB vector index to correct dimensions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic migration (drops old index, creates 384-dim index)
  python scripts/migrate_vector_index.py

  # Force recreation even if dimensions match
  python scripts/migrate_vector_index.py --force

  # Verbose output
  python scripts/migrate_vector_index.py --verbose

  # Custom MongoDB URI
  SECONDBRAIN_MONGO_URI=mongodb://localhost:27017 python scripts/migrate_vector_index.py
        """,
    )

    parser.add_argument(
        "--mongo-uri",
        default=None,
        help="MongoDB URI (default: from SECONDBRAIN_MONGO_URI env var or mongodb://localhost:27017)",
    )
    parser.add_argument(
        "--db-name",
        default="secondbrain",
        help="Database name (default: secondbrain)",
    )
    parser.add_argument(
        "--collection-name",
        default="embeddings",
        help="Collection name (default: embeddings)",
    )
    parser.add_argument(
        "--dimensions",
        type=int,
        default=384,
        help="Target embedding dimensions (default: 384)",
    )
    parser.add_argument(
        "--index-name",
        default="embedding_index",
        help="Vector index name (default: embedding_index)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force index recreation even if dimensions match",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Get MongoDB URI
    mongo_uri = args.mongo_uri
    if mongo_uri is None:
        import os

        mongo_uri = os.getenv("SECONDBRAIN_MONGO_URI", "mongodb://localhost:27017")

    try:
        migrate_vector_index(
            mongo_uri=mongo_uri,
            db_name=args.db_name,
            collection_name=args.collection_name,
            target_dimensions=args.dimensions,
            index_name=args.index_name,
            force=args.force,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        logger.info("\nMigration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error("\nMigration failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
