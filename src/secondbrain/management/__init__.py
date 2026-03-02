from secondbrain.storage import StorageConnectionError, VectorStorage
from secondbrain.utils.connections import ServiceUnavailableError


class Lister:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.storage = VectorStorage()

    def list_chunks(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        self._ensure_storage_available()

        return self.storage.list_chunks(
            source_filter=source_filter,
            chunk_id=chunk_id,
            limit=limit,
            offset=offset,
        )

    def _ensure_storage_available(self) -> None:
        from secondbrain.utils.connections import ensure_service_available

        ensure_service_available("MongoDB", self.storage.validate_connection)


class Deleter:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.storage = VectorStorage()

    def delete(
        self,
        source: str | None = None,
        chunk_id: str | None = None,
        all: bool = False,
    ) -> int:
        self._ensure_storage_available()

        if all:
            return self.storage.delete_all()

        if chunk_id:
            return self.storage.delete_by_chunk_id(chunk_id)

        if source:
            return self.storage.delete_by_source(source)

        return 0

    def _ensure_storage_available(self) -> None:
        from secondbrain.utils.connections import ensure_service_available

        ensure_service_available("MongoDB", self.storage.validate_connection)


class StatusChecker:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.storage = VectorStorage()

    def get_status(self) -> dict:
        self._ensure_storage_available()

        return self.storage.get_stats()

    def _ensure_storage_available(self) -> None:
        from secondbrain.utils.connections import ensure_service_available

        ensure_service_available("MongoDB", self.storage.validate_connection)
