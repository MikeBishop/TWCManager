# X2 report: Trim the desired store and provider declarations

Status: DONE_WITH_CONCERNS. Commit: see `git log -1` on vehicle-model/phase5 (message "Trim the desired store and provider declarations"). Not pushed.

## A2 (Desired.py)
- Removed `DesiredStore.decision()` (no caller), `settled()` and `_settled()`, `ASPECTS` and `_checkAspect` with its 8 calls.
- `adopt` keeps its explicit ValueError (test_outcome_desired pins it).
- `AttemptRecord.newDesire()` is now `self.__dict__.update(self._FRESH)` (a class-level dict of the 15 volatile fields) plus the UNSUPPORTED-only `excluded` filter. It never touches `inFlight`, `lastProvider`, `lastSentAt` or `pendingSave`, and does not go through `__init__`.
- Behaviour note: an unknown aspect no longer raises ValueError in set/clear/clearIf/get/record/noteOutcome (the audit accepts this; no test pinned it).
- Tests: the 7 `settled(` asserts (test_limit_reconciler, test_outcome_desired, test_presence) now call a new helper `settled(store, key, aspect)` in tests/unit/reconcile_helpers.py with identical semantics (record.settledAt not None and >= desired.at, False when no desire). No assertion loosened.

## A4 (providers)
- `Capability.Declaration` removed; `DECLARATIONS` is `{capability: Cost}`. `Provider.cost()` returns the Cost directly; Order.ordered tests `capability not in p.declarations()`.
- `declarations()` kept as a method (Mock and test-double providers override it; test_wall_connector_vins uses `declarations.return_value`).
- BLE and HA `CAPABILITIES` removed: `dict.fromkeys(COMMANDS | {READ_CHARGE}, LOCAL)` and `dict.fromkeys((COMMANDS - {WAKE}) | {READ_CHARGE}, HA_BILLED)`; their `ready()` uses `self.declares(...)`. Owner/Fleet tables shrunk; `WALL_CONNECTOR_VINS` constant folded into `CLOUD_FREE`.
- `ampsRange` x3: one module function `carAmpsRange(vehicle, master)` in Provider.py (not a base default; base stays None). TeslaAPI's version is now tolerant of a missing config key like BLE/HA (was `config["config"]`, KeyError).
- Gen2 `setAmps` removed (no production caller). **Gen3 `setAmps` kept**: the audit says only test_gen2twc_provider calls them, but test_gen3twc_provider.py:102,107,108 call Gen3's `setAmps` and assert fake-Neurio behaviour (`setHouseWatts`); dropping it would need removing those assertions, which the brief forbids.
- Tests: `C.Declaration(x)` -> `x` in 12 files (mechanical, paren-matched); `declaration._replace(cost=tier)` in ScriptedProvider -> `dict.fromkeys(caps, tier)`; test_provider_tables `D(...)` -> plain Cost; `"rateLimit" not in C.Declaration._fields` -> `C.Cost._fields` (same intent). Deleted `test_set_amps_publishes_a_target_for_the_heartbeat` (Gen2 setAmps removed per audit; the heartbeat/pointAmps path is covered by test_charging_points and test_control_tick).

## A10
- `POWER_FLOWING_AMPS` single definition in Belief.py; VehicleEndpoint imports it.
- `Run.workerOf(provider)` is `getattr(provider, "worker", "cloud")` (None gives "cloud"), reused at the two other getattr sites; Reconciler passes `providerOrder.provider(name)`.

## Tests run
`tests/unit + tests/EMS`: 2035 passed, 1 warning (baseline 2036; the one fewer is the deleted Gen2 setAmps test). test_command_path_parity untouched. black --check clean on all 12 touched lib files (tests not reformatted, they use compact style).

## Lib delta
Before 26509, after 26430: net -79 (`git diff --shortstat -- lib`: 84 insertions, 163 deletions) vs estimate -86. Shortfall about 7: Gen3 `setAmps` kept (about 3) and the shared `carAmpsRange` helper adds about 10 lines against the three bodies it replaces.

## Concerns
- The audit's A4 claim about Gen3 `setAmps` is wrong (see above); Gen3 `setAmps` is worth reconsidering only together with its tests.

## Fix round 1
Commit "Drop dead Gen3 setAmps; one source for a desire's fresh fields".
1. Gen3TWCProvider.setAmps deleted (SET_AMPS declaration kept). In test_gen3twc_provider the setAmps call and its setHouseWatts assertion, the setAmps term in test_gen3_commands_return_outcomes and the lambda loop entry were dropped; the remaining assertions are unchanged.
2. AttemptRecord.__init__ now sets only the persistent fields (inFlight, lastProvider, excluded, lastSentAt, pendingSave) and then updates from `_FRESH`; newDesire uses `_FRESH` too. All `_FRESH` values are immutable, so sharing is safe. Field comments moved beside `_FRESH`.
3. `settled` test helper now uses `store.peek` and `state.records.get` (no record created); two blank lines after the imports.
Tests: tests/unit + tests/EMS 2035 passed, 1 warning.
Lib delta vs f9015bd1: see the shortstat in the reply (cumulative for X2).
