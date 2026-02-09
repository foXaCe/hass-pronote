"""Fixtures for the Pronote integration tests."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


@pytest.fixture
def mock_subject():
    """Create a mock subject."""

    def _make(name="Mathématiques"):
        return SimpleNamespace(name=name)

    return _make


@pytest.fixture
def mock_lesson(mock_subject):
    """Create a mock lesson."""

    def _make(
        subject_name="Mathématiques",
        start=None,
        end=None,
        canceled=False,
        detention=False,
        teacher_name="M. Dupont",
        classroom="A101",
        status="",
        background_color="#FFFFFF",
        teacher_names=None,
        classrooms=None,
        outing=False,
        memo=None,
        group_name=None,
        group_names=None,
        exempted=False,
        virtual_classrooms=None,
        num=1,
        test=False,
    ):
        if start is None:
            start = datetime(2025, 1, 15, 8, 0)
        if end is None:
            end = start + timedelta(hours=1)
        return SimpleNamespace(
            subject=mock_subject(subject_name),
            start=start,
            end=end,
            canceled=canceled,
            detention=detention,
            teacher_name=teacher_name,
            classroom=classroom,
            status=status,
            background_color=background_color,
            teacher_names=teacher_names or [teacher_name],
            classrooms=classrooms or [classroom],
            outing=outing,
            memo=memo,
            group_name=group_name,
            group_names=group_names or [],
            exempted=exempted,
            virtual_classrooms=virtual_classrooms or [],
            num=num,
            test=test,
        )

    return _make


@pytest.fixture
def mock_grade(mock_subject):
    """Create a mock grade."""

    def _make(
        subject_name="Mathématiques",
        grade="15",
        out_of="20",
        default_out_of="20",
        coefficient="1",
        average="12.5",
        max_grade="18",
        min_grade="5",
        comment="Bien",
        date_val=None,
        is_bonus=False,
        is_optionnal=False,
        is_out_of_20=True,
    ):
        return SimpleNamespace(
            subject=mock_subject(subject_name),
            grade=grade,
            out_of=out_of,
            default_out_of=default_out_of,
            coefficient=coefficient,
            average=average,
            max=max_grade,
            min=min_grade,
            comment=comment,
            date=date_val or date(2025, 1, 15),
            is_bonus=is_bonus,
            is_optionnal=is_optionnal,
            is_out_of_20=is_out_of_20,
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
        days="0",
        reasons=None,
    ):
        return SimpleNamespace(
            from_date=from_date or datetime(2025, 1, 15, 8, 0),
            to_date=to_date or datetime(2025, 1, 15, 10, 0),
            justified=justified,
            hours=hours,
            days=days,
            reasons=reasons or ["Maladie"],
        )

    return _make


@pytest.fixture
def mock_delay():
    """Create a mock delay."""

    def _make(
        date_val=None,
        minutes=10,
        justified=False,
        justification="",
        reasons=None,
    ):
        return SimpleNamespace(
            date=date_val or datetime(2025, 1, 15, 8, 0),
            minutes=minutes,
            justified=justified,
            justification=justification,
            reasons=reasons or ["Transports"],
        )

    return _make


@pytest.fixture
def mock_evaluation(mock_subject):
    """Create a mock evaluation."""

    def _make(
        name="Contrôle",
        domain="Algèbre",
        date_val=None,
        subject_name="Mathématiques",
        description="",
        coefficient=1,
        paliers="",
        teacher="M. Dupont",
        acquisitions=None,
    ):
        return SimpleNamespace(
            name=name,
            domain=domain,
            date=date_val or date(2025, 1, 15),
            subject=mock_subject(subject_name),
            description=description,
            coefficient=coefficient,
            paliers=paliers,
            teacher=teacher,
            acquisitions=acquisitions or [],
        )

    return _make


@pytest.fixture
def mock_average(mock_subject):
    """Create a mock average."""

    def _make(
        student="14.5",
        class_average="12.0",
        max_avg="18.0",
        min_avg="5.0",
        out_of="20",
        default_out_of="20",
        subject_name="Mathématiques",
        background_color="#FFFFFF",
    ):
        return SimpleNamespace(
            student=student,
            class_average=class_average,
            max=max_avg,
            min=min_avg,
            out_of=out_of,
            default_out_of=default_out_of,
            subject=mock_subject(subject_name),
            background_color=background_color,
        )

    return _make


@pytest.fixture
def mock_punishment():
    """Create a mock punishment."""

    def _make(
        given=None,
        during_lesson="Mathématiques",
        reasons=None,
        circumstances="Bavardage",
        nature="Retenue",
        duration="1h",
        homework="",
        exclusion=False,
        homework_documents=None,
        circumstance_documents=None,
        giver="M. Dupont",
        schedule=None,
        schedulable=True,
    ):
        return SimpleNamespace(
            given=given or datetime(2025, 1, 15, 10, 0),
            during_lesson=during_lesson,
            reasons=reasons or ["Bavardage"],
            circumstances=circumstances,
            nature=nature,
            duration=duration,
            homework=homework,
            exclusion=exclusion,
            homework_documents=homework_documents or [],
            circumstance_documents=circumstance_documents or [],
            giver=giver,
            schedule=schedule or [],
            schedulable=schedulable,
        )

    return _make


@pytest.fixture
def mock_homework(mock_subject):
    """Create a mock homework."""

    def _make(
        date_val=None,
        subject_name="Mathématiques",
        description="Exercices 1 à 10 page 42",
        done=False,
        background_color="#FFFFFF",
        files=None,
    ):
        return SimpleNamespace(
            date=date_val or date(2025, 1, 16),
            subject=mock_subject(subject_name),
            description=description,
            done=done,
            background_color=background_color,
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
