"""Tests for the Pronote sensor module."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from slugify import slugify

from custom_components.pronote.const import (
    DEFAULT_GRADES_TO_DISPLAY,
    DOMAIN,
    EVALUATIONS_TO_DISPLAY,
)
from custom_components.pronote.coordinator import PronoteDataUpdateCoordinator
from custom_components.pronote.sensor import (
    PronoteAbsensesSensor,
    PronoteAveragesSensor,
    PronoteClassSensor,
    PronoteCurrentPeriodSensor,
    PronoteDelaysSensor,
    PronoteEvaluationsSensor,
    PronoteGenericSensor,
    PronoteGradesSensor,
    PronoteHomeworkSensor,
    PronoteInformationAndSurveysSensor,
    PronoteMenusSensor,
    PronoteOverallAverageSensor,
    PronotePeriodRelatedSensor,
    PronotePeriodsSensor,
    PronotePunishmentsSensor,
    PronoteTimetableSensor,
    async_setup_entry,
    len_or_none,
)

# ---------------------------------------------------------------------------
# Helper: create a mock coordinator without triggering real __init__
# ---------------------------------------------------------------------------


def _make_coordinator(data=None, options=None):
    """Create a mock coordinator for testing sensors."""
    with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
        coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)

    coord.data = data or {
        "account_type": "eleve",
        "sensor_prefix": "jean_dupont",
        "child_info": SimpleNamespace(
            name="Jean Dupont",
            class_name="3eme A",
            establishment="College Victor Hugo",
        ),
        "current_period": SimpleNamespace(
            name="Trimestre 1",
            start=date(2025, 9, 1),
            end=date(2025, 12, 20),
        ),
        "lessons_today": [],
        "lessons_tomorrow": [],
        "lessons_next_day": [],
        "lessons_period": [],
        "grades": [],
        "averages": [],
        "homework": [],
        "homework_period": [],
        "absences": [],
        "delays": [],
        "evaluations": [],
        "punishments": [],
        "menus": [],
        "information_and_surveys": [],
        "periods": [],
        "previous_periods": [],
        "active_periods": [],
        "next_alarm": None,
        "overall_average": "14.5",
        "ical_url": "https://example.com/ical",
    }

    entry = MagicMock()
    entry.options = {"nickname": "Jean", "lunch_break_time": "13:00"} if options is None else options
    coord.config_entry = entry
    coord.last_update_success = True
    coord.last_update_success_time = datetime(2025, 1, 15, 10, 0)

    return coord


def _make_lesson(
    subject_name="Mathematiques",
    start=None,
    end=None,
    canceled=False,
    is_detention=False,
    teacher="M. Dupont",
    room="A101",
    status="",
    color="#FFFFFF",
    is_outside=False,
):
    if start is None:
        start = datetime(2025, 1, 15, 8, 0)
    if end is None:
        end = start + timedelta(hours=1)
    return SimpleNamespace(
        subject=subject_name,
        start=start,
        end=end,
        canceled=canceled,
        is_detention=is_detention,
        teacher=teacher,
        room=room,
        status=status,
        color=color,
        is_outside=is_outside,
    )


def _make_grade(
    subject_name="Mathematiques",
    grade="15",
    grade_out_of="20",
    coefficient="1",
    class_average="12.5",
    comment="Bien",
    date_val=None,
    is_bonus=False,
    is_optional=False,
):
    return SimpleNamespace(
        subject=subject_name,
        grade=grade,
        grade_out_of=grade_out_of,
        coefficient=coefficient,
        class_average=class_average,
        comment=comment,
        date=date_val or date(2025, 1, 15),
        is_bonus=is_bonus,
        is_optional=is_optional,
    )


def _make_homework(
    subject_name="Mathematiques",
    description="Exercices 1 a 10 page 42",
    done=False,
    date_val=None,
    background_color="#FFFFFF",
    files=None,
):
    return SimpleNamespace(
        subject=subject_name,
        description=description,
        done=done,
        date=date_val or date(2025, 1, 16),
        background_color=background_color,
        files=files or [],
    )


def _make_absence(
    from_date=None,
    to_date=None,
    justified=False,
    hours="2",
    reason="Maladie",
):
    return SimpleNamespace(
        from_date=from_date or datetime(2025, 1, 15, 8, 0),
        to_date=to_date or datetime(2025, 1, 15, 10, 0),
        justified=justified,
        hours=hours,
        reason=reason,
    )


def _make_delay(
    date_val=None,
    minutes=10,
    justified=False,
    reason="Transports",
):
    return SimpleNamespace(
        date=date_val or datetime(2025, 1, 15, 8, 0),
        minutes=minutes,
        justified=justified,
        reason=reason,
    )


def _make_evaluation(
    name="Controle",
    date_val=None,
    subject_name="Mathematiques",
    acquisitions=None,
):
    return SimpleNamespace(
        name=name,
        date=date_val or date(2025, 1, 15),
        subject=subject_name,
        acquisitions=acquisitions or [],
    )


def _make_average(
    student="14.5",
    class_average="12.0",
    max_avg="18.0",
    min_avg="5.0",
    subject_name="Mathematiques",
):
    return SimpleNamespace(
        student=student,
        class_average=class_average,
        max=max_avg,
        min=min_avg,
        subject=subject_name,
    )


def _make_punishment(
    given=None,
    subject="Mathematiques",
    reason="Bavardage",
    circumstances="Bavardage",
    duration="1h",
    during_lesson=False,
    homework="",
):
    return SimpleNamespace(
        given=given or date(2025, 1, 15),
        subject=subject,
        reason=reason,
        circumstances=circumstances,
        duration=duration,
        during_lesson=during_lesson,
        homework=homework,
    )


def _make_menu(
    name="Dejeuner",
    date_val=None,
    is_lunch=True,
    is_dinner=False,
    first_meal=None,
    main_meal=None,
    side_meal=None,
    other_meal=None,
    cheese=None,
    dessert=None,
):
    return SimpleNamespace(
        name=name,
        date=date_val or date(2025, 1, 15),
        is_lunch=is_lunch,
        is_dinner=is_dinner,
        first_meal=first_meal,
        main_meal=main_meal,
        side_meal=side_meal,
        other_meal=other_meal,
        cheese=cheese,
        dessert=dessert,
    )


def _make_info_survey(
    author="M. Le Principal",
    title="Sortie scolaire",
    read=False,
    creation_date=None,
    start_date=None,
    end_date=None,
    category="Information",
    survey=False,
    anonymous_response=False,
    attachments=None,
    template=None,
    shared_template=None,
    content="Contenu de l'information",
):
    return SimpleNamespace(
        author=author,
        title=title,
        read=read,
        creation_date=creation_date or datetime(2025, 1, 15, 10, 0),
        start_date=start_date or datetime(2025, 1, 15),
        end_date=end_date or datetime(2025, 1, 20),
        category=category,
        survey=survey,
        anonymous_response=anonymous_response,
        attachments=attachments or [],
        template=template,
        shared_template=shared_template,
        content=content,
    )


def _make_period(
    name="Trimestre 1",
    start=None,
    end=None,
):
    return SimpleNamespace(
        name=name,
        start=start or date(2025, 9, 1),
        end=end or date(2025, 12, 20),
    )


# ===================================================================
# TestLenOrNone (preserved from original)
# ===================================================================


class TestLenOrNone:
    def test_none_returns_none(self):
        assert len_or_none(None) is None

    def test_empty_list(self):
        assert len_or_none([]) == 0

    def test_list_with_items(self):
        assert len_or_none([1, 2, 3]) == 3

    def test_string(self):
        assert len_or_none("hello") == 5


# ===================================================================
# TestPronoteGenericSensor
# ===================================================================


class TestPronoteGenericSensor:
    def test_native_value_with_data(self):
        coord = _make_coordinator()
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        assert sensor.native_value == "https://example.com/ical"

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["next_alarm"] = None
        sensor = PronoteGenericSensor(coord, "next_alarm", "Next alarm")
        assert sensor.native_value is None

    def test_native_value_with_state(self):
        coord = _make_coordinator()
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL", state="custom_state")
        assert sensor.native_value == "custom_state"

    def test_native_value_with_state_but_data_is_none(self):
        """When coordinator data is None, native_value should be None even if state is set."""
        coord = _make_coordinator()
        coord.data["ical_url"] = None
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL", state="custom_state")
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        attrs = sensor.extra_state_attributes

        assert attrs["full_name"] == "Jean Dupont"
        assert attrs["nickname"] == "Jean"
        assert attrs["via_parent_account"] is False
        assert attrs["updated_at"] == datetime(2025, 1, 15, 10, 0)

    def test_extra_state_attributes_parent_account(self):
        coord = _make_coordinator()
        coord.data["account_type"] = "parent"
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        attrs = sensor.extra_state_attributes

        assert attrs["via_parent_account"] is True

    def test_available_true(self):
        coord = _make_coordinator()
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        assert sensor.available is True

    def test_available_false_no_data(self):
        """When last_update_success is False, available should be False."""
        coord = _make_coordinator()
        coord.last_update_success = False
        coord.data["ical_url"] = None
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        assert sensor.available is False

    def test_available_false_update_failed(self):
        coord = _make_coordinator()
        coord.last_update_success = False
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        assert sensor.available is False

    def test_unique_id_format(self):
        coord = _make_coordinator()
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        assert sensor._attr_unique_id == f"{DOMAIN}_jean_dupont_Timetable iCal URL"

    def test_device_class_set(self):
        from homeassistant.components.sensor import SensorDeviceClass

        coord = _make_coordinator()
        sensor = PronoteGenericSensor(coord, "next_alarm", "Next alarm", device_class=SensorDeviceClass.TIMESTAMP)
        assert sensor._attr_device_class == SensorDeviceClass.TIMESTAMP

    def test_device_class_not_set(self):
        coord = _make_coordinator()
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        assert not hasattr(sensor, "_attr_device_class")

    def test_nickname_none_when_not_in_options(self):
        coord = _make_coordinator(options={})
        sensor = PronoteGenericSensor(coord, "ical_url", "Timetable iCal URL")
        attrs = sensor.extra_state_attributes
        assert attrs["nickname"] is None


# ===================================================================
# TestPronoteClassSensor
# ===================================================================


class TestPronoteClassSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        sensor = PronoteClassSensor(coord)
        assert sensor.native_value == "3eme A"

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        sensor = PronoteClassSensor(coord)
        attrs = sensor.extra_state_attributes

        assert attrs["class_name"] == "3eme A"
        assert attrs["establishment"] == "College Victor Hugo"
        assert attrs["full_name"] == "Jean Dupont"


# ===================================================================
# TestPronoteTimetableSensor
# ===================================================================


class TestPronoteTimetableSensor:
    def test_native_value_with_lessons(self):
        coord = _make_coordinator()
        coord.data["lessons_today"] = [
            _make_lesson(start=datetime(2025, 1, 15, 8, 0)),
            _make_lesson(start=datetime(2025, 1, 15, 9, 0)),
        ]
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        assert sensor.native_value == 2

    def test_native_value_none_lessons(self):
        coord = _make_coordinator()
        coord.data["lessons_today"] = None
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        assert sensor.native_value is None

    def test_native_value_empty_lessons(self):
        coord = _make_coordinator()
        coord.data["lessons_today"] = []
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        assert sensor.native_value == 0

    def test_extra_state_attributes_today_with_lessons(self):
        lessons = [
            _make_lesson(start=datetime(2025, 1, 15, 8, 0), end=datetime(2025, 1, 15, 9, 0)),
            _make_lesson(
                subject_name="Francais",
                start=datetime(2025, 1, 15, 9, 0),
                end=datetime(2025, 1, 15, 10, 0),
            ),
            _make_lesson(
                subject_name="Histoire",
                start=datetime(2025, 1, 15, 14, 0),
                end=datetime(2025, 1, 15, 15, 0),
            ),
        ]
        coord = _make_coordinator()
        coord.data["lessons_today"] = lessons
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        attrs = sensor.extra_state_attributes

        assert "lessons" in attrs
        assert len(attrs["lessons"]) == 3
        assert attrs["canceled_lessons_counter"] == 0
        assert attrs["day_start_at"] == datetime(2025, 1, 15, 8, 0)
        assert attrs["day_end_at"] == datetime(2025, 1, 15, 15, 0)
        assert "lunch_break_start_at" in attrs
        assert "lunch_break_end_at" in attrs

    def test_extra_state_attributes_lunch_break(self):
        """Verify lunch break is computed from last morning lesson end and first afternoon lesson start."""
        lessons = [
            _make_lesson(start=datetime(2025, 1, 15, 8, 0), end=datetime(2025, 1, 15, 9, 0)),
            _make_lesson(start=datetime(2025, 1, 15, 11, 0), end=datetime(2025, 1, 15, 12, 0)),
            _make_lesson(start=datetime(2025, 1, 15, 14, 0), end=datetime(2025, 1, 15, 15, 0)),
        ]
        coord = _make_coordinator()
        coord.data["lessons_today"] = lessons
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        attrs = sensor.extra_state_attributes

        assert attrs["lunch_break_start_at"] == datetime(2025, 1, 15, 12, 0)
        assert attrs["lunch_break_end_at"] == datetime(2025, 1, 15, 14, 0)

    def test_extra_state_attributes_none_lessons(self):
        coord = _make_coordinator()
        coord.data["lessons_today"] = None
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        attrs = sensor.extra_state_attributes

        assert attrs["canceled_lessons_counter"] is None
        assert attrs["lessons"] == []
        assert attrs["day_start_at"] is None
        assert attrs["day_end_at"] is None

    def test_extra_state_attributes_period_no_lunch_break(self):
        """Period timetable should NOT have lunch_break_* keys."""
        coord = _make_coordinator()
        coord.data["lessons_period"] = [
            _make_lesson(start=datetime(2025, 1, 15, 8, 0)),
        ]
        sensor = PronoteTimetableSensor(coord, key="lessons_period", name="Period's timetable")
        attrs = sensor.extra_state_attributes

        assert "lunch_break_start_at" not in attrs
        assert "lunch_break_end_at" not in attrs

    def test_unrecorded_attributes(self):
        assert "lessons" in PronoteTimetableSensor._unrecorded_attributes

    def test_canceled_lesson_counted(self):
        lessons = [
            _make_lesson(start=datetime(2025, 1, 15, 8, 0), canceled=True),
            _make_lesson(start=datetime(2025, 1, 15, 9, 0), canceled=False),
        ]
        coord = _make_coordinator()
        coord.data["lessons_today"] = lessons
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        attrs = sensor.extra_state_attributes

        assert attrs["canceled_lessons_counter"] == 1

    def test_duplicate_canceled_lessons_filtered(self):
        """When two lessons at the same time and one is canceled, the duplicate canceled one is filtered."""
        lessons = [
            _make_lesson(
                subject_name="Maths",
                start=datetime(2025, 1, 15, 8, 0),
                end=datetime(2025, 1, 15, 9, 0),
                canceled=False,
            ),
            _make_lesson(
                subject_name="Maths",
                start=datetime(2025, 1, 15, 8, 0),
                end=datetime(2025, 1, 15, 9, 0),
                canceled=True,
            ),
        ]
        coord = _make_coordinator()
        coord.data["lessons_today"] = lessons
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        attrs = sensor.extra_state_attributes

        # The second lesson (canceled duplicate) should be filtered out from the formatted list
        assert len(attrs["lessons"]) == 1
        # The duplicate canceled lesson is entirely skipped, so not counted
        assert attrs["canceled_lessons_counter"] == 0

    def test_day_start_at_skips_canceled(self):
        """day_start_at should be the first NON-canceled lesson."""
        lessons = [
            _make_lesson(start=datetime(2025, 1, 15, 8, 0), canceled=True),
            _make_lesson(start=datetime(2025, 1, 15, 9, 0), canceled=False),
        ]
        coord = _make_coordinator()
        coord.data["lessons_today"] = lessons
        sensor = PronoteTimetableSensor(coord, key="lessons_today", name="Today's timetable")
        attrs = sensor.extra_state_attributes

        assert attrs["day_start_at"] == datetime(2025, 1, 15, 9, 0)


# ===================================================================
# TestPronoteGradesSensor
# ===================================================================


class TestPronoteGradesSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["grades"] = [_make_grade(), _make_grade(subject_name="Francais")]
        sensor = PronoteGradesSensor(coord, key="grades", name="Grades", period_key="trimestre_1")
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["grades"] = None
        sensor = PronoteGradesSensor(coord, key="grades", name="Grades", period_key="trimestre_1")
        assert sensor.native_value is None

    def test_extra_state_attributes_with_grades(self):
        coord = _make_coordinator()
        coord.data["grades"] = [_make_grade(), _make_grade(subject_name="Francais")]
        sensor = PronoteGradesSensor(coord, key="grades", name="Grades", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert "grades" in attrs
        assert len(attrs["grades"]) == 2
        assert attrs["period_key"] == "trimestre_1"
        assert attrs["is_current_period"] is True

    def test_extra_state_attributes_non_current_period(self):
        coord = _make_coordinator()
        coord.data["grades_trimestre_2"] = [_make_grade()]
        sensor = PronoteGradesSensor(
            coord, key="grades_trimestre_2", name="Grades Trimestre 2", period_key="trimestre_2"
        )
        attrs = sensor.extra_state_attributes

        assert attrs["is_current_period"] is False

    def test_extra_state_attributes_limits_display(self):
        """Only grades_to_display grades should be shown."""
        grades = [_make_grade(subject_name=f"Subject {i}") for i in range(DEFAULT_GRADES_TO_DISPLAY + 5)]
        coord = _make_coordinator(
            options={"nickname": "Jean", "lunch_break_time": "13:00", "grades_to_display": DEFAULT_GRADES_TO_DISPLAY}
        )
        coord.data["grades"] = grades
        sensor = PronoteGradesSensor(coord, key="grades", name="Grades", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert len(attrs["grades"]) == DEFAULT_GRADES_TO_DISPLAY

    def test_extra_state_attributes_empty_grades(self):
        coord = _make_coordinator()
        coord.data["grades"] = []
        sensor = PronoteGradesSensor(coord, key="grades", name="Grades", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert attrs["grades"] == []

    def test_extra_state_attributes_none_grades(self):
        coord = _make_coordinator()
        coord.data["grades"] = None
        sensor = PronoteGradesSensor(coord, key="grades", name="Grades", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert attrs["grades"] == []

    def test_unrecorded_attributes(self):
        assert "grades" in PronoteGradesSensor._unrecorded_attributes


# ===================================================================
# TestPronoteHomeworkSensor
# ===================================================================


class TestPronoteHomeworkSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["homework"] = [_make_homework(), _make_homework()]
        sensor = PronoteHomeworkSensor(coord, key="homework", name="Homework")
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["homework"] = None
        sensor = PronoteHomeworkSensor(coord, key="homework", name="Homework")
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["homework"] = [_make_homework(), _make_homework(done=True)]
        sensor = PronoteHomeworkSensor(coord, key="homework", name="Homework")
        attrs = sensor.extra_state_attributes

        assert "homework" in attrs
        assert len(attrs["homework"]) == 2
        assert "todo_counter" in attrs

    def test_todo_counter(self):
        coord = _make_coordinator()
        coord.data["homework"] = [
            _make_homework(done=False),
            _make_homework(done=True),
            _make_homework(done=False),
        ]
        sensor = PronoteHomeworkSensor(coord, key="homework", name="Homework")
        attrs = sensor.extra_state_attributes

        assert attrs["todo_counter"] == 2

    def test_todo_counter_all_done(self):
        coord = _make_coordinator()
        coord.data["homework"] = [_make_homework(done=True), _make_homework(done=True)]
        sensor = PronoteHomeworkSensor(coord, key="homework", name="Homework")
        attrs = sensor.extra_state_attributes

        assert attrs["todo_counter"] == 0

    def test_todo_counter_none_when_data_is_none(self):
        coord = _make_coordinator()
        coord.data["homework"] = None
        sensor = PronoteHomeworkSensor(coord, key="homework", name="Homework")
        attrs = sensor.extra_state_attributes

        assert attrs["todo_counter"] is None

    def test_unrecorded_attributes(self):
        assert "homework" in PronoteHomeworkSensor._unrecorded_attributes


# ===================================================================
# TestPronoteAbsensesSensor
# ===================================================================


class TestPronoteAbsensesSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["absences"] = [_make_absence(), _make_absence()]
        sensor = PronoteAbsensesSensor(coord, key="absences", name="Absences", period_key="trimestre_1")
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["absences"] = None
        sensor = PronoteAbsensesSensor(coord, key="absences", name="Absences", period_key="trimestre_1")
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["absences"] = [_make_absence()]
        sensor = PronoteAbsensesSensor(coord, key="absences", name="Absences", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert "absences" in attrs
        assert len(attrs["absences"]) == 1
        assert attrs["period_key"] == "trimestre_1"

    def test_extra_state_attributes_empty(self):
        coord = _make_coordinator()
        coord.data["absences"] = []
        sensor = PronoteAbsensesSensor(coord, key="absences", name="Absences", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert attrs["absences"] == []

    def test_extra_state_attributes_none(self):
        coord = _make_coordinator()
        coord.data["absences"] = None
        sensor = PronoteAbsensesSensor(coord, key="absences", name="Absences", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert attrs["absences"] == []

    def test_unrecorded_attributes(self):
        assert "absences" in PronoteAbsensesSensor._unrecorded_attributes


# ===================================================================
# TestPronoteDelaysSensor
# ===================================================================


class TestPronoteDelaysSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["delays"] = [_make_delay(), _make_delay()]
        sensor = PronoteDelaysSensor(coord, key="delays", name="Delays", period_key="trimestre_1")
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["delays"] = None
        sensor = PronoteDelaysSensor(coord, key="delays", name="Delays", period_key="trimestre_1")
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["delays"] = [_make_delay()]
        sensor = PronoteDelaysSensor(coord, key="delays", name="Delays", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert "delays" in attrs
        assert len(attrs["delays"]) == 1
        assert attrs["period_key"] == "trimestre_1"

    def test_extra_state_attributes_none(self):
        coord = _make_coordinator()
        coord.data["delays"] = None
        sensor = PronoteDelaysSensor(coord, key="delays", name="Delays", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert attrs["delays"] == []

    def test_unrecorded_attributes(self):
        assert "delays" in PronoteDelaysSensor._unrecorded_attributes


# ===================================================================
# TestPronoteEvaluationsSensor
# ===================================================================


class TestPronoteEvaluationsSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["evaluations"] = [_make_evaluation(), _make_evaluation()]
        sensor = PronoteEvaluationsSensor(coord, key="evaluations", name="Evaluations", period_key="trimestre_1")
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["evaluations"] = None
        sensor = PronoteEvaluationsSensor(coord, key="evaluations", name="Evaluations", period_key="trimestre_1")
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["evaluations"] = [_make_evaluation()]
        sensor = PronoteEvaluationsSensor(coord, key="evaluations", name="Evaluations", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert "evaluations" in attrs
        assert len(attrs["evaluations"]) == 1
        assert attrs["period_key"] == "trimestre_1"

    def test_extra_state_attributes_limits_display(self):
        """Only EVALUATIONS_TO_DISPLAY evaluations should be shown."""
        evaluations = [_make_evaluation(name=f"Eval {i}") for i in range(EVALUATIONS_TO_DISPLAY + 5)]
        coord = _make_coordinator()
        coord.data["evaluations"] = evaluations
        sensor = PronoteEvaluationsSensor(coord, key="evaluations", name="Evaluations", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert len(attrs["evaluations"]) == EVALUATIONS_TO_DISPLAY

    def test_extra_state_attributes_none(self):
        coord = _make_coordinator()
        coord.data["evaluations"] = None
        sensor = PronoteEvaluationsSensor(coord, key="evaluations", name="Evaluations", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert attrs["evaluations"] == []

    def test_unrecorded_attributes(self):
        assert "evaluations" in PronoteEvaluationsSensor._unrecorded_attributes


# ===================================================================
# TestPronoteAveragesSensor
# ===================================================================


class TestPronoteAveragesSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["averages"] = [_make_average(), _make_average(subject_name="Francais")]
        sensor = PronoteAveragesSensor(coord, key="averages", name="Averages", period_key="trimestre_1")
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["averages"] = None
        sensor = PronoteAveragesSensor(coord, key="averages", name="Averages", period_key="trimestre_1")
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["averages"] = [_make_average()]
        sensor = PronoteAveragesSensor(coord, key="averages", name="Averages", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert "averages" in attrs
        assert len(attrs["averages"]) == 1
        assert attrs["period_key"] == "trimestre_1"

    def test_extra_state_attributes_none(self):
        coord = _make_coordinator()
        coord.data["averages"] = None
        sensor = PronoteAveragesSensor(coord, key="averages", name="Averages", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert attrs["averages"] == []

    def test_unrecorded_attributes(self):
        assert "averages" in PronoteAveragesSensor._unrecorded_attributes


# ===================================================================
# TestPronotePunishmentsSensor
# ===================================================================


class TestPronotePunishmentsSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["punishments"] = [_make_punishment()]
        sensor = PronotePunishmentsSensor(coord, key="punishments", name="Punishments", period_key="trimestre_1")
        assert sensor.native_value == 1

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["punishments"] = None
        sensor = PronotePunishmentsSensor(coord, key="punishments", name="Punishments", period_key="trimestre_1")
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["punishments"] = [_make_punishment()]
        sensor = PronotePunishmentsSensor(coord, key="punishments", name="Punishments", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert "punishments" in attrs
        assert len(attrs["punishments"]) == 1
        assert attrs["period_key"] == "trimestre_1"

    def test_extra_state_attributes_none(self):
        coord = _make_coordinator()
        coord.data["punishments"] = None
        sensor = PronotePunishmentsSensor(coord, key="punishments", name="Punishments", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert attrs["punishments"] == []

    def test_unrecorded_attributes(self):
        assert "punishments" in PronotePunishmentsSensor._unrecorded_attributes


# ===================================================================
# TestPronoteMenusSensor
# ===================================================================


class TestPronoteMenusSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["menus"] = [_make_menu(), _make_menu(name="Diner")]
        sensor = PronoteMenusSensor(coord)
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["menus"] = None
        sensor = PronoteMenusSensor(coord)
        assert sensor.native_value is None

    def test_native_value_empty(self):
        coord = _make_coordinator()
        coord.data["menus"] = []
        sensor = PronoteMenusSensor(coord)
        assert sensor.native_value == 0

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["menus"] = [_make_menu()]
        sensor = PronoteMenusSensor(coord)
        attrs = sensor.extra_state_attributes

        assert "menus" in attrs
        assert len(attrs["menus"]) == 1
        assert attrs["menus"][0]["name"] == "Dejeuner"

    def test_extra_state_attributes_none(self):
        coord = _make_coordinator()
        coord.data["menus"] = None
        sensor = PronoteMenusSensor(coord)
        attrs = sensor.extra_state_attributes

        assert attrs["menus"] == []

    def test_unrecorded_attributes(self):
        assert "menus" in PronoteMenusSensor._unrecorded_attributes


# ===================================================================
# TestPronoteInformationAndSurveysSensor
# ===================================================================


class TestPronoteInformationAndSurveysSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["information_and_surveys"] = [_make_info_survey(), _make_info_survey()]
        sensor = PronoteInformationAndSurveysSensor(coord)
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["information_and_surveys"] = None
        sensor = PronoteInformationAndSurveysSensor(coord)
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["information_and_surveys"] = [
            _make_info_survey(read=False),
            _make_info_survey(read=True),
        ]
        sensor = PronoteInformationAndSurveysSensor(coord)
        attrs = sensor.extra_state_attributes

        assert "information_and_surveys" in attrs
        assert len(attrs["information_and_surveys"]) == 2
        assert "unread_count" in attrs
        assert attrs["unread_count"] == 1

    def test_unread_count_all_read(self):
        coord = _make_coordinator()
        coord.data["information_and_surveys"] = [
            _make_info_survey(read=True),
            _make_info_survey(read=True),
        ]
        sensor = PronoteInformationAndSurveysSensor(coord)
        attrs = sensor.extra_state_attributes

        assert attrs["unread_count"] == 0

    def test_unread_count_none_when_data_none(self):
        coord = _make_coordinator()
        coord.data["information_and_surveys"] = None
        sensor = PronoteInformationAndSurveysSensor(coord)
        attrs = sensor.extra_state_attributes

        assert attrs["unread_count"] is None
        assert attrs["information_and_surveys"] == []

    def test_unrecorded_attributes(self):
        assert "information_and_surveys" in PronoteInformationAndSurveysSensor._unrecorded_attributes


# ===================================================================
# TestPronoteCurrentPeriodSensor
# ===================================================================


class TestPronoteCurrentPeriodSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        sensor = PronoteCurrentPeriodSensor(coord)
        assert sensor.native_value == "Trimestre 1"

    def test_native_value_no_period(self):
        coord = _make_coordinator()
        coord.data["current_period"] = None
        # The sensor is initialized with a valid coordinator, then we set data to None.
        # But init reads current_period. So let's create a special case.
        # We need to create the sensor with valid data first, then change data.
        sensor = PronoteCurrentPeriodSensor(coord)
        # Now set data to have None period for testing native_value
        # But current_period has .name in format_period... so we need a more careful approach
        # Actually, the native_value just checks `period.name if period else None`
        # So the sensor was created, now we set current_period to None
        coord.data["current_period"] = None
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        sensor = PronoteCurrentPeriodSensor(coord)
        attrs = sensor.extra_state_attributes

        assert attrs["name"] == "Trimestre 1"
        assert attrs["start"] == date(2025, 9, 1)
        assert attrs["end"] == date(2025, 12, 20)
        assert attrs["is_current_period"] is True
        assert "id" in attrs


# ===================================================================
# TestPronoteOverallAverageSensor
# ===================================================================


class TestPronoteOverallAverageSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["overall_average"] = "14.5"
        sensor = PronoteOverallAverageSensor(
            coord, key="overall_average", name="Overall average", period_key="trimestre_1"
        )
        assert sensor.native_value == "14.5"

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["overall_average"] = None
        sensor = PronoteOverallAverageSensor(
            coord, key="overall_average", name="Overall average", period_key="trimestre_1"
        )
        assert sensor.native_value is None

    def test_native_value_numeric(self):
        coord = _make_coordinator()
        coord.data["overall_average"] = "16.75"
        sensor = PronoteOverallAverageSensor(
            coord, key="overall_average", name="Overall average", period_key="trimestre_1"
        )
        assert sensor.native_value == "16.75"

    def test_extra_state_attributes_period_key(self):
        coord = _make_coordinator()
        sensor = PronoteOverallAverageSensor(
            coord, key="overall_average", name="Overall average", period_key="trimestre_1"
        )
        attrs = sensor.extra_state_attributes

        assert attrs["period_key"] == "trimestre_1"
        assert attrs["is_current_period"] is True

    def test_extra_state_attributes_non_current_period(self):
        coord = _make_coordinator()
        coord.data["overall_average_trimestre_2"] = "15.0"
        sensor = PronoteOverallAverageSensor(
            coord,
            key="overall_average_trimestre_2",
            name="Overall average Trimestre 2",
            period_key="trimestre_2",
        )
        attrs = sensor.extra_state_attributes

        assert attrs["is_current_period"] is False


# ===================================================================
# TestPronotePeriodsSensor
# ===================================================================


class TestPronotePeriodsSensor:
    def test_native_value(self):
        coord = _make_coordinator()
        coord.data["periods"] = [_make_period(), _make_period(name="Trimestre 2")]
        sensor = PronotePeriodsSensor(coord, key="periods", name="Periods")
        assert sensor.native_value == 2

    def test_native_value_none(self):
        coord = _make_coordinator()
        coord.data["periods"] = None
        sensor = PronotePeriodsSensor(coord, key="periods", name="Periods")
        assert sensor.native_value is None

    def test_extra_state_attributes(self):
        coord = _make_coordinator()
        coord.data["periods"] = [
            _make_period(name="Trimestre 1"),
            _make_period(name="Trimestre 2"),
        ]
        sensor = PronotePeriodsSensor(coord, key="periods", name="Periods")
        attrs = sensor.extra_state_attributes

        assert "periods" in attrs
        assert len(attrs["periods"]) == 2
        # The first period matches current_period name, so is_current_period is True
        assert attrs["periods"][0]["is_current_period"] is True
        assert attrs["periods"][1]["is_current_period"] is False

    def test_extra_state_attributes_none(self):
        coord = _make_coordinator()
        coord.data["periods"] = None
        sensor = PronotePeriodsSensor(coord, key="periods", name="Periods")
        attrs = sensor.extra_state_attributes

        assert attrs["periods"] == []

    def test_unrecorded_attributes(self):
        assert "periods" in PronotePeriodsSensor._unrecorded_attributes


# ===================================================================
# TestPronotePeriodRelatedSensor
# ===================================================================


class TestPronotePeriodRelatedSensor:
    def test_is_current_period_true(self):
        coord = _make_coordinator()
        sensor = PronotePeriodRelatedSensor(coord, key="grades", name="Grades", period_key="trimestre_1")
        assert sensor._is_current_period is True

    def test_is_current_period_false(self):
        coord = _make_coordinator()
        sensor = PronotePeriodRelatedSensor(coord, key="grades", name="Grades", period_key="trimestre_2")
        assert sensor._is_current_period is False

    def test_extra_state_attributes_includes_period_info(self):
        coord = _make_coordinator()
        sensor = PronotePeriodRelatedSensor(coord, key="grades", name="Grades", period_key="trimestre_1")
        attrs = sensor.extra_state_attributes

        assert "period_key" in attrs
        assert "is_current_period" in attrs
        assert attrs["period_key"] == "trimestre_1"
        assert attrs["is_current_period"] is True


# ===================================================================
# TestAsyncSetupEntry
# ===================================================================


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_all_sensors(self):
        """Verify async_setup_entry creates the expected number of sensors with no previous periods."""
        coord = _make_coordinator()

        config_entry = MagicMock()
        config_entry.runtime_data = coord

        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), config_entry, async_add_entities)

        async_add_entities.assert_called_once()
        sensors = async_add_entities.call_args[0][0]

        # Count the base sensors (no previous periods):
        # PronoteClassSensor: 1
        # PronoteTimetableSensor: 4 (today, tomorrow, next_day, period)
        # PronoteHomeworkSensor: 2 (homework, homework_period)
        # PronoteGradesSensor: 1
        # PronoteAbsensesSensor: 1
        # PronoteEvaluationsSensor: 1
        # PronoteAveragesSensor: 1
        # PronotePunishmentsSensor: 1
        # PronoteDelaysSensor: 1
        # PronoteInformationAndSurveysSensor: 1
        # PronoteGenericSensor (ical_url): 1
        # PronoteGenericSensor (next_alarm): 1
        # PronoteMenusSensor: 1
        # PronoteOverallAverageSensor: 1
        # PronoteCurrentPeriodSensor: 1
        # PronotePeriodsSensor: 3 (periods, previous_periods, active_periods)
        # Total: 22
        assert len(sensors) == 22

    @pytest.mark.asyncio
    async def test_creates_previous_period_sensors(self):
        """With 1 previous period, verify additional sensors are created (7 per period)."""
        coord = _make_coordinator()
        previous_period = SimpleNamespace(
            name="Trimestre 0",
            start=date(2025, 5, 1),
            end=date(2025, 8, 31),
        )
        coord.data["previous_periods"] = [previous_period]

        # Add data keys for the previous period
        period_key = slugify(previous_period.name, separator="_")
        coord.data[f"grades_{period_key}"] = []
        coord.data[f"averages_{period_key}"] = []
        coord.data[f"absences_{period_key}"] = []
        coord.data[f"delays_{period_key}"] = []
        coord.data[f"evaluations_{period_key}"] = []
        coord.data[f"punishments_{period_key}"] = []
        coord.data[f"overall_average_{period_key}"] = None

        config_entry = MagicMock()
        config_entry.runtime_data = coord

        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), config_entry, async_add_entities)

        async_add_entities.assert_called_once()
        sensors = async_add_entities.call_args[0][0]

        # 22 base sensors + 7 for the previous period
        assert len(sensors) == 22 + 7

    @pytest.mark.asyncio
    async def test_creates_multiple_previous_period_sensors(self):
        """With 2 previous periods, verify additional sensors are created (7 per period)."""
        coord = _make_coordinator()
        previous_periods = [
            SimpleNamespace(name="Trimestre 0", start=date(2025, 1, 1), end=date(2025, 4, 30)),
            SimpleNamespace(name="Semestre 0", start=date(2024, 9, 1), end=date(2024, 12, 31)),
        ]
        coord.data["previous_periods"] = previous_periods

        for period in previous_periods:
            pk = slugify(period.name, separator="_")
            coord.data[f"grades_{pk}"] = []
            coord.data[f"averages_{pk}"] = []
            coord.data[f"absences_{pk}"] = []
            coord.data[f"delays_{pk}"] = []
            coord.data[f"evaluations_{pk}"] = []
            coord.data[f"punishments_{pk}"] = []
            coord.data[f"overall_average_{pk}"] = None

        config_entry = MagicMock()
        config_entry.runtime_data = coord

        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), config_entry, async_add_entities)

        sensors = async_add_entities.call_args[0][0]
        assert len(sensors) == 22 + 14

    @pytest.mark.asyncio
    async def test_sensor_types_present(self):
        """Verify that each expected sensor type is present."""
        coord = _make_coordinator()

        config_entry = MagicMock()
        config_entry.runtime_data = coord

        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), config_entry, async_add_entities)

        sensors = async_add_entities.call_args[0][0]
        sensor_types = {type(s) for s in sensors}

        assert PronoteClassSensor in sensor_types
        assert PronoteTimetableSensor in sensor_types
        assert PronoteHomeworkSensor in sensor_types
        assert PronoteGradesSensor in sensor_types
        assert PronoteAbsensesSensor in sensor_types
        assert PronoteEvaluationsSensor in sensor_types
        assert PronoteAveragesSensor in sensor_types
        assert PronotePunishmentsSensor in sensor_types
        assert PronoteDelaysSensor in sensor_types
        assert PronoteInformationAndSurveysSensor in sensor_types
        assert PronoteGenericSensor in sensor_types
        assert PronoteMenusSensor in sensor_types
        assert PronoteOverallAverageSensor in sensor_types
        assert PronoteCurrentPeriodSensor in sensor_types
        assert PronotePeriodsSensor in sensor_types
