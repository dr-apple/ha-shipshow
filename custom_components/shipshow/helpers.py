"""Shared helpers for ShipShow entities."""

from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import ShipShowDataUpdateCoordinator


class ShipShowEntity(CoordinatorEntity[ShipShowDataUpdateCoordinator]):
    """Base ShipShow entity."""

    _attr_has_entity_name = False


class ShipShowAccountEntity(ShipShowEntity):
    """Base entity for global ShipShow account data."""

    @property
    def device_info(self) -> DeviceInfo:
        """Return global ShipShow device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="ShipShow",
            manufacturer="ShipShow",
            configuration_url="https://www.shipshow.net",
        )

    @property
    def shipshow_attributes(self) -> dict[str, Any]:
        """Return attributes used by dashboards and automations."""
        return {
            "shipshow_scope": "global",
            "shipshow_dashboard_group": "shipshow_global",
        }


class ShipShowTrackingEntity(ShipShowEntity):
    """Base entity tied to one tracking."""

    def __init__(self, coordinator: ShipShowDataUpdateCoordinator, tracking_id: str) -> None:
        super().__init__(coordinator)
        self.tracking_id = tracking_id

    @property
    def tracking(self) -> dict[str, Any]:
        """Return the current tracking payload."""
        return self.coordinator.data.trackings.get(self.tracking_id, {})

    @property
    def available(self) -> bool:
        """Return if the tracking still exists in the latest data."""
        return super().available and self.tracking_id in self.coordinator.data.trackings

    @property
    def device_info(self) -> DeviceInfo:
        """Return package device info."""
        tracking = self.tracking
        carrier = tracking.get("carrier") or {}
        carrier_name = carrier.get("name") or carrier.get("id")
        return DeviceInfo(
            identifiers={(DOMAIN, self.tracking_id)},
            name=tracking_title(tracking),
            manufacturer=carrier_name,
            model=tracking.get("trackingnumber"),
            configuration_url=tracking.get("carrierurl"),
        )

    def tracking_object_id(self, role: str) -> str:
        """Return a stable suggested entity object id."""
        return f"shipshow_lieferung_{tracking_slug(self.tracking_id, self.tracking)}_{role}"

    def tracking_name(self, label: str) -> str:
        """Return a consistent dashboard-friendly tracking entity name."""
        return f"ShipShow Lieferung {tracking_title(self.tracking)} - {label}"

    def tracking_attributes(self, role: str) -> dict[str, Any]:
        """Return attributes used by dashboards and automations."""
        tracking = self.tracking
        group = f"shipshow_lieferung_{tracking_slug(self.tracking_id, tracking)}"
        return {
            "shipshow_scope": "lieferung",
            "shipshow_dashboard_group": "shipshow_lieferungen",
            "shipshow_entity_group": group,
            "shipshow_entity_role": role,
            "shipshow_tracking_id": self.tracking_id,
            "shipshow_sendungsnummer": tracking.get("trackingnumber"),
            "shipshow_titel": tracking_title(tracking),
            "shipshow_dienstleister": tracking_carrier(tracking),
        }


def tracking_title(tracking: dict[str, Any]) -> str:
    """Return the best human-readable package title."""
    return str(
        tracking.get("title")
        or tracking.get("shorttitle")
        or tracking.get("longtitle")
        or tracking.get("trackingnumber")
        or "Package"
    )


def tracking_carrier(tracking: dict[str, Any]) -> str | None:
    """Return carrier name or id."""
    carrier = tracking.get("carrier") or {}
    return carrier.get("name") or carrier.get("id")


def tracking_slug(tracking_id: str, tracking: dict[str, Any]) -> str:
    """Return a stable slug for tracking entity ids and grouping."""
    reference = tracking.get("trackingnumber") or tracking_id
    return slugify(str(reference)) or slugify(str(tracking_id)) or "unbekannt"


def tracking_stops(tracking: dict[str, Any]) -> dict[str, Any] | None:
    """Extract delivery stops from carrier-specific metadata when available."""
    candidates: list[tuple[str, Any]] = []
    for field in ("extra", "config"):
        payload = tracking.get(field)
        candidates.extend(_walk_values(payload, field))

    for field in (
        "deliveryprogressmessage",
        "deliveryProgressMessage",
        "last_status_message",
        "last_status",
    ):
        if value := tracking.get(field):
            candidates.append((field, value))

    history = tracking.get("history") or []
    if isinstance(history, list):
        for index, item in enumerate(history[:3]):
            candidates.extend(_walk_values(item, f"history[{index}]"))

    for path, value in candidates:
        normalized_path = path.lower().replace("_", "")
        if isinstance(value, int) and "stop" in normalized_path:
            return {"remaining": value, "source": path}
        if isinstance(value, str):
            number = _extract_stop_count(value)
            if number is not None:
                return {"remaining": number, "source": path, "message": value}

    return None


def _walk_values(value: Any, path: str) -> list[tuple[str, Any]]:
    """Flatten dict/list values with paths."""
    if isinstance(value, dict):
        values: list[tuple[str, Any]] = []
        for key, item in value.items():
            child_path = f"{path}.{key}"
            values.append((child_path, item))
            values.extend(_walk_values(item, child_path))
        return values
    if isinstance(value, list):
        values = []
        for index, item in enumerate(value):
            values.extend(_walk_values(item, f"{path}[{index}]"))
        return values
    return []


def _extract_stop_count(value: str) -> int | None:
    """Extract a stop count from English/German carrier messages."""
    lowered = value.lower()
    patterns = [
        r"(\d+)\s*(?:stops?|stopps?|stationen?)",
        r"(?:stops?|stopps?|stationen?)\D{0,12}(\d+)",
    ]
    for pattern in patterns:
        if match := re.search(pattern, lowered):
            return int(match.group(1))
    return None


def parse_date(value: Any) -> date | None:
    """Parse a date-only value."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    """Parse ShipShow timestamps."""
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
