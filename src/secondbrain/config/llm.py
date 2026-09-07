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
        default=0.3,
        description="LLM generation temperature (0.0-2.0)",
    )
    llm_top_p: float = Field(
        default=0.95,
        description="LLM nucleus-sampling top_p (0.0-1.0).",
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
    llm_reasoning_effort: str | None = Field(
        default=None,
        description=(
            "Optional reasoning-effort hint for reasoning models, sent as "
            "`reasoning_effort` in the request body to OpenAI-compatible "
            "endpoints. Proxies like LiteLLM map it to the model's thinking "
            "controls; endpoints that do not support it ignore or reject it "
            "(unset the variable in that case). One of minimal, low, medium, "
            "high. Unset omits the parameter entirely, leaving the model's "
            "default reasoning behavior."
        ),
    )
    llm_max_tokens: int = Field(
        default=384000,
        description="Maximum tokens for LLM responses",
    )
    llm_max_answer_chars: int = Field(
        default=24000,
        description=(
            "Bounded maximum length of the answer (content) text streamed per "
            "response. Healthily accommodates long multi-paragraph overviews "
            "(e.g. a full chapter summary quoting every source figure); a runaway "
            "generator (e.g. a model endlessly re-verifying exact figures in its "
            "own prose) is cut here and a clean sentence-ending prefix returned. "
            "0 disables the bound."
        ),
    )
    llm_timeout: int = Field(
        default=120,
        description="Request timeout in seconds for LLM",
    )
    llm_stream_idle_timeout_seconds: int = Field(
        default=600,
        description=(
            "Bounded wait (seconds) for the next streamed token before aborting "
            "the response, preventing an indefinite hang when the server stops "
            "sending mid-output. Counts only wall-clock silence (no content or "
            "reasoning token arriving), so normal slow reasoning is unaffected. "
            "Heavy-reasoning models can fall silent for minutes mid-answer while "
            "deliberating server-side (those pauses emit no tokens at all), so "
            "keep this generous: a 120s bound silently truncated GLM chapter "
            "summaries mid-sentence and dropped whole windows. 0 disables the "
            "bound (legacy unlimited behavior)."
        ),
    )

    @field_validator("llm_temperature")
    @classmethod
    def validate_llm_temperature(cls, v: float) -> float:
        """Validate LLM temperature is between 0.0 and 2.0."""
        if v < 0.0 or v > 2.0:
            raise ValueError("llm_temperature must be between 0.0 and 2.0")
        return v

    @field_validator("llm_top_p")
    @classmethod
    def validate_llm_top_p(cls, v: float) -> float:
        """Validate top_p is between 0.0 and 1.0."""
        if v < 0.0 or v > 1.0:
            raise ValueError("llm_top_p must be between 0.0 and 1.0")
        return v

    @field_validator("llm_repetition_penalty")
    @classmethod
    def validate_llm_repetition_penalty(cls, v: float) -> float:
        """Validate LLM repetition penalty is >= 1.0."""
        if v < 1.0:
            raise ValueError("llm_repetition_penalty must be >= 1.0")
        return v

    @field_validator("llm_reasoning_effort")
    @classmethod
    def validate_llm_reasoning_effort(cls, v: str | None) -> str | None:
        """Validate reasoning effort is one of the supported levels.

        An empty value (e.g. a blank `SECONDBRAIN_LLM_REASONING_EFFORT=` line)
        is treated as unset so the parameter is simply omitted.
        """
        if v is None:
            return v
        normalized = v.strip().lower()
        if not normalized:
            return None
        allowed = {"minimal", "low", "medium", "high"}
        if normalized not in allowed:
            raise ValueError(
                "llm_reasoning_effort must be one of: minimal, low, medium, high"
            )
        return normalized

    @field_validator("llm_max_tokens")
    @classmethod
    def validate_llm_max_tokens(cls, v: int) -> int:
        """Validate LLM max tokens is positive."""
        if v <= 0:
            raise ValueError("llm_max_tokens must be positive")
        return v

    @field_validator("llm_max_answer_chars")
    @classmethod
    def validate_llm_max_answer_chars(cls, v: int) -> int:
        """Validate LLM max answer chars is non-negative (0 disables)."""
        if v < 0:
            raise ValueError("llm_max_answer_chars must be >= 0")
        return v

    @field_validator("llm_timeout")
    @classmethod
    def validate_llm_timeout(cls, v: int) -> int:
        """Validate LLM timeout is positive."""
        if v <= 0:
            raise ValueError("llm_timeout must be positive")
        return v

    @field_validator("llm_stream_idle_timeout_seconds")
    @classmethod
    def validate_llm_stream_idle_timeout_seconds(cls, v: int) -> int:
        """Validate LLM stream idle timeout is non-negative (0 disables)."""
        if v < 0:
            raise ValueError("llm_stream_idle_timeout_seconds must be >= 0")
        return v
