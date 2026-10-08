# Planika Wi-Fi module: protocol and how it was worked out

Technical reference for the local protocol used by the **Planika Gas Control** app and by this integration. Everything here was derived from network captures of the official app and then confirmed by sending the commands to a real fireplace (October 2026). Nothing was taken from vendor documentation, which does not exist publicly.

Scope and honesty: one fireplace, one firmware. Statements marked **observed** were seen directly on that unit. Statements marked **inferred** are interpretation. Open points are listed in [section 9](#9-open-questions).

Contents

1. [Summary](#1-summary)
2. [Methodology](#2-methodology)
3. [Transport and framing](#3-transport-and-framing)
4. [Commands](#4-commands)
5. [Status frame](#5-status-frame)
6. [Behaviour and timing](#6-behaviour-and-timing)
7. [Flame levels](#7-flame-levels)
8. [How the integration uses the protocol](#8-how-the-integration-uses-the-protocol)
9. [Open questions](#9-open-questions)
10. [Reproducing the analysis](#10-reproducing-the-analysis)
11. [Test log](#11-test-log)

## 1. Summary

* Plain **TCP, port 2000**, no authentication, no encryption.
* Messages are **ASCII text**, framed `STX (0x02)` + `30303030` + *code* + `ETX (0x03)`.
* Commands are short hex-looking codes: `801A` ignite, `8010` extinguish, `8016LL` set flame level (`LL` = `00`..`FF`), `802001` / `802000` second burner on / off, `8003` poll status.
* The reply to the status poll `8003` contains the **real device state** (off / igniting / lit), the **current flame level byte** and a few flag bits. State therefore never has to be guessed.
* The module handles a connection that stays open far better than many short ones, so the integration keeps one connection and polls over it.

## 2. Methodology

The path from "the integration says *can't connect*" to a documented protocol, in the order it happened.

### 2.1 Starting assumption was wrong

The first version of this integration assumed the fireplace speaks a text/JSON protocol (`STATUS`, `ON`, `OFF`, `FLAME=N`) on **port 3000**. That assumption came from a third-party plugin for another platform, not from the hardware. In Home Assistant the config flow failed with "can't connect".

### 2.2 Find the real port

The phone and the fireplace were on the same LAN, so the fireplace's IP address was known (DHCP lease / router client list). A port scan of the device with a phone network-analyzer app found **exactly one open TCP port: 2000**. Port 3000 was closed. (Port 2000 is commonly labelled "cisco-sccp" by scanners; that label is just the IANA registration, not evidence of what the device speaks.)

### 2.3 Probe with a plain client

A raw TCP connection to port 2000 was opened and the old text commands were sent. The module did not answer them. So the port was right but the protocol was different, and the only way to learn it was to watch the real app.

### 2.4 Capture the official app's traffic

The app is Wi-Fi based and talks to the module directly, so the traffic can be captured on the phone side:

1. iPhone connected to a Mac by USB.
2. A **Remote Virtual Interface** was created for the phone (`rvictl -s <device UDID>`), which exposes the phone's traffic as a network interface (`rvi0`) on the Mac. (On recent macOS `rvictl` needs the `com.apple.rpmuxd` daemon to be loaded, otherwise it fails with `bootstrap_look_up ... 1102`.)
3. Wireshark captured on `rvi0` with the display filter `ip.addr == <fireplace> && tcp.port == 2000`.
4. In the app, one action was performed at a time with pauses between actions, so each action could be matched to the packets around it.
5. **Follow TCP stream -> Hex dump** exported each stream.

Capture sessions that carried the most information:

| Session | Actions in the app | What it showed |
|---|---|---|
| A | ignite, wait 10 s, extinguish, wait, ignite, wait, step down through the flame levels | Basic framing; ignite and extinguish codes; the app polls constantly |
| B | ignite, wait, extinguish | `801A` / `8010`; ignition takes a while to show as "on" in the app |
| C | LED on/off (no LED fitted), second burner off/on, flame from High down through the app's level steps to Low and Standby | `802001` / `802000`; the `8016LL` family; level byte values for each app step |
| D | ignite at full, switch to a mid flame, wait, extinguish | Level change while burning |
| E | ignite at 100 %, set 50 % by hand, extinguish | Level command values for round percentages |
| F | ignite, wait until the flame burns, set 9 %, set 5 %, set high, extinguish | Which of the app's steps visibly change the flame |
| G | on, low, high, low, standby, off | Order of commands for the presets |

### 2.5 Read the hex

Every message in every dump had the same shape:

```
02  33 30 33 30 33 30 33 30 38 30 30 33  03
STX  ASCII text "303030308003"             ETX
     = "30303030" (prefix) + "8003" (code)
```

Bytes `33 30 33 30 ...` are ASCII digits, so each byte after STX is a printable character. The text between STX and ETX is therefore `30303030` followed by a command code. Commands that appeared in the captures:

* `8003` and `8001`, repeated about once a second throughout: **polls** (the app keeps its UI in sync this way).
* `801A` exactly when the user pressed *ignite*; `8010` exactly when the user pressed *off*.
* `802001` / `802000` exactly when the second burner was toggled.
* `8016` followed by two hex digits (`8016FF`, `801680`, `80168B`, `801660`) at each level change in the app.
* `8050ff00`, `8050ff01` and `80B0` around some level changes.

### 2.6 Decode the reply

The device sends back a frame after every command. Replies to `8003` are much longer than the other replies and begin `030300000003`. Comparing those frames before, during and after each app action showed which characters change:

* Two characters (positions 14-15) track the **flame level** and move after every level command.
* A 16-bit field (positions 16-19) flips specific bits at the moments the user observed *ignition start* and *flame lit*.

The rest of the frame stayed constant or varied in a way that did not correlate with anything done (see open questions).

### 2.7 First conclusions were partly wrong, and were corrected by live tests

The first reading of the captures suggested a **two-position valve**: `801A` = high, bare `80B0` = low, nothing in between. The app shows percentages (for example 75, 65, 53, 47, 36, 27, 20, 10 %) but in the first captures the physical flame appeared to change only between "high" and "low". Sending commands directly to the fireplace falsified this:

* Sending bare `80B0` changed nothing.
* `8016LL` really is a **proportional** flame control, and the level is reported back in the status frame.
* Some app percentage steps are close enough that the eye cannot distinguish them (for example 9 % versus 5 % - only the lower one visibly changed the flame), which had been mistaken for a two-level device.

Because of this, the protocol was only treated as understood after **sending each command from our own code** and watching both the flame and the status frame (section 11).

### 2.8 Validate with our own client

Commands were sent with a minimal TCP client (first from a shell script, then from Home Assistant buttons backed by it), always with a person standing at the fireplace. Each test recorded: command sent, reply, status frame sequence, and what the flame did. The integration was written only after these tests.

## 3. Transport and framing

* TCP, port **2000**, one stream, no handshake, no authentication.
* Every message in both directions is ASCII text wrapped as:

```
STX (0x02)  "30303030"  <code>  ETX (0x03)
```

* `30303030` is a constant prefix on all **commands** the app sends. Its meaning is unknown; it is always sent.
* The device answers every message. Replies are also `STX ... ETX` framed and start with `0303000000` followed by the last two characters of the command code (for example `03030000001A` acknowledges `801A`, `030300000016` acknowledges `8016LL`, and `030300000003` marks a status reply to `8003`).
* **Connection behaviour (observed):** shortly after one connection closes, a new connection often receives no answer for some time. Holding **one long-lived connection** and polling over it is reliable. The module also disappears from Wi-Fi for minutes at a time on the tested unit, so a client must reconnect with back-off.
* **Multiple clients (not tested):** whether the official app and another client can be connected simultaneously is unknown. Close the app while Home Assistant is connected to be safe.

Example: poll status.

```
02 33 30 33 30 33 30 33 30 38 30 30 33 03
STX  "303030308003" = "30303030" + "8003"  ETX
```

## 4. Commands

Codes are shown as the text between the prefix and ETX. A full message is `STX` + `30303030` + code + `ETX`.

| Code | Meaning | Reply | Status |
|---|---|---|---|
| `8003` | Poll status | Status frame (section 5) | Observed, used |
| `8001` | Poll static info | Constant block, `...01005400` | Observed, not used |
| `801A` | Ignite | Ack `03030000001A` | Observed, used |
| `8010` | Extinguish | Ack `030300000010` | Observed, used |
| `8016` + `LL` | Set flame level, `LL` = `00`..`FF`, two hex digits | Ack `030300000016` | Observed, used. Also accepted while off. |
| `802001` | Second burner on | Ack | Observed, used (optional) |
| `802000` | Second burner off | Ack | Observed, used (optional) |
| `8050ff00`, `8050ff01` | Unknown. Seen next to some level changes in the app | - | Observed, not needed |
| `80B0` | Unknown. Alone it changes nothing | - | Observed, not needed |

A few important behaviours:

* `8016LL` is the only command needed to change flame height. The app additionally sends `8050`/`80B0` around some changes; those were **not required** in tests.
* Level commands are accepted while the fireplace is off. The integration still blocks them in the UI unless the fireplace is lit (see section 8).
* Ignition is a request, not an immediate state. The fireplace confirms `lit` a number of seconds later (section 6).

## 5. Status frame

Reply to `8003`, with STX and ETX removed. Positions are 0-based character offsets into the ASCII text.

```
030300000003 | 5F | LL | FFFF | ...
  0 .. 11       12-13  14-15  16-19
  prefix         const  level   flag word
```

| Positions | Meaning |
|---|---|
| 0-11 | `030300000003`: prefix identifying a status reply |
| 12-13 | `5F`: constant on the tested unit |
| 14-15 | **Flame level byte**, hex `00`..`FF`. The value the valve currently reports. After a command it ramps to the target rather than jumping (roughly 30 steps per second, observed). |
| 16-19 | **Flag word**, 16-bit hex, see below |
| 20 onwards | Further fields. Only the part around positions 28-31 varies with activity; meaning unknown. The remainder is constant or looks like device identity. |

Flag word bits:

| Mask | Meaning | Evidence |
|---|---|---|
| `0x0010` | **Igniting** | Set from about 1 s after `801A`; cleared when lit. |
| `0x0080` | **Lit** (flame confirmed by the device) | Set about 18-21 s after `801A`; stays set while burning, including at level `00`. |
| `0x0008` | Second burner enabled | Follows `802001` / `802000`. |
| `0x0200` | Unknown | Set in some sessions and not in others; unrelated to the controls tested. |

State derivation used by the integration:

```
if flags & 0x0080:  state = lit
elif flags & 0x0010: state = igniting
else:                state = off
```

Because the **device** reports `lit`, Home Assistant can show "igniting" for the whole ignition phase and knows with certainty when the flame is established.

## 6. Behaviour and timing

All values observed on the tested unit.

| Event | Timing |
|---|---|
| `801A` sent -> `igniting` flag | about 1 s |
| `igniting` -> `lit` flag | about 18-21 s after the command |
| Level byte reaches `FF` after ignite | about 25-27 s after the command |
| Level command -> visible flame change | about 5-10 s |
| Poll interval used by the app | about 1 s |
| Poll interval used by this integration | 2 s |

Practical consequences:

* A UI button that reflects "on" must have an intermediate **igniting** state; otherwise it looks broken for the first ~20 s.
* Flame controls should be disabled until `lit` is confirmed.
* After sending a command, the integration holds the expected state for a few seconds so the UI does not flicker back before the first poll shows the new state, then resumes trusting the device.

## 7. Flame levels

`8016LL` is proportional. Levels tested by eye:

| Level byte | Percent | Result |
|---|---|---|
| `FF` | 100 % | Full flame |
| `8B` | about 55 % | Visibly lower flame (used for the "Low" preset) |
| `40` | about 25 % | Almost out |
| `00` | 0 % | Small waiting flame ("Standby"). Status still reports **lit**. |

Notes:

* Levels close together (for example 9 % versus 5 % in the app's own steps) can look identical to a person. The device is proportional, but the visible difference is not.
* "Standby" is not off. The fireplace stays lit with a small pilot-style flame. Only `8010` extinguishes it.
* The integration maps the percentage slider to the byte as `round(percent * 255 / 100)` and reports back `round(level * 100 / 255)`.
* Presets: `standby` = `00`, `low` = `8B`, `high` = `FF`. A reported level is mapped back to the nearest preset (below `0x20` standby, `0xC0` and above high, otherwise low).

## 8. How the integration uses the protocol

* **One persistent connection** opened by a background task; reconnect with back-off (5 s up to 60 s).
* **Poll `8003` every 2 s** over that connection; the frame is parsed with a strict prefix check, so unrelated frames are ignored.
* **Availability:** the entities become unavailable when no valid status frame has arrived for 8 s or the connection is lost, and recover automatically when frames resume.
* **Commands** go over the same connection. After a command the expected state is applied immediately ("optimistic") and held for up to 6 s; the next real status frame then takes over.
* **Entities:**
  * `switch` Fireplace: `801A` / `8010`; on whenever the state is not `off`.
  * `sensor` Status: `off` / `igniting` / `lit` from the flag word.
  * `select` Flame preset and `number` Flame level: `8016LL`. Unavailable unless `lit`.
  * `switch` Second burner: `802001` / `802000`, disabled by default, unavailable unless `lit`.
* **Config flow:** performs a real `8003` poll to validate the address and port. The options flow lets you change the address without removing the integration.

## 9. Open questions

* Whether the Planika app and another client can be connected at the same time.
* Time from `8010` to the flame being completely out. The measurement was lost; the status flag clears quickly but the physical burner takes longer.
* Meaning of flag `0x0200` and the field around positions 28-31 of the status frame.
* What the second burner physically does. No visible effect was seen on the tested unit, so the switch is disabled by default.
* Purpose of `8050ff00` / `8050ff01` / `80B0`, and of the `30303030` prefix.
* Behaviour on other Planika models or firmware versions.
* Whether a timer, child-lock or error state exists in the status frame (the app's LED option, for a fireplace without LEDs, sent codes whose effect could not be observed).

If you have a different model, a capture (hex dump of a session with a note of what was pressed when) is the most useful contribution.

## 10. Reproducing the analysis

You do not need special hardware beyond a Mac and an iPhone.

1. Put the fireplace on a fixed IP and note it.
2. Connect the iPhone to the Mac by USB and trust the computer.
3. Find the phone's UDID (Xcode -> Window -> Devices, or Finder).
4. Create the virtual interface: `rvictl -s <UDID>` (if it fails with `bootstrap_look_up`, load `com.apple.rpmuxd`).
5. In Wireshark capture on `rvi0` with the filter `ip.addr == <fireplace-ip> && tcp.port == 2000`.
6. Use the Planika app one action at a time, waiting about 10 s between actions, and note the time of each action.
7. Right-click a packet -> *Follow -> TCP Stream* -> show data as *Hex dump* and save.
8. Compare the dumps with section 4 and 5. Any message of the form `02 3330 3330 ... 03` is a frame; convert the bytes between `02` and `03` to ASCII.

Quick connectivity check without Home Assistant (prints the status frame):

```sh
printf '\002303030308003\003' | nc -w 3 <fireplace-ip> 2000 | xxd
```

(`\002` is STX, `\003` is ETX; the text in between is `30303030` + `8003`.)

## 11. Test log

Live tests against the physical fireplace, always with a person present.

| Date | Test | Result |
|---|---|---|
| 2026-10-05 | `801A` from our own client | Fireplace ignites; status shows igniting then lit. |
| 2026-10-05 | `8010` | Fireplace extinguishes. |
| 2026-10-05 | Bare `80B0` | No change - the earlier "80B0 = low" reading was wrong. |
| 2026-10-05 | `8016LL` at several values | Proportional flame; level echoed in status frame. |
| 2026-10-08 | Ignite and watch the status frame | `igniting` ~1 s, `lit` ~18-21 s, level `FF` ~25-27 s. |
| 2026-10-08 | Level `8B` then `40` then `00` | Visibly lower, then almost out, then a small waiting flame; status stays lit. |
| 2026-10-08 | Second burner on/off | No visible change on this unit. |
| 2026-10-08 | Flame response time | About 5-10 s after a level command. |
| 2026-10-08 | Integration installed in Home Assistant | Entities load and report `off`; flame preset and level are unavailable while the fireplace is off. A full ignite -> lit -> presets -> extinguish run through the Home Assistant UI is still to be recorded here. |

Not yet tested: simultaneous app + Home Assistant, long-term behaviour across Wi-Fi drop-outs, other models.
