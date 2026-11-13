"""Tests for the "keep delivered packages (days)" option."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shipshow.api import ShipShowClient, ShipShowPage
from custom_components.shipshow.const import (
    CONF_API_BASE_URL,
    CONF_DELIVERED_KEEP_DAYS,
    CONF_INCLUDE_DELIVERED,
    DOMAIN,
)


def _entry(keep_days: int, include_delivered: bool = False) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="ShipShow",
        unique_id="secret-key",
        data={
            CONF_API_KEY: "secret-key",
            CONF_API_BASE_URL: "https://api.shipshow.net/external/",
        },
        options={
            CONF_DELIVERED_KEEP_DAYS: keep_days,
            CONF_INCLUDE_DELIVERED: include_delivered,
        },
    )


def _tracking(tracking_id: str, status: str = "transit") -> dict[str, Any]:
    return {
        "tracking_id": tracking_id,
        "trackingnumber": f"number-{tracking_id}",
        "title": f"Package {tracking_id}",
        "last_status": status,
        "carrier": {"name": "Carrier"},
    }


def _package_devices(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    """Return the tracking ids that still have a device (account device excluded)."""
    prefix = f"{entry.entry_id}_"
    return {
        identifier[len(prefix) :]
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        for domain, identifier in device.identifiers
        if domain == DOMAIN and identifier.startswith(prefix)
    }


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, fetch: AsyncMock) -> None:
    entry.add_to_hass(hass)
    with patch.object(ShipShowClient, "async_get_all_trackings", new=fetch):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry, fetch: AsyncMock) -> None:
    with patch.object(ShipShowClient, "async_get_all_trackings", new=fetch):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()


async def test_delivered_package_is_kept_for_n_days_then_removed(
    hass: HomeAssistant, enable_custom_integrations: None, freezer
) -> None:
    entry = _entry(keep_days=2)
    fetch = AsyncMock(return_value=ShipShowPage(trackings=[_tracking("t1")]))
    await _setup(hass, entry, fetch)
    assert _package_devices(hass, entry) == {"t1"}

    # Delivered now: stays visible and available for the keep time.
    fetch.return_value = ShipShowPage(trackings=[_tracking("t1", "delivered")])
    await _refresh(hass, entry, fetch)
    assert "t1" in entry.runtime_data.data.trackings
    assert _package_devices(hass, entry) == {"t1"}

    freezer.tick(timedelta(days=1))
    await _refresh(hass, entry, fetch)
    assert _package_devices(hass, entry) == {"t1"}

    freezer.tick(timedelta(days=1, hours=1))
    await _refresh(hass, entry, fetch)
    assert "t1" not in entry.runtime_data.data.trackings
    assert _package_devices(hass, entry) == set()
    # The global ShipShow device must survive.
    remaining = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert {(DOMAIN, entry.entry_id)} in [device.identifiers for device in remaining]


async def test_untracked_delivered_history_is_not_added(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    entry = _entry(keep_days=2)
    fetch = AsyncMock(
        return_value=ShipShowPage(trackings=[_tracking("old", "delivered"), _tracking("t2")])
    )
    await _setup(hass, entry, fetch)
    assert set(entry.runtime_data.data.trackings) == {"t2"}
    assert _package_devices(hass, entry) == {"t2"}


async def test_option_off_never_removes_devices(
    hass: HomeAssistant, enable_custom_integrations: None, freezer
) -> None:
    entry = _entry(keep_days=0)
    fetch = AsyncMock(return_value=ShipShowPage(trackings=[_tracking("t1")]))
    await _setup(hass, entry, fetch)

    fetch.return_value = ShipShowPage(trackings=[_tracking("t1", "delivered")])
    freezer.tick(timedelta(days=30))
    await _refresh(hass, entry, fetch)
    assert "t1" not in entry.runtime_data.data.trackings  # include_delivered is off
    assert _package_devices(hass, entry) == {"t1"}


async def test_vanished_package_is_removed_after_n_days(
    hass: HomeAssistant, enable_custom_integrations: None, freezer
) -> None:
    entry = _entry(keep_days=3)
    fetch = AsyncMock(return_value=ShipShowPage(trackings=[_tracking("t1")]))
    await _setup(hass, entry, fetch)

    fetch.return_value = ShipShowPage(trackings=[])
    await _refresh(hass, entry, fetch)
    assert _package_devices(hass, entry) == {"t1"}

    # A cut-off result list is no proof that the package is gone.
    fetch.return_value = ShipShowPage(trackings=[], has_more_data=True)
    freezer.tick(timedelta(days=4))
    await _refresh(hass, entry, fetch)
    assert _package_devices(hass, entry) == {"t1"}

    fetch.return_value = ShipShowPage(trackings=[])
    await _refresh(hass, entry, fetch)
    assert _package_devices(hass, entry) == set()
