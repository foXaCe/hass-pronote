"""Fixtures for the Pronote integration tests."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


@pytest.fixture
def mock_lesson():
    """Create a mock lesson."""

    def _make(
        subject_name="Mathématiques",
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

    return _make


@pytest.fixture
def mock_grade():
    """Create a mock grade."""

    def _make(
        subject_name="Mathématiques",
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

    return _make


@pytest.fixture
def mock_absence():
    """Create a mock absence."""

    def _make(
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

    return _make


@pytest.fixture
def mock_delay():
    """Create a mock delay."""

    def _make(
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

    return _make


@pytest.fixture
def mock_evaluation():
    """Create a mock evaluation."""

    def _make(
        name="Contrôle",
        date_val=None,
        subject_name="Mathématiques",
        acquisitions=None,
    ):
        return SimpleNamespace(
            name=name,
            date=date_val or date(2025, 1, 15),
            subject=subject_name,
            acquisitions=acquisitions,
        )

    return _make


@pytest.fixture
def mock_average():
    """Create a mock average."""

    def _make(
        student="14.5",
        class_average="12.0",
        max_avg="18.0",
        min_avg="5.0",
        subject_name="Mathématiques",
    ):
        return SimpleNamespace(
            student=student,
            class_average=class_average,
            max=max_avg,
            min=min_avg,
            subject=subject_name,
        )

    return _make


@pytest.fixture
def mock_punishment():
    """Create a mock punishment."""

    def _make(
        given=None,
        subject="Mathématiques",
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

    return _make


@pytest.fixture
def mock_homework():
    """Create a mock homework."""

    def _make(
        date_val=None,
        subject_name="Mathématiques",
        description="Exercices 1 à 10 page 42",
        done=False,
        color="#FFFFFF",
        files=None,
    ):
        return SimpleNamespace(
            date=date_val or date(2025, 1, 16),
            subject=subject_name,
            description=description,
            done=done,
            background_color=color,
            files=files or [],
        )

    return _make


@pytest.fixture
def mock_period():
    """Create a mock period."""

    def _make(
        name="Trimestre 1",
        start=None,
        end=None,
        grades=None,
        absences=None,
        delays=None,
        averages=None,
        punishments=None,
        evaluations=None,
        overall_average="14.5",
    ):
        return SimpleNamespace(
            name=name,
            start=start or date(2025, 9, 1),
            end=end or date(2025, 12, 20),
            grades=grades if grades is not None else [],
            absences=absences if absences is not None else [],
            delays=delays if delays is not None else [],
            averages=averages if averages is not None else [],
            punishments=punishments if punishments is not None else [],
            evaluations=evaluations if evaluations is not None else [],
            overall_average=overall_average,
        )

    return _make


@pytest.fixture
def mock_menu():
    """Create a mock menu."""

    def _make(
        name="Déjeuner",
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

    return _make


@pytest.fixture
def mock_info_survey():
    """Create a mock information and survey."""

    def _make(
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

    return _make


@pytest.fixture
def mock_attachment():
    """Create a mock attachment."""

    def _make(name="document.pdf", url="https://example.com/doc.pdf", type="file"):
        return SimpleNamespace(name=name, url=url, type=type)

    return _make


@pytest.fixture
def mock_child_info():
    """Create a mock child info."""

    def _make(name="Jean Dupont", class_name="3ème A", establishment="Collège Victor Hugo"):
        return SimpleNamespace(name=name, class_name=class_name, establishment=establishment)

    return _make
