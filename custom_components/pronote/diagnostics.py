"""Diagnostics support for the Pronote integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import PronoteConfigEntry

TO_REDACT = {
    "password",
    "username",
    "qr_code_json",
    "qr_code_pin",
    "qr_code_password",
    "qr_code_username",
    "qr_code_uuid",
    "jeton",
    "uuid",
    "client_identifier",
    "account_pin",
    "device_name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: PronoteConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}

    child_info = data.get("child_info")

    return {
        "config_entry": async_redact_data(entry.data, TO_REDACT),
        "options": dict(entry.options),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update_success_time": str(coordinator.last_update_success_time),
            "update_interval": str(coordinator.update_interval),
            "child_info": {
                "name": child_info.name if child_info else None,
                "class_name": child_info.class_name if child_info else None,
                "establishment": child_info.establishment if child_info else None,
            },
            "account_type": data.get("account_type"),
            "current_period": data.get("current_period", {}).name if data.get("current_period") else None,
            "sensor_counts": {
                "lessons_today": _safe_len(data.get("lessons_today")),
                "lessons_tomorrow": _safe_len(data.get("lessons_tomorrow")),
                "lessons_next_day": _safe_len(data.get("lessons_next_day")),
                "lessons_period": _safe_len(data.get("lessons_period")),
                "grades": _safe_len(data.get("grades")),
                "averages": _safe_len(data.get("averages")),
                "homework": _safe_len(data.get("homework")),
                "homework_period": _safe_len(data.get("homework_period")),
                "absences": _safe_len(data.get("absences")),
                "delays": _safe_len(data.get("delays")),
                "evaluations": _safe_len(data.get("evaluations")),
                "punishments": _safe_len(data.get("punishments")),
                "menus": _safe_len(data.get("menus")),
                "information_and_surveys": _safe_len(data.get("information_and_surveys")),
                "periods": _safe_len(data.get("periods")),
                "previous_periods": _safe_len(data.get("previous_periods")),
            },
            "overall_average": data.get("overall_average"),
        },
    }


def _safe_len(data) -> int | None:
    """Return the length of data or None if data is None."""
    return len(data) if data is not None else None
