"""LLM provider and generation settings fragment."""

from pydantic import Field, field_validator


class LLMMixin:
    """LLM provider + generation settings."""

    llm_provider: str = Field(
        default="openai",
        description="LLM provider type (openai, anthropic)",
    )
    openai_base_url: str | None = Field(
        default=None,
        description=(
            "OpenAI-compatible API base URL (optional, defaults to OpenAI). Use for "
            "self-hosted endpoints like vLLM, LM Studio, Azure OpenAI, Groq, etc."
        ),
    )
    openai_api_key: str | None = Field(
        default=None,
        description=(
            "OpenAI-compatible API key (optional for self-hosted endpoints without "
            "auth). Defaults to SECONDBRAIN_OPENAI_API_KEY env var."
        ),
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Default LLM model for RAG",
    )
    llm_temperature: float = Field(
        default=0.1,
        description="LLM generation temperature (0.0-2.0)",
    )
    llm_max_tokens: int = Field(
        default=2048,
        description="Maximum tokens for LLM responses",
    )
    llm_timeout: int = Field(
        default=120,
        description="Request timeout in seconds for LLM",
    )

    @field_validator("llm_temperature")
    @classmethod
    def validate_llm_temperature(cls, v: float) -> float:
        """Validate LLM temperature is between 0.0 and 2.0."""
        if v < 0.0 or v > 2.0:
            raise ValueError("llm_temperature must be between 0.0 and 2.0")
        return v

    @field_validator("llm_max_tokens")
    @classmethod
    def validate_llm_max_tokens(cls, v: int) -> int:
        """Validate LLM max tokens is positive."""
        if v <= 0:
            raise ValueError("llm_max_tokens must be positive")
        return v

    @field_validator("llm_timeout")
    @classmethod
    def validate_llm_timeout(cls, v: int) -> int:
        """Validate LLM timeout is positive."""
        if v <= 0:
            raise ValueError("llm_timeout must be positive")
        return v
