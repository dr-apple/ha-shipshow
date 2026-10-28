"""Delivery stop and arrival helpers shared by the coordinator and the entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


def stops_field(tracking: dict[str, Any] | None) -> tuple[bool, int | None]:
    """Return whether ShipShow sent `deliverystopsremaining` and its value.

    The field is an integer while an Amazon Logistics package is out for
    delivery and null for other carriers and delivered packages. When the key is
    present, it is authoritative and the text heuristics must not be used.
    """
    if not tracking or "deliverystopsremaining" not in tracking:
        return False, None
    value = tracking["deliverystopsremaining"]
    if isinstance(value, int) and not isinstance(value, bool):
        return True, value
    return True, None


def _short_time(value: Any) -> str | None:
    """Return HH:MM from an HH:MM:SS string."""
    if not value:
        return None
    text = str(value)
    return text[:5] if len(text) >= 5 else None


def _parse_eta(value: Any) -> datetime | None:
    """Parse `derivedeta` (ISO 8601, UTC) into a local datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return dt_util.as_local(parsed)


def tracking_arrival(tracking: dict[str, Any] | None) -> dict[str, Any]:
    """Return the expected arrival as shown in the ShipShow app.

    `derivedeta` wins when set. Otherwise a window runs from
    `earliestdeliverytime` to `scheduleddeliverytime`, and a lone
    `scheduleddeliverytime` is a single expected time.
    """
    tracking = tracking or {}
    window_start = _short_time(tracking.get("earliestdeliverytime"))
    window_end = _short_time(tracking.get("scheduleddeliverytime"))
    eta = _parse_eta(tracking.get("derivedeta"))

    if eta is not None:
        text = f"ca. {eta:%H:%M}"
    elif window_start and window_end:
        text = f"{window_start}–{window_end}"
    else:
        text = window_end

    return {
        "text": text,
        "von": window_start,
        "bis": window_end,
        "geschaetzt": eta.isoformat() if eta else None,
    }
