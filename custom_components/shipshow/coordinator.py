"""Data coordinator for ShipShow."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ShipShowAuthError, ShipShowClient, ShipShowError, ShipShowQuery
from .const import (
    CONF_CATEGORY_ID,
    CONF_DELIVERED_KEEP_DAYS,
    CONF_INCLUDE_DELIVERED,
    CONF_LIMIT,
    CONF_MAX_PAGES,
    CONF_SCAN_INTERVAL,
    CONF_SEARCH,
    CONF_SORT_BY,
    CONF_SORT_ORDER,
    CONF_STATUS_FILTER,
    DEFAULT_DELIVERED_KEEP_DAYS,
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
from .delivery import stops_field, tracking_arrival

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
        self._gone_since: dict[str, str] = {}
        self._delivered_since: dict[str, str] = {}
        self._store: Store[dict[str, dict[str, str]]] = Store(
            hass, 1, f"{DOMAIN}_gone_since_{config_entry.entry_id}"
        )
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

    async def async_load_state(self) -> None:
        """Load persisted delivered/missing timestamps."""
        stored = await self._store.async_load() or {}
        self._gone_since = dict(stored.get("gone", {}))
        self._delivered_since = dict(stored.get("delivered", {}))

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

        keep_days = int(options.get(CONF_DELIVERED_KEEP_DAYS, DEFAULT_DELIVERED_KEEP_DAYS))
        now = dt_util.utcnow()
        known = self._known_tracking_ids() if keep_days > 0 else set()
        delivered_ids: set[str] = set()
        expired_ids: set[str] = set()
        trackings: dict[str, dict[str, Any]] = {}
        for tracking in page.trackings:
            tracking_id = tracking.get("tracking_id") or tracking.get("id")
            tracking_number = tracking.get("trackingnumber")
            unique_id = str(tracking_id or tracking_number or len(trackings))
            if tracking.get("last_status") == "delivered":
                if keep_days > 0:
                    # Keep delivered packages for N days after we first saw them delivered.
                    # Packages we never tracked (old history) stay out.
                    if unique_id not in known and unique_id not in self._delivered_since:
                        continue
                    delivered_ids.add(unique_id)
                    since = dt_util.parse_datetime(self._delivered_since.get(unique_id, ""))
                    if since is None:
                        self._delivered_since[unique_id] = now.isoformat()
                        since = now
                        self._store.async_delay_save(self._state_to_save, 10)
                    if now - since >= timedelta(days=keep_days):
                        expired_ids.add(unique_id)
                        continue
                elif not include_delivered:
                    continue
            trackings[unique_id] = tracking
        if keep_days > 0:
            for stale in [key for key in self._delivered_since if key not in delivered_ids]:
                del self._delivered_since[stale]
                self._store.async_delay_save(self._state_to_save, 10)
        elif self._delivered_since:
            self._delivered_since.clear()
            self._store.async_delay_save(self._state_to_save, 10)

        categories = {
            str(category["id"]): category for category in page.categories if category.get("id")
        }
        status_counts = Counter(
            str(tracking.get("last_status") or "unknown") for tracking in trackings.values()
        )

        data = ShipShowData(
            trackings=trackings,
            categories=categories,
            status_counts=status_counts,
            has_more_data=page.has_more_data,
        )
        self._async_fire_delivery_events(data)
        self._async_remove_stale_devices(data, keep_days, expired_ids)
        return data

    def _known_tracking_ids(self) -> set[str]:
        """Return tracking ids we already have (previous data or a device in the registry)."""
        known = set(self.data.trackings) if getattr(self, "data", None) else set()
        entry_id = self.config_entry.entry_id
        prefix = f"{entry_id}_"
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, entry_id):
            for domain, ident in device.identifiers:
                if domain == DOMAIN and ident.startswith(prefix):
                    known.add(ident[len(prefix) :])
        return known

    def _state_to_save(self) -> dict[str, dict[str, str]]:
        """Return the persisted timestamps."""
        return {"gone": self._gone_since, "delivered": self._delivered_since}

    def _async_remove_stale_devices(
        self, data: ShipShowData, keep_days: int, expired_ids: set[str]
    ) -> None:
        """Remove package devices (and their entities) that are expired or vanished.

        Delivered packages are dropped right away once they are older than the keep time
        (``expired_ids``); packages that disappeared from ShipShow without being reported
        as delivered are removed after the same number of days.
        """
        if keep_days <= 0:
            if self._gone_since:
                self._gone_since.clear()
                self._store.async_delay_save(self._state_to_save, 10)
            return
        registry = dr.async_get(self.hass)
        entry_id = self.config_entry.entry_id
        prefix = f"{entry_id}_"
        now = dt_util.utcnow()
        changed = False
        seen: set[str] = set()
        for device in dr.async_entries_for_config_entry(registry, entry_id):
            tracking_id = next(
                (
                    ident[len(prefix) :]
                    for domain, ident in device.identifiers
                    if domain == DOMAIN and ident.startswith(prefix)
                ),
                None,
            )
            if tracking_id is None:  # global ShipShow account device
                continue
            seen.add(device.id)
            if tracking_id in data.trackings:
                changed |= self._gone_since.pop(device.id, None) is not None
                continue
            if tracking_id in expired_ids:
                gone = True
            elif data.has_more_data:  # list is cut off: a missing package may not be gone
                continue
            else:
                since = dt_util.parse_datetime(self._gone_since.get(device.id, ""))
                if since is None:
                    self._gone_since[device.id] = now.isoformat()
                    changed = True
                gone = since is not None and now - since >= timedelta(days=keep_days)
            if gone:
                LOGGER.info("Removing delivered package device %s", device.name)
                registry.async_remove_device(device.id)
                self._gone_since.pop(device.id, None)
                changed = True
        for stale in [key for key in self._gone_since if key not in seen]:
            del self._gone_since[stale]
            changed = True
        if changed:
            self._store.async_delay_save(self._state_to_save, 10)

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

            if stops is not None and previous_stops is not None and stops < previous_stops:
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
    arrival = tracking_arrival(tracking)
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
        "ankunft": arrival["text"],
        "ankunft_von": arrival["von"],
        "ankunft_bis": arrival["bis"],
        "ankunft_geschaetzt": arrival["geschaetzt"],
    }
    if previous_stops is not None:
        data["vorherige_stopps"] = previous_stops
    data["benachrichtigung"] = _notification_text(title, stops, previous_stops, arrival["text"])
    return data


def _notification_text(
    title: str,
    stops: int | None,
    previous_stops: int | None,
    arrival: str | None = None,
) -> str:
    """Return a ready-to-send German notification message."""
    suffix = f" Ankunft {arrival}." if arrival else ""
    if previous_stops is not None and stops is not None:
        return f"{title}: noch {stops} Stopps (vorher {previous_stops}).{suffix}"
    if stops is not None:
        return f"{title} ist in Zustellung. Noch {stops} Stopps.{suffix}"
    return f"{title} ist in Zustellung.{suffix}"


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
    """Extract remaining delivery stops, preferring the API field `deliverystopsremaining`."""
    if not tracking:
        return None

    present, remaining = stops_field(tracking)
    if present:
        return remaining

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
