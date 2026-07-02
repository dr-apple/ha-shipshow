"""Sensors for ShipShow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShipShowConfigEntry
from .const import DOMAIN
from .coordinator import ShipShowDataUpdateCoordinator
from .helpers import (
    ShipShowEntity,
    ShipShowTrackingEntity,
    parse_date,
    tracking_carrier,
    tracking_stops,
    tracking_title,
)


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
        value_fn=lambda tracking: _status_label(tracking.get("last_status")),
        attrs_fn=lambda tracking: {
            "status_code": tracking.get("last_status"),
            "meldung": tracking.get("last_status_message"),
            "sendungsnummer": tracking.get("trackingnumber"),
            "sendungsverfolgung_url": tracking.get("carrierurl"),
            "kategorie_id": tracking.get("category_id"),
            "kommentare": tracking.get("comments"),
            "medien": tracking.get("media"),
            "verlauf": tracking.get("history"),
            "stopps": tracking_stops(tracking),
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
        value_fn=lambda tracking: _days_until_delivery(tracking),
    ),
]

TRACKING_SENSOR_NAMES = {
    "status": "Status",
    "last_status_message": "Letzte Meldung",
    "scheduled_delivery": "Geplante Lieferung",
    "days_until_delivery": "Tage bis Lieferung",
}


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
                    ShipShowAccountSensor(self.coordinator, "total", "Pakete gesamt"),
                    ShipShowActiveDeliveriesSensor(self.coordinator),
                    ShipShowDeliveryOverviewSensor(self.coordinator),
                    ShipShowAccountSensor(self.coordinator, "transit", "Unterwegs"),
                    ShipShowAccountSensor(
                        self.coordinator,
                        "outfordelivery",
                        "In Zustellung",
                    ),
                    ShipShowAccountSensor(self.coordinator, "delivered", "Zugestellt"),
                    ShipShowAccountSensor(self.coordinator, "exception", "Probleme"),
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


class ShipShowActiveDeliveriesSensor(ShipShowEntity, SensorEntity):
    """Automation-friendly overview of current deliveries."""

    _attr_icon = "mdi:truck-delivery-outline"
    _attr_native_unit_of_measurement = "packages"

    def __init__(self, coordinator: ShipShowDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Aktuelle Lieferungen"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_active_deliveries"

    @property
    def native_value(self) -> int:
        """Return active delivery count."""
        return len(_active_trackings(self.coordinator.data.trackings))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return compact delivery data for automations."""
        deliveries = _sorted_deliveries(self.coordinator.data.trackings)
        next_delivery = deliveries[0] if deliveries else None
        return {
            "lieferungen": deliveries,
            "naechste_lieferung": next_delivery,
            "in_zustellung": [
                item for item in deliveries if item.get("status_code") == "outfordelivery"
            ],
            "mit_stopps": [
                item for item in deliveries if item.get("stopps_verbleibend") is not None
            ],
            "hat_lieferung_in_zustellung": any(
                item.get("status_code") == "outfordelivery" for item in deliveries
            ),
            "hat_probleme": any(
                item.get("status_code") == "exception" for item in deliveries
            ),
        }


class ShipShowDeliveryOverviewSensor(ShipShowEntity, SensorEntity):
    """Human-readable current delivery overview."""

    _attr_icon = "mdi:clipboard-list-outline"

    def __init__(self, coordinator: ShipShowDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Lieferübersicht"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_delivery_overview"

    @property
    def native_value(self) -> str:
        """Return a concise delivery summary."""
        deliveries = _sorted_deliveries(self.coordinator.data.trackings)
        if not deliveries:
            return "Keine aktiven Lieferungen"

        out_for_delivery = [
            item for item in deliveries if item.get("status_code") == "outfordelivery"
        ]
        selected = out_for_delivery[0] if out_for_delivery else deliveries[0]
        stops = selected.get("stopps_verbleibend")
        if stops is not None:
            return f"{selected['titel']} - noch {stops} Stopps"
        if selected.get("geplante_lieferung"):
            return f"{selected['titel']} - {selected['geplante_lieferung']}"
        if selected.get("meldung"):
            return f"{selected['titel']} - {selected['meldung']}"
        return str(selected["titel"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the same automation-friendly overview as attributes."""
        deliveries = _sorted_deliveries(self.coordinator.data.trackings)
        return {
            "aktive_lieferungen": len(deliveries),
            "lieferungen": deliveries,
            "naechste_lieferung": deliveries[0] if deliveries else None,
            "in_zustellung": [
                item for item in deliveries if item.get("status_code") == "outfordelivery"
            ],
            "mit_stopps": [
                item for item in deliveries if item.get("stopps_verbleibend") is not None
            ],
            "hat_lieferung_in_zustellung": any(
                item.get("status_code") == "outfordelivery" for item in deliveries
            ),
            "hat_probleme": any(
                item.get("status_code") == "exception" for item in deliveries
            ),
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
        label = TRACKING_SENSOR_NAMES.get(
            self.entity_description.key,
            self.entity_description.key,
        )
        return f"{tracking_title(self.tracking)} {label}"

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


def _status_label(status: Any) -> str | None:
    """Return German status label."""
    if status is None:
        return None
    return {
        "inforeceived": "Info erhalten",
        "transit": "Unterwegs",
        "outfordelivery": "In Zustellung",
        "delivered": "Zugestellt",
        "exception": "Problem",
        "expired": "Abgelaufen",
        "notfound": "Nicht gefunden",
        "pending": "Ausstehend",
        "undelivered": "Nicht zugestellt",
    }.get(str(status), str(status))


def _active_trackings(
    trackings: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return non-delivered trackings."""
    return {
        tracking_id: tracking
        for tracking_id, tracking in trackings.items()
        if tracking.get("last_status") != "delivered"
    }


def _sorted_deliveries(trackings: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact active deliveries sorted for display."""
    deliveries = [
        _compact_delivery(tracking_id, tracking)
        for tracking_id, tracking in _active_trackings(trackings).items()
    ]
    deliveries.sort(
        key=lambda item: (
            item.get("geplante_lieferung") or "9999-12-31",
            item.get("titel") or "",
        )
    )
    return deliveries


def _compact_delivery(tracking_id: str, tracking: dict[str, Any]) -> dict[str, Any]:
    """Return a compact delivery object suitable for automation attributes."""
    stops = tracking_stops(tracking) or {}
    status_code = tracking.get("last_status")
    return {
        "id": tracking_id,
        "titel": tracking_title(tracking),
        "sendungsnummer": tracking.get("trackingnumber"),
        "dienstleister": tracking_carrier(tracking),
        "status": _status_label(status_code),
        "status_code": status_code,
        "meldung": tracking.get("last_status_message"),
        "geplante_lieferung": tracking.get("scheduleddeliverydate"),
        "tage_bis_lieferung": _days_until_delivery(tracking),
        "sendungsverfolgung_url": tracking.get("carrierurl"),
        "kategorie_id": tracking.get("category_id"),
        "stopps_verbleibend": stops.get("remaining"),
        "stopp_meldung": stops.get("message"),
    }
