"""Binary sensors for ShipShow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShipShowConfigEntry
from .coordinator import ShipShowDataUpdateCoordinator
from .helpers import ShipShowTrackingEntity, tracking_title


@dataclass(frozen=True, kw_only=True)
class ShipShowBinarySensorDescription(BinarySensorEntityDescription):
    """Description for tracking binary sensors."""

    value_fn: Callable[[dict[str, Any]], bool]


BINARY_SENSOR_DESCRIPTIONS = [
    ShipShowBinarySensorDescription(
        key="delivered",
        translation_key="delivered",
        icon="mdi:package-check",
        value_fn=lambda tracking: tracking.get("last_status") == "delivered",
    ),
    ShipShowBinarySensorDescription(
        key="out_for_delivery",
        translation_key="out_for_delivery",
        icon="mdi:truck-fast-outline",
        value_fn=lambda tracking: tracking.get("last_status") == "outfordelivery",
    ),
    ShipShowBinarySensorDescription(
        key="exception",
        translation_key="exception",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda tracking: tracking.get("last_status") == "exception",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShipShowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ShipShow binary sensors."""
    coordinator = entry.runtime_data
    manager = ShipShowBinarySensorManager(coordinator, async_add_entities)
    manager.async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(manager.async_add_new_entities))


class ShipShowBinarySensorManager:
    """Add dynamic package binary sensors."""

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
        """Add binary sensors for newly seen packages."""
        entities: list[BinarySensorEntity] = []
        for tracking_id in self.coordinator.data.trackings:
            if tracking_id in self.known_trackings:
                continue
            self.known_trackings.add(tracking_id)
            entities.extend(
                ShipShowTrackingBinarySensor(self.coordinator, tracking_id, description)
                for description in BINARY_SENSOR_DESCRIPTIONS
            )
        if entities:
            self.async_add_entities(entities)


class ShipShowTrackingBinarySensor(ShipShowTrackingEntity, BinarySensorEntity):
    """Tracking binary sensor."""

    entity_description: ShipShowBinarySensorDescription

    def __init__(
        self,
        coordinator: ShipShowDataUpdateCoordinator,
        tracking_id: str,
        description: ShipShowBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, tracking_id)
        self.entity_description = description
        self._attr_unique_id = f"{tracking_id}_{description.key}"

    @property
    def name(self) -> str:
        """Return entity name."""
        return f"{tracking_title(self.tracking)} {self.entity_description.key}"

    @property
    def is_on(self) -> bool:
        """Return binary state."""
        return self.entity_description.value_fn(self.tracking)
