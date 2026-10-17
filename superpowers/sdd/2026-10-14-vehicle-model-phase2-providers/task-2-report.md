# Task 2 report: Suppressions and the fixed ProviderOrder

Status: DONE_WITH_CONCERNS (one minor concern: the wiring is not in place yet, see below)
Commit: 02ed0d7 on vehicle-model/phase2 (parent 84316de)

## TDD
- The test file was copied verbatim from the brief to tests/unit/test_provider_order.py.
- Failing run: `E   ModuleNotFoundError: No module named 'TWCManager.Vehicle.Providers.Order'` (collection error).
- After implementation, the Step 4 set passed: test_provider_order + test_registry_read_cascade + test_registry_membership, 66 passed.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): 1176 passed, 1 xfailed, 1 warning. That is 1157 + the 19 new tests.

## Files
- New: lib/TWCManager/Vehicle/Providers/Suppressions.py, lib/TWCManager/Vehicle/Providers/Order.py.
- Modified:
  - Registry/ReadSource.py: `provider: str = ""`.
  - Registry/VehicleRegistry.py: `_readOrder`, `useReadOrder`, `readSources` (fn called outside the lock on a snapshot).
  - Providers/__init__.py: exports Suppressions, ProviderOrder and registerProviders.
- black was run on the Providers/ and Registry/ dirs. It only reformatted the new files; git diff shows no unrelated changes.

## Implementation notes
- Logging uses the stdlib `logging.getLogger("TWCManager.Vehicle.Providers")` pattern, as Registry does, so caplog sees it. Exceptions are logged by type name only, so no token or message is ever logged.
- Suppressions:
  - The config commandPolicy is validated once in `__init__`; an invalid value logs an error once, as VehiclePriority does.
  - Settings are re-read on every call.
  - `explicit()` ignores malformed input name by name: a non-dict top level, a non-str key, a non-list value, or an unknown or non-str capability. `"*"` maps to ALL. The config dict replaces the settings entry per provider (dict.update).
- ProviderOrder:
  - The provider list is copy-on-write: `register` builds a new list and replaces in place to keep the index. There are no locks anywhere.
  - In `candidates`, filters run in this order: readiness (raise counts as not ready), then the amps range filter (an unknown range is kept), then the paid-amps rule on the ready survivors.
  - `dispatch` skips module-less providers, increments moduleFailures once per exhausted provider and moduleSuccess on success, and returns literal False when nothing succeeds.
  - `orderReadSources` sorts a provider with no READ_* declaration like an unknown one (tier 9).
- `available()` raising counts as not available, logged at DEBUG.
- One small addition beyond the brief: in `debugCommand`, a non-dict JSON body is treated as `{}`, and a `charge_rate` that cannot be parsed as a number returns False rather than raising.

## Concerns
- Nothing calls `registerProviders` or creates `master.providerOrder` yet. TWCManager.py is not in this task's Files list, so I left it alone. A later task must create `master.providerOrder = ProviderOrder(master)`, call `registerProviders(master)` after the module-load loop, and install `vehicleRegistry.useReadOrder(master.providerOrder.orderReadSources)`.
- `noticeOnce()` is likewise not called anywhere yet.
