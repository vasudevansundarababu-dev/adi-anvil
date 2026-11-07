# Shares the authenticated test-client fixture with every integration module.
import pytest
from journey_support import provision_journey
from test_api_security import client_factory  # noqa: F401


@pytest.fixture(scope="session")
def journey():
    """One self-provisioned synthetic journey per session, in its own demo project."""
    return provision_journey()
