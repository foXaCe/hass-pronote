"""Data update coordinator for the Pronote integration."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import TimestampDataUpdateCoordinator, UpdateFailed
from pronotepy import CryptoError, ENTLoginError, QRCodeDecryptError
from slugify import slugify

from .const import (
    DEFAULT_ALARM_OFFSET,
    DEFAULT_REFRESH_INTERVAL,
    EVENT_TYPE,
    HOMEWORK_MAX_DAYS,
    INFO_SURVEY_LIMIT_MAX_DAYS,
    LESSON_MAX_DAYS,
    LESSON_NEXT_DAY_SEARCH_LIMIT,
    PronoteConfigEntry,
)
from .pronote_formatter import format_absence, format_delay, format_evaluation, format_grade
from .pronote_helper import get_day_start_at, get_pronote_client

_LOGGER = logging.getLogger(__name__)


def get_grades(period):
    try:
        grades = period.grades
        return sorted(grades, key=lambda grade: grade.date, reverse=True)
    except Exception as ex:
        _LOGGER.warning("Error getting grades from period (%s): %s", period.name, ex)
        return None


def get_absences(period):
    try:
        absences = period.absences
        return sorted(absences, key=lambda absence: absence.from_date, reverse=True)
    except Exception as ex:
        _LOGGER.warning("Error getting absences from period (%s): %s", period.name, ex)
        return None


def get_delays(period):
    try:
        delays = period.delays
        return sorted(delays, key=lambda delay: delay.date, reverse=True)
    except Exception as ex:
        _LOGGER.warning("Error getting delays from period (%s): %s", period.name, ex)
        return None


def get_averages(period):
    try:
        averages = period.averages
        return averages
    except Exception as ex:
        _LOGGER.warning("Error getting averages from period (%s): %s", period.name, ex)
        return None


def get_punishments(period):
    try:
        punishments = period.punishments
        return sorted(
            punishments,
            key=lambda punishment: punishment.given.strftime("%Y-%m-%d"),
            reverse=True,
        )
    except Exception as ex:
        _LOGGER.warning("Error getting punishments from period (%s): %s", period.name, ex)
        return None


def get_evaluations(period):
    try:
        evaluations = period.evaluations
        evaluations = sorted(evaluations, key=lambda evaluation: evaluation.name)
        return sorted(evaluations, key=lambda evaluation: evaluation.date, reverse=True)
    except Exception as ex:
        _LOGGER.warning("Error getting evaluations from period (%s): %s", period.name, ex)
        return None


def get_overall_average(period):
    try:
        return period.overall_average
    except Exception as ex:
        _LOGGER.warning("Error getting overall average from period (%s): %s", period.name, ex)
        return None


def _fetch_all_sync_data(client, config_data: dict, today: date) -> dict[str, Any]:
    """Fetch all data from Pronote in a single sync call.

    This runs in the executor thread. Since pronotepy uses a single sync HTTP
    session, batching all calls here avoids ~20+ async↔sync context switches.
    """
    data: dict[str, Any] = {}

    # Credentials
    data["credentials"] = client.export_credentials()
    data["password"] = client.password

    # Child info
    child_info = client.info
    if config_data["account_type"] == "parent":
        client.set_child(config_data["child"])
        child_info = client._selected_child
    data["child_info"] = child_info

    # Lessons
    try:
        lessons_today = client.lessons(today)
        data["lessons_today"] = sorted(lessons_today, key=lambda lesson: lesson.start)
    except Exception as ex:
        data["lessons_today"] = None
        _LOGGER.warning("Error getting lessons_today from pronote: %s", ex)

    try:
        lessons_tomorrow = client.lessons(today + timedelta(days=1))
        data["lessons_tomorrow"] = sorted(lessons_tomorrow, key=lambda lesson: lesson.start)
    except Exception as ex:
        data["lessons_tomorrow"] = None
        _LOGGER.warning("Error getting lessons_tomorrow from pronote: %s", ex)

    lessons_period = None
    delta = LESSON_MAX_DAYS
    while delta > 0:
        try:
            lessons_period = client.lessons(today, today + timedelta(days=delta))
        except Exception as ex:
            _LOGGER.debug("No lessons at: %s from today, searching best earlier alternative (%s)", delta, ex)
        if lessons_period:
            break
        delta -= 1
    _LOGGER.debug("Lessons found at: %s days, for a maximum of %s from today", delta, LESSON_MAX_DAYS)
    data["lessons_period"] = (
        sorted(lessons_period, key=lambda lesson: lesson.start) if lessons_period is not None else None
    )

    # Next day lessons
    if data["lessons_tomorrow"] is not None and len(data["lessons_tomorrow"]) > 0:
        data["lessons_next_day"] = data["lessons_tomorrow"]
    else:
        try:
            lessons_nextday = None
            delta = 2
            while delta < LESSON_NEXT_DAY_SEARCH_LIMIT:
                lessons_nextday = client.lessons(today + timedelta(days=delta))
                if lessons_nextday:
                    break
                lessons_nextday = None
                delta += 1
            if lessons_nextday is not None:
                data["lessons_next_day"] = sorted(lessons_nextday, key=lambda lesson: lesson.start)
            else:
                data["lessons_next_day"] = None
        except Exception as ex:
            data["lessons_next_day"] = None
            _LOGGER.warning("Error getting lessons_next_day from pronote: %s", ex)

    # Current period data
    current_period = client.current_period
    data["grades"] = get_grades(current_period)
    data["averages"] = get_averages(current_period)
    data["absences"] = get_absences(current_period)
    data["delays"] = get_delays(current_period)
    data["evaluations"] = get_evaluations(current_period)
    data["punishments"] = get_punishments(current_period)
    data["overall_average"] = get_overall_average(current_period)

    # Homework
    try:
        homework = client.homework(today)
        data["homework"] = sorted(homework, key=lambda hw: hw.date)
    except Exception as ex:
        data["homework"] = None
        _LOGGER.warning("Error getting homework from pronote: %s", ex)

    try:
        homework_period = client.homework(today, today + timedelta(days=HOMEWORK_MAX_DAYS))
        data["homework_period"] = sorted(homework_period, key=lambda hw: hw.date)
    except Exception as ex:
        data["homework_period"] = None
        _LOGGER.warning("Error getting homework_period from pronote: %s", ex)

    # Information and Surveys
    try:
        date_from = datetime.combine(today - timedelta(days=INFO_SURVEY_LIMIT_MAX_DAYS), datetime.min.time())
        information_and_surveys = client.information_and_surveys(date_from)
        data["information_and_surveys"] = sorted(
            information_and_surveys,
            key=lambda item: item.creation_date,
            reverse=True,
        )
    except Exception as ex:
        data["information_and_surveys"] = None
        _LOGGER.warning("Error getting information_and_surveys from pronote: %s", ex)

    # iCal
    try:
        data["ical_url"] = client.export_ical()
    except Exception as ex:
        data["ical_url"] = None
        _LOGGER.debug("iCal export not available: %s", ex)

    # Menus
    try:
        data["menus"] = client.menus(today, today + timedelta(days=7))
    except Exception as ex:
        data["menus"] = None
        _LOGGER.warning("Error getting menus from pronote: %s", ex)

    # Periods
    try:
        data["periods"] = client.periods
    except Exception as ex:
        data["periods"] = None
        _LOGGER.warning("Error getting periods from pronote: %s", ex)

    try:
        data["current_period"] = current_period
        data["current_period_key"] = slugify(current_period.name, separator="_")
    except Exception as ex:
        data["current_period"] = None
        data["current_period_key"] = None
        _LOGGER.warning("Error getting current period from pronote: %s", ex)

    # Previous periods data
    data["previous_periods"] = []
    supported_period_types = ["trimestre", "semestre"]
    period_type = None
    if data["current_period"] is not None:
        period_type = data["current_period"].name.split(" ")[0].lower()

    if period_type in supported_period_types and data["periods"] is not None:
        for period in data["periods"]:
            if period.name.lower().startswith(period_type) and period.start < data["current_period"].start:
                data["previous_periods"].append(period)
                period_key = slugify(period.name, separator="_")
                data[f"grades_{period_key}"] = get_grades(period)
                data[f"averages_{period_key}"] = get_averages(period)
                data[f"absences_{period_key}"] = get_absences(period)
                data[f"delays_{period_key}"] = get_delays(period)
                data[f"evaluations_{period_key}"] = get_evaluations(period)
                data[f"punishments_{period_key}"] = get_punishments(period)
                data[f"overall_average_{period_key}"] = get_overall_average(period)

    data["active_periods"] = data["previous_periods"] + (
        [data["current_period"]] if data["current_period"] is not None else []
    )

    return data


class PronoteDataUpdateCoordinator(TimestampDataUpdateCoordinator):
    """Data update coordinator for the Pronote integration."""

    config_entry: PronoteConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PronoteConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=entry.title,
            update_interval=timedelta(minutes=entry.options.get("refresh_interval", DEFAULT_REFRESH_INTERVAL)),
        )
        self.config_entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from Pronote and updates the state."""
        today = date.today()
        previous_data = None if self.data is None else self.data.copy()

        config_data = self.config_entry.data

        # Create client (auth step)
        try:
            client = await self.hass.async_add_executor_job(get_pronote_client, config_data)
        except (CryptoError, QRCodeDecryptError, ENTLoginError) as err:
            raise ConfigEntryAuthFailed(f"Authentication failed with Pronote: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Pronote: {err}") from err
        if client is None:
            raise ConfigEntryAuthFailed("Unable to authenticate with Pronote")

        # Fetch ALL data in a single executor call
        try:
            fetched = await self.hass.async_add_executor_job(_fetch_all_sync_data, client, dict(config_data), today)
        except Exception as err:
            raise UpdateFailed(f"Error fetching data from Pronote: {err}") from err

        # Save possibly refreshed credentials (must run on event loop)
        new_data = self.config_entry.data.copy()
        creds = fetched.pop("credentials")
        password = fetched.pop("password")

        if config_data["connection_type"] == "qrcode":
            # Remove one-time QR code data after first successful login
            new_data.pop("qr_code_json", None)
            new_data.pop("qr_code_pin", None)
            # Save refreshed token credentials for next token_login
            new_data["qr_code_url"] = creds["pronote_url"]
            new_data["qr_code_username"] = creds["username"]
            new_data["qr_code_password"] = password
            new_data["qr_code_uuid"] = creds["uuid"]
            new_data["client_identifier"] = creds["client_identifier"]

        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)

        child_info = fetched.get("child_info")
        if child_info is None:
            raise UpdateFailed("No child info available from Pronote")

        # Build final data dict
        self.data = {
            "account_type": config_data["account_type"],
            "sensor_prefix": re.sub("[^A-Za-z]", "_", child_info.name.lower()),
        }
        self.data.update(fetched)

        # Compute next alarm (needs hass timezone, runs on event loop)
        next_alarm = None
        tz = ZoneInfo(self.hass.config.time_zone)
        today_start_at = get_day_start_at(self.data.get("lessons_today"))
        next_day_start_at = get_day_start_at(self.data.get("lessons_next_day"))
        if today_start_at or next_day_start_at:
            alarm_offset = self.config_entry.options.get("alarm_offset", DEFAULT_ALARM_OFFSET)
            if today_start_at is not None:
                todays_alarm = today_start_at - timedelta(minutes=alarm_offset)
                if datetime.now() <= todays_alarm:
                    next_alarm = todays_alarm
            if next_alarm is None and next_day_start_at is not None:
                next_alarm = next_day_start_at - timedelta(minutes=alarm_offset)
        if next_alarm is not None:
            next_alarm = next_alarm.replace(tzinfo=tz)
        self.data["next_alarm"] = next_alarm

        # Fire events for new items (must run on event loop)
        self.compare_data(
            previous_data,
            "grades",
            ["date", "subject", "grade_out_of"],
            "new_grade",
            format_grade,
        )
        self.compare_data(previous_data, "absences", ["from", "to"], "new_absence", format_absence)
        self.compare_data(previous_data, "delays", ["date", "minutes"], "new_delay", format_delay)
        self.compare_data(
            previous_data,
            "evaluations",
            ["name", "date", "subject"],
            "new_evaluation",
            format_evaluation,
        )

        return self.data

    def compare_data(self, previous_data, data_key, compare_keys, event_type, format_func):
        if previous_data is None or previous_data.get(data_key) is None or self.data[data_key] is None:
            return
        # Build a set of keys from previous data — O(n)
        previous_keys = set()
        for item in previous_data[data_key]:
            formatted = format_func(item)
            previous_keys.add(tuple(formatted[k] for k in compare_keys))
        # Find new items — O(m)
        for item in self.data[data_key]:
            formatted = format_func(item)
            key = tuple(formatted[k] for k in compare_keys)
            if key not in previous_keys:
                self.trigger_event(event_type, formatted)

    def trigger_event(self, event_type, event_data):
        event_data = {
            "child_name": self.data["child_info"].name,
            "child_nickname": self.config_entry.options.get("nickname"),
            "child_slug": self.data["sensor_prefix"],
            "type": event_type,
            "data": event_data,
        }
        self.hass.bus.async_fire(EVENT_TYPE, event_data)
