"""Home Assistant 2026.8 compatibility tests."""

from collections import Counter
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shipshow.const import CONF_API_BASE_URL, DOMAIN
from custom_components.shipshow.coordinator import (
    ShipShowData,
    ShipShowDataUpdateCoordinator,
)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="ShipShow",
        unique_id="secret-key",
        data={
            CONF_API_KEY: "secret-key",
            CONF_API_BASE_URL: "https://api.shipshow.net/external/",
        },
    )


def _data() -> ShipShowData:
    return ShipShowData(
        trackings={
            "tracking-1": {
                "tracking_id": "tracking-1",
                "trackingnumber": "123456789",
                "title": "Test package",
                "last_status": "transit",
                "scheduleddeliverydate": "2026-08-10",
                "carrier": {"name": "Carrier"},
            }
        },
        categories={},
        status_counts=Counter({"transit": 1}),
        has_more_data=False,
    )


async def test_setup_scopes_package_entities_and_devices_to_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Package registry IDs are safe when multiple accounts contain one shipment."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch.object(
        ShipShowDataUpdateCoordinator,
        "_async_update_data",
        new=AsyncMock(return_value=_data()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 17
    assert all(entity.unique_id.startswith(f"{entry.entry_id}_") for entity in entities)

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 2
    assert all(device.config_entry_id == entry.entry_id for device in devices)
    assert (DOMAIN, f"{entry.entry_id}_tracking-1") in {
        identifier for device in devices for identifier in device.identifiers
    }


async def test_legacy_registry_ids_are_migrated_without_entity_id_change(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """The 2026.8 migration preserves user-facing entity IDs."""
    entry = _entry()
    entry.add_to_hass(hass)
    entity_registry = er.async_get(hass)
    legacy_entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "tracking-1_status",
        config_entry=entry,
        suggested_object_id="shipshow_test_status",
    )
    device_registry = dr.async_get(hass)
    legacy_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "tracking-1")},
        name="Test package",
    )

    with patch.object(
        ShipShowDataUpdateCoordinator,
        "_async_update_data",
        new=AsyncMock(return_value=_data()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    migrated_entity = entity_registry.async_get(legacy_entity.entity_id)
    assert migrated_entity is not None
    assert migrated_entity.entity_id == legacy_entity.entity_id
    assert migrated_entity.unique_id == f"{entry.entry_id}_tracking-1_status"

    migrated_device = device_registry.async_get(legacy_device.id)
    assert migrated_device is not None
    assert migrated_device.identifiers == {(DOMAIN, f"{entry.entry_id}_tracking-1")}
