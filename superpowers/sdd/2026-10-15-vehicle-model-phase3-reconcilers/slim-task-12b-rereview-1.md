# Slim Task 12b re-review 1 (fix round 1: 9d3fb64..889e510)

Worktree `scratchpad/wt-vm3` at 889e510. Read-only: every revert, mutation and probe was restored with `git checkout` or deleted, and `git status` is clean.

Suite at 889e510: **1657 passed, 1 xfailed** (`tests --ignore=tests/API --ignore=tests/integration`), matching the report.

**Verdict: NOT APPROVED.** All the code findings are fixed and pinned. One new Important finding (N1) reopens the cost cap that I2 was meant to set.

## 1. Code findings: is each fix reverted and its test failing?

| Finding | Fixed | Result with the fix reverted |
|---|---|---|
| I1 (mode-3 lift once per range entry) | Yes. ChargingPoint.py:176-191: the lift is gated on `vehicleRateRaised` in both modes, and the below-floor branch resets the flag. | Reverting ChargingPoint.py fails `test_mode_3_lift_goes_once_per_range_entry_even_when_the_car_clamps_it`, `test_user_changed_amps_after_a_lift_are_left_alone[3]` and the M4 test. Dropping only the below-floor reset fails the "exactly one more lift" leg. |
| I2 (VIN-less fan-out) | Yes, in the ruled shape. TWCSlave.py:98-140 (`_anonCars`, `_ampsKeys`, `_clearCarAmps`). | Reverting TWCSlave.py fails 4 tests: the plugged-only/`vehicles[0]` test, the mode-1 lift test, the leaves-the-set test and the M2 test. **But see N1.** |
| I3 (read-only INFO hint) | Yes. `TeslaAPI.noteReadOnly` keyed on `fleetSlot.changes`, called from `FleetAPIProvider.available` for COMMANDS. | Removing the call fails both `TestRefusalHint` tests. |
| M2 (heartbeat withdraws its rate below the minimum) | Yes. TWCSlave.py:810-812. | Removing the call fails `test_heartbeat_withdraws_its_rate_when_the_offer_drops_below_the_minimum`. |
| R9 (no exception text in logs) | Yes. VehicleCommandQueue `_frames()` (file, line and function only); the dying worker is logged, not re-raised. | Reverting VehicleCommandQueue.py fails `test_a_raising_report_is_logged_by_type_name` and `test_a_worker_that_dies_logs_no_exception_text_at_any_level`. |
| Audit row 61 (HA at home and on a TWC) | Yes. Targets.py:49-53 matches main's `car_api_charge` (`at_home` plus `_is_vehicle_connected` via `getTWCbyVIN`), which I checked against origin/main. | Reverting Targets.py fails `test_an_anonymous_point_reaches_at_home_connected_home_assistant_cars`. |

## 2. Mapping table spot-check (15 mutations)

Each mutation targets the behaviour the row claims, and each was restored afterwards.

| Row | Mutation | Result |
|---|---|---|
| 12b PARTIAL 7, audit 63/68/69/71 (Fleet then HA) | `p = paid[min(rec.paidSends, …)]`: fall through to HA after a Fleet send | KILLED (5 tests) |
| Audit 77 (a read or rules outcome spends no gap) | `sent = True` in `noteOutcome` | KILLED (3) |
| 12b GAP 1 (POST timeout) | `COMMAND_TIMEOUT = 30` | KILLED |
| 12b GAP 4/5 (a request that never left: no refresh) | `refreshSlot(slot)` in the `RequestException` branch | **SURVIVED.** See N2. |
| 12b PARTIAL 2/3 (low rate) | resend after an unsettled first send | KILLED |
| 12b PARTIAL 2/3 | keep the first outcome and ignore the second | KILLED |
| 12b PARTIAL 5 (wake 401 refreshed at Fleet auth) | never refresh on "expired" | KILLED |
| Audit 56 (a stop during a live drain) | `if dead or self._draining:` | KILLED |
| Audit 28-32 (two-car isolation, real requests) | `_car()` returns the last-listed car | KILLED |
| 12b PARTIAL 6 (pairing and pairing_failed claimed) | skip claiming `pairing_failed` | KILLED |
| 12b PARTIAL 1 (garbage rate) | `get("charge_rate") or 0`, so null is accepted | KILLED |
| M6 (re-arm once per desire) | `not rec.rearmed` → `True` | KILLED |
| 12b GAP 6 (disabled HA, provider) | `HomeAssistantProvider.available` returns True | KILLED |
| 12b GAP 6 (disabled HA, checkCharge) | drop `not p.available(READ_CHARGE)` in `updateChargeAtHome` | KILLED |
| Audit 16 (a restore stamps the outside value) | no `noteWrite` after DONE | KILLED |

**Result: 14 of 15 killed.** One test asserts less than its row claims (N2). No test I read asserts nothing.

## 3. The Belief.py move (M1)

It is a pure move. The function bodies removed from Reconciler.py, together with `LIVE_READ_SOURCES` and `POWER_FLOWING_AMPS`, are byte-identical to Belief.py's bodies once the header comment and imports are set aside (checked with `diff`). Nothing in lib/ or tests/ imports or patches a moved name through `Reconciler`. VehicleEndpoint and TWCMaster now import from Belief, which fixes the layering problem M1 raised. Reconciler.py is now 515 lines.

## 4. New paid paths and caps

- **No new paid path.**
  - Row 61 reaches HA only for start/stop, under main's own condition.
  - `noteReadOnly` makes no HTTP call and records no error.
- **I1 lift: at most one per session.** It runs once per range entry. This is pinned by a Fleet test over one hour of readings (one `setAmps`). A mode-3 offer that oscillates around the floor lifts once per crossing. That matches main's reset at the `< 6` handoff, and the shared AMPS 15 s gap bounds it.
- **I2 fan-out: one paid send per plugged-in car, else a single `vehicles[0]`.** This holds only when every source's `chargingState` means plugged. **It fails when Home Assistant reports the car (N1).**
  - The `vehicles[0]` fallback is stricter than the ruling: the car must also be at home and unnamed. This is cost-safe.
- **No wake for amps.** `(p.local or aspect != AMPS)` is unchanged (Reconciler.py:376). The I1 and I2 tests assert the exact call lists, so they would see a wake.
- **Paid amps at least 15 s apart.** `MIN_SEND_GAP[AMPS] = 15` is unchanged. The lift and the distributor share one record.

## 5. Secrets

The reconciler's report path is clean at every level:
- The VCQ logs type names only; its DEBUG traceback is frames only.
- `report()` logs `outcome.detail`. Every detail is a code: HTTP status, `type(e).__name__`, Tesla `reason` (filtered to `[a-z_]{1,40}`, TeslaAPI.py:1257), BLE category, or a rules string.
- The new INFO hint carries no data.
- `WallConnectorVins.py:152` (`exc_info=True` at DEBUG) is on the read path. It is already parked for Task 13.

## 6. Locks and threads

- No new lock.
- `_anonCars`, `_clearCarAmps` and `broadcastVehicles` (with `getTWCbyVIN`) do registry and dict reads only, on the serial thread, with no I/O.
- `noteReadOnly` is a `logger.info` reached through `available()`. No caller holds `settingsLock` or `_bleLock` (Order.py takes none).
- The stated order holds: `_bleLock -> settingsLock -> registry leaf`, plus `vehicleListLock -> settingsLock`.
- No RS-485 I/O moved.

## 7. Size

**+78 lib** in this round:
- Belief.py move: +16 (header and imports).
- TWCSlave (I2 and M2): +30, against the review's estimate of about 15 plus 6.
- TeslaAPI (I3): +14.
- VCQ (R9): +10.
- Targets (row 61): +3.
- TeslaAPIProviders: +3.
- ChargingPoint and TWCMaster: +1 each.

Every line restores main behaviour or a ruled cap. This is proportionate. The task total is −742.

---

## New findings

### N1 (Important). An HA "Stopped" reading makes an unplugged car count as plugged in, so the VIN-less fan-out pays N× again

**Where:** TWCSlave.py:107-108, which tests `obs.value not in (None, "Disconnected")` on the latest vehicle-source reading.

**Cause:** HomeAssistant.py:164 maps HA's binary charging sensor to `"Charging"` or `"Stopped"`. So HA reports a car that is *not plugged in* as `"Stopped"`.

**When it happens:**
- 12b now refreshes HA on every checkCharge, alongside TeslaAPI (concern 4, GAP 7).
- HA observes into the same registry car by VIN.
- On the install that M8 and PARTIAL 7 design for (Fleet plus HA for the same car), HA's `"Stopped"` is usually the newest reading. It overrides TeslaAPI's or Telemetry's `"Disconnected"`.

**Probe** (a temporary test, now deleted; based on `anonTwc`):
- Setup: three unnamed at-home Fleet cars. Each reads `"Disconnected"` from TeslaAPI, then `"Stopped"` from HomeAssistant.
- Result: one hour of a fluctuating offer gives **720 paid `set_charging_amps`, 240 to each of the 3 unplugged cars**, which is about $0.72/h.
- The ruling: rate a car only when its latest reading shows it plugged in or charging; with none known, rate `vehicles[0]` alone, so 240 per hour at most.

**Same weakness, smaller impact:**
- BLE's enum `"Unknown"` and TeslaMate's `str(None)` = `"None"` also pass the `not in` test.

**Fix (2-4 lines):**
- Test a positive set, `{"Charging", "Starting", "Stopped", "Complete", "NoPower"}`, instead of `not in (None, "Disconnected")`.
- Count an HA reading as plugged only when it is `"Charging"`, because HA's sensor cannot tell "stopped" from "unplugged". One way is to read `v.reported("chargingState")` per source and skip HA unless its value is `"Charging"`.

**Test:** extend `test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0` with HA `"Stopped"` on VIN and VIN4 after TeslaAPI `"Disconnected"`. Assert that only VIN2 is rated and there are at most 240 sends.

### N2 (Minor). `test_a_wake_or_command_that_never_left_is_an_error_and_refreshes_nothing` does not test "refreshes nothing"

**Where:** test_provider_outcomes_cloud.py:275.

**Problem:** the `fleet()` fixture stores a Fleet token with no refresh token. So `slot.refresh()` returns `"not_configured"` without any HTTP call. A mutation that calls `refreshSlot(slot)` on every `RequestException` survives.

**Check:** with `api.storeToken(fleet_token(), "refresh-me")` added, the same mutation fails both cases.

**Fix:** add the refresh token to the test, which is a one-line change. The outcome leg (`ERROR "ConnectionError"`) is meaningful already.

### Notes (no action)

- **The `vehicles[0]` fallback uses registry insertion order.** After a restart, that is the persisted registry order, which may not be the order of TeslaAPI's list. It still picks one car at most, so the cap holds.
- **Mode 1 with two car members on one point now lifts only the first**, because the flag is set inside the loop. A point normally has one car.
