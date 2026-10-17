### Spec Compliance
Compliant. Every success path in the brief stamps once with the value sent, via a non-creating lookup. Verified in the code; the 29 focused tests pass.
- TeslaAPI.py:1870-1878 `_recordChargeRate` is reached only when the response is accepted. The below-5A double send records only after both sends are accepted. The skip-repeat early return does not stamp. The lookup is `getattr(vehicle, "_liveVehicle", None)` followed by a call, so the attribute-only fake keeps working. `_liveVehicle` is `registry.get`, which has no side effects.
- TeslaAPI.py:2505-2507 `apply_charge_limit` stamps `limit` only on `result is True or already_set` (accepted per controller ruling). Read-only refusal, retry-backoff and failure paths do not stamp.
- TeslaBLE.py:625-634 `_stampWrite` upper-cases the VIN, uses `registry.get` and skips on None. The try/except keeps a stamp failure from breaking the command path. Call sites: 663 (per-vehicle, only if `success`), 695 (all-vehicles, per success), 800 (limit, `target_limit`, so a -1 restore stamps the outside value). Wake failure or `ret None` returns before the stamp. A skipped restore or an already-applied vehicle `continue`s before the stamp.
- HomeAssistant.py:684-686 stamps only after `_call_service` ok, using the `limit` sent. Limit -1 and the "already at limit" or not-connected skips `continue` before it. The VIN is upper-cased and the lookup is non-creating.
- Locks: the registry lock is a leaf and no settingsLock is taken. Stamping under `_bleLock` is fine.
- Black: the diff has no unrelated reformatting. The only wrapped line is the new one at TeslaBLE.py:695.

### Strengths
- Tests cover success, failure, an unparsed failure, an unknown vehicle, restore, and not reviving a forgotten vehicle. They also cover the attribute-only fake.
- The `_stampWrite` helper is small and its failures are isolated.
- The follow-up commit cfb39fd fixed an initial revive-on-write problem.

### Issues
Critical: none.
Important: none.
Minor:
- HomeAssistant.py:693-756 `setChargeRate` does not stamp `availableCurrent` after a successful `_call_service`. This is outside the brief's file ranges, but the brief's own check names HomeAssistant as a charge-rate path. The Phase 3 own-write reads would then see no stamp for HA-driven rates. Add a non-creating stamp of the clamped `amps` (a float, e.g. 16.0; the other modules stamp ints), or record it as a known gap. Also note that the "not connected" and "already matches" early returns correctly do not stamp.
- TeslaAPI.py:1870 `_recordChargeRate` stamps the post-clamp `int` rate. This is correct and is the value sent.

### Assessment
**Task quality:** Approved
**Reasoning:** Every write path in scope stamps only on success, with the value sent and a non-creating lookup. There are no lock-order problems and no stray reformatting. The one gap is the HA charge-rate path, which the brief did not list, so it is Minor.
