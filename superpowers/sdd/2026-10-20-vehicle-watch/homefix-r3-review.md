# Review: homefix round 3 (phase5 d370287b, phase6 004f2235)

Verdict: APPROVED. There are no Critical or Important findings, and the Minor items below are optional.

## 1. Rule
- `learnHome` (Presence.py) refuses when `lat.source != "TeslaBLE" and lat.at < max(plugIn mark, twcVin obs time)`.
  - It uses the observation's own time, with no slack. The reference is the raw `latest("twcVin").at`, not `twcVinAt`, so it is the VIN-read time.
  - BLE is exempt. The `HOME_FIX_MAX_AGE` check by GPS time is unchanged.
- Both call paths go through `learnHome`:
  - TWCMaster:1632 runs after `observeTwcVin` (:1576), so the VIN-read time is already stamped.
  - The `Presence.observe` lat/lon branch (:124-125) is unchanged and reaches the same gate.
- Consequence, which the implementer also reported: at the VIN read, no non-BLE fix can qualify, because its read time is earlier than the VIN-read time. After naming, a cloud fix outside the radius first sets `outside`, which makes `twcVinAt` return NEVER, so `learnHome` is not reached. A cloud fix can therefore only set home when no home exists. It never moves an existing home. This is consistent with the user's rule as implemented, and the test `test_twc_vin_is_overridden_by_a_newer_drive_start_or_outside_fix` still passes.

## 2. Earlier Important findings
- I1 and I2 no longer apply. `_fixAt`, `PARKING_SLACK`, GPS-dated `_fix()` and the GPS-dated `outside` mark are gone (grep is clean). `_fix` and `outside` are untouched.

## 3. Phase6 parity
- `git diff 8e2afe2f 004f2235 -- Watch.py` is empty.
- Presence.py differs from 8e2afe2f only by the 8-line `learnHome` change.
- The lib diff e976d6d0 to 004f2235 (the phase6 tip before this commit) is exactly those `learnHome` lines. Nothing in the lib diff comes from the reverted GPS dating.

## 4. Tests
- test_presence.py and test_twcmaster_vin_confirmation.py: 112 passed on phase5. The presence, watch and vin subset passes on phase6 (339).
- Mutations I ran, one at a time:
  - Rule removed: the bug test fails.
  - BLE exemption removed: the new BLE test and the changed VIN-confirmation test fail.
  - GPS time used in place of the read time: the read-30-s-after test fails.
  - VIN-read term dropped: the bug test fails.
  - plugIn term dropped: SURVIVES. See M1.
- The changed VIN-confirmation test now uses a BLE fix, which keeps its point (learning without I/O). Its ordering is odd but sound: home is set to the fix's own position first, then moved wrong, then moved by the VIN read.
- The old BLE test and the read-after test pass without the fix, as the implementer disclosed. The new BLE test guards the BLE exemption.

## 5. Comments, CHANGELOG, docs
- No history, phase IDs or ruling IDs were found in the diff.
- CHANGELOG, Settings.md and PolicyCustomization.md add one accurate sentence: "never moves home" for a read from before the drive home. None claims that a cloud position moves an existing home.

## Minor (no action required)
- M1. The plugIn half of `max(...)` is not distinguished by any test. In practice `twcVin` is re-stamped at each Gen2 plug/charge restart, so it is almost always at or after the plugIn mark. Keep it, since the rule states it, or add a Gen3 or re-plug test.
- M2. Vehicle_HomeAssistant.md, and loosely the "set or moved ... when a TWC reads the car's VIN" sentences, imply that a non-BLE fix read after the car reached its TWC can move home at the VIN read. At that call it cannot (see section 1). The parenthetical "unless it came over BLE, read after the car reached its TWC" is true but suggests more than it does. Consider "only a BLE position moves an existing home".
- M3. The new `learnHome` comment is a fragment: "may be from before the drive home: its plug-in, or the VIN read (...)" has no period and an unclear antecedent. Suggested wording: "A fix not read over BLE must be read after the car reached its TWC (the later of its plug-in and the VIN read; a Gen2's plug-in mark stays on the anonymous session the VIN read replaces), else it may predate the drive home."
