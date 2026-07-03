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
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShipShowConfigEntry
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import ShipShowDataUpdateCoordinator
from .helpers import (
    ShipShowAccountEntity,
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
        key="overview",
        translation_key="overview",
        icon="mdi:clipboard-text-outline",
        value_fn=lambda tracking: _tracking_summary(tracking),
        attrs_fn=lambda tracking: _tracking_overview_attributes(tracking),
    ),
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
    "overview": "Übersicht",
    "status": "Status",
    "last_status_message": "Letzte Meldung",
    "scheduled_delivery": "Geplante Lieferung",
    "days_until_delivery": "Tage bis Lieferung",
}

TRACKING_SENSOR_ROLES = {
    "overview": "uebersicht",
    "status": "status",
    "last_status_message": "letzte_meldung",
    "scheduled_delivery": "geplante_lieferung",
    "days_until_delivery": "tage_bis_lieferung",
}

ACCOUNT_SENSOR_ROLES = {
    "total": "pakete_gesamt",
    "transit": "unterwegs",
    "outfordelivery": "in_zustellung",
    "delivered": "zugestellt",
    "exception": "probleme",
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
                    ShipShowScanIntervalSensor(self.coordinator),
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


class ShipShowAccountSensor(ShipShowAccountEntity, SensorEntity):
    """Account-level summary sensor."""

    _attr_icon = "mdi:package-variant"
    _attr_native_unit_of_measurement = "packages"

    def __init__(
        self,
        coordinator: ShipShowDataUpdateCoordinator,
        status_key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self.status_key = status_key
        self.role = ACCOUNT_SENSOR_ROLES.get(status_key, status_key)
        self._attr_name = f"ShipShow {name}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{status_key}"
        self._attr_suggested_object_id = f"shipshow_{self.role}"

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
            **self.shipshow_attributes,
            "shipshow_entity_role": self.role,
            "categories": list(self.coordinator.data.categories.values()),
            "has_more_data": self.coordinator.data.has_more_data,
        }


class ShipShowActiveDeliveriesSensor(ShipShowAccountEntity, SensorEntity):
    """Automation-friendly overview of current deliveries."""

    _attr_icon = "mdi:truck-delivery-outline"
    _attr_native_unit_of_measurement = "packages"

    def __init__(self, coordinator: ShipShowDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "ShipShow Aktuelle Lieferungen"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_active_deliveries"
        self._attr_suggested_object_id = "shipshow_aktuelle_lieferungen"

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
            **self.shipshow_attributes,
            "shipshow_entity_role": "aktuelle_lieferungen",
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


class ShipShowDeliveryOverviewSensor(ShipShowAccountEntity, SensorEntity):
    """Human-readable current delivery overview."""

    _attr_icon = "mdi:clipboard-list-outline"

    def __init__(self, coordinator: ShipShowDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "ShipShow Lieferübersicht"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_delivery_overview"
        self._attr_suggested_object_id = "shipshow_lieferuebersicht"

    @property
    def native_value(self) -> str:
        """Return a concise delivery summary."""
        deliveries = _sorted_deliveries(self.coordinator.data.trackings)
        if not deliveries:
            return "Keine aktiven Lieferungen"

        overview = f"{len(deliveries)} aktiv: "
        lines = [_delivery_overview_line(item) for item in deliveries]
        return _truncate_state(f"{overview}{'; '.join(lines)}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the same automation-friendly overview as attributes."""
        deliveries = _sorted_deliveries(self.coordinator.data.trackings)
        return {
            **self.shipshow_attributes,
            "shipshow_entity_role": "lieferuebersicht",
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


class ShipShowScanIntervalSensor(ShipShowAccountEntity, SensorEntity):
    """Currently configured polling interval."""

    _attr_icon = "mdi:timer-sync-outline"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, coordinator: ShipShowDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "ShipShow Abrufintervall"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_scan_interval"
        self._attr_suggested_object_id = "shipshow_abrufintervall"

    @property
    def native_value(self) -> int:
        """Return active polling interval in seconds."""
        return _scan_interval(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return interval details."""
        return {
            **self.shipshow_attributes,
            "shipshow_entity_role": "abrufintervall",
            "minimum_sekunden": MIN_SCAN_INTERVAL,
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
        self.role = TRACKING_SENSOR_ROLES.get(description.key, description.key)
        self._attr_suggested_object_id = self.tracking_object_id(self.role)

    @property
    def name(self) -> str:
        """Return entity name."""
        label = TRACKING_SENSOR_NAMES.get(
            self.entity_description.key,
            self.entity_description.key,
        )
        return self.tracking_name(label)

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        return self.entity_description.value_fn(self.tracking)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional details."""
        if self.entity_description.attrs_fn is None:
            return self.tracking_attributes(self.role)
        return {
            **self.tracking_attributes(self.role),
            **self.entity_description.attrs_fn(self.tracking),
        }


def _days_until_delivery(tracking: dict[str, Any]) -> int | None:
    """Calculate days until scheduled delivery."""
    delivery_date = parse_date(tracking.get("scheduleddeliverydate"))
    if delivery_date is None:
        return None
    return (delivery_date - date.today()).days


def _scan_interval(coordinator: ShipShowDataUpdateCoordinator) -> int:
    """Return configured polling interval clamped to the supported minimum."""
    return max(
        MIN_SCAN_INTERVAL,
        int(
            coordinator.config_entry.options.get(
                CONF_SCAN_INTERVAL,
                DEFAULT_SCAN_INTERVAL,
            )
        ),
    )


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


def _tracking_summary(tracking: dict[str, Any]) -> str:
    """Return a concise shipment summary for dashboard rows."""
    compact = _compact_delivery("", tracking)
    return _truncate_state(_delivery_overview_line(compact))


def _tracking_overview_attributes(tracking: dict[str, Any]) -> dict[str, Any]:
    """Return all shipment details for the more-info dialog."""
    compact = _compact_delivery("", tracking)
    return {
        "titel": compact["titel"],
        "sendungsnummer": compact["sendungsnummer"],
        "dienstleister": compact["dienstleister"],
        "status": compact["status"],
        "status_code": compact["status_code"],
        "meldung": compact["meldung"],
        "geplante_lieferung": compact["geplante_lieferung"],
        "tage_bis_lieferung": compact["tage_bis_lieferung"],
        "sendungsverfolgung_url": compact["sendungsverfolgung_url"],
        "kategorie_id": compact["kategorie_id"],
        "stopps_verbleibend": compact["stopps_verbleibend"],
        "stopp_meldung": compact["stopp_meldung"],
        "kommentare": tracking.get("comments"),
        "medien": tracking.get("media"),
        "verlauf": tracking.get("history"),
        "rohdaten": tracking,
    }


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


def _delivery_overview_line(delivery: dict[str, Any]) -> str:
    """Return one compact human-readable delivery line."""
    title = str(delivery["titel"])
    stops = delivery.get("stopps_verbleibend")
    if stops is not None:
        return f"{title} - noch {stops} Stopps"
    if delivery.get("geplante_lieferung"):
        return f"{title} - {delivery['geplante_lieferung']}"
    if delivery.get("status"):
        return f"{title} - {delivery['status']}"
    return title


def _truncate_state(value: str) -> str:
    """Keep the visible sensor state below Home Assistant's state length limit."""
    if len(value) <= 255:
        return value
    return f"{value[:252]}..."
