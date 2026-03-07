"""Exception hierarchy for secondbrain.

This module provides a hierarchical exception structure for better error
handling and categorization across the application.
"""


class SecondBrainError(Exception):
    """Base exception for all secondbrain errors."""

    ...


class ConfigError(SecondBrainError):
    """Raised when configuration issues occur."""

    ...


class ValidationError(SecondBrainError):
    """Raised when input validation fails."""

    ...


class ServiceError(SecondBrainError):
    """Raised when external service (Ollama, MongoDB) is unavailable."""

    ...


class StorageError(SecondBrainError):
    """Raised when database/storage operations fail."""

    ...


class DocumentExtractionError(SecondBrainError):
    """Raised when document extraction fails."""

    ...


class EmbeddingError(SecondBrainError):
    """Raised when embedding generation fails."""

    ...


class StorageConnectionError(SecondBrainError):
    """Raised when MongoDB connection cannot be established."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "Cannot connect to MongoDB")


class CLIValidationError(SecondBrainError):
    """Raised when CLI input validation fails."""

    ...


class UnsupportedFileError(SecondBrainError):
    """Raised when attempting to process an unsupported file type."""

    ...


class EmbeddingGenerationError(EmbeddingError):
    """Raised when embedding generation fails due to API or model errors."""

    ...


class OllamaUnavailableError(ServiceError):
    """Raised when Ollama service is unavailable or unreachable."""

    ...


class ServiceUnavailableError(ServiceError):
    """Raised when a service is unavailable."""

    service_name: str

    def __init__(self, service_name: str, message: str | None = None) -> None:
        super().__init__(message or f"{service_name} is unavailable")
        self.service_name = service_name
