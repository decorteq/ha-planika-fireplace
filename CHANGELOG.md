# Changelog

## 3.0.1

* Existing 1.x config entries are migrated automatically (the port is corrected from 3000 to 2000), instead of failing to load.
* Setup error text no longer tells you to close the Planika app; the app and Home Assistant can be connected at the same time.
* CI workflows can be started manually.

## 3.0.0

Complete rewrite based on the real protocol of the module (see docs/PROTOCOL.md).

* Correct transport: TCP port **2000**, ASCII frames `STX 30303030 <code> ETX`. Versions 1.x assumed port 3000 and a plain-text/JSON protocol, which the hardware does not speak.
* One persistent connection with background polling (`8003`, every 2 s) and automatic reconnect. Fresh connections are often ignored by the module, so the connection is kept open.
* Real device state: `off` / `igniting` / `lit`, decoded from the status frame. The switch shows the ignition phase; the status sensor distinguishes `igniting` from `lit`.
* Flame control through the level command `8016LL` (0-100 % number entity) plus Standby / Low / High presets.
* Flame controls are unavailable unless the fireplace is confirmed lit.
* Optional second-burner switch (disabled by default).
* Config flow validates the connection with a real status poll; options flow to change address.
* Light platform removed.

## 1.0.1

Initial release (assumed port 3000 and a text protocol; did not work with real hardware).
