"""Shared base entities for the Planika Fireplace integration."""

from __future__ import annotations

from collections.abc import Awaitable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .client import PlanikaClient, PlanikaConnectionError, PlanikaStatus
from .const import DOMAIN, FireState


class PlanikaEntity(Entity):
    """Entity that follows the client's push updates."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client: PlanikaClient, entry: ConfigEntry, key: str) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Planika",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._client.available and self._client.status is not None

    @property
    def status(self) -> PlanikaStatus:
        status = self._client.status
        assert status is not None  # guaranteed whenever `available` is True
        return status

    async def _async_run(self, command: Awaitable[None]) -> None:
        try:
            await command
        except PlanikaConnectionError as err:
            raise HomeAssistantError(f"Planika fireplace: {err}") from err


class PlanikaControlEntity(PlanikaEntity):
    """A control that only works once the fireplace has confirmed it is lit.

    While the fireplace is off or still igniting these show as unavailable.
    """

    @property
    def available(self) -> bool:
        return super().available and self.status.state is FireState.LIT
