"""Pytest fixtures for chaos tests."""

import pytest

from secondbrain.utils.failure_injector import FailureInjector


@pytest.fixture
def failure_injector() -> FailureInjector:
    """Provide a FailureInjector instance for chaos tests.

    Yields:
        FailureInjector: Configured failure injector instance.

    Note:
        The fixture automatically cleans up after each test by resetting
        all active failures.
    """
    injector = FailureInjector.get_instance()
    try:
        yield injector
    finally:
        injector.reset()
        FailureInjector.reset_instance()
