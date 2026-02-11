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

from .api import (
    AuthenticationError,
    CircuitBreakerOpenError,
    ConnectionError,
    InvalidResponseError,
    Lesson,
    PronoteAPIClient,
    RateLimitError,
)
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

_LOGGER = logging.getLogger(__name__)


def get_day_start_at(lessons: list[Lesson] | None) -> datetime | None:
    """Get the start time of the first non-canceled lesson."""
    if lessons is None:
        return None

    for lesson in lessons:
        if not lesson.canceled:
            return lesson.start

    return None


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
        self._api_client = PronoteAPIClient(hass)

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from Pronote and updates the state."""
        today = date.today()
        previous_data = None if self.data is None else self.data.copy()

        config_data = dict(self.config_entry.data)
        connection_type = config_data.get("connection_type", "username_password")

        # Authentication
        try:
            await self._api_client.authenticate(connection_type, config_data)
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed with Pronote: {err}") from err
        except RateLimitError as err:
            # Honor retry_after from rate limiting (HTTP 429)
            raise UpdateFailed(
                f"Rate limited by Pronote: {err}",
                retry_after=err.retry_after,
            ) from err
        except CircuitBreakerOpenError as err:
            # Circuit breaker open - wait for recovery
            raise UpdateFailed(
                f"Pronote API temporarily unavailable: {err}",
                retry_after=300,  # 5 minutes default recovery
            ) from err
        except ConnectionError as err:
            raise UpdateFailed(f"Connection error with Pronote: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error authenticating with Pronote: {err}") from err

        if not self._api_client.is_authenticated():
            raise ConfigEntryAuthFailed("Unable to authenticate with Pronote")

        # Fetch all data
        try:
            pronote_data = await self._api_client.fetch_all_data(
                today=today,
                lesson_max_days=LESSON_MAX_DAYS,
                homework_max_days=HOMEWORK_MAX_DAYS,
                info_survey_max_days=INFO_SURVEY_LIMIT_MAX_DAYS,
            )
        except RateLimitError as err:
            raise UpdateFailed(
                f"Rate limited by Pronote: {err}",
                retry_after=err.retry_after,
            ) from err
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(f"Session expired: {err}") from err
        except InvalidResponseError as err:
            raise UpdateFailed(f"Invalid response from Pronote: {err}") from err
        except ConnectionError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching data from Pronote: {err}") from err

        # Save refreshed credentials for QR code connections
        if connection_type == "qrcode" and pronote_data.credentials:
            new_data = config_data.copy()
            # Remove one-time QR code data after first successful login
            new_data.pop("qr_code_json", None)
            new_data.pop("qr_code_pin", None)
            # Save refreshed token credentials for next token_login
            new_data["qr_code_url"] = pronote_data.credentials["pronote_url"]
            new_data["qr_code_username"] = pronote_data.credentials["username"]
            new_data["qr_code_password"] = pronote_data.password
            new_data["qr_code_uuid"] = pronote_data.credentials["uuid"]
            new_data["client_identifier"] = pronote_data.credentials["client_identifier"]

            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)

        # Verify we have child info
        if pronote_data.child_info is None:
            raise UpdateFailed("No child info available from Pronote")

        # Build final data dict
        data: dict[str, Any] = {
            "account_type": config_data["account_type"],
            "sensor_prefix": re.sub("[^A-Za-z]", "_", pronote_data.child_info.name.lower()),
            "child_info": pronote_data.child_info,
            "lessons_today": pronote_data.lessons_today,
            "lessons_tomorrow": pronote_data.lessons_tomorrow,
            "lessons_next_day": pronote_data.lessons_next_day,
            "lessons_period": pronote_data.lessons_period,
            "grades": pronote_data.grades,
            "averages": pronote_data.averages,
            "overall_average": pronote_data.overall_average,
            "absences": pronote_data.absences,
            "delays": pronote_data.delays,
            "punishments": pronote_data.punishments,
            "evaluations": pronote_data.evaluations,
            "homework": pronote_data.homework,
            "homework_period": pronote_data.homework_period,
            "information_and_surveys": pronote_data.information_and_surveys,
            "menus": pronote_data.menus,
            "periods": pronote_data.periods,
            "current_period": pronote_data.current_period,
            "current_period_key": pronote_data.current_period_key,
            "previous_periods": pronote_data.previous_periods,
            "active_periods": pronote_data.active_periods,
            "ical_url": pronote_data.ical_url,
        }

        # Add previous period data dynamically
        if pronote_data.previous_period_data:
            data.update(pronote_data.previous_period_data)

        # Compute next alarm (needs hass timezone)
        next_alarm = self._compute_next_alarm(
            pronote_data.lessons_today,
            pronote_data.lessons_next_day,
        )
        data["next_alarm"] = next_alarm

        self.data = data

        # Fire events for new items
        self._compare_and_fire_events(previous_data)

        return self.data

    def _compute_next_alarm(
        self,
        lessons_today: list[Lesson] | None,
        lessons_next_day: list[Lesson] | None,
    ) -> datetime | None:
        """Compute the next alarm time based on lessons."""
        next_alarm = None
        tz = ZoneInfo(self.hass.config.time_zone)
        today_start_at = get_day_start_at(lessons_today)
        next_day_start_at = get_day_start_at(lessons_next_day)

        if today_start_at or next_day_start_at:
            alarm_offset = self.config_entry.options.get("alarm_offset", DEFAULT_ALARM_OFFSET)
            if today_start_at is not None:
                todays_alarm = today_start_at - timedelta(minutes=alarm_offset)
                if datetime.now(tz) <= todays_alarm:
                    next_alarm = todays_alarm

            if next_alarm is None and next_day_start_at is not None:
                next_alarm = next_day_start_at - timedelta(minutes=alarm_offset)

        if next_alarm is not None:
            next_alarm = next_alarm.replace(tzinfo=tz)

        return next_alarm

    def _compare_and_fire_events(self, previous_data: dict[str, Any] | None) -> None:
        """Compare data and fire events for new items."""
        # Grades
        self._compare_data(
            previous_data,
            "grades",
            ["date", "subject", "grade_out_of"],
            "new_grade",
            format_grade,
        )
        # Absences
        self._compare_data(
            previous_data,
            "absences",
            ["from", "to"],
            "new_absence",
            format_absence,
        )
        # Delays
        self._compare_data(
            previous_data,
            "delays",
            ["date", "minutes"],
            "new_delay",
            format_delay,
        )
        # Evaluations
        self._compare_data(
            previous_data,
            "evaluations",
            ["name", "date", "subject"],
            "new_evaluation",
            format_evaluation,
        )

    def _compare_data(
        self,
        previous_data: dict[str, Any] | None,
        data_key: str,
        compare_keys: list[str],
        event_type: str,
        format_func: callable,
    ) -> None:
        """Compare data between updates and fire events for new items."""
        if previous_data is None or self.data is None:
            return

        previous_items = previous_data.get(data_key)
        current_items = self.data.get(data_key)

        if previous_items is None or current_items is None:
            return

        # Build a set of keys from previous data — O(n)
        previous_keys: set[tuple] = set()
        for item in previous_items:
            formatted = format_func(item)
            try:
                previous_keys.add(tuple(formatted[k] for k in compare_keys))
            except KeyError:
                # Skip items with missing keys
                continue

        # Find new items — O(m)
        for item in current_items:
            formatted = format_func(item)
            try:
                key = tuple(formatted[k] for k in compare_keys)
            except KeyError:
                continue

            if key not in previous_keys:
                self._trigger_event(event_type, formatted)

    def _trigger_event(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Fire an event on the Home Assistant bus."""
        if self.data is None or "child_info" not in self.data:
            return

        event_payload = {
            "child_name": self.data["child_info"].name,
            "child_nickname": self.config_entry.options.get("nickname"),
            "child_slug": self.data.get("sensor_prefix", "unknown"),
            "type": event_type,
            "data": event_data,
        }
        self.hass.bus.async_fire(EVENT_TYPE, event_payload)
