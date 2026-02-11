"""Tests for the coordinator compare_data and trigger_event methods."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.pronote.coordinator import PronoteDataUpdateCoordinator


def _make_coordinator():
    """Create a minimal coordinator for testing compare_data and trigger_event."""
    hass = MagicMock()
    entry = MagicMock()
    entry.title = "Test"
    entry.options = {"refresh_interval": 15, "nickname": "Jean"}

    with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
        coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
        coord.hass = hass
        coord.config_entry = entry
        coord.data = {}
    return coord


def _make_grade(date_val, subject, grade_out_of):
    return SimpleNamespace(
        date=date_val,
        subject=SimpleNamespace(name=subject),
        grade=grade_out_of.split("/")[0],
        out_of=grade_out_of.split("/")[1],
        default_out_of="20",
        coefficient="1",
        average="12",
        max="18",
        min="5",
        comment="",
        is_bonus=False,
        is_optionnal=False,
        is_out_of_20=True,
    )


class TestCompareData:
    def test_no_previous_data(self):
        coord = _make_coordinator()
        coord.data = {"grades": [_make_grade(date(2025, 1, 15), "Maths", "15/20")]}

        # Should not raise
        coord._compare_data(None, "grades", ["date", "subject", "grade_out_of"], "new_grade", _format_grade)

    def test_previous_data_none_key(self):
        coord = _make_coordinator()
        coord.data = {"grades": [_make_grade(date(2025, 1, 15), "Maths", "15/20")]}

        # Should not raise
        coord._compare_data({"grades": None}, "grades", ["date", "subject", "grade_out_of"], "new_grade", _format_grade)

    def test_current_data_none(self):
        coord = _make_coordinator()
        coord.data = {"grades": None}

        # Should not raise
        coord._compare_data(
            {"grades": [_make_grade(date(2025, 1, 15), "Maths", "15/20")]},
            "grades",
            ["date", "subject", "grade_out_of"],
            "new_grade",
            _format_grade,
        )

    def test_detects_new_items(self):
        coord = _make_coordinator()
        coord.data = {
            "child_info": SimpleNamespace(name="Jean"),
            "sensor_prefix": "jean",
            "grades": [
                _make_grade(date(2025, 1, 15), "Maths", "15/20"),
                _make_grade(date(2025, 1, 16), "Français", "12/20"),
            ],
        }

        previous = {
            "grades": [_make_grade(date(2025, 1, 15), "Maths", "15/20")],
        }

        coord._compare_data(previous, "grades", ["date", "subject", "grade_out_of"], "new_grade", _format_grade)

        # Should fire one event for the new Français grade
        coord.hass.bus.async_fire.assert_called_once()
        call_args = coord.hass.bus.async_fire.call_args
        assert call_args[0][1]["type"] == "new_grade"

    def test_no_new_items(self):
        coord = _make_coordinator()
        grade = _make_grade(date(2025, 1, 15), "Maths", "15/20")
        coord.data = {
            "child_info": SimpleNamespace(name="Jean"),
            "sensor_prefix": "jean",
            "grades": [grade],
        }

        previous = {"grades": [grade]}

        coord._compare_data(previous, "grades", ["date", "subject", "grade_out_of"], "new_grade", _format_grade)

        coord.hass.bus.async_fire.assert_not_called()


class TestTriggerEvent:
    def test_fires_event(self):
        coord = _make_coordinator()
        coord.data = {
            "child_info": SimpleNamespace(name="Jean Dupont"),
            "sensor_prefix": "jean_dupont",
        }

        event_data = {"date": "2025-01-15", "subject": "Maths"}
        coord._trigger_event("new_grade", event_data)

        coord.hass.bus.async_fire.assert_called_once()
        call_args = coord.hass.bus.async_fire.call_args
        assert call_args[0][0] == "pronote_event"
        fired_data = call_args[0][1]
        assert fired_data["child_name"] == "Jean Dupont"
        assert fired_data["child_slug"] == "jean_dupont"
        assert fired_data["child_nickname"] == "Jean"
        assert fired_data["type"] == "new_grade"
        assert fired_data["data"] == event_data


def _format_grade(grade):
    """Simplified format_grade for testing."""
    return {
        "date": grade.date,
        "subject": grade.subject.name,
        "grade_out_of": grade.grade + "/" + grade.out_of,
    }
