# Task 1 report: every RS-485 write goes through the serial loop's outbox

Status: DONE. Commit `874a20d9` "Send every RS-485 message from the serial loop; compact the VIN check digit" on `vehicle-model/phase4` (BASE 1029809b). Not pushed.

## What was implemented

- `TWCMaster._outbox` (a `collections.deque`, set in `__init__`), `sendRS485(msg)` (append, no lock, any thread) and `flushRS485()` (serial thread only: pops FIFO and sends with `getInterfaceModule().send`, returns the count).
- `getSlaveLifetimekWh`, `getVehicleVIN`, `sendStartCommand` and `sendStopCommand` call `self.sendRS485`. Their signatures are unchanged.
- HTTP `sendTWCMsg` calls `master.sendRS485(createMessage(packet))`, and WebIPC calls `self.master.sendRS485(twcMsg)`. Both still clear `lastTWCResponseMsg` before enqueuing.
  - **Small fix:** these two used `getModuleByName("RS485").send`. The outbox sends on the active interface, so a TCP-interface install no longer fails here.
- `Gen2TWCProvider` mode 3 calls `self.master.sendStopCommand(slave.TWCID)` and still returns `Outcome(DONE, "queued")`. `stopRequested` is gone from `TWCSlave` (class attribute and the heartbeat branch), from `Gen2TWC.__init__`, and from the provider's header comment.
- `TWCManager.py`:
  - `master.flushRS485()` runs right after the sleep and stall check, before the `fakeMaster == 1` block.
  - A final `master.flushRS485()` runs right before `master.getInterfaceModule().close()` at shutdown, after the reconciler drain and the background-task wait.
  - VIN rx: `vinValid = len(potentialVIN) == 0 or vinCheckDigitValid(potentialVIN)`, followed by `potentialVIN = potentialVIN.upper()`. BASE's length-0 "stop querying" branch, valid branch and re-request branch are kept unchanged.
- `Registry/VIN.py`: `vinCheckDigitValid(vin)` checks the length (17) first, as BASE did, then upper-cases. It transliterates with `str.maketrans`, so any character outside the table (I, O, Q, non-ASCII, punctuation) gives False. It compares position 9 against the weighted sum mod 11, with X for 10. Black leaves it in a compact form.
- The background tasks (`checkVINEntitlement`, `getLifetimekWh`, `getVehicleVIN`) are unchanged. They keep their dedupe and delay, and only the send inside them now enqueues.

## Tests and results

New file `tests/unit/test_rs485_serial_only.py` (13 tests):
- start/stop are queued and FIFO: `[fcb1, fcb1, fcb2]`, and the stop goes to 8244.
- The VIN query and kWh poll are queued (3 messages).
- AST offender scan of `lib/TWCManager` (Interface/ excluded). A `.send(` on `getInterfaceModule()`, `getModulesByType("Interface")[..]` or `getModuleByName("RS485")` is allowed only in `flushRS485`, the linkready senders, the slave heartbeat senders, or `TWCManager.py` module level.
- Static: the loop flush comes after `time.sleep(0.025)` and before the fakeMaster block. The shutdown flush (`rindex`) comes after `reconciler.drain(` and before `getInterfaceModule().close()`.
- A parametrized check-digit test, with the BASE answer for `5YJ3E1EA1KF000001` = False (computed by running `_baseRule`, not guessed). It covers lowercase input too.
- `test_check_digit_agrees_with_the_base_rule_on_10k_random_vins`: seeded, and the alphabet includes I/O/Q, lowercase, space and `-`. Half the samples get a correct check digit, which gives 618 valid VINs. Wrong lengths are also checked.
- `test_an_all_empty_vin_still_stops_querying` and `test_a_valid_vin_is_recorded_and_a_bad_one_requeried`: these exec the real VIN rx `If` block taken from `TWCManager.py` source (AST) with a real `re.search` match on an FD F1 message. The empty VIN sets `lastVINQuery = 0` and `vinQueryAttempt = 0` and queues nothing. A lowercase valid VIN is recorded upper-cased. A bad check digit re-requests part 0.

`_baseRule` interpretation: the brief says both "delete the copy in Step 3" and "keep the 10k test", and the 10k test needs the copy. So the parametrized test asserts literal answers (still checked against `_baseRule` too), and `_baseRule` stays for the kept 10k test.

Full suite, `tests --ignore=tests/API --ignore=tests/integration`: **1881 passed, 1 xfailed, 1 warning**. Baseline was 1868 passed. The difference is 13 new tests, plus 1 from splitting the gen2 provider mode-3 check into its own test, minus 1 test renamed and kept. The 1 warning is pre-existing. `grep stopRequested lib` gives no hits. The only hit in tests is `assert not hasattr(TWCSlave, "stopRequested")`.

With `-W error`, the touched files show one failure: `test_twcmaster_vin_confirmation.py::test_background_thread_dispatches_the_home_check`. It has an unclosed `open()` and is unchanged by this task. My new file closes every file it opens.

## TDD evidence

RED: `pytest tests/unit/test_rs485_serial_only.py tests/unit/test_gen2twc_provider.py tests/unit/test_charging_reconciler.py tests/unit/test_provider_outcomes_local.py`
- The new file failed at collection: `ImportError: cannot import name 'vinCheckDigitValid'`.
- The other three files gave `6 failed, 66 passed`, with `AttributeError: 'TWCMaster' object has no attribute '_outbox'` / `'flushRS485'` and `assert not True` (the slave still had `stopRequested`).
- `offenders()` at BASE: `['Control/HTTPControl.py:942', 'Control/WebIPCControl.py:258', 'TWCMaster.py:1806', 'TWCMaster.py:1818', 'TWCMaster.py:720', 'TWCMaster.py:842']`.

GREEN:
- The same files plus `test_twcmaster_vin_confirmation.py` gave 100 passed, after two test-side fixes. The sanity floor of the 10k test was too high at >1000 (actual 618, set to >500). The agreement assertion never failed. I also closed the files the new test opens.
- Full suite as above.
- The VIN-confirmation tests needed no edits.

## Files changed

lib: `TWCMaster.py`, `TWCManager.py`, `TWCSlave.py`, `EVSEInstance/Gen2TWC.py`, `Vehicle/Providers/Gen2TWCProvider.py`, `Vehicle/Registry/VIN.py`, `Control/HTTPControl.py`, `Control/WebIPCControl.py`.
tests: `test_rs485_serial_only.py` (new), `test_gen2twc_provider.py`, `test_charging_reconciler.py`, `test_provider_outcomes_local.py`.

## Lib delta

`git ls-files lib | grep '\.py$' | xargs cat | wc -l`: 27,425 → **27,377 (−48)**, against an expected ≈ −50.

## Deleted/rewritten test map

- `test_gen2twc_provider.py::make`: the TWCID changed from `"AB"` to `b"\x77\x77"` (bytes, as the launcher passes it, and what `gen2_helpers.drive` already set). The real `sendStopCommand` concatenates bytes. PLUMBING-ONLY. Every test that uses `make` (gen2, limit/charging reconciler, outcomes_local) passes.
- `test_gen2twc_provider.py:176` (the tail of `test_disruptive_stop_declared_very_high_cost_and_off_by_default`): moved to the new `test_mode_3_stop_is_queued_for_the_serial_loop`. It asserts `Outcome(DONE,"queued")` and `[fcb2]` in `m._outbox`, and fails if anything reaches the interface. PLUMBING-ONLY (F11). The leftover `chargeStopMode = "3"` line was dropped from the original test.
- `test_charging_reconciler.py:52-56` (`test_heartbeat_stop_targets_the_anonymous_car`): `s.stopRequested` plus the Mock `sendStopCommand` called by the next heartbeat became `_outbox == [fcb2 + s.TWCID]` after `r.pass_()`, then `flushRS485() == 1` sending fcb2. PLUMBING-ONLY.
- `test_charging_reconciler.py:104-107` (`test_disruptive_stop_on_the_real_clock_is_sent_once`): `sendStopCommand.call_count == 1 and not s.stopRequested` became `flushRS485() == 1` after 20 passes and a heartbeat (one relay stop, not one per pass). PLUMBING-ONLY. The dedupe claim is kept.
- `test_charging_reconciler.py:126`: `getSlaveTWCs()[0].stopRequested` became `[x[:2] for x in m._outbox] == [fcb2]`. This proves the real send ran and did not raise inside the reconciler. PLUMBING-ONLY.
- `test_provider_outcomes_local.py:46-51`: renamed `test_mode_3_stop_is_sent_by_the_heartbeat_not_the_caller` to `..._by_the_serial_loop_not_the_caller`. The stop is queued, the heartbeat sends only `fbe0` and leaves the outbox untouched, and `flushRS485()` sends the fcb2. PLUMBING-ONLY.
- `test_provider_outcomes_local.py:96-98`: `test_bare_twcslave_has_no_stop_requested` (`TWCSlave.stopRequested is False`) became `test_twcslave_has_no_stop_flag` (`not hasattr(TWCSlave, "stopRequested")`). INTENTIONALLY CHANGED: the attribute no longer exists.

## Self-review findings

- The diff is limited to the brief's files. An unrelated Black reformat of two lines in `test_gen2twc_provider.py` was reverted.
- No locks were added. `deque.append` and `popleft` are atomic. `flushRS485` is only called from module level in TWCManager.py (the loop and shutdown).
- The ordering for `sendTWCMsg` is unchanged: `lastTWCResponseMsg` is cleared before enqueuing, and the reply is captured once the loop sends.
- `vinCheckDigitValid` gives False where BASE could raise (a non-ASCII digit such as "²" at position 9: BASE's `int()` raised ValueError). It is otherwise identical, including the length check before upper-casing.

## Concerns (minor)

- If the final shutdown `flushRS485()` hits a send error, it raises before `close()`, much as a failing `close()` would. I added no try/except (YAGNI). Say if you want it guarded.
- Messages enqueued while the interface is not yet up wait for the first loop pass. That is the intended behaviour.
- The test `assert not hasattr(TWCSlave, "stopRequested")` is the one remaining textual hit for `stopRequested`. Drop it if a zero-hit grep is required literally.
