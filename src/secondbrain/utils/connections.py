from typing import Callable


class ServiceUnavailableError(Exception):
    def __init__(self, service_name: str, message: str | None = None):
        super().__init__(message or f"{service_name} is unavailable")
        self.service_name = service_name


def ensure_service_available(service_name: str, validator: Callable[[], bool]) -> None:
    if not validator():
        raise ServiceUnavailableError(service_name)
