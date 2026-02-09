"""Fixtures for the Pronote integration tests."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


@pytest.fixture
def mock_pronote_client():
    """Mock a Pronote client."""
    with patch("custom_components.pronote.coordinator.get_pronote_client") as mock_client:
        yield mock_client
