# Planika Fireplace — Home Assistant Custom Integration

Control your [Planika](https://planikafires.com/) bioethanol fireplace from Home Assistant.

Ported from the [homebridge-planika](https://github.com/bkovacic/homebridge-planika) plugin by bkovacic.

## Features

- **Turn on / off** the fireplace
- **Flame level control** (1–5) via the brightness slider
- Polled state updates every 30 seconds
- Config flow: set up entirely through the HA UI (Settings → Integrations)

## Installation

### Manual

1. Copy the `custom_components/planika` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Planika Fireplace**.
3. Enter the local IP address of your fireplace (e.g. `192.168.1.100`).
4. Optionally change the port (default `3000`) and the display name.

The fireplace will appear as a **Light** entity with brightness control.

## How it works

The fireplace exposes a TCP socket on port 3000.
The integration sends plain-text commands and reads JSON responses:

| Command    | Effect                                        |
|------------|-----------------------------------------------|
| `STATUS`   | Returns `{"status":"on/off","flame":1-5}`     |
| `ON`       | Ignites the fireplace                         |
| `OFF`      | Extinguishes the fireplace                    |
| `FLAME=N`  | Sets flame level (1 = low, 5 = high)          |

Brightness in Home Assistant (0–255) is linearly mapped to flame levels 1–5.

## Troubleshooting

- Make sure your fireplace and HA instance are on the same network.
- Test connectivity: `nc -zv <ip> 3000`
- Check HA logs (`Settings → System → Logs`) and filter for `planika`.

## License

Apache 2.0 — same as the original homebridge-planika plugin.
