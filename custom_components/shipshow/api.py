"""Async client for the ShipShow external API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import aiohttp
import async_timeout

from .const import DEFAULT_API_BASE_URL, DEFAULT_LIMIT


class ShipShowError(Exception):
    """Base ShipShow API error."""


class ShipShowAuthError(ShipShowError):
    """Raised when the API key is missing, invalid, or not allowed."""


class ShipShowConnectionError(ShipShowError):
    """Raised when ShipShow cannot be reached."""


@dataclass(slots=True)
class ShipShowQuery:
    """Query parameters supported by the documented external API."""

    category_id: str | None = None
    search: str | None = None
    statusfilter: str | None = None
    limit: int = DEFAULT_LIMIT
    offset: int = 0
    sortby: str | None = None
    sortorder: str | None = None

    def as_params(self, api_key: str) -> dict[str, Any]:
        """Return request params, dropping empty optional values."""
        params: dict[str, Any] = {
            "apikey": api_key,
            "limit": max(1, min(50, self.limit)),
            "offset": max(0, self.offset),
        }
        optional = {
            "category_id": self.category_id,
            "search": self.search,
            "statusfilter": self.statusfilter,
            "sortby": self.sortby,
            "sortorder": self.sortorder,
        }
        params.update({key: value for key, value in optional.items() if value})
        return params


@dataclass(slots=True)
class ShipShowPage:
    """A single ShipShow tracking page."""

    trackings: list[dict[str, Any]] = field(default_factory=list)
    categories: list[dict[str, Any]] = field(default_factory=list)
    has_more_data: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


class ShipShowClient:
    """Minimal client for the public ShipShow external API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        api_base_url: str = DEFAULT_API_BASE_URL,
        timeout: int = 20,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._api_base_url = api_base_url.rstrip("/") + "/"
        self._timeout = timeout

    async def async_get_trackings(self, query: ShipShowQuery) -> ShipShowPage:
        """Fetch one page of trackings."""
        url = f"{self._api_base_url}getTrackings"
        try:
            async with async_timeout.timeout(self._timeout):
                response = await self._session.get(
                    url,
                    params=query.as_params(self._api_key),
                    headers={"Accept": "application/json"},
                )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ShipShowConnectionError("Could not connect to ShipShow") from err

        try:
            payload = await response.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError) as err:
            raise ShipShowError("ShipShow returned an invalid response") from err

        if response.status in {401, 403}:
            raise ShipShowAuthError("ShipShow rejected the API key")

        if response.status >= 400:
            message = payload.get("error") if isinstance(payload, dict) else None
            raise ShipShowError(message or f"ShipShow returned HTTP {response.status}")

        if isinstance(payload, dict) and payload.get("error"):
            error = str(payload["error"])
            if "api key" in error.lower() or "subscription" in error.lower():
                raise ShipShowAuthError(error)
            raise ShipShowError(error)

        if not isinstance(payload, dict):
            raise ShipShowError("ShipShow returned an unexpected response")

        return ShipShowPage(
            trackings=list(payload.get("trackings") or []),
            categories=list(payload.get("categories") or []),
            has_more_data=bool(payload.get("hasmoredata")),
            raw=payload,
        )

    async def async_get_all_trackings(
        self,
        query: ShipShowQuery,
        max_pages: int,
    ) -> ShipShowPage:
        """Fetch all available pages up to max_pages."""
        all_trackings: list[dict[str, Any]] = []
        categories: list[dict[str, Any]] = []
        has_more_data = False
        raw: dict[str, Any] = {}
        limit = max(1, min(50, query.limit))

        for page_number in range(max(1, max_pages)):
            page = await self.async_get_trackings(
                ShipShowQuery(
                    category_id=query.category_id,
                    search=query.search,
                    statusfilter=query.statusfilter,
                    limit=limit,
                    offset=query.offset + page_number * limit,
                    sortby=query.sortby,
                    sortorder=query.sortorder,
                )
            )
            raw = page.raw
            all_trackings.extend(page.trackings)
            if page.categories:
                categories = page.categories
            has_more_data = page.has_more_data
            if not page.has_more_data:
                break

        return ShipShowPage(
            trackings=all_trackings,
            categories=categories,
            has_more_data=has_more_data,
            raw=raw,
        )
