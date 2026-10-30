# Follow-up report: the Gen2 RS-485 link never has to be disabled

Status: DONE_WITH_CONCERNS (lib is +32 net against a +30 target; stale slaves stay listed while the link is closed, which is out of scope)
Commit: `6f59b1a4` "Keep running when the Gen2 RS-485 adapter is absent", on `vehicle-model/phase4` (parent 57dcea94). Not pushed.
Worktree: scratchpad/wt-vm4

## What today does (verified)
`RS485.connect()` calls `serial_for_url`. With no device there it raises `SerialException`. The module loader's
`except Exception` logs `FAIL: Interface.RS485 - SerialException ...` and then **re-raises** (TWCManager.py ~:763), so
startup aborts. The new sigterm test's RED run shows exactly this.

## Implemented, per behaviour
1. **An unopenable port never aborts startup.** `RS485.connect()` wraps the open in `try/except Exception`. On failure it
   sets `ser = None` and `timeOpenFailed = now`, and logs one ERROR only when `timeOpenFailed` was 0:
   `No Gen2 TWCs can be controlled until <port> opens: <exc>`. On a later success it logs INFO `Opened RS485 port <port>`
   and clears the flag. While closed, `connect()` returns at once until 30 s have passed since the last failed try.
   The module stays registered and is not released.
   The no-port release is unchanged. `KeyboardInterrupt` is not an `Exception`, so SIGTERM still gets through.
2. **The Gen2 link stands down on the Gen3 port.** In `RS485.__init__`, after the port is resolved: if
   `config["controller.Gen3TWCs"]` is enabled and its `port` (default `/dev/ttyUSB1`) equals the Gen2 port, it logs one
   INFO line, `<port> belongs to the Gen3 Wall Connector link`, releases the module and never calls `serial_for_url`.
   This reads config because the Gen3TWCs module registers after the module loop.
3. **The loop services the bus only while it is open.** The new `TWCMaster.busUp()` returns True when an interface is
   loaded and `getattr(ref, "connected", True)` is true. Dummy and TCP have no `connected` attribute, so they count as up.
   `RS485.connected` is `ser is not None`. The startup-fixed `hasBus` and its comment are gone.
   - The loop runs `if not master.busUp(): (if an interface is loaded: getInterfaceModule().connect()); continue`. The
     existing 25 ms top-of-loop sleep is the "sleep while closed", and `connect()` throttles itself to one try per 30 s.
   - Shutdown flushes and closes only `if master.busUp()`.
   - On a closed port, `getBufferLen()` returns 0, `send()` returns without writing and `close()` does nothing. This
     covers a failure partway through an iteration: one write loses the port, the reopen fails, and later sends or
     polls in the same iteration then see `ser is None` and stop.
   - `read()` has no guard because it can't reach a closed port. The loop calls it only right after a positive
     `getBufferLen()`, on the same thread, with nothing in between. A `read()` that loses the port itself already
     returns `b""` through the existing except clause.
4. **Blindness follows the open link.** `_blindTWCs` blinds for "no slave linked" only when `master.busUp()` is true.
   The docstring now says a closed link controls no TWC.
5. **Default-config Gen3-only and vehicle-only installs work with no config change.** The shipped RS485 (`/dev/ttyUSB0`,
   absent) loads closed, so it neither blinds nor raises. The tests below cover this with a real `RS485` and a real
   `TWCMaster`, and with a real process start.
6. **`enabled: false` is unchanged.** The module is skipped or released as before, and `busUp()` is False with no
   interface. The existing `test_an_install_with_no_interface_runs_and_shuts_down_cleanly` still passes.
7. **The live Gen2 box is unaffected.**
   - Startup: `ser` is None and `timeOpenFailed` is 0, so the throttle condition (`now - 0 < 30`) is false and the
     open goes ahead exactly as before.
   - Mid-run reconnect after a `SerialException`: the stale `ser` is not None, so the throttle is skipped and the
     reopen is immediate, as before. When it succeeds, nothing new is logged.
   - Loop cost: one `getModulesByType` walk and one attribute read per 25 ms iteration. The read loop already does that
     walk through `getInterfaceModule()`.
   - `send()`/`getBufferLen()` gain one `is not None` check each. Heartbeat, linkready and RX timings are untouched.
   - The only Gen2 behaviour change is a reopen that **fails**. Before, `connect()` raised out of the except clause into
     the main loop's catch-all, again on every 25 ms iteration. Now the link closes, the failure is logged once, and the
     open is retried every 30 s.

## Queued RS-485 messages while closed: kept
`flushRS485` sits after the gate, so while the link is closed nothing is sent and nothing is dropped. The outbox drains
on the first iteration after it reopens.
- **Why keep them:** each queued message is something a person (HTTP or WebIPC) or the reconciler (Gen2TWCProvider
  start/stop) asked for. The reconciler cannot tell a dropped send from a delivered one, so delivering late keeps its
  record true. Keeping them also costs no code.
- **Why the queue stays small:**
  - The automatic enqueuers live inside the gated loop: VIN retries (`retryVINQuery`) and the kWh poll trigger.
  - `getSlaveLifetimekWh` and `sendStart/StopCommand` iterate `getSlaveTWCs()`. A Gen3-only install has no slaves, so
    its outbox stays empty.
  - During a Gen2 outage the outbox holds only what was asked for in the meantime.
- **Cost:** a short burst of sends when the link reopens.

## Tests (12 new; full suite 1966 passed, 1 xfailed, baseline 1954 passed, 1 xfailed)
- `tests/unit/test_rs485.py`:
  - `test_a_port_that_cannot_open_leaves_the_link_loaded_and_closed`
  - `test_the_link_reopens_every_30_s_and_logs_once`: no retry at +29 s, a retry at +30 s, one ERROR in total, then a
    successful open after another 30 s logs exactly one INFO naming the port
  - `test_a_closed_link_is_neither_polled_nor_written`: `getBufferLen`, `send` and `close` on `ser=None`
  - `test_a_write_that_loses_the_port_closes_the_link_without_raising`: the mid-iteration case
  - `test_the_gen3_port_is_never_opened_as_a_gen2_bus`
  - `test_the_gen2_link_opens_beside_the_gen3_on_another_port`: Gen3 enabled on another port, or Gen3 disabled on the
    same port
- `tests/unit/test_rs485_serial_only.py`:
  - `test_the_bus_is_up_only_while_an_interface_is_open`: real TWCMaster
  - `test_the_serial_loop_skips_a_closed_link_and_retries_it`: source order is gate, then reopen and `continue`, then
    flush
- `tests/unit/test_vehicle_endpoint.py`: `test_no_slave_linked_blinds_only_while_the_gen2_link_is_open`
- `tests/unit/test_control_tick.py` (real `RS485` on the shipped `/dev/ttyUSB0` with no device, registered on a real
  master):
  - `test_a_gen3_only_install_with_default_config_is_controlled`: the Gen3 gets its target and a car on a mobile
    connector is rated 20 A
  - `test_a_vehicle_only_install_with_default_config_is_controlled`
- `tests/unit/test_sigterm_shutdown.py`: `test_an_absent_gen2_adapter_does_not_stop_startup`. A real process with
  RS485 enabled on a nonexistent port reaches the main loop, logs the ERROR exactly once over about 3 s of loop, prints
  no traceback and shuts down cleanly. Its ~3 s of loop runs the 25 ms gate and the throttled reopen.
- `tests/unit/test_command_path_parity.py` is unchanged (`git diff --quiet 57dcea94` passes).

Deleted-test rule: no test was deleted or rewritten. Two PLUMBING-ONLY edits:
- The comment in `test_a_gen2_install_with_no_slave_linked_sends_no_amps` dropped "a dead adapter", which is no
  longer a blind case.
- `test_vehicle_endpoint.master()` gained `m.busUp = lambda: False`. Its master is a bare Mock, and that matches the
  helper's existing "no RS-485 interface loaded".

## TDD evidence
RED, before any lib change:
```
$PY -m pytest tests/unit/test_rs485.py tests/unit/test_rs485_serial_only.py tests/unit/test_vehicle_endpoint.py tests/unit/test_control_tick.py -q --timeout=60 -p no:cacheprovider
E   AttributeError: 'NoneType' object has no attribute 'inWaiting'
E   AssertionError: Expected 'serial_for_url' to not have been called. Called 1 times.
E   AttributeError: 'RS485' object has no attribute 'connected'. Did you mean: 'connect'?
E   AttributeError: 'TWCMaster' object has no attribute 'busUp'
E   ValueError: substring not found
======================== 11 failed, 64 passed in 1.56s =========================

$PY -m pytest tests/unit/test_sigterm_shutdown.py -k absent ...
E   Failed: main loop never started; output:
E   ... FAIL: Interface.RS485 - SerialException: [Errno 2] could not open port .../ttyUSB0: [Errno 2] No such file or directory
FAILED tests/unit/test_sigterm_shutdown.py::test_an_absent_gen2_adapter_does_not_stop_startup
```
GREEN:
```
$PY -m pytest tests/unit/test_rs485.py tests/unit/test_rs485_serial_only.py tests/unit/test_vehicle_endpoint.py tests/unit/test_control_tick.py tests/unit/test_sigterm_shutdown.py -q --timeout=90 -p no:cacheprovider
============================== 80 passed in 9.16s ==============================
$PY -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider
============ 1966 passed, 1 xfailed, 1 warning in 98.40s (0:01:38) =============
```
The one warning is also present in the baseline run.

## Files changed
- lib/TWCManager/Interface/RS485.py: open/reopen, `connected`, Gen3 stand-down, closed-port guards
- lib/TWCManager/TWCMaster.py: `busUp()`
- lib/TWCManager/TWCManager.py: live gate and reopen in the loop, `hasBus` removed, shutdown gate
- lib/TWCManager/EVSEInstance/VehicleEndpoint.py: `_blindTWCs` uses `busUp()`, docstring updated
- CHANGELOG.md: one 1.4.0 Bugfixes line. No existing doc or CHANGELOG line told users to disable RS485, so nothing
  needed rewording.
- docs/modules/Controller_Gen3TWCs.md: a Gen3-only install can leave the shipped Gen2 settings as they are. The link
  waits for an adapter, and stands down on the Gen3 port.
- tests: test_rs485.py, test_rs485_serial_only.py, test_vehicle_endpoint.py, test_control_tick.py,
  test_sigterm_shutdown.py

## Line reporting
- lib .py lines: 26490 before, 26522 after.
- `git diff --shortstat 57dcea94 -- lib`: 4 files changed, 44 insertions(+), 12 deletions(-), so **+32 net** against
  a target of ≤ +30.
- The two lines over are the `getBufferLen`/`send` closed-port guards. Requirement 3's "nothing may raise" needs them
  for the mid-iteration failure case.
- Already trimmed: no `connected` on Dummy/TCP (`getattr` default), no separate `reopen()` (`connect()` throttles
  itself), no `read()` guard, `hasBus` and its comment deleted.

## Self-review
- **Behaviours:** all 7 covered as above.
- **YAGNI and patterns:** `connected` is an interface attribute with a `getattr` default; `busUp` sits beside
  `getInterfaceModule`; the release uses the module's existing `releaseModule` pattern.
- **Threading:** `connect()` runs only on the serial thread (the loop and RS485's own error paths). The control tick
  reads `busUp()`, which does no I/O. No new locks.
- **Comments:** they explain why (the 30 s retry finds a late USB adapter, a closed link controls no TWC). No history,
  phase or ruling IDs.
- **Checks:** `git grep -nw hasBus` is empty. black is clean on touched files. `test_vehicle_endpoint.py` was not
  black-formatted at HEAD, so it was left as is.

## Concerns
1. **Lib +32 vs ≤ +30**, explained above.
2. **Stale slaves while closed.** The slave timeout and scratch run inside the gated heartbeat branch. If a Gen2 adapter
   is unplugged mid-run, known slaves stay listed for the whole outage, and each 30 s `connect()` try refreshes their
   `timeLastRx`. While that lasts:
   - The distributor keeps making offers to TWCs it can't reach.
   - `_blindTWCs` still weighs their last reported state.
   - So the brief's accepted consequence ("an API-controllable car may be rated over the API") applies only when no
     slave had linked before the link closed.

   This is harmless: the TWC is on its own fallback limit, and the slaves time out normally after the link reopens. I
   left it alone because fixing it would touch Gen2 timing and the brief didn't ask for it.

## Fix round 1

Commit: `8754a516` "Drop RS-485 messages queued while the link is closed", on top of 6f59b1a4. Not pushed.
This replaces the "Queued RS-485 messages: kept" section above: they are now **dropped**.

1. **Messages queued while the link is closed are dropped (Important).**
   - `TWCMaster.flushRS485()` starts with `if not self.busUp()`. In that case it clears the outbox, logs
     `Dropped N RS-485 messages: the link is closed` at INFO when N > 0, and returns 0.
   - The closed-link branch of the serial loop calls `master.flushRS485()` before `continue`, so the outbox is emptied
     on every closed iteration and nothing queued during an outage is sent when the link reopens.
   - The comment gives the reason: sent late, a stop could reach a car that should be charging by then.
   - On an open link, `flushRS485` does one extra `busUp()` check per iteration and nothing else changes.
   - No earlier test asserted "kept". The new tests:
     - `test_messages_queued_while_the_link_is_closed_are_dropped`: real TWCMaster, `sendStopCommand` to two slaves
       while closed. The flush returns 0 and logs "Dropped 2". After the link reopens, the flush sends nothing.
     - `test_the_closed_link_branch_drops_the_outbox`: source order is gate, then flush, then `continue`.
2. **An unplugged adapter's `OSError` reaches the close-and-retry path (Minor).**
   - `getBufferLen`, `read` and `send` now catch `OSError`. `SerialException` subclasses it, and a vanished USB device
     raises a plain EIO `OSError` from the ioctl.
   - The new test `test_an_unplugged_adapter_reconnects` raises `OSError(5)` from `inWaiting` and checks that it
     reconnects.
3. **The `close()` guard is reverted** to `return self.ser.close()`. Its only caller is already under `busUp()`. The
   `rs.close()` call was removed from `test_a_closed_link_is_neither_polled_nor_written`.

TDD:
- RED, before the fix: `test_an_unplugged_adapter_reconnects` failed with `OSError: [Errno 5]`. The drop test failed
  with `assert 2 == 0` from `flushRS485()`. The source-order test failed with flush not before `continue`.
- GREEN, covering tests (`test_rs485`, `test_rs485_serial_only`, `test_control_tick`, `test_vehicle_endpoint`,
  `test_sigterm_shutdown`, `test_gen2twc_provider`): 97 passed.
- Full suite: **1969 passed, 1 xfailed**. That is the earlier 1966 plus 3 new tests; the one warning is pre-existing.
- test_command_path_parity.py is still unchanged.

Lines:
- lib .py total is 26531, against 26522 after round 0 and 26490 at 57dcea94.
- This round adds +9 net in lib. Cumulative `git diff --shortstat 57dcea94 -- lib` is 55 insertions(+), 14
  deletions(-), so **+41 net** against the +30 target.
- The extra lines are the drop branch the review asked for. black expands its `logger.info` call to 3 lines.
