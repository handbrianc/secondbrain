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
    llm_summary_temperature: float = Field(
        default=0.7,
        description=(
            "Temperature for chapter/section summary window generation (0.0-2.0). "
            "Independent of ``llm_temperature``: long comprehensive summaries are "
            "more prone to degenerate into word-salad at high temperature, so a "
            "lower value here keeps them stable while leaving general chat sampling "
            "untouched."
        ),
    )
    llm_repetition_penalty: float = Field(
        default=1.0,
        description=(
            "Repetition penalty for generation (>= 1.0). Values above 1.0 discourage "
            "the model from repeating itself (e.g. 1.1-1.3). 1.0 disables it. Sent as "
            "`repetition_penalty` for OpenAI-compatible servers that support it "
            "(DeepSeek, vLLM, TGI); ignored by servers that don't."
        ),
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

    @field_validator("llm_summary_temperature")
    @classmethod
    def validate_llm_summary_temperature(cls, v: float) -> float:
        """Validate the summary temperature is between 0.0 and 2.0."""
        if v < 0.0 or v > 2.0:
            raise ValueError("llm_summary_temperature must be between 0.0 and 2.0")
        return v

    @field_validator("llm_repetition_penalty")
    @classmethod
    def validate_llm_repetition_penalty(cls, v: float) -> float:
        """Validate LLM repetition penalty is >= 1.0."""
        if v < 1.0:
            raise ValueError("llm_repetition_penalty must be >= 1.0")
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
