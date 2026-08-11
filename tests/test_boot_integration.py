"""End-to-end boot tests for the Pronote integration.

These tests drive the real ``async_setup_entry`` against a real Home Assistant
instance with only the Pronote API client mocked, so the whole chain is
exercised: boot cache, coordinator, platform setup, entity and device
registries.
"""

import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from slugify import slugify

from custom_components.pronote.boot_cache import PronoteBootInfo, boot_info_from_data
from custom_components.pronote.const import DOMAIN

ENTRY_ID = "pronote_entry_1"
STORAGE_KEY = f"pronote.boot_cache.{ENTRY_ID}"

# A warm setup that waits for the network would hang forever behind the gate:
# the timeout turns that regression into a failure instead of a frozen suite.
SETUP_TIMEOUT = 10

ENTRY_DATA = {
    "connection_type": "username_password",
    "account_type": "eleve",
    "url": "https://demo.index-education.net/pronote/eleve.html",
    "username": "jean",
    "password": "secret",
}
ENTRY_OPTIONS = {"refresh_interval": 15, "nickname": "", "lunch_break_time": "13:00"}

CHILD_NAME = "Jean Dupont"
SENSOR_PREFIX = "jean_dupont"
CURRENT_PERIOD = "Trimestre 2"
PREVIOUS_PERIODS = ("Trimestre 1",)


def _period(name: str):
    return SimpleNamespace(
        name=name,
        start=date(2025, 9, 1),
        end=date(2025, 12, 20),
        overall_average="14.5",
    )


def _pronote_data(previous_period_names=PREVIOUS_PERIODS, child_name=CHILD_NAME):
    """Build a PronoteData-shaped object as the API client returns it."""
    previous_periods = [_period(name) for name in previous_period_names]
    previous_period_data: dict = {}
    for period in previous_periods:
        key = slugify(period.name, separator="_")
        previous_period_data |= {
            f"grades_{key}": [],
            f"averages_{key}": [],
            f"absences_{key}": [],
            f"delays_{key}": [],
            f"evaluations_{key}": [],
            f"punishments_{key}": [],
            f"overall_average_{key}": "13.0",
        }

    return SimpleNamespace(
        child_info=SimpleNamespace(
            name=child_name,
            class_name="3eme A",
            establishment="College Victor Hugo",
        ),
        lessons_today=[],
        lessons_tomorrow=[],
        lessons_next_day=[],
        lessons_period=[],
        grades=[],
        averages=[],
        overall_average="14.5",
        absences=[],
        delays=[],
        punishments=[],
        evaluations=[],
        homework=[],
        homework_period=[],
        information_and_surveys=[],
        menus=[],
        periods=[_period(CURRENT_PERIOD), *previous_periods],
        current_period=_period(CURRENT_PERIOD),
        current_period_key=slugify(CURRENT_PERIOD, separator="_"),
        previous_periods=previous_periods,
        active_periods=[_period(CURRENT_PERIOD)],
        ical_url="https://example.com/ical",
        previous_period_data=previous_period_data,
        credentials=None,
        password=None,
    )


def _cached_boot_info(previous_period_names=PREVIOUS_PERIODS, child_name=CHILD_NAME) -> PronoteBootInfo:
    return PronoteBootInfo(
        child_name=child_name,
        sensor_prefix=SENSOR_PREFIX,
        account_type="eleve",
        child_class_name="3eme A",
        child_establishment="College Victor Hugo",
        current_period_name=CURRENT_PERIOD,
        previous_period_names=tuple(previous_period_names),
    )


def _seed_cache(hass_storage, boot_info: PronoteBootInfo | None = None, raw=None) -> None:
    """Pre-populate the boot cache as a previous Home Assistant run would."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": raw if raw is not None else (boot_info or _cached_boot_info()).as_dict(),
    }


def _mock_client(fetch_result=None, gate: asyncio.Event | None = None):
    """Return a mocked PronoteAPIClient whose session is already valid."""
    client = MagicMock()
    client.is_authenticated = MagicMock(return_value=True)
    client.check_session = AsyncMock(return_value=True)
    client.authenticate = AsyncMock()
    client.reset = MagicMock()
    client.get_credentials = MagicMock(return_value=None)
    client._client = None

    async def _fetch(**kwargs):
        if gate is not None:
            await gate.wait()
        if isinstance(fetch_result, Exception):
            raise fetch_result
        return fetch_result if fetch_result is not None else _pronote_data()

    client.fetch_all_data = AsyncMock(side_effect=_fetch)
    return client


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=CHILD_NAME,
        data=ENTRY_DATA,
        options=ENTRY_OPTIONS,
        version=2,
        entry_id=ENTRY_ID,
    )
    entry.add_to_hass(hass)
    return entry


def _unique_ids(hass: HomeAssistant, entry_id: str) -> set[str]:
    registry = er.async_get(hass)
    return {e.unique_id for e in er.async_entries_for_config_entry(registry, entry_id)}


def _device_identifiers(hass: HomeAssistant, entry_id: str) -> set[frozenset]:
    registry = dr.async_get(hass)
    return {frozenset(d.identifiers) for d in dr.async_entries_for_config_entry(registry, entry_id)}


# ---------------------------------------------------------------------------
# Cold boot: no cache, historical blocking behaviour
# ---------------------------------------------------------------------------


class TestColdBoot:
    async def test_blocking_first_refresh_and_cache_written(self, hass: HomeAssistant, hass_storage):
        entry = _entry(hass)
        client = _mock_client()

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done(wait_background_tasks=True)

        assert entry.state is ConfigEntryState.LOADED
        # Data was fetched before the platforms were forwarded.
        client.fetch_all_data.assert_awaited_once()
        assert entry.runtime_data.data is not None
        assert entry.runtime_data.booted_from_cache is False
        # The snapshot is on disk for the next start.
        assert hass_storage[STORAGE_KEY]["data"]["child_name"] == CHILD_NAME
        assert hass_storage[STORAGE_KEY]["data"]["sensor_prefix"] == SENSOR_PREFIX
        assert hass_storage[STORAGE_KEY]["data"]["previous_period_names"] == list(PREVIOUS_PERIODS)

    async def test_failed_first_refresh_keeps_retrying(self, hass: HomeAssistant, hass_storage):
        """Without a cache, an unreachable Pronote must fail the setup as before."""
        from custom_components.pronote.api import ConnectionError as PronoteConnectionError

        entry = _entry(hass)
        client = _mock_client(fetch_result=PronoteConnectionError("boom"))

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            assert not await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert STORAGE_KEY not in hass_storage

    async def test_corrupted_cache_falls_back_to_the_blocking_path(self, hass: HomeAssistant, hass_storage):
        _seed_cache(hass_storage, raw={"child_name": "Jean Dupont"})  # no sensor_prefix
        entry = _entry(hass)
        client = _mock_client()

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done(wait_background_tasks=True)

        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data.booted_from_cache is False
        client.fetch_all_data.assert_awaited_once()
        # The corrupted payload has been replaced by a valid one.
        assert hass_storage[STORAGE_KEY]["data"]["sensor_prefix"] == SENSOR_PREFIX


# ---------------------------------------------------------------------------
# Warm boot: entities before the network
# ---------------------------------------------------------------------------


class TestWarmBoot:
    async def test_platforms_are_created_before_the_first_fetch(self, hass: HomeAssistant, hass_storage):
        """The whole point: setup completes while Pronote is still being queried."""
        _seed_cache(hass_storage)
        entry = _entry(hass)
        gate = asyncio.Event()
        client = _mock_client(gate=gate)

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            # The timeout is the assertion: setup must not wait for the fetch.
            async with asyncio.timeout(SETUP_TIMEOUT):
                assert await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

            # Setup returned, entities exist, and the fetch is still in flight.
            assert entry.state is ConfigEntryState.LOADED
            assert entry.runtime_data.booted_from_cache is True
            assert entry.runtime_data.data is None
            assert not gate.is_set()

            entity_ids = [e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)]
            assert len(entity_ids) > 20
            assert any(entity_id.startswith("calendar.") for entity_id in entity_ids)

            # Every entity is unavailable until data lands, and no property raised.
            states = [hass.states.get(entity_id) for entity_id in entity_ids]
            live = [state for state in states if state is not None]
            assert live
            assert all(state.state == STATE_UNAVAILABLE for state in live)

            # Release the background refresh.
            gate.set()
            await hass.async_block_till_done(wait_background_tasks=True)

        assert entry.runtime_data.data is not None
        refreshed = [hass.states.get(entity_id) for entity_id in entity_ids]
        assert any(state is not None and state.state != STATE_UNAVAILABLE for state in refreshed)

    async def test_background_refresh_failure_leaves_entities_unavailable(self, hass: HomeAssistant, hass_storage):
        from custom_components.pronote.api import ConnectionError as PronoteConnectionError

        _seed_cache(hass_storage)
        entry = _entry(hass)
        client = _mock_client(fetch_result=PronoteConnectionError("network down"))

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done(wait_background_tasks=True)

        # The entry stays loaded: entities exist but report unavailable.
        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data.data is None
        assert entry.runtime_data.last_update_success is False

        entity_ids = [e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)]
        states = [hass.states.get(entity_id) for entity_id in entity_ids]
        live = [state for state in states if state is not None]
        assert live
        assert all(state.state == STATE_UNAVAILABLE for state in live)

    async def test_auth_failure_in_background_starts_a_reauth_flow(self, hass: HomeAssistant, hass_storage):
        """async_refresh (not first_refresh) must still surface a reauth flow."""
        from custom_components.pronote.api import AuthenticationError

        _seed_cache(hass_storage)
        entry = _entry(hass)
        client = _mock_client()
        client.check_session = AsyncMock(return_value=False)
        client.authenticate = AsyncMock(side_effect=AuthenticationError("bad password"))

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done(wait_background_tasks=True)

        assert entry.state is ConfigEntryState.LOADED
        flows = [flow for flow in hass.config_entries.flow.async_progress() if flow["handler"] == DOMAIN]
        assert [flow for flow in flows if flow["context"]["source"] == "reauth"]


# ---------------------------------------------------------------------------
# Non-regression: identifiers must not move
# ---------------------------------------------------------------------------


class TestIdentifiersNonRegression:
    async def test_warm_boot_reuses_the_exact_same_registry_entries(self, hass: HomeAssistant, hass_storage):
        """A single differing unique_id would duplicate every entity of the user."""
        entry = _entry(hass)
        client = _mock_client()

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done(wait_background_tasks=True)

            cold_unique_ids = _unique_ids(hass, entry.entry_id)
            cold_devices = _device_identifiers(hass, entry.entry_id)
            assert cold_unique_ids
            assert cold_devices == {frozenset({(DOMAIN, CHILD_NAME)})}

            # Reload: the boot cache is now on disk, entities are built from it
            # while the refresh is still gated.
            gate = asyncio.Event()
            client.fetch_all_data.side_effect = _mock_client(gate=gate).fetch_all_data.side_effect
            async with asyncio.timeout(SETUP_TIMEOUT):
                await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()

            assert entry.runtime_data.booted_from_cache is True
            assert entry.runtime_data.data is None

            warm_unique_ids = _unique_ids(hass, entry.entry_id)
            warm_devices = _device_identifiers(hass, entry.entry_id)

            gate.set()
            await hass.async_block_till_done(wait_background_tasks=True)

        assert warm_unique_ids == cold_unique_ids
        assert len(warm_unique_ids) == len(cold_unique_ids)
        assert warm_devices == cold_devices

    async def test_new_period_triggers_a_single_reload(self, hass: HomeAssistant, hass_storage):
        """The cache lags one period behind; the entry reloads to catch up."""
        _seed_cache(hass_storage, _cached_boot_info(previous_period_names=("Trimestre 1",)))
        entry = _entry(hass)
        client = _mock_client(fetch_result=_pronote_data(previous_period_names=("Trimestre 1", "Trimestre 2")))

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done(wait_background_tasks=True)
            await hass.async_block_till_done(wait_background_tasks=True)

            assert hass_storage[STORAGE_KEY]["data"]["previous_period_names"] == [
                "Trimestre 1",
                "Trimestre 2",
            ]
            # After the reload the sensors of the new period exist.
            unique_ids = _unique_ids(hass, entry.entry_id)
            assert f"{DOMAIN}_{SENSOR_PREFIX}_Grades Trimestre 2" in unique_ids
            # And the layout is stable now: no further reload is needed.
            assert entry.runtime_data.boot_info.previous_period_names == ("Trimestre 1", "Trimestre 2")
            assert entry.runtime_data._boot_reload_scheduled is False


# ---------------------------------------------------------------------------
# Entry removal
# ---------------------------------------------------------------------------


class TestRemoveEntry:
    async def test_removing_the_entry_deletes_the_cache(self, hass: HomeAssistant, hass_storage):
        entry = _entry(hass)
        client = _mock_client()

        with patch("custom_components.pronote.coordinator.PronoteAPIClient", return_value=client):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done(wait_background_tasks=True)
            assert STORAGE_KEY in hass_storage

            await hass.config_entries.async_remove(entry.entry_id)
            await hass.async_block_till_done()

        assert STORAGE_KEY not in hass_storage


# ---------------------------------------------------------------------------
# Unit-level identifier lock (no hass): cold vs warm entity construction
# ---------------------------------------------------------------------------


def _fake_coordinator(data, boot_info):
    from custom_components.pronote.coordinator import PronoteDataUpdateCoordinator

    with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
        coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
    coord.data = data
    coord.boot_info = boot_info
    coord.booted_from_cache = boot_info is not None
    coord.last_update_success = data is not None
    coord.last_update_success_time = datetime(2025, 1, 15, 10, 0)
    entry = MagicMock()
    entry.options = ENTRY_OPTIONS
    entry.runtime_data = coord
    coord.config_entry = entry
    return coord


async def _build_entities(data, boot_info):
    """Run both platform setups and return the created entities."""
    from custom_components.pronote import calendar as calendar_platform
    from custom_components.pronote import sensor as sensor_platform

    coordinator = _fake_coordinator(data, boot_info)
    created: list = []

    def _add(entities, update_before_add=False):
        created.extend(entities)

    await sensor_platform.async_setup_entry(MagicMock(), coordinator.config_entry, _add)
    await calendar_platform.async_setup_entry(MagicMock(), coordinator.config_entry, _add)
    return created


def _full_data():
    """coordinator.data as the coordinator builds it after a refresh."""
    pronote_data = _pronote_data()
    data = {
        "account_type": "eleve",
        "sensor_prefix": SENSOR_PREFIX,
        "child_info": pronote_data.child_info,
        "current_period": pronote_data.current_period,
        "previous_periods": pronote_data.previous_periods,
        "periods": pronote_data.periods,
        "active_periods": pronote_data.active_periods,
        "ical_url": pronote_data.ical_url,
        "next_alarm": None,
    }
    data |= pronote_data.previous_period_data
    return data


# Captured by running the pre-boot-cache code (git tag v1.1.13) against the
# payload built by _full_data(). Any diff here means the user's entity registry
# would gain duplicates on upgrade: do NOT "fix" the golden list, fix the code.
GOLDEN_UNIQUE_IDS = [
    "pronote_jean_dupont_Class",
    "pronote_jean_dupont_Today's timetable",
    "pronote_jean_dupont_Tomorrow's timetable",
    "pronote_jean_dupont_Next day's timetable",
    "pronote_jean_dupont_Period's timetable",
    "pronote_jean_dupont_Homework",
    "pronote_jean_dupont_Period's homework",
    "pronote_jean_dupont_Grades",
    "pronote_jean_dupont_Absences",
    "pronote_jean_dupont_Evaluations",
    "pronote_jean_dupont_Averages",
    "pronote_jean_dupont_Punishments",
    "pronote_jean_dupont_Delays",
    "pronote_jean_dupont_Information and surveys",
    "pronote_jean_dupont_Timetable iCal URL",
    "pronote_jean_dupont_Next alarm",
    "pronote_jean_dupont_Menus",
    "pronote_jean_dupont_Overall average",
    "pronote_jean_dupont_Current period",
    "pronote_jean_dupont_Periods",
    "pronote_jean_dupont_previous Periods",
    "pronote_jean_dupont_Active periods",
    "pronote_jean_dupont_Grades Trimestre 1",
    "pronote_jean_dupont_Averages Trimestre 1",
    "pronote_jean_dupont_Absences Trimestre 1",
    "pronote_jean_dupont_Delays Trimestre 1",
    "pronote_jean_dupont_Evaluations Trimestre 1",
    "pronote_jean_dupont_Punishments Trimestre 1",
    "pronote_jean_dupont_Overall average Trimestre 1",
    "pronote_jean_dupont_timetable",
]

GOLDEN_TRANSLATION_KEYS = [
    "child_class",
    "timetable_today",
    "timetable_tomorrow",
    "timetable_next_day",
    "timetable_period",
    "homework",
    "homework_period",
    "grades",
    "absences",
    "evaluations",
    "averages",
    "punishments",
    "delays",
    "information_and_surveys",
    "ical_url",
    "next_alarm",
    "menus",
    "overall_average",
    "current_period",
    "periods",
    "previous_periods",
    "active_periods",
    "grades_period",
    "averages_period",
    "absences_period",
    "delays_period",
    "evaluations_period",
    "punishments_period",
    "overall_average_period",
    "timetable",
]


class TestGoldenIdentifiers:
    """Absolute lock on the identifiers produced before the boot cache existed."""

    @pytest.mark.parametrize("from_cache", [False, True])
    async def test_unique_ids_match_the_pre_cache_release(self, from_cache):
        data = _full_data()
        boot_info = boot_info_from_data(data)
        entities = await _build_entities(None if from_cache else data, boot_info if from_cache else None)

        assert [e._attr_unique_id for e in entities] == GOLDEN_UNIQUE_IDS

    @pytest.mark.parametrize("from_cache", [False, True])
    async def test_device_info_matches_the_pre_cache_release(self, from_cache):
        data = _full_data()
        boot_info = boot_info_from_data(data)
        entities = await _build_entities(None if from_cache else data, boot_info if from_cache else None)

        for entity in entities:
            device_info = entity._attr_device_info
            assert device_info["identifiers"] == {("pronote", "Jean Dupont")}
            assert device_info["name"] == "Pronote - Jean Dupont"
            assert device_info["model"] == "Jean Dupont"
            assert device_info["manufacturer"] == "Pronote"

    @pytest.mark.parametrize("from_cache", [False, True])
    async def test_translation_keys_match_the_pre_cache_release(self, from_cache):
        data = _full_data()
        boot_info = boot_info_from_data(data)
        entities = await _build_entities(None if from_cache else data, boot_info if from_cache else None)

        assert [e._attr_translation_key for e in entities] == GOLDEN_TRANSLATION_KEYS


class TestEntityIdentifiersColdVsWarm:
    async def test_unique_ids_and_device_identifiers_are_byte_identical(self):
        data = _full_data()
        boot_info = boot_info_from_data(data)

        cold = await _build_entities(data, None)
        warm = await _build_entities(None, boot_info)

        assert len(cold) == len(warm)
        assert [e._attr_unique_id for e in cold] == [e._attr_unique_id for e in warm]
        assert [e._attr_device_info["identifiers"] for e in cold] == [e._attr_device_info["identifiers"] for e in warm]
        assert [e._attr_device_info["name"] for e in cold] == [e._attr_device_info["name"] for e in warm]
        assert [e._attr_device_info["model"] for e in cold] == [e._attr_device_info["model"] for e in warm]

    async def test_translation_keys_and_placeholders_are_identical(self):
        data = _full_data()
        boot_info = boot_info_from_data(data)

        cold = await _build_entities(data, None)
        warm = await _build_entities(None, boot_info)

        assert [e._attr_translation_key for e in cold] == [e._attr_translation_key for e in warm]
        assert [getattr(e, "_attr_translation_placeholders", None) for e in cold] == [
            getattr(e, "_attr_translation_placeholders", None) for e in warm
        ]
        assert [getattr(e, "_is_current_period", None) for e in cold] == [
            getattr(e, "_is_current_period", None) for e in warm
        ]

    async def test_no_property_raises_while_data_is_none(self):
        """Every entity must survive a state write before the first refresh."""
        boot_info = boot_info_from_data(_full_data())
        entities = await _build_entities(None, boot_info)

        for entity in entities:
            assert entity.available is False
            # Properties must answer, not raise.
            assert entity.extra_state_attributes is None or isinstance(entity.extra_state_attributes, dict)
            if hasattr(entity, "native_value"):
                assert entity.native_value is None

    async def test_setup_without_data_nor_cache_is_not_ready(self):
        from homeassistant.exceptions import PlatformNotReady

        with pytest.raises(PlatformNotReady):
            await _build_entities(None, None)
