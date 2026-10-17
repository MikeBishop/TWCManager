### Task 4: Local provider command methods return outcomes (TeslaBLE, Gen2, Gen3)

Today `TeslaBLE.sendCommand` returns the tesla-control output or `None`; `_sendCommand_internal` sets `_keyRefusal.refused` and records a refusal through `_noteBleRefusal` → `_setBleStatus`, which drops the registry claim except inside `PAIRING_WINDOW`; `parseCommandOutput` and `_is_already_satisfied` classify output; `_scheduleBlocksStart` says the car's own schedule blocks a start; `_sendCommand_internal` calls `_noteBleProof` on any answered command. `Gen2TWCProvider.stopCharging` has no caller yet, compares the raw key (final-review M5) and, in mode 3, would call `master.sendStopCommand` (an RS-485 write) from whatever thread runs it. `ProviderOrder.dispatch` is still called by `VehiclePriority.setAmps` until Task 10 and reads success by truthiness, which an `Outcome` tuple always is.

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaBLE.py` (`commandOutcome`, `probe`, `_sendCommand_internal(..., noteProof=True)`), `lib/TWCManager/Vehicle/Providers/TeslaBLEProvider.py`, `Gen2TWCProvider.py`, `Gen3TWCProvider.py`, `lib/TWCManager/Vehicle/Providers/Suppressions.py` (billed stops under `chargeStopMode` 2/3), `lib/TWCManager/Vehicle/Providers/Order.py` (`dispatch` reads outcomes), `lib/TWCManager/TWCSlave.py` (`stopRequested` sent by `send_master_heartbeat`), `lib/TWCManager/EVSEInstance/Gen2TWC.py` (`stopRequested` attribute), `tests/unit/test_teslable_provider.py` (`test_commands_call_the_module_by_vin`), `test_gen2twc_provider.py` (`test_disruptive_stop_declared_very_high_cost_and_off_by_default`, `test_set_amps_publishes_a_target_for_the_heartbeat`), `tests/unit/test_gen3twc_provider.py` (`test_provider_commands_go_to_the_unit`) — return values are outcomes now.
- Test: `tests/unit/test_provider_outcomes_local.py`; create `tests/unit/gen2_helpers.py` (the real-heartbeat driver Tasks 8 and 9 reuse).

**Interfaces:**
- Produces (`tests/unit/gen2_helpers.py`): `drive(master, slave, amps_actual, state=0x04, amps_max=0.0) -> Mock` — works on the `make()`/`setup()` masters (verified against base 6a6c14e under the capped pytest: one heartbeat per call, `iface.send` once per call): on first use it (1) completes `master.config["config"]` **and** `slave.configConfig` with `fakeMaster = 1` and `displayMilliseconds = False` (`print_status` reads them), (2) gives `master.TWCID` the bytes value `b"\x77\x77"` when it is not bytes (`make()` passes `"AB"`), (3) replaces `master.getModuleByName` with a dict lookup that answers `"Policy"` with a Mock whose `policyIsGreen()` is False (the heartbeat calls `fireWebhook` and `policyIsGreen` on it) and `"Dummy"` with a Mock interface, falling back to the previous lookup (`None` on error) for other names, and (4) wraps `master.getModulesByType` so `"Interface"` yields `[{"name": "Dummy", "ref": iface, "type": "Interface"}]`; then feeds one `receive_slave_heartbeat` with the given state/max/actual (the 7-byte layout `test_gen2_idle_minimum.heartbeat()` builds) and one `send_master_heartbeat`; returns the interface mock so a test can read the wire offer. The stubs are kept on `master._driveStubs` so repeated calls reuse them. `test_gen2_idle_minimum.py` keeps its own helpers.
- Produces (`TeslaBLE`): `commandOutcome(self, vin, command, args=None) -> Outcome`: `vin` upper-cased; `_keyRefusal.refused` after the call, or a stored BLE status of `"refused"` → `Outcome(REFUSED, "key")` — the claim is whatever `_setBleStatus` made of it (dropped outside the pairing window, kept inside it); this method never touches claims; `sendCommand` → `None` → `Outcome(UNREACHABLE, "no reply")` (timeout, circuit breaker open, binary missing, VIN not in settings); output with `_is_already_satisfied` → `Outcome(SATISFIED, <reason word>)`; `parseCommandOutput` True → `DONE`; else `Outcome(ERROR, <error category>)`. Never logs the output beyond today's DEBUG lines. `probe(self, vin) -> Outcome`: one `_sendCommand_internal(vin, "body-controller-state", noteProof=False)` (tesla-control's VCSEC query, answered while infotainment sleeps and without an authenticated session, so it never wakes the car and must not count as key proof; one shot, no `_execute_with_retry` backoff, bounded by `commandTimeout` under `_bleLock`), classified as `commandOutcome` does. `_sendCommand_internal(self, vin, command, args=None, noteProof=True)`: `noteProof=False` skips `_noteBleProof`.
- Produces (`TeslaBLEProvider`): `probe(vin)` → `ble.probe(vin)`; `setChargeLimit(vin, limit)` → `commandOutcome(vin, "charging-set-limit", int(limit))`; `startCharging(vin)` → `Outcome(SATISFIED, "scheduled")` when `ble._scheduleBlocksStart(vin)` (today: treated as done, not re-asked), else `commandOutcome(vin, "charging-start")`; `stopCharging(vin)` → `"charging-stop"`; `setAmps(vin, amps)` → `"charging-set-amps"` with `int(amps)`; `wake(vin)` → `commandOutcome(vin, "wake")`. No pre-wake inside the provider: the lane wakes when the attempt says so.
- Produces (`Gen2TWC`): `stopRequested: bool = False` (set off the serial thread, consumed on it).
- Produces (`TWCSlave.send_master_heartbeat`): at the top, `if self.stopRequested: self.stopRequested = False; self.master.sendStopCommand(self.TWCID)` — the only place a stop reaches RS-485, on the serial thread.
- Produces (`Gen2TWCProvider`): `declarations()` adds `START_CHARGING: Declaration(LOCAL)`; `ready(vehicle, START_CHARGING)` → `stopMode() == 2 and slaveFor(vehicle) and master.desired.state(vehicle.key).lastStopProvider == "Gen2TWC"` (mode 2's "start" is to answer slaves again; it undoes only a stop this provider delivered, never a BLE or cloud stop — Task 8); `startCharging(vin)` → under `settingsLock` `settings["respondToSlaves"] = 1` → `Outcome(DONE, "respond")`; `stopCharging(vin)`: no slave for the key → `Outcome(UNSUPPORTED, "no slave")`; mode 1 → `Outcome(UNSUPPORTED, "mode 1")`; mode 2 → `master.stopRespondingToSlaves()` → `Outcome(DONE, "respond")`; mode 3 → `slave.stopRequested = True` → `Outcome(DONE, "queued")` (the heartbeat sends it); `_slaveForKey` upper-cases a VIN key (M5); `setAmps(vin, amps)` → publishes the target → `Outcome(DONE)` (still never chosen for the `AMPS` aspect: Task 9).
- Produces (`Gen3TWCProvider`): `startCharging`/`stopCharging`/`setAmps` return `Outcome(DONE)`; `Outcome(UNSUPPORTED, "no unit")` when `unitFor(vehicle)` is `None`. The zero-headroom stop stays at the local tier, unverified on hardware (Phase 2 G4).
- Produces (`Suppressions.suppressed`): additionally `True` when `capability == STOP_CHARGING`, `not provider.local` and `int(settings.get("chargeStopMode", 1)) in (2, 3)` — a user who chose a disruptive local stop pays nothing for stops today and keeps paying nothing (Decision 7).
- Produces (`ProviderOrder.dispatch`): a result `r` counts as success when `isOutcome(r) and r.kind in SETTLED`, or, for a legacy non-outcome return, `r and r != "error"` as today — the façade's `setAmps` keeps working with outcome-returning providers until Task 10 deletes both.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_provider_outcomes_local.py
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Reconcile import Outcome as O
from TWCManager.Vehicle.Reconcile.Desired import DesiredStore
from tests.unit.reconcile_helpers import ScriptedProvider
from tests.unit.test_teslable_pairing_status import make, VIN
from tests.unit.test_gen2twc_provider import make as make_gen2

def test_ble_outcomes_follow_tesla_control_output():
    ble, reg, master = make(); (p,) = ble.providers(); v = reg.getOrCreate(VIN, "t"); ble._claimUnproven(v)
    ble.sendCommand = Mock(return_value=None);        assert p.setChargeLimit(VIN, 80) == O.Outcome(O.UNREACHABLE, "no reply")
    ble.sendCommand = Mock(return_value="Command executed successfully"); assert p.setChargeLimit(VIN, 80).kind == O.DONE
    ble.sendCommand = Mock(return_value="Error: car could not execute command: already_set"); assert p.setChargeLimit(VIN, 80) == O.Outcome(O.SATISFIED, "already_set")
    ble.sendCommand = Mock(return_value="connection failed"); assert p.stopCharging(VIN) == O.Outcome(O.ERROR, "connection")
    assert ble.sendCommand.call_args.args == (VIN, "charging-stop")

def test_ble_key_refusal_is_refused_and_the_claim_follows_the_pairing_window():
    ble, reg, master = make(); (p,) = ble.providers(); v = reg.getOrCreate(VIN, "t"); ble._claimUnproven(v)
    def refuse(vin, command, args=None): ble._keyRefusal.refused = True; ble._noteBleRefusal(vin, ble.KEY_REFUSED_TEXT); return None
    ble.sendCommand = refuse
    assert p.startCharging(VIN).kind == O.REFUSED and "TeslaBLE" not in reg.get(VIN).claims and p.ready(reg.get(VIN), C.START_CHARGING) is False
    ble._claimUnproven(v); ble._setBleStatus(VIN, "pairing", pairingSent=__import__("time").time())
    assert p.startCharging(VIN).kind == O.REFUSED and "TeslaBLE" in reg.get(VIN).claims                   # inside the window: not a refusal of the key

def test_ble_probe_is_one_non_waking_body_controller_query_that_proves_nothing():
    ble, reg, master = make(); (p,) = ble.providers(); v = reg.getOrCreate(VIN, "t"); ble._claimUnproven(v)
    ble._run_command_with_timeout = Mock(return_value=(b"", b"ok", 0)); ble.sendPrivateKey = Mock(return_value=True); ble._execute_with_retry = Mock(side_effect=AssertionError("no retry wrapper"))
    master.settings.setdefault("Vehicles", {})[VIN] = {"privKey": "k"}
    assert p.probe(VIN).kind == O.DONE and ble._run_command_with_timeout.call_args.args[0][-1] == "body-controller-state"
    assert reg.get(VIN).claims["TeslaBLE"].status == "unproven"                                           # no proof from a VCSEC answer
    ble._run_command_with_timeout = Mock(return_value=(None, None, None)); assert p.probe(VIN).kind == O.UNREACHABLE

def test_ble_schedule_block_is_satisfied_without_a_command():
    ble, reg, master = make(); (p,) = ble.providers(); ble._scheduleBlocksStart = lambda vin: True; ble.sendCommand = Mock()
    assert p.startCharging(VIN) == O.Outcome(O.SATISFIED, "scheduled") and ble.sendCommand.call_count == 0

def test_gen2_stop_and_start_outcomes_and_the_billed_stop_suppression():
    m, s = make_gen2(); m.desired = DesiredStore(); p = m.providerOrder.provider("Gen2TWC"); v = m.vehicleRegistry.getOrCreate(VIN, "t"); s.currentVIN = VIN.lower()
    assert p.stopCharging(VIN.lower()) == O.Outcome(O.UNSUPPORTED, "mode 1") and p.ready(v, C.START_CHARGING) is False
    m.settings["chargeStopMode"] = "2"
    assert p.stopCharging(VIN).kind == O.DONE and m.settings["respondToSlaves"] == 0 and p.ready(v, C.START_CHARGING) is False   # no Gen2 stop recorded yet
    m.desired.state(VIN).lastStopProvider = "Gen2TWC"
    assert p.ready(v, C.START_CHARGING) and p.startCharging(VIN).kind == O.DONE and m.settings["respondToSlaves"] == 1
    m.desired.state(VIN).lastStopProvider = "TeslaBLE"; assert p.ready(v, C.START_CHARGING) is False      # a BLE stop is undone over BLE
    fleet = Mock(local=False, name="FleetAPI"); assert m.providerOrder.suppressions.suppressed(fleet, C.STOP_CHARGING) and not m.providerOrder.suppressions.suppressed(fleet, C.START_CHARGING)
    m.settings["chargeStopMode"] = "1"; assert not m.providerOrder.suppressions.suppressed(fleet, C.STOP_CHARGING)
    assert p.stopCharging("5YJ3E1EA1KF000009") == O.Outcome(O.UNSUPPORTED, "no slave")

def test_mode_3_stop_is_sent_by_the_heartbeat_not_the_caller():
    from tests.unit.gen2_helpers import drive
    m, s = make_gen2(); m.desired = DesiredStore(); p = m.providerOrder.provider("Gen2TWC"); s.currentVIN = VIN; m.settings["chargeStopMode"] = "3"; m.sendStopCommand = Mock()
    assert p.stopCharging(VIN) == O.Outcome(O.DONE, "queued") and s.stopRequested and m.sendStopCommand.call_count == 0
    drive(m, s, amps_actual=12.0)                                                                         # the serial thread's own heartbeat
    m.sendStopCommand.assert_called_once_with(s.TWCID); assert not s.stopRequested

def test_dispatch_reads_outcomes_until_the_facade_goes():
    m, s = make_gen2(); v = m.vehicleRegistry.getOrCreate(VIN, "t")
    a = ScriptedProvider("TeslaBLE", 2, True, [O.Outcome(O.UNREACHABLE)]); b = ScriptedProvider("FleetAPI", 5, False, [O.Outcome(O.DONE)], tier=C.FLEET_COMMAND)
    m.providerOrder.register(a); m.providerOrder.register(b)
    assert m.providerOrder.dispatch(v, C.SET_AMPS, lambda p: p.setAmps(VIN, 10), amps=10, localRule=False).kind == O.DONE and len(a.calls) == 3 and len(b.calls) == 1
```
(`send_master_heartbeat` needs an Interface module and a Policy; `drive` registers both.) Add to `test_gen3twc_provider.py`: `test_gen3_commands_return_outcomes` (`p.stopCharging(anon.key).kind == O.DONE`, unknown key → `UNSUPPORTED`).

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: setChargeLimit`).

- [ ] **Step 3: Implement** per Interfaces; adjust the Phase 2 provider tests named in Files to `.kind == O.DONE`.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_provider_outcomes_local.py tests/unit/test_teslable_provider.py tests/unit/test_gen2twc_provider.py tests/unit/test_gen3twc_provider.py tests/unit/test_provider_order.py tests/unit/test_vehicle_priority.py tests/unit/test_lanes.py tests/unit/test_gen2_idle_minimum.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/ lib/TWCManager/TWCSlave.py lib/TWCManager/EVSEInstance/Gen2TWC.py
git add lib/TWCManager tests/unit
git commit -m "Give the local providers command methods with classified outcomes; the Gen2 stop is sent by the heartbeat"
```

