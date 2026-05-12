"""Light platform for Planika Fireplace.

The fireplace is exposed as a Light entity in Home Assistant:
  - On/Off  → ignite / extinguish
  - Brightness (0-255) → flame level 1-5

This mirrors the Homebridge plugin behaviour where the fireplace was
represented as a dimmable lightbulb so that flame height could be
controlled through the brightness slider.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import PlanikaClient, PlanikaCommunicationError
from .const import DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

MIN_FLAME = 1
MAX_FLAME = 5


def _brightness_to_flame(brightness: int) -> int:
    """Convert HA brightness (1-255) to Planika flame level (1-5)."""
    level = round(1 + (brightness - 1) * (MAX_FLAME - MIN_FLAME) / 254)
    return max(MIN_FLAME, min(MAX_FLAME, level))


def _flame_to_brightness(flame: int) -> int:
    """Convert Planika flame level (1-5) to HA brightness (1-255)."""
    brightness = round(1 + (flame - 1) * 254 / (MAX_FLAME - MIN_FLAME))
    return max(1, min(255, brightness))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Planika light entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client: PlanikaClient = data["client"]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    async_add_entities([PlanikaFireplace(coordinator, client, entry, name)])


class PlanikaFireplace(CoordinatorEntity, LightEntity):
    """Representation of a Planika fireplace as a dimmable Light."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_icon = "mdi:fireplace"

    def __init__(self, coordinator, client: PlanikaClient, entry: ConfigEntry, name: str) -> None:
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = f"planika_{entry.data['host']}"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        status = self.coordinator.data.get("status", "off")
        return status.lower() == "on"

    @property
    def brightness(self) -> int | None:
        if not self.coordinator.data:
            return None
        flame = self.coordinator.data.get("flame", MIN_FLAME)
        try:
            return _flame_to_brightness(int(flame))
        except (ValueError, TypeError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            if not self.is_on:
                await self._client.turn_on()
            if ATTR_BRIGHTNESS in kwargs:
                flame = _brightness_to_flame(kwargs[ATTR_BRIGHTNESS])
                await self._client.set_flame_level(flame)
        except PlanikaCommunicationError as exc:
            _LOGGER.error("Failed to turn on Planika fireplace: %s", exc)
        finally:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._client.turn_off()
        except PlanikaCommunicationError as exc:
            _LOGGER.error("Failed to turn off Planika fireplace: %s", exc)
        finally:
            await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.data["host"])},
            "name": self._attr_name,
            "manufacturer": "Planika",
            "model": "BEV Fireplace",
        }
