"""Tests for the Pronote integration __init__."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.pronote import (
    async_migrate_entry,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
    update_listener,
)
from custom_components.pronote.boot_cache import PronoteBootInfo, async_get_boot_cache
from custom_components.pronote.const import DEFAULT_REFRESH_INTERVAL, PLATFORMS

BOOT_INFO = PronoteBootInfo(
    child_name="Jean Dupont",
    sensor_prefix="jean_dupont",
    account_type="eleve",
    current_period_name="Trimestre 2",
    previous_period_names=("Trimestre 1",),
)


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
            "custom_components.pronote.coordinator.PronoteDataUpdateCoordinator",
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
                "custom_components.pronote.coordinator.PronoteDataUpdateCoordinator",
                return_value=mock_coordinator,
            ),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, entry)


class TestBootCachePaths:
    """async_setup_entry picks the blocking or the background path."""

    @staticmethod
    def _entry():
        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {
            "username": "jean",
            "password": "pass",
            "account_type": "eleve",
            "connection_type": "username_password",
        }
        entry.options = {"refresh_interval": 15, "nickname": ""}
        entry.async_on_unload = MagicMock()

        def _consume(hass, coro, name, **kwargs):
            # Close the coroutine instead of scheduling it: the test asserts
            # on the call, it does not want a real refresh.
            coro.close()
            return MagicMock()

        entry.async_create_background_task = MagicMock(side_effect=_consume)
        return entry

    @staticmethod
    def _coordinator():
        async def _refresh():
            return None

        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_refresh = MagicMock(side_effect=lambda: _refresh())
        return coordinator

    async def test_cold_boot_blocks_and_creates_no_background_task(self, hass: HomeAssistant):
        entry = self._entry()
        coordinator = self._coordinator()
        hass.config_entries.async_forward_entry_setups = AsyncMock()

        with patch(
            "custom_components.pronote.coordinator.PronoteDataUpdateCoordinator",
            return_value=coordinator,
        ):
            assert await async_setup_entry(hass, entry)

        coordinator.async_config_entry_first_refresh.assert_awaited_once()
        coordinator.attach_boot_cache.assert_called_once()
        assert coordinator.attach_boot_cache.call_args[0][1] is None
        entry.async_create_background_task.assert_not_called()

    async def test_warm_boot_skips_the_blocking_refresh(self, hass: HomeAssistant):
        entry = self._entry()
        coordinator = self._coordinator()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        await async_get_boot_cache(hass, "entry1").async_save(BOOT_INFO)

        with patch(
            "custom_components.pronote.coordinator.PronoteDataUpdateCoordinator",
            return_value=coordinator,
        ):
            assert await async_setup_entry(hass, entry)

        coordinator.async_config_entry_first_refresh.assert_not_awaited()
        assert coordinator.attach_boot_cache.call_args[0][1] == BOOT_INFO
        # Platforms are forwarded, then the refresh runs in the background.
        hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)
        entry.async_create_background_task.assert_called_once()
        coordinator.async_refresh.assert_called_once()
        # Non-first refresh: DataUpdateCoordinator turns ConfigEntryAuthFailed
        # into a reauth flow instead of failing a loaded entry.
        coordinator.async_config_entry_first_refresh.assert_not_called()

    async def test_corrupted_cache_falls_back_to_the_blocking_path(self, hass: HomeAssistant, hass_storage):
        entry = self._entry()
        coordinator = self._coordinator()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        hass_storage["pronote.boot_cache.entry1"] = {
            "version": 1,
            "minor_version": 1,
            "key": "pronote.boot_cache.entry1",
            "data": {"garbage": True},
        }

        with patch(
            "custom_components.pronote.coordinator.PronoteDataUpdateCoordinator",
            return_value=coordinator,
        ):
            assert await async_setup_entry(hass, entry)

        coordinator.async_config_entry_first_refresh.assert_awaited_once()
        entry.async_create_background_task.assert_not_called()


class TestAsyncRemoveEntry:
    async def test_removes_the_boot_cache(self, hass: HomeAssistant, hass_storage):
        entry = MagicMock()
        entry.entry_id = "entry1"
        await async_get_boot_cache(hass, "entry1").async_save(BOOT_INFO)
        assert "pronote.boot_cache.entry1" in hass_storage

        await async_remove_entry(hass, entry)

        assert "pronote.boot_cache.entry1" not in hass_storage


class TestAsyncUnloadEntry:
    async def test_unload_success(self, hass: HomeAssistant):
        """Verify async_unload_platforms is called and coordinator is shut down."""
        entry = MagicMock()
        coordinator = MagicMock()
        coordinator.async_shutdown = AsyncMock()
        entry.runtime_data = coordinator
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, PLATFORMS)
        coordinator.async_shutdown.assert_awaited_once()

    async def test_unload_no_shutdown_on_failure(self, hass: HomeAssistant):
        """Verify coordinator is not shut down if platform unload fails."""
        entry = MagicMock()
        coordinator = MagicMock()
        coordinator.async_shutdown = AsyncMock()
        entry.runtime_data = coordinator
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(hass, entry)

        assert result is False
        coordinator.async_shutdown.assert_not_awaited()
