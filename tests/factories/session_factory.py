"""Factory for creating test Session objects."""

from factory import Factory, Faker, List, SubFactory

from .message_factory import MessageFactory


class SessionFactory(Factory):
    """Factory for creating test Session objects.

    Provides flexible session creation for conversation tests.

    Attributes
    ----------
    session_id : str
        Unique session identifier (auto-generated UUID)
    messages : list[dict]
        List of message dictionaries
    created_at : datetime
        Session creation timestamp
    updated_at : datetime
        Session last update timestamp
    """

    class Meta:
        model = dict

    session_id = Faker("uuid4")
    messages = List([SubFactory(MessageFactory)])
    created_at = Faker("date_time_this_year")
    updated_at = Faker("date_time_this_year")
