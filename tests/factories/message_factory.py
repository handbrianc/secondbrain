"""Factory for creating test Message objects."""

from datetime import datetime

from factory import Faker, Sequence, Factory, LazyFunction
from typing import Any


class MessageFactory(Factory):
    """Factory for creating test Message objects.

    Provides flexible message creation for conversation tests.

    Attributes
    ----------
    role : str
        Message role: 'user', 'assistant', or 'system'
    content : str
        Message content text
    timestamp : datetime
        Message creation timestamp
    """

    class Meta:
        model = dict

    role = Faker("random_element", elements=["user", "assistant", "system"])
    content = Faker("paragraph")
    timestamp = LazyFunction(lambda: datetime.now().isoformat())
