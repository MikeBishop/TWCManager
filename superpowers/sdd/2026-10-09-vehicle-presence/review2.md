# Review 2: fix/vehicle-presence, 244b02c..944f6ec

Reviewer: Fable 5.1 (self-reviewed, advisor consulted once before writing).
Read-only. Read in passes: the ledger entries after "Final review:
complete", the four implementer reports, the spec; then the current
VehiclePresence.py, PresenceHandlers.py, ChargeLimitRules.py and
PresenceSources.py in full, the lib diff for TWCSlave, TWCManager,
VehiclePriority, VehicleCommandQueue, HomeAssistant, TeslaAPI and TeslaBLE,
and the unchanged code they lean on (TWCMaster limit helpers, VIN
bookkeeping and queue resolution, the VIN-query trigger in the main loop,
VehiclePriority._dispatch, update_charge / update_vehicle_data, the BLE
circuit breaker, the heartbeat path). Test names were checked for each
risk area and a few test bodies read. Suite: 888 passed, 1 pre-existing
warning. black --check clean. Worktree clean.

Judged against the spec plus the ledger decisions for this batch (BLE
read-before-write, breaker closes on evidence, ARRIVING with a 600 s
fallback, DEPARTING on a debounced unplug with the early localOnly restore,
plugVIN / NON_TESLA trust, VIN-less candidate rules, slow probes after the
cap, ChargeLimitRules with telemetry preferred except on restores that
disagree with lastApplied, handler adoption removed).

## Strengths

- The state machine is still readable. Every internal state has a
  bounded exit path in the code: ARRIVING always carries `_arrivingSince`
  and its deadline is put in `_due` (:739-742), so the timeout fires even
  if no probe ever answers; DEPARTING schedules its own probe every pass
  (:466-472) and the slow interval keeps it alive after the cap. Each
  transition goes through `_setState`, which clears the per-state
  bookkeeping (`_arrivingSince`, `_departing*`, `_timeoutHome`) in one
  place (:744-769).
- Handlers run exactly once per transition. The departing hook is run
  only after all observations in the batch are applied and only if the
  VIN is still DEPARTING (:412-418); a proof followed by a plug on the
  same TWC yields one arrival (the plug finds the VIN already HOME,
  :681-685); ARRIVING -> AWAY and UNKNOWN -> AWAY run nothing (:785-790).
- Lock discipline holds. Sources, `bleApplies`, `knownVehicles`, the
  home-proof hook, the departing hook and the handlers all run with the
  presence lock released; only logging happens under it. The only cross
  order is `_bleLock -> presence._lock` (`_reportContact`); `atHome`
  takes the presence lock as a leaf; `resetCircuitBreaker` and
  `record_success` touch plain dicts and take no lock.
- `_checkPlugState` is safe on the serial loop: time arithmetic, one list
  comprehension over the slave list (wrapped in try/except), one
  record-only observer call, one INFO line on the NON_TESLA path.
- ChargeLimitRules is pure and its table matches the old TeslaAPI and
  TeslaBLE branches path for path, apart from the three documented
  differences (adoption on apply, `sendWhenUnknown`, restore saves
  `(outside, -1)` for BLE too). The `saveNow`/`send` exclusivity invariant
  is tested. The pre-wake BLE gate on `lastApplied == -1` (87a4dc9) is
  what keeps the arrival apply with a -1 policy from waking the car.
- The queue interactions under the `(applyChargeLimit, vin)` key resolve
  correctly in every order I traced: early localOnly restore pending ->
  replaced by the remote restore on AWAY or by the arrival apply on a
  replug; early restore running -> the later remote restore is a read-only
  no-op through `decideChargeLimit`; remote restore pending -> replaced by
  the arrival apply. `_applyChargeLimitKwargs` keeps old signatures
  working.
- plugVIN / `hasReportedVIN` is the right answer to the "CAN off or
  non-Tesla" ambiguity: NON_TESLA is only trusted on a TWC that has read a
  VIN this run, so a DIP-2-down TWC still gets the candidate rules.
- Good tests for the new surface: real-queue depart/return, real TeslaBLE
  + FakeCar early-restore-then-departure (4 outcomes), the real-lock
  read-before-write test, breaker reset without the BLE lock, the
  no-source-under-lock invariant, the plug debounce table.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

1. **The departure handler still adopts a hand-set limit from a probe's
   telemetry value, without a live read; a stale TeslaMate limit skips the
   remote restore.**
   `lib/TWCManager/PresenceHandlers.py:106-114`, fed by
   `lib/TWCManager/VehiclePresence.py:591` and `:620` (both pass
   `outcome["limit"]` on a transition to AWAY), where for a
   telemetry-decided probe that limit is `_limit(vehicle)` = the pushed
   TeslaMate value (`PresenceSources.py:54`).
   The ledger ruled "telemetry fill arrivals only" because a stale
   telemetry limit on a departure skips the restore and corrupts the
   normal; 944f6ec then taught both channels to read live when telemetry
   disagrees with lastApplied; eec589b removed the arrival handler's
   adoption because "the channel adopts". The departure handler was left
   "unchanged" (extract-report) and is now the one place that trusts a
   telemetry limit for a restore decision. Path: we hold 50 (normal 80),
   TeslaMate still shows 80; the car leaves; the +300 s nomination probe
   or a DEPARTING probe gets telemetry "away, limit 80" before the pushed
   fix lands (pushes pass None and are safe) -> AWAY with limit 80 ->
   handler sees 80 != 50 -> "hand-set; keeping it", saves (80, -1), queues
   nothing. The car drives off at 50 and the pending early BLE restore (if
   any) then hits the -1 gate and skips too. On the live box the pushed
   fix usually wins the race (observations are applied before probes in a
   pass), so the window is the lat-then-lon split and the DEPARTING probe
   cadence; the consequence is the incident class.
   Fix: delete :106-114 and always queue the remoteOnly restore while a
   limit is held. TeslaAPI's `needsLiveRead` + `decideChargeLimit` already
   does the adoption correctly (hand-set -> save `(current, -1)`, send
   nothing; stale -> restore), at the cost of one `vehicle_data` GET in the
   hand-set case. With no remote channel the end state is the same either
   way (the next arrival apply adopts). `currentLimit` then becomes
   unused in both handlers, matching the "channel adopts" ruling.

2. **A DEPARTING car replugged into a different TWC that cannot read its
   VIN stays DEPARTING (reported AWAY) while it charges.**
   `lib/TWCManager/VehiclePresence.py:678-686` (`_applyPlug` pops only the
   unplug TWC's set), `:632-638` (BLE contact never exits DEPARTING),
   `:701-704` (location home is ignored), `:615-630` (a reachable probe
   only resets the count); `TWCSlave.py:183-184` sends `observePlug` only
   for a TWC that itself reported an unplug.
   So with two TWCs where the replug TWC is VIN-less (CAN off, or any
   VIN-less TWC other than the unplug one), nothing ever brings the car
   HOME: power-start nominates and probes it, BLE answers, telemetry says
   home, all ignored. Effects while it charges: `state()` says AWAY so the
   policy-wide BLE and API applies skip it; it charges at the normal limit
   the early restore set (or at a stale policy limit if the restore was
   ambiguous); `atHome` is False so an API `car_api_charge` start is
   skipped and `stopAskingToStartCharging` latches. It recovers only when
   the car finally drives off and comes back. Single-TWC installs (the
   live box) are unaffected. This needs a design call rather than a
   one-liner; the cheapest rule that is still sound: a plug (or
   power-start) on a TWC with no departing set brings the DEPARTING car
   HOME when exactly one VIN is DEPARTING overall. For several DEPARTING
   cars it remains ambiguous, as the candidate rules already accept.

3. **`excluded` for a VIN-less unplug uses `currentVIN`, which is cleared
   5 s after charging stops; an idle car plugged in on another VIN-reading
   TWC is a candidate and gets an early restore while plugged in.**
   `lib/TWCManager/TWCSlave.py:140-148` with `TWCMaster.py:1246-1250`.
   VIN-less TWC A reports an unplug; car V is plugged into VIN-reading TWC
   B and idle (currentVIN ""), so it is not excluded. If V is the only HOME
   bleProven car it becomes DEPARTING unambiguously: early BLE restore to
   its normal while plugged in, then skipped by policy-wide applies until B
   next reads its VIN (a proof needs a charge start). A restore to a higher
   normal can start it charging past the policy limit meanwhile. Fix: also
   exclude other slaves' `plugVIN` when it is a real VIN (it persists until
   that TWC's unplug is reported), falling back to `currentVIN`.
   `plugVIN` was introduced for exactly this attribution, so this is the
   missing half of 5fa7b69.

### Minor (Nice to Have)

1. **`_failedProbes` is not reset on the replug and timeout exits.**
   `VehiclePresence.py:683` and `:460` use `_setState` directly, unlike
   `_applyHome`. A count of 1 from before the unplug survives DEPARTING ->
   HOME, so one more failed BLE-only probe gives AWAY plus a departure
   restore instead of two. One-liner: use `_applyHome` (or reset there).

2. **`plugVIN` is wiped on every replug-hold restart.**
   `TWCSlave.py:187-188`. A Gen2 state-00 flicker during the 60 s hold
   (while `_unplugReported` is still True) re-enters that branch after a
   VIN may have been read in the new session, so the later unplug falls to
   the candidate rules. `test_flicker_keeps_the_plug_session` covers a
   flicker before any unplug report, not this one. The clear at the unplug
   report (:170) already expresses the intent; a VIN cannot be read while
   the TWC is in 00, so the hold-start clear is redundant and can go.

3. **`forceLive` is reachable on more paths than the remote-only restore.**
   `TeslaAPI.py:1024-1036` with `:2003-2020`. (a) A non-remoteOnly per-VIN
   restore that fell through to TeslaAPI after three BLE failures runs
   update_charge's BLE read and its BLE wake again. (b) Under `prefer_ble`
   the policy-wide API restore for a telemetry-synced car whose telemetry
   differs from lastApplied now does a BLE read (plus a possible wake), then
   a `vehicle_data` GET, where before this batch it read nothing. Rate
   limited to once a minute and only on the restore path; a cost note, not
   a bug, but the BLE wake inside update_charge is the "wake-on-read" the
   spec lists as a follow-up and this batch widens its reach.

4. **Stale telemetry equal to the target latches BLE's dedupe with no
   command.** `TeslaBLE.py:830-859` via `decideChargeLimit` "already at".
   Sequence: restore to 80 over BLE while the car was asleep, TeslaMate
   still shows 50, the policy later re-applies 50 -> "already at 50",
   dedupe latched, car actually at 80 until the next arrival reset. This is
   the user's "prefer TeslaMate" ruling applied as asked; the window is
   short in practice (a BLE wake brings the car online and TeslaMate polls
   it), so Minor, but it is the one direction `needsLiveRead` does not
   cover. If it shows up live, extend `needsLiveRead` to applies where
   telemetry == limit while lastApplied != limit.

5. **A DEPARTING car whose ble source raises never goes AWAY by probe.**
   `VehiclePresence.py:548-561` turns an exception into "does not apply",
   so `bleFailed` stays False (:527-528) and `_applyDepartingProbe` counts
   nothing. Only a location "away" or plug evidence ends it. The
   implementer noted it; a failing `probePresence` should count as a
   failed probe for bleProven VINs.

6. **More INFO logging under the presence lock.** `VehiclePresence.py:657,
   669, 720, 755-768`. `state()` is called from the serial loop through
   `CarApiVehicle.atHome` (HTTPControl, TeslaAPI gates), so a blocking log
   handler would stall it. Same class as the base's `_setState` logging;
   noting that the batch adds four more sites.

7. **`localOnly` under `commandPolicy: api_only` dispatches nothing.**
   `VehiclePriority.py:152` after `_skip_module_for_command` drops
   TeslaBLE: `_dispatch` returns False, the saved limit stays, the
   departure handler's remote restore covers it. bleProven can still be set
   in such an install because presence probes do not consult
   commandPolicy. Harmless; mention only.

8. **UNKNOWN -> DEPARTING -> AWAY runs the departure handler.**
   `VehiclePresence.py:647` admits UNKNOWN, `:785` runs the handler for
   old DEPARTING. Sound (a car on a TWC was home) and the handler checks
   the saved limit first; noting it because the spec's "unknown -> away
   runs no handler" rule now has this deliberate exception.

## Risk-area check

1. State machine: every transition traced (table in the reading notes
   above); no stuck state in single-TWC installs; the multi-TWC stuck
   DEPARTING is Important 2. Flapping: the timeout-home exemption holds
   until a BLE contact; ARRIVING <-> AWAY at the geofence boundary runs no
   handler, an improvement over the first batch.
2. Serial loop: `_checkPlugState`, `recordPlugVIN`, `_otherSlaveVINs` do
   no I/O and cannot block. OK.
3. Lock order: `_bleLock -> presence._lock` only; presence calls out only
   with its lock released; `atHome` is a leaf. OK.
4. ChargeLimitRules: equivalent to the old TeslaAPI branches except the
   deliberate differences; dedupe latches on every settled outcome and not
   on "unknown"; no API wake on any presence-only path (`needToWake` is
   False for -1); the Fleet API is used only for the remote-only restore
   and as the ordinary fallback. The one restore-skip gap is Important 1
   (handler level, not the rules).
5. Queue: traced; OK.
6. Multi-car / VIN-less: Important 2 and 3; `fakeMaster != 1` records into
   the bounded deque and never acts. OK.

## Challenge of ledger rulings

- "Prefer telemetry on applies" (extraction): accepted, with Minor 4 as the
  residual exposure.
- "Departures and departureHandler unchanged" (extract-report): this is
  where Important 1 lives. The ruling to move adoption into the channel is
  right; it was applied to arrival only.
- "Stay DEPARTING after the cap" (slow probes): right for one TWC; its
  cost in multi-TWC installs is Important 2.

## Recommendations

- Fix Important 1 now (a deletion plus test updates); it is the only item
  that can lose a restore on the live box.
- Fix Important 3 now (one more term in `_otherSlaveVINs`).
- Decide Important 2 with the user before merging if any multi-TWC
  install is in scope; otherwise record it as a known limitation in the
  spec's install matrix.
- Minors 1 and 2 are one-liners worth taking in the same pass.

## Assessment

**Ready to merge?** With fixes.

**Reasoning:** The batch implements the approved decisions faithfully,
the lock, serial-loop and no-wake invariants hold, and the queue
interactions resolve correctly. One handler still trusts a telemetry limit
for a restore decision (the exact failure the batch set out to close) and
two attribution gaps affect multi-TWC / VIN-less installs; all three are
small, contained changes.
