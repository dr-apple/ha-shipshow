"""Shared helpers for ShipShow entities."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ShipShowDataUpdateCoordinator


class ShipShowEntity(CoordinatorEntity[ShipShowDataUpdateCoordinator]):
    """Base ShipShow entity."""

    _attr_has_entity_name = True


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


def tracking_title(tracking: dict[str, Any]) -> str:
    """Return the best human-readable package title."""
    return str(
        tracking.get("title")
        or tracking.get("shorttitle")
        or tracking.get("longtitle")
        or tracking.get("trackingnumber")
        or "Package"
    )


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
