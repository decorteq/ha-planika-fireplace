"""The Planika Fireplace integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .client import PlanikaClient
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

type PlanikaConfigEntry = ConfigEntry[PlanikaClient]


async def async_setup_entry(hass: HomeAssistant, entry: PlanikaConfigEntry) -> bool:
    """Open the connection and set up the platforms.

    The connection is made in the background, so entities start out
    unavailable and become available with the first status frame.
    """
    client = PlanikaClient(
        entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)
    )
    await client.async_start()
    entry.runtime_data = client
    entry.async_on_unload(client.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlanikaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_update(hass: HomeAssistant, entry: PlanikaConfigEntry) -> None:
    """Reload when host/port are changed in the options."""
    await hass.config_entries.async_reload(entry.entry_id)
