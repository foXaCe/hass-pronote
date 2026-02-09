"""Tests for the Pronote calendar module."""

from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.pronote.calendar import async_get_calendar_event_from_lessons


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
