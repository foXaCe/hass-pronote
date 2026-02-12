"""Constants for the Pronote integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import PronoteDataUpdateCoordinator

DOMAIN = "pronote"
EVENT_TYPE = "pronote_event"

LESSON_MAX_DAYS = 15
LESSON_NEXT_DAY_SEARCH_LIMIT = 30
HOMEWORK_MAX_DAYS = 15

EVALUATIONS_TO_DISPLAY = 15
TIMETABLE_PERIOD_MAX_LESSONS = 16

INFO_SURVEY_LIMIT_MAX_DAYS = 7

HOMEWORK_DESC_MAX_LENGTH = 125

# default values for options
DEFAULT_GRADES_TO_DISPLAY = 11
DEFAULT_REFRESH_INTERVAL = 15
DEFAULT_ALARM_OFFSET = 60
DEFAULT_LUNCH_BREAK_TIME = "13:00"
DEFAULT_SHOW_ALL_PERIODS = False

PLATFORMS = [Platform.SENSOR, Platform.CALENDAR]

type PronoteConfigEntry = ConfigEntry[PronoteDataUpdateCoordinator]
