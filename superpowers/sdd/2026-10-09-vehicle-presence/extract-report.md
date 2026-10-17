# Charge-limit rules extraction: report

Status: DONE

## Commits
- f674d37 Add ChargeLimitRules: one copy of the charge-limit decision rules
- 389815e TeslaAPI.applyChargeLimit uses the shared charge-limit rules
- ca9e14d TeslaBLE.applyChargeLimit uses the shared rules and prefers telemetry
- eec589b Hand-set limits are adopted by the channel, not on arrival
- 87a4dc9 TeslaBLE skips a restore without a wake when no limit is held

## Shape
`lib/TWCManager/ChargeLimitRules.py`:
- `decideChargeLimit(limit, current, saved, sendWhenUnknown=False)` -> `ChargeLimitDecision(send, saveNow, saveOnSuccess, settled, reason)` (a namedtuple). It is pure.
  - `send` is the limit to send, or None.
  - `saveNow` is a save for a no-send outcome (restore that adopts, already at target).
  - `saveOnSuccess` is the save after a successful send.
  - `settled` is True when nothing needs sending and the outcome is final, so the channel latches its dedupe flag. It is False for "unknown, decided nothing" and for pending sends.
  - Invariant (tested): `saveNow` and `send` are never both set. Neither channel saved before a send, so no pre-send save was introduced.
- `telemetryChargeLimit(master, vin)` reads attributes only. It returns the limit pushed by a live telemetry module (syncSource != "TeslaAPI", a positive non-bool int), or None. It replaces `PresenceSources.telemetryLimit`, which is deleted.

## Where the two copies disagreed
1. **Hand-set adoption on apply (BLE's behaviour kept, not TeslaAPI's code).** TeslaAPI adopted a hand-set limit only on a restore. On an apply with `current != lastApplied`, it saved the stale `outside`. BLE adopted on both. The brief lists adoption as a rule, and step 4 removes the arrival handler's adoption, which had covered API cars. Following TeslaAPI's code here would regress API cars. The end state is unchanged. Before: the handler saved (80, 70), then the apply saved (80, 50). After: the apply alone saves (80, 50). Tested in test_teslaapi_presence (`test_hand_set_limit_is_adopted_on_apply`).
2. **Unknown current limit: parameterized, not unified.** TeslaAPI sends nothing and doesn't latch ("could not read the current limit; nothing sent"). BLE sends anyway: on an apply it saves (saved outside, or the target if nothing is saved), and on a restore it sends the saved outside. The parameter is `sendWhenUnknown` (TeslaAPI False, BLE True). Both modes are table-tested.
3. **Restore success save (TeslaAPI wins).** BLE used to `removeNormalChargeLimit`. It now saves (outside, -1) as TeslaAPI does. The same applies to "restore, already at normal". Knock-on: the entry now survives, so BLE's pre-wake "no saved limit" skip no longer short-circuits a following policy-wide restore. To keep that cheap, BLE now latches its dedupe flag (True, -1) on a successful restore instead of popping it, which matches TeslaAPI's `stopTryingToApplyLimit = True`. Tested: a restore followed by a policy-wide restore runs no command. Tests that asserted the entry was removed were updated, and so was the departingHandler comment. The departure and departing handlers already treat lastApplied -1 as nothing held. A per-VIN restore after an arrival reset (when the policy has no limit) would otherwise wake the car and read it, and if the read failed it would resend the normal limit. So BLE's pre-wake gate now also skips a restore when lastApplied == -1 (87a4dc9, tested). departing-report.md describes the old removal as an implementation detail; the spec does not require it.

## Other behaviour and log changes
- BLE prefers a live telemetry limit over its `state charge` read, and skips the read when it has one. The lookup is wrapped in try/except, so a failing lookup falls back to the read. The wake is unchanged.
- Log wording:
  - TeslaAPI's restore outcome for a hand-set limit is now "set by hand to N%; nothing to restore" (it was "already at N%"). One test was updated.
  - BLE's no-send outcomes log "Charge limit for VIN: <reason>".
  - BLE's sends log "Set/Restored VIN to charge limit N% (<reason>)". This replaces the separate "adopting it as the normal limit" and "Not restoring ..." lines.
- Arrival: `onArrival(vin, currentLimit)` keeps its signature, and `currentLimit` is unused. `VehiclePresence(limitLookup=...)` is removed, and pushed arrivals carry None again. Departures and departureHandler are unchanged.
- BLE keeps its pre-wake restore gate (nothing saved, and now also lastApplied -1). It avoids I/O; it is not a copy of a rule. With a known current limit, the rules would reach no-send there anyway. The difference is that the record is not re-saved as (current, -1).

## Tests
- Full suite: 871 passed, 1 warning (pre-existing). The baseline was 830.
- Added: 47 rules and helper tests, 2 TeslaAPI tests, 5 BLE telemetry tests, and a BLE restore-then-policy-restore dedupe check.
- Removed or merged: the presence fill-in tests (limitLookup), the arrival-adoption tests, and the PresenceSources telemetryLimit tests (now covered by the helper tests).
- test_vehicle_presence.py ran 5 times: 102 passed each time.
- `black --check` is clean.

## Concerns
- **A stale telemetry limit on a BLE restore can skip the restore.** This now applies to BLE as well as TeslaAPI. If TeslaMate still shows the pre-set normal (say 80) after we set 50 over BLE, a restore sees current 80 != lastApplied 50. It reads that as hand-set, saves (80, -1) and sends nothing, so the car stays at 50. TeslaAPI already had this exposure through update_charge. The user asked for telemetry to be preferred, so it is implemented as asked, but this is the main risk. A mitigation, if wanted: on a restore, ignore the telemetry value and do the BLE read; or only trust telemetry newer than our last set.
- The same staleness on an apply adopts a stale value as normal. This is usually harmless when the stale value is the old normal.
- On the TeslaAPI path, the adoption on apply is new behaviour. It is the intended replacement for the arrival handler's adoption, but it also applies to policy-wide applies.
- Adoption is still saved only after a successful send. If the send fails and the next read fails too (BLE unknown path), the hand-set value is lost for that apply. This is the pre-existing BLE behaviour and a possible follow-up.

---

# Follow-up: stale telemetry on a restore (concern 1)

Commit: see the git log entry "A restore reads the car live when telemetry shows a limit not ours".

- `ChargeLimitRules.needsLiveRead(limit, telemetryCurrent, saved)` is pure. It is True only for a restore while we hold a limit (hasSaved, lastApplied != -1) when telemetry shows something other than lastApplied. Telemetry equal to lastApplied is trusted, so the restore is sent with no read. Applies keep preferring telemetry.
- TeslaBLE: when the check is True, the telemetry value is dropped and the BLE `state charge` read decides. If that read fails, the BLE unknown-current restore applies (it sends the saved normal).
- TeslaAPI: when the check is True and the vehicle's syncSource is a telemetry module, it calls `update_charge(allowBle=not remoteOnly, forceLive=True)`. `forceLive` takes the normal live path even while telemetry is live: BLE first unless remoteOnly or api_only, then the API, with `statusDeferral` cleared so the API really queries. A failed live read means TeslaAPI's unknown behaviour: nothing is sent and the dedupe flag is not latched.
- Tests:
  - rules: a table for needsLiveRead.
  - TeslaAPI:
    - stale 80 / ours 50: live read, restore sent;
    - live read finds a hand-set 70: adopted, nothing sent;
    - telemetry equals ours: no read, restore sent;
    - remote-only: the live read runs without BLE;
    - the live read fails: nothing sent;
    - an apply still uses telemetry;
    - `update_charge(forceLive=True)` reads over BLE despite telemetry, and over the API past the deferral.
  - TeslaBLE:
    - stale 80: BLE read, restore sent;
    - hand-set 70: adopted, nothing sent;
    - telemetry equals ours: no read;
    - the read fails: unknown-current restore.
- Full suite: 888 passed, 1 warning (pre-existing). test_vehicle_presence.py passed 102 on each of 5 runs. `black --check` is clean.
- Remaining note: the forced API read on a remote-only restore is one `vehicle_data` GET, which doesn't wake the car. If the car is asleep it fails, and TeslaAPI then sends nothing for that attempt. That is the same as any other failed read on that path.
