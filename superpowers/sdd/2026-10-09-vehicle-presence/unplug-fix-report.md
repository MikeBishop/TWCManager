# Unplug false positive fix (Gen2 steady 00 after re-link)

Base a78fe3d. Commits:
- 6437f29 A TWC unplug needs a plugged run before it and none in the link grace
- f27532d Presence honours live telemetry's plug state
- a70fe5e TeslaMate's plugged_in feeds presence

Tests: full unit suite 937 pass (was 911 + 26 new); test_vehicle_presence.py 128 pass x5; black clean. f27532d alone: 934 pass.

## 1. TWC rule (TWCSlave._checkPlugState)
- `_runSince`: start of the current non-00 run (set on the first non-00 heartbeat after a 00, or when None). `_linkedAt`: the first heartbeat's `now` (heartbeat clock, so tests with injected `now` work).
- When a 00 begins, `_unplugQualified` = run >= UNPLUG_DEBOUNCE (60 s) and the 00 began >= LINK_GRACE (300 s) after the link. Only the report branch is gated; the "unplugged again during a replug hold clears plugVIN" bookkeeping is not.
- Grace is judged at the 00's onset, not at report time, so "link, 03 for 100 s, steady 00" is never reported (it would otherwise be reported at t=300).
- Re-link: a TWC silent > 26 s is deleted (`deleteSlaveTWC`) and its next linkready builds a new TWCSlave; a restart builds new objects. A re-link inside 26 s reuses the object, so the master-mode linkready branch now calls `slaveTWC.noteLinkReady()`, which resets `_linkedAt`, `_runSince` and `_unplugQualified` (a reported unplug and its plugVIN are kept, so the replug hold still applies).
- 00 flickers inside a plugged run end the run: the next 00 needs a fresh 60 s non-00 run before it.

Existing tests adjusted (setup now unrealistic: a 1 s plugged run, or a slave that had just linked, before the unplug):
- test_twcslave.py TestPlugDebounce fixture (shared by TestPlugVIN): seeded as linked and plugged in long ago (`_linkedAt = _runSince = -1000`, `reportedState = 0x01`). No test bodies changed except:
- TestPlugDebounce.test_startup_in_state_00_is_not_an_unplug: resets to a fresh slave (unseeded).
- test_vehicle_presence.py TestSameTwcReplugEndToEnd: an 03 beat at t=-400 added before the existing sequence.

New: TestUnplugNeedsAPluggedRun (incident sequence, short run after grace, 00 begun inside grace, re-link re-arms grace, genuine unplug after a long 03, charging states count toward the run, linkready hook source check). All but the genuine-unplug/charging ones fail on the old code.

## 2/3. Telemetry plug signal
- TeslaMateVehicle.events["plugged_in"] -> `pluggedIn` via `parse_bool` ("true"/"false" only, else None, so an empty payload is never an unplug). `CarApiVehicle.pluggedIn = None`.
- Telemetry.applyDataToVehicle captures the previous value; on a pluggedIn change between two bools, `_reportPlug` calls `presence.observeTelemetryPlug(vin, value)` (record-only, MQTT thread, no I/O). The retained value on connect starts from None: not a change.
- PresenceSources.telemetryPluggedIn(master, vin): True/False/None, None unless syncSource is the telemetry module (telemetryChargeLimit's criterion). Injectable as `VehiclePresence(pluggedIn=...)`.
- runPass reads it outside the lock, only when the batch has a TWC unplug, for the unplug VINs plus HOME VINs. `_applyUnplug`: named VIN plugged in -> INFO, ignored; VIN-less -> plugged-in candidates removed (INFO), and ambiguity is counted after removal.
- "telemetryPlug" observations: False for a HOME BLE car -> `_applyUnplug("telemetry", (vin, frozenset()), ...)`, so DEPARTING and the early BLE restore through the same path (`_departing["telemetry"]`). True for a DEPARTING car -> `_applyHome` -> arrival handler.

New presence tests: TestTelemetryPlug, TestTelemetryPluggedInDefault, TestUnplugEndToEnd (real TWCSlave into real presence: incident stays HOME, a genuine unplug after a long 03 departs, telemetry plugged-in overrules it). Telemetry tests: change-only push, odd payload is unknown, parse_bool.

## Concerns
- Linkready frequency, checked on the box (48 h journal): 14 "ready to link" lines, all in bursts of 1-3 within 6 s at a (re)link, never periodic while linked, so noteLinkReady() does not keep re-arming the grace. One was a mid-run re-link without the 26 s timeout (19:29:20, about 10 s after a main-loop stall at charge start), which is the case the hook covers. Each such re-link opens a fresh 300 s window with no TWC unplugs.
- A car plugged in for under 60 s and then unplugged is no longer an unplug (by design); likewise a genuine unplug in the first 300 s after a restart or re-link. Delayed probes and telemetry still cover these.
- A Gen2 flicker to 00 shortly before a genuine unplug resets the run; if the car is unplugged within 60 s of the flicker the TWC reports nothing. Telemetry or probes catch it.
- A TWC unplug that telemetry suppressed leaves the slave's `_unplugReported` set, so its later replug sends observePlug. On a VIN-less TWC with no departing set, that can bring the one DEPARTING car overall home (the existing I2 rule).
- A stale-but-live True (TeslaMate not updating plugged_in while the car sleeps right after unplugging) would hide a genuine TWC unplug; the telemetry False transition would then depart the car when it arrives.
- Telemetry unplugs only apply to HOME cars (not UNKNOWN), per the brief.
