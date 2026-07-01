"""Data coordinator for ShipShow."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
import logging
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

        return ShipShowData(
            trackings=trackings,
            categories=categories,
            status_counts=status_counts,
            has_more_data=page.has_more_data,
        )


def _empty_to_none(value: Any) -> str | None:
    """Convert Home Assistant form empty strings to None."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None
