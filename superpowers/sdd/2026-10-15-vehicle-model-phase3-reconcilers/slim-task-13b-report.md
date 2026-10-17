# Slim Task 13b report: registry reads go through the providers

**Status:** DONE_WITH_CONCERNS (minor; see Concerns)
**Branch:** vehicle-model/phase3 in wt-vm3. BASE is f0327e5.
**Commits:**
- e3c7d71 Read vehicle fields through the providers; the parallel read-source classes go
- fc7bd2f Pin that a provider registered twice reads once

**Tests:** full suite (`tests --ignore=tests/API --ignore=tests/integration`) gives 1675 passed and 1 xfailed. BASE was 1670 passed and 1 xfailed.
**Lib delta (non-test):** +152 / −312 = **−160**. The expected figure was about −150. Tests are +300 / −230.

## What changed

- `Provider` gains `FIELDS: FrozenSet[str] = frozenset()` and `fetch(vehicle, field, allowWake=False) -> bool`. `fetch` returns True when the provider now vouches for `vehicle.latest(field)`, and the provider records its own observations.
  - **TeslaBLEProvider:** `FIELDS = CHARGE_FIELDS | LOCATION_FIELDS`. It does the old `TeslaBLEReadSource` read: charge or location, one `wakeVehicle` retry only under `allowWake`, None values dropped, and observations stamped "TeslaBLE". It returns True only when the requested field came back non-None, so a reply without that field still falls through to the cloud (P14).
  - **OwnerAPI and FleetAPI:** both now share a `_TeslaAPIProvider` base. The base holds the shared `__init__`, `FIELDS` and a single `fetch`, and `slotName` selects the slot. The fetch keeps the old order: status deferral first (returns True with no request), then the free `is_awake`, then the paid `update_vehicle_data`. It never wakes. Observations stay "TeslaAPI" for both slots, via the CarApiVehicle descriptors.
  - **HomeAssistantProvider:** `FIELDS = HA_FIELDS`. `fetch` parses the entities, observes as "HomeAssistant", and returns `field in seen`.
  - `CHARGE_FIELDS` and `LOCATION_FIELDS` now live in `Providers/Capability.py`, so each is defined once.
- **`ProviderOrder.read(vehicle, field, allowWake, providers)`** is the cascade. It walks `ordered(READ_CHARGE)`, so suppression, `available()` and the cost tier/rank order are the same as for commands. It skips providers without the field and those not in `providers` (given as objects or names). Each provider's `_ready(…, READ_CHARGE)` is asked **just before** its fetch, as `canRead` was. That keeps the case where a refused Owner read hands reads to Fleet in the same walk. A raising fetch logs only its exception type.
- **Deviation from the brief, for deduplication:** the brief puts `cascade` in VehicleRegistry. I put the walk on `ProviderOrder`, because it reuses `ordered()` and `_ready()` (including its exception handling) rather than duplicating them. It also keeps the Registry package free of any import from Providers. The registry holds only an opaque `providerOrder` reference, which TWCMaster sets where `useReadOrder` used to be called.
- **`Vehicle.read(field, maxAge, allowWake=False, providers=None, force=False)`:** `providers` replaces `sources`. With no registry, or a registry with no `providerOrder`, it returns the latest value and never fetches.
- **Reconciler read-before-write (Run.runAttempt):** passes `providers=[p for p in providerOrder.providers() if p.worker == attempt provider's worker]`. `workerOf` stays for `submit`, and its "until Task 13b" comment is gone.
- **Deleted:**
  - `Registry/ReadSource.py` and `Registry/Sources.py`;
  - `VehicleRegistry.registerReadSource`, `useReadOrder`, `readSources`, `_sources` and `_readOrder`;
  - `ProviderOrder.orderReadSources`, `UNKNOWN_TIER` and `UNKNOWN_RANK`;
  - the `readSource` / `ownerReadSource` / `fleetReadSource` attributes and their registration in TeslaBLE, TeslaAPI and HomeAssistant.

## Invariants checked

- **Source names:** observation sources are unchanged ("TeslaBLE", "TeslaAPI", "HomeAssistant"). Belief.py's source-identity rules and `_readFresh`'s `obs.source == "TeslaBLE"` see the same strings as before. Mutation M8 below pins this.
- **Paid reads:** the order is the same as before, as are the conditions under which Fleet is ready: BLE (tier 0), then Owner (1), then Fleet (FLEET_DATA, and only when the Owner slot cannot read), then HA. The old code ranked Fleet by its minimum read tier (1), but its rank still put it after Owner, so the order has not changed. `force` only skips the freshness check, as before. Nothing adds a vehicle_data request. The existing requests_mock paid-count tests (`test_owner_reads_cost_nothing_with_a_fleet_token_held`, `test_a_refused_owner_read_hands_reads_to_fleet`, `test_fleet_reads_when_owner_holds_no_token`) now run through the new walk, because `api_with_registry` wires the providers. The reconciler's I3 paid-read test now counts the Fleet provider's own fetches at FLEET_DATA.
- **Locks:** `Vehicle.read` calls the walk with no lock held. `test_free_first_and_stops_at_first_success` asserts that no registry or vehicle lock is held during a fetch.
- **Gen3:** Gen2 and Gen3 TWC providers declare only passive reads, so `ordered(READ_CHARGE)` never includes them. No Gen3 path changed.
- **Startup:** reads now need `registerProviders` to have run, because the old read sources registered themselves at module init. HA readiness also now requires `ha.enabled()`. The old source registered only after connectivity was verified, so in practice this is the same gate.

## Mutation checks (each reverted; full suite each time)

| Mutation | Killed by |
|---|---|
| M1: readiness evaluated once up front | test_readiness_is_asked_just_before_each_fetch, test_a_refused_owner_read_hands_reads_to_fleet |
| M2: Fleet ready for reads even when Owner can read | test_fleet_reads_only_when_owner_cannot, test_owner_reads_cost_nothing_with_a_fleet_token_held[unusable] (paid count), test_provider_tables full-install order ×5 |
| M3: no worker filter in read-before-write | test_read_before_write_uses_only_the_lane_s_own_providers |
| M4: BLE vouches without the field | test_ble_reply_with_no_values_falls_through_to_api |
| M5: HA vouches without the field | test_provider_fetch_observes_its_fields |
| M6: no free is_awake before vehicle_data | test_api_source_checks_free_online_state_before_paid_vehicle_data, test_each_provider_reads_through_its_own_slot[0,1] |
| M7: Fleet fetch uses the Owner slot | 4 tests in test_charging_reconciler |
| M8: BLE observes under another source name | 5 tests in test_reads_no_wake, test_claimed_vin_reads_from_ble_first |

## Deleted, renamed and retargeted tests

| Old test | Now pinned by | Class |
|---|---|---|
| read_cascade::test_fresh_value_returned_without_fetch | same name (providers) | retarget |
| read_cascade::test_stale_value_cascades_in_order_and_stops_at_first_success | test_free_first_and_stops_at_first_success. Distinct cost tiers, with registration and rank set against tier, so it now tests tier order | retarget, stronger |
| read_cascade::test_allow_wake_is_passed_through_and_defaults_false | test_never_wakes_unless_asked | retarget |
| read_cascade::test_max_age_none_never_fetches | same name | retarget |
| read_cascade::test_source_without_field_or_declining_is_skipped | test_provider_without_field_not_ready_or_not_reading_is_skipped (adds the passive-declaration case) | retarget |
| read_cascade::test_all_sources_fail_returns_stale_latest | test_all_providers_fail_returns_stale_latest | retarget |
| read_cascade::test_raising_source_counts_as_failure_and_next_is_tried | test_raising_provider_counts_as_failure_and_next_is_tried | retarget |
| read_cascade::test_empty_result_means_source_wrote_it_itself | test_true_after_recording_itself_ends_the_walk, test_true_with_nothing_recorded_continues; reads_no_wake::test_status_deferral_counts_as_success_without_fetch | retarget. `{}` became `True` |
| read_cascade::test_no_registry_returns_latest | test_no_registry_or_no_order_returns_latest | retarget |
| read_cascade::test_raising_fetch_logs_no_message_or_traceback | same name | retarget |
| read_cascade::test_value_not_newer_than_our_write_is_not_fresh / _falls_back_to_latest | same names | retarget |
| read_cascade::test_result_lacking_requested_field_continues_to_next_source | …_to_next_provider | retarget |
| read_cascade::test_read_with_sources_skips_other_sources | test_read_with_providers_skips_other_providers (also by name) | retarget |
| read_cascade::test_read_with_sources_keeps_registry_order | test_read_with_providers_keeps_cost_order | retarget |
| read_cascade::test_force_reads_past_a_live_feed / test_force_still_never_fetches_without_max_age | same names | retarget |
| (new) | test_readiness_is_asked_just_before_each_fetch, test_api_only_skips_ble_reads, test_ble_only_keeps_cloud_reads, test_a_provider_registered_twice_reads_once | added |
| registry_membership::test_read_sources_sorted_by_order_then_registration | PLUMBING-ONLY. Order: provider_order::test_reads_ordered_by_tier_then_rank, read_cascade::test_free_first…. Duplicate registration: read_cascade::test_a_provider_registered_twice_reads_once | deleted |
| provider_order::test_registry_uses_installed_read_order | PLUMBING-ONLY (`useReadOrder` hook gone; the order is ProviderOrder's, pinned above) | deleted |
| provider_order::test_read_sources_ordered_by_tier_then_rank_and_unknown_last | test_reads_ordered_by_tier_then_rank. The "unknown last" half is INTENTIONALLY CHANGED: no unowned read source can exist now; every reader is a registered provider | retarget, part removed |
| provider_order::test_ble_only_suppresses_remote_commands_not_reads / test_api_only_suppresses_ble_for_everything | same names, asserting `ordered(READ_CHARGE)` | retarget |
| provider_registration::test_home_assistant_provider_follows_entities | same name; asserts READ_CHARGE cost and FIELDS instead of `readSource.provider` | retarget |
| provider_registration::test_ble_only_drops_home_assistant_commands_but_not_its_reads | same name, `ordered(READ_CHARGE)` | retarget |
| provider_registration::test_home_assistant_reads_after_the_fleet_read_source | test_home_assistant_reads_after_the_fleet_provider (full order BLE, Owner, Fleet, HA) | retarget |
| provider_registration::test_api_only_without_registered_providers_still_reads_over_ble | test_nothing_reads_over_ble_before_register_providers[None, api_only]. INTENTIONALLY CHANGED: before registerProviders nothing reads, rather than BLE reading unsuppressed | retarget, changed |
| provider_registration::test_api_only_after_register_providers_never_reads_over_ble / test_other_policies_keep_reading_over_ble | same names, with `ordered(READ_CHARGE)` in place of `readSources()` | retarget |
| homeassistant_registry::test_read_source_registered | test_provider_reads_once_enabled | retarget |
| homeassistant_registry::test_disabled_registers_nothing | test_disabled_reads_nothing (not available, not ready) | retarget |
| homeassistant_registry::test_read_source_fetch_returns_observed_fields | test_provider_fetch_observes_its_fields (adds the source name and the "observed but not the field asked" case) | retarget |
| homeassistant_registry::test_ha_down_is_a_failed_read_and_cascade_continues | same name, through a real ProviderOrder | retarget |
| homeassistant_registry::test_unobserved_field_not_advertised_and_order_after_api | test_unobserved_field_not_advertised; the order half moved to provider_registration::test_home_assistant_reads_after_the_fleet_provider | retarget |
| reads_no_wake::test_teslable_registers_its_read_source | test_teslable_provider_reads_through_the_module. Registration into the order is pinned by provider_registration::test_other_policies_keep_reading_over_ble (real TeslaBLE + registerProviders) | retarget |
| teslable_provider::test_read_source_no_longer_consults_command_policy | test_read_readiness_does_not_consult_command_policy | retarget |
| teslable_provider::test_read_source_orders_at_the_local_tier | test_reads_order_at_the_local_tier. The unowned "other" source is INTENTIONALLY CHANGED (see above) | retarget |
| teslaapi_providers::test_read_source_passes_its_slot_to_the_car | test_each_provider_reads_through_its_own_slot[owner, fleet] (adds Fleet slot and asleep → no paid read with allowWake=True) | retarget, stronger |
| teslaapi_providers::test_two_providers_with_honest_costs / test_fleet_reads_only_when_owner_cannot | same names; `readSource.provider` / `canRead` assertions are now FIELDS / `ready` | retarget |
| reconciler_queues::test_read_before_write_uses_only_the_lane_s_own_sources | test_read_before_write_uses_only_the_lane_s_own_providers. Adds a "Custom" provider on the BLE worker, so the worker attribute decides, not the name. The "unregistered source counts as cloud" case is INTENTIONALLY CHANGED: no unregistered readers exist | retarget |
| reconciler_queues::test_an_attempt_whose_desire_changed_is_cancelled_before_any_read | same name; the Fleet provider itself reads | retarget |
| limit_reconciler::test_the_blind_retry_and_a_fallback_buy_no_paid_read | same name; the Fleet provider reads at FLEET_DATA and its fetches are counted | retarget |
| registry_vehicle::test_feed_outage_costs_one_cloud_read_not_one_per_window | same name; the cloud reader is a Provider observing "TeslaAPI" | retarget |
| gen2twc_provider::test_master_registers_gen2_provider_and_read_order | same name; asserts `vehicleRegistry.providerOrder is providerOrder` | retarget |

Fixtures: `reconcile_helpers.ScriptedProvider.reads()` and `make_order` wire the registry to the order. `teslatokens.wire_reads()` is used by `api_with_registry`, the teslamate fixture, reads_no_wake setup and the BLE pairing test.

## Concerns

- The walk lives on `ProviderOrder.read`, not in VehicleRegistry as the brief said. I did this deliberately, for deduplication and to keep Registry free of Provider imports.
- Reads now begin only after `registerProviders`. The old read sources registered at module init, so a read issued during module init would have fetched before. Today nothing reads during init that I could find. HA readiness also adds `ha.enabled()`.
