# Task 3 review (9733ec7..14ffaf2)

Reviewed in one pass from `review-9733ec7..14ffaf2.diff`, with focused out-of-diff reads for the named risks (listed below). I ran one probe test from the scratchpad, not the suite.

### Spec Compliance

- ✅ Spec compliant. Every file and step in the brief has its hunk. VehiclePriority: `applyChargeLimit`, `resetChargeLimitState`, `_dispatch` (VehiclePriority.py:85-226). TeslaBLE: `applyChargeLimit`/`resetChargeLimitState` (TeslaBLE.py:668-810). TeslaAPI: `car_api_charge` call at :719, `applyChargeLimit` at :892, `resetChargeLimitState` at :1446, `update_charge(allowBle)`. HomeAssistant: vin filter and no-op reset (HomeAssistant.py:569-631). TWCManager.py: the `checkArrival`/`checkDeparture` branches are gone. All four test files are present and match the brief verbatim. The implementation follows the brief's code exactly, so the findings below that sit in brief-supplied code are labelled **plan-mandated**.
- The commit trailer names Sonnet. Ledger ruling, not flagged.
- ⚠️ Cannot verify from diff: whether Task 7's VehiclePresence (1) refreshes `vehicle.atHome` before calling the TeslaAPI channel per VIN, and (2) can tolerate HomeAssistant returning `"success"` for a VIN it skipped (see Minor 1). `car_api_available(applyLimit=True)` (TeslaAPI.py:313-343) iterates every API vehicle, not just the target VIN. So a per-VIN arrival apply that sets `needToWake` can send an API `wake_up` to a *different* at-home vehicle whose `stopTryingToApplyLimit` is False. It also refuses to wake the target if its cached `atHome` is False. The controller should check this against the "Presence never calls wake_up over the API" constraint when Task 7 lands.

### Named-risk checks

- **(a) Policy-wide apply (vin=None) unchanged.** I compared the old and new TeslaAPI bodies line by line, read `getNormalChargeLimit` (TWCMaster.py:932-942, which returns `(False, None, None)` when nothing is saved), and ran a probe (below). The 60 s throttle is identical for vin=None (TeslaAPI.py diff L208), and the `atHome` skip is kept (L310). Differences found:
  1. The dedupe is lost for at-home vehicles with no saved limit, and for away vehicles with a saved `-1` (Important 1).
  2. `atHome` is no longer refreshed by `update_location()` inside the apply, so the vin=None path uses the cached value. This is intentional per the brief (`test_flags_are_gone` asserts it).
  3. The return value changed from `None` to `"success"`/`"error"`. Before, VehiclePriority always treated TeslaAPI as failed and fell through to the next module. Now a TeslaAPI success stops the fallback. This is an improvement, but it changes behaviour.
  4. `stopAskingToStartCharging` is now cleared only on a limit *increase*. It used to be cleared on any limit change for a saved vehicle.
  5. When `lastApplied == -1`, `outside` is now re-read from the car's current limit rather than the stale saved value (TeslaAPI diff L319-322). This is an improvement: it picks up a hand change made since the last restore.
  6. `car_api_charge` (TeslaAPI.py:719) now goes through the 60 s throttle. The old `checkArrival=True` bypassed it (Minor 2).

  TeslaBLE with vin=None is unchanged: `targets = list(vehicles.keys())`, the same loop and the same dedupe. The deleted `total_vehicles` is not referenced in `applyChargeLimit`; TeslaBLE.py:660 is `setChargeRate`'s own variable.
- **(b) remoteOnly never reaches BLE.** VehiclePriority.py `_dispatch` skips `"TeslaBLE"` when the caller asks it to, after the commandPolicy check. TeslaAPI passes `allowBle=not remoteOnly`, and `update_charge` gates both `get_charge_state` and `ble.wakeVehicle` behind `allowBle` (TeslaAPI.py ~1892). Other code on the path: `apply_charge_limit` (TeslaAPI.py:1945-2000) is API-only, and `ready()`/`is_awake()` are API-only. `car_api_available(applyLimit=True)` makes an API wake, never a BLE one, and is unreachable for a `-1` restore because `-1 > x` is never true. **Pass.**
- **(c) A per-VIN apply leaves the policy-wide state alone.** `lastChargeLimitApplied` and `carApiLastChargeLimitApplyTime` are both written only under `if vin is None` (diff L282-289). `test_per_vin_apply_leaves_policy_wide_state_alone` covers this. **Pass.**
- **(d) The `__getattr__` → `_dispatch` refactor.** The body of `_dispatch` matches the old closure line for line (diff L642-826). The only addition is the `skip` check, after `_skip_module_for_command` and before the retry calculation. With the default `skip=()` it is a no-op. `__getattr__` still proxies every undefined name. Only `applyChargeLimit` and `resetChargeLimitState` are now real methods. Callers: `VehicleCommandQueue._applyChargeLimitKwargs` (VehicleCommandQueue.py:22-30) passes only `limit`/`vin`/`remoteOnly`, which match the new signature. All four modules that define `applyChargeLimit` accept the `vin`/`remoteOnly` kwargs that VehiclePriority now always forwards (grep of lib/). **Pass.**

### Strengths

- Gating the per-VIN path on `vin is None` is clean. Throttle, policy state and the `atHome` filter all key off one condition, each with a comment explaining why (TeslaAPI diff L178-190, L284-289).
- The `_dispatch` extraction is a faithful move. The `skip` parameter is the smallest change that works, and the explicit `applyChargeLimit` documents why BLE is excluded.
- `resetChargeLimitState` fans out with exception isolation, and the self-skip is tested (test_vehicle_priority.py, `TestChannelInterface`).
- The `update_charge(allowBle=False)` test exercises the real `CarApiVehicle` with the wake fallback armed (`lastAPIAccessTime = 0`), so the BLE-avoidance assertion is meaningful.
- The implementer's report is accurate. The RED-count discrepancy (22 vs 23) is explained correctly, and both concerns it raises are real.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **TeslaAPI.py ~:937-939 and :967-970 — dedupe lost for at-home vehicles with no saved limit under the default `-1` policy. (Plan-mandated.)** `getNormalChargeLimit` returns `(False, None, None)` for an unsaved VIN, so `if limit != lastApplied` is always true and `stopTryingToApplyLimit` is reset on every apply. The new `limit == -1 and not hasSaved` branch then sets `stopTryingToApplyLimit = True` and `continue`s *without saving*. The next policy apply resets the flag again.
   - **Old behaviour:** `wasAtHome` gated the reset, and the `-1` path saved `(chargeLimit, -1)`. The vehicle was read once and then left alone.
   - **Probe:** three vin=None `-1` applies, one minute apart, against an at-home unsaved `FakeVehicle` gave `update_charge calls: 3, saves: 0`. The old code would give 1 read and 1 save.
   - **How a vehicle gets here:** TeslaBLE's successful restore *removes* the saved entry (TeslaBLE.py:763), and every newly seen car starts unsaved. An at-home car in that state is re-read every minute whenever TeslaAPI is reached: `api_only`, BLE failure, or the `get_vehicle_module` fallback. That means an `is_awake` API probe every 2 min and `vehicle_data` every 5 min (statusDeferral), or a BLE `get_charge_state` every minute under `prefer_ble`.
   - **Why it matters:** Fleet API data calls are billed, and polling `vehicle_data` can keep a car awake. This breaks named risk (a) "same dedupe".
   - **Second scenario, same root cause:** a saved vehicle with `lastApplied == -1` (after any restore) that is now **away**, while the policy moves to a real limit such as 70.
     - Loop 1: `70 != -1`, so the flag is cleared.
     - Loop 2: `update_charge()` runs (BLE read and wake fallback under `prefer_ble`, or `is_awake` plus `vehicle_data` under `api_only`), then `vin is None and not atHome` hits `continue`. The flag stays False.
     - This repeats every minute for as long as the car is away.
     - **Probe:** `FakeVehicle(atHome=False, stopTrying=True)` with `getNormalChargeLimit → (True, 80, -1)` and three `applyChargeLimit(70)` calls gave `update_charge calls: 3, stopTrying: False`.
     - **Why the old code didn't do this:** it re-latched through departure detection (`forgetVehicle` → `removeNormalChargeLimit`, with stopTrying left True), so the next apply saw `wasAtHome=False` and never reset the flag. Nothing on the new policy path ever re-latches an away vehicle.
   - **Root cause:** loop 1 clears `stopTryingToApplyLimit` for every vehicle where `limit != lastApplied`, and loop 2 then skips some of those vehicles without re-latching the flag.
   - **Fix (both parts needed; neither alone is sufficient):**
     1. Treat an unsaved VIN as "not holding a limit", e.g. `if limit != (lastApplied if hasSaved else -1):`. This fixes the unsaved-at-home case. Don't restore the old `saveNormalChargeLimit(VIN, chargeLimit, -1)` instead: a saved `-1` entry makes TeslaBLE treat `outside` as a restore target and resend it each minute (TeslaBLE.py:729-733 has no dedupe once the restore pops its flags).
     2. For `vin is None`, don't pay for a read on a vehicle believed away. Either gate the loop-1 reset on cached `atHome` when `vin is None`, or move the `vin is None and not vehicle.atHome` check above `update_charge`.
     - **Trade-off (controller's call):** with part 2, the policy path no longer refreshes `atHome` for away cars through the `vehicle_data` read. That is fine once Task 7 owns arrival, but it is a change from the old opportunistic read.
     - Moving the `atHome` check alone does **not** fix the unsaved-at-home case.
   - **Tests:** add one per scenario. Assert a single `update_charge` call (or none, for the away car) across repeated policy-wide applies.

#### Minor (Nice to Have)

1. **HomeAssistant.py:569-605 — the per-VIN apply still enforces `at_home`, and a no-op returns `"success"`.** With `vin` set, an away vehicle (or an unknown VIN) is skipped, `vehicles_processed == 0`, and the method returns `"success"`. VehiclePriority then stops the fallback, so a remoteOnly departure restore routed through HA at a higher priority than TeslaAPI is silently acknowledged and TeslaAPI never runs. The brief only required the vin filter, so this is a contract gap rather than a deviation. TeslaAPI documents that "with a vin, the caller has already decided", and HA doesn't follow that. Suggested fix: skip the `at_home` check when `vin` is given, and return `"error"` when `vin` is given and nothing was processed. At minimum, carry it as a Task 7 note.
2. **TeslaAPI.py:719 — the `car_api_charge` re-apply is now throttled. (Plan-mandated.)** The old `checkArrival=True` bypassed the 60 s gate, so a limit re-apply just before `charge_start` always ran. Now it returns `"error"` silently if any policy-wide apply happened in the last minute. That is mostly harmless, since the limit was just applied, but nothing documents the change.
3. **TeslaAPI.py ~:940-943 — `stopAskingToStartCharging` is now cleared only on a limit increase**, not on any limit change as before. Policy.py:202 and TWCSlave.py:590 still clear it elsewhere, so the impact is small. Worth a line in the commit or plan if it's intended.
4. **tests/unit/test_teslable_presence.py:5, 49-62 — unused scaffolding.** `import json` is unused, and `CommandRecorder.timeouts`/`locked_during_call`/`ble` are never asserted. The module docstring mentions `probePresence` and contact reporting, which this task doesn't add. This is presumably groundwork for a later task (plan-mandated text), but as committed it is dead code.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Named risks (b), (c) and (d) pass cleanly, and the refactor is faithful. The vin=None path loses its dedupe for at-home vehicles with no saved limit (probe-confirmed; the code is in the brief), which causes repeated per-minute reads and billable API probes in the common `-1` policy state. The same problem also leaves away vehicles with a saved -1 un-latched (both cases probe-confirmed). The fix needs both parts plus tests before building on this channel.
