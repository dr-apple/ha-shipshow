"""Calendar entities for ShipShow deliveries."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShipShowConfigEntry
from .coordinator import ShipShowDataUpdateCoordinator
from .helpers import ShipShowTrackingEntity, parse_date, parse_datetime, tracking_title


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShipShowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ShipShow calendars."""
    coordinator = entry.runtime_data
    manager = ShipShowCalendarManager(coordinator, async_add_entities)
    manager.async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(manager.async_add_new_entities))


class ShipShowCalendarManager:
    """Add dynamic package calendar entities."""

    def __init__(
        self,
        coordinator: ShipShowDataUpdateCoordinator,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities
        self.known_trackings: set[str] = set()

    @callback
    def async_add_new_entities(self) -> None:
        """Add calendars for newly seen packages."""
        entities: list[CalendarEntity] = []
        for tracking_id, tracking in self.coordinator.data.trackings.items():
            if tracking_id in self.known_trackings:
                continue
            if not tracking.get("scheduleddeliverydate"):
                continue
            self.known_trackings.add(tracking_id)
            entities.append(ShipShowDeliveryCalendar(self.coordinator, tracking_id))
        if entities:
            self.async_add_entities(entities)


class ShipShowDeliveryCalendar(ShipShowTrackingEntity, CalendarEntity):
    """Delivery calendar entity for one package."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: ShipShowDataUpdateCoordinator,
        tracking_id: str,
    ) -> None:
        super().__init__(coordinator, tracking_id)
        self._attr_unique_id = f"{tracking_id}_delivery_calendar"

    @property
    def name(self) -> str:
        """Return calendar name."""
        return f"{tracking_title(self.tracking)} Delivery"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next event."""
        return _event_from_tracking(self.tracking)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return events in range."""
        event = _event_from_tracking(self.tracking)
        if event is None:
            return []
        event_start = event.start
        if isinstance(event_start, datetime) and start_date <= event_start <= end_date:
            return [event]
        if not isinstance(event_start, datetime) and start_date.date() <= event_start <= end_date.date():
            return [event]
        return []


def _event_from_tracking(tracking: dict[str, Any]) -> CalendarEvent | None:
    """Build a delivery event from tracking data."""
    delivery_date = parse_date(tracking.get("scheduleddeliverydate"))
    if delivery_date is None:
        return None

    status_time = parse_datetime(tracking.get("last_status_statustimestamp"))
    start: datetime | Any
    end: datetime | Any
    if tracking.get("scheduleddeliverytime"):
        try:
            hour, minute, *_ = str(tracking["scheduleddeliverytime"]).split(":")
            start = datetime.combine(delivery_date, time(int(hour), int(minute)))
            end = start + timedelta(hours=1)
        except (TypeError, ValueError):
            start = delivery_date
            end = delivery_date + timedelta(days=1)
    else:
        start = delivery_date
        end = delivery_date + timedelta(days=1)

    return CalendarEvent(
        summary=tracking_title(tracking),
        start=start,
        end=end,
        description=tracking.get("last_status_message"),
        location=(tracking.get("history") or [{}])[0].get("locationaddress"),
        uid=str(tracking.get("tracking_id") or tracking.get("trackingnumber")),
        recurrence_id=status_time,
    )
