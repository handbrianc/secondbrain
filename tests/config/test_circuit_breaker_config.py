"""Tests for the circuit-breaker resilience settings and their wiring.

Covers ``src/secondbrain/config/resilience.py`` (fields, validators, the
``circuit_breaker_config_from_config`` builder) and the production wiring that
consumes it:

- ``StorageFactory`` wires ``QdrantVectorStorage`` with a circuit breaker when
  the config enables it (default ON in production);
- ``EmbeddingProviderFactory`` wires ``OpenAIEmbeddingProvider`` the same way;
- ``ConversationStorage`` (a ``ValidatableService``) receives the config-built
  ``CircuitBreakerConfig``;
- an OPEN circuit degrades gracefully on each service's connection-validation
  path, consistent with that path's existing error semantics.

All tests run under the ``isolate_config_env`` fixture (no SECONDBRAIN_* env
vars, no dotenv in cwd, fresh ``get_config`` cache). Under pytest the
``Config`` test-env defaults force ``circuit_breaker_enabled`` to ``False``
when the key is unset, so tests that exercise the enabled wiring set the env
var (or pass an explicit kwarg) first.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from secondbrain.config import Config, get_config
from secondbrain.config.resilience import circuit_breaker_config_from_config
from secondbrain.conversation.storage_sqlite import ConversationStorage
from secondbrain.embedding.providers.factory import EmbeddingProviderFactory
from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider
from secondbrain.storage.factory import StorageFactory
from secondbrain.storage.qdrant import QdrantVectorStorage
from secondbrain.utils.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
)


def make_config(**kwargs: Any) -> Config:
    """Build a Config from explicit kwargs only (env/dotenv isolated)."""
    return Config(**kwargs)


class TestCircuitBreakerDefaults:
    """Field defaults from config/resilience.py."""

    def test_circuit_breaker_enabled_defaults_on_in_production(self):
        """The shipped field default is ON (production decision)."""
        assert Config.model_fields["circuit_breaker_enabled"].default is True

    def test_threshold_and_timeout_defaults(self):
        config = make_config()

        assert config.circuit_breaker_failure_threshold == 5
        assert config.circuit_breaker_success_threshold == 2
        assert config.circuit_breaker_recovery_timeout == 30.0

    def test_circuit_breaker_disabled_by_default_under_pytest(self):
        """The test-env default forces the breaker off when unset."""
        config = make_config()

        assert config.circuit_breaker_enabled is False

    def test_bool_env_var_parsing(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_ENABLED", "true")
        assert make_config().circuit_breaker_enabled is True

        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_ENABLED", "false")
        assert make_config().circuit_breaker_enabled is False

    def test_env_vars_map_thresholds_and_timeout(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3")
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_SUCCESS_THRESHOLD", "1")
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "45.5")

        config = make_config()

        assert config.circuit_breaker_failure_threshold == 3
        assert config.circuit_breaker_success_threshold == 1
        assert config.circuit_breaker_recovery_timeout == 45.5


class TestCircuitBreakerValidation:
    """Validators reject non-positive circuit breaker settings."""

    @pytest.mark.parametrize("value", [0, -1, -5])
    def test_failure_threshold_must_be_positive(self, value):
        with pytest.raises(
            ValidationError, match="circuit breaker thresholds must be positive"
        ):
            make_config(circuit_breaker_failure_threshold=value)

    @pytest.mark.parametrize("value", [0, -1, -5])
    def test_success_threshold_must_be_positive(self, value):
        with pytest.raises(
            ValidationError, match="circuit breaker thresholds must be positive"
        ):
            make_config(circuit_breaker_success_threshold=value)

    @pytest.mark.parametrize("value", [0, -1.0, -30.0])
    def test_recovery_timeout_must_be_positive(self, value):
        with pytest.raises(
            ValidationError, match="circuit_breaker_recovery_timeout must be positive"
        ):
            make_config(circuit_breaker_recovery_timeout=value)

    def test_smallest_positive_values_accepted(self):
        config = make_config(
            circuit_breaker_failure_threshold=1,
            circuit_breaker_success_threshold=1,
            circuit_breaker_recovery_timeout=0.001,
        )

        assert config.circuit_breaker_failure_threshold == 1
        assert config.circuit_breaker_success_threshold == 1
        assert config.circuit_breaker_recovery_timeout == 0.001


class TestCircuitBreakerConfigBuilder:
    """``circuit_breaker_config_from_config`` conversion rules."""

    def test_returns_none_when_disabled(self):
        config = make_config(circuit_breaker_enabled=False)

        assert circuit_breaker_config_from_config(config) is None

    def test_returns_default_breaker_when_enabled(self):
        config = make_config(circuit_breaker_enabled=True)

        assert circuit_breaker_config_from_config(config) == CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            recovery_timeout=30.0,
        )

    def test_maps_custom_values(self):
        config = make_config(
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=3,
            circuit_breaker_success_threshold=1,
            circuit_breaker_recovery_timeout=45.5,
        )

        assert circuit_breaker_config_from_config(config) == CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=1,
            recovery_timeout=45.5,
        )

    def test_falls_back_to_defaults_for_partial_stubs(self):
        """Stubs setting only the flag still build a default breaker."""
        stub = SimpleNamespace(circuit_breaker_enabled=True)

        assert circuit_breaker_config_from_config(stub) == CircuitBreakerConfig()  # type: ignore[arg-type]


class TestCircuitBreakerProductionWiring:
    """Construction sites build an enabled breaker from config (C1a)."""

    def test_storage_factory_wires_enabled_breaker(self):
        config = make_config(circuit_breaker_enabled=True)

        storage = StorageFactory.create_from_config(config)

        assert isinstance(storage, QdrantVectorStorage)
        assert storage._circuit_breaker_enabled is True
        breaker = storage._circuit_breaker
        assert breaker is not None
        assert breaker.config.failure_threshold == 5
        assert breaker.config.success_threshold == 2
        assert breaker.config.recovery_timeout == 30.0

    def test_storage_factory_keeps_breaker_disabled_when_disabled(self):
        config = make_config(circuit_breaker_enabled=False)

        storage = StorageFactory.create_from_config(config)

        assert isinstance(storage, QdrantVectorStorage)
        assert storage._circuit_breaker_enabled is False
        assert storage._circuit_breaker is None

    def test_embedding_factory_wires_enabled_breaker(self):
        config = make_config(circuit_breaker_enabled=True, embedding_api_key="sk-test")

        provider = EmbeddingProviderFactory.create_from_config(config)

        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider._circuit_breaker_enabled is True
        assert provider._circuit_breaker is not None

    def test_embedding_factory_keeps_breaker_disabled_when_disabled(self):
        config = make_config(circuit_breaker_enabled=False, embedding_api_key="sk-test")

        provider = EmbeddingProviderFactory.create_from_config(config)

        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider._circuit_breaker_enabled is False
        assert provider._circuit_breaker is None

    def test_embedding_factory_create_openai_wires_enabled_breaker(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_ENABLED", "true")
        get_config.cache_clear()

        provider = EmbeddingProviderFactory.create_openai(api_key="sk-test")

        assert provider._circuit_breaker_enabled is True
        assert provider._circuit_breaker is not None

    def test_conversation_storage_wires_enabled_breaker(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_ENABLED", "true")
        get_config.cache_clear()

        storage = ConversationStorage(db_path=str(tmp_path / "conversations.db"))

        assert storage._circuit_breaker_enabled is True
        assert storage.circuit_breaker is not None

    def test_conversation_storage_breaker_disabled_by_test_env_default(self, tmp_path):
        """Under pytest the config singleton disables the breaker when unset."""
        storage = ConversationStorage(db_path=str(tmp_path / "conversations.db"))

        assert storage._circuit_breaker_enabled is False
        assert storage.circuit_breaker is None


class TestCircuitBreakerOpenPathDegradation:
    """An OPEN circuit degrades per the path's existing semantics (C1b)."""

    def test_qdrant_probe_skipped_and_false_while_open(self):
        storage = QdrantVectorStorage(
            url="http://localhost:6333",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        assert storage._circuit_breaker is not None
        # One failed probe (threshold=1) opens the circuit.
        storage._circuit_breaker.record_failure()
        # The raw probe must not run while the circuit is open.
        storage._get_client = MagicMock(  # type: ignore[method-assign]
            side_effect=AssertionError("probe must not run while circuit is open")
        )

        assert storage.validate_connection(force=True) is False

    def test_qdrant_circuit_opens_after_repeated_probe_failures(self):
        storage = QdrantVectorStorage(
            url="http://localhost:6333",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=2),
        )
        failing_client = MagicMock()
        failing_client.get_collections.side_effect = RuntimeError("boom")
        storage._get_client = MagicMock(return_value=failing_client)  # type: ignore[method-assign]
        breaker = storage._circuit_breaker
        assert breaker is not None

        assert storage.validate_connection(force=True) is False
        assert breaker.failure_count == 1
        assert breaker.state is CircuitState.CLOSED

        assert storage.validate_connection(force=True) is False
        assert breaker.state is CircuitState.OPEN

        # Circuit open: degrade to False without touching the network.
        calls_before = failing_client.get_collections.call_count
        assert storage.validate_connection(force=True) is False
        assert failing_client.get_collections.call_count == calls_before

    def test_qdrant_successful_probe_records_circuit_success(self):
        storage = QdrantVectorStorage(
            url="http://localhost:6333",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=2),
        )
        client = MagicMock()
        client.get_collections.return_value = []
        storage._get_client = MagicMock(return_value=client)  # type: ignore[method-assign]
        breaker = storage._circuit_breaker
        assert breaker is not None

        assert storage.validate_connection(force=True) is True

        assert breaker.state is CircuitState.CLOSED
        assert breaker.get_failure_count() == 0

    def test_qdrant_async_validation_traverses_the_circuit(self):
        import asyncio

        storage = QdrantVectorStorage(
            url="http://localhost:6333",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        failing_client = MagicMock()
        failing_client.get_collections.side_effect = RuntimeError("boom")
        storage._get_client = MagicMock(return_value=failing_client)  # type: ignore[method-assign]

        assert asyncio.run(storage.validate_connection_async(force=True)) is False
        breaker = storage._circuit_breaker
        assert breaker is not None
        assert breaker.state is CircuitState.OPEN

    def test_embedding_provider_probe_skipped_and_false_while_open(self):
        provider = OpenAIEmbeddingProvider(
            api_key="sk-test",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        assert provider._circuit_breaker is not None
        failing_client = MagicMock()
        failing_client.models.list.side_effect = RuntimeError("boom")
        provider._client = failing_client  # type: ignore[assignment]

        assert provider.validate_connection() is False
        assert provider._circuit_breaker.state is CircuitState.OPEN

        # Circuit open: degrade to False without touching the network.
        calls_before = failing_client.models.list.call_count
        assert provider.validate_connection() is False
        assert failing_client.models.list.call_count == calls_before

    def test_embedding_provider_successful_probe_records_circuit_success(self):
        provider = OpenAIEmbeddingProvider(
            api_key="sk-test",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        provider._client = MagicMock()  # type: ignore[assignment]
        breaker = provider._circuit_breaker
        assert breaker is not None

        assert provider.validate_connection() is True

        assert breaker.state is CircuitState.CLOSED
        assert breaker.get_failure_count() == 0

    def test_conversation_storage_open_circuit_raises_circuit_breaker_error(
        self, monkeypatch, tmp_path
    ):
        """The ValidatableService path fails fast with CircuitBreakerError."""
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_ENABLED", "true")
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
        get_config.cache_clear()

        storage = ConversationStorage(db_path=str(tmp_path / "conversations.db"))
        assert storage._circuit_breaker_enabled is True
        storage._do_validate = lambda: False  # type: ignore[method-assign]

        assert storage.validate_connection_with_circuit_breaker(force=True) is False
        assert storage.circuit_breaker is not None
        assert storage.circuit_breaker.state is CircuitState.OPEN

        with pytest.raises(CircuitBreakerError):
            storage.validate_connection_with_circuit_breaker(force=True)


class TestStartupProbeCircuitBreakerBypass:
    """Startup-wait probes bypass the breaker; post-startup paths do not.

    docker_manager polls ``storage.validate_connection()`` every 2s for up to
    60s while waiting for Qdrant to boot. With the breaker default-ON, five
    failed polls would open the circuit (~10s in) and the recovery backoff
    would starve later polls, raising a spurious ``QdrantStartupError`` for a
    server that becomes ready later. The startup loop therefore passes
    ``bypass_circuit_breaker=True``: the probe runs directly and records
    nothing — success or failure — into the breaker. The breaker stays fully
    active for post-startup health/connection paths.
    """

    def test_qdrant_bypass_failures_record_nothing(self):
        """Bypassed failing probes run raw and leave the breaker closed."""
        storage = QdrantVectorStorage(
            url="http://localhost:6333",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        failing_client = MagicMock()
        failing_client.get_collections.side_effect = RuntimeError("boom")
        storage._get_client = MagicMock(return_value=failing_client)  # type: ignore[method-assign]
        breaker = storage._circuit_breaker
        assert breaker is not None

        # More failing bypass probes than the failure threshold: the raw
        # probe runs every time and nothing is recorded.
        for _ in range(3):
            assert (
                storage.validate_connection(force=True, bypass_circuit_breaker=True)
                is False
            )
        assert failing_client.get_collections.call_count == 3
        assert breaker.state is CircuitState.CLOSED
        assert breaker.get_failure_count() == 0

        # Post-startup path (no bypass) still feeds the breaker.
        assert storage.validate_connection(force=True) is False
        assert breaker.get_failure_count() == 1
        assert storage.validate_connection(force=True) is False
        assert breaker.state is CircuitState.OPEN

    def test_qdrant_bypass_success_records_nothing(self):
        """Bypassed successful probes run raw and record no success."""
        storage = QdrantVectorStorage(
            url="http://localhost:6333",
            circuit_breaker_config=CircuitBreakerConfig(
                failure_threshold=1,
                success_threshold=2,
            ),
        )
        client = MagicMock()
        client.get_collections.return_value = []
        storage._get_client = MagicMock(return_value=client)  # type: ignore[method-assign]
        breaker = storage._circuit_breaker
        assert breaker is not None

        # Force HALF_OPEN (as after the recovery timeout elapses) so a
        # recorded success would be observable via the success counter.
        breaker.record_failure()
        breaker._state = CircuitState.HALF_OPEN

        assert storage.validate_connection(force=True, bypass_circuit_breaker=True)

        # The probe ran despite the OPEN-then-HALF_OPEN circuit...
        assert client.get_collections.called
        # ...and the success was not recorded.
        assert breaker.state is CircuitState.HALF_OPEN
        assert breaker.success_count == 0

    def test_qdrant_bypass_runs_probe_while_circuit_open(self):
        """A bypassed probe runs even while the circuit is OPEN."""
        storage = QdrantVectorStorage(
            url="http://localhost:6333",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        failing_client = MagicMock()
        failing_client.get_collections.side_effect = RuntimeError("boom")
        storage._get_client = MagicMock(return_value=failing_client)  # type: ignore[method-assign]
        breaker = storage._circuit_breaker
        assert breaker is not None
        breaker.record_failure()
        assert breaker.state is CircuitState.OPEN

        # Without bypass: skipped entirely, no network call.
        calls_before = failing_client.get_collections.call_count
        assert storage.validate_connection(force=True) is False
        assert failing_client.get_collections.call_count == calls_before

        # With bypass: the raw probe runs and reports the real result.
        assert (
            storage.validate_connection(force=True, bypass_circuit_breaker=True)
            is False
        )
        assert failing_client.get_collections.call_count == calls_before + 1
        assert breaker.state is CircuitState.OPEN

    def test_embedding_provider_bypass_failures_record_nothing(self):
        """Bypassed failing embedding probes leave the breaker closed."""
        provider = OpenAIEmbeddingProvider(
            api_key="sk-test",
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        failing_client = MagicMock()
        failing_client.models.list.side_effect = RuntimeError("boom")
        provider._client = failing_client  # type: ignore[assignment]
        breaker = provider._circuit_breaker
        assert breaker is not None

        for _ in range(3):
            assert provider.validate_connection(bypass_circuit_breaker=True) is False
        assert failing_client.models.list.call_count == 3
        assert breaker.state is CircuitState.CLOSED
        assert breaker.get_failure_count() == 0

        # Post-startup path (no bypass) still feeds the breaker.
        assert provider.validate_connection() is False
        assert breaker.state is CircuitState.OPEN
