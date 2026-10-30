# Follow-up: the Gen2 RS-485 link never has to be disabled

User, 2026-10-18: "Gen3 TWCs are controlled over RS485, just a different protocol. We shouldn't be making Gen3-only users
disable something they're using when we really mean something else." Then: "Fix the code."

Today (branch `vehicle-model/phase4`, HEAD 57dcea94):
- `Interface/RS485.py` is the **Gen2** master/slave link only (`config["interface"]["RS485"]`, shipped enabled on
  `/dev/ttyUSB0`). Gen3 units use their own adapter on the Neurio header, configured as `config["controller.Gen3TWCs"]["port"]`
  (a flat dotted key; default `/dev/ttyUSB1`), loaded at `TWCManager.py:~776`.
- `RS485.connect()` calls `serial.serial_for_url(...)`; with no device there, the exception aborts module load / startup.
- `TWCManager.py:~883` `hasBus = bool(master.getModulesByType("Interface"))` is fixed at startup; the serial loop idles when False.
- `VehicleEndpoint._blindTWCs` (~:143): an Interface module loaded and no slave linked → blind (an API-only car is not rated).
  So a Gen3-only or vehicle-only install must set `interface.RS485.enabled: false` to work. That requirement goes away.

## Required behaviour
1. **A Gen2 port that can't be opened never aborts startup.** The RS485 module stays loaded but disconnected (`ser` None),
   logs one ERROR naming the port and that no Gen2 TWCs can be controlled until it opens, and retries the open from the
   serial loop every 30 s (log the failure once, not every retry; log INFO when it opens). A late-enumerating USB adapter
   on a real Gen2 install is therefore picked up without a restart.
2. **The Gen2 link stands down when its port is the Gen3 controller's port** (Gen3 controller configured, enabled, same
   port string): release the module with one INFO line saying the port belongs to the Gen3 Wall Connector link. Never open
   the Gen3 adapter as a Gen2 bus.
3. **The serial loop services the bus only while it is open.** Replace the startup-fixed `hasBus` with a live check (e.g. an
   interface `connected` property / `master.busUp()`); while closed, the loop sleeps and runs the 30 s reopen. `flushRS485`,
   reads and sends must not touch a closed port (queued RS-485 messages are dropped or kept — say which and why; nothing
   may raise).
4. **Blindness follows the open link:** `_blindTWCs` blinds for "no slave linked" only while the Gen2 link is open. A
   closed link controls no TWC, so it hides no car. (Accepted consequence: while a real Gen2 adapter is unplugged, an
   API-controllable car may be rated over the API; the TWC is on its own fallback limit then, so this is harmless.)
5. With defaults untouched, a Gen3-only install (Gen3 on `/dev/ttyUSB1`, nothing on `/dev/ttyUSB0`) and a vehicle-only
   install (no adapter) start, distribute, and rate cars. No config change is needed for either.
6. Disabling the module (`enabled: false`) keeps working exactly as today.
7. The live Gen2 box (adapter present, slave linked) is unaffected: same open, same loop, same timings.

## Constraints
- Smallest correct change; lib growth target ≤ +30 net. Look for lines the change lets you delete (e.g. the startup
  `hasBus` and its comment).
- Comment rule: comments explain why the code is what it is; no history, no phase/PR/issue numbers.
- Never cut Gen3 features.
- Tests (new or extended, e.g. `tests/unit/test_rs485_interface.py`, the vehicle-only/Gen3-only control tests, the blind
  tests): open failure keeps the module loaded and disconnected without raising; reopen after 30 s succeeds and logs once;
  same-port-as-Gen3 releases; serial loop gate skips a closed link; `_blindTWCs` not blind with a closed link and no slave,
  blind with an open link and no slave; default-config Gen3-only and vehicle-only rows distribute. Existing parity tests
  (`tests/unit/test_command_path_parity.py`) unchanged.
- Docs: any doc or the CHANGELOG 1.4.0 lines that tell Gen3-only or vehicle-only users to disable RS485 are updated to say
  nothing is needed (the Gen2 link waits for its adapter); `docs/modules/Controller_Gen3TWCs.md` may say the Gen2 link
  stands down if pointed at the Gen3 port.
- Commit message: "Keep running when the Gen2 RS-485 adapter is absent" + blank line +
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.
