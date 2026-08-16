"""MongoDB connection settings fragment for :class:`secondbrain.config.Config`."""

from pydantic import Field, field_validator


def _validate_mongo_uri(value: str) -> str:
    if not value.startswith("mongodb://") and not value.startswith("mongodb+srv://"):
        raise ValueError(
            f"mongo_uri must start with 'mongodb://' or 'mongodb+srv://', got: {value}"
        )
    return value


class MongoMixin:
    """MongoDB connection configuration."""

    mongo_uri: str = Field(
        default="mongodb://localhost:27017",
        description=(
            "MongoDB connection URI (override via SECONDBRAIN_MONGO_URI env var "
            "for production)"
        ),
    )

    @field_validator("mongo_uri")
    @classmethod
    def validate_mongo_uri(cls, v: str) -> str:
        """Validate MongoDB URI.

        Args:
            v: MongoDB URI to validate.

        Returns
        -------
            Validated URI string.
        """
        return _validate_mongo_uri(v)

    mongo_db: str = Field(
        default="secondbrain",
        description="Database name",
    )
    mongo_collection: str = Field(
        default="embeddings",
        description="Collection name for embeddings",
    )
