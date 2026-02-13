"""Data update coordinator for the Pronote integration."""

from __future__ import annotations

import logging
import re
import time
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
    PronoteConfigEntry,
)
from .pronote_formatter import format_absence, format_delay, format_evaluation, format_grade
from .repairs import (
    async_create_connection_error_issue,
    async_create_rate_limited_issue,
    async_create_session_expired_issue,
    async_delete_issue_for_entry,
)

_LOGGER = logging.getLogger(__name__)


def get_day_start_at(lessons: list[Lesson] | None, logger: logging.Logger | None = None) -> datetime | None:
    """Get the start time of the first non-canceled lesson."""
    if lessons is None:
        return None

    for i, lesson in enumerate(lessons):
        if logger:
            logger.debug("get_day_start_at: lesson[%d] start=%s canceled=%s", i, lesson.start, lesson.canceled)
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
        self._previous_period_cache: dict[str, Any] | None = None
        self._previous_period_cache_date: date | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from Pronote and updates the state."""
        today = date.today()
        previous_data = None if self.data is None else self.data.copy()

        config_data = dict(self.config_entry.data)
        connection_type = config_data.get("connection_type", "username_password")

        # Authentication (skip if already connected)
        t_auth_start = time.perf_counter()
        if not self._api_client.is_authenticated():
            try:
                await self._api_client.authenticate(connection_type, config_data)
                # Clear any transient issues after successful auth
                async_delete_issue_for_entry(self.hass, self.config_entry, "connection_error")
                async_delete_issue_for_entry(self.hass, self.config_entry, "rate_limited")
            except AuthenticationError as err:
                async_create_session_expired_issue(self.hass, self.config_entry)
                raise ConfigEntryAuthFailed(f"Authentication failed with Pronote: {err}") from err
            except RateLimitError as err:
                async_create_rate_limited_issue(self.hass, self.config_entry, err.retry_after)
                raise UpdateFailed(f"Rate limited by Pronote: {err}") from err
            except CircuitBreakerOpenError as err:
                raise UpdateFailed(f"Pronote API temporarily unavailable: {err}") from err
            except ConnectionError as err:
                async_create_connection_error_issue(self.hass, self.config_entry, str(err))
                raise UpdateFailed(f"Connection error with Pronote: {err}") from err
            except Exception as err:
                raise UpdateFailed(f"Error authenticating with Pronote: {err}") from err

            if not self._api_client.is_authenticated():
                async_create_session_expired_issue(self.hass, self.config_entry)
                raise ConfigEntryAuthFailed("Unable to authenticate with Pronote")
        else:
            _LOGGER.debug("TIMING: auth skipped (reusing session)")

        t_auth_end = time.perf_counter()
        _LOGGER.debug("TIMING: auth=%.3fs", t_auth_end - t_auth_start)

        # Fetch all data (pass previous_period_cache if still valid today)
        t_fetch_start = time.perf_counter()
        prev_cache = self._previous_period_cache if self._previous_period_cache_date == today else None
        show_all_periods = self.config_entry.options.get("show_all_periods", False)
        try:
            pronote_data = await self._api_client.fetch_all_data(
                today=today,
                lesson_max_days=LESSON_MAX_DAYS,
                homework_max_days=HOMEWORK_MAX_DAYS,
                info_survey_max_days=INFO_SURVEY_LIMIT_MAX_DAYS,
                previous_period_cache=prev_cache,
                show_all_periods=show_all_periods,
            )
            # Clear all transient issues after successful fetch
            async_delete_issue_for_entry(self.hass, self.config_entry, "connection_error")
            async_delete_issue_for_entry(self.hass, self.config_entry, "rate_limited")
        except RateLimitError as err:
            async_create_rate_limited_issue(self.hass, self.config_entry, err.retry_after)
            raise UpdateFailed(f"Rate limited by Pronote: {err}") from err
        except AuthenticationError as err:
            self._api_client.reset()  # Force re-auth on next refresh
            async_create_session_expired_issue(self.hass, self.config_entry)
            raise ConfigEntryAuthFailed(f"Session expired: {err}") from err
        except InvalidResponseError as err:
            self._api_client.reset()
            raise UpdateFailed(f"Invalid response from Pronote: {err}") from err
        except ConnectionError as err:
            self._api_client.reset()
            async_create_connection_error_issue(self.hass, self.config_entry, str(err))
            raise UpdateFailed(f"Connection error: {err}") from err
        except Exception as err:
            self._api_client.reset()
            raise UpdateFailed(f"Error fetching data from Pronote: {err}") from err

        # Update previous_period_cache after successful fetch
        if pronote_data.previous_period_data:
            self._previous_period_cache = pronote_data.previous_period_data
            self._previous_period_cache_date = today

        # Save refreshed credentials for QR code connections
        if connection_type == "qrcode" and pronote_data.credentials:
            new_data = config_data.copy()
            # Save refreshed token credentials for next token_login
            new_data["qr_code_url"] = pronote_data.credentials["pronote_url"]
            new_data["qr_code_username"] = pronote_data.credentials["username"]
            new_data["qr_code_password"] = pronote_data.password
            new_data["qr_code_uuid"] = pronote_data.credentials["uuid"]
            new_data["client_identifier"] = pronote_data.credentials["client_identifier"]

            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)

        t_fetch_end = time.perf_counter()
        _LOGGER.debug("TIMING: fetch_all_data=%.3fs", t_fetch_end - t_fetch_start)

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
            pronote_data.lessons_period,
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
        lessons_period: list[Lesson] | None,
    ) -> datetime | None:
        """Compute the next alarm time based on lessons."""
        next_alarm = None
        tz = ZoneInfo(self.hass.config.time_zone)
        now = datetime.now(tz)
        alarm_offset = self.config_entry.options.get("alarm_offset", DEFAULT_ALARM_OFFSET)

        today_start_at = get_day_start_at(lessons_today, _LOGGER)
        if today_start_at is not None:
            if today_start_at.tzinfo is None:
                today_start_at = today_start_at.replace(tzinfo=tz)
            todays_alarm = today_start_at - timedelta(minutes=alarm_offset)
            _LOGGER.debug("compute_next_alarm: todays_alarm=%s, now=%s", todays_alarm, now)
            if now <= todays_alarm:
                next_alarm = todays_alarm

        if next_alarm is None:
            next_day_start_at = get_day_start_at(lessons_next_day, _LOGGER)
            if next_day_start_at is not None:
                next_day_alarm = next_day_start_at - timedelta(minutes=alarm_offset)
                if next_day_alarm.tzinfo is None:
                    next_day_alarm = next_day_alarm.replace(tzinfo=tz)
                if now <= next_day_alarm:
                    next_alarm = next_day_alarm

        if next_alarm is None and lessons_period:
            _LOGGER.debug("compute_next_alarm: searching in lessons_period (%d lessons)", len(lessons_period))
            today_date = now.date()
            # Group future lessons by day (skip today, already handled)
            future_days: dict[date, list] = {}
            for lesson in lessons_period:
                lesson_date = lesson.start.date()
                if lesson_date <= today_date:
                    continue
                future_days.setdefault(lesson_date, []).append(lesson)
            # Find first future school day with non-canceled lessons
            for day_date in sorted(future_days):
                day_start = get_day_start_at(future_days[day_date])
                if day_start is not None:
                    if day_start.tzinfo is None:
                        day_start = day_start.replace(tzinfo=tz)
                    next_alarm = day_start - timedelta(minutes=alarm_offset)
                    _LOGGER.debug(
                        "compute_next_alarm: found in period, day=%s, lesson_start=%s",
                        day_date,
                        day_start,
                    )
                    break

        if next_alarm is not None and next_alarm.tzinfo is None:
            next_alarm = next_alarm.replace(tzinfo=tz)

        _LOGGER.debug("compute_next_alarm: final next_alarm=%s", next_alarm)
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
