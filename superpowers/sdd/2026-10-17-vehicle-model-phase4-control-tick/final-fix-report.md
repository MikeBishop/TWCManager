# Phase 4 final-review fix wave: f506104d..7648704d (vehicle-model/phase4)

Worktree: `scratchpad/wt-vm4`. Ten commits, not pushed. Pytest command throughout (PY = `scratchpad/venv/bin/python`):
`timeout 600 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest <args> --timeout=60 -p no:cacheprovider`

| Commit | Finding |
|---|---|
| 0594eca5 | Important 1 |
| 22517616, 7648704d | Important 2 (7648704d shortens the ERROR message to save 4 lib lines) |
| 1fdd4395 | Important 3 |
| 7df29e31 | Minors 4 and 5 |
| 5d7165a1 | Minor 6 |
| 26557eaf | Minor 7 |
| fa01ccaf | Minor 8 |
| ef1c8fc5 | Minor 9 |
| 8e36aa9d | Minor 10 |

## Important 1: the serial loop and shutdown need an Interface module

**Change** (`lib/TWCManager/TWCManager.py`). Before the main loop, `hasBus = bool(master.getModulesByType("Interface"))`. Whether an interface is loaded is settled by the end of startup: RS485 releases itself in `__init__`/`connect()` only. Right after the stall check, `if not hasBus: continue` skips everything below it: `flushRS485`, the `fakeMaster == 1` send block (linkready1/2, heartbeats), `send_slave_linkready`, the kWh poll, `retryVINQuery` and the RX section, including the kWh reply send at the old :1833. With no interface there are no slaves, so the kWh poll and VIN retry have nothing to do anyway. At shutdown, `flushRS485()` and `getInterfaceModule().close()` run only `if hasBus`. I grepped `lib` for other `getInterfaceModule(`/`getTimeLastTx(` callers. All of them are in the loop, in `TWCMaster.flushRS485`/`getTimeLastTx`/linkready senders reached only from the loop, or in shutdown.

**Test.** `tests/unit/test_sigterm_shutdown.py::test_an_install_with_no_interface_runs_and_shuts_down_cleanly`. It boots the real process on `.testconfig.json` with `interface.Dummy/RS485/TCP.enabled = false`, lets the main loop run 3 s, then sends SIGTERM. It asserts exit code 0, no `Traceback` and no `Unhandled Exception` in the output, and that `Shutdown complete` is printed. The existing SIGTERM test's scaffolding was factored into `_runThenSigterm(tmp_path, configure, settle)`, and the old test now calls it with no change in behaviour.
- RED (lib change reverted): `1 failed` with `IndexError: list index out of range` repeated in the output.
- GREEN: `test_sigterm_shutdown.py` plus `test_rs485_serial_only.py`: `16 passed`. That includes `test_shutdown_flushes_the_outbox` and the loop-source tests.

**pr-notes.md** (in this directory, not committed):
- (g) gains a sub-bullet. Configure `controller.Gen3TWCs` and set `interface.RS485.enabled: false` (Dummy and TCP are off by default). With no interface loaded, the serial loop idles and shutdown skips the bus. If RS-485 is left enabled with no `port`, it logs an error and unloads itself. But the shipped config sets `port: /dev/ttyUSB0`, and a configured port with no adapter behind it aborts startup.
- (h)'s "must be disabled" bullet now says what to configure: the vehicle module(s) plus `interface.RS485.enabled: false`, as for (g). It keeps the blind rule as the reason the cars become rateable.

## Important 2: the control tick fails safe and says why

**Change.**
- `lib/TWCManager/ControlTick.py`: `pass_` calls `_controlPass()`, which keeps `self.failures` (consecutive failed passes).
  - It logs a WARNING with `exc_info=True` on failure 1 and on every 60th (60, 120, …).
  - At failure 30 (`WITHDRAW_AFTER`) it logs one ERROR: `Control tick: 30 failed passes; offers withdrawn`.
  - On every failing pass from 30 on, it calls `master.withdrawOffers()` (guarded). Repeating the call keeps a slave that a partial pass touched, or that became heard-from during the outage, at zero.
  - On the first successful pass after a withdrawal it logs one INFO (`controlPass succeeded; offers resume`) and resets the count. Any success resets it.
  - Housekeeping keeps its one-line warning.
- `TWCMaster.withdrawOffers()`: first, every heard-from slave gets `offer = Offer(0, 0)`. A 0 offer is the TWC's idle minimum, and unheard slaves keep `None`, so a restart still never offers 0. Then every non-read-only charging point gets `setTargetPower(0)`, which gives Gen3 units and cars a zero target. The slaves go first, so a raising `chargingPoints()` can't leave them on a stale offer.

**Tests** (`tests/unit/test_control_tick.py`):
- `test_a_failing_pass_logs_its_traceback_first_and_every_60th`: over 120 failing passes, records carrying exc_info appear at exactly 1, 60 and 120.
- `test_offers_are_withdrawn_after_30_failed_passes_and_resume`: after 29 failures the offers are unchanged. By 35, both slaves hold `Offer(0, 0)` and the unheard slave still has `None`. There is exactly one ERROR. A working pass restores 20/20 and logs the resume INFO once over two passes, and `failures == 0`.
- `test_a_withdrawal_targets_gen3_units_and_cars_zero`: a real Gen3 unit gets `setUnitTarget(u.ID, 0)`, and a vehicle-only car's AMPS desire is withdrawn.
- `test_a_withdrawal_zeroes_the_slaves_even_if_points_cannot_be_built`.
- The existing `test_a_raising_pass_is_logged_and_the_tick_continues` passes unchanged.
- GREEN: `test_control_tick.py`: `33 passed` at that commit.

## Important 3: token capture at the claim

**Change** (`lib/TWCManager/Vehicle/TeslaTokenSlot.py`). Under `_cond`, right after `self._claimedAt = claimed = self.changes`, the code now reads `token, clientID = self.refreshToken, self.clientID`. `_refreshOnce(now, claimed, token, clientID)` uses those values for the not-configured checks and the POST body. There are no other callers.

**Test.** `tests/unit/test_teslatokenslot.py::test_a_paste_just_after_the_claim_does_not_change_what_is_posted`. It wraps `_refreshOnce` so that `setTokens(pasted, "rp")` runs between the claim and the payload build. It asserts that the POST's `refresh_token` is `r1`, and that the late answer is discarded (the slot keeps the pasted tokens).
- RED (lib reverted): `AssertionError: assert 'rp' == 'r1'`.
- GREEN: `test_teslatokenslot.py`: `43 passed`.

## Minor 4: test tags and stale headers

- `test_control_tick.py`: the header is rewritten. It now says "every install", not "with a Gen2 slave", and drops "Phase 4, Task 3".
  - `# Task 4:` becomes `# Offers are computed on the tick; …`.
  - The `# F9`/`# F7` tags are removed. So are the four `# Review Focus N` tags, which are the same class of tag (:128, :144, :201, :236).
- `test_offer_characterization.py`: the header loses the "1029809b … Phase 4 Task 4" history. The `# F6` tag is removed, and so is `# F13` (same class).
- I left the `# (a)`–`# (h)` behaviour tags, which the review did not flag.

## Minor 5: black on test_control_tick.py

`black` reformatted the file, and `black --check` is now clean. `test_control_tick.py` plus `test_offer_characterization.py`: `53 passed`.

## Minor 6: debug page

- `debug.html.j2`: removed the `/debug/save` form opener, the "Advanced Settings" heading and warning, the header-only table and the trailing page-level "Save Settings" button. "Debug Information" stays. The saveToggle form and its own Save button are untouched.
- Nothing else posted to `/debug/save` (I grepped lib, tests and html), and `process_save_settings("debug")` had no `page == "debug"` branch. So the 3-line route in `HTTPControl.do_POST` is removed too.
- `-k "http or debug or template"`: `62 passed`.

## Minor 7: docs/config_examples.md

The "Considerations" bullet is rewritten. Charging starts only once `minAmpsPerTWC` (6 A) is available above the 5 kW export limit and stops when generation falls back below that, so it never dips into exportable energy. The Outcome sub-bullet that said "We will use flex charging…" is removed. The later "Flex current is not supported from 1.4.0" outcome bullet stays.

## Minor 8: no offer drift during the mode-2 silence

**Change** (`TWCMaster.controlPass`). After the distribution (which still runs, as at BASE), a silent pass returns before building the `OfferContext`. `offerFor` doesn't run, so `offer`, `lastAmpsOffered`, `timeLastAmpsOfferedChanged` and the status publishes hold. The per-slave `silent` check is gone.

**Tests:**
- New: `test_offers_and_their_status_hold_during_the_mode_2_silence`. A silent pass with a changed budget leaves `(offer, lastAmpsOffered, timeLastAmpsOfferedChanged)` unchanged and makes no `setStatus` call.
- INTENTIONALLY CHANGED (Minor 8 ruling):
  - `test_no_stop_cancel_during_the_mode_2_silence` now asserts `s.offer is None` during the silence (it was 32) and `s.offer.amps == 32` after it.
  - `test_offer_characterization.py::test_no_gate_runs_during_the_mode_2_silence` simulated a reply during the silence, which a real TWC never sends. Its offer is now made before the silence starts (one non-silent beat, asserting the expected cancelStop), and then it runs as before.
- It still passes on BASE: in a scratch worktree at 1029809b with the new `test_offer_characterization.py` and `gen2_helpers.py` copied in, the result is `20 passed` (`scratchpad/fix8_base_char.txt`). After: passes.
- RED (lib reverted): both silence tests in `test_control_tick.py` fail.

## Minor 9: offer status only on change

**Change** (`TWCSlave.offerFor`). It compares with `self.offer`, the previous offer, which `controlPass` (the only caller) stores. It publishes `amps_offered` when `amps` differs and `amps_desired` when `desired` differs, and publishes both when there is no previous offer.

**Test.** `test_offer_status_is_published_only_when_it_changes`: the first pass publishes both, an identical pass publishes nothing, and a budget change publishes both new values. RED (lib reverted): fails. GREEN: `test_control_tick`, `test_offer_characterization` and `test_twcslave`: `86 passed`.

## Minor 10: one liftedSession reset

I removed `self.liftedSession = None` from `offerFor`'s car-carries branch and kept `ChargingPoint.setTargetPower`'s reset, which sits beside the lift's set.

Why behaviour doesn't change:
- In mode 2, `carriers()` is `(False, True)`, so every non-zero point target takes the car-carries branch and resets there. With a zero target, `offerFor` takes the `desired < minOffer` branch, which never reset.
- In mode 3 below 6 A (`< layerFloorAmps`), ChargingPoint also takes the car-carries branch. Its condition is a superset of `offerFor`'s.
- Both run on the tick, in the same pass.

`-k "lift or offer or charging_point or control_tick or parity"`: `153 passed`.

## Full suite

`tests --ignore=tests/API --ignore=tests/integration`: **1955 passed, 1 xfailed, 1 warning** in 94 s (`scratchpad/fix8_full.txt`). That is the 1947 baseline plus 8 new tests (1 subprocess, 6 control tick, 1 token slot). The warning is the pre-existing urllib3 InsecureRequestWarning.

## Lib delta

`git ls-files lib | grep '\.py$' | xargs cat | wc -l`: 26,450 → **26,492 (+42)**. `git diff --shortstat f506104d -- lib`: 7 files changed, 67 insertions(+), 40 deletions(-), which includes −15 lines of the j2 template.

Per file (.py, net):

| File | Net | Reason |
|---|---|---|
| ControlTick.py | +25 | Important 2 |
| TWCMaster.py | +10 | `withdrawOffers` +11, silence early return −1 |
| TWCManager.py | +5 | Important 1 guards |
| TWCSlave.py | +3 | publish on change +4, redundant reset −1 |
| TeslaTokenSlot.py | +3 | Important 3, including a 2-line why-comment |
| HTTPControl.py | −4 | dead `/debug/save` route |

All of the growth is what the Important fixes need; the minors are net −2.

## Parity

`tests/unit/test_command_path_parity.py` is untouched (`git diff f506104d -- tests/unit/test_command_path_parity.py` is empty). I recorded the per-test request lists with `scratchpad/plug/paritycounts.py` at f506104d (scratch worktree, removed afterwards) and at HEAD. The two lists are byte-identical, 51 rows each (`scratchpad/fix8_parity_before.jsonl`, `fix8_parity_after.jsonl`). No count or order moved.

## Black

`black --check` is clean on every changed lib `.py` (6 files) and on `test_control_tick.py`.

## Concerns

- While offers are withdrawn, the `amps_offered`/`amps_desired` status keeps its last published values: `withdrawOffers` sets `Offer(0, 0)` without publishing. On recovery, the next real offer is compared with `(0, 0)` and published, so status is correct again after the first good pass. This happens only in the failure state, which logs an ERROR.
- A withdrawal calls `setTargetPower(0)` on every point, every failing pass, so a car member's charging target goes to 0 through the normal reconciler. It is the same path the distributor uses for an idle point. It makes no new paid call in the parity rows, but a persistent failure stops cars charging, as the ruling accepted.
- If `chargingPoints()` itself is what keeps raising, the withdrawal (run every failing pass from 30 on) logs `WARNING Control tick: withdrawOffers raised X` once a second through `_guarded`. The slaves are already zeroed by then, so behaviour is correct, but the log is noisy in a state that has already logged its ERROR. I left it to avoid more lib.
- The `(a)`–`(h)` behaviour tags remain in `test_control_tick.py` (see Minor 4). The comment rule's example list includes "(d)", so you may want them gone too.
- 7648704d is a small follow-up to 22517616 (a shorter ERROR message). I left it as its own commit rather than rewrite history non-interactively; squash it if you prefer.
