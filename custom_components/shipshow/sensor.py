"""Sensors for ShipShow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShipShowConfigEntry
from .const import DOMAIN
from .coordinator import ShipShowDataUpdateCoordinator
from .helpers import ShipShowEntity, ShipShowTrackingEntity, parse_date, tracking_title


@dataclass(frozen=True, kw_only=True)
class ShipShowTrackingSensorDescription(SensorEntityDescription):
    """Description for tracking sensors."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


TRACKING_SENSOR_DESCRIPTIONS = [
    ShipShowTrackingSensorDescription(
        key="status",
        translation_key="status",
        icon="mdi:package-variant-closed",
        value_fn=lambda tracking: tracking.get("last_status"),
        attrs_fn=lambda tracking: {
            "message": tracking.get("last_status_message"),
            "tracking_number": tracking.get("trackingnumber"),
            "carrier_url": tracking.get("carrierurl"),
            "category_id": tracking.get("category_id"),
            "comments": tracking.get("comments"),
            "media": tracking.get("media"),
            "history": tracking.get("history"),
        },
    ),
    ShipShowTrackingSensorDescription(
        key="last_status_message",
        translation_key="last_status_message",
        icon="mdi:message-text-clock-outline",
        value_fn=lambda tracking: tracking.get("last_status_message"),
    ),
    ShipShowTrackingSensorDescription(
        key="scheduled_delivery",
        translation_key="scheduled_delivery",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda tracking: parse_date(tracking.get("scheduleddeliverydate")),
    ),
    ShipShowTrackingSensorDescription(
        key="days_until_delivery",
        translation_key="days_until_delivery",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=_days_until_delivery,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShipShowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ShipShow sensors."""
    coordinator = entry.runtime_data
    manager = ShipShowSensorManager(coordinator, async_add_entities)
    manager.async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(manager.async_add_new_entities))


class ShipShowSensorManager:
    """Add dynamic package sensors."""

    def __init__(
        self,
        coordinator: ShipShowDataUpdateCoordinator,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities
        self.known_trackings: set[str] = set()
        self.added_account = False

    @callback
    def async_add_new_entities(self) -> None:
        """Add new sensors discovered in coordinator data."""
        entities: list[SensorEntity] = []
        if not self.added_account:
            entities.extend(
                [
                    ShipShowAccountSensor(self.coordinator, "total", "Total Packages"),
                    ShipShowAccountSensor(self.coordinator, "transit", "In Transit"),
                    ShipShowAccountSensor(
                        self.coordinator,
                        "outfordelivery",
                        "Out For Delivery",
                    ),
                    ShipShowAccountSensor(self.coordinator, "delivered", "Delivered"),
                    ShipShowAccountSensor(self.coordinator, "exception", "Exceptions"),
                ]
            )
            self.added_account = True

        for tracking_id in self.coordinator.data.trackings:
            if tracking_id in self.known_trackings:
                continue
            self.known_trackings.add(tracking_id)
            entities.extend(
                ShipShowTrackingSensor(self.coordinator, tracking_id, description)
                for description in TRACKING_SENSOR_DESCRIPTIONS
            )

        if entities:
            self.async_add_entities(entities)


class ShipShowAccountSensor(ShipShowEntity, SensorEntity):
    """Account-level summary sensor."""

    _attr_icon = "mdi:package-variant"
    _attr_native_unit_of_measurement = "packages"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: ShipShowDataUpdateCoordinator,
        status_key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self.status_key = status_key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{status_key}"

    @property
    def native_value(self) -> int:
        """Return count."""
        if self.status_key == "total":
            return len(self.coordinator.data.trackings)
        return self.coordinator.data.status_counts[self.status_key]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return account details."""
        return {
            "categories": list(self.coordinator.data.categories.values()),
            "has_more_data": self.coordinator.data.has_more_data,
        }


class ShipShowTrackingSensor(ShipShowTrackingEntity, SensorEntity):
    """Tracking detail sensor."""

    entity_description: ShipShowTrackingSensorDescription

    def __init__(
        self,
        coordinator: ShipShowDataUpdateCoordinator,
        tracking_id: str,
        description: ShipShowTrackingSensorDescription,
    ) -> None:
        super().__init__(coordinator, tracking_id)
        self.entity_description = description
        self._attr_unique_id = f"{tracking_id}_{description.key}"

    @property
    def name(self) -> str:
        """Return entity name."""
        return f"{tracking_title(self.tracking)} {self.entity_description.name or self.entity_description.key}"

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        return self.entity_description.value_fn(self.tracking)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional details."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.tracking)


def _days_until_delivery(tracking: dict[str, Any]) -> int | None:
    """Calculate days until scheduled delivery."""
    delivery_date = parse_date(tracking.get("scheduleddeliverydate"))
    if delivery_date is None:
        return None
    return (delivery_date - date.today()).days
