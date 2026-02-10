"""Calendar platform for the Pronote integration."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PronoteConfigEntry
from .coordinator import PronoteDataUpdateCoordinator
from .entity import PronoteEntity
from .pronote_formatter import format_displayed_lesson

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PronoteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pronote calendar based on a config entry."""
    coordinator: PronoteDataUpdateCoordinator = config_entry.runtime_data

    async_add_entities([PronoteCalendar(coordinator)], False)


@callback
def async_get_calendar_event_from_lessons(lesson, timezone) -> CalendarEvent:
    """Get a CalendarEvent from a Pronote Lesson."""
    tz = ZoneInfo(timezone)

    lesson_name = format_displayed_lesson(lesson)
    if lesson.canceled:
        lesson_name = f"Annulé - {lesson_name}"

    return CalendarEvent(
        summary=lesson_name,
        description=f"{lesson.teacher_name} - Salle {lesson.classroom}",
        location=f"Salle {lesson.classroom}",
        start=lesson.start.replace(tzinfo=tz),
        end=lesson.end.replace(tzinfo=tz),
    )


class PronoteCalendar(PronoteEntity, CalendarEntity):
    """Pronote calendar entity."""

    def __init__(
        self,
        coordinator: PronoteDataUpdateCoordinator,
    ) -> None:
        """Initialize the Pronote calendar entity."""
        super().__init__(coordinator)

        child_info = coordinator.data["child_info"]
        calendar_name = child_info.name
        nickname = coordinator.config_entry.options.get("nickname", "")
        if nickname != "":
            calendar_name = nickname

        self._attr_translation_key = "timetable"
        self._attr_translation_placeholders = {"child": calendar_name}
        self._attr_unique_id = f"{DOMAIN}_{coordinator.data['sensor_prefix']}_timetable"
        self._event: CalendarEvent | None = None

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        return self._event

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        lessons = self.coordinator.data.get("lessons_period")
        if not lessons:
            self._event = None
        else:
            now = datetime.now()
            try:
                current_event = next(event for event in lessons if event.start <= now < event.end)
            except StopIteration:
                self._event = None
            else:
                self._event = async_get_calendar_event_from_lessons(current_event, self.hass.config.time_zone)

        super()._handle_coordinator_update()

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        lessons = self.coordinator.data.get("lessons_period")
        if not lessons:
            return []
        return [
            async_get_calendar_event_from_lessons(event, hass.config.time_zone)
            for event in lessons
            if not event.canceled and event.end >= start_date and event.start < end_date
        ]
