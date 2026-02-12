"""Tests for the Pronote constants."""

from homeassistant.const import Platform

from custom_components.pronote.const import (
    DEFAULT_ALARM_OFFSET,
    DEFAULT_GRADES_TO_DISPLAY,
    DEFAULT_LUNCH_BREAK_TIME,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
    EVALUATIONS_TO_DISPLAY,
    HOMEWORK_DESC_MAX_LENGTH,
    HOMEWORK_MAX_DAYS,
    INFO_SURVEY_LIMIT_MAX_DAYS,
    LESSON_MAX_DAYS,
    LESSON_NEXT_DAY_SEARCH_LIMIT,
    PLATFORMS,
)


def test_domain():
    assert DOMAIN == "pronote"


def test_platforms():
    assert Platform.SENSOR in PLATFORMS
    assert Platform.CALENDAR in PLATFORMS
    assert len(PLATFORMS) == 2


def test_lesson_constants():
    assert LESSON_MAX_DAYS == 15
    assert LESSON_NEXT_DAY_SEARCH_LIMIT == 30


def test_homework_constants():
    assert HOMEWORK_MAX_DAYS == 15
    assert HOMEWORK_DESC_MAX_LENGTH == 125


def test_display_constants():
    assert DEFAULT_GRADES_TO_DISPLAY == 11
    assert EVALUATIONS_TO_DISPLAY == 15


def test_default_options():
    assert DEFAULT_REFRESH_INTERVAL == 15
    assert DEFAULT_ALARM_OFFSET == 60
    assert DEFAULT_LUNCH_BREAK_TIME == "13:00"


def test_info_survey_limit():
    assert INFO_SURVEY_LIMIT_MAX_DAYS == 7
