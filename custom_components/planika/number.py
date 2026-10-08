"""Number platform: exact flame level as a percentage."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import PlanikaClient
from .entity import PlanikaControlEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[PlanikaClient],
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PlanikaLevelNumber(entry.runtime_data, entry)])


class PlanikaLevelNumber(PlanikaControlEntity, NumberEntity):
    """0-100 %, mapped onto the device's 00-FF level byte."""

    _attr_translation_key = "flame_level"
    _attr_icon = "mdi:fire"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, client: PlanikaClient, entry: ConfigEntry) -> None:
        super().__init__(client, entry, "flame_level")

    @property
    def native_value(self) -> float:
        return round(self.status.level * 100 / 255)

    async def async_set_native_value(self, value: float) -> None:
        await self._async_run(self._client.async_set_level(round(value * 255 / 100)))
