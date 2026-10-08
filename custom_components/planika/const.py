"""Constants for the Planika Fireplace integration.

Protocol (reverse-engineered from the official "Planika Gas Control" app and
confirmed with live tests against real hardware, October 2026):

* Plain TCP, port 2000. The device holds one stream; the app polls it about
  once a second.
* Every message is ASCII text framed as ``STX (0x02) + "30303030" + <code> +
  ETX (0x03)``.
* The device answers every message. A poll ``8003`` returns a *status frame*
  that starts with ``030300000003``, followed by:

      chars 12-15  ``5F`` + level byte (two hex digits, 00-FF)
      chars 16-19  a 16-bit flag word:
                     0x0010  igniting
                     0x0080  lit (flame confirmed by the device)
                     0x0008  second burner enabled
                     0x0200  unknown (changes with the time of day / mode)

* Commands:
      801A      ignite
      8010      extinguish
      8016 LL   set the flame level, LL = 00..FF (also settable while off)
      802001/0  second burner on / off (no visible effect on the unit tested)
"""

from __future__ import annotations

from enum import StrEnum

DOMAIN = "planika"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_NAME = "name"

DEFAULT_PORT = 2000
DEFAULT_NAME = "Planika Fireplace"

CMD_PREFIX = "30303030"
CMD_POLL_STATUS = "8003"
CMD_POLL_STATIC = "8001"
CMD_IGNITE = "801A"
CMD_EXTINGUISH = "8010"
CMD_LEVEL = "8016"
CMD_BURNER2_ON = "802001"
CMD_BURNER2_OFF = "802000"

STATUS_PREFIX = "030300000003"
FLAG_BURNER2 = 0x0008
FLAG_IGNITING = 0x0010
FLAG_LIT = 0x0080

CONNECT_TIMEOUT = 5
PROBE_TIMEOUT = 8
POLL_INTERVAL = 2
STALE_AFTER = 8
RECONNECT_DELAY = 5
RECONNECT_MAX_DELAY = 60
PENDING_HOLD = 6


class FireState(StrEnum):
    """What the fireplace reports about itself."""

    OFF = "off"
    IGNITING = "igniting"
    LIT = "lit"


PRESET_STANDBY = "standby"
PRESET_LOW = "low"
PRESET_HIGH = "high"
PRESET_LEVELS = {PRESET_STANDBY: 0x00, PRESET_LOW: 0x8B, PRESET_HIGH: 0xFF}


def level_to_preset(level: int) -> str:
    """Map a reported level byte to the nearest preset name."""
    if level < 0x20:
        return PRESET_STANDBY
    if level >= 0xC0:
        return PRESET_HIGH
    return PRESET_LOW
