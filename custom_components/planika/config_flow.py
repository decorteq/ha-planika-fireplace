"""Config flow for Planika Fireplace integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .client import PlanikaClient, PlanikaCommunicationError
from .const import DEFAULT_NAME, DEFAULT_PORT, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


async def _validate_input(hass: HomeAssistant, data: dict) -> dict[str, str]:
    """Validate that the fireplace is reachable."""
    client = PlanikaClient(data[CONF_HOST], data[CONF_PORT])
    if not await client.async_verify_connection():
        raise PlanikaCommunicationError("Cannot reach fireplace")
    return {"title": data.get(CONF_NAME, DEFAULT_NAME)}


class PlanikaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow for Planika."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_input(self.hass, user_input)
            except PlanikaCommunicationError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
