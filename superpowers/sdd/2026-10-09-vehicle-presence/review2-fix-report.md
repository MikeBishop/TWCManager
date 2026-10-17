# Review 2 fix pass (944f6ec..ef2305d)

Implementer: Opus 5.5. Advisor consulted before I2 and before declaring done.
Suite: 905 passed, 1 pre-existing warning. test_vehicle_presence.py 5x: 111
passed each (pytest-randomly is not installed, so the order is fixed). black --check is clean on the changed lib files. Each new test
was run against the pre-fix lib file and failed there.

## Commits

- bac6dbd I1: the departure handler always queues the remoteOnly restore while
  a limit is held. The hand-set adoption block is gone.
- 5d0f608 I3 + M2: `_otherSlaveVINs` also excludes other slaves' real
  `plugVIN`. `plugVIN` is no longer wiped when a replug hold (re)starts.
- e198ace M1: the replug and arriving-timeout exits go through `_applyHome`.
  `_timeoutHome.add` still runs after it, so the ab545e7 exemption holds.
- 33d92ff M5: for a DEPARTING VIN, a ble source that raises counts as a failed
  probe. Elsewhere, raising still means "does not apply" (tested).
- 2622e74 I2: plug evidence on a TWC with no departing set brings a car HOME
  only when it is the one DEPARTING car overall.
- ef2305d M3: TeslaAPI's forceLive read on a restore uses `allowBle=False`.

## Notes per item

**I1.** `currentLimit` is now unused by both built-in handlers. The plumbing
stays: `_probe` collects the limit, `_setState` returns it in the transition
tuple, `_runHandler` passes it on, and about 25 tests depend on it. Removing
it would churn the tests for no behaviour change. The VehiclePresence header
says the built-in handlers ignore it. This is a candidate follow-up cleanup.
Tests: handler-level tests (stale 80 and hand-set 100 both queue the restore
and save nothing), plus a presence-level test where a telemetry probe answers
"away, limit 90" while we hold 70.

**I3.** Adds `s.plugVIN` when it is truthy and not NON_TESLA, next to
`currentVIN`. Tests: an idle car on another VIN-reading TWC is excluded; a
NON_TESLA plug elsewhere excludes nothing.

**M2.** Removed the clear at the start of the hold. One addition: a 00 held for
the full debounce while `_unplugReported` is already True (an unplug before the
replug hold completed) now clears `plugVIN`. Without it, a VIN read during an
aborted hold would carry into the next plug session, since no new unplug is
reported to clear it. Tests: a 00 flicker during the hold keeps the VIN and the
later unplug passes it; an aborted hold clears it.

**M5.** A sentinel from `_callSource(..., reportRaise=True)` is used only for
the ble source when the probed VIN is DEPARTING.

**I2.** Changes in each module:
- VehiclePresence: `observePlug(twc, vinReading=False)`. `_applyPlug` homes
  the TWC's own set if it has one, as before. Otherwise, unless `vinReading` is
  set, it counts VINs in state DEPARTING. It counts by state rather than by set
  membership because one VIN can sit in several VIN-less TWCs' sets. With
  exactly one, it calls `_applyHome` (the reason is "a plug on TWC X"):
  `_clearDeparting` removes the VIN from every set and the arrival handler
  runs. With several, it logs at INFO and does nothing.
- TWCSlave, plug evidence, using signals the slave already has:
  - The debounced replug, now sent with `vinReading=self.hasReportedVIN`.
  - A power-start on a TWC that has reported no unplug and has never read a
    VIN. A TWC idle since boot never reports an unplug (previousState starts
    at 00), so power-start is its only plug-in signal. A generic 00 -> plugged
    debounce was ruled out: it would need a boot-time unplug (candidate rules
    would depart HOME cars) and would misread a short Gen2 flicker.
- Narrowing of the ruling: plug evidence from a VIN-reading TWC is not used.
  That TWC's VIN query proves the car itself through observeProof. Its plug
  evidence would otherwise send a different car HOME, for example a nightly
  scheduled start on an already-plugged car while one other car is DEPARTING.
- Tests (presence): the one DEPARTING car goes HOME with an arrival; two
  DEPARTING cars stay put; once one candidate goes AWAY by probes, the other
  goes HOME; a VIN-reading TWC is ignored; no DEPARTING car means nothing
  happens. The old `test_plug_on_another_twc_changes_nothing` now tests the
  inverted behaviour.
- Tests (slave): power-start emits plug evidence only on a TWC that is
  VIN-less and not unplug-reported.
- Known limitations:
  1. A DEPARTING car replugged into another TWC that draws no current (full,
     or scheduled charging not yet due) stays DEPARTING until it draws current
     or another signal decides. This holds for both kinds of TWC. A VIN-less
     TWC that has reported no unplug has only the power-start signal. On a
     VIN-reading TWC, plug evidence waits for the VIN proof, and that proof
     comes with the first charge start.
  2. On a VIN-less TWC that has reported no unplug, power-start fires on
     every charge resume, not just at plug-in: policy stop/start, solar
     tracking, scheduled starts. Each resume during another car's DEPARTING
     window (typically 2-3 min, two failed BLE probes) sends that car HOME.
     What a false HOME costs: an arrival apply over BLE, which likely lands
     because the car is still in the driveway and overwrites the early
     restore. Then a Fleet API departure restore when it really leaves. That
     is the incident class this batch exists to avoid, though the rate is
     low. The ruling named power-start, so this is what was asked. Possible
     tightening: emit on power-start only after a recent 00 -> plugged
     transition on that TWC. That filters solar and policy resumes but not
     scheduled starts, because state 00 is briefly reported just before a
     scheduled start. A different car plugging into a VIN-less TWC has the
     same effect; that is the accepted ambiguity of the ruling.

**M3.** I used the fallback heuristic in a simpler form: the forceLive read
always uses `allowBle=False`. Justification:
- `calculateModulePriority` is fixed: TeslaBLE 20, TeslaAPI 10.
- `_resolveVehicleCommandModule` prefers VehiclePriority, then HomeAssistant,
  then TeslaBLE, then TeslaAPI. Every caller of `applyChargeLimit` and
  `car_api_charge` goes through the queue (grep).
- So TeslaAPI is reached only (a) via VehiclePriority after TeslaBLE failed
  or was excluded (remoteOnly, api_only), or (b) when TeslaBLE is not loaded.
  In (b), and under api_only, `update_charge` already did no BLE read. So
  "allowBle=False when forceLive, TeslaBLE is loaded and policy is not
  api_only" is the same as always False.
- On the VehiclePriority fallback after `TeslaBLE.applyChargeLimit` failed,
  TeslaBLE has already made its own live read (its `needsLiveRead` path), so
  the "BLE first" ruling from 944f6ec still holds. That reason does not cover
  every path, and the commit message and code comment don't say so. The
  `car_api_charge` -> `self.applyChargeLimit(lastChargeLimitApplied)` call at
  TeslaAPI:724 is reached after VehiclePriority dispatched `car_api_charge`
  (TeslaBLE's charge command failed), not `applyChargeLimit`, so TeslaBLE's
  limit read never ran there. The outcome is still the one review 3(b) asked
  for: one API GET, with no BLE read or BLE wake.
- Two existing assertions changed from `liveReads == [True]` to `[False]`.
- This also covers review 3(b): under prefer_ble, the policy-wide API restore
  is now one `vehicle_data` GET, with no BLE read or BLE wake.
- Not changed: the first `update_charge(allowBle=not remoteOnly)` read for
  `syncSource == "TeslaAPI"` cars can still try BLE after TeslaBLE failed. The
  same argument applies to it; I left it out of scope.

## Concerns

- I1 left `currentLimit` / probe-limit plumbing in place, now dead for the
  built-in handlers (see above).
- I2's `vinReading` / `hasReportedVIN` narrowing goes beyond the literal
  ruling; reverting it is a one-line change in each module.
- I2 power-start fires on every charge resume (limitation 2 above).
- I2: a replug that draws no current leaves the car DEPARTING (limitation 1).
- M3's code comment gives an incomplete reason for the car_api_charge path.
- The I1 commit also black-formatted three pre-existing lines in two test
  files.

## Coordinator follow-ups (ef2305d..f27c287)

**A. Same-TWC replug on a VIN-reading TWC (927bc67, test only).** This
already worked, so no code change was needed. `_applyPlug` pops and homes
the TWC's own departing set before it looks at `vinReading`, so the
concern-1 narrowing only applies to a TWC with no departing set. The new
end-to-end test `TestSameTwcReplugEndToEnd` uses a real TWCSlave on a
VIN-reading TWC and a real VehiclePresence. The sequence is: unplug (the car
becomes DEPARTING), then 03 held for 60 s, with no VIN read and no current.
The car goes HOME, the arrival handler runs and the departing sets are
empty. This corrects limitation 1 above for VIN-reading TWCs, and for any
TWC with an own set: a full car replugged into the TWC it left from comes
home after the 60 s hold. Limitation 1 still holds only for a replug into a
*different* TWC that never starts drawing current.

**B. PLUG_EVIDENCE_WINDOW (f27c287).** `TWCSlave.PLUG_EVIDENCE_WINDOW = 300`.
`_checkPresenceTriggers` records `_pluggedInAt` on a 00 -> 01/03/08
transition. Power-start counts as plug evidence (on a VIN-less TWC that has
reported no unplug) only within 300 s of that time. The first heartbeat after
startup is not a transition (`_heartbeatSeen`), because its previous state is
the class default 00. A car plugged in before startup therefore gives no
power-start evidence. Tests: a resume inside the window counts; one at 301 s
does not, though presence is still nominated; a resume with no plug-in seen
since startup does not count. The existing guard tests now include a recent
plug-in, so each one still checks its own guard. Residual exposure: a
scheduled start preceded by a brief 00 still looks like a plug-in, as noted.
Also fixed a stale `plugVIN` comment ("cleared ... when a replug starts").

Suite: 908 passed, 1 pre-existing warning. black --check is clean.
