#!/usr/bin/env python3
"""Backfill migration script to add `element_type` field to MongoDB embeddings.

This script backfills `element_type: null` for historical documents that don't
have this field. New documents will have `element_type` populated during
ingestion.

The dual-read probe query relies on this field:
    {$or: [{element_type: {$in: [...]}}, {chunk_role: {...}}]}

With `element_type: null`, historical docs fall through to the `chunk_role`
clause, preserving backward compatibility.

Usage:
    # Dry run (default) - shows counts without updating
    python scripts/backfill_element_type.py

    # Execute the migration
    python scripts/backfill_element_type.py --execute

Environment Variables:
    SECONDBRAIN_MONGO_URI: MongoDB connection URI
    SECONDBRAIN_MONGO_DB: Database name (default: secondbrain)
    SECONDBRAIN_MONGO_COLLECTION: Collection name (default: embeddings)
"""

import argparse
import logging
import os
import sys

from pymongo import MongoClient

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
        client = MongoClient(uri, serverSelectionTimeoutMS=5000, directConnection=True)
        client.admin.command("ping")
        logger.info("Successfully connected to MongoDB")
        return client
    except Exception as e:
        logger.error("Failed to connect to MongoDB: %s", e)
        raise


def count_missing_field(collection) -> int:
    """Count documents missing the element_type field."""
    count = collection.count_documents({"element_type": {"$exists": False}})
    return count


def count_total_docs(collection) -> int:
    """Count total documents in collection."""
    return collection.count_documents({})


def backfill_element_type(
    mongo_uri: str,
    db_name: str = "secondbrain",
    collection_name: str = "embeddings",
    execute: bool = False,
    verbose: bool = False,
) -> dict:
    """Backfill `element_type: null` for documents missing the field.

    Args:
        mongo_uri: MongoDB connection URI
        db_name: Database name
        collection_name: Collection name
        execute: If True, perform the update; if False, dry-run only
        verbose: Enable debug logging

    Returns:
        Dict with counts: total, missing_before, modified, missing_after
    """
    setup_logging(verbose)

    logger.info("=" * 60)
    logger.info("Element Type Backfill Migration")
    logger.info("=" * 60)
    if not execute:
        logger.info("DRY-RUN MODE: No changes will be made")

    client = None
    try:
        client = get_mongo_client(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]

        total = count_total_docs(collection)
        missing_before = count_missing_field(collection)

        logger.info("Collection: %s.%s", db_name, collection_name)
        logger.info("Total documents: %d", total)
        logger.info("Documents missing element_type: %d", missing_before)

        if missing_before == 0:
            logger.info("All documents already have element_type field. Nothing to do.")
            return {
                "total": total,
                "missing_before": missing_before,
                "modified": 0,
                "missing_after": 0,
            }

        if not execute:
            logger.info("")
            logger.info("Would set element_type=null for %d documents", missing_before)
            logger.info("Run with --execute to apply the changes")
            return {
                "total": total,
                "missing_before": missing_before,
                "modified": 0,
                "missing_after": missing_before,
            }

        # Execute the migration
        logger.info("")
        logger.info("Applying backfill...")

        result = collection.update_many(
            {"element_type": {"$exists": False}},
            {"$set": {"element_type": None}},
        )

        modified = result.modified_count
        missing_after = count_missing_field(collection)

        logger.info("Documents modified: %d", modified)
        logger.info("Documents still missing element_type: %d", missing_after)

        if missing_after != 0:
            logger.warning(
                "Expected 0 documents still missing element_type, got %d",
                missing_after,
            )

        return {
            "total": total,
            "missing_before": missing_before,
            "modified": modified,
            "missing_after": missing_after,
        }

    finally:
        if client is not None:
            client.close()


def main():
    """Execute the backfill migration from CLI."""
    parser = argparse.ArgumentParser(
        description="Backfill element_type field in MongoDB embeddings collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Safety Behavior:
    This script runs in DRY-RUN mode by default. Use --execute to apply changes.

Examples:
  # Dry run - shows what would be changed
  python scripts/backfill_element_type.py

  # Dry run with verbose output
  python scripts/backfill_element_type.py --verbose

  # Actually execute the migration
  python scripts/backfill_element_type.py --execute

  # Custom MongoDB connection
  SECONDBRAIN_MONGO_URI='mongodb://user:pass@localhost:27017' \\
      python scripts/backfill_element_type.py --execute
        """,
    )

    parser.add_argument(
        "--mongo-uri",
        default=None,
        help="MongoDB URI (default: SECONDBRAIN_MONGO_URI env var)",
    )
    parser.add_argument(
        "--db-name",
        default=None,
        help="Database name (default: SECONDBRAIN_MONGO_DB env var or 'secondbrain')",
    )
    parser.add_argument(
        "--collection-name",
        default=None,
        help=(
            "Collection name "
            "(default: SECONDBRAIN_MONGO_COLLECTION env var or 'embeddings')"
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the migration (default is dry-run)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Get MongoDB connection params from env or CLI
    mongo_uri = args.mongo_uri or os.getenv("SECONDBRAIN_MONGO_URI", "")
    db_name = args.db_name or os.getenv("SECONDBRAIN_MONGO_DB", "secondbrain")
    collection_name = (
        args.collection_name or os.getenv("SECONDBRAIN_MONGO_COLLECTION", "embeddings")
    )

    if not mongo_uri:
        print(
            "ERROR: SECONDBRAIN_MONGO_URI environment variable or --mongo-uri argument is required.\n"
            "Example: SECONDBRAIN_MONGO_URI='mongodb://user:pass@localhost:27017/db' \\\n"
            "    python scripts/backfill_element_type.py",
            file=sys.stderr,
        )
        sys.exit(1)

    # Safety check: require --execute in non-CI environments
    ci_mode = os.getenv("CI", "").lower() in ("true", "1", "yes")
    if not args.execute and not ci_mode:
        print(
            "\n"
            + "=" * 60 + "\n"
            " WARNING: This is a LIVE database mutation!\n"
            " Running in DRY-RUN mode by default.\n"
            " Use --execute to apply changes.\n"
            + "=" * 60 + "\n",
            file=sys.stderr,
        )

    try:
        result = backfill_element_type(
            mongo_uri=mongo_uri,
            db_name=db_name,
            collection_name=collection_name,
            execute=args.execute,
            verbose=args.verbose,
        )

        # Summary output
        logger.info("")
        logger.info("=" * 60)
        logger.info("Summary")
        logger.info("=" * 60)
        logger.info("Total documents: %d", result["total"])
        logger.info("Missing element_type before: %d", result["missing_before"])

        if args.execute:
            logger.info("Modified: %d", result["modified"])
            logger.info("Missing element_type after: %d", result["missing_after"])

            if result["missing_after"] == 0 and result["modified"] > 0:
                logger.info("Backfill completed successfully!")

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\nMigration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error("\nMigration failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
