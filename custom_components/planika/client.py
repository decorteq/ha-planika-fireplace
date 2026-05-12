"""Planika fireplace TCP communication client.

Protocol reverse-engineered from homebridge-planika (bkovacic).
The fireplace listens on TCP port 3000 and accepts plain-text commands.

Known commands (as used in the Homebridge plugin):
  STATUS    – request current state, returns JSON-like string
  ON        – ignite / turn fireplace on
  OFF       – extinguish / turn fireplace off
  FLAME=N   – set flame level (1–5)

Responses are newline-terminated strings, e.g.:
  {"status":"on","flame":3}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

PLANIKA_PORT = 3000
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 5


class PlanikaCommunicationError(Exception):
    """Raised when the TCP connection to the fireplace fails."""


class PlanikaClient:
    """Async TCP client for Planika fireplaces."""

    def __init__(self, host: str, port: int = PLANIKA_PORT) -> None:
        self._host = host
        self._port = port

    async def _send_command(self, command: str) -> str:
        """Open a TCP connection, send *command*, return the response line."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=CONNECT_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise PlanikaCommunicationError(
                f"Cannot connect to Planika at {self._host}:{self._port}: {exc}"
            ) from exc

        try:
            writer.write(f"{command}\n".encode())
            await writer.drain()

            raw = await asyncio.wait_for(reader.readline(), timeout=READ_TIMEOUT)
            return raw.decode().strip()
        except asyncio.TimeoutError as exc:
            raise PlanikaCommunicationError(
                f"Timeout waiting for response from {self._host}"
            ) from exc
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _parse_state(self, raw: str) -> dict[str, Any]:
        """Parse the JSON response from the fireplace."""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            _LOGGER.warning("Unexpected response from Planika: %r", raw)
            return {}

    async def get_state(self) -> dict[str, Any]:
        """Return current fireplace state as a dict."""
        raw = await self._send_command("STATUS")
        return self._parse_state(raw)

    async def turn_on(self) -> None:
        """Turn the fireplace on."""
        await self._send_command("ON")

    async def turn_off(self) -> None:
        """Turn the fireplace off."""
        await self._send_command("OFF")

    async def set_flame_level(self, level: int) -> None:
        """Set flame level (1 = minimum, 5 = maximum)."""
        level = max(1, min(5, level))
        await self._send_command(f"FLAME={level}")

    async def async_verify_connection(self) -> bool:
        """Return True if the fireplace is reachable."""
        try:
            await self.get_state()
            return True
        except PlanikaCommunicationError:
            return False