"""The Pronote integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.core import HomeAssistant

import custom_components.pronote._compat  # noqa: F401  # Apply autoslot hotfix before pronotepy

from .const import DEFAULT_REFRESH_INTERVAL, PLATFORMS, PronoteConfigEntry

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
    """Set up Pronote from a config entry.

    Two paths:

    - warm boot (a boot cache written by a previous run is available): the
      entities are created from the cached snapshot and the first Pronote
      authentication + fetch runs in a background task, so setup does not block
      Home Assistant startup;
    - cold boot (first install, or unusable cache): the historical blocking
      first refresh, so a wrong password or an unreachable Pronote server still
      fails the setup cleanly and gets retried by Home Assistant.
    """
    from .boot_cache import async_get_boot_cache  # noqa: PLC0415  # lazy: keeps module import cheap
    from .coordinator import PronoteDataUpdateCoordinator  # noqa: PLC0415  # lazy: heavy imports (pronotepy)

    t0 = time.perf_counter()
    boot_cache = async_get_boot_cache(hass, entry.entry_id)
    boot_info = await boot_cache.async_load()

    t1 = time.perf_counter()
    coordinator = PronoteDataUpdateCoordinator(hass, entry)
    coordinator.attach_boot_cache(boot_cache, boot_info)

    t2 = time.perf_counter()
    if boot_info is None:
        await coordinator.async_config_entry_first_refresh()
    t3 = time.perf_counter()

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    t4 = time.perf_counter()

    if boot_info is not None:
        # Non-first refresh on purpose: a ConfigEntryAuthFailed raised here is
        # turned into a reauth flow by DataUpdateCoordinator._async_refresh
        # instead of failing an already-loaded entry.
        entry.async_create_background_task(
            hass,
            coordinator.async_refresh(),
            f"pronote initial refresh {entry.entry_id}",
        )

    _LOGGER.debug(
        "BOOT TIMING: boot_cache_load=%.3fs (hit=%s), coordinator_init=%.3fs, "
        "first_refresh=%.3fs, platform_setup=%.3fs, total=%.3fs",
        t1 - t0,
        boot_info is not None,
        t2 - t1,
        t3 - t2,
        t4 - t3,
        t4 - t0,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PronoteConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = entry.runtime_data
        await coordinator.async_shutdown()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: PronoteConfigEntry) -> None:
    """Delete the boot cache when the config entry is removed."""
    from .boot_cache import async_remove_boot_cache  # noqa: PLC0415  # lazy: keeps module import cheap

    await async_remove_boot_cache(hass, entry.entry_id)


async def update_listener(hass: HomeAssistant, entry: PronoteConfigEntry):
    """Handle options update."""
    entry.runtime_data.update_interval = timedelta(
        minutes=entry.options.get("refresh_interval", DEFAULT_REFRESH_INTERVAL)
    )

    return True
