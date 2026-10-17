# Task 2 review: Suppressions and the fixed ProviderOrder (84316de..02ed0d7)

**Spec compliance: ✅**
**Quality: Approved** (Minor findings only)

Tests: `tests/unit/test_provider_order.py` matches the brief byte for byte. The Step 4 set (with test_registry_read_cascade and test_registry_membership) gives 66 passed.

## Spec compliance

- Every Interfaces name exists with the brief's signature:
  - Suppressions: `VALID_COMMAND_POLICIES`, `commandPolicy`, `commandPolicyOverridden`, `explicit`, `suppressed`, `noticeOnce` (the once-flag is per instance).
  - ProviderOrder: `suppressions`, `register` (keeps the replaced provider's index), `provider`, `providers`, `orderKey`, `ordered`, `candidates`, `orderReadSources`, `dispatch`, `debugCommand`.
  - Module level: `registerProviders`.
  - Registry: `ReadSource.provider`, and `VehicleRegistry.useReadOrder` / `readSources`.
  - `__init__.py` exports all of them.
- The commandPolicy mapping matches today's `VehiclePriority` (lib/TWCManager/Vehicle/VehiclePriority.py:37-76) and `TeslaBLEReadSource.canRead` (Registry/Sources.py:39):
  - The config override is validated once, logs an error once, and then falls back to settings.
  - An invalid settings value becomes `prefer_ble`.
  - `ble_only` blocks every non-local provider's COMMANDS. This now covers HomeAssistant as well as TeslaAPI, as the brief specifies.
  - `api_only` blocks TeslaBLE for every capability, including its read source through `orderReadSources`.
- Cost safety holds:
  - `ordered` sorts by tier first, so a ready, unsuppressed free provider is always tried before a paid one.
  - The paid-amps rule (Order.py:204-211) drops tier >= BILLED whenever a ready local candidate covers the target, or the target is unknown.
  - `dispatch` skips module-less TWC providers, so in that case it returns False instead of falling through to Fleet. The brief requires this, and `test_dispatch_skips_providers_without_a_module` covers it.
- The implementer's concerns:
  - Wiring deferred (`master.providerOrder`, the `registerProviders` call, `useReadOrder`, `noticeOnce`): correct per plan (Task 3 / Task 8). TWCManager.py is not in this task's Files.
  - debugCommand returns False for a non-numeric `charge_rate`, and treats a non-object JSON body as `{}`: **acceptable**. The brief's formula would raise there (`.get` on a list, `float("abc")`), and "never raise from a debug endpoint" is the evident intent. This is defensive hardening, not scope creep.

## Findings

### Critical
None.

### Important
None.

### Minor

1. **Order.py:270-274: `OverflowError` escapes debugCommand.**
   - `{"charge_rate": 1e999}`, `"inf"` or `"Infinity"` reaches `int(float(...))`, which raises OverflowError. That error is not a ValueError, so it is not caught. Probed: all three raise.
   - Fix: catch `(TypeError, ValueError, OverflowError)`.

2. **Order.py:207-208 + brief rule: a local provider with an unknown `ampsRange` never counts as the local amps path once `amps` is given.**
   - Probe: `twc(amps=None)` + fleet with amps=10 gives `["Gen2TWC", "FleetAPI"]`. Dispatch skips the module-less TWC, so Fleet would be billed.
   - This matches the brief's literal rule, and the below-floor case is in the spec (design spec :104, layered actuators), so it is not a defect here.
   - It is a downstream constraint, though. Tasks 4 to 7 must guarantee that `ampsRange()` is non-None whenever `ready()` is True for Gen2TWC, Gen3TWC and TeslaBLE. Otherwise the cost-safety rule has a silent hole, and a later task could break this task's guarantee without touching this code.

3. **Suppressions.py:79-88: `explicit()` re-parses settings and config on every `suppressed()` call.**
   - That happens once per provider per `ordered()` / `orderReadSources()` walk. With a malformed setting, the DEBUG "Ignoring ..." lines repeat on every walk.
   - This is harmless at DEBUG and keeps settings live, as intended. Optionally cache on `id()` of the raw value, or log a given malformed shape only once.

4. **Suppressions.py:82-84: config replaces a provider's settings entry; it does not union with it.**
   - Config `{"FleetAPI": []}` un-suppresses a settings `{"FleetAPI": ["setAmps"]}`.
   - "Merged over" allows this reading, and it is reasonable (config wins). Say so in the docs or settings help when the setting is documented.

5. **Order.py:231-235: `_count` does a read-modify-write on `master.stats` dicts without a lock.**
   - Concurrent HTTP-thread and worker-thread dispatches can lose an increment. The existing stats counters work the same way, and these are diagnostics only. No change needed.

6. **Robustness: only `ready()` and `available()` are guarded.**
   - A provider whose `declarations()`, `ampsRange()` or `attempts()` raises propagates out of `ordered` / `candidates` / `dispatch`.
   - Through `useReadOrder` it also propagates out of `VehicleRegistry.readSources()`, the read cascade.
   - Concrete instance: `_parse` iterates a dict that lives in `master.settings`, on the read-cascade path. If the HTTP thread ever mutated that nested dict in place, `RuntimeError: dictionary changed size during iteration` would escape `readSources()`. "Never raises" holds for shape, not for concurrent mutation. Settings saves most likely replace the reference.
   - This is within the brief. Consider wrapping the per-provider body of `ordered`, and the `orderReadSources` tier computation, in the same try/DEBUG pattern, so one bad provider cannot stall reads or commands.

## Checked and fine

- Malformed `providerSuppressions` never raises. Probed with: non-dict top level, an int, a non-str key, a `None` value, nested lists or dicts inside the capability list, and every case in the brief's parametrize.
- Thread safety:
  - The provider list is copy-on-write.
  - `readSources` snapshots under the registry lock and calls the ordering fn outside it, so the leaf-lock rule holds.
  - No lock is held during dispatch.
- Exception logging records the type name only, so no token text reaches the logs.
