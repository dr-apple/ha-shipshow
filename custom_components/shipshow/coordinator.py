"""Data coordinator for ShipShow."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ShipShowAuthError, ShipShowClient, ShipShowError, ShipShowQuery
from .const import (
    CONF_CATEGORY_ID,
    CONF_INCLUDE_DELIVERED,
    CONF_LIMIT,
    CONF_MAX_PAGES,
    CONF_SCAN_INTERVAL,
    CONF_SEARCH,
    CONF_SORT_BY,
    CONF_SORT_ORDER,
    CONF_STATUS_FILTER,
    DEFAULT_LIMIT,
    DEFAULT_MAX_PAGES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_ORDER,
    DOMAIN,
    EVENT_DELIVERY_OUT_FOR_DELIVERY,
    EVENT_STOPS_DECREASED,
    MIN_SCAN_INTERVAL,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ShipShowData:
    """Normalized data from ShipShow."""

    trackings: dict[str, dict[str, Any]]
    categories: dict[str, dict[str, Any]]
    status_counts: Counter[str]
    has_more_data: bool


class ShipShowDataUpdateCoordinator(DataUpdateCoordinator[ShipShowData]):
    """Coordinator for ShipShow data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: ShipShowClient,
    ) -> None:
        self.client = client
        scan_interval = max(
            MIN_SCAN_INTERVAL,
            int(config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        super().__init__(
            hass,
            logger=LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> ShipShowData:
        """Fetch data from ShipShow."""
        options = self.config_entry.options
        query = ShipShowQuery(
            category_id=_empty_to_none(options.get(CONF_CATEGORY_ID)),
            search=_empty_to_none(options.get(CONF_SEARCH)),
            statusfilter=_empty_to_none(options.get(CONF_STATUS_FILTER)),
            limit=int(options.get(CONF_LIMIT, DEFAULT_LIMIT)),
            sortby=options.get(CONF_SORT_BY, DEFAULT_SORT_BY),
            sortorder=options.get(CONF_SORT_ORDER, DEFAULT_SORT_ORDER),
        )
        max_pages = int(options.get(CONF_MAX_PAGES, DEFAULT_MAX_PAGES))
        include_delivered = bool(options.get(CONF_INCLUDE_DELIVERED, True))

        try:
            page = await self.client.async_get_all_trackings(query, max_pages)
        except ShipShowAuthError as err:
            raise ConfigEntryAuthFailed from err
        except ShipShowError as err:
            raise UpdateFailed(str(err)) from err

        trackings: dict[str, dict[str, Any]] = {}
        for tracking in page.trackings:
            tracking_id = tracking.get("tracking_id") or tracking.get("id")
            tracking_number = tracking.get("trackingnumber")
            unique_id = str(tracking_id or tracking_number or len(trackings))
            if not include_delivered and tracking.get("last_status") == "delivered":
                continue
            trackings[unique_id] = tracking

        categories = {
            str(category["id"]): category
            for category in page.categories
            if category.get("id")
        }
        status_counts = Counter(
            str(tracking.get("last_status") or "unknown")
            for tracking in trackings.values()
        )

        data = ShipShowData(
            trackings=trackings,
            categories=categories,
            status_counts=status_counts,
            has_more_data=page.has_more_data,
        )
        self._async_fire_delivery_events(data)
        return data

    def _async_fire_delivery_events(self, data: ShipShowData) -> None:
        """Fire Home Assistant events for delivery status and stop updates."""
        previous_data = getattr(self, "data", None)
        previous_trackings = previous_data.trackings if previous_data else {}

        for tracking_id, tracking in data.trackings.items():
            previous = previous_trackings.get(tracking_id)
            status = tracking.get("last_status")
            previous_status = previous.get("last_status") if previous else None
            stops = _tracking_stop_count(tracking)
            previous_stops = _tracking_stop_count(previous) if previous else None

            if status == "outfordelivery" and previous_status != "outfordelivery":
                self.hass.bus.async_fire(
                    EVENT_DELIVERY_OUT_FOR_DELIVERY,
                    _delivery_event_data(
                        tracking_id,
                        tracking,
                        stops,
                        event_kind="in_zustellung",
                    ),
                )

            if (
                stops is not None
                and previous_stops is not None
                and stops < previous_stops
            ):
                self.hass.bus.async_fire(
                    EVENT_STOPS_DECREASED,
                    _delivery_event_data(
                        tracking_id,
                        tracking,
                        stops,
                        event_kind="stopps_weniger",
                        previous_stops=previous_stops,
                    ),
                )


def _empty_to_none(value: Any) -> str | None:
    """Convert Home Assistant form empty strings to None."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _delivery_event_data(
    tracking_id: str,
    tracking: dict[str, Any],
    stops: int | None,
    *,
    event_kind: str,
    previous_stops: int | None = None,
) -> dict[str, Any]:
    """Return event data for delivery automations."""
    title = _tracking_title(tracking)
    data = {
        "ereignis": event_kind,
        "tracking_id": tracking_id,
        "titel": title,
        "sendungsnummer": tracking.get("trackingnumber"),
        "dienstleister": _tracking_carrier(tracking),
        "status": tracking.get("last_status"),
        "meldung": tracking.get("last_status_message"),
        "sendungsverfolgung_url": tracking.get("carrierurl"),
        "stopps_verbleibend": stops,
    }
    if previous_stops is not None:
        data["vorherige_stopps"] = previous_stops
    data["benachrichtigung"] = _notification_text(title, stops, previous_stops)
    return data


def _notification_text(
    title: str,
    stops: int | None,
    previous_stops: int | None,
) -> str:
    """Return a ready-to-send German notification message."""
    if previous_stops is not None and stops is not None:
        return f"{title}: noch {stops} Stopps (vorher {previous_stops})."
    if stops is not None:
        return f"{title} ist in Zustellung. Noch {stops} Stopps."
    return f"{title} ist in Zustellung."


def _tracking_title(tracking: dict[str, Any]) -> str:
    """Return the best human-readable package title."""
    return str(
        tracking.get("title")
        or tracking.get("shorttitle")
        or tracking.get("longtitle")
        or tracking.get("trackingnumber")
        or "Paket"
    )


def _tracking_carrier(tracking: dict[str, Any]) -> str | None:
    """Return carrier name or id."""
    carrier = tracking.get("carrier") or {}
    return carrier.get("name") or carrier.get("id")


def _tracking_stop_count(tracking: dict[str, Any] | None) -> int | None:
    """Extract remaining delivery stops from carrier metadata when available."""
    if not tracking:
        return None

    candidates: list[tuple[str, Any]] = []
    for field in ("extra", "config"):
        candidates.extend(_walk_values(tracking.get(field), field))

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
            return value
        if isinstance(value, str):
            number = _extract_stop_count(value)
            if number is not None:
                return number

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
