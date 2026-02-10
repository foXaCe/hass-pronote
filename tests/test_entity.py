"""Tests for the Pronote entity base class."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.pronote.coordinator import PronoteDataUpdateCoordinator
from custom_components.pronote.entity import PronoteEntity


def _make_coordinator(data=None, options=None):
    """Create a minimal coordinator for testing."""
    with patch.object(
        PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None
    ):
        coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
    coord.data = data or {}
    entry = MagicMock()
    entry.options = options or {"nickname": ""}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.last_update_success_time = datetime(2025, 1, 15, 10, 0)
    return coord


class TestPronoteEntity:
    def test_has_entity_name(self):
        """_attr_has_entity_name is True."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
        }
        coord = _make_coordinator(data=data)
        entity = PronoteEntity(coord)

        assert entity._attr_has_entity_name is True

    def test_device_info(self):
        """Verify device_info name, identifiers, manufacturer, and model."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
        }
        coord = _make_coordinator(data=data)
        entity = PronoteEntity(coord)

        device_info = entity._attr_device_info
        assert device_info["name"] == "Pronote - Jean Dupont"
        assert ("pronote", "Jean Dupont") in device_info["identifiers"]
        assert device_info["manufacturer"] == "Pronote"
        assert device_info["model"] == "Jean Dupont"
