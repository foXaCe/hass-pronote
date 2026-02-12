from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from slugify import slugify

from .const import (
    DEFAULT_GRADES_TO_DISPLAY,
    DEFAULT_LUNCH_BREAK_TIME,
    DOMAIN,
    EVALUATIONS_TO_DISPLAY,
    TIMETABLE_PERIOD_MAX_LESSONS,
    PronoteConfigEntry,
)
from .coordinator import PronoteDataUpdateCoordinator
from .entity import PronoteEntity
from .pronote_formatter import (
    format_absence,
    format_average,
    format_compact_lesson,
    format_delay,
    format_evaluation,
    format_grade,
    format_homework,
    format_information_and_survey,
    format_lesson,
    format_menu,
    format_period,
    format_punishment,
)

PARALLEL_UPDATES = 0

_TIMETABLE_TRANSLATION_KEYS = {
    "lessons_today": "timetable_today",
    "lessons_tomorrow": "timetable_tomorrow",
    "lessons_next_day": "timetable_next_day",
    "lessons_period": "timetable_period",
}


def len_or_none(data):
    return None if data is None else len(data)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PronoteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PronoteDataUpdateCoordinator = config_entry.runtime_data

    current_period_key = slugify(coordinator.data["current_period"].name, separator="_")

    sensors = [
        PronoteClassSensor(coordinator),
        PronoteTimetableSensor(coordinator, key="lessons_today", name="Today's timetable"),
        PronoteTimetableSensor(coordinator, key="lessons_tomorrow", name="Tomorrow's timetable"),
        PronoteTimetableSensor(coordinator, key="lessons_next_day", name="Next day's timetable"),
        PronoteTimetableSensor(coordinator, key="lessons_period", name="Period's timetable"),
        PronoteHomeworkSensor(coordinator, key="homework", name="Homework"),
        PronoteHomeworkSensor(coordinator, key="homework_period", name="Period's homework"),
        # period related sensors
        PronoteGradesSensor(coordinator, key="grades", name="Grades", period_key=current_period_key),
        PronoteAbsensesSensor(coordinator, key="absences", name="Absences", period_key=current_period_key),
        PronoteEvaluationsSensor(
            coordinator,
            key="evaluations",
            name="Evaluations",
            period_key=current_period_key,
        ),
        PronoteAveragesSensor(coordinator, key="averages", name="Averages", period_key=current_period_key),
        PronotePunishmentsSensor(
            coordinator,
            key="punishments",
            name="Punishments",
            period_key=current_period_key,
        ),
        PronoteDelaysSensor(coordinator, key="delays", name="Delays", period_key=current_period_key),
        # generic sensors
        PronoteInformationAndSurveysSensor(coordinator),
        PronoteGenericSensor(coordinator, "ical_url", "Timetable iCal URL", enabled_default=False),
        PronoteGenericSensor(
            coordinator,
            coordinator_key="next_alarm",
            name="Next alarm",
            device_class=SensorDeviceClass.TIMESTAMP,
        ),
        PronoteMenusSensor(coordinator),
        PronoteOverallAverageSensor(
            coordinator,
            key="overall_average",
            name="Overall average",
            period_key=current_period_key,
        ),
        # periods sensors
        PronoteCurrentPeriodSensor(coordinator),
        PronotePeriodsSensor(coordinator, key="periods", name="Periods"),
        PronotePeriodsSensor(coordinator, key="previous_periods", name="previous Periods"),
        PronotePeriodsSensor(coordinator, key="active_periods", name="Active periods"),
    ]

    for period in coordinator.data["previous_periods"]:
        period_key = slugify(period.name, separator="_")
        sensors.extend(
            [
                PronoteGradesSensor(
                    coordinator,
                    key=f"grades_{period_key}",
                    name=f"Grades {period.name}",
                    period_key=period_key,
                    period_name=period.name,
                ),
                PronoteAveragesSensor(
                    coordinator,
                    key=f"averages_{period_key}",
                    name=f"Averages {period.name}",
                    period_key=period_key,
                    period_name=period.name,
                ),
                PronoteAbsensesSensor(
                    coordinator,
                    key=f"absences_{period_key}",
                    name=f"Absences {period.name}",
                    period_key=period_key,
                    period_name=period.name,
                ),
                PronoteDelaysSensor(
                    coordinator,
                    key=f"delays_{period_key}",
                    name=f"Delays {period.name}",
                    period_key=period_key,
                    period_name=period.name,
                ),
                PronoteEvaluationsSensor(
                    coordinator,
                    key=f"evaluations_{period_key}",
                    name=f"Evaluations {period.name}",
                    period_key=period_key,
                    period_name=period.name,
                ),
                PronotePunishmentsSensor(
                    coordinator,
                    key=f"punishments_{period_key}",
                    name=f"Punishments {period.name}",
                    period_key=period_key,
                    period_name=period.name,
                ),
                PronoteOverallAverageSensor(
                    coordinator,
                    key=f"overall_average_{period_key}",
                    name=f"Overall average {period.name}",
                    period_key=period_key,
                    period_name=period.name,
                ),
            ]
        )

    async_add_entities(sensors, False)


class PronoteGenericSensor(PronoteEntity, SensorEntity):
    """Representation of a Pronote sensor."""

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        coordinator_key: str,
        name: str,
        state: str | None = None,
        device_class: SensorDeviceClass | None = None,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator)
        self._coordinator_key = coordinator_key
        self._name = name
        self._state = state

        self._attr_translation_key = coordinator_key
        self._attr_unique_id = f"{DOMAIN}_{self.coordinator.data['sensor_prefix']}_{self._name}"
        self._attr_entity_registry_enabled_default = enabled_default

        if device_class is not None:
            self._attr_device_class = device_class

        self._child_info = coordinator.data["child_info"]
        self._account_type = coordinator.data["account_type"]

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data[self._coordinator_key] is None:
            return None
        if self._state is not None:
            return self._state
        return self.coordinator.data[self._coordinator_key]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "full_name": self._child_info.name,
            "nickname": self.coordinator.config_entry.options.get("nickname"),
            "via_parent_account": self._account_type == "parent",
            "updated_at": self.coordinator.last_update_success_time,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


class PronotePeriodRelatedSensor(PronoteGenericSensor):
    """Representation of a Pronote sensor."""

    def __init__(
        self, coordinator, key: str, name: str, period_key: str, state: str = None, period_name: str | None = None
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name, state)
        self._period_key = period_key
        self._is_current_period = period_key == slugify(coordinator.data["current_period"].name, separator="_")

        if not self._is_current_period and period_name:
            base = key.removesuffix(f"_{self._period_key}")
            self._attr_translation_key = f"{base}_period"
            self._attr_translation_placeholders = {"period": period_name}

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        attributes["period_key"] = self._period_key
        attributes["is_current_period"] = self._is_current_period

        return attributes


class PronoteClassSensor(PronoteGenericSensor):
    """Representation of a Pronote sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(
            coordinator,
            "child_info",
            "Class",
        )
        self._attr_translation_key = "child_class"

    @property
    def native_value(self):
        """Return the class name."""
        return self.coordinator.data["child_info"].class_name

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return super().extra_state_attributes | {
            "class_name": self._child_info.class_name,
            "establishment": self._child_info.establishment,
        }


class PronoteTimetableSensor(PronoteGenericSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"lessons"})

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str,
        name: str,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name)
        self._key = key
        self._start_at = None
        self._end_at = None
        self._lunch_break_start_at = None
        self._lunch_break_end_at = None
        self._attr_translation_key = _TIMETABLE_TRANSLATION_KEYS[key]

    @property
    def native_value(self):
        """Return the number of lessons."""
        return len_or_none(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        lessons = self.coordinator.data[self._key]
        attributes = []
        canceled_counter = None
        single_day = self._key in [
            "lessons_today",
            "lessons_tomorrow",
            "lessons_next_day",
        ]
        is_period = self._key == "lessons_period"
        lunch_break_time = datetime.strptime(
            self.coordinator.config_entry.options.get("lunch_break_time", DEFAULT_LUNCH_BREAK_TIME),
            "%H:%M",
        ).time()

        if lessons is not None:
            self._start_at = None
            self._end_at = None
            self._lunch_break_start_at = None
            self._lunch_break_end_at = None
            canceled_counter = 0

            # For period timetable, keep only upcoming lessons and cap the count
            if is_period:
                now = datetime.now()
                filtered_lessons = [lesson for lesson in lessons if lesson.start >= now]
                if len(filtered_lessons) > TIMETABLE_PERIOD_MAX_LESSONS:
                    filtered_lessons = filtered_lessons[:TIMETABLE_PERIOD_MAX_LESSONS]
            else:
                filtered_lessons = lessons

            for index, lesson in enumerate(filtered_lessons):
                # Skip duplicated canceled lessons sharing the same start time
                if index > 0 and lesson.start == filtered_lessons[index - 1].start and lesson.canceled is True:
                    continue

                if is_period:
                    attributes.append(format_compact_lesson(lesson, lunch_break_time))
                else:
                    attributes.append(format_lesson(lesson, lunch_break_time))
                if lesson.canceled is False and self._start_at is None:
                    self._start_at = lesson.start
                if lesson.canceled is True:
                    canceled_counter += 1
                if single_day is True and lesson.canceled is False:
                    self._end_at = lesson.end
                    if lesson.end.time() < lunch_break_time:
                        self._lunch_break_start_at = lesson.end
                    if self._lunch_break_end_at is None and lesson.start.time() >= lunch_break_time:
                        self._lunch_break_end_at = lesson.start

        result = super().extra_state_attributes | {
            "updated_at": self.coordinator.last_update_success_time,
            "lessons": attributes,
            "canceled_lessons_counter": canceled_counter,
            "day_start_at": self._start_at,
            "day_end_at": self._end_at,
        }

        if single_day is True:
            result["lunch_break_start_at"] = self._lunch_break_start_at
            result["lunch_break_end_at"] = self._lunch_break_end_at

        return result


class PronoteGradesSensor(PronotePeriodRelatedSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"grades"})

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str = "grades",
        name: str = "Grades",
        period_key: str = "current",
        **kwargs,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name, period_key=period_key, **kwargs)
        self._key = key

    @property
    def native_value(self):
        """Return the number of grades (capped by grades_to_display option)."""
        data = self.coordinator.data.get(self._key)
        if data is None:
            return None
        limit = int(self.coordinator.config_entry.options.get("grades_to_display", DEFAULT_GRADES_TO_DISPLAY))
        return min(len(data), limit)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        grades = []
        limit = int(self.coordinator.config_entry.options.get("grades_to_display", DEFAULT_GRADES_TO_DISPLAY))
        if self.coordinator.data[self._key] is not None:
            for grade in self.coordinator.data[self._key][:limit]:
                grades.append(format_grade(grade))

        attributes["grades"] = grades

        return attributes


class PronoteHomeworkSensor(PronoteGenericSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"homework"})

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str = "homework",
        name: str = "Homework",
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name)
        self._key = key

    @property
    def native_value(self):
        """Return the number of homework items."""
        return len_or_none(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        homework_attributes = []
        todo_counter = None
        if self.coordinator.data[self._key] is not None:
            todo_counter = 0
            for homework in self.coordinator.data[self._key]:
                homework_attributes.append(format_homework(homework))
                if homework.done is False:
                    todo_counter += 1

        attributes["homework"] = homework_attributes
        attributes["todo_counter"] = todo_counter

        return attributes


class PronoteAbsensesSensor(PronotePeriodRelatedSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"absences"})

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str = "absences",
        name: str = "Absences",
        period_key: str = "current",
        **kwargs,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name, period_key=period_key, **kwargs)
        self._key = key

    @property
    def native_value(self):
        """Return the number of absences."""
        return len_or_none(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        absences = []
        if self.coordinator.data[self._key] is not None:
            for absence in self.coordinator.data[self._key]:
                absences.append(format_absence(absence))

        attributes["absences"] = absences

        return attributes


class PronoteDelaysSensor(PronotePeriodRelatedSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"delays"})

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str = "delays",
        name: str = "Delays",
        period_key: str = "current",
        **kwargs,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name, period_key=period_key, **kwargs)
        self._key = key

    @property
    def native_value(self):
        """Return the number of delays."""
        return len_or_none(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        delays = []
        if self.coordinator.data[self._key] is not None:
            for delay in self.coordinator.data[self._key]:
                delays.append(format_delay(delay))

        attributes["delays"] = delays

        return attributes


class PronoteEvaluationsSensor(PronotePeriodRelatedSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"evaluations"})

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str = "evaluations",
        name: str = "Evaluations",
        period_key: str = "current",
        **kwargs,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name, period_key=period_key, **kwargs)
        self._key = key

    @property
    def native_value(self):
        """Return the number of evaluations."""
        return len_or_none(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        evaluations = []
        if self.coordinator.data[self._key] is not None:
            for evaluation in self.coordinator.data[self._key][:EVALUATIONS_TO_DISPLAY]:
                evaluations.append(format_evaluation(evaluation))

        attributes["evaluations"] = evaluations

        return attributes


class PronoteAveragesSensor(PronotePeriodRelatedSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"averages"})

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str = "averages",
        name: str = "Averages",
        period_key: str = "current",
        **kwargs,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name, period_key=period_key, **kwargs)
        self._key = key

    @property
    def native_value(self):
        """Return the number of averages."""
        return len_or_none(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        averages = []
        if self.coordinator.data[self._key] is not None:
            for average in self.coordinator.data[self._key]:
                averages.append(format_average(average))

        attributes["averages"] = averages

        return attributes


class PronotePunishmentsSensor(PronotePeriodRelatedSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"punishments"})

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str = "punishments",
        name: str = "Punishments",
        period_key: str = "current",
        **kwargs,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name, period_key=period_key, **kwargs)
        self._key = key

    @property
    def native_value(self):
        """Return the number of punishments."""
        return len_or_none(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        punishments = []
        if self.coordinator.data[self._key] is not None:
            for punishment in self.coordinator.data[self._key]:
                punishments.append(format_punishment(punishment))

        attributes["punishments"] = punishments

        return attributes


class PronoteMenusSensor(PronoteGenericSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"menus"})

    def __init__(self, coordinator) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, "menus", "Menus")

    @property
    def native_value(self):
        """Return the number of menus."""
        return len_or_none(self.coordinator.data["menus"])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        menus = []
        if self.coordinator.data["menus"] is not None:
            for menu in self.coordinator.data["menus"]:
                menus.append(format_menu(menu))

        attributes["menus"] = menus

        return attributes


class PronoteInformationAndSurveysSensor(PronoteGenericSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"information_and_surveys"})

    def __init__(self, coordinator) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(
            coordinator,
            "information_and_surveys",
            "Information and surveys",
        )

    @property
    def native_value(self):
        """Return the number of information and surveys."""
        return len_or_none(self.coordinator.data["information_and_surveys"])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        information_and_surveys = []
        unread_count = None
        if self.coordinator.data["information_and_surveys"] is not None:
            unread_count = 0
            for information_and_survey in self.coordinator.data["information_and_surveys"]:
                information_and_surveys.append(format_information_and_survey(information_and_survey))
                if information_and_survey.read is False:
                    unread_count += 1

        attributes["unread_count"] = unread_count
        attributes["information_and_surveys"] = information_and_surveys

        return attributes


class PronoteCurrentPeriodSensor(PronoteGenericSensor):
    """Representation of a Pronote sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, "current_period", "Current period")

    @property
    def native_value(self):
        """Return the current period name."""
        period = self.coordinator.data["current_period"]
        return period.name if period else None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        period = self.coordinator.data["current_period"]
        attributes = super().extra_state_attributes

        return attributes | format_period(period, True)


class PronoteOverallAverageSensor(PronotePeriodRelatedSensor):
    """Representation of an overall average sensor."""

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
        key: str = "overall_average",
        name: str = "Overall average",
        period_key: str = "current",
        **kwargs,
    ) -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name, period_key=period_key, **kwargs)
        self._key = key

    @property
    def native_value(self):
        """Return the overall average."""
        return self.coordinator.data[self._key]


class PronotePeriodsSensor(PronoteGenericSensor):
    """Representation of a Pronote sensor."""

    _unrecorded_attributes = frozenset({"periods"})

    def __init__(self, coordinator, key: str = "periods", name: str = "periods") -> None:
        """Initialize the Pronote sensor."""
        super().__init__(coordinator, key, name)
        self._key = key

    @property
    def native_value(self):
        """Return the number of periods."""
        return len_or_none(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        periods = []
        current_period_name = self.coordinator.data["current_period"].name
        if self.coordinator.data[self._key] is not None:
            for period in self.coordinator.data[self._key]:
                periods.append(format_period(period, period.name == current_period_name))

        attributes["periods"] = periods

        return attributes
