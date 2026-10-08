"""Sensor platform: what the fireplace reports about itself."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import PlanikaClient
from .const import FireState
from .entity import PlanikaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[PlanikaClient],
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PlanikaStatusSensor(entry.runtime_data, entry)])


class PlanikaStatusSensor(PlanikaEntity, SensorEntity):
    """off / igniting / lit, straight from the device's status frame."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [state.value for state in FireState]

    def __init__(self, client: PlanikaClient, entry: ConfigEntry) -> None:
        super().__init__(client, entry, "status")

    @property
    def native_value(self) -> str:
        return self.status.state.value

    @property
    def icon(self) -> str:
        state = self.status.state if self.available else FireState.OFF
        return {
            FireState.OFF: "mdi:fire-off",
            FireState.IGNITING: "mdi:fire-alert",
            FireState.LIT: "mdi:fire",
        }[state]
