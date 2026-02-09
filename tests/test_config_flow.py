"""Tests for the Pronote config flow."""

from custom_components.pronote.const import DOMAIN


async def test_domain():
    """Test the domain constant."""
    assert DOMAIN == "pronote"
