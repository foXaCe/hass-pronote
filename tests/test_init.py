"""Tests for the Pronote integration __init__."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.pronote import async_migrate_entry, async_setup_entry, async_unload_entry, update_listener
from custom_components.pronote.const import DEFAULT_REFRESH_INTERVAL, PLATFORMS


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
        entry.runtime_data = coordinator

        result = await update_listener(hass, entry)

        assert result is True
        assert coordinator.update_interval == timedelta(minutes=30)

    async def test_default_interval(self, hass: HomeAssistant):
        entry = MagicMock()
        entry.options = {}
        coordinator = MagicMock()
        entry.runtime_data = coordinator

        result = await update_listener(hass, entry)

        assert result is True
        assert coordinator.update_interval == timedelta(minutes=DEFAULT_REFRESH_INTERVAL)


class TestAsyncSetupEntry:
    async def test_setup_success(self, hass: HomeAssistant):
        """Mock coordinator with successful refresh -> entry.runtime_data is set, platforms forwarded."""
        entry = MagicMock()
        entry.data = {
            "username": "jean",
            "password": "pass",
            "account_type": "eleve",
            "connection_type": "username_password",
        }
        entry.options = {"refresh_interval": 15, "nickname": ""}
        entry.async_on_unload = MagicMock()

        mock_coordinator = MagicMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()

        hass.config_entries.async_forward_entry_setups = AsyncMock()

        with patch(
            "custom_components.pronote.PronoteDataUpdateCoordinator",
            return_value=mock_coordinator,
        ):
            result = await async_setup_entry(hass, entry)

        assert result is True
        assert entry.runtime_data is mock_coordinator
        mock_coordinator.async_config_entry_first_refresh.assert_awaited_once()
        hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)
        entry.async_on_unload.assert_called_once()

    async def test_setup_auth_failure(self, hass: HomeAssistant):
        """When coordinator.async_config_entry_first_refresh raises, the exception propagates."""
        entry = MagicMock()
        entry.data = {
            "username": "jean",
            "password": "wrong",
            "account_type": "eleve",
            "connection_type": "username_password",
        }
        entry.options = {"refresh_interval": 15, "nickname": ""}

        mock_coordinator = MagicMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock(side_effect=ConfigEntryNotReady("Auth failed"))

        with (
            patch(
                "custom_components.pronote.PronoteDataUpdateCoordinator",
                return_value=mock_coordinator,
            ),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, entry)


class TestAsyncUnloadEntry:
    async def test_unload_success(self, hass: HomeAssistant):
        """Verify async_unload_platforms is called with the correct platforms."""
        entry = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, PLATFORMS)
