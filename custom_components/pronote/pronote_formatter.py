"""Data Formatter for the Pronote integration."""

from __future__ import annotations

import logging

from slugify import slugify

from .const import (
    HOMEWORK_DESC_MAX_LENGTH,
)

_LOGGER = logging.getLogger(__name__)


def format_displayed_lesson(lesson):
    if getattr(lesson, "is_detention", False) is True:
        return "RETENUE"
    if lesson.subject:
        return lesson.subject if isinstance(lesson.subject, str) else lesson.subject.name
    return "autre"


def format_lesson(lesson, lunch_break_time):
    return {
        "start_at": lesson.start,
        "end_at": lesson.end,
        "start_time": lesson.start.strftime("%H:%M"),
        "end_time": lesson.end.strftime("%H:%M"),
        "lesson": format_displayed_lesson(lesson),
        "classroom": lesson.room,
        "canceled": lesson.canceled,
        "status": lesson.status,
        "background_color": lesson.color,
        "teacher_name": lesson.teacher,
        "teacher_names": [],
        "classrooms": [lesson.room] if lesson.room else [],
        "outing": lesson.is_outside if lesson.is_outside else False,
        "memo": None,
        "group_name": None,
        "group_names": [],
        "exempted": False,
        "virtual_classrooms": [],
        "num": None,
        "detention": lesson.is_detention,
        "test": False,
        "is_morning": lesson.start.time() < lunch_break_time,
        "is_afternoon": lesson.start.time() >= lunch_break_time,
    }


def format_compact_lesson(lesson, lunch_break_time):
    """Compact representation of a lesson for long-range timetable sensors."""
    return {
        "start_at": lesson.start,
        "end_at": lesson.end,
        "start_time": lesson.start.strftime("%H:%M"),
        "end_time": lesson.end.strftime("%H:%M"),
        "lesson": format_displayed_lesson(lesson),
        "classroom": lesson.room,
        "canceled": lesson.canceled,
        "status": lesson.status,
        "is_morning": lesson.start.time() < lunch_break_time,
        "is_afternoon": lesson.start.time() >= lunch_break_time,
    }


def format_attachment_list(attachments):
    return [
        {
            "name": attachment.name,
            "url": attachment.url,
            "type": attachment.type,
        }
        for attachment in attachments
    ]


def format_homework(homework) -> dict:
    return {
        "date": homework.date,
        "subject": homework.subject,
        "short_description": (homework.description)[0:HOMEWORK_DESC_MAX_LENGTH],
        "description": (homework.description),
        "done": homework.done,
        "background_color": getattr(homework, "background_color", None),
        "files": format_attachment_list(homework.files) if hasattr(homework, "files") and homework.files else None,
    }


def format_grade(grade) -> dict:
    return {
        "date": grade.date,
        "subject": grade.subject if isinstance(grade.subject, str) else grade.subject.name,
        "comment": grade.comment,
        "grade": grade.grade,
        "out_of": grade.grade_out_of,
        "grade_out_of": f"{grade.grade}/{grade.grade_out_of}",
        "coefficient": grade.coefficient,
        "class_average": grade.class_average,
        "is_bonus": grade.is_bonus,
        "is_optional": grade.is_optional,
    }


def format_absence(absence) -> dict:
    return {
        "from": absence.from_date,
        "to": absence.to_date,
        "justified": absence.justified,
        "hours": absence.hours,
        "reason": absence.reason,
    }


def format_delay(delay) -> dict:
    return {
        "date": delay.date,
        "minutes": delay.minutes,
        "justified": delay.justified,
        "reason": delay.reason,
    }


def format_evaluation(evaluation) -> dict:
    return {
        "name": evaluation.name,
        "date": evaluation.date,
        "subject": evaluation.subject,
        "acquisitions": evaluation.acquisitions,
    }


def format_average(average) -> dict:
    return {
        "average": average.student,
        "class": average.class_average,
        "max": average.max,
        "min": average.min,
        "subject": average.subject,
    }


def format_punishment(punishment) -> dict:
    return {
        "date": punishment.given.strftime("%Y-%m-%d") if punishment.given else None,
        "subject": punishment.subject,
        "reason": punishment.reason,
        "duration": str(punishment.duration) if punishment.duration else None,
        "during_lesson": punishment.during_lesson,
        "homework": punishment.homework,
        "circumstances": punishment.circumstances,
    }


def format_food_list(food_list) -> list:
    formatted_food_list = []
    if food_list is None:
        return formatted_food_list

    for food in food_list:
        formatted_food_labels = []
        for label in food.labels:
            formatted_food_labels.append(
                {
                    "name": label.name,
                    "color": label.color,
                }
            )
        formatted_food_list.append(
            {
                "name": food.name,
                "labels": formatted_food_labels,
            }
        )

    return formatted_food_list


def format_menu(menu) -> dict:
    return {
        "name": getattr(menu, "name", None),
        "date": menu.date.strftime("%Y-%m-%d") if hasattr(menu, "date") and menu.date else None,
        "is_lunch": getattr(menu, "is_lunch", None),
        "is_dinner": getattr(menu, "is_dinner", None),
        "first_meal": format_food_list(getattr(menu, "first_meal", None)),
        "main_meal": format_food_list(getattr(menu, "main_meal", None)),
        "side_meal": format_food_list(getattr(menu, "side_meal", None)),
        "other_meal": format_food_list(getattr(menu, "other_meal", None)),
        "cheese": format_food_list(getattr(menu, "cheese", None)),
        "dessert": format_food_list(getattr(menu, "dessert", None)),
    }


def format_information_and_survey(information_and_survey) -> dict:
    return {
        "author": getattr(information_and_survey, "author", None),
        "title": getattr(information_and_survey, "title", None),
        "read": getattr(information_and_survey, "read", None),
        "creation_date": getattr(information_and_survey, "creation_date", None),
        "start_date": getattr(information_and_survey, "start_date", None),
        "end_date": getattr(information_and_survey, "end_date", None),
        "category": getattr(information_and_survey, "category", None),
        "survey": getattr(information_and_survey, "survey", None),
        "anonymous_response": getattr(information_and_survey, "anonymous_response", None),
        "attachments": format_attachment_list(getattr(information_and_survey, "attachments", [])),
        "template": getattr(information_and_survey, "template", None),
        "shared_template": getattr(information_and_survey, "shared_template", None),
        "content": getattr(information_and_survey, "content", None),
    }


def format_period(period, is_current_period: bool) -> dict:
    return {
        "id": slugify(period.name, separator="_"),
        "name": period.name,
        "start": period.start,
        "end": period.end,
        "is_current_period": is_current_period,
    }
