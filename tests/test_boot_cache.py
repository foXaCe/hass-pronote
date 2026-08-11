"""Tests for the Pronote boot cache."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.pronote.boot_cache import (
    STORAGE_VERSION,
    PronoteBootCache,
    PronoteBootInfo,
    async_claim_layout_reload,
    async_get_boot_cache,
    async_remove_boot_cache,
    boot_info_from_data,
)
from custom_components.pronote.coordinator import PronoteDataUpdateCoordinator

BOOT_INFO = PronoteBootInfo(
    child_name="Jean Dupont",
    sensor_prefix="jean_dupont",
    account_type="eleve",
    child_class_name="3eme A",
    child_establishment="College Victor Hugo",
    current_period_name="Trimestre 2",
    previous_period_names=("Trimestre 1",),
)


def _data(
    child_name="Jean Dupont",
    current_period_name="Trimestre 2",
    previous_period_names=("Trimestre 1",),
    sensor_prefix="jean_dupont",
):
    """Build a coordinator.data payload."""
    return {
        "account_type": "eleve",
        "sensor_prefix": sensor_prefix,
        "child_info": SimpleNamespace(
            name=child_name,
            class_name="3eme A",
            establishment="College Victor Hugo",
        ),
        "current_period": SimpleNamespace(name=current_period_name, start=date(2025, 9, 1)),
        "previous_periods": [SimpleNamespace(name=name) for name in previous_period_names],
    }


class TestPronoteBootInfo:
    def test_round_trip_is_lossless(self):
        """from_dict(as_dict()) must give back the exact same snapshot.

        A lossy round trip would make the coordinator believe the layout
        changed at every refresh and reload the entry in a loop.
        """
        restored = PronoteBootInfo.from_dict(BOOT_INFO.as_dict())

        assert restored == BOOT_INFO
        assert restored.identity == BOOT_INFO.identity

    def test_as_dict_is_json_types_only(self):
        raw = BOOT_INFO.as_dict()

        assert isinstance(raw["previous_period_names"], list)
        for value in raw.values():
            assert value is None or isinstance(value, str | list)

    def test_current_period_key_is_the_sensor_slug(self):
        assert BOOT_INFO.current_period_key == "trimestre_2"

    def test_current_period_key_none_without_period(self):
        assert PronoteBootInfo(child_name="A", sensor_prefix="a").current_period_key is None

    def test_identity_ignores_class_and_establishment(self):
        """Class or establishment changes must not trigger an entry reload."""
        other = PronoteBootInfo(
            child_name=BOOT_INFO.child_name,
            sensor_prefix=BOOT_INFO.sensor_prefix,
            account_type=BOOT_INFO.account_type,
            child_class_name="2nde B",
            child_establishment="Lycee Pasteur",
            current_period_name=BOOT_INFO.current_period_name,
            previous_period_names=BOOT_INFO.previous_period_names,
        )

        assert other.identity == BOOT_INFO.identity

    @pytest.mark.parametrize(
        "raw",
        [
            "not a mapping",
            None,
            {},
            {"child_name": "Jean"},
            {"child_name": "", "sensor_prefix": "jean"},
            {"child_name": "Jean", "sensor_prefix": ""},
            {"child_name": "Jean", "sensor_prefix": "jean", "previous_period_names": "T1"},
            {"child_name": "Jean", "sensor_prefix": "jean", "previous_period_names": [1, 2]},
            {"child_name": "Jean", "sensor_prefix": "jean", "current_period_name": 42},
        ],
    )
    def test_from_dict_rejects_corrupted_payloads(self, raw):
        with pytest.raises(ValueError):
            PronoteBootInfo.from_dict(raw)

    def test_from_dict_tolerates_missing_optionals(self):
        restored = PronoteBootInfo.from_dict({"child_name": "Jean", "sensor_prefix": "jean"})

        assert restored.account_type is None
        assert restored.previous_period_names == ()


class TestBootInfoFromData:
    def test_derives_every_field(self):
        boot_info = boot_info_from_data(_data())

        assert boot_info == BOOT_INFO

    def test_returns_none_without_data(self):
        assert boot_info_from_data(None) is None
        assert boot_info_from_data({}) is None

    def test_returns_none_without_child_info(self):
        data = _data()
        del data["child_info"]

        assert boot_info_from_data(data) is None

    def test_returns_none_without_sensor_prefix(self):
        data = _data()
        data["sensor_prefix"] = None

        assert boot_info_from_data(data) is None

    def test_tolerates_missing_current_period(self):
        data = _data()
        data["current_period"] = None

        boot_info = boot_info_from_data(data)

        assert boot_info is not None
        assert boot_info.current_period_name is None

    def test_tolerates_missing_previous_periods(self):
        data = _data()
        data["previous_periods"] = None

        boot_info = boot_info_from_data(data)

        assert boot_info.previous_period_names == ()


class TestPronoteBootCache:
    async def test_save_then_load(self, hass: HomeAssistant, hass_storage):
        cache = PronoteBootCache(hass, "entry1")
        await cache.async_save(BOOT_INFO)

        assert hass_storage["pronote.boot_cache.entry1"]["version"] == STORAGE_VERSION
        assert await PronoteBootCache(hass, "entry1").async_load() == BOOT_INFO

    async def test_load_missing_returns_none(self, hass: HomeAssistant):
        assert await PronoteBootCache(hass, "unknown").async_load() is None

    async def test_load_corrupted_payload_returns_none(self, hass: HomeAssistant, hass_storage):
        hass_storage["pronote.boot_cache.entry1"] = {
            "version": STORAGE_VERSION,
            "minor_version": 1,
            "key": "pronote.boot_cache.entry1",
            "data": {"child_name": "Jean"},  # no sensor_prefix
        }

        assert await PronoteBootCache(hass, "entry1").async_load() is None

    async def test_load_store_error_returns_none(self, hass: HomeAssistant):
        cache = PronoteBootCache(hass, "entry1")
        with patch.object(cache._store, "async_load", AsyncMock(side_effect=OSError("boom"))):
            assert await cache.async_load() is None

    async def test_delayed_save_uses_the_store_delay(self, hass: HomeAssistant):
        cache = PronoteBootCache(hass, "entry1")
        with patch.object(cache._store, "async_delay_save") as delay_save:
            cache.async_schedule_save(BOOT_INFO)

        delay_save.assert_called_once()
        data_func, delay = delay_save.call_args[0]
        assert delay > 0
        assert data_func() == BOOT_INFO.as_dict()

    async def test_remove_deletes_the_stored_snapshot(self, hass: HomeAssistant, hass_storage):
        cache = async_get_boot_cache(hass, "entry1")
        await cache.async_save(BOOT_INFO)
        assert "pronote.boot_cache.entry1" in hass_storage

        await async_remove_boot_cache(hass, "entry1")

        assert "pronote.boot_cache.entry1" not in hass_storage

    async def test_get_boot_cache_is_a_per_entry_singleton(self, hass: HomeAssistant):
        """A single Store per entry, so a pending write can be cancelled on removal."""
        assert async_get_boot_cache(hass, "entry1") is async_get_boot_cache(hass, "entry1")
        assert async_get_boot_cache(hass, "entry1") is not async_get_boot_cache(hass, "entry2")

    async def test_remove_unknown_entry_does_not_raise(self, hass: HomeAssistant):
        await async_remove_boot_cache(hass, "never-seen")


class TestLayoutReloadClaim:
    """One reload per entry and per Home Assistant run, never a loop."""

    async def test_only_the_first_claim_is_granted(self, hass: HomeAssistant):
        assert async_claim_layout_reload(hass, "entry1") is True
        assert async_claim_layout_reload(hass, "entry1") is False
        assert async_claim_layout_reload(hass, "entry1") is False

    async def test_claims_are_per_entry(self, hass: HomeAssistant):
        assert async_claim_layout_reload(hass, "entry1") is True
        assert async_claim_layout_reload(hass, "entry2") is True

    async def test_removing_the_entry_clears_the_claim(self, hass: HomeAssistant):
        assert async_claim_layout_reload(hass, "entry1") is True

        await async_remove_boot_cache(hass, "entry1")

        assert async_claim_layout_reload(hass, "entry1") is True

    async def test_coordinator_stops_reloading_a_flapping_layout(self, hass: HomeAssistant):
        """Two setups in a row seeing a different layout must reload only once."""
        reloads = []

        def _coordinator():
            with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
                coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
            coord.hass = hass
            coord.config_entry = MagicMock()
            coord.config_entry.entry_id = "entry1"
            coord.boot_info = BOOT_INFO
            coord.booted_from_cache = True
            coord._boot_cache = MagicMock()
            coord._boot_cache.async_save = AsyncMock()
            coord._boot_reload_scheduled = False
            return coord

        with patch.object(
            hass.config_entries,
            "async_schedule_reload",
            side_effect=lambda entry_id: reloads.append(entry_id),
        ):
            # First setup: layout moved, reload granted.
            await _coordinator()._async_persist_boot_info(_data(previous_period_names=("T1", "T2")))
            # Second setup (after the reload): layout moved again, refused.
            await _coordinator()._async_persist_boot_info(_data(previous_period_names=("T3",)))

        assert reloads == ["entry1"]


class TestCoordinatorPersistence:
    """The coordinator refreshes the snapshot after every successful update."""

    def _coordinator(self, boot_info=None, booted_from_cache=False):
        with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
            coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
        coord.hass = MagicMock()
        coord.config_entry = MagicMock()
        coord.config_entry.entry_id = "entry1"
        coord.boot_info = boot_info
        coord.booted_from_cache = booted_from_cache
        coord._boot_cache = MagicMock()
        coord._boot_cache.async_save = AsyncMock()
        coord._boot_reload_scheduled = False
        return coord

    def test_attach_boot_cache_marks_a_warm_boot(self):
        coord = self._coordinator()
        cache = MagicMock()

        coord.attach_boot_cache(cache, BOOT_INFO)

        assert coord.boot_info is BOOT_INFO
        assert coord.booted_from_cache is True

    def test_attach_boot_cache_marks_a_cold_boot(self):
        coord = self._coordinator()

        coord.attach_boot_cache(MagicMock(), None)

        assert coord.boot_info is None
        assert coord.booted_from_cache is False

    async def test_first_write_is_immediate(self):
        """A cold boot has nothing cached yet: write now, do not reload."""
        coord = self._coordinator()

        await coord._async_persist_boot_info(_data())

        assert coord.boot_info == BOOT_INFO
        coord._boot_cache.async_save.assert_awaited_once_with(BOOT_INFO)
        coord._boot_cache.async_schedule_save.assert_not_called()
        coord.hass.config_entries.async_schedule_reload.assert_not_called()

    async def test_unchanged_layout_is_saved_with_a_delay(self):
        coord = self._coordinator(boot_info=BOOT_INFO, booted_from_cache=True)

        await coord._async_persist_boot_info(_data())

        coord._boot_cache.async_schedule_save.assert_called_once_with(BOOT_INFO)
        coord._boot_cache.async_save.assert_not_awaited()
        coord.hass.config_entries.async_schedule_reload.assert_not_called()

    async def test_new_period_reloads_the_entry_once(self):
        coord = self._coordinator(boot_info=BOOT_INFO, booted_from_cache=True)

        await coord._async_persist_boot_info(_data(previous_period_names=("Trimestre 1", "Trimestre 2")))

        coord._boot_cache.async_save.assert_awaited_once()
        coord.hass.config_entries.async_schedule_reload.assert_called_once_with("entry1")

        # A second mismatch must not schedule another reload for this instance.
        coord.hass.config_entries.async_schedule_reload.reset_mock()
        await coord._async_persist_boot_info(_data(previous_period_names=("Trimestre 3",)))
        coord.hass.config_entries.async_schedule_reload.assert_not_called()

    async def test_cold_boot_never_reloads_on_mismatch(self):
        """Entities were built from this very payload: nothing to rebuild."""
        coord = self._coordinator(boot_info=BOOT_INFO, booted_from_cache=False)

        await coord._async_persist_boot_info(_data(child_name="Jeanne Dupont"))

        coord.hass.config_entries.async_schedule_reload.assert_not_called()

    async def test_unusable_payload_is_ignored(self):
        coord = self._coordinator(boot_info=BOOT_INFO, booted_from_cache=True)

        await coord._async_persist_boot_info({})

        assert coord.boot_info is BOOT_INFO
        coord._boot_cache.async_save.assert_not_awaited()
        coord._boot_cache.async_schedule_save.assert_not_called()

    async def test_no_cache_attached_only_updates_memory(self):
        coord = self._coordinator()
        coord._boot_cache = None

        await coord._async_persist_boot_info(_data())

        assert coord.boot_info == BOOT_INFO
