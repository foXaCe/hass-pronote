"""Boot cache for the Pronote integration.

The objects pronotepy returns and that end up in ``coordinator.data`` are not
JSON serialisable, so the full payload cannot be persisted. What *is* persisted
here is the tiny set of scalars the platforms need to build their entities:
device identifiers, unique ids, translation placeholders and the list of school
periods.

Restoring that snapshot lets ``async_setup_entry`` create every entity before
the first network round-trip instead of after it, which removes the Pronote
authentication + full fetch (several seconds) from the Home Assistant startup
critical path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant, callback
from slugify import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# Delay before the boot cache hits the disk after a successful refresh. The
# payload is tiny but there is no urgency: a refresh happens every 15 min by
# default and losing the very last write only costs one slow boot.
SAVE_DELAY = 30.0

_HASS_DATA_KEY = f"{DOMAIN}_boot_cache"
_HASS_DATA_RELOADED_KEY = f"{DOMAIN}_boot_cache_reloaded"


def _storage_key(entry_id: str) -> str:
    """Return the .storage key holding the boot cache of a config entry."""
    return f"{DOMAIN}.boot_cache.{entry_id}"


@dataclass(frozen=True)
class PronoteBootInfo:
    """Minimal JSON-serialisable snapshot needed to build the entities.

    Every field here is read by a platform setup or an entity ``__init__``.
    Nothing that is only read by a property belongs in this class: properties
    read ``coordinator.data`` live.
    """

    child_name: str
    sensor_prefix: str
    account_type: str | None = None
    child_class_name: str | None = None
    child_establishment: str | None = None
    current_period_name: str | None = None
    previous_period_names: tuple[str, ...] = ()

    @property
    def current_period_key(self) -> str | None:
        """Return the slug of the current period, as sensor.py computes it."""
        if not self.current_period_name:
            return None
        return slugify(self.current_period_name, separator="_")

    @property
    def identity(self) -> tuple[Any, ...]:
        """Return the fields that drive which entities exist and their ids.

        Two boot infos with the same identity produce byte-for-byte identical
        unique ids and device identifiers, and the exact same set of entities.
        """
        return (
            self.child_name,
            self.sensor_prefix,
            self.current_period_name,
            self.previous_period_names,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-serialisable representation."""
        return {
            "child_name": self.child_name,
            "sensor_prefix": self.sensor_prefix,
            "account_type": self.account_type,
            "child_class_name": self.child_class_name,
            "child_establishment": self.child_establishment,
            "current_period_name": self.current_period_name,
            "previous_period_names": list(self.previous_period_names),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> PronoteBootInfo:
        """Rebuild from the stored representation.

        Raises ValueError when the payload is unusable so the caller can fall
        back to the blocking setup path instead of building entities with
        wrong unique ids.
        """
        if not isinstance(raw, dict):
            raise ValueError("boot cache payload is not a mapping")

        child_name = raw.get("child_name")
        sensor_prefix = raw.get("sensor_prefix")
        if not isinstance(child_name, str) or not child_name:
            raise ValueError("boot cache has no usable child_name")
        if not isinstance(sensor_prefix, str) or not sensor_prefix:
            raise ValueError("boot cache has no usable sensor_prefix")

        previous_periods = raw.get("previous_period_names") or []
        if not isinstance(previous_periods, list) or any(not isinstance(name, str) for name in previous_periods):
            raise ValueError("boot cache has a malformed previous_period_names")

        current_period_name = raw.get("current_period_name")
        if current_period_name is not None and not isinstance(current_period_name, str):
            raise ValueError("boot cache has a malformed current_period_name")

        return cls(
            child_name=child_name,
            sensor_prefix=sensor_prefix,
            account_type=_optional_str(raw.get("account_type")),
            child_class_name=_optional_str(raw.get("child_class_name")),
            child_establishment=_optional_str(raw.get("child_establishment")),
            current_period_name=current_period_name,
            previous_period_names=tuple(previous_periods),
        )


def _optional_str(value: Any) -> str | None:
    """Return value when it is a string, None otherwise."""
    return value if isinstance(value, str) else None


def boot_info_from_data(data: dict[str, Any] | None) -> PronoteBootInfo | None:
    """Derive the boot info from a fresh ``coordinator.data`` payload.

    Returns None when the payload cannot identify the child, which is the only
    case where entities must not be built.
    """
    if not data:
        return None

    child_info = data.get("child_info")
    child_name = getattr(child_info, "name", None)
    sensor_prefix = data.get("sensor_prefix")
    if not isinstance(child_name, str) or not child_name or not isinstance(sensor_prefix, str) or not sensor_prefix:
        return None

    current_period = data.get("current_period")
    current_period_name = getattr(current_period, "name", None)

    previous_periods = data.get("previous_periods") or []
    previous_period_names = tuple(
        name for period in previous_periods if isinstance(name := getattr(period, "name", None), str)
    )

    return PronoteBootInfo(
        child_name=child_name,
        sensor_prefix=sensor_prefix,
        account_type=_optional_str(data.get("account_type")),
        child_class_name=_optional_str(getattr(child_info, "class_name", None)),
        child_establishment=_optional_str(getattr(child_info, "establishment", None)),
        current_period_name=current_period_name if isinstance(current_period_name, str) else None,
        previous_period_names=previous_period_names,
    )


class PronoteBootCache:
    """Persist and restore the boot info of a single config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the boot cache (no I/O happens here)."""
        from homeassistant.helpers.storage import Store  # noqa: PLC0415  # lazy: keeps module import cheap

        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, _storage_key(entry_id))

    async def async_load(self) -> PronoteBootInfo | None:
        """Return the stored boot info, or None when absent or corrupted."""
        try:
            raw = await self._store.async_load()
        except Exception:  # noqa: BLE001  # a broken cache must never break setup
            _LOGGER.warning("Pronote boot cache unreadable, falling back to a blocking setup", exc_info=True)
            return None

        if raw is None:
            return None

        try:
            return PronoteBootInfo.from_dict(raw)
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Pronote boot cache is invalid (%s), falling back to a blocking setup", err)
            return None

    @callback
    def async_schedule_save(self, boot_info: PronoteBootInfo) -> None:
        """Schedule a delayed write of the boot info."""
        self._store.async_delay_save(boot_info.as_dict, SAVE_DELAY)

    async def async_save(self, boot_info: PronoteBootInfo) -> None:
        """Write the boot info immediately."""
        await self._store.async_save(boot_info.as_dict())

    async def async_remove(self) -> None:
        """Cancel any pending write and delete the stored boot info."""
        await self._store.async_remove()


@callback
def async_get_boot_cache(hass: HomeAssistant, entry_id: str) -> PronoteBootCache:
    """Return the boot cache of a config entry, creating it on first use.

    A single instance per entry is required so a pending delayed write can be
    cancelled when the entry is removed.
    """
    caches: dict[str, PronoteBootCache] = hass.data.setdefault(_HASS_DATA_KEY, {})
    if (cache := caches.get(entry_id)) is None:
        cache = caches[entry_id] = PronoteBootCache(hass, entry_id)
    return cache


@callback
def async_claim_layout_reload(hass: HomeAssistant, entry_id: str) -> bool:
    """Return True the first time an entry asks to reload for a layout change.

    A reload rebuilds the entities from the freshly saved snapshot, so one is
    enough. Should Pronote keep flip-flopping (periods reordered from one
    request to the next), refusing the second reload is what stops an endless
    setup/reload loop: the entry then simply picks the new layout up at the
    next Home Assistant start, which is the pre-cache behaviour.
    """
    reloaded: set[str] = hass.data.setdefault(_HASS_DATA_RELOADED_KEY, set())
    if entry_id in reloaded:
        return False
    reloaded.add(entry_id)
    return True


async def async_remove_boot_cache(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the boot cache of a config entry."""
    caches: dict[str, PronoteBootCache] = hass.data.setdefault(_HASS_DATA_KEY, {})
    cache = caches.pop(entry_id, None) or PronoteBootCache(hass, entry_id)
    hass.data.setdefault(_HASS_DATA_RELOADED_KEY, set()).discard(entry_id)
    await cache.async_remove()
