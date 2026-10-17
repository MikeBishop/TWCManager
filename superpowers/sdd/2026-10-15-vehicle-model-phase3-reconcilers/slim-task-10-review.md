# Slim Task 10 review: consolidate the command stack

Reviewed d98d643..846349b in `scratchpad/wt-vm3` against slim-task-10-brief.md, preflight-r4.md and these rulings: the runner stays its own module; Reconciler.py stays under 600 lines; gaps are 10 s, and 15 s for amps; at most one re-arm per desire, so at most 4 paid sends. Line numbers are at 846349b.

**Suite:** `tests --ignore=tests/API --ignore=tests/integration`: 1666 passed, 1 xfailed (this matches the report).

**Scratch evidence:** the scenario tests were run outside the worktree, in `scratchpad/review10/`. That directory holds:
- `base/`: d98d643 extracted;
- `fix/`: 846349b plus the one-line I1 fix;
- the test files `sleepy.py` and `test_zz_review10_scratch.py`.

The worktree is clean.

## Verdicts

- **(A) Spec compliance: PASS, with one deviation that has been ruled on.** Every interface, deletion and test in the brief is present. The extra c4 clause in 846349b (Concern 1) goes beyond the brief; it is ruled on below.
- **(B) Quality and cost safety: NOT YET. Two Important findings.**
  - No path sends unbounded paid calls. I verified the ≤4 cap holds on every re-arm trigger.
  - However, a lowered limit can be skipped by a start: I1, which is Concern 2 surfacing through Concern 1's clause.
  - A start can stall forever on a car that BLE is not paired with: I2.

Counts: **Critical 0, Important 2, Minor 6.**

---

## Spec compliance checklist

| Brief item | Status | Evidence |
|---|---|---|
| Runner stays a module, with `runAttempt(reconciler, attempt)`, `checked`, `_tagged`, `writtenValue`, `entryKey`, `isStop`, `_call` | ✓ | Run.py:56-205 |
| Calls `beforeWrite/afterWrite` directly: no hook lookup, no lazy import, no `isinstance` | ✓ | Run.py:148, 200 |
| `Workers`, `RateLimits`, `_reconcilerParts` gone | ✓ | grep finds them only in the negative test, test_reconciler_queues.py:393 |
| `_workerOf` kept until 13b (M2) | ✓, renamed to public `workerOf` because Reconciler uses it | Run.py:95; Reconciler.py:212 |
| The reconciler owns `ble`/`cloud`, with `submit`, `cancel`, `start` (queues, then the thread), `drain` and `_run` | ✓ | Reconciler.py:177-231 |
| Stale-desire guard | ✓. It reads `reconciler.desired`, which is the same object as `master.desired` | Run.py:116 |
| `DesiredStore.changed` and `VehicleRegistry.removed` are single callables, called outside the lock | ✓ | Desired.py:217, 242-248; VehicleRegistry.py:54, 125-132 |
| VCQ loses `inline`, `_entries` and `summary` (and the test-only `pending`, `busy` and `_running`) | ✓ | VehicleCommandQueue.py diff |
| `RateLimit`, `Declaration.rateLimit`, `FLEET_COMMAND_LIMIT`, `CHARGE_SWITCH_LIMIT`, the WC VINs limit and `_allowed/_calls` deleted | ✓ | Capability.py, TeslaAPIProviders.py:31, HomeAssistantProvider.py, WallConnectorVins.py |
| `EDGE_MIN_GAP = 30.0` in `due()` | ✓ | WallConnectorVins.py:34, 83-88 |
| `MIN_SEND_GAP = {CHARGE_LIMIT: 10, CHARGING: 10, AMPS: 15}` in `plan()` | ✓ | Reconciler.py:70, 310-315 |
| `lastSentAt` survives `newDesire` and is stamped for every outcome not in NOT_SENT, even a replaced desire's (I5) | ✓ | Desired.py:129-143, 366-370 |
| `reachedCar` scans every source and uses exact `LIVE_READ_SOURCES` | ✓ | Reconciler.py:73, 84-93, 125-131. The source names match the Sources.py names (`TeslaBLE`, `TeslaAPI`) and Telemetry's class name |
| `rearmed` flag, reset in `newDesire`, shared by reached-car, ride and charging | ✓ | Desired.py:125, 142; Reconciler.py:395-405 |
| c4: all declared providers excluded, readiness ignored (M11); `paidSends>=2 and paidReached`; `_REFUSALS` | ✓, plus the 846349b clause | Reconciler.py:480-496 |
| `debugCommand` reads `master.reconciler` | ✓ | Order.py:192-223 |
| Tests: rename, `InlineQueue`/`inline`, the 3 RateLimits tests deleted, every listed new test added | ✓ | test_reconciler_queues.py, reconcile_helpers.py, test_limit_reconciler.py:405-519 |
| Reconciler.py < 600 | ✓ 577 | |
| Commit message | ✓, the brief's Step 5 text plus a body | 44c4ddb |

`test_protocol.py` and `test_twcmaster.py` were on the brief's update list but were not touched. Neither references a removed name, and both pass.

---

## Rulings on the implementer's concerns

### Concern 1: limit spent when `paidSends and rearmed and not paidRetryDue`

**Keep the clause, but it is safe only together with I1's fix.**

With I1 fixed, the re-armed send is a full attempt. If a start is wanted, it carries the start's wake. Once that attempt and its blind retry have gone, every paid path for the desire is used up (the ≤4 cap). The only other option is to hold the start until the value changes, which is the stall 846349b fixed.

**Without I1's fix, the answer to "can it start charging past a limit that could still be delivered" is yes.** Both post-re-arm sends go out blind, the limit never rides a wake, and then the clause releases the start (I1).

Two further notes:
- After I1, one residual remains: the cap can be spent by a reached-car or charging trigger *before* a start is wanted. A later start then charges on the old limit. That follows from the 4-send ruling; see Minor M2.
- The M11 edge case the implementer flagged (the rearmed case no longer holding for a declared-but-unready BLE) is harmless, because free BLE sends are not capped. It is also moot given I2: BLE readiness is claim-based, not radio-based.

### Concern 2: the re-arm does not reset `paidRetryDue`

**This must change. See I1.**

### Concern 4: every sent outcome, including UNSUPPORTED and REFUSED, stamps MIN_SEND_GAP

**It complies with the brief and is cost-neutral. I recommend narrowing it (Minor M1).**

An EXCLUDING outcome changed nothing on the car, and it already excludes that provider, so not stamping it cannot cause a repeat. Stamping only delays the fallthrough.

Verified: with BLE answering UNSUPPORTED "no claim", there is no Fleet stop at t+1 s, and the Fleet stop goes out at t+10 s. Under the derating rule a 10 s stop delay is tolerable, but it buys nothing.

Use `sent and outcome.kind not in EXCLUDING` for the stamp. I5 is kept, because a start in flight that returns DONE or UNREACHABLE still stamps.

### The other concerns

- **3: re-arm timing.** Accepted. The cap holds at 4.
- **5: retained Telemetry redelivery.** Accepted. It is bounded by the cap.
- **6: report normalization.** Accepted. `_deliver` and `_logFailure` log a raising report.
- **7: lib delta.** See the Lib delta section.
- **8: Task 11 wiring.** Accepted.

---

## Important

### I1: A re-arm keeps `paidRetryDue`, so the re-armed sends go out blind. A `ride` re-arm never wakes, and since 846349b the start then goes with its own wake while the lowered limit is never delivered.

**Evidence.**
- `Reconciler.py:395-405`: the re-arm sets `paidSends = 0` and `rearmed = True`, but leaves `paidRetryDue` as it was.
- `Reconciler.py:437`: `blind = p in paid and rec.paidRetryDue`, so `wake=False` and `maxAge=None`.
- `Desired.py:377-381`: the blind send's own failure sets `paidRetryDue` again, because `paidSends == 0` at that report.
- So when a first send fails retryably without a wake (a lower, or any attempt whose start is wanted later), then:
  - both re-armed sends are blind;
  - `_limitSpent` (Reconciler.py:491-493) then counts the limit as spent;
  - the start goes with its own wake.

**Reproduced** with a sleepy Fleet car that answers 408 until it is woken (`review10/sleepy.py`). The car has limit 90; the steps are: lower to 50, then start 30 s later.

| Version | Calls | Final limit |
|---|---|---|
| HEAD | `setChargeLimit, setChargeLimit, setChargeLimit, wake, startCharging` | 90: charges past the lowered limit |
| BASE | `setChargeLimit` ×9 in 40 min, never a wake, start blocked forever | 90 |
| HEAD + fix | `setChargeLimit, wake, setChargeLimit, wake, startCharging` | 50 |

BASE had the same flaw, unbounded and stalled. The cap and 846349b turned it into a bounded but wrong outcome.

**Fix.** Add `rec.paidRetryDue = False` in the re-arm block (Reconciler.py:404-405). This is one line. With it, test_limit_reconciler, test_reconciler_queues and test_outcome_desired all pass (124 tests).

The cap still holds at 4: a full send, then its blind retry.

Add a paid-counted test: "a lowered limit that failed once, then a start, rides the start's wake". Use the sleepy-car shape: expected calls `[set, wake, set, wake, start]`, limit 50.

### I2: c4's "every declared provider excluded" counts a provider that can never serve the car, so the start stalls forever. M11's premise does not hold for BLE.

**Evidence.**
- `Reconciler.py:485-488` uses `providerOrder.ordered(SET_CHARGE_LIMIT)`. That list is global, not per vehicle (Order.py:57-72).
- `TeslaBLEProvider.ready` (TeslaBLEProvider.py:50-55) is `"TeslaBLE" in vehicle.claims`. Readiness is the pairing claim, not the radio.
  - A briefly down radio leaves BLE *ready*: it stays a candidate, fails UNREACHABLE and is never excluded. So the M11 hold protects nothing real.
  - A car BLE is not paired with has BLE declared and never ready, so it is never excluded.
- Then:
  - on a BLE install, a second car that is not paired whose limit provider is REFUSED or UNSUPPORTED has its start held forever;
  - `paidSends` is 1 with `paidReached` True, so the paid clause does not apply;
  - the excluded provider leaves no candidate, so there is no re-arm.

Reproduced: BLE with `readyFor=False` plus HA (`REFUSED "403"` on the limit, DONE on the start). After 24 h of passes, the calls are `['setChargeLimit']` and there is no start (`review10/fix/tests/unit/test_zz_unpaired.py`). test_limit_reconciler.py:490 pins this same state as intended behaviour, but only over 5 minutes.

**Fix.** Compute the "all excluded" set over `providerOrder.candidates(vehicle, SET_CHARGE_LIMIT)`, which is readiness by claim. Pass `vehicle` into `_limitSpent`; `plan` has it.
- This keeps M11's real intent: a paired BLE with a down radio is still a candidate and still holds the start.
- It drops a provider that cannot serve this car.
- Rewrite the M11 test so the paired BLE answers UNREACHABLE (radio down), and expect the start to stay held. Add "an unpaired BLE does not hold the start of a car HA refused".

If the brief's literal "readiness ignored" must stand, then bound the hold instead. For example, count the limit as spent once `now - limit.lastOutcomeAt >= PAID_AFTER[CHARGE_LIMIT]` while the only providers not excluded are unready. Either way, record the change to M11 in the ledger.

---

## Minor

**M1: The gap is stamped for EXCLUDING outcomes** (Desired.py:366-370). See the Concern 4 ruling. Use `sent and outcome.kind not in EXCLUDING`. Add a test: "BLE no-claim UNSUPPORTED falls through to Fleet the same pass, or the next one, without waiting 10 s."

**M2: A re-arm spent before a start is wanted means the start charges on the old limit.**
- Sequence: a lowered limit, Fleet 408 ×2, Telemetry shows the car awake (re-arm), 408 ×2, then a start. Calls: `set ×4, wake, startCharging`, and the limit stays 90 (scratch `test_rearm_consumed_before_start_then_start_skips_limit`).
- This is the price of the ≤4 ruling.
- Record it in the ledger and Decision 15 as accepted, so that Task 14's parity rows do not rediscover it.

**M3: The I4 trigger counts `"Complete"` as charging.**
- `_chargingSince` (Reconciler.py:471-478) uses `CHARGING_LIKE`, which includes `"Complete"` (Rules.py:17).
- A car that has finished is not drawing power and may be asleep. Fresh TeslaMate or HA republishes of "Complete" would spend the one re-arm on up to 2 likely-UNREACHABLE commands ($0.002).
- Use `{"Charging", "Starting"}` for this trigger, to match its comment ("a car drawing power is awake").

**M4: Stale comments.**
- Reconciler.py:389-390 still says "At most two paid sends per desire". It is now two per arm and two arms, so four.
- :402-403 "Two more sends" is fine, but should say "at most".

**M5: Report arithmetic.**
- The report's lib table says Reconciler.py is +114 (472 → 577). That span is **+105**, and only +105 makes the table sum to −139.
- The −139 total is correct (`git diff --shortstat`: 292+/431−).
- Rules.py's +20 is code moved out of Reconciler, so new code in Reconciler is about +125: queue plumbing about 50, report and logging about 15, and c2/c4/I4/gap with comments about 60.
- No added code duplicates something that should have been deleted:
  - `_newer` replaced the `reportedBy` loop;
  - `noteOutcome` lost `freeProvider`;
  - `summary` went.
- `newerReading` remains only for the settledAt reopen, and its TWC stand-in branch is distinct from `reachedCar`.
- The shortfall against −200 is explained by the ruling that keeps `runAttempt` in Run.py.

**M6: An overlong comment line.** VehicleCommandQueue.py:15 is 97 columns; the reworded comment was not reflowed.

---

## Hunt results (no finding)

- **Unbounded paid calls.** None found.
  - Paid sends are capped per desire at 2 per arm × 2 arms: `paidSends < 2` at Reconciler.py:406-410 and `rearmed` at :398.
  - Each attempt carries at most one wake.
  - The reads before a write are bounded by the attempt count and maxAge.
  - Flips are new desires, paced by MIN_SEND_GAP (10 s; amps 15 s) as ruled. BASE's Fleet 50/60 s window was looser.
  - The wall-connector VIN polling is free and spaced 30 s on edges.
- **Lock order and I/O under a lock.**
  - `_notify` and `_removed` call out after releasing their locks.
  - `report` → `noteOutcome` takes only the store's leaf lock.
  - `_save` (settingsLock) runs from `plan` with no lock held, and from `beforeWrite/afterWrite` outside any provider call, so `_bleLock` is not held.
  - `InlineQueue` sets `_busy` under `_cond`, then runs outside it.
  - `Vehicle.reported` returns a copy made under the field store's leaf lock.
- **Missed stop.**
  - `runAttempt` skips the stale guard for stops.
  - `cancel` removes only pending stops, as specified.
  - A closed queue still takes stops while its thread is live.
  - The gap delays a stop by at most 10 s after a send, which is accepted under the derating rule.
- **Start stall.** Only I2. The 846349b stall is fixed: the ride-wake-failed test passes, and the re-arm cap leaves no other reviver-less hold.
