# Task 5 report: the start/stop gates run on the control tick

**Status:** DONE. Branch `vehicle-model/phase4`, BASE 6b89f9fd. Not pushed.

Commits:
- `9e3e72c8` Decide TWC start and stop on the control tick
- `dc2609f5` Tighten the control tick's gate application (inlines the gate map, fixes the key-guard comment, applies the new comment rule)

## Implementation

- `lib/TWCManager/TWCSlave.py`
  - Deleted the gate block in `send_master_heartbeat`: the protocol-2 stop / cancel-stop / start / withdraw decisions plus the 116-line 2017 comment. The heartbeat now only builds the offer bytes, applies the override and sends.
  - Added `chargeGate(now) -> Optional[str]`, as in the brief. It returns `"stop"`, `"cancelStop"`, `"start"`, `"withdraw"` or None, and None when the TWC is not protocol 2, has no key, or has no offer yet. It reads `self.offer.amps`. BASE's unreachable `or reportedAmpsActual < 4.0` is gone. The rationale is cut to a 4-line rule comment.
- `lib/TWCManager/TWCMaster.py` `controlPass`
  - For each slave it has heard from, after `offerFor`: during the chargeStopMode-2 silence it `continue`s, so there is no stop-cancel (same as Task 4) and no gate.
  - Otherwise it runs the positive-offer cancel (unchanged from Task 4), then `chargeGate(now)`. On `"cancelStop"` it logs BASE's DEBUG "Don't stop charging TWC: … yet because: …" line, now with the timings as format arguments. It then maps the decision to `stopCarsCharging` / `cancelStopCarsCharging` / `startCarsCharging` / `withdrawStartCharging` with the key, through a local dict.
  - It applies a decision only when the key it read is not None. `chargeGate` reads `vehicleKey` again on its own, and `None` would reach every car (see Concerns).

## Behaviour changes (each sanctioned by the brief)

1. `or reportedAmpsActual < 4.0` is dropped from the stop hold. It could never be true under `> 4.0`, so nothing changes.
2. No gate acts before the first offer. This is the carry-in from Task 4's review: the first heartbeat after a slave's first reply could `withdrawStartCharging` while `lastAmpsOffered` was -1. The fix comes from the structure: the gates now run in `controlPass` right after `offerFor` sets `slave.offer`, so on the tick path `offer` is never None when a gate runs. The `offer is None` guard in `chargeGate` covers direct callers. `test_no_gate_acts_before_the_first_offer` checks `chargeGate` directly. Its `send_master_heartbeat` assertion is now trivially true, and the static test is what enforces it.
3. Timing: the gates now run on every 1 s tick instead of once per heartbeat round. This falls under the accepted (d). They write desired state only (the reconciler sends once per write), and the parity request lists are identical.

## Tests and results

- **RED** (`scratchpad/t5_red.txt`, lib still at HEAD): 2 failed, 46 passed. `test_the_heartbeat_decides_no_charging` failed because CarsCharging is in the heartbeat source. `test_no_gate_acts_before_the_first_offer` failed because `chargeGate` did not exist (and at HEAD the heartbeat would also have withdrawn). The 7 characterization tests were green against both the old and the new shape, as intended.
- **BASE+after characterization**: 7 new tests in `tests/unit/test_offer_characterization.py` (20 in the file), all run through `tickThenBeat` with a real `TWCMaster`/`Gen2TWC`/registry/`DesiredStore`, `VehicleEndpoints` registered and spike settings 0.
  - At 1029809b: **20/20 passed** (`scratchpad/t5_base_char.txt`; re-run on the final file). Method: a detached scratch worktree with this file and `gen2_helpers.py` copied in. A probe test confirmed the run imported the scratch worktree's lib (`TWCMaster` had no `controlPass`). The worktree was removed and pruned.
  - After: 20/20 passed.
- **GREEN** covering run (`test_control_tick`, `test_offer_characterization`, `test_charging_reconciler`, `test_command_path_parity`, `test_gen2_idle_minimum`): **165 passed** (`scratchpad/t5_green.txt`).
- **Full suite** (`tests --ignore=tests/API --ignore=tests/integration`): **1942 passed, 1 xfailed, 1 warning**. That is the 1933 baseline plus 9 new tests. The one warning is the pre-existing urllib3 `InsecureRequestWarning` in `test_enphase_ems` (confirmed with `-o addopts="" -rw`, since the repo sets `--disable-warnings`).
- **Black**: clean on `TWCMaster.py` and `TWCSlave.py`. Test files are not run through black: black reformatted unrelated lines in `test_control_tick.py`, so I reverted those.

## Parity

The `test_command_path_parity.py` per-test request lists were recorded with `scratchpad/plug/paritycounts.py`, at 6b89f9fd (a scratch worktree, since removed) and after `dc2609f5`. The two lists are identical, 51 rows each (`scratchpad/t5_parity_before.jsonl`, `t5_parity_after.jsonl`). No count or order moved.

## Files changed

- `lib/TWCManager/TWCSlave.py`, `lib/TWCManager/TWCMaster.py`
- `tests/unit/test_offer_characterization.py` (7 gate characterizations)
- `tests/unit/test_control_tick.py` (2 new tests)
- `tests/unit/test_gen2_idle_minimum.py` (1 test rewritten)

The brief lists `test_control_tick.py` for the characterizations. I put them in `test_offer_characterization.py` instead, because they have to run at 1029809b, and that file imports nothing BASE lacks and shares the fixture.

## Lib delta

- `git ls-files lib | grep '\.py$' | xargs cat | wc -l`: 27,092 before, 27,026 after.
- `git diff --shortstat 6b89f9fd -- lib`: 2 files changed, 51 insertions(+), 117 deletions(-).
- **Δ −66 against the expected ≈ −88.** The 22-line gap comes from black wrapping `chargeGate` (24 lines against the brief's 13-line sketch), the inline 6-line decision-to-call dict, the guard and its comment, and BASE's DEBUG line kept as a 9-line call.

## Test map (deleted or rewritten)

| Test | Mapping |
|---|---|
| `test_gen2_idle_minimum.py::test_start_request_follows_the_range_override` | PLUMBING-ONLY. It drove the gate with `lastAmpsOffered` and `send_master_heartbeat`; it now uses `pointAmps` and `controlPass(distribute=False)`. Same assertions: an 8 A override-minimum offer starts the car, 7 A does not. It also asserts the offers (8, then 0). |
| `test_charging_reconciler.py` | No change needed. `drive` runs receive, `controlPass`, send, so moving the gates from the heartbeat into the pass is invisible through it. |

No test was deleted.

## Thread ownership

- No slave field changed writer. `chargeGate` is read-only: it reads `offer` (written by the tick) and `reported*`, `timeReportedAmpsActualChangedSignificantly` and `vehicleKey` inputs (written by the serial thread), as `offerFor` already did.
- The callers moved threads: `stopCarsCharging`, `cancelStopCarsCharging`, `startCarsCharging` and `withdrawStartCharging` from the gates now run on the tick, not the serial thread. With them, the gate-driven `DesiredStore` writes, `reconciler.cancel`, `policy.clearOverride()`/`overrideLimit()` and the `stopTimeout` write (`TWCMaster.py:2073`) now come from the tick. The other `stopTimeout` writer is `TWCMaster.py:1409`, as at BASE. This matches the global constraints' "serial thread and tick" prediction, and the exposure is no greater than at BASE.
- No I/O under any lock. No RS-485 I/O off the serial thread: the heartbeat still sends, and the tick only writes desires.

## Grep for removed names

No names were removed by this task, so the grep has nothing to check. `git grep -n "Don't stop charging" -- lib` finds exactly one hit, `TWCMaster.py` (controlPass).

## Self-review

- Every brief item is done, including the mode-2 skip with its BASE+after test and the carry-in with its test. The stop-cancel is not duplicated: it stays in Task 4's line, now under the silence `continue`.
- Comments follow the new rule: they say why, with no history and no phase, review or ruling IDs in anything I wrote or touched. The commit messages carry the history.
- YAGNI: there is no new class-level table. The decision-to-call map is a local dict.

## Concerns

1. **The key is read twice.** `controlPass` reads `slave.vehicleKey`, and `chargeGate` reads it again. If the serial thread changes `currentVIN` or `reportedState` between the two reads, a decision computed for one key could be applied to the other. This is benign: `_chargeTargets` resolves the key against present cars, and the `key is not None` guard rules out the one dangerous case, a None key reaching every car. I did not widen `chargeGate`'s signature, because the brief pins it to `chargeGate(now)`. The guard has no dedicated test: triggering the race would need a mocked `chargeGate`.
2. The lib delta is 22 lines short of the expected figure (see above). It still shrinks.
