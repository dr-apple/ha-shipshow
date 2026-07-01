"""ShipShow integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, ServiceCall
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

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ShipShowConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ShipShowConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, "refresh"):
        return

    async def async_refresh(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if coordinator := getattr(entry, "runtime_data", None):
                await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "refresh", async_refresh)
