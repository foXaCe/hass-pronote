"""Tests for the Pronote calendar module."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from custom_components.pronote.calendar import (
    PronoteCalendar,
    async_get_calendar_event_from_lessons,
)
from custom_components.pronote.coordinator import PronoteDataUpdateCoordinator


def _make_coordinator(data=None, options=None):
    """Create a minimal coordinator for testing."""
    with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
        coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
    coord.data = data or {}
    entry = MagicMock()
    entry.options = options or {"nickname": ""}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.last_update_success_time = datetime(2025, 1, 15, 10, 0)
    return coord


class TestAsyncGetCalendarEventFromLessons:
    def test_basic_lesson(self, mock_lesson):
        lesson = mock_lesson(
            subject_name="Français",
            start=datetime(2025, 1, 15, 8, 0),
            teacher_name="Mme Martin",
            classroom="B202",
        )
        event = async_get_calendar_event_from_lessons(lesson, "Europe/Paris")

        assert event.summary == "Français"
        assert "Mme Martin" in event.description
        assert "B202" in event.location
        assert event.start.tzinfo == ZoneInfo("Europe/Paris")
        assert event.end.tzinfo == ZoneInfo("Europe/Paris")

    def test_canceled_lesson(self, mock_lesson):
        lesson = mock_lesson(subject_name="Maths", canceled=True)
        event = async_get_calendar_event_from_lessons(lesson, "Europe/Paris")

        assert event.summary.startswith("Annulé")
        assert "Maths" in event.summary

    def test_detention_lesson(self, mock_lesson):
        lesson = mock_lesson(detention=True)
        event = async_get_calendar_event_from_lessons(lesson, "Europe/Paris")

        assert event.summary == "RETENUE"

    def test_canceled_detention(self, mock_lesson):
        lesson = mock_lesson(detention=True, canceled=True)
        event = async_get_calendar_event_from_lessons(lesson, "Europe/Paris")

        assert event.summary == "Annulé - RETENUE"

    def test_timezone_applied(self, mock_lesson):
        lesson = mock_lesson(start=datetime(2025, 1, 15, 8, 0))
        event = async_get_calendar_event_from_lessons(lesson, "America/New_York")

        assert event.start.tzinfo == ZoneInfo("America/New_York")


class TestPronoteCalendar:
    def test_init_with_nickname(self, mock_lesson):
        """When nickname is set, calendar_name uses the nickname."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
        }
        coord = _make_coordinator(data=data, options={"nickname": "Jeanot"})
        cal = PronoteCalendar(coord)

        assert cal._attr_translation_key == "timetable"
        assert cal._attr_translation_placeholders["child"] == "Jeanot"

    def test_init_without_nickname(self, mock_lesson):
        """When nickname is empty, calendar_name uses child_info.name."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
        }
        coord = _make_coordinator(data=data, options={"nickname": ""})
        cal = PronoteCalendar(coord)

        assert cal._attr_translation_key == "timetable"
        assert cal._attr_translation_placeholders["child"] == "Jean Dupont"

    def test_unique_id(self):
        """Verify unique_id format is pronote_{sensor_prefix}_timetable."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
        }
        coord = _make_coordinator(data=data)
        cal = PronoteCalendar(coord)

        assert cal._attr_unique_id == "pronote_jean_dupont_timetable"

    def test_event_property(self, mock_lesson):
        """The event property returns self._event."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
        }
        coord = _make_coordinator(data=data)
        cal = PronoteCalendar(coord)

        # Initially None
        assert cal.event is None

        # Set an event manually to verify property
        from homeassistant.components.calendar import CalendarEvent

        ev = CalendarEvent(
            summary="Test",
            start=datetime(2025, 1, 15, 8, 0, tzinfo=ZoneInfo("Europe/Paris")),
            end=datetime(2025, 1, 15, 9, 0, tzinfo=ZoneInfo("Europe/Paris")),
        )
        cal._event = ev
        assert cal.event is ev


class TestHandleCoordinatorUpdate:
    def _make_calendar(self, data, options=None):
        """Helper to create a PronoteCalendar with mocked hass."""
        coord = _make_coordinator(data=data, options=options)
        cal = PronoteCalendar(coord)
        cal.hass = MagicMock()
        cal.hass.config.time_zone = "Europe/Paris"
        cal.async_write_ha_state = MagicMock()
        return cal

    def test_no_lessons(self):
        """When lessons_period is None, event is None."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
            "lessons_period": None,
        }
        cal = self._make_calendar(data)
        cal._handle_coordinator_update()

        assert cal.event is None

    def test_empty_lessons(self):
        """When lessons_period is an empty list, event is None."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
            "lessons_period": [],
        }
        cal = self._make_calendar(data)
        cal._handle_coordinator_update()

        assert cal.event is None

    def test_current_event_found(self, mock_lesson):
        """When a lesson matches now, the event is set."""
        now = datetime.now()
        lesson = mock_lesson(
            subject_name="Français",
            start=now - timedelta(minutes=10),
            end=now + timedelta(minutes=50),
            teacher_name="Mme Martin",
            classroom="B202",
        )
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
            "lessons_period": [lesson],
        }
        cal = self._make_calendar(data)
        cal._handle_coordinator_update()

        assert cal.event is not None
        assert cal.event.summary == "Français"

    def test_no_current_event(self, mock_lesson):
        """When no lesson matches now, event is None."""
        past_lesson = mock_lesson(
            start=datetime(2025, 1, 15, 8, 0),
            end=datetime(2025, 1, 15, 9, 0),
        )
        future_lesson = mock_lesson(
            start=datetime(2099, 12, 31, 8, 0),
            end=datetime(2099, 12, 31, 9, 0),
        )
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
            "lessons_period": [past_lesson, future_lesson],
        }
        cal = self._make_calendar(data)
        cal._handle_coordinator_update()

        assert cal.event is None


class TestAsyncGetEvents:
    def _make_calendar(self, data, options=None):
        """Helper to create a PronoteCalendar with mocked hass."""
        coord = _make_coordinator(data=data, options=options)
        cal = PronoteCalendar(coord)
        cal.hass = MagicMock()
        cal.hass.config.time_zone = "Europe/Paris"
        cal.async_write_ha_state = MagicMock()
        return cal

    async def test_returns_events_in_range(self, mock_lesson):
        """Only lessons within the requested date range are returned."""
        in_range = mock_lesson(
            subject_name="Maths",
            start=datetime(2025, 1, 15, 8, 0),
            end=datetime(2025, 1, 15, 9, 0),
        )
        out_of_range = mock_lesson(
            subject_name="Français",
            start=datetime(2025, 2, 15, 8, 0),
            end=datetime(2025, 2, 15, 9, 0),
        )
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
            "lessons_period": [in_range, out_of_range],
        }
        cal = self._make_calendar(data)

        hass = MagicMock()
        hass.config.time_zone = "Europe/Paris"

        events = await cal.async_get_events(
            hass,
            start_date=datetime(2025, 1, 14),
            end_date=datetime(2025, 1, 16),
        )

        assert len(events) == 1
        assert events[0].summary == "Maths"

    async def test_no_lessons(self):
        """When lessons_period is None, an empty list is returned."""
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
            "lessons_period": None,
        }
        cal = self._make_calendar(data)

        hass = MagicMock()
        hass.config.time_zone = "Europe/Paris"

        events = await cal.async_get_events(
            hass,
            start_date=datetime(2025, 1, 14),
            end_date=datetime(2025, 1, 16),
        )

        assert events == []

    async def test_canceled_lessons_excluded(self, mock_lesson):
        """Canceled lessons should be filtered out of async_get_events."""
        active = mock_lesson(
            subject_name="Maths",
            start=datetime(2025, 1, 15, 8, 0),
            end=datetime(2025, 1, 15, 9, 0),
            canceled=False,
        )
        canceled = mock_lesson(
            subject_name="Français",
            start=datetime(2025, 1, 15, 10, 0),
            end=datetime(2025, 1, 15, 11, 0),
            canceled=True,
        )
        data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
            "lessons_period": [active, canceled],
        }
        cal = self._make_calendar(data)

        hass = MagicMock()
        hass.config.time_zone = "Europe/Paris"

        events = await cal.async_get_events(
            hass,
            start_date=datetime(2025, 1, 14),
            end_date=datetime(2025, 1, 16),
        )

        assert len(events) == 1
        assert events[0].summary == "Maths"
