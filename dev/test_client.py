import asyncio, importlib, sys, types

PKG = str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'custom_components' / 'planika')
pkg = types.ModuleType('planika'); pkg.__path__ = [PKG]; sys.modules['planika'] = pkg
const = importlib.import_module('planika.const')
client = importlib.import_module('planika.client')
FireState = const.FireState

# speed everything up for the test
client.POLL_INTERVAL = 0.2
client.STALE_AFTER = 1.5
client.RECONNECT_DELAY = 0.3
client.PENDING_HOLD = 1.0

class FakeFireplace:
    """Mimics the observed behaviour: status frame per 8003, acks per command."""
    def __init__(self):
        self.state, self.level, self.burner2 = 'off', 0, True
        self.writers, self.server, self.silent = [], None, False
    def status_frame(self):
        flags = 0x0200 | (0x08 if self.burner2 else 0)
        if self.state == 'igniting': flags |= 0x10
        if self.state == 'lit': flags |= 0x80
        body = f"030300000003" + f"5F{self.level:02X}{flags:04X}" + "0000000000DC00C84861617264" + "F"*32 + "45501"
        return b"\x02" + body.encode() + b"\x03"
    async def handle(self, reader, writer):
        self.writers.append(writer)
        try:
            while True:
                frame = await reader.readuntil(b"\x03")
                code = frame.strip(b"\x02\x03").decode()[8:]
                if self.silent: continue
                if code == '8003': writer.write(self.status_frame())
                elif code == '8001': writer.write(b"\x02030300000001005400\x03")
                elif code == '801A':
                    self.state = 'igniting'; writer.write(b"\x0203030000001A\x03")
                    asyncio.get_event_loop().call_later(0.8, self._lit)
                elif code == '8010':
                    writer.write(b"\x02030300000010\x03")
                    asyncio.get_event_loop().call_later(0.5, self._off)
                elif code.startswith('8016'):
                    self.level = int(code[4:6], 16); writer.write(b"\x02030300000016\x03")
                elif code in ('802001', '802000'):
                    self.burner2 = code.endswith('1'); writer.write(("\x0203030000002" + code[-4:] + "\x03").encode())
                await writer.drain()
        except Exception:
            pass
    def _lit(self):
        if self.state == 'igniting': self.state, self.level = 'lit', 255
    def _off(self): self.state, self.level = 'off', 0
    async def start(self, port):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', port)
    async def stop(self):
        for w in self.writers: w.close()
        self.writers.clear()
        self.server.close()
        await asyncio.sleep(0.05)
    def drop_clients(self):
        for w in self.writers: w.close()
        self.writers.clear()

async def wait_for(cond, timeout=5, what=''):
    t = asyncio.get_event_loop().time()
    while not cond():
        if asyncio.get_event_loop().time() - t > timeout:
            raise AssertionError(f'timeout waiting for: {what}')
        await asyncio.sleep(0.05)

results = []
def check(name, ok):
    results.append((name, ok)); print(('PASS ' if ok else 'FAIL ') + name)

async def main():
    PORT = 12000
    # --- parse real captured frames -------------------------------------
    real = {
      'off 800A':  ("0303000000035F00800A00000000066600C84861617264FFFF", FireState.OFF, 0x00, True),
      'igniting':  ("0303000000035F00821A0000000000DC00C84861617264FFFF", FireState.IGNITING, 0x00, True),
      'lit 828A':  ("0303000000035F00828A0000000000DC00C84861617264FFFF", FireState.LIT, 0x00, True),
      'lit full':  ("0303000000035FFF828A0000000000DC00C84861617264FFFF", FireState.LIT, 0xFF, True),
      'lit 8B':    ("0303000000035F8B808A00000000066600C84861617264FFFF", FireState.LIT, 0x8B, True),
      'burner off':("0303000000035FFF8282000000000DC00C84861617264FFFF", FireState.LIT, 0xFF, False),
    }
    for name, (txt, st, lvl, b2) in real.items():
        p = client.parse_status(b"\x02" + txt.encode() + b"\x03")
        check(f'parse real frame: {name}', p is not None and p.state is st and p.level == lvl and p.second_burner == b2)
    check('static frame is not a status', client.parse_status(b"\x02030300000001005400\x03") is None)
    check('garbage is not a status', client.parse_status(b"\x02hello\x03") is None)
    check('level_to_preset', [const.level_to_preset(x) for x in (0, 0x40, 0x8B, 0xFF)] == ['standby', 'low', 'low', 'high'])

    # --- live behaviour --------------------------------------------------
    dev = FakeFireplace(); await dev.start(PORT)
    check('probe succeeds on a live device', await client.PlanikaClient.async_probe('127.0.0.1', PORT))
    check('probe fails on a closed port', not await client.PlanikaClient.async_probe('127.0.0.1', PORT + 1))

    c = client.PlanikaClient('127.0.0.1', PORT)
    events = []
    c.add_listener(lambda: events.append((c.available, c.status.state if c.status else None)))
    await c.async_start()
    await wait_for(lambda: c.available, what='first status')
    check('becomes available and reads OFF', c.status.state is FireState.OFF)

    await c.async_ignite()
    check('ignite shows IGNITING immediately (optimistic)', c.status.state is FireState.IGNITING)
    await wait_for(lambda: c.status.state is FireState.LIT, what='lit')
    check('reaches LIT from the device report', True)
    await wait_for(lambda: c.status.level == 255, what='full level')
    check('level read back as 255', c.status.level == 255)

    await c.async_set_level(0x8B)
    await wait_for(lambda: c.status.level == 0x8B, what='level 8B')
    check('set_level 0x8B read back', dev.level == 0x8B and c.status.level == 0x8B)
    await c.async_set_level(999)
    await wait_for(lambda: c.status.level == 255, what='clamped level')
    check('set_level clamps to 255', dev.level == 255)

    await c.async_set_second_burner(False)
    await wait_for(lambda: c.status.second_burner is False, what='burner2 off')
    check('second burner off read back', dev.burner2 is False)
    await c.async_set_second_burner(True)
    await wait_for(lambda: c.status.second_burner is True, what='burner2 on')
    check('second burner on read back', dev.burner2 is True)

    await c.async_extinguish()
    check('extinguish shows OFF immediately (optimistic)', c.status.state is FireState.OFF)
    await wait_for(lambda: dev.state == 'off', what='device off')
    await asyncio.sleep(1.4)
    check('stays OFF after the hold window (no flicker back)', c.status.state is FireState.OFF)
    flicker = [e for e in events if e[1] is FireState.LIT][-1:]
    check('no LIT event after extinguish was sent', events[-1][1] is FireState.OFF)

    # --- connection drops --------------------------------------------------
    dev.drop_clients()
    await wait_for(lambda: not c.available, what='unavailable after drop')
    check('goes unavailable when the connection drops', True)
    await wait_for(lambda: c.available, timeout=5, what='reconnect')
    check('reconnects by itself', c.available)

    dev.silent = True   # connected but the device stops answering
    await wait_for(lambda: not c.available, timeout=6, what='unavailable when silent')
    check('goes unavailable when the device goes silent', True)
    dev.silent = False
    await wait_for(lambda: c.available, timeout=6, what='recover from silence')
    check('recovers after the device answers again', c.available)

    await dev.stop()
    await wait_for(lambda: not c.available, timeout=6, what='unavailable when server gone')
    check('unavailable while the device is gone', True)
    await dev.start(PORT)
    await wait_for(lambda: c.available, timeout=8, what='reconnect after outage')
    check('recovers after a full outage', c.available)

    try:
        await c.async_stop(); await dev.stop()
        check('stops cleanly', True)
    except Exception as e:
        check(f'stops cleanly ({e!r})', False)

    # command while disconnected must raise, not hang
    c2 = client.PlanikaClient('127.0.0.1', PORT + 5)
    try:
        await c2.async_ignite(); check('command without connection raises', False)
    except client.PlanikaConnectionError:
        check('command without connection raises PlanikaConnectionError', True)

    bad = [n for n, ok in results if not ok]
    print(f'\n{len(results) - len(bad)}/{len(results)} passed')
    sys.exit(1 if bad else 0)

asyncio.run(asyncio.wait_for(main(), 90))
