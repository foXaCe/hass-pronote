"""Base entity for the Pronote integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .boot_cache import PronoteBootInfo, boot_info_from_data
from .const import DOMAIN
from .coordinator import PronoteDataUpdateCoordinator


class PronoteEntity(CoordinatorEntity[PronoteDataUpdateCoordinator]):
    """Base Pronote entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PronoteDataUpdateCoordinator) -> None:
        """Initialize the Pronote entity.

        The identity of the entity (unique id, device identifiers) comes from
        the boot info, never from ``coordinator.data``: on a warm boot the
        entities are created before the first refresh, so ``coordinator.data``
        is still None at this point.
        """
        super().__init__(coordinator)

        boot_info = coordinator.boot_info or boot_info_from_data(coordinator.data)
        if boot_info is None:
            raise ValueError("Cannot build a Pronote entity without boot info nor coordinator data")
        self._boot_info: PronoteBootInfo = boot_info

        child_name = boot_info.child_name
        self._attr_device_info = DeviceInfo(
            name=f"Pronote - {child_name}",
            identifiers={(DOMAIN, child_name)},
            manufacturer="Pronote",
            model=child_name,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available.

        ``last_update_success`` starts at True, so it alone is not enough: on a
        warm boot the entities exist before any data does.
        """
        return super().available and self.coordinator.data is not None

    def _get(self, key: str) -> Any:
        """Return a coordinator data key, None-safe.

        Data is None until the first refresh completes, and a key built from
        the boot cache may be missing from a fresh payload (a school period can
        disappear between two runs).
        """
        data = self.coordinator.data
        return None if data is None else data.get(key)
