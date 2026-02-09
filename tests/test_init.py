"""Tests for the Pronote integration __init__."""

from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.pronote import async_migrate_entry, update_listener
from custom_components.pronote.const import DEFAULT_REFRESH_INTERVAL, DOMAIN


class TestAsyncMigrateEntry:
    async def test_migrate_v1_to_v2(self, hass: HomeAssistant):
        entry = MagicMock()
        entry.version = 1
        entry.data = {"username": "jean", "password": "pass"}

        # Patch async_update_entry to avoid real config entry lookup
        hass.config_entries.async_update_entry = MagicMock()

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 2
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        new_data = call_args[1].get("data") or call_args.kwargs.get("data")
        assert new_data["connection_type"] == "username_password"
        assert new_data["username"] == "jean"

    async def test_migrate_v2_no_change(self, hass: HomeAssistant):
        entry = MagicMock()
        entry.version = 2
        entry.data = {"username": "jean", "connection_type": "username_password"}

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 2


class TestUpdateListener:
    async def test_updates_interval(self, hass: HomeAssistant):
        entry = MagicMock()
        entry.options = {"refresh_interval": 30}
        coordinator = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}

        result = await update_listener(hass, entry)

        assert result is True
        assert coordinator.update_interval == timedelta(minutes=30)

    async def test_default_interval(self, hass: HomeAssistant):
        entry = MagicMock()
        entry.options = {}
        coordinator = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}

        result = await update_listener(hass, entry)

        assert result is True
        assert coordinator.update_interval == timedelta(minutes=DEFAULT_REFRESH_INTERVAL)
