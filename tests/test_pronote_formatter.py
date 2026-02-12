"""Tests for the Pronote data formatter."""

from datetime import datetime, time
from types import SimpleNamespace

from custom_components.pronote.pronote_formatter import (
    format_absence,
    format_attachment_list,
    format_average,
    format_delay,
    format_displayed_lesson,
    format_evaluation,
    format_food_list,
    format_grade,
    format_homework,
    format_information_and_survey,
    format_lesson,
    format_menu,
    format_period,
    format_punishment,
)


class TestFormatDisplayedLesson:
    def test_detention(self, mock_lesson):
        lesson = mock_lesson(is_detention=True)
        assert format_displayed_lesson(lesson) == "RETENUE"

    def test_with_subject(self, mock_lesson):
        lesson = mock_lesson(subject_name="Français")
        assert format_displayed_lesson(lesson) == "Français"

    def test_no_subject(self, mock_lesson):
        lesson = mock_lesson()
        lesson.subject = None
        assert format_displayed_lesson(lesson) == "autre"

    def test_detention_takes_priority_over_subject(self, mock_lesson):
        lesson = mock_lesson(subject_name="Français", is_detention=True)
        assert format_displayed_lesson(lesson) == "RETENUE"


class TestFormatLesson:
    def test_morning_lesson(self, mock_lesson):
        lesson = mock_lesson(start=datetime(2025, 1, 15, 8, 0))
        lunch = time(13, 0)
        result = format_lesson(lesson, lunch)

        assert result["start_time"] == "08:00"
        assert result["end_time"] == "09:00"
        assert result["lesson"] == "Mathématiques"
        assert result["classroom"] == "A101"
        assert result["canceled"] is False
        assert result["is_morning"] is True
        assert result["is_afternoon"] is False
        assert result["teacher_name"] == "M. Dupont"

    def test_afternoon_lesson(self, mock_lesson):
        lesson = mock_lesson(start=datetime(2025, 1, 15, 14, 0))
        lunch = time(13, 0)
        result = format_lesson(lesson, lunch)

        assert result["is_morning"] is False
        assert result["is_afternoon"] is True

    def test_canceled_lesson(self, mock_lesson):
        lesson = mock_lesson(canceled=True)
        lunch = time(13, 0)
        result = format_lesson(lesson, lunch)
        assert result["canceled"] is True

    def test_all_fields_present(self, mock_lesson):
        lesson = mock_lesson()
        lunch = time(13, 0)
        result = format_lesson(lesson, lunch)

        expected_keys = {
            "start_at",
            "end_at",
            "start_time",
            "end_time",
            "lesson",
            "classroom",
            "canceled",
            "status",
            "background_color",
            "teacher_name",
            "teacher_names",
            "classrooms",
            "outing",
            "memo",
            "group_name",
            "group_names",
            "exempted",
            "virtual_classrooms",
            "num",
            "detention",
            "test",
            "is_morning",
            "is_afternoon",
        }
        assert set(result.keys()) == expected_keys


class TestFormatAttachmentList:
    def test_empty_list(self):
        assert format_attachment_list([]) == []

    def test_single_attachment(self, mock_attachment):
        att = mock_attachment(name="file.pdf", url="https://example.com/file.pdf", type="file")
        result = format_attachment_list([att])
        assert len(result) == 1
        assert result[0]["name"] == "file.pdf"
        assert result[0]["url"] == "https://example.com/file.pdf"
        assert result[0]["type"] == "file"

    def test_multiple_attachments(self, mock_attachment):
        attachments = [
            mock_attachment(name="a.pdf"),
            mock_attachment(name="b.pdf"),
        ]
        result = format_attachment_list(attachments)
        assert len(result) == 2


class TestFormatHomework:
    def test_basic(self, mock_homework):
        hw = mock_homework()
        result = format_homework(hw)
        assert result["subject"] == "Mathématiques"
        assert result["done"] is False
        assert result["description"] == "Exercices 1 à 10 page 42"
        assert result["files"] is None

    def test_short_description_truncation(self, mock_homework):
        long_desc = "A" * 200
        hw = mock_homework(description=long_desc)
        result = format_homework(hw)
        assert len(result["short_description"]) == 125
        assert result["description"] == long_desc

    def test_done_homework(self, mock_homework):
        hw = mock_homework(done=True)
        result = format_homework(hw)
        assert result["done"] is True

    def test_with_files(self, mock_homework, mock_attachment):
        hw = mock_homework(files=[mock_attachment()])
        result = format_homework(hw)
        assert len(result["files"]) == 1


class TestFormatGrade:
    def test_basic(self, mock_grade):
        grade = mock_grade()
        result = format_grade(grade)
        assert result["grade"] == "15"
        assert result["out_of"] == "20"
        assert result["grade_out_of"] == "15/20"
        assert result["subject"] == "Mathématiques"
        assert result["comment"] == "Bien"

    def test_decimal_replacement(self, mock_grade):
        grade = mock_grade(grade_out_of="20.0", coefficient="2.5", class_average="12.5")
        result = format_grade(grade)
        assert result["out_of"] == "20.0"
        assert result["coefficient"] == "2.5"
        assert result["class_average"] == "12.5"

    def test_bonus_grade(self, mock_grade):
        grade = mock_grade(is_bonus=True)
        result = format_grade(grade)
        assert result["is_bonus"] is True

    def test_optional_grade(self, mock_grade):
        grade = mock_grade(is_optional=True)
        result = format_grade(grade)
        assert result["is_optional"] is True


class TestFormatAbsence:
    def test_basic(self, mock_absence):
        absence = mock_absence()
        result = format_absence(absence)
        assert result["justified"] is False
        assert result["hours"] == "2"
        assert result["reason"] == "Maladie"

    def test_justified_absence(self, mock_absence):
        absence = mock_absence(justified=True)
        result = format_absence(absence)
        assert result["justified"] is True


class TestFormatDelay:
    def test_basic(self, mock_delay):
        delay = mock_delay()
        result = format_delay(delay)
        assert result["minutes"] == 10
        assert result["justified"] is False
        assert result["reason"] == "Transports"

    def test_justified_delay(self, mock_delay):
        delay = mock_delay(justified=True, reason="Grève SNCF")
        result = format_delay(delay)
        assert result["justified"] is True
        assert result["reason"] == "Grève SNCF"


class TestFormatEvaluation:
    def test_basic(self, mock_evaluation):
        ev = mock_evaluation()
        result = format_evaluation(ev)
        assert result["name"] == "Contrôle"
        assert result["subject"] == "Mathématiques"
        assert result["acquisitions"] is None

    def test_with_acquisitions(self, mock_evaluation):
        acq = {"name": "Résoudre une équation", "level": "Acquis"}
        ev = mock_evaluation(acquisitions=[acq])
        result = format_evaluation(ev)
        assert len(result["acquisitions"]) == 1
        assert result["acquisitions"][0]["name"] == "Résoudre une équation"
        assert result["acquisitions"][0]["level"] == "Acquis"


class TestFormatAverage:
    def test_basic(self, mock_average):
        avg = mock_average()
        result = format_average(avg)
        assert result["average"] == "14.5"
        assert result["class"] == "12.0"
        assert result["subject"] == "Mathématiques"
        assert result["max"] == "18.0"
        assert result["min"] == "5.0"


class TestFormatPunishment:
    def test_basic(self, mock_punishment):
        pun = mock_punishment()
        result = format_punishment(pun)
        assert result["date"] == "2025-01-15"
        assert result["subject"] == "Mathématiques"
        assert result["reason"] == "Bavardage"
        assert result["duration"] == "1h"
        assert result["during_lesson"] is False
        assert result["homework"] == ""
        assert result["circumstances"] == "Bavardage"

    def test_with_duration(self, mock_punishment):
        pun = mock_punishment(duration="2h")
        result = format_punishment(pun)
        assert result["duration"] == "2h"


class TestFormatFoodList:
    def test_none_returns_empty(self):
        assert format_food_list(None) == []

    def test_empty_list(self):
        assert format_food_list([]) == []

    def test_food_with_labels(self):
        label = SimpleNamespace(name="Bio", color="#00FF00")
        food = SimpleNamespace(name="Salade verte", labels=[label])
        result = format_food_list([food])
        assert len(result) == 1
        assert result[0]["name"] == "Salade verte"
        assert result[0]["labels"][0]["name"] == "Bio"
        assert result[0]["labels"][0]["color"] == "#00FF00"

    def test_food_without_labels(self):
        food = SimpleNamespace(name="Riz", labels=[])
        result = format_food_list([food])
        assert result[0]["labels"] == []


class TestFormatMenu:
    def test_basic(self, mock_menu):
        menu = mock_menu()
        result = format_menu(menu)
        assert result["name"] == "Déjeuner"
        assert result["date"] == "2025-01-15"
        assert result["is_lunch"] is True
        assert result["is_dinner"] is False

    def test_null_meals(self, mock_menu):
        menu = mock_menu()
        result = format_menu(menu)
        assert result["first_meal"] == []
        assert result["main_meal"] == []
        assert result["dessert"] == []


class TestFormatInformationAndSurvey:
    def test_basic(self, mock_info_survey):
        info = mock_info_survey()
        result = format_information_and_survey(info)
        assert result["author"] == "M. Le Principal"
        assert result["title"] == "Sortie scolaire"
        assert result["read"] is False
        assert result["category"] == "Information"
        assert result["content"] == "Contenu de l'information"
        assert result["attachments"] == []

    def test_read_info(self, mock_info_survey):
        info = mock_info_survey(read=True)
        result = format_information_and_survey(info)
        assert result["read"] is True

    def test_survey(self, mock_info_survey):
        info = mock_info_survey(survey=True, anonymous_response=True)
        result = format_information_and_survey(info)
        assert result["survey"] is True
        assert result["anonymous_response"] is True


class TestFormatPeriod:
    def test_current_period(self, mock_period):
        period = mock_period(name="Trimestre 1")
        result = format_period(period, True)
        assert result["id"] == "trimestre_1"
        assert result["name"] == "Trimestre 1"
        assert result["is_current_period"] is True

    def test_not_current_period(self, mock_period):
        period = mock_period(name="Trimestre 2")
        result = format_period(period, False)
        assert result["is_current_period"] is False
