"""Async client for a Planika fireplace.

Holds one persistent TCP connection, polls the status every few seconds,
and reconnects by itself when the module drops off the network (it does that
for minutes at a time). This file deliberately has no Home Assistant imports
so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from .const import (
    CMD_BURNER2_OFF,
    CMD_BURNER2_ON,
    CMD_EXTINGUISH,
    CMD_IGNITE,
    CMD_LEVEL,
    CMD_POLL_STATIC,
    CMD_POLL_STATUS,
    CMD_PREFIX,
    CONNECT_TIMEOUT,
    FLAG_BURNER2,
    FLAG_IGNITING,
    FLAG_LIT,
    PENDING_HOLD,
    POLL_INTERVAL,
    PROBE_TIMEOUT,
    RECONNECT_DELAY,
    RECONNECT_MAX_DELAY,
    STALE_AFTER,
    STATUS_PREFIX,
    FireState,
)

_LOGGER = logging.getLogger(__name__)

STX = b"\x02"
ETX = b"\x03"

_NETWORK_ERRORS = (
    OSError,
    TimeoutError,
    asyncio.IncompleteReadError,
    asyncio.LimitOverrunError,
)


class PlanikaConnectionError(Exception):
    """The fireplace cannot be reached right now."""


@dataclass(frozen=True)
class PlanikaStatus:
    """One decoded status frame."""

    state: FireState
    level: int  # 0-255
    second_burner: bool


def build_frame(code: str) -> bytes:
    """Wrap a command code in the wire framing."""
    return STX + (CMD_PREFIX + code).encode("ascii") + ETX


def parse_status(frame: bytes) -> PlanikaStatus | None:
    """Decode a status frame, or return None if it is not one."""
    text = frame.strip(STX + ETX).decode("ascii", errors="ignore")
    if not text.startswith(STATUS_PREFIX) or len(text) < 20:
        return None
    try:
        level = int(text[14:16], 16)
        flags = int(text[16:20], 16)
    except ValueError:
        return None
    if flags & FLAG_LIT:
        state = FireState.LIT
    elif flags & FLAG_IGNITING:
        state = FireState.IGNITING
    else:
        state = FireState.OFF
    return PlanikaStatus(state, level, bool(flags & FLAG_BURNER2))


class PlanikaClient:
    """Persistent connection to one fireplace."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._status: PlanikaStatus | None = None
        self._available = False
        self._last_status = 0.0
        self._pending: tuple[FireState, float] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._task: asyncio.Task | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------ state

    @property
    def available(self) -> bool:
        return self._available

    @property
    def status(self) -> PlanikaStatus | None:
        return self._status

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for state changes; returns an unsubscribe."""
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    def _set_status(self, status: PlanikaStatus) -> None:
        changed = status != self._status or not self._available
        self._status = status
        self._available = True
        self._last_status = time.monotonic()
        if changed:
            self._notify()

    def _set_unavailable(self) -> None:
        if self._available:
            self._available = False
            self._notify()

    def _apply_reported(self, new: PlanikaStatus) -> None:
        """Take a status the device reported.

        After we sent ignite/extinguish we show the expected state for a few
        seconds, so the UI doesn't flicker back while the device catches up.
        """
        if self._pending is not None:
            target, deadline = self._pending
            reached = new.state is target or (
                target is FireState.IGNITING and new.state is FireState.LIT
            )
            if reached or time.monotonic() > deadline:
                self._pending = None
            else:
                new = replace(new, state=target)
        self._set_status(new)

    # -------------------------------------------------------------- lifecycle

    async def async_start(self) -> None:
        """Start the background connection task."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def async_stop(self) -> None:
        """Stop the background task and close the connection."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._available = False

    @staticmethod
    async def async_probe(host: str, port: int) -> bool:
        """True if a fireplace answers a status poll (used by the config flow)."""
        try:
            async with asyncio.timeout(PROBE_TIMEOUT):
                reader, writer = await asyncio.open_connection(host, port)
                try:
                    writer.write(build_frame(CMD_POLL_STATUS))
                    await writer.drain()
                    while True:
                        frame = await reader.readuntil(ETX)
                        if parse_status(frame) is not None:
                            return True
                finally:
                    writer.close()
        except _NETWORK_ERRORS:
            return False

    # ------------------------------------------------------------ connection

    async def _run(self) -> None:
        delay = RECONNECT_DELAY
        while True:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=CONNECT_TIMEOUT,
                )
            except _NETWORK_ERRORS as err:
                _LOGGER.debug("Planika: cannot connect to %s: %r", self._host, err)
                self._set_unavailable()
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
                continue

            delay = RECONNECT_DELAY
            try:
                await self._session(reader, writer)
            except (*_NETWORK_ERRORS, PlanikaConnectionError) as err:
                _LOGGER.debug("Planika: connection lost: %r", err)
            finally:
                writer.close()
                self._writer = None
                self._set_unavailable()
            await asyncio.sleep(RECONNECT_DELAY)

    async def _session(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writer = writer
        self._last_status = time.monotonic()
        poller = asyncio.create_task(self._poll_loop())
        try:
            while True:
                try:
                    async with asyncio.timeout(STALE_AFTER):
                        frame = await reader.readuntil(ETX)
                except TimeoutError as err:
                    raise PlanikaConnectionError("no data from fireplace") from err
                status = parse_status(frame)
                if status is not None:
                    self._apply_reported(status)
                if time.monotonic() - self._last_status > STALE_AFTER:
                    raise PlanikaConnectionError("no status from fireplace")
        finally:
            poller.cancel()

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._write(CMD_POLL_STATUS)
                await self._write(CMD_POLL_STATIC)
            except (*_NETWORK_ERRORS, PlanikaConnectionError):
                return
            await asyncio.sleep(POLL_INTERVAL)

    async def _write(self, code: str) -> None:
        writer = self._writer
        if writer is None:
            raise PlanikaConnectionError("not connected to the fireplace")
        async with self._write_lock:
            writer.write(build_frame(code))
            await writer.drain()

    async def _command(self, code: str) -> None:
        try:
            await self._write(code)
            await self._write(CMD_POLL_STATUS)
        except _NETWORK_ERRORS as err:
            raise PlanikaConnectionError(f"command failed: {err}") from err

    # -------------------------------------------------------------- commands

    def _expect(self, state: FireState) -> None:
        self._pending = (state, time.monotonic() + PENDING_HOLD)
        if self._status is not None:
            self._status = replace(self._status, state=state)
            self._notify()

    async def async_ignite(self) -> None:
        await self._command(CMD_IGNITE)
        self._expect(FireState.IGNITING)

    async def async_extinguish(self) -> None:
        await self._command(CMD_EXTINGUISH)
        self._expect(FireState.OFF)

    async def async_set_level(self, level: int) -> None:
        level = max(0, min(255, int(level)))
        await self._command(f"{CMD_LEVEL}{level:02X}")

    async def async_set_second_burner(self, on: bool) -> None:
        await self._command(CMD_BURNER2_ON if on else CMD_BURNER2_OFF)
