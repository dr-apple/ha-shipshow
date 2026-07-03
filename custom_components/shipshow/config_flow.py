"""Config flow for ShipShow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ShipShowAuthError, ShipShowClient, ShipShowError, ShipShowQuery
from .const import (
    CONF_API_BASE_URL,
    CONF_CATEGORY_ID,
    CONF_INCLUDE_DELIVERED,
    CONF_LIMIT,
    CONF_MAX_PAGES,
    CONF_SCAN_INTERVAL,
    CONF_SEARCH,
    CONF_SORT_BY,
    CONF_SORT_ORDER,
    CONF_STATUS_FILTER,
    DEFAULT_API_BASE_URL,
    DEFAULT_LIMIT,
    DEFAULT_MAX_PAGES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_ORDER,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    SORT_BY_OPTIONS,
    SORT_ORDER_OPTIONS,
    STATUS_OPTIONS,
)


class ShipShowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a ShipShow config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            api_base_url = user_input.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL).strip()
            try:
                await self._async_validate(api_key, api_base_url)
            except ShipShowAuthError:
                errors["base"] = "invalid_auth"
            except ShipShowError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(api_key)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="ShipShow",
                    data={
                        CONF_API_KEY: api_key,
                        CONF_API_BASE_URL: api_base_url,
                    },
                    options=_default_options(),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Optional(CONF_API_BASE_URL, default=DEFAULT_API_BASE_URL): str,
                }
            ),
            errors=errors,
        )

    async def _async_validate(self, api_key: str, api_base_url: str) -> None:
        """Validate credentials by fetching one tracking page."""
        client = ShipShowClient(
            async_get_clientsession(self.hass),
            api_key=api_key,
            api_base_url=api_base_url,
        )
        await client.async_get_trackings(ShipShowQuery(limit=1))

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> ShipShowOptionsFlow:
        """Return options flow."""
        return ShipShowOptionsFlow(config_entry)


class ShipShowOptionsFlow(config_entries.OptionsFlow):
    """Handle ShipShow options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {**_default_options(), **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CATEGORY_ID,
                        default=options.get(CONF_CATEGORY_ID, ""),
                    ): str,
                    vol.Optional(CONF_SEARCH, default=options.get(CONF_SEARCH, "")): str,
                    vol.Optional(
                        CONF_STATUS_FILTER,
                        default=options.get(CONF_STATUS_FILTER, ""),
                    ): vol.In(["", *STATUS_OPTIONS]),
                    vol.Required(
                        CONF_LIMIT,
                        default=options.get(CONF_LIMIT, DEFAULT_LIMIT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
                    vol.Required(
                        CONF_MAX_PAGES,
                        default=options.get(CONF_MAX_PAGES, DEFAULT_MAX_PAGES),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                    vol.Required(
                        CONF_SORT_BY,
                        default=options.get(CONF_SORT_BY, DEFAULT_SORT_BY),
                    ): vol.In(SORT_BY_OPTIONS),
                    vol.Required(
                        CONF_SORT_ORDER,
                        default=options.get(CONF_SORT_ORDER, DEFAULT_SORT_ORDER),
                    ): vol.In(SORT_ORDER_OPTIONS),
                    vol.Required(
                        CONF_INCLUDE_DELIVERED,
                        default=options.get(CONF_INCLUDE_DELIVERED, True),
                    ): bool,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                }
            ),
        )


def _default_options() -> dict[str, Any]:
    """Return default options."""
    return {
        CONF_CATEGORY_ID: "",
        CONF_SEARCH: "",
        CONF_STATUS_FILTER: "",
        CONF_LIMIT: DEFAULT_LIMIT,
        CONF_MAX_PAGES: DEFAULT_MAX_PAGES,
        CONF_SORT_BY: DEFAULT_SORT_BY,
        CONF_SORT_ORDER: DEFAULT_SORT_ORDER,
        CONF_INCLUDE_DELIVERED: True,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    }
