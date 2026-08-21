"""Vector storage factory — selects the backend from configuration.

Mirrors ``secondbrain.embedding.providers.factory.EmbeddingProviderFactory``:
a single ``create_from_config`` entry point returns the concrete storage
backend, so the 9 production construction sites swap to this one call.
"""

from typing import Any, cast

from secondbrain.config import config as get_config
from secondbrain.storage.protocol import VectorStorageProtocol
from secondbrain.storage.qdrant import QdrantVectorStorage


class StorageFactory:
    """Factory for :class:`~secondbrain.storage.protocol.VectorStorageProtocol`."""

    @staticmethod
    def create_from_config(
        cfg: Any | None = None,
    ) -> VectorStorageProtocol:
        """Create a vector storage backend from application config.

        Args:
            cfg: Optional :class:`secondbrain.config.Config`. Defaults to the
                process-wide singleton.

        Returns:
            A concrete :class:`VectorStorageProtocol` for the configured
            ``storage_backend`` (``qdrant`` default, or ``mock`` for fast
            in-memory tests).

        Raises:
            ValueError: If ``storage_backend`` is not recognized.
        """
        if cfg is None:
            cfg = get_config()
        backend = cfg.storage_backend.lower()

        if backend == "qdrant":
            return QdrantVectorStorage(
                url=cfg.qdrant_url,
                api_key=cfg.qdrant_api_key,
                collection_name=cfg.qdrant_collection,
            )
        if backend == "mock":
            from secondbrain.storage.mock import MockVectorStorage

            # MockVectorStorage predates the protocol and is used directly by
            # tests; at runtime it satisfies the methods those tests call, so
            # cast it for the typed factory contract.
            return cast(VectorStorageProtocol, MockVectorStorage())
        raise ValueError(f"Unknown storage_backend: {backend!r}")


__all__ = ["StorageFactory"]
