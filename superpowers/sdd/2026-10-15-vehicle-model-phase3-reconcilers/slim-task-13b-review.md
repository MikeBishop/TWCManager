# Slim Task 13b review: registry reads through the providers

Range f0327e5..fc7bd2f (e3c7d71, fc7bd2f), reviewed at fc7bd2f in wt-vm3.

**Spec compliance: PASS.** One deviation: the cascade lives in `ProviderOrder.read`, not in VehicleRegistry. It is already ruled acceptable in progress.md.
**Quality/cost safety: APPROVED.** 0 Critical, 0 Important, 3 Minor.

Suite at fc7bd2f in wt-vm3: 1675 passed, 1 xfailed, which matches the report. The tree was left clean. All mutations ran on a `git archive` copy in the scratchpad, not in wt-vm3.

## Spec checklist

| Item | Status |
|---|---|
| `Provider.FIELDS`, `Provider.fetch(vehicle, field, allowWake=False) -> bool` | Present. Provider.py:49, :71 |
| Read readiness is the provider's own `ready(vehicle, READ_CHARGE)`; suppression and cost order come from ProviderOrder | Order.py:119-124 |
| `Vehicle.read(field, maxAge, allowWake=False, providers=None, force=False)` | Vehicle.py:170-193 |
| Reconciler read-before-write passes the providers on the attempt's worker | Run.py:155-165 |
| ReadSource.py, Sources.py, registerReadSource/useReadOrder/readSources, orderReadSources and the readSource attributes are deleted | Yes. A repo-wide grep (lib, html, docs, tests) finds no remaining reference |
| Tests: free first, never wakes unless asked, force past a live feed, restricted providers, api_only skips BLE | Present and mutation-killed (below) |

## Hunt results

**Paid reads.** No new paid read and no new wake.
- `_TeslaAPIProvider.fetch` keeps the old order, deferral then free `is_awake` then paid `update_vehicle_data`, and never wakes (TeslaAPIProviders.py:46-58).
- Fleet's READ_CHARGE readiness is `available()`, meaning `fleetSlot.usable("read")`, plus `not ownerSlot.usable("read")` (TeslaAPIProviders.py:119-133). That is exactly the old `TeslaAPIReadSource.canRead`.
- `force` still only skips the freshness check (Vehicle.py:185).
- BLE wakes only under `allowWake` (TeslaBLEProvider.py:84). Only `_readFresh` and Run.py call `Vehicle.read`, and neither passes `allowWake=True`.

**Read order.** It is unchanged for every field.
- Old key: (min READS tier, rank, order, index) gave BLE(0,2), Owner(1,4), Fleet(1,5), HA(2,6).
- New key: (READ_CHARGE tier, rank, index) gives BLE(0,2), Owner(1,4), Fleet(2,5), HA(2,6).
- Fleet's tier rose from 1 to 2, but its rank already placed it after Owner, and HA still comes after Fleet. Telemetry and Gen2/Gen3 declare reads only as passive, so they never enter the walk.
- Location fields walk the same READ_CHARGE order. Every provider declares READ_LOCATION at the same cost as READ_CHARGE, so nothing changes today (see Minor 2).

**Source identity.** Unchanged.
- BLE observes as `self.name` = "TeslaBLE" (TeslaBLEProvider.py:89).
- HA observes as "HomeAssistant" (HomeAssistantProvider.py:80).
- Both API slots still observe "TeslaAPI" through the CarApiVehicle descriptors (TeslaAPI.py:41,54).
- Belief.py's `LIVE_READ_SOURCES = {"TeslaBLE","TeslaAPI","FleetTelemetryMQTT"}` (Belief.py:11) and `_readFresh`'s `obs.source == "TeslaBLE"` (TeslaAPI.py:1914) see the same strings. TelemetryProvider's name is still the class name.

**Startup.** Reads before `registerProviders` (TWCManager.py:764) now return the latest value without fetching. There are only two callers of `Vehicle.read`:
- `TeslaAPI._readFresh`, reached from `update_charge` and `update_location`. These run from the background-task thread, started at TWCManager.py:819, and from `Targets.py:111` in the reconciler, started at :826.
- `Run.runAttempt`, which runs on the reconciler.

Both start after registration. HTTP pages only queue background tasks (HTTPControl.py:732), and no module `__init__` reads.

HA readiness now requires `ha.enabled()`, which is correct. The old `HomeAssistantReadSource` was registered only on the success path of `HomeAssistant.__init__`, and every failure path there sets `_enabled = False` (HomeAssistant.py:207-268). Nothing sets it back to True, so the gate is identical.

TeslaBLE has the same gate as before. A missing or non-executable binary calls `releaseModule` before `providers()` can be collected (TeslaBLE.py:155-171), as the old registration did.

**Gen3.** No change. Gen3TWCProvider declares no READ_CHARGE, and the cloud VIN path (READ_WALL_CONNECTOR_VINS ready/available, `wallConnectorVins`) is untouched: the diff only moves `__init__` into the base class. The Gen3 tests pass.

**Locks.** `ProviderOrder.read` takes no lock (Order.py:113-133), and `Vehicle.read` calls it with none held (Vehicle.py:191-193). BLE's `_get` takes and releases `_bleLock` inside the module, and `observe` (the registry leaf) runs afterwards, as in the old cascade. `test_free_first_and_stops_at_first_success` asserts that no lock is held during a fetch. No new lock path was added.

**Size.** `git diff --numstat -- lib` gives +152 / −312 = **−160**, which is honest. Of the deletions, 202 lines are the two deleted files. The rest removes the duplicated readiness and slot plumbing, partly offset by the base class and `ProviderOrder.read`. Tests are +300 / −230.

## Mutation checks (scratch copy; each reverted)

| # | Mutation | Mapping row | Result |
|---|---|---|---|
| R1 | Walk `reversed(ordered(READ_CHARGE))` | test_free_first_and_stops_at_first_success / keeps_cost_order | KILLED (14 tests) |
| R2 | HA READ_CHARGE tier 1 (HA reads before Fleet) | provider_registration::test_home_assistant_reads_after_the_fleet_provider | KILLED (3, full suite) |
| R3 | API deferral returns False (walk continues past a deferred car) | read_cascade::test_empty_result_means_source_wrote_it_itself → reads_no_wake::test_status_deferral_counts_as_success_without_fetch | **SURVIVED** (full suite). Also survives on BASE f0327e5 (`return {}`→`None` in Sources.py). See Minor 1 |
| R4 | BLE wakes without `allowWake` | test_never_wakes_unless_asked | KILLED (2) |
| R4b | Order passes `allowWake=True` to every fetch | test_never_wakes_unless_asked | KILLED (8) |
| R5 | `providers` filter removed | test_read_with_providers_skips_other_providers; reconciler lane test | KILLED (2) |
| R6 | A raising fetch propagates | test_raising_provider_counts_as_failure_and_next_is_tried | KILLED (2) |
| R7b | `force` ignored | test_force_reads_past_a_live_feed | KILLED (full suite) |
| R8 | api_only no longer suppresses BLE reads | test_api_only_after_register_providers_never_reads_over_ble | KILLED |
| R9 | HA ready ignores `enabled()` | homeassistant_registry::test_disabled_reads_nothing | KILLED |
| R10 | `True` ends the walk even with nothing recorded | test_true_with_nothing_recorded_continues | KILLED |
| R11 | Fleet reads although Owner can (paid) | test_fleet_reads_only_when_owner_cannot, test_owner_reads_cost_nothing…[unusable] | KILLED |

Result: 11 of 12 killed. The one survivor is a gap that already existed at BASE.

## Critical

None.

## Important

None.

## Minor

**M1. The status-deferral short-circuit is not pinned, and the mapping row overclaims.**
- Evidence: TeslaAPIProviders.py:52-55 (`return True` on deferral). Mutating it to `return False` passes the full suite (R3). `test_status_deferral_counts_as_success_without_fetch` (test_reads_no_wake.py:63) passes either way, because with Owner as the only provider the read falls back to the stale latest value, and `_readFresh` accepts it under `statusDeferral`.
- Cost: if this regresses, a deferred car on an Owner+HA install pays one HA read per refresh instead of zero.
- This is not new. The equivalent mutation also survives at f0327e5.
- Fix: add a test with Owner and HA providers both ready, Owner deferred and a stored value. Assert that `HomeAssistantProvider.fetch` (or `parse_from_home_assistant`) is not called and that no request is made. Correct the mapping row.

**M2. Location fields walk and gate on READ_CHARGE.**
- Evidence: Order.py:119 and :124 use READ_CHARGE for `lat`/`lon`/`gpsAsOf`.
- This matches the old behaviour (`orderReadSources` suppressed on READ_CHARGE) and every provider prices the two capabilities identically, so the order is the same today.
- Risk: a provider that later prices READ_LOCATION differently would be misordered silently.
- Fix (one line): `capability = READ_LOCATION if field in LOCATION_FIELDS else READ_CHARGE`, used in both places. Alternatively, a comment stating the assumption.

**M3. `HomeAssistantProvider.fetch` dereferences the attachment without a guard.**
- Evidence: HomeAssistantProvider.py:79. It relies on `ready()` having checked the attachment. If the attachment is detached between ready and fetch, the result is an `AttributeError`, which the walk catches and logs at DEBUG as a failure. That is harmless, but inconsistent with `_TeslaAPIProvider.fetch`'s `None` guard (TeslaAPIProviders.py:50).
- Fix: `hv = vehicle.attachment("HomeAssistant"); if hv is None: return False`. Optional.
