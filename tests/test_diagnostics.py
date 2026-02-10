"""Tests for the Pronote diagnostics module."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.pronote.diagnostics import (
    _safe_len,
    async_get_config_entry_diagnostics,
)


class TestSafeLen:
    def test_with_list(self):
        """Returns len for a non-empty list."""
        assert _safe_len([1, 2, 3]) == 3

    def test_with_none(self):
        """Returns None for None input."""
        assert _safe_len(None) is None

    def test_with_empty_list(self):
        """Returns 0 for an empty list."""
        assert _safe_len([]) == 0


def _make_entry_and_coordinator(
    entry_data=None,
    entry_options=None,
    coordinator_data=None,
    last_update_success=True,
):
    """Build mock entry and coordinator for diagnostics tests."""
    entry = MagicMock()
    entry.data = entry_data or {
        "username": "secret_user",
        "password": "secret_pass",
        "account_type": "eleve",
        "connection_type": "username_password",
    }
    entry.options = entry_options or {"nickname": "Jean"}

    coordinator = MagicMock()
    coordinator.data = coordinator_data
    coordinator.last_update_success = last_update_success
    coordinator.last_update_success_time = datetime(2025, 1, 15, 10, 0)
    coordinator.update_interval = timedelta(minutes=15)

    entry.runtime_data = coordinator
    return entry, coordinator


class TestAsyncGetConfigEntryDiagnostics:
    async def test_redacts_sensitive_data(self):
        """Sensitive fields like password and username are redacted."""
        entry, _ = _make_entry_and_coordinator(
            coordinator_data={
                "child_info": SimpleNamespace(
                    name="Jean", class_name="3A", establishment="College"
                ),
                "account_type": "eleve",
                "current_period": SimpleNamespace(name="Trimestre 1"),
            },
        )
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["config_entry"]["username"] == "**REDACTED**"
        assert result["config_entry"]["password"] == "**REDACTED**"
        # Non-sensitive fields are preserved
        assert result["config_entry"]["account_type"] == "eleve"

    async def test_returns_coordinator_status(self):
        """Verify last_update_success, update_interval, and child_info."""
        entry, _ = _make_entry_and_coordinator(
            coordinator_data={
                "child_info": SimpleNamespace(
                    name="Jean", class_name="3A", establishment="College"
                ),
                "account_type": "eleve",
                "current_period": SimpleNamespace(name="Trimestre 1"),
            },
        )
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        coord_result = result["coordinator"]
        assert coord_result["last_update_success"] is True
        assert "0:15:00" in coord_result["update_interval"]
        assert coord_result["child_info"]["name"] == "Jean"
        assert coord_result["child_info"]["class_name"] == "3A"
        assert coord_result["child_info"]["establishment"] == "College"
        assert coord_result["account_type"] == "eleve"
        assert coord_result["current_period"] == "Trimestre 1"

    async def test_returns_sensor_counts(self):
        """Verify all sensor count keys are present in the output."""
        entry, _ = _make_entry_and_coordinator(
            coordinator_data={
                "child_info": SimpleNamespace(
                    name="Jean", class_name="3A", establishment="College"
                ),
                "account_type": "eleve",
                "current_period": SimpleNamespace(name="Trimestre 1"),
                "lessons_today": [1, 2],
                "lessons_tomorrow": [3],
                "lessons_next_day": [],
                "lessons_period": [1, 2, 3, 4],
                "grades": [1],
                "averages": [1, 2],
                "homework": None,
                "homework_period": [1],
                "absences": [],
                "delays": [1],
                "evaluations": [1, 2, 3],
                "punishments": None,
                "menus": [1],
                "information_and_surveys": [1, 2],
                "periods": [1, 2, 3],
                "previous_periods": [],
                "overall_average": "14.5",
            },
        )
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        counts = result["coordinator"]["sensor_counts"]
        assert counts["lessons_today"] == 2
        assert counts["lessons_tomorrow"] == 1
        assert counts["lessons_next_day"] == 0
        assert counts["lessons_period"] == 4
        assert counts["grades"] == 1
        assert counts["averages"] == 2
        assert counts["homework"] is None
        assert counts["homework_period"] == 1
        assert counts["absences"] == 0
        assert counts["delays"] == 1
        assert counts["evaluations"] == 3
        assert counts["punishments"] is None
        assert counts["menus"] == 1
        assert counts["information_and_surveys"] == 2
        assert counts["periods"] == 3
        assert counts["previous_periods"] == 0
        assert result["coordinator"]["overall_average"] == "14.5"

    async def test_with_no_coordinator_data(self):
        """When coordinator.data is None or empty, handles gracefully."""
        entry, coordinator = _make_entry_and_coordinator(coordinator_data=None)
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        coord_result = result["coordinator"]
        assert coord_result["child_info"]["name"] is None
        assert coord_result["child_info"]["class_name"] is None
        assert coord_result["child_info"]["establishment"] is None
        assert coord_result["account_type"] is None
        assert coord_result["current_period"] is None

    async def test_with_no_child_info(self):
        """When child_info is None, corresponding fields are None."""
        entry, _ = _make_entry_and_coordinator(
            coordinator_data={
                "account_type": "eleve",
                "current_period": SimpleNamespace(name="Trimestre 1"),
            },
        )
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        coord_result = result["coordinator"]
        assert coord_result["child_info"]["name"] is None
        assert coord_result["child_info"]["class_name"] is None
        assert coord_result["child_info"]["establishment"] is None
