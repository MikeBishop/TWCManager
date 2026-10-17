### Task 13b: Registry reads through the providers (expected lib Δ ≈ −150)

Audit item 7.

**Files:**
- Modify: `Registry/VehicleRegistry.py` (`cascade` walks `providerOrder.ordered(READ_CHARGE)`), `Registry/Vehicle.py`, `Providers/Provider.py`, `TeslaBLEProvider.py`, `TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `Providers/Order.py`, `Reconcile/Reconciler.py` (read-before-write filter), and the `readSource` attributes on TeslaBLE/TeslaAPI/HomeAssistant.
- Delete: `Registry/ReadSource.py`, `Registry/Sources.py`, `VehicleRegistry.registerReadSource/useReadOrder/readSources` and `ProviderOrder.orderReadSources`.
- Test: `test_registry_read_cascade.py` is retargeted to providers; read-source registration tests are deleted.

**Interfaces:**
- `Provider.FIELDS: FrozenSet[str] = frozenset()` and `Provider.fetch(self, vehicle, field, allowWake=False) -> bool` (what `ReadSource.fetch` did).
- Readiness for a read is the provider's own `ready(vehicle, READ_CHARGE)`. Suppression and cost order come from `ProviderOrder`, as for commands.
- `Vehicle.read(field, maxAge, allowWake=False, providers=None, force=False)`: `providers` replaces `sources`.
- The reconciler's read-before-write passes the providers on the attempt provider's `worker`.

- [ ] **Step 1: Tests.** Retarget the cascade tests: free first, never wakes unless asked, `force` past a live feed, restricted to the given providers, `api_only` skips BLE.
- [ ] **Step 2–4:** FAIL → implement → full suite PASS.
- [ ] **Step 5: Commit.** `git commit -m "Read vehicle fields through the providers; the parallel read-source classes go"`

