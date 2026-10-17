# Slim Task 12a re-review 1 (fix round 1)

Reviewed: `c563d70..5a42a6d` in `scratchpad/wt-vm3`. Read-only. Line numbers are at 5a42a6d. The tree was left clean: each mutation was restored and the probe file deleted, and `git status` is empty.

## Findings

| Finding | Addressed? | Does the test fail without the fix? |
|---|---|---|
| C1 (wake before read) | Yes | Yes, two ways. With `wakeFirst = False`, the C1 test fails. With the `wakeOutcome` cache refresh removed, the C1 test also fails. |
| C1 backstop (`unread >= 2`) | Yes | Yes: `test_a_limit_that_stays_unreadable_stops_holding_the_start` fails. |
| I1 (anonymous fan-out, main parity) | Yes | Yes: `test_an_anonymous_point_fans_out_as_main_did` fails. |
| I2 (no cloud start in mode 2) | Yes | Yes: `test_mode_2_starts_no_paid_provider` fails, and so do the table and outcome tests. |
| I3 (`minChargeLevel`) | Yes | Yes: `test_a_car_below_min_charge_level_is_not_stopped` fails. |
| I4 (offer flaps) | Yes | Yes, two ways. With `keep=False` in TWCMaster, the flap test fails. With the store's `keep` branch disabled, it fails too. |
| M1 (comment) | Yes | n/a |
| M2 (token-state log) | Yes | Yes: the test fails. |
| M3 (rejected VIN) | Yes | Yes: the test fails. |
| M4 (#591) | Yes | Yes: the test fails. |

Suite at 5a42a6d:

- The touched test files: 147 passed.
- `tests/unit`: 1666 passed.
- `tests/unit`, `scenarios`, `integration` and `pid_file` together: 1670 passed, 2 skipped and 1 xfailed. The `tests/integration` errors are pytest-timeouts waiting for a live server, which is environmental and unrelated to this change.

## Cost of C1, "wake before read on paid providers"

I probed with a real TeslaAPI and requests_mock. The probes were throwaway and are now deleted.

- **A wake only when the read is needed.**
  - `plan` returns early when the cached belief already satisfies the desire (`Reconciler.py:348`), so no attempt is made and nothing wakes.
  - `wake` is set only for a start, a limit raise over a *known* lower value, or a limit that rides a wanted start (`:458`).
  - Probes:
    - An awake car with a stale lower limit, raised: one free GET, then `vehicle_data`, then SATISFIED. No `wake_up` and no POST.
    - An awake start with a fresh "Stopped": one free GET, then `charge_start`. No `wake_up`.
  - Compared with c563d70, an asleep car whose belief is stale costs the same as before: the old path's read found nothing and then woke anyway. An awake car costs one extra free GET.
  - Nit (no action needed): wake-first runs before the in-run `satisfied` check. So a reading that lands between plan and run does not save the free check. It can save a paid wake only in the rare case where the car is asleep and its belief has just changed.
- **A stop never wakes.**
  - `allowWake` is False for a stop, and `ride` applies only to `CHARGE_LIMIT`.
  - Probe (stop to an asleep car whose state is "Charging"): `charge_stop` with no GET and no `wake_up`.
  - The fan-out does open a new cost, though: see N2.
- **A restore never wakes.** `allowWake` returns False on `restore`, and `ride` is gated by `not d.restore` (`:458`).
- **The free check and the wake hold.**
  - `wakeOutcome` always runs `is_awake` (the free GET, cached for 120 s) before any `wake_up`.
  - It never wakes blind (`lastVehicleAwakeKnown`), and it enforces `wakeDue` (the `wakeDelayMins` grace and the 1800 s hold after a failure).
  - The C1 test pins the GET-first order. The amps path never wakes a cloud car (`p.local or aspect != AMPS`).
- **The `wakeOutcome` cache refresh (`TeslaAPI.py:1461-1462`).**
  - It is set only when `wake_up` itself answered `state == "online"`, and it is stamped with the same clock that `is_awake` compares against. It cannot mark an asleep car online.
  - Residual (Minor N4): `is_awake` checks a telemetry "asleep" before the cache, with no age limit. On a TeslaMate install, a paid wake can be followed by a skipped read until TeslaMate catches up. The unread backstop bounds this.
- **I1 and I4 together.**
  - `_wantCharging` computes `keep` per fanned-out car, so a flap re-creates a desire, and with it a fresh paid budget, only for a car that has reported since its last send.
  - There is no per-flap broadcast storm, but see N3.

## New issues

### N1 (Important): in mode 2 the limit still rides a start that the cloud can no longer send, so it buys a paid wake

- **Where:** `Reconciler.py:404`, `:475-484` and `Run.py:147`.
- **How it happens.**
  - `_startWanted` checks the desire, `satisfied` and `handsOff`. It does not check whether a waking provider can deliver the start.
  - Under I2, the mode-2 start goes through Gen2TWC (`respondToSlaves`, free) and never through Fleet. But the Fleet limit attempt still gets `wake=ride`, and C1 runs that wake first.
- **Probe:** a Fleet-only car, mode 2, asleep, with the hold over. `setPolicyLimit(50)` plus a start gives a free GET, then `POST wake_up` (failed: asleep). Outcome: `unreachable "wake asleep"`. The re-arm through `ride` allows a second wake after RETRY and the 1800 s hold.
- **Cost:** up to $0.04 per limit desire.
- **Compared with main and c563d70:**
  - On main, a mode-2 start did not wake the car. `applyChargeLimit` woke it only for a raise over `lastApplied`.
  - At c563d70 this was NOT_SENT and cost nothing.
  - This contradicts the I2 ruling ("mode 2 must not add paid" starts or their wakes).
- **Fix (about 2 lines):** in `_startWanted`, also require a start candidate that would itself spend the wake: `any(not p.local and p.declares(WAKE) for p in providerOrder.candidates(vehicle, START_CHARGING))`. The ride's premise ("the same wake the start would spend") then holds.
- **Known side effect of the fix.** In mode 2, an asleep car with an unknown limit goes NOT_SENT "rules: could not read" twice, RETRY apart. Only then does `unread >= 2` release the Gen2TWC start, so `respondToSlaves=1` comes about 300–600 s late after a restart. That is the c4 design plus the ruled backstop, and it is bounded. Accept it; do not reopen it.
- **Test:** the probe above, asserting no `wake_up`.

### N2 (Important): the mode-1 fan-out stop sends a paid `charge_stop` to an asleep at-home car

- **Where:** `TWCMaster.py:215-227`, `Targets.py:44-57` and `Run.py:157-183`.
- **How it happens.** Take an at-home car on the list with no `chargingState` reading, for example after a restart. It gets a stop desire. The read (`is_awake`, free) finds it asleep and reads nothing, so `believed` is None and `beforeWrite` passes the stop through.
- **Probe:** an anonymous point plus a second listed at-home car that is asleep and unread. A stop gives `GET vehicles/{vin2}` (asleep), then `POST charge_stop`.
  - That is up to 2 × $0.001 per car per stop desire: the 408 is UNREACHABLE, so the blind retry follows.
- **Main:** `car_api_charge` did `if not vehicle.ready(): continue` (`main:TeslaAPI.py:786`). An asleep car got no stop command at all, so this is a main-parity cost regression.
- **Scope:** the same blind stop exists for a *named* car whose state is unknown, but that car is normally drawing power and so awake. The fan-out makes the case routine.
- **Second trigger.** N2 also covers a stale "Charging" belief: the belief is older than `maxAge` and the car has since fallen asleep. That case can hit a named car too.
- **Fix, about 3 lines.**
  - **Where:** the Fleet/Owner provider's `stopCharging` (`TeslaAPIProviders.py:145`). It already has `carapi`, and with it the cached free `is_awake`. Run.py should not read TeslaAPI's awake cache.
  - **What:** when the car is known not awake, return without a request.
  - **Outcome kind:** use a detail that `isNotSent` recognises, so `noteOutcome` neither counts a paid send nor stamps `lastSentAt`. Plain `SATISFIED "asleep"` would count as sent and burn the paid budget.
  - **Wait for a newer reading:** the stop should not re-poll every RETRY. Either use a SETTLED kind with a NOT_SENT detail (SATISFIED plus a new NOT_SENT entry such as "asleep"), so `settledAt` is set and the stop waits, or accept the H2 RETRY hold. The first is preferred.
  - **Why it is safe:** an asleep car is not charging.
- **Test:** the probe, asserting no `charge_stop`.

### N3 (Minor): `keep` has no age bound

- **Where:** `TWCMaster.py:235` and `Desired.py:294-296`.
- **What happens.**
  - `lastSentAt` is never reset, and records outlive plug sessions for a listed car. So a start withdrawn and re-desired hours or days later reuses an exhausted budget, provided no `chargingState` reading arrived in between.
  - Example: one failed wake ends the start's paid sends, and nothing re-arms without a reading. An asleep Fleet-only car can then stay unstarted across offer cycles until it reports by itself.
  - This matches the steady-state bound within one desire, so it is by design. But main retried a wake every 30 minutes.
- **Two edges.**
  - With a streaming source (Fleet Telemetry), each flap with a newer reading gets a fresh budget, spaced only by `MIN_SEND_GAP` (10 s). Main used a 60 s gate.
  - Option: `keep` only while `now - lastSentAt < PROBE_AFTER`, and require `RETRY[CHARGING]` since `lastSentAt` before a new budget.
- **Action:** park with a note, or a one-line bound.

### N4 (Minor): a telemetry "asleep" can mask a successful wake

- **Where:** `TeslaAPI.py:1921-1935` versus `:1461`.
- **What happens:**
  - `is_awake` trusts a telemetry "asleep" before the refreshed cache, so the read after a paid wake can be skipped.
  - That gives "could not read". The backstop releases the start after 2.
  - The start's own wake is held for `wakeDelayMins`, after which it may pay again if TeslaMate has not updated.
- **Cost:** rare, and bounded.
- **Action:** park.

## Other checks

- **Locks.**
  - New heartbeat-thread work: `withdrawStartCharging`, `_chargeTargets` and `broadcastVehicles`.
  - These take only registry reads, provider `ready()` (claims, slots and entity flags, with no I/O), and `DesiredStore` `record`/`set`/`clearIf`.
  - Each takes the store or registry leaf lock alone, and the notify runs outside it.
  - `isPending` (M3) is a registry leaf lock.
  - No nesting and no I/O under a lock.
  - `keep` is computed from a record read outside `set()`'s lock. That race is benign: the worst case is one new desire, or one kept record.
- **Tokens.** No token appears in any new log. `_noTokenReason` logs fixed reason strings, and the wake logs use `vehicle.name`.
- **Proportionality (+125 lib).**
  - TWCMaster +31 net (fan-out, `keep`, withdraw).
  - Desired +20, of which about 10 is black-formatting the `set()` signature.
  - Run +15 (the wake step factored into `_wake`, which is reasonable).
  - TeslaAPI +18 (the M2 log).
  - Targets +16, Reconciler +13, and Gen2TWC/Provider/Suppressions +14.
  - Each restores main behaviour that a ruling demanded. There is no duplication, and the task's net is still −852. Proportionate.
- **Broadcast per heartbeat.** `withdrawStartCharging` now runs `broadcastVehicles` on every heartbeat while the offer is below the minimum, for an anonymous point. It is CPU only: a registry scan plus `ready()`. It is acceptable.

## Verdict

**NOT APPROVED.** Every original finding is fixed and pinned by a test that fails without its fix. Two new Important cost issues need fixing first, each in about 2–3 lines: N1 (the mode-2 ride wake) and N2 (the fan-out stop sends `charge_stop` to asleep cars, where main skipped not-ready cars). Park N3 and N4 with notes.
