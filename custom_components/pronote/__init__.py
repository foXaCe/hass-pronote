"""The Pronote integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant

import custom_components.pronote._compat  # noqa: F401  # Apply autoslot hotfix before pronotepy

from .const import DEFAULT_REFRESH_INTERVAL, PLATFORMS, PronoteConfigEntry
from .coordinator import PronoteDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass, config_entry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        new = {**config_entry.data}
        new["connection_type"] = "username_password"

        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data=new)

    _LOGGER.debug("Migration to version %s successful", config_entry.version)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: PronoteConfigEntry) -> bool:
    """Set up Pronote from a config entry."""
    coordinator = PronoteDataUpdateCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PronoteConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: PronoteConfigEntry):
    """Handle options update."""
    entry.runtime_data.update_interval = timedelta(
        minutes=entry.options.get("refresh_interval", DEFAULT_REFRESH_INTERVAL)
    )

    return True
