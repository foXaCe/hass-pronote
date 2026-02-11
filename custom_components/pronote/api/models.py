"""Modèles de données pour les réponses API Pronote."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class ChildInfo:
    """Informations sur l'enfant/élève."""

    name: str
    id: str | None = None
    class_name: str | None = None
    establishment: str | None = None


@dataclass(slots=True, frozen=True)
class Lesson:
    """Représente un cours."""

    id: str
    subject: str | None
    start: datetime
    end: datetime
    room: str | None = None
    teacher: str | None = None
    canceled: bool = False
    is_detention: bool = False
    status: str | None = None
    color: str | None = None
    is_outside: bool | None = None


@dataclass(slots=True, frozen=True)
class Grade:
    """Représente une note."""

    id: str
    date: date
    subject: str
    grade: str
    grade_out_of: str
    coefficient: str | None = None
    class_average: str | None = None
    comment: str | None = None
    is_bonus: bool = False
    is_optional: bool = False


@dataclass(slots=True, frozen=True)
class Average:
    """Représente une moyenne par matière."""

    subject: str
    student: str
    class_average: str | None = None
    max: str | None = None
    min: str | None = None


@dataclass(slots=True, frozen=True)
class Absence:
    """Représente une absence."""

    id: str
    from_date: datetime
    to_date: datetime
    justified: bool = False
    hours: str | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class Delay:
    """Représente un retard."""

    id: str
    date: datetime
    minutes: int
    justified: bool = False
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class Punishment:
    """Représente une punition."""

    id: str
    given: date
    subject: str | None = None
    reason: str | None = None
    duration: str | None = None
    during_lesson: bool = False
    homework: str | None = None
    exclusion_dates: list[date] | None = None
    # Deprecated: to be removed after deprecation period
    # Kept for compatibility during transition
    circumstances: str | None = None


@dataclass(slots=True, frozen=True)
class Evaluation:
    """Représente une évaluation."""

    id: str
    name: str
    subject: str | None
    date: datetime
    acquisitions: list[dict[str, Any]] | None = None


@dataclass(slots=True, frozen=True)
class Homework:
    """Représente un devoir à faire."""

    id: str
    date: date
    subject: str | None
    description: str
    done: bool = False
    color: str | None = None
    files: list[dict[str, Any]] | None = None


@dataclass(slots=True, frozen=True)
class PeriodInfo:
    """Informations sur une période scolaire."""

    id: str
    name: str
    start: date
    end: date


@dataclass(slots=True, frozen=True)
class InformationSurvey:
    """Représente une information ou un sondage."""

    id: str
    title: str
    creation_date: datetime
    author: str | None = None
    read: bool = False
    anonymous_response: bool = False


@dataclass(slots=True, frozen=True)
class Menu:
    """Représente un menu de cantine."""

    date: date
    lunch: list[str] | None = None
    dinner: list[str] | None = None


@dataclass(slots=True, frozen=True)
class PronoteData:
    """Conteneur de toutes les données récupérées."""

    child_info: ChildInfo
    lessons_today: list[Lesson] | None = None
    lessons_tomorrow: list[Lesson] | None = None
    lessons_next_day: list[Lesson] | None = None
    lessons_period: list[Lesson] | None = None
    grades: list[Grade] | None = None
    averages: list[Average] | None = None
    overall_average: str | None = None
    absences: list[Absence] | None = None
    delays: list[Delay] | None = None
    punishments: list[Punishment] | None = None
    evaluations: list[Evaluation] | None = None
    homework: list[Homework] | None = None
    homework_period: list[Homework] | None = None
    information_and_surveys: list[InformationSurvey] | None = None
    menus: list[Menu] | None = None
    periods: list[PeriodInfo] | None = None
    current_period: PeriodInfo | None = None
    current_period_key: str | None = None
    previous_periods: list[PeriodInfo] | None = None
    active_periods: list[PeriodInfo] | None = None
    ical_url: str | None = None
    # Dynamic period data stored as dict[period_key, list[Item]]
    previous_period_data: dict[str, Any] | None = None
    # Raw credentials for token refresh
    credentials: dict[str, Any] | None = None
    password: str | None = None


@dataclass(slots=True, frozen=True)
class Credentials:
    """Credentials pour authentification Pronote."""

    pronote_url: str
    username: str
    password: str
    uuid: str | None = None
    client_identifier: str | None = None
