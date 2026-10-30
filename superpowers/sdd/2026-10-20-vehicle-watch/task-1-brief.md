### Task 1: The charge-port door, and a keyless ping

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/Fields.py:15-41`, `lib/TWCManager/Vehicle/TeslaBLE.py:627-648`, `lib/TWCManager/Vehicle/Presence.py:69-80, 120-160, 170-186, 196-212`
- Test: `tests/unit/test_presence.py`, `tests/unit/test_teslable_pairing_status.py`

**Interfaces:**
- Produces: registry field `chargePortOpen` (bool, source `TeslaBLE`); `TeslaBLE.ping(vin, scan=True) -> Optional[bool]` (True answered, False scan ran and missed, None no answer and no scan); `Presence._plug("chargePortOpen", obs)` → False for a False value, None for True.
- Behaviour changes (named): (a) a CLOSED door while awake is strong unplug evidence from `TeslaBLE`; (b) `ping` works for any well-formed VIN while `canScan()` or the tool is present, not only a claimed one; (c) `checkPlug` pings any such car, and an awake answer with the door CLOSED returns False without a charge read.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_presence.py` (helpers `home`, `placed`, `later` exist):

```python
def test_a_closed_charge_port_while_awake_marks_an_unplug():
    m, v, c = placed()
    v.observe("pluggedIn", True, "TeslaBLE")          # plugged, strong
    later(c)
    v.observe("chargePortOpen", False, "TeslaBLE")
    assert v.markAt("unplug") == c.t and P.pluggedNow(m, v) is False

def test_an_open_charge_port_is_not_plug_evidence():
    m, v, c = placed()
    v.observe("chargePortOpen", True, "TeslaBLE")
    assert v.markAt("plugIn") == P.NEVER and P.pluggedNow(m, v, None) is None

def test_check_plug_answers_from_an_awake_closed_door_without_a_read():
    m, r, v, c = home()
    v.observe("pluggedIn", True, "TeslaBLE")
    later(c)
    ble = m.providerOrder.provider("TeslaBLE").module
    def ping(vin, scan=True):
        v.observe("state", "online", "TeslaBLE"); v.observe("chargePortOpen", False, "TeslaBLE"); return True
    ble.ping = ping
    reads = []
    v.read = lambda *a, **k: reads.append(a)
    assert P.checkPlug(m, v, c.t - 1) is False and reads == []
```

In `tests/unit/test_teslable_pairing_status.py` (`scanner()` and the `run` pattern at :523 exist):

```python
AWAKE_OPEN = b'{"closureStatuses":{"chargePort":"CLOSURESTATE_OPEN"},"vehicleSleepStatus":"VEHICLE_SLEEP_STATUS_AWAKE","userPresence":"VEHICLE_USER_PRESENCE_NOT_PRESENT"}'
ASLEEP = b'{"vehicleSleepStatus":"VEHICLE_SLEEP_STATUS_ASLEEP","userPresence":"VEHICLE_USER_PRESENCE_NOT_PRESENT"}'

def test_ping_records_the_door_while_awake_and_nothing_asleep():
    ble, reg, master = scanner()
    v = reg.getOrCreate(VIN, "t")
    ble._tool = lambda vin, *args: (AWAKE_OPEN, b"", 0)
    assert ble.ping(VIN) is True
    assert v.value("state") == "online" and v.value("chargePortOpen") is True
    ble._tool = lambda vin, *args: (ASLEEP, b"", 0)
    assert ble.ping(VIN) is True
    assert v.value("state") == "asleep" and v.latest("chargePortOpen").value is True  # unchanged

def test_ping_runs_for_a_vin_with_no_key_and_no_settings_record():
    ble, reg, master = scanner()
    v = reg.getOrCreate(VIN, "t")       # no TeslaBLE claim, nothing under settings["Vehicles"]
    assert not master.settings.get("Vehicles", {}).get(VIN)
    runs = []
    ble._run_command_with_timeout = lambda cmd, timeout, **k: runs.append(cmd) or (ASLEEP, b"", 0)
    assert ble.ping(VIN) is True and v.value("state") == "asleep"
    assert len(runs) == 1 and runs[0][-1] == "body-controller-state" and "-key-file" not in runs[0]

def test_ping_with_scan_false_returns_none_and_observes_nothing_when_unanswered():
    ble, reg, master = scanner()
    v = reg.getOrCreate(VIN, "t")
    ble._tool = lambda vin, *args: (b"", b"timeout", 1)
    ble.scanForVehicleInRange = lambda vin: pytest.fail("no scan asked")
    assert ble.ping(VIN, scan=False) is None and v.latest("bleReach") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/unit/test_presence.py -k "charge_port or closed_door" tests/unit/test_teslable_pairing_status.py -k ping -q`
Expected: FAIL (`KeyError: 'chargePortOpen'`, `TypeError: ping() got an unexpected keyword argument 'scan'`).

- [ ] **Step 3: Add the field and record the door**

- `Fields.py`: append `"chargePortOpen"` to `FIELDS` with a one-line comment (the VCSEC charge-port door, reported only while the car is awake).
- `TeslaBLE._noteSleep(self, vin, out)`: parse `closureStatuses.chargePort` when present: `"CLOSURESTATE_OPEN"` → observe `chargePortOpen` True, `"CLOSURESTATE_CLOSED"` → False, anything else or absent → no observation. Keep the sleep observation as is.
- `TeslaBLE._tool` (`:588-604`): for `body-controller-state` only, run without `-key-file` and without `sendPrivateKey`, and do not require a `settings["Vehicles"][vin]` record (the command is unauthenticated); every other subcommand keeps the key and the record check.
- `TeslaBLE.ping(self, vin, scan=True) -> Optional[bool]`: `_runPing` takes `scan`; with `scan=False` an unanswered tool run returns None and observes nothing. With `scan=True` behaviour is as today. Drop any claim check on the ping path (there is none in `ping` itself; `checkPlug` and `pick` gate on claims, below).

- [ ] **Step 4: Presence: CLOSED is unplug evidence, OPEN is nothing**

- `Presence._plug(field, obs)`: `if field == "chargePortOpen": return False if obs.value is False else None`.
- `Presence.noteObservation`: add `"chargePortOpen"` to the `("pluggedIn", "chargingState")` branch so a False marks `unplug` (and `lifeAt` when seen) by the same rule; a True never marks `plugIn` (`_plug` returns None, so the existing `plugged is True` branch does not fire).
- `Presence.pluggedNow`: iterate `("pluggedIn", "chargingState", "chargePortOpen")`.
- `Presence.unpluggedAt`: same three fields.
- `Presence.checkPlug`: replace the claim gate with `canPing = ble is not None and ble.module is not None`; after a True ping: `if asleep(v): return True`; else `door = v.reported("chargePortOpen").get("TeslaBLE")`; `if door is not None and door.at >= since and door.value is False: return False`; otherwise fall through to the read as today.
- `Presence.pick` (`fits`): the pre-read ping's `"TeslaBLE" in v.claims` stays for the **charge read** (it needs the key) but the ping itself may run for any car; a CLOSED door excludes the car (`return False`) before any read.

- [ ] **Step 5: Run the tests and the full suite**

Run: the three test files, then the full suite. Expected: all pass; `test_presence.py` rows that count BLE reads in `pick` are unchanged (the door is absent in their fixtures).

- [ ] **Step 6: Commit**

```bash
git add lib/TWCManager/Vehicle/Registry/Fields.py lib/TWCManager/Vehicle/TeslaBLE.py lib/TWCManager/Vehicle/Presence.py tests/unit/test_presence.py tests/unit/test_teslable_pairing_status.py
git commit -m "Read the charge-port door on the sleep-safe ping; a closed door is an unplug"
```

---

