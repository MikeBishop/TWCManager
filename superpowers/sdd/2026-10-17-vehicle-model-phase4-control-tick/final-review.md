# Phase 4 final review: 1029809b..f506104d (vehicle-model/phase4)

Reviewed the whole range as one diff (13 commits, 69 files, +2,484/−2,225; lib 27,425 → 26,450), read against the plan, the spec's binding sections, global-constraints.md, rulings-since-plan.md and the progress ledger. Full unit suite on the checkout: **1947 passed, 1 xfailed, 1 warning** (the pre-existing urllib3 InsecureRequestWarning). `black --check` is clean on every touched lib `.py` file (the only "failure" is the Jinja template, which black cannot parse at BASE either).

## Strengths

- **The threading split is real and verifiable.** `TWCSlave.send_master_heartbeat` is now pure protocol: it reads one immutable `Offer` tuple and sends. `receive_slave_heartbeat` writes only observations and calls `observeChargingSessions()`. The tick writes `offer`, `pointAmps`, `lastAmpsOffered`, `timeLastAmpsOfferedChanged`, `liftedSession`, `_lastKeys`; the serial thread writes `reported*`, `heardFrom`, `isCharging`, `plugSessions`. I traced every writer and found no attribute with two writers beyond those the constraints already accept (`stopTimeout`, `pointAmps` via `Gen2TWCProvider.setAmps`, and the latter is actually unreachable from the reconciler: `plan()` excludes providers with `module is None` from AMPS attempts, so F14's exception is moot).
- **The outbox is the right shape.** `deque.append`/`popleft` from any thread, drained only at the top of the serial loop; the static AST test (`test_only_serial_thread_code_writes_rs485`) pins the invariant rather than trusting review. Shutdown flushes after both drains so a mode-3 stop reaches the bus.
- **The once-per-session lift as `liftedSession == plugSessions`** is an elegant fix for the two-writer `vehicleRateRaised` bool; `test_the_lift_survives_a_session_end_racing_the_tick` covers the race.
- **Token single-flight** waits without holding the lock across the POST, shares the result, discards a late answer after a paste (including the 401 clear), and a waiter whose tokens changed refreshes its own afterwards. Lock order holds: `_cond` is a leaf; `classify()` (which logs) runs before the lock.
- **Characterization discipline.** `tickThenBeat` encodes BASE's order and the tick's order, and the offer/gate rules are pinned by tests that passed on a BASE checkout before the move. Parity counts are untouched; row 26's BLE order is back to BASE's thanks to Task 4b. Rows 29/30 state the (h) paid bound explicitly.
- **`Gen3` untouched** beyond its base class and docstrings; the solver, `WallConnectorVins`, `_correlate` are intact.
- **Honest size reporting** per task in pr-notes.md; the stack shrank by 975 lines with no padding I could find (the `DEFAULT_SETTINGS` dedupe is a genuine −42).
- **Comment sweep** of lib reads as designed; the `test_code_comments_name_no_phase_or_issue` guard keeps it that way.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

1. **(g) Gen3-only and (h) vehicle-only are advertised, but the serial loop cannot run without an Interface module.** `TWCManager.py:1004` (`master.getInterfaceModule().getBufferLen()`) and the linkready sends run unconditionally every iteration; `getInterfaceModule()` indexes `getModulesByType("Interface")[0]`. pr-notes.md says vehicle-only requires the RS-485 interface *disabled*; `Interface.Dummy` defaults to disabled; `Interface/RS485.py` with no port configured releases itself (`connect()`), and with a port but no adapter raises and the module loader re-raises, aborting startup. So every configuration that makes `_blindTWCs` return not-blind with zero slaves (`not slaves and master.getModulesByType("Interface")` → blind) is one where the main loop throws `IndexError` every iteration, prints a traceback and sleeps 5 s (`TWCManager.py:1898–1912`), and shutdown dies at `master.getInterfaceModule().close()` before `os._exit`. Gen3-only has the same shape (its Modbus port is Gen3TWCs' own). `test_a_vehicle_only_install_is_controlled` asserts `getModulesByType("Interface") == []` in-process and the parity rows run `controlPass` directly, so none of them can see this. This is pre-existing at BASE and main, but BASE never claimed these installs as controlled. Fix one of: (a) guard the loop and shutdown on an interface being present (a handful of guards: the `fakeMaster == 1` send block, the RX section, `send_slave_linkready`, `flushRS485`, `close()`; arguably in scope since Phase 4 is what makes these installs meaningful), or (b) reword the (g)/(h) PR-notes bullets to say what a user must actually do and that the serial loop logs a traceback every 5 s today, and open an issue. Either way the current wording overclaims.

2. **The control tick fails open with no diagnostics.** `ControlTick._guarded` logs `WARNING Control tick: controlPass raised KeyError` once a second with the type name only. If `controlPass` raises persistently (a bad config value, a registry inconsistency, a Status module that throws), every slave keeps its last `offer` on the wire indefinitely while the budget may have dropped to zero — the wiring cap and the stop rule are no longer re-evaluated. At BASE the same exception hit the serial loop's handler: a traceback in the log and a visible loop stall. The new failure is quiet, and keeps the last offer on the wire. A raise mid-loop also leaves the slaves before it updated and those after it stale. Minimum: `exc_info=True` on the first occurrence (and perhaps every Nth), so the operator can see *what* raised. Whether offers should be withdrawn (sent as "no change" or 0) after N consecutive failures is a design question for the user, not something to decide in a fix round; raise it. (Ledger: Task 3 minor "ControlTick failure log has no detail".)

3. **`TeslaTokenSlot._refreshOnce` reads `self.refreshToken` and `self.clientID` after the claim, outside `_cond`.** A paste landing in the microseconds between `_claimedAt = changes` and the payload build POSTs the *pasted* refresh token; the answer is then discarded (`claimed != changes`) and the slot is left holding a spent single-use token, so the next refresh gets a 401 and clears it. The window is tiny, but this is exactly the race the task exists to close, and the fix is a one-line capture of `(refreshToken, clientID)` under `_cond` at the claim and passing them into `_refreshOnce`. (Ledger: Task 2 minor.) Classified Important because of what it costs when it hits; the fix is trivial.

### Minor (Nice to Have)

4. **Phase-4-authored tests still carry phase/task/ruling tags**: `test_control_tick.py:1–3` ("every install with a Gen2 slave" is also wrong since ruling 1), `:222`, `:285`, `:308`, `:320` (`F9`, `F7`, "Task 4"), `test_offer_characterization.py:4, :149` (`F6`). The Task 6 brief scoped the sweep to lib and said not to churn tests, so this is within brief — but these files were written in Phase 4 under the rule, and f506104d already did this for two other test files. A five-minute sweep.

5. **`test_control_tick.py` is a new file and fails `black --check`** (two long `assert` lines). The other two new test files are clean.

6. **`debug.html.j2` keeps an empty "Advanced Settings" section**: the warning paragraph, a header-only table, and the page-level "Save Settings" submit button now post a form with no fields. Drop the section (ledger: Task 4 minor).

7. **`docs/config_examples.md`** still tells the reader, in the "Considerations" bullets above the config block, to *use* flex ("We will use flex charging to allow the charge to dip…"); only the config snippet and one outcome bullet were updated. The example's rationale now contradicts its own outcome.

8. **Silence-window drift.** During the chargeStopMode-2 silence BASE got no replies, so `lastAmpsOffered`, `timeLastAmpsOfferedChanged` and the status publishes froze. Now `offerFor` runs every tick during silence, so a policy change mid-silence resets `timeLastAmpsOfferedChanged`, and the 60 s stop hold can restart when the silence ends (test `test_no_gate_runs_during_the_mode_2_silence` only checks the *gate* is skipped). Low impact (the silence *is* a stop), but it is a behaviour change outside (a)–(h). Skipping `offerFor` while silent, or at least not touching the timestamps, would restore BASE.

9. **Status publish rate scales with slave count.** `offerFor` publishes `amps_offered`/`amps_desired` per slave per tick; BASE published once per slave per round (≈ N × 1.1 s). HASS dedupes by value; MQTT publishes every call unless `msgRatePerTopic` is configured. For 3 TWCs that is ~3× the MQTT traffic on two topics. Publish only on change, or note it.

10. **`liftedSession = None` is written in two places on the same pass** — `TWCSlave.offerFor` (mode 2 / mode 3 < 6 branch) and `ChargingPoint.setTargetPower` (car-carries branch). Same thread, so harmless, but one of them is redundant and the duplication will confuse the next reader.

11. **`refreshTokens` first run at +300 s** (was ≈ immediately at BASE): called out in pr-notes.md, fine; just confirming `loadList`'s own `refreshTokenIfNeeded` covers boot.

12. **`ast.unparse` (3.9+) in `test_rs485_serial_only.py:220–222`** while CI's unit job runs on 3.8: pre-existing precedent `test_provider_registration.py:151` is equally unguarded, so the 3.8 job is already red or tolerant. Not a regression; worth a `sys.version_info` skip on both some day.

## Deferred-minor triage (each ledger minor: fix before merge / leave)

| Task | Ledger line | Disposition |
|---|---|---|
| 1 | `ast.unparse` 3.9+ in test (CI 3.8) | **Leave** — pre-existing unguarded precedent at `test_provider_registration.py:151`; not a regression (Minor 12) |
| 1 | shutdown `flushRS485` unguarded; loop drops one message on send error | **Leave** — same handling as a heartbeat send error at BASE; shutdown ends in `os._exit` anyway |
| 1 | invalid-length VIN upper-cased before logging | **Leave** — log text only |
| 1 | `_baseRule` copy kept in test | **Leave** — it is the 10k cross-check's oracle |
| 2 | `refreshToken`/`clientID` read after the claim outside the lock | **Fix before merge** (Important 3) |
| 2 | readers unlocked; comment overclaims "never half-written" | **Leave** — reads of individual attributes are atomic under the GIL; the comment now says "write the slot under it", which is accurate |
| 2 | first periodic refresh + listPending retry at +300 s | **Leave** — in pr-notes.md |
| 2 | lib +32 vs +22 | **Leave** |
| 2 | full suite "1 warning" unattributed | **Leave** — identified in Task 4b as urllib3 InsecureRequestWarning in test_enphase_ems |
| 2 | `test_teslatokenslot.py:373–383` 0.2 s thread-start assumption | **Leave** — suite is green here; watch CI |
| 2 | rare redundant extra refresh after setTokens before `_refreshing` clears | **Leave** — single-use-safe |
| 3 | "1 warning" | **Leave** (as above) |
| 3 | stale docstrings: `VehicleEndpoints.py:4-5` (file deleted), `test_control_tick.py:1-2`, `docs/config_examples.md` flex text | **Fix before merge** for the test header and the doc (Minors 4, 7); the first is moot |
| 3 | ControlTick failure log has no detail | **Fix before merge** (Important 2) |
| 3 | fragile `side_effect` list in test_control_tick | **Leave** |
| 3 | untargeted-beat early return skips print_status/override | **Leave** — obsolete after Task 4: the heartbeat always builds the payload and `print_status` is in `receive` |
| 3 | lib −38 vs −58 | **Leave** |
| 3 | RS485 defaults enabled; vehicle-only needs RS485 disabled; note in PR | **Fix before merge** — folded into Important 1 (the note as written describes a crash loop) |
| 4 | first beat after first reply runs gates with `lastAmpsOffered == -1` | **Done** in Task 5 (`chargeGate` returns None while `offer is None`; verified) |
| 4 | `ChargingPoint.setTargetPower` ~75 lines with nested closures | **Leave** — readable enough; the closures share `mine`/`local` |
| 4 | stale comment `Gen2TWCProvider.setAmps` | **Done** (now "the control tick offers it, the heartbeat sends it") |
| 4 | per-TWC cap DEBUG line every tick | **Leave** — DEBUG level |
| 4 | `debug.html.j2` Advanced Settings table empty | **Fix before merge** (Minor 6) |
| 4 | no test pins TWC-only point holding raw watts (mode 3 < 6 A) | **Leave** — the plan notes the distributor never reaches it in production |
| 4 | suite warning detail not recorded | **Leave** |
| 4b | cross-queue race (rate on cloud, start on BLE) | **Parked/out of scope** by ruling; see Declined |
| 4b | real-Fleet ordering test uses a sleep loop | **Leave** |
| 4b | no combined limit→rate→held-start test | **Leave** — parity row 26 is that sequence end to end |
| 4b | `Reconciler.py:92-94` comment omits why stops keep stop-first | **Done** ("a stop never waits behind a rate") |
| 5 | vacuous assertion in `test_no_gate_acts_before_the_first_offer` | **Done** in Task 6 (`heardFrom = False; controlPass()`; verified) |
| 5 | `chargeGate` lacks type hints/docstring | **Leave** — has `-> Optional[str]` and a why-comment |
| 5 | DEBUG text differs from BASE wording | **Leave** |
| 6 | `test_one_distributor_entry` misses module-level calls | **Leave** — `test_the_serial_loop_no_longer_distributes_or_processes_ipc` covers the loop source |
| 6 | `test_control_tick.py:1–3` header stale + phase tag | **Fix before merge** (Minor 4) |
| 6 | ragged comment reflows | **Leave** |
| 6 | live-check.sh: REPO hard-coded, rollback detached HEAD, `cp` without sudo | **Leave** — operator script in `.superpowers`, not shipped; the user runs it interactively and can adjust |
| 6 | `EVSEInstance.controllers = []` shared mutable default | **Leave** — every subclass overrides it; nothing mutates it |

## Declined to judge

- **Gen2TWCProvider as a lift/AMPS carrier** (would set `pointAmps` from a reconciler lane): unreachable — `Reconciler.plan` excludes `module is None` providers from AMPS; pre-existing design, not Phase 4's.
- **Mode 3 with car members below the floor**: `ChargingPoint` takes the car-carries branch while `offerFor` (seeing `max(floor, amps) ≥ 6`) takes the TWC branch; identical to BASE and noted in the plan as pre-existing, revisited by two-pass admission (#709).
- **Cross-lane rate-then-start ordering** (rate on the cloud worker, start on the BLE worker): ruled out of scope in Task 4b.
- **A car known only to BLE/HA getting no VehicleEndpoint** ((h) partial): ruling 3 defers it to Phase 5's presence port.
- **`WebIPCControl.processIPC` raising when TeslaAPI is not loaded** (`getModuleByName("TeslaAPI").slotFor`): pre-existing; moving it to the tick makes it less harmful (it used to be on the serial loop).
- **First tick before the Policy thread's first evaluation offering 0** (F17): pre-existing at BASE, documented in the plan.
- **`loadVehicleList` holding `vehicleListLock` across its GET and refresh**: pre-existing, named out of scope in the constraints; a single-flight waiter under it blocks for the same duration a POST would have.
- **One IPC message per second for the PHP UI** (was per 25 ms): accepted by ruling F15.
- **Heartbeat delayed up to 1 s after a flush** (every interface `send` stamps `timeLastTx`): identical to BASE, where background-thread sends stamped it too.
- **Shutdown leaving slaves without heartbeats for up to 80 s**: pre-existing.
- **Dummy interface + no scenario** behaviour for (g)/(h) users: not examined beyond "an Interface module exists, so `_blindTWCs` says blind".
- **Test-file black formatting of pre-existing compact test files**: they were unformatted at BASE by design (one-line style); only the new file is flagged (Minor 5).

## Behaviour vs main, by install shape

| Install | Verdict |
|---|---|
| Pure Gen2 (TeslaAPI disabled) | Moves to the water-fill distributor, flex and dampening gone: tagged (b), (c), (f); pinned by `test_teslaapi_disabled_install_uses_the_one_distributor` and `test_flex_settings_are_read_but_ignored` |
| Gen2 + TeslaAPI (default) | Same allocation; offers lag ≤ 1 tick (d), wiring cap re-checked every offer (e), spike gone (a); gates and lift unchanged; parity counts identical in all 51 rows |
| Gen3-only | Now controlled (g) — but see Important 1: the serial loop needs an Interface module |
| Mixed Gen2 + Gen3 | `_budgets()` reproduces `Gen2TWCs.maxPower`/`Gen3TWCs.maxPower`; the solver is untouched |
| BLE-only vehicle | Row 30: rate over BLE, 0 paid; (h) partial per ruling 3; Important 1 applies |
| Fleet-only vehicle | Row 29: one $0.001 `set_charging_amps` per hour at 16 A; Important 1 applies |
| HomeAssistant | Comment-only changes; its start/stop gate (`MIN_SEND_GAP`) unchanged |

## Assessment

**Ready to merge?** With fixes

**Reasoning:** The architecture the plan asked for landed cleanly — one writer per field, the bus written only by the serial loop, the tick never blocking on I/O, paid-call counts untouched — and the suite is green; but the PR notes advertise two install shapes ((g), (h)) that the serial loop cannot actually run without a traceback every 5 s, the tick's new fail-open failure mode is logged without a traceback, and the token refresh still has a one-line race on the field it exists to protect. Fix those three (plus the cheap tag/black/doc/template sweep) and it is ready.
