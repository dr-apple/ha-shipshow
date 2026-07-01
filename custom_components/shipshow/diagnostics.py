"""Diagnostics for ShipShow."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import ShipShowConfigEntry

TO_REDACT = {"api_key", "apikey"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ShipShowConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": _redact(entry.data),
            "options": _redact(entry.options),
        },
        "data": {
            "tracking_count": len(coordinator.data.trackings),
            "category_count": len(coordinator.data.categories),
            "status_counts": dict(coordinator.data.status_counts),
            "has_more_data": coordinator.data.has_more_data,
        },
    }


def _redact(value: Any) -> Any:
    """Redact secrets recursively."""
    if isinstance(value, dict):
        return {
            key: "**REDACTED**" if key in TO_REDACT else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
