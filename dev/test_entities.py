import asyncio, enum, importlib, sys, types

def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m

# ---- minimal stand-ins for the Home Assistant classes the integration uses ----
class Entity:
    _attr_unique_id = None
    def __init__(self): self.writes = 0; self._removers = []
    def async_on_remove(self, f): self._removers.append(f)
    def async_write_ha_state(self): self.writes += 1
class _E: pass
class SwitchEntity(_E): pass
class SensorEntity(_E): pass
class SelectEntity(_E): pass
class NumberEntity(_E): pass
class SensorDeviceClass(enum.StrEnum): ENUM = 'enum'
class NumberMode(enum.StrEnum): SLIDER = 'slider'
class Platform(enum.StrEnum):
    SENSOR='sensor'; SWITCH='switch'; SELECT='select'; NUMBER='number'
class ConfigEntry:
    def __class_getitem__(cls, item): return cls
class ConfigFlow:
    def __init_subclass__(cls, domain=None, **kw): cls.domain = domain
class OptionsFlow: pass
class HomeAssistantError(Exception): pass

mod('homeassistant'); mod('homeassistant.components')
mod('homeassistant.components.switch', SwitchEntity=SwitchEntity)
mod('homeassistant.components.sensor', SensorEntity=SensorEntity, SensorDeviceClass=SensorDeviceClass)
mod('homeassistant.components.select', SelectEntity=SelectEntity)
mod('homeassistant.components.number', NumberEntity=NumberEntity, NumberMode=NumberMode)
mod('homeassistant.config_entries', ConfigEntry=ConfigEntry, ConfigFlow=ConfigFlow,
    ConfigFlowResult=dict, OptionsFlow=OptionsFlow)
mod('homeassistant.const', Platform=Platform, PERCENTAGE='%')
mod('homeassistant.core', HomeAssistant=object, callback=lambda f: f)
mod('homeassistant.exceptions', HomeAssistantError=HomeAssistantError)
mod('homeassistant.helpers')
mod('homeassistant.helpers.device_registry', DeviceInfo=dict)
mod('homeassistant.helpers.entity', Entity=Entity)
mod('homeassistant.helpers.entity_platform', AddEntitiesCallback=object)

pkg = types.ModuleType('planika'); pkg.__path__ = [str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'custom_components' / 'planika')]
sys.modules['planika'] = pkg
const = importlib.import_module('planika.const')
client_mod = importlib.import_module('planika.client')
FireState = const.FireState
modules = {n: importlib.import_module(f'planika.{n}') for n in
           ('entity', 'switch', 'sensor', 'select', 'number', 'config_flow', '__init__')}
print('all modules import')

results = []
def check(name, ok):
    results.append(ok); print(('PASS ' if ok else 'FAIL ') + name)

class Entry:
    entry_id = 'abc'; title = 'Planika Fireplace'
entry = Entry()

def make(cls_mod, cls_name, client):
    ent = getattr(modules[cls_mod], cls_name)(client, entry)
    Entity.__init__(ent)
    return ent

def set_state(c, available, state=None, level=0, burner2=True):
    c._available = available
    c._status = None if state is None else client_mod.PlanikaStatus(state, level, burner2)

calls = []
c = client_mod.PlanikaClient('x', 1)
async def rec(name, *a): calls.append((name, a))
c.async_ignite = lambda: rec('ignite')
c.async_extinguish = lambda: rec('extinguish')
c.async_set_level = lambda lv: rec('level', lv)
c.async_set_second_burner = lambda on: rec('burner2', on)

main = make('switch', 'PlanikaFireplaceSwitch', c)
burner = make('switch', 'PlanikaSecondBurnerSwitch', c)
status = make('sensor', 'PlanikaStatusSensor', c)
preset = make('select', 'PlanikaPresetSelect', c)
level = make('number', 'PlanikaLevelNumber', c)
controls = [burner, preset, level]
everything = [main, status] + controls

set_state(c, False)
check('disconnected: everything unavailable', not any(e.available for e in everything))
set_state(c, True, None)
check('connected but no status yet: everything unavailable', not any(e.available for e in everything))
set_state(c, True, FireState.OFF)
check('OFF: main switch and status available', main.available and status.available)
check('OFF: all other controls unavailable', not any(e.available for e in controls))
set_state(c, True, FireState.IGNITING)
check('IGNITING: main switch available (can cancel)', main.available)
check('IGNITING: all other controls unavailable', not any(e.available for e in controls))
set_state(c, True, FireState.LIT, 0xFF)
check('LIT: everything available', all(e.available for e in everything))

set_state(c, True, FireState.OFF)
check('switch is off when OFF', main.is_on is False)
set_state(c, True, FireState.IGNITING)
check('switch is on while IGNITING', main.is_on is True and main.icon == 'mdi:fire-alert')
check('phase attribute', main.extra_state_attributes['phase'] == 'igniting')
set_state(c, True, FireState.LIT, 0xFF)
check('switch is on when LIT', main.is_on is True and main.icon == 'mdi:fireplace')
check('status sensor value', status.native_value == 'lit' and status._attr_options == ['off', 'igniting', 'lit'])
for lv, expect in ((0x00, 'standby'), (0x41, 'low'), (0x89, 'low'), (0xFF, 'high')):
    set_state(c, True, FireState.LIT, lv)
    check(f'preset for level {lv:02X} = {expect}', preset.current_option == expect)
set_state(c, True, FireState.LIT, 255); check('number 100 %', level.native_value == 100)
set_state(c, True, FireState.LIT, 0x8B); check('number 55 %', level.native_value == 55)
set_state(c, True, FireState.LIT, 0, burner2=False); check('burner2 off reads False', burner.is_on is False)
set_state(c, True, FireState.LIT, 0, burner2=True); check('burner2 on reads True', burner.is_on is True)
check('second burner disabled by default', burner._attr_entity_registry_enabled_default is False)

async def cmds():
    await main.async_turn_on(); await main.async_turn_off()
    await preset.async_select_option('standby'); await preset.async_select_option('low'); await preset.async_select_option('high')
    await level.async_set_native_value(100); await level.async_set_native_value(25)
    await burner.async_turn_on(); await burner.async_turn_off()
asyncio.run(cmds())
check('commands map to the right client calls', calls == [
    ('ignite', ()), ('extinguish', ()), ('level', (0x00,)), ('level', (0x8B,)), ('level', (0xFF,)),
    ('level', (255,)), ('level', (64,)), ('burner2', (True,)), ('burner2', (False,))])

async def boom(): raise client_mod.PlanikaConnectionError('not connected')
c.async_ignite = lambda: boom()
async def err():
    try: await main.async_turn_on(); return False
    except HomeAssistantError: return True
check('connection errors become HomeAssistantError', asyncio.run(err()))

main._handle_update(); check('listener callback writes state', main.writes == 1)
unsub = c.add_listener(main._handle_update); c._notify(); unsub(); c._notify()
check('listeners can be added and removed', main.writes == 2)

bad = results.count(False)
print(f'\n{len(results) - bad}/{len(results)} passed'); sys.exit(1 if bad else 0)
