"""Tests for the coordinator helper functions."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.pronote.coordinator import (
    get_absences,
    get_averages,
    get_delays,
    get_evaluations,
    get_grades,
    get_overall_average,
    get_punishments,
)


class TestGetGrades:
    def test_returns_sorted_by_date_desc(self, mock_grade):
        grade1 = mock_grade(date_val=date(2025, 1, 10))
        grade2 = mock_grade(date_val=date(2025, 1, 15))
        grade3 = mock_grade(date_val=date(2025, 1, 5))
        period = SimpleNamespace(name="T1", grades=[grade1, grade2, grade3])

        result = get_grades(period)

        assert result[0].date == date(2025, 1, 15)
        assert result[1].date == date(2025, 1, 10)
        assert result[2].date == date(2025, 1, 5)

    def test_empty_grades(self):
        period = SimpleNamespace(name="T1", grades=[])
        result = get_grades(period)
        assert result == []

    def test_exception_returns_none(self):
        period = MagicMock()
        period.name = "T1"
        type(period).grades = property(lambda self: (_ for _ in ()).throw(Exception("API Error")))

        result = get_grades(period)
        assert result is None


class TestGetAbsences:
    def test_returns_sorted_by_from_date_desc(self, mock_absence):
        abs1 = mock_absence(from_date=datetime(2025, 1, 10, 8, 0))
        abs2 = mock_absence(from_date=datetime(2025, 1, 15, 8, 0))
        period = SimpleNamespace(name="T1", absences=[abs1, abs2])

        result = get_absences(period)

        assert result[0].from_date == datetime(2025, 1, 15, 8, 0)
        assert result[1].from_date == datetime(2025, 1, 10, 8, 0)

    def test_exception_returns_none(self):
        period = MagicMock()
        period.name = "T1"
        type(period).absences = property(lambda self: (_ for _ in ()).throw(Exception("Error")))

        result = get_absences(period)
        assert result is None


class TestGetDelays:
    def test_returns_sorted_by_date_desc(self, mock_delay):
        d1 = mock_delay(date_val=datetime(2025, 1, 10, 8, 0))
        d2 = mock_delay(date_val=datetime(2025, 1, 15, 8, 0))
        period = SimpleNamespace(name="T1", delays=[d1, d2])

        result = get_delays(period)

        assert result[0].date == datetime(2025, 1, 15, 8, 0)
        assert result[1].date == datetime(2025, 1, 10, 8, 0)

    def test_exception_returns_none(self):
        period = MagicMock()
        period.name = "T1"
        type(period).delays = property(lambda self: (_ for _ in ()).throw(Exception("Error")))

        result = get_delays(period)
        assert result is None


class TestGetAverages:
    def test_returns_averages(self, mock_average):
        avg = mock_average()
        period = SimpleNamespace(name="T1", averages=[avg])

        result = get_averages(period)
        assert len(result) == 1

    def test_exception_returns_none(self):
        period = MagicMock()
        period.name = "T1"
        type(period).averages = property(lambda self: (_ for _ in ()).throw(Exception("Error")))

        result = get_averages(period)
        assert result is None


class TestGetPunishments:
    def test_returns_sorted_by_given_date_desc(self, mock_punishment):
        p1 = mock_punishment(given=datetime(2025, 1, 10, 10, 0))
        p2 = mock_punishment(given=datetime(2025, 1, 15, 10, 0))
        period = SimpleNamespace(name="T1", punishments=[p1, p2])

        result = get_punishments(period)

        assert result[0].given == datetime(2025, 1, 15, 10, 0)
        assert result[1].given == datetime(2025, 1, 10, 10, 0)

    def test_exception_returns_none(self):
        period = MagicMock()
        period.name = "T1"
        type(period).punishments = property(lambda self: (_ for _ in ()).throw(Exception("Error")))

        result = get_punishments(period)
        assert result is None


class TestGetEvaluations:
    def test_returns_sorted_by_date_desc_then_name(self, mock_evaluation):
        ev1 = mock_evaluation(name="B eval", date_val=date(2025, 1, 10))
        ev2 = mock_evaluation(name="A eval", date_val=date(2025, 1, 15))
        ev3 = mock_evaluation(name="C eval", date_val=date(2025, 1, 15))
        period = SimpleNamespace(name="T1", evaluations=[ev1, ev2, ev3])

        result = get_evaluations(period)

        # Sorted by date desc, then by name (from the double sort)
        assert result[0].date == date(2025, 1, 15)
        assert result[-1].date == date(2025, 1, 10)

    def test_exception_returns_none(self):
        period = MagicMock()
        period.name = "T1"
        type(period).evaluations = property(lambda self: (_ for _ in ()).throw(Exception("Error")))

        result = get_evaluations(period)
        assert result is None


class TestGetOverallAverage:
    def test_returns_average(self):
        period = SimpleNamespace(name="T1", overall_average="14.5")
        result = get_overall_average(period)
        assert result == "14.5"

    def test_exception_returns_none(self):
        period = MagicMock()
        period.name = "T1"
        type(period).overall_average = property(lambda self: (_ for _ in ()).throw(Exception("Error")))

        result = get_overall_average(period)
        assert result is None
