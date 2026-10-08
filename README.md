# Planika Fireplace for Home Assistant

Local control of a [Planika](https://planikafires.com/) fireplace that has the Wi-Fi module used by the **Planika Gas Control** app. No cloud, no account: Home Assistant talks directly to the module over TCP.

> Unofficial. Not affiliated with or endorsed by Planika. The protocol was reverse-engineered from the official app's network traffic and verified on one real unit. See [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Entities

| Entity | Type | What it does |
|---|---|---|
| **Fireplace** | switch | Ignite / extinguish. Reads *on* from the moment ignition starts. |
| **Status** | sensor (enum) | `off`, `igniting`, `lit`. Reported by the fireplace itself, not guessed. Ignition takes about 20 s before `lit` is confirmed. |
| **Flame preset** | select | `standby`, `low`, `high`. *Standby* is a small waiting flame, not off. |
| **Flame level** | number | Exact flame level, 0-100 %. |
| **Second burner** | switch | Disabled by default (no visible effect was observed on the development unit). Enable it in the entity settings if your unit reacts to it. |

Flame preset, flame level and second burner are **unavailable unless the fireplace is confirmed `lit`**. They are greyed out while the fireplace is off or still igniting, so a command can never be sent into a fireplace that is not burning.

## Installation

### HACS (custom repository)

1. HACS -> three-dot menu -> *Custom repositories* -> add `https://github.com/decorteq/ha-planika-fireplace`, category *Integration*.
2. Install **Planika Fireplace** and restart Home Assistant.

### Manual

Copy `custom_components/planika` into your Home Assistant `config/custom_components/` directory and restart.

## Setup

1. Give the fireplace a **fixed IP address** (DHCP reservation in your router). The module can also drop off Wi-Fi for minutes at a time; the integration reconnects on its own.
2. *Settings -> Devices & services -> Add integration -> Planika Fireplace*.
3. Enter the IP address. The port is **2000**.

If the address changes later, use the integration's **Configure** button. You do not need to delete and re-add it.

## Dashboard

[docs/dashboard-example.yaml](docs/dashboard-example.yaml) contains a ready-made view (needs the [button-card](https://github.com/custom-cards/button-card) HACS frontend card):

* a main button that **pulses orange while igniting** and turns solid red once the fireplace confirms `lit`;
* Standby / Low / High as a three-segment control with the active mode highlighted;
* the flame level slider.

Entity IDs follow the name you gave the fireplace (default `Planika Fireplace` -> `switch.planika_fireplace`, `sensor.planika_fireplace_status`, `select.planika_fireplace_flame_preset`, `number.planika_fireplace_flame_level`).

## Safety

Turning the switch on **lights a real flame**. Do not automate ignition unattended unless you have considered the consequences. The integration only sends the same commands the official app sends.

## Known limits

* The Planika app and Home Assistant can be connected at the same time; a change made in one shows up in the other.
* The flame follows a level change after roughly 5-10 s.
* Only one unit has been tested. Behaviour on other models is unknown. Reports are welcome in the issue tracker.
* Meaning of a few status bits and of three app commands is still unknown (see [docs/PROTOCOL.md](docs/PROTOCOL.md#9-open-questions)).

## Documentation

* [docs/PROTOCOL.md](docs/PROTOCOL.md) - how the protocol works and how it was worked out (frame format, commands, status decoding, behaviour, test log).
* [docs/dashboard-example.yaml](docs/dashboard-example.yaml) - dashboard view.
* [CHANGELOG.md](CHANGELOG.md)
* `dev/` - offline tests that run the client (and, with Home Assistant installed, the entities) against a simulated fireplace: `python3 dev/test_client.py`.

## License

Apache 2.0, see [LICENSE](LICENSE).
