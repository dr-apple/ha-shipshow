"""Constants for the ShipShow integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "shipshow"

DEFAULT_API_BASE_URL = "https://api.shipshow.net/external/"
DEFAULT_LIMIT = 50
DEFAULT_MAX_PAGES = 10
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 60

DEFAULT_SORT_BY = "deliverydate"
DEFAULT_SORT_ORDER = "desc"

CONF_API_KEY = "api_key"
CONF_API_BASE_URL = "api_base_url"
CONF_CATEGORY_ID = "category_id"
CONF_INCLUDE_DELIVERED = "include_delivered"
CONF_LIMIT = "limit"
CONF_MAX_PAGES = "max_pages"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SEARCH = "search"
CONF_SORT_BY = "sort_by"
CONF_SORT_ORDER = "sort_order"
CONF_STATUS_FILTER = "status_filter"

SORT_BY_OPTIONS = [
    "deliverydate",
    "carrier",
    "status",
    "dateadded",
    "lastactivity",
    "alphabetical",
]

SORT_ORDER_OPTIONS = ["asc", "desc"]

STATUS_OPTIONS = [
    "inforeceived",
    "transit",
    "outfordelivery",
    "delivered",
    "exception",
    "expired",
    "notfound",
    "pending",
    "undelivered",
]

PLATFORMS = ["sensor", "binary_sensor", "calendar"]

RECOMMENDED_SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
