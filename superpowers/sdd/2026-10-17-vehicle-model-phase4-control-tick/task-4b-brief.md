# Task 4b: Set the rate before the start (reconciler ordering guarantee)

User, 2026-10-17: when tracking solar it matters that the charge rate is set before the start command, to minimise overshoot.
Today parity row 26 sends set-amps before charging-start only because of timing in Task 4 (the offer is computed right
after the reply in the same beat). Make it a guarantee in the reconciler instead.

## Requirement
- In `lib/TWCManager/Vehicle/Reconcile/Reconciler.py`, when AMPS and a CHARGING start (desired True) are both due for the same
  car in the same planning pass, the AMPS attempt is planned and sent before the CHARGING start. The aspect order becomes
  CHARGE_LIMIT, AMPS, CHARGING (currently CHARGE_LIMIT, CHARGING, AMPS at ~line 94). The existing limit-then-start gap
  (~line 83, check ~384) is unchanged: a start still waits for a just-raised limit.
- A CHARGING stop is not delayed by a pending amps change (a stop should not wait behind a rate); if the reorder would put a
  stop behind an amps send, keep stop-first for stops. Decide the smallest correct rule and test both.
- No change to paid-send caps, send gaps, wake rules or which providers are chosen.

## Tests (test-first)
- A car with a start and an amps change due on the same pass: the provider receives set_amps before start (BLE and Fleet
  providers, through the real reconciler walk, e.g. tests/unit/test_limit_reconciler.py / test_charging_reconciler.py helpers).
- A stop and an amps change due on the same pass: stop is not delayed behind amps.
- test_command_path_parity.py: all request COUNTS unchanged; row 26 keeps set-amps before charging-start. If any other row's
  command ORDER changes, list it with before/after and why in the report.

## Constraints
Global constraints: global-constraints.md in this directory. Lib must not grow (target ≤ +5 net). Map any changed test.
