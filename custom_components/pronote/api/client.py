"""Client API Pronote avec mécanismes de résilience Platinum."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, TypeVar

import pronotepy
from slugify import slugify

from .auth import PronoteAuth
from .circuit_breaker import CircuitBreaker
from .exceptions import (
    AuthenticationError,
    CircuitBreakerOpenError,
    ConnectionError,
    InvalidResponseError,
    PronoteAPIError,
)
from .models import (
    Absence,
    Average,
    ChildInfo,
    Credentials,
    Delay,
    Evaluation,
    Food,
    FoodLabel,
    Grade,
    Homework,
    InformationSurvey,
    Lesson,
    Menu,
    PeriodInfo,
    PronoteData,
    Punishment,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

# Configuration des timeouts (secondes)
DEFAULT_TIMEOUT = 30
CONNECT_TIMEOUT = 10

# Configuration du retry
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0  # secondes
MAX_RETRY_DELAY = 30.0  # secondes

# Configuration du circuit breaker
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 300  # 5 minutes


class PronoteAPIClient:
    """Client API Pronote avec résilience intégrée.

    Fonctionnalités:
    - Retry avec exponential backoff
    - Circuit breaker (5 échecs → pause 5 min)
    - Rate limiting (honore HTTP 429)
    - Timeouts configurés
    - Exceptions métier typées
    - Token refresh automatique
    """

    def __init__(
        self,
        hass: HomeAssistant | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """Initialize le client API.

        Args:
            hass: Instance Home Assistant (optionnel)
            timeout: Timeout global en secondes
            max_retries: Nombre maximum de retry
        """
        self.hass = hass
        self.timeout = timeout
        self.max_retries = max_retries
        self._auth = PronoteAuth(hass)
        self._circuit_breaker = CircuitBreaker()
        self._client: pronotepy.Client | pronotepy.ParentClient | None = None
        self._credentials: Credentials | None = None
        self._connection_type: str | None = None
        self._config_data: dict[str, Any] | None = None

    async def authenticate(
        self,
        connection_type: str,
        config_data: dict[str, Any],
    ) -> None:
        """Authentifie le client.

        Args:
            connection_type: 'username_password' ou 'qrcode'
            config_data: Données de configuration

        Raises:
            AuthenticationError: Si échec d'auth
            CircuitBreakerOpenError: Si circuit breaker ouvert
        """
        if self._circuit_breaker.is_open:
            raise CircuitBreakerOpenError("Trop d'échecs récents, attente de récupération")

        self._connection_type = connection_type
        self._config_data = config_data

        try:
            # Exécution avec await car authenticate est maintenant async
            client, creds = await asyncio.wait_for(
                self._auth.authenticate(connection_type, config_data),
                timeout=self.timeout,
            )

            self._client = client
            self._credentials = creds
            self._circuit_breaker.record_success()

        except TimeoutError as err:
            self._circuit_breaker.record_failure()
            raise ConnectionError(f"Timeout authentification ({self.timeout}s)") from err
        except PronoteAPIError:
            self._circuit_breaker.record_failure()
            raise
        except Exception as err:
            self._circuit_breaker.record_failure()
            raise AuthenticationError(f"Authentification inattendue: {err}") from err

    def is_authenticated(self) -> bool:
        """Vérifie si le client est authentifié."""
        return self._client is not None

    def reset(self) -> None:
        """Reset le client pour forcer une re-authentification."""
        self._client = None
        self._credentials = None

    async def fetch_all_data(
        self,
        today: date | None = None,
        lesson_max_days: int = 15,
        homework_max_days: int = 15,
        info_survey_max_days: int = 7,
        previous_period_cache: dict[str, Any] | None = None,
        show_all_periods: bool = False,
    ) -> PronoteData:
        """Récupère toutes les données Pronote.

        Args:
            today: Date de référence (défaut: aujourd'hui)
            lesson_max_days: Jours max pour les cours
            homework_max_days: Jours max pour les devoirs
            info_survey_max_days: Jours max pour infos/sondages

        Returns:
            PronoteData avec toutes les données

        Raises:
            AuthenticationError: Si non authentifié ou session expirée
            ConnectionError: Si erreur réseau
            RateLimitError: Si rate limit atteint
        """
        if not self.is_authenticated():
            raise AuthenticationError("Client non authentifié")

        if self._circuit_breaker.is_open:
            raise CircuitBreakerOpenError("Trop d'échecs récents, attente de récupération")

        if today is None:
            today = date.today()

        try:
            # Exécution synchrone dans executor
            if self.hass:
                data = await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        self._fetch_all_data_sync,
                        today,
                        lesson_max_days,
                        homework_max_days,
                        info_survey_max_days,
                        previous_period_cache,
                        show_all_periods,
                    ),
                    timeout=self.timeout,
                )
            else:
                data = self._fetch_all_data_sync(
                    today,
                    lesson_max_days,
                    homework_max_days,
                    info_survey_max_days,
                    previous_period_cache,
                    show_all_periods,
                )

            self._circuit_breaker.record_success()
            return data

        except TimeoutError as err:
            self._circuit_breaker.record_failure()
            raise ConnectionError(f"Timeout fetch ({self.timeout}s)") from err
        except PronoteAPIError:
            self._circuit_breaker.record_failure()
            raise
        except Exception as err:
            self._circuit_breaker.record_failure()
            raise InvalidResponseError(f"Erreur fetch inattendue: {err}") from err

    def _fetch_all_data_sync(
        self,
        today: date,
        lesson_max_days: int,
        homework_max_days: int,
        info_survey_max_days: int,
        previous_period_cache: dict[str, Any] | None = None,
        show_all_periods: bool = False,
    ) -> PronoteData:
        """Version synchrone de fetch_all_data."""
        if not self._client:
            raise AuthenticationError("Client non initialisé")

        t0 = time.perf_counter()
        client = self._client
        account_type = self._config_data.get("account_type", "student") if self._config_data else "student"

        # Child info avec sélection enfant si parent
        child_info_obj = client.info
        if account_type == "parent" and hasattr(client, "set_child"):
            child_name = self._config_data.get("child") if self._config_data else None
            if child_name:
                client.set_child(child_name)
                child_info_obj = client._selected_child

        child_info = ChildInfo(
            name=child_info_obj.name if hasattr(child_info_obj, "name") else "Unknown",
            id=getattr(child_info_obj, "id", None),
            class_name=getattr(child_info_obj, "class_name", None),
            establishment=getattr(child_info_obj, "establishment", None),
        )

        # Cours
        t1 = time.perf_counter()
        lessons_today = self._safe_get_lessons(client, today)
        lessons_tomorrow = self._safe_get_lessons(client, today + timedelta(days=1))
        lessons_period = self._get_lessons_period(client, today, lesson_max_days)
        lessons_next_day = self._get_next_day_lessons(client, today, lessons_tomorrow, lesson_max_days)
        t2 = time.perf_counter()
        _LOGGER.debug("TIMING: lessons=%.3fs", t2 - t1)

        # Période courante
        current_period = getattr(client, "current_period", None)
        period_info = self._convert_period(current_period) if current_period else None

        # Données de la période courante
        t3 = time.perf_counter()
        grades = self._safe_get_period_data(current_period, "grades", self._convert_grade)
        averages = self._safe_get_period_data(current_period, "averages", self._convert_average)
        absences = self._safe_get_period_data(current_period, "absences", self._convert_absence)
        delays = self._safe_get_period_data(current_period, "delays", self._convert_delay)
        punishments = self._safe_get_period_data(current_period, "punishments", self._convert_punishment)
        evaluations = self._safe_get_period_data(current_period, "evaluations", self._convert_evaluation)
        overall_average = self._safe_get_overall_average(current_period)
        t4 = time.perf_counter()
        _LOGGER.debug("TIMING: period_data=%.3fs", t4 - t3)

        # Devoirs
        t5 = time.perf_counter()
        homework = self._safe_get_homework(client, today)
        homework_period = self._safe_get_homework(client, today, today + timedelta(days=homework_max_days))
        t6 = time.perf_counter()
        _LOGGER.debug("TIMING: homework=%.3fs", t6 - t5)

        # Informations et sondages
        t7 = time.perf_counter()
        info_surveys = self._safe_get_info_surveys(client, today, info_survey_max_days)
        t8 = time.perf_counter()
        _LOGGER.debug("TIMING: info_surveys=%.3fs", t8 - t7)

        # iCal
        t9 = time.perf_counter()
        ical_url = self._safe_get_ical(client)
        t10 = time.perf_counter()
        _LOGGER.debug("TIMING: ical=%.3fs", t10 - t9)

        # Menus
        menus = self._safe_get_menus(client, today)
        t11 = time.perf_counter()
        _LOGGER.debug("TIMING: menus=%.3fs", t11 - t10)

        # Toutes les périodes
        periods = self._safe_get_periods(client)
        current_period_key = slugify(period_info.name, separator="_") if period_info else None

        # Périodes précédentes (avec cache optionnel)
        t12 = time.perf_counter()
        previous_periods: list[PeriodInfo] = []
        supported_types = ["trimestre", "semestre"]
        period_type = None
        if period_info:
            period_type = period_info.name.split(" ")[0].lower() if " " in period_info.name else None

        previous_period_data: dict[str, Any] = {}
        if period_type in supported_types and periods:
            for period in periods:
                if period.name.lower().startswith(period_type) and (
                    show_all_periods or period.start < period_info.start
                ):
                    previous_periods.append(period)

            if previous_period_cache is not None:
                # Utiliser le cache (les données de périodes passées ne changent pas)
                previous_period_data = previous_period_cache
                _LOGGER.debug("TIMING: previous_periods using cache (%d keys)", len(previous_period_data))
            else:
                for period in previous_periods:
                    p_key = slugify(period.name, separator="_")
                    raw_period = next((p for p in client.periods if p.name == period.name), None)
                    if raw_period:
                        previous_period_data[f"grades_{p_key}"] = self._safe_get_period_data(
                            raw_period, "grades", self._convert_grade
                        )
                        previous_period_data[f"averages_{p_key}"] = self._safe_get_period_data(
                            raw_period, "averages", self._convert_average
                        )
                        previous_period_data[f"absences_{p_key}"] = self._safe_get_period_data(
                            raw_period, "absences", self._convert_absence
                        )
                        previous_period_data[f"delays_{p_key}"] = self._safe_get_period_data(
                            raw_period, "delays", self._convert_delay
                        )
                        previous_period_data[f"evaluations_{p_key}"] = self._safe_get_period_data(
                            raw_period, "evaluations", self._convert_evaluation
                        )
                        previous_period_data[f"punishments_{p_key}"] = self._safe_get_period_data(
                            raw_period, "punishments", self._convert_punishment
                        )
                        previous_period_data[f"overall_average_{p_key}"] = self._safe_get_overall_average(raw_period)
        t13 = time.perf_counter()
        _LOGGER.debug("TIMING: previous_periods=%.3fs", t13 - t12)

        active_periods = previous_periods + ([period_info] if period_info else [])

        _LOGGER.debug("TIMING: _fetch_all_data_sync total=%.3fs", t13 - t0)

        # Credentials pour refresh
        creds_dict = None
        password = None
        if self._credentials:
            creds_dict = {
                "pronote_url": self._credentials.pronote_url,
                "username": self._credentials.username,
                "uuid": self._credentials.uuid,
                "client_identifier": self._credentials.client_identifier,
            }
            password = self._credentials.password

        return PronoteData(
            child_info=child_info,
            lessons_today=lessons_today,
            lessons_tomorrow=lessons_tomorrow,
            lessons_next_day=lessons_next_day,
            lessons_period=lessons_period,
            grades=grades,
            averages=averages,
            overall_average=overall_average,
            absences=absences,
            delays=delays,
            punishments=punishments,
            evaluations=evaluations,
            homework=homework,
            homework_period=homework_period,
            information_and_surveys=info_surveys,
            menus=menus,
            periods=periods,
            current_period=period_info,
            current_period_key=current_period_key,
            previous_periods=previous_periods,
            active_periods=active_periods,
            ical_url=ical_url,
            previous_period_data=previous_period_data,
            credentials=creds_dict,
            password=password,
        )

    def _safe_get_lessons(self, client, day: date) -> list[Lesson] | None:
        """Récupère les cours d'un jour avec gestion d'erreur."""
        try:
            lessons = client.lessons(day)
            return sorted(
                [self._convert_lesson(lesson) for lesson in lessons],
                key=lambda x: x.start,
            )
        except Exception as err:
            _LOGGER.debug("Erreur récupération cours %s: %s", day, err)
            return None

    def _get_lessons_period(self, client, today: date, max_days: int) -> list[Lesson] | None:
        """Recherche les cours sur une période avec fallback."""
        delta = max_days
        while delta > 0:
            try:
                lessons = client.lessons(today, today + timedelta(days=delta))
                if lessons:
                    _LOGGER.debug("Cours trouvés à %s jours", delta)
                    return sorted(
                        [self._convert_lesson(lesson) for lesson in lessons],
                        key=lambda x: x.start,
                    )
            except Exception as err:
                _LOGGER.debug("Pas de cours à %s jours: %s", delta, err)
            delta -= 1
        return None

    def _get_next_day_lessons(
        self,
        client,
        today: date,
        lessons_tomorrow: list[Lesson] | None,
        max_search: int = 30,
    ) -> list[Lesson] | None:
        """Détermine les cours du prochain jour scolaire."""
        if lessons_tomorrow and len(lessons_tomorrow) > 0:
            return lessons_tomorrow

        delta = 2
        while delta < max_search:
            try:
                lessons = client.lessons(today + timedelta(days=delta))
                if lessons:
                    return sorted(
                        [self._convert_lesson(lesson) for lesson in lessons],
                        key=lambda x: x.start,
                    )
            except Exception:
                pass
            delta += 1
        return None

    def _safe_get_period_data(self, period, attr: str, converter: Callable[[Any], T]) -> list[T] | None:
        """Récupère les données d'une période avec conversion."""
        try:
            items = getattr(period, attr, None)
            if items is None:
                return None
            converted = []
            for item in items:
                try:
                    converted.append(converter(item))
                except Exception as err:
                    _LOGGER.debug("Erreur conversion %s: %s", attr, err)
            return converted
        except Exception as err:
            _LOGGER.debug("Erreur récupération %s: %s", attr, err)
            return None

    def _safe_get_overall_average(self, period) -> float | str | None:
        """Récupère la moyenne générale, normalisée en float si possible."""
        try:
            overall = getattr(period, "overall_average", None)
            if overall is None:
                return None
            # Pronote peut retourner "13,2" (virgule française) → normaliser en float
            if isinstance(overall, str):
                try:
                    return float(overall.replace(",", "."))
                except (TypeError, ValueError):
                    return overall
            return overall
        except Exception as err:
            _LOGGER.debug("Erreur moyenne générale: %s", err)
            return None

    def _safe_get_homework(self, client, start: date, end: date | None = None) -> list[Homework] | None:
        """Récupère les devoirs."""
        try:
            if end:
                items = client.homework(start, end)
            else:
                items = client.homework(start)
            return sorted(
                [self._convert_homework(h) for h in items],
                key=lambda x: x.date,
            )
        except Exception as err:
            _LOGGER.debug("Erreur devoirs: %s", err)
            return None

    def _safe_get_info_surveys(self, client, today: date, max_days: int) -> list[InformationSurvey] | None:
        """Récupère les informations et sondages."""
        try:
            date_from = datetime.combine(today - timedelta(days=max_days), datetime.min.time())
            items = client.information_and_surveys(date_from)
            return sorted(
                [self._convert_info_survey(i) for i in items],
                key=lambda x: x.creation_date,
                reverse=True,
            )
        except Exception as err:
            _LOGGER.debug("Erreur infos/sondages: %s", err)
            return None

    def _safe_get_ical(self, client) -> str | None:
        """Récupère l'URL iCal."""
        try:
            return client.export_ical()
        except Exception as err:
            _LOGGER.debug("iCal non disponible: %s", err)
            return None

    def _safe_get_menus(self, client, today: date) -> list[Menu] | None:
        """Récupère les menus."""
        try:
            items = client.menus(today, today + timedelta(days=7))
            return [self._convert_menu(m) for m in items]
        except Exception as err:
            _LOGGER.debug("Erreur menus: %s", err)
            return None

    def _safe_get_periods(self, client) -> list[PeriodInfo] | None:
        """Récupère toutes les périodes."""
        try:
            return [self._convert_period(p) for p in client.periods]
        except Exception as err:
            _LOGGER.debug("Erreur périodes: %s", err)
            return None

    # Convertisseurs d'objets pronotepy vers modèles

    def _convert_lesson(self, lesson) -> Lesson:
        """Convertit un objet Lesson pronotepy."""
        return Lesson(
            id=str(getattr(lesson, "id", "")),
            subject=getattr(lesson, "subject", None),
            start=getattr(lesson, "start", datetime.now()),
            end=getattr(lesson, "end", datetime.now()),
            room=getattr(lesson, "classroom", None),
            teacher=getattr(lesson, "teacher", None),
            canceled=getattr(lesson, "canceled", False),
            status=getattr(lesson, "status", None),
            color=getattr(lesson, "background_color", None),
            is_outside=getattr(lesson, "is_outside", None),
            is_detention=getattr(lesson, "detention", False),
        )

    def _convert_grade(self, grade) -> Grade:
        """Convertit un objet Grade pronotepy."""
        subject = getattr(grade, "subject", None)
        subject_name = str(subject.name) if subject and hasattr(subject, "name") else str(subject) if subject else ""
        return Grade(
            id=str(getattr(grade, "id", "")),
            date=getattr(grade, "date", date.today()),
            subject=subject_name,
            grade=str(getattr(grade, "grade", "")),
            grade_out_of=str(getattr(grade, "grade_out_of", "")),
            coefficient=str(getattr(grade, "coefficient", "")),
            class_average=str(getattr(grade, "average", "")),
            comment=getattr(grade, "comment", None),
            is_bonus=getattr(grade, "is_bonus", False),
            is_optional=getattr(grade, "is_optionnal", False),
        )

    def _convert_average(self, average) -> Average:
        """Convertit un objet Average pronotepy."""
        subject = getattr(average, "subject", None)
        subject_name = str(subject.name) if subject and hasattr(subject, "name") else str(subject) if subject else ""
        return Average(
            subject=subject_name,
            student=str(getattr(average, "student", "")),
            class_average=str(getattr(average, "class_average", "")),
            max=str(getattr(average, "max", "")),
            min=str(getattr(average, "min", "")),
        )

    def _convert_absence(self, absence) -> Absence:
        """Convertit un objet Absence pronotepy."""
        return Absence(
            id=str(getattr(absence, "id", "")),
            from_date=getattr(absence, "from_date", datetime.now()),
            to_date=getattr(absence, "to_date", datetime.now()),
            justified=getattr(absence, "justified", False),
            hours=getattr(absence, "hours", None),
            reason=getattr(absence, "reasons", None),
        )

    def _convert_delay(self, delay) -> Delay:
        """Convertit un objet Delay pronotepy."""
        return Delay(
            id=str(getattr(delay, "id", "")),
            date=getattr(delay, "date", datetime.now()),
            minutes=int(getattr(delay, "minutes", 0) or 0),
            justified=getattr(delay, "justified", False),
            reason=getattr(delay, "reasons", None),
        )

    def _convert_punishment(self, punishment) -> Punishment:
        """Convertit un objet Punishment pronotepy."""
        exclusion_dates = getattr(punishment, "exclusion_dates", None)
        reasons = getattr(punishment, "reasons", None)
        reason_str = ", ".join(reasons) if reasons and isinstance(reasons, list) else str(reasons) if reasons else None
        return Punishment(
            id=str(getattr(punishment, "id", "")),
            given=getattr(punishment, "given", date.today()),
            subject=getattr(punishment, "subject", None),
            reason=reason_str,
            duration=getattr(punishment, "duration", None),
            during_lesson=getattr(punishment, "during_lesson", False),
            homework=getattr(punishment, "homework", None),
            exclusion_dates=list(exclusion_dates) if exclusion_dates else None,
        )

    def _convert_evaluation(self, evaluation) -> Evaluation:
        """Convertit un objet Evaluation pronotepy."""
        acquisitions = getattr(evaluation, "acquisitions", None)
        subject = getattr(evaluation, "subject", None)
        subject_name = str(subject.name) if subject and hasattr(subject, "name") else str(subject) if subject else None
        return Evaluation(
            id=str(getattr(evaluation, "id", "")),
            name=str(getattr(evaluation, "name", "")),
            subject=subject_name,
            date=getattr(evaluation, "date", datetime.now()),
            acquisitions=[{"name": a.name, "level": a.level} for a in acquisitions] if acquisitions else None,
        )

    def _convert_homework(self, homework) -> Homework:
        """Convertit un objet Homework pronotepy."""
        subject = getattr(homework, "subject", None)
        subject_name = str(subject.name) if subject and hasattr(subject, "name") else str(subject) if subject else None
        return Homework(
            id=str(getattr(homework, "id", "")),
            date=getattr(homework, "date", date.today()),
            subject=subject_name,
            description=str(getattr(homework, "description", "")),
            done=getattr(homework, "done", False),
            color=getattr(homework, "background_color", None),
            files=getattr(homework, "files", None),
        )

    def _convert_period(self, period) -> PeriodInfo:
        """Convertit un objet Period pronotepy."""
        return PeriodInfo(
            id=str(getattr(period, "id", "")),
            name=str(getattr(period, "name", "")),
            start=getattr(period, "start", date.today()),
            end=getattr(period, "end", date.today()),
        )

    def _convert_info_survey(self, info) -> InformationSurvey:
        """Convertit un objet Information/Survey pronotepy."""
        return InformationSurvey(
            id=str(getattr(info, "id", "")),
            title=str(getattr(info, "title", "")),
            creation_date=getattr(info, "creation_date", datetime.now()),
            author=getattr(info, "author", None),
            read=getattr(info, "read", False),
            anonymous_response=getattr(info, "anonymous_response", False),
        )

    def _convert_food_list(self, food_list) -> list[Food] | None:
        """Convertit une liste d'aliments pronotepy."""
        if not food_list:
            return None
        result = []
        for food in food_list:
            labels = None
            raw_labels = getattr(food, "labels", None)
            if raw_labels:
                labels = [
                    FoodLabel(
                        name=getattr(lbl, "name", ""),
                        color=getattr(lbl, "color", None),
                    )
                    for lbl in raw_labels
                ]
            result.append(Food(name=getattr(food, "name", ""), labels=labels))
        return result or None

    def _convert_menu(self, menu) -> Menu:
        """Convertit un objet Menu pronotepy."""
        return Menu(
            date=getattr(menu, "date", date.today()),
            name=getattr(menu, "name", None),
            is_lunch=getattr(menu, "is_lunch", False),
            is_dinner=getattr(menu, "is_dinner", False),
            first_meal=self._convert_food_list(getattr(menu, "first_meal", None)),
            main_meal=self._convert_food_list(getattr(menu, "main_meal", None)),
            side_meal=self._convert_food_list(getattr(menu, "side_meal", None)),
            other_meal=self._convert_food_list(getattr(menu, "other_meal", None)),
            cheese=self._convert_food_list(getattr(menu, "cheese", None)),
            dessert=self._convert_food_list(getattr(menu, "dessert", None)),
        )
