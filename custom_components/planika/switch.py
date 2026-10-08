"""Switch platform: the main ignite/extinguish switch and the second burner."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import PlanikaClient
from .const import FireState
from .entity import PlanikaControlEntity, PlanikaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[PlanikaClient],
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = entry.runtime_data
    async_add_entities(
        [
            PlanikaFireplaceSwitch(client, entry),
            PlanikaSecondBurnerSwitch(client, entry),
        ]
    )


class PlanikaFireplaceSwitch(PlanikaEntity, SwitchEntity):
    """On from the moment ignition starts; the status sensor says which phase."""

    _attr_name = None  # uses the device name

    def __init__(self, client: PlanikaClient, entry: ConfigEntry) -> None:
        super().__init__(client, entry, "fireplace")

    @property
    def is_on(self) -> bool:
        return self.status.state is not FireState.OFF

    @property
    def icon(self) -> str:
        state = self.status.state if self.available else FireState.OFF
        return {
            FireState.OFF: "mdi:fireplace-off",
            FireState.IGNITING: "mdi:fire-alert",
            FireState.LIT: "mdi:fireplace",
        }[state]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"phase": self.status.state.value, "flame_level": self.status.level}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_run(self._client.async_ignite())

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_run(self._client.async_extinguish())


class PlanikaSecondBurnerSwitch(PlanikaControlEntity, SwitchEntity):
    """Second burner. No visible effect on the unit tested, so off by default."""

    _attr_translation_key = "second_burner"
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:fire-plus"

    def __init__(self, client: PlanikaClient, entry: ConfigEntry) -> None:
        super().__init__(client, entry, "second_burner")

    @property
    def is_on(self) -> bool:
        return self.status.second_burner

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_run(self._client.async_set_second_burner(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_run(self._client.async_set_second_burner(False))
