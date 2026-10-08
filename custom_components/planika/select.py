"""Select platform: Standby / Low / High presets."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import PlanikaClient
from .const import PRESET_LEVELS, level_to_preset
from .entity import PlanikaControlEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[PlanikaClient],
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PlanikaPresetSelect(entry.runtime_data, entry)])


class PlanikaPresetSelect(PlanikaControlEntity, SelectEntity):
    """Standby is a small waiting flame, not 'off'. Only usable while lit."""

    _attr_translation_key = "flame_preset"
    _attr_icon = "mdi:fire-circle"
    _attr_options = list(PRESET_LEVELS)

    def __init__(self, client: PlanikaClient, entry: ConfigEntry) -> None:
        super().__init__(client, entry, "flame_preset")

    @property
    def current_option(self) -> str:
        return level_to_preset(self.status.level)

    async def async_select_option(self, option: str) -> None:
        await self._async_run(self._client.async_set_level(PRESET_LEVELS[option]))
