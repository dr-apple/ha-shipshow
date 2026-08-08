"""ShipShow integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ShipShowClient
from .const import CONF_API_BASE_URL, DEFAULT_API_BASE_URL, DOMAIN, PLATFORMS
from .coordinator import ShipShowDataUpdateCoordinator

type ShipShowConfigEntry = ConfigEntry[ShipShowDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ShipShowConfigEntry) -> bool:
    """Set up ShipShow from a config entry."""
    session = async_get_clientsession(hass)
    client = ShipShowClient(
        session=session,
        api_key=entry.data[CONF_API_KEY],
        api_base_url=entry.data.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
    )
    coordinator = ShipShowDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    await _async_migrate_registry_entries(hass, entry)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ShipShowConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_migrate_registry_entries(hass: HomeAssistant, entry: ShipShowConfigEntry) -> None:
    """Scope legacy package entities and devices to their config entry."""
    unique_id_prefix = f"{entry.entry_id}_"

    @callback
    def migrate_entity(entity_entry: er.RegistryEntry) -> dict[str, str] | None:
        if entity_entry.unique_id.startswith(unique_id_prefix):
            return None
        return {"new_unique_id": f"{unique_id_prefix}{entity_entry.unique_id}"}

    await er.async_migrate_entries(hass, entry.entry_id, migrate_entity)

    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        identifiers = {
            (domain, f"{unique_id_prefix}{identifier}")
            if domain == DOMAIN
            and identifier != entry.entry_id
            and not identifier.startswith(unique_id_prefix)
            else (domain, identifier)
            for domain, identifier in device_entry.identifiers
        }
        if identifiers != device_entry.identifiers:
            device_registry.async_update_device(
                device_entry.id,
                new_identifiers=identifiers,
            )


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, "refresh"):
        return

    async def async_refresh(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if coordinator := getattr(entry, "runtime_data", None):
                await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "refresh", async_refresh)
