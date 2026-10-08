"""Config and options flow for the Planika Fireplace integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .client import PlanikaClient
from .const import CONF_HOST, CONF_NAME, CONF_PORT, DEFAULT_NAME, DEFAULT_PORT, DOMAIN


class PlanikaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a fireplace by IP address."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            # A plain TCP connect is not enough - the module accepts
            # connections while being silent - so ask it for a status.
            if await PlanikaClient.async_probe(host, port):
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_HOST: host, CONF_PORT: port, CONF_NAME: user_input[CONF_NAME]},
                )
            errors["base"] = "cannot_connect"

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PlanikaOptionsFlow:
        return PlanikaOptionsFlow()


class PlanikaOptionsFlow(OptionsFlow):
    """Change the address without removing the entry (e.g. after a new DHCP lease)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.data

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            if await PlanikaClient.async_probe(host, port):
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**current, CONF_HOST: host, CONF_PORT: port},
                )
                return self.async_create_entry(data={})
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current[CONF_HOST]): str,
                vol.Required(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
