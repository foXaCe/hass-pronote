"""Base entity for the Pronote integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PronoteDataUpdateCoordinator


class PronoteEntity(CoordinatorEntity[PronoteDataUpdateCoordinator]):
    """Base Pronote entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PronoteDataUpdateCoordinator) -> None:
        """Initialize the Pronote entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            name=f"Pronote - {coordinator.data['child_info'].name}",
            identifiers={(DOMAIN, coordinator.data["child_info"].name)},
            manufacturer="Pronote",
            model=coordinator.data["child_info"].name,
        )
