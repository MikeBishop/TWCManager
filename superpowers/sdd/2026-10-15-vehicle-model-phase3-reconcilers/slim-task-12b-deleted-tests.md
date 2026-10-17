# Slim Task 12b: audit of the 100 deleted tests

Worktree `scratchpad/wt-vm3`, HEAD 9d3fb64, BASE 8b22849. Each deleted body was read at 8b22849. Each replacement was read at 9d3fb64, and the whole `tests/` tree was searched.

Some claims were checked by mutating a scratch copy of the tree (`scratchpad/r12b/mut`, made with `git archive`); the worktree itself was not edited. "Survived" means the full `tests/unit` suite still passed with the mutation. That copy has one baseline failure, `test_registry_callers`, which comes from the copy and was ignored.

## Counts

| Class | Count |
|---|---|
| COVERED | 56 |
| PARTIAL | 8 |
| GAP | 7 (2 of them because a behaviour was lost: the read-only INFO hint, which a ruling says to restore) |
| INTENTIONALLY CHANGED | 10 |
| PLUMBING-ONLY | 19 |
| **Total** | **100** |

Rulings cited:
- R-resend: an unchanged rate is never resent. This replaces the 600 s refresh and `CHARGE_RATE_RESEND_AFTER`.
- R-retry: a failed paid rate gets one blind retry, then waits for a new value or a newer reading.
- R-15s: Fleet amps are paced at 15 s, as on main.
- R-lift: in mode 1 the car is lifted once per session.
- R-hint: the INFO "Tesla API is read-only" hint is restored.
- R-gen3: a Gen3 unit carries its own target in every mode.
- B: the 12b brief's Files/Interfaces list, e.g. "delete … `Provider.attempts()`", "`checkCharge` calls each unsuppressed module's `updateChargeAtHome()` once", "`VehicleEndpoint.setTargetPower` writes `desired.set(key, AMPS, max(1, amps), "distributor")`".

## tests/unit/test_charging_points.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_mode_2_named_twc_leaves_the_rate_to_the_heartbeat | Mode 2 with a named TWC: the distributor sends the car no rate; the heartbeat queues setChargeRate(20) | INTENTIONALLY CHANGED | B (`carriers()` mode 2 = `(F,T)`; `pointOwnsAmps`). Replaced by `test_charging_points.py::test_mode_2_named_twc_offers_its_max_and_the_car_carries_the_rate`: the TWC offers its max, the car's desire is 20 A by "distributor", and the heartbeat writes no rate |

## tests/unit/test_own_write_stamps.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_api_charge_rate_stamps_available_current | A successful Fleet rate is stamped as TeslaAPI's own write | COVERED | `test_reconciler_queues.py::test_a_rate_is_stamped_as_the_provider_s_own_write_only_on_success[FleetAPI]`. The field moved to `chargeCurrentRequest` on purpose, and the test asserts `availableCurrent` is not stamped |
| test_api_charge_rate_attribute_only_fake_still_works | `_recordChargeRate` works on an attribute-only fake | PLUMBING-ONLY | `_recordChargeRate` is deleted |
| test_ble_set_charge_rate_stamps_on_success | A BLE rate is stamped on success | COVERED | `…only_on_success[TeslaBLE]` (ERROR then DONE) |
| test_ble_set_charge_rate_no_stamp_on_failure | No reply: no stamp | COVERED | `…only_on_success[TeslaBLE]` (ERROR: no stamp); the stamp rule is in Run.py:199-205 |
| test_ble_set_charge_rate_unparsed_failure_no_stamp | Unparsed tesla-control output: failure, no stamp | COVERED | `test_provider_outcomes_local.py::test_ble_outcomes_follow_tesla_control_output` (unparsed output gives ERROR) plus the stamp test above |
| test_ble_set_charge_rate_unknown_vehicle_is_skipped | A rate never creates or revives a registry vehicle | COVERED | `test_reconciler_queues.py::test_a_rate_for_a_forgotten_car_never_revives_it` (`no vehicle`, no call) |
| test_ble_set_charge_rate_all_vehicles_stamps_each_success | The VIN-less BLE broadcast stamps each car | PLUMBING-ONLY | The all-vehicle BLE command is deleted (B: `_allVehicleTargets`); each fanned-out key is its own attempt and is stamped by Run.py |
| test_api_charge_rate_does_not_revive_forgotten_vehicle | A rate stamp does not revive a forgotten car | COVERED | `test_reconciler_queues.py::test_a_rate_for_a_forgotten_car_never_revives_it` |
| test_ha_set_charge_rate_stamps_on_success | A Home Assistant rate is stamped on success | COVERED | `…only_on_success[HomeAssistant]` |
| test_ha_set_charge_rate_failure_no_stamp | A failed Home Assistant rate: no stamp | COVERED | `…only_on_success[HomeAssistant]` |

## tests/unit/test_provider_order.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_dispatch_skips_providers_without_a_module | A TWC provider (no module) is never written as a vehicle amps path, and Fleet is dropped where the TWC covers the rate | COVERED | Reconciler.py:384. A mutation dropping that filter fails `test_amps_reconciler.py::test_mode_1_twc_carries_and_the_car_is_lifted_once_per_session`. For the debug path, see `test_provider_order.py::test_debug_set_charge_rate_reaches_fleet_past_a_covering_twc` (`t.calls == []`) |
| test_dispatch_walks_candidates_with_attempts_and_stats | The walk makes 3 BLE attempts, then Fleet, and counts stats | INTENTIONALLY CHANGED | B: `Provider.attempts()`, `ProviderOrder.dispatch` and the stats are deleted. The reconciler makes one attempt per pass, with RETRY and R-retry |
| test_dispatch_treats_error_and_exceptions_as_failures | An "error" return or an exception is a failure | COVERED | `test_reconciler_queues.py::test_bad_return_and_exception_become_error_outcomes_without_a_stamp` |

## tests/unit/test_provider_outcomes_local.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_dispatch_reads_outcomes_until_the_facade_goes | `dispatch` walks Outcomes (BLE ×3, then Fleet) | PLUMBING-ONLY | The test's own name limits it to "until the facade goes"; dispatch is deleted (B) |

## tests/unit/test_provider_tables.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_a_403_on_the_legacy_wake_refuses_wakes_only | A 403 on wake retires wakes only and never resends a wake to the refused token | COVERED | `test_provider_tables.py::test_a_403_on_wake_refuses_wakes_only` (the provider path, paid calls counted; commands still go). The legacy `wakeVehicle` is deleted |

## tests/unit/test_teslaapi_chargerate.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_same_rate_not_resent | An accepted rate is not resent (16, 16, 16.4 make 1 POST) | COVERED | `test_amps_reconciler.py::test_unchanged_rate_is_never_resent` (120 cycles, 1 send). `int()` in VehicleEndpoint.py:152 folds 16.4 into 16 |
| test_changed_rate_is_sent | A changed rate is sent with body `{"charging_amps": N}` | COVERED | `test_amps_reconciler.py::test_failed_paid_rate_retries_once_then_waits_for_a_new_value` (11 is sent); `test_teslaapi_providers.py::test_fleet_commands_resolve_the_car_by_vin` (body) |
| test_set_again_bypasses_dedupe | The internal `set_again` flag resends | PLUMBING-ONLY | The flag is gone; the low-rate repeat is inside `FleetAPIProvider.setAmps` |
| test_low_rate_still_sent_twice | A rate below 5 A is POSTed twice (TeslaPy #42), and a repeat of the same low rate is not resent | COVERED | `test_provider_outcomes_cloud.py::test_low_amps_are_sent_twice_and_counted` (4 A makes 2 requests, 10 A makes 1); the reconciler never resends an unchanged rate (above) |
| test_failed_post_does_not_record_rate | A connection error records nothing, so the rate is retried | COVERED | `…only_on_success` (ERROR: no stamp). The retry cadence changed by R-retry: `test_failed_paid_rate_retries_once_then_waits_for_a_new_value` |
| test_rejected_command_does_not_record_rate | `result: false` records nothing | COVERED | `test_provider_outcomes_cloud.py::test_fleet_command_outcomes_and_one_request_each` (result False is classified) plus the stamp test |
| test_post_has_timeout | The paid POST carries `timeout=10` | **GAP** | The behaviour is present (TeslaAPI.py:76, :1284) but no test reads `request.timeout`. A mutation to `timeout=None` survived |
| test_same_rate_skipped_inside_resend_window | No resend inside 600 s | INTENTIONALLY CHANGED | R-resend: never resent. `test_unchanged_rate_is_never_resent` |
| test_same_rate_resent_after_resend_window | Resent after 600 s | INTENTIONALLY CHANGED | R-resend (`CHARGE_RATE_RESEND_AFTER` deleted). A newer disagreeing reading resends instead: `test_user_changed_amps_are_resent_on_the_next_reading_under_mode_2` |
| test_low_rate_not_recorded_when_resend_fails | A low rate whose 2nd send fails is not recorded | **PARTIAL** | `FleetAPIProvider.setAmps` returns the second outcome (TeslaAPIProviders.py:157-165), so a failed second send is not DONE and not stamped. No test drives a failing second send. A mutation that ignores the second outcome survived |
| test_low_rate_not_recorded_when_resend_rejected | The same, with the 2nd send rejected | **PARTIAL** | As above. The new code also skips the second send when the first did not settle, which is stricter than main (main sent the second send regardless); nothing pins that |
| test_low_rate_recorded_after_both_sends_succeed | Both low sends succeed: recorded | COVERED | `test_low_amps_are_sent_twice_and_counted` (DONE) plus `…only_on_success` (DONE is stamped) |
| test_numeric_string_rate_is_accepted | The debug JSON's numeric string rate is accepted | COVERED | `test_provider_order.py::test_debug_command_goes_through_the_order` (`"12"` becomes setAmps 12; `0` becomes 1) |
| test_garbage_rate_is_rejected | "lots", None and NaN are rejected with no POST | **PARTIAL** | Order.py:145-149 rejects them (`int(float(...))` raises). `test_debug_command_refuses_an_infinite_rate` pins only ±inf |

## tests/unit/test_teslaapi_readonly_gate.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| TestRefusalLogging::test_logged_once_per_state_change | The INFO "Tesla API is read-only … not sending" hint is logged once per read-only state change | **GAP (behaviour lost)** | R-hint says restore it. At 9d3fb64 there is no such log: `grep "read-only" lib/TWCManager/Vehicle` finds only comments. `TeslaAPI.command` returns `REFUSED "no command token"` silently (TeslaAPI.py:1235-1237), and the reconciler reports at DEBUG (Reconciler.py:577-586). Main has it at TeslaAPI.py:1766 |
| TestRefusalLogging::test_resync_of_owner_token_does_not_log_again | A rotated Owner token does not log the hint again | **GAP (behaviour lost)** | As above (R-hint) |
| TestTeslaAPIRefusesCommands::test_fleet_token_is_not_refused | A Fleet token sends `set_charging_amps` | COVERED | `TestFleetProviderRefusesCommands::test_fleet_token_is_not_refused` (the same name, on the provider) |
| TestTeslaAPIRefusesCommands::test_set_charge_rate | Owner-only: a rate makes no HTTP call, records no error and leaves `lastAPIAccessTime` unchanged | **PARTIAL** | `TestFleetProviderRefusesCommands::test_no_command_token_sends_nothing[setAmps]` and `test_teslaapi_token_slots.py::test_command_refused_without_usable_fleet` pin no HTTP call and no error. Neither asserts `lastAPIAccessTime` unchanged, which feeds `is_awake`/`wakeDue` (code: `command()` returns before touching it) |
| TestTeslaAPIRefusesCommands::test_wake | Owner-only: no wake HTTP call | COVERED | `test_no_command_token_sends_nothing[wake]`; `test_command_refused_without_usable_fleet` (`wakeOutcome`) |
| TestVehiclePrioritySkipsReadOnly::test_read_only_api_skipped_for_commands | Owner-only: Fleet is never in a command walk | COVERED | `test_vehicle_endpoint.py::test_read_only_follows_fleet_slot` (provider ""); `test_teslaapi_providers.py::test_two_providers_with_honest_costs` (`fleet.available(SET_AMPS) is False`); `test_a_data_only_fleet_token_reads_but_never_commands` |
| TestVehiclePrioritySkipsReadOnly::test_read_only_api_used_for_reads | Owner-only still refreshes reads | COVERED | `TestCheckChargeRefreshesEachModuleOnce::test_read_only_api_still_refreshes_once` |
| TestVehiclePrioritySkipsReadOnly::test_writable_api_used_for_commands | A Fleet token is used for commands | COVERED | `test_read_only_follows_fleet_slot` (provider becomes FleetAPI); `test_fleet_token_is_not_refused` |
| TestVehiclePrioritySkipsReadOnly::test_every_command_method_skips | Every command method skips the read-only API | COVERED | `test_no_command_token_sends_nothing[setAmps,wake]`; `test_command_refused_without_usable_fleet` |

## tests/unit/test_teslaapi_refresh.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| TestFleetRefreshUnchanged::test_wake_401_refreshes_a_fleet_token_at_fleet_auth | A wake 401 "expired" refreshes at Fleet auth, never Owner auth, and resends once | **PARTIAL** | The wake shares `_paidPost` (TeslaAPI.py:1268-1326, `purpose="wake"`). `test_provider_outcomes_cloud.py::test_an_expired_token_is_refreshed_and_the_command_sent_once_more` pins it for a command only, and does not assert that Owner auth is never called |
| TestWakeNeverSent::test_connection_error_does_not_crash | A wake ConnectionError: no crash, no token refresh | **GAP** | The behaviour is present (TeslaAPI.py:1286-1287: a RequestException gives `ERROR`, with no refresh). No test raises a ConnectionError on `wake_up` or `command/*` |

## tests/unit/test_teslaapi_request_errors.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| TestWake::test_request_never_sent | A wake that never went out: False, no refresh | **GAP** | As above (TeslaAPI.py:1286-1287); unpinned |

## tests/unit/test_teslable_pairing_status.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_all_vehicle_commands_skip_a_refused_key | BLE never commands a VIN whose key was refused | COVERED | A refused key holds no claim: `test_update_settings_seeds_keyed_entries_as_unproven_and_paired_as_managed`, `test_later_boot_claims_held_and_paired_vins`, `test_state_read_refusal_drops_claim`. `ready` needs the claim: `test_teslable_provider.py::test_provider_is_local_free_and_ready_for_claimed_vins` |
| test_all_vehicle_commands_skip_a_vin_without_a_key | A history-only VIN (no privKey) is never commanded | COVERED | `test_update_settings_ignores_hand_edited_entries_without_a_key` (no vehicle; a mutation dropping the privKey check at TeslaBLE.py:1615 fails it), plus the readiness test |
| test_unproven_and_pairing_keys_are_still_commanded | Unproven, "pairing" and "pairing_failed" keys are still commanded | **PARTIAL** | Unproven is pinned (`…seeds_keyed_entries_as_unproven…`). Claiming "pairing" and "pairing_failed" at seeding (TeslaBLE.py:1634-1635, `status != "refused"`) is not: a mutation excluding both survived |
| test_no_usable_key_fails_the_all_vehicle_command | The all-vehicle command fails when no key is usable | PLUMBING-ONLY | The all-vehicle BLE command is deleted (B). A car with no claim has no BLE candidate, which is covered by the readiness test |

## tests/unit/test_twcmaster.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| TestVehicleCommandRouting::test_master_creates_unstarted_queue | The master owns an unstarted legacy VCQ | PLUMBING-ONLY | B (`TWCMaster.vehicleCommandQueue` deleted). `test_other_tasks_stay_on_background_queue` asserts it is gone; the reconciler owns its queues (`test_reconciler_queues.py::test_start_starts_both_queues_then_the_thread`) |
| TestVehicleCommandRouting::test_queue_vehicle_command_forwards_callback | `queue_vehicle_command` forwards the callback | PLUMBING-ONLY | B; asserted absent |
| TestVehicleCommandRouting::test_resolve_vehicle_command_module | The legacy module lookup order | PLUMBING-ONLY | B (`_resolveVehicleCommandModule` deleted) |

## tests/unit/test_twcslave.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| TestVehicleChargeRateQueueing::test_heartbeat_code_never_calls_set_charge_rate_inline | The serial thread never calls the vehicle module | COVERED | Moved to `TestVehicleChargeRateDesired::test_heartbeat_code_never_calls_set_charge_rate_inline` (stronger: neither `setChargeRate` nor `queue_vehicle_command` appears in the source) |
| TestVehicleChargeRateQueueing::test_queue_charge_rate | The heartbeat rate is int-truncated and targets the TWC's car | COVERED | `TestVehicleChargeRateDesired::test_queue_charge_rate_sets_desired` (16.7 becomes 16 by "heartbeat") |
| TestVehicleChargeRateQueueing::test_raise_queues_wiring_max_with_callback | The raise asks for wiringMaxAmps | COVERED | `TestVehicleChargeRateDesired::test_raise_sets_a_lift_and_the_flag_at_once` (32, lift) |
| TestVehicleChargeRateQueueing::test_raise_success_sets_flag | The flag is set once the raise succeeds | COVERED | `test_raise_sets_a_lift_and_the_flag_at_once`. The timing changed per B: the flag is set when the desire is written |
| TestVehicleChargeRateQueueing::test_raise_failure_leaves_flag | A failed raise leaves the flag clear, so the raise is asked again | INTENTIONALLY CHANGED | B ("set when `_requestVehicleRateRaise` sets the desire"). Delivery and retry of the lift desire are the reconciler's (R-retry, R-lift) |
| TestVehicleChargeRateQueueing::test_stale_raise_ignored_after_reset | A stale callback after a reset is ignored | PLUMBING-ONLY | There are no callbacks or generation counter |
| TestVehicleChargeRateQueueing::test_reset_clears_flag_and_bumps_generation | A reset clears the flag | COVERED | `test_raise_sets_a_lift_and_the_flag_at_once` (reset gives False); `test_amps_reconciler.py::test_a_session_end_resets_the_once_per_session_lift`. The generation is plumbing |

## tests/unit/test_vehicle_command_queue.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| TestDispatch::test_set_amps | A `setAmps` dict task reaches the module | PLUMBING-ONLY | The dict tasks and `_DISPATCH` are deleted (B) |
| TestDispatch::test_set_charge_rate | A `setChargeRate` dict task reaches the module | PLUMBING-ONLY | B |
| TestDispatch::test_set_charge_rate_without_vehicle | A VIN-less rate is dispatched | PLUMBING-ONLY | B. The VIN-less behaviour is now the anonymous fan-out: `test_amps_reconciler.py::test_an_anonymous_twc_rates_the_cars_main_s_broadcast_reached` (see the note on the fan-out ruling below) |
| TestDispatch::test_put_does_not_block_while_worker_busy | `put` never blocks the caller | COVERED | `test_reconciler_queues.py::test_put_never_blocks_while_the_worker_runs_and_a_raising_run_spares_the_worker` |
| TestCoalescing::test_set_charge_rate_latest_wins_per_vehicle | The latest rate wins, per car | COVERED | `test_queue_coalesces_per_key_aspect_stops_first_and_is_bounded_and_reports_the_losers` (70 keys kept apart; one entry per (key, aspect)); `test_replaced_and_dropped_report_the_losing_attempt_object` (`entries == [second]`) |
| TestCoalescing::test_set_amps_latest_wins | The latest amps value wins | COVERED | As above |
| TestCoalescing::test_replaced_callback_not_called | A replaced entry's callback is not called with a result | COVERED | `test_replaced_and_dropped_report_the_losing_attempt_object` (the loser is reported once, as "replaced") |
| TestCallbacksAndErrors::test_callback_receives_result | The caller receives the result | COVERED | `test_started_lane_runs_on_its_own_thread_and_drain_joins_it` (the report receives DONE) |
| TestCallbacksAndErrors::test_dispatch_exception_gives_false_and_worker_survives | A raising command does not kill the worker | COVERED | `test_put_never_blocks_while_the_worker_runs_and_a_raising_run_spares_the_worker` |
| TestCallbacksAndErrors::test_callback_exception_does_not_kill_worker | A raising callback does not kill the worker | COVERED | `test_a_raising_report_is_logged_by_type_name` |
| TestCallbacksAndErrors::test_no_module_gives_false_and_worker_survives | No module: False, and the worker survives | PLUMBING-ONLY | Module resolution is deleted; an unknown provider gives `ERROR "no provider"` (Run.py:142-144) |
| TestCallbacksAndErrors::test_unknown_command_gives_false | An unknown cmd gives False | PLUMBING-ONLY | Entries are typed Attempts |
| TestCallbacksAndErrors::test_base_exception_in_dispatch_clears_busy | A SystemExit still clears busy | COVERED | `test_base_exception_in_a_run_still_reports_and_clears_busy` |
| TestCallbacksAndErrors::test_malformed_put_is_dropped_without_raising | A malformed dict is dropped | PLUMBING-ONLY | Entries are typed Attempts |
| TestDrain::test_drain_finishes_the_running_command_and_drops_the_rest | The drain finishes the running command and drops the low-priority rest | COVERED | `test_drain_runs_pending_stops_only`; `test_drain_on_a_started_lane_lets_its_thread_run_the_pending_stop`; `test_drain_delivers_a_cloud_stop_and_drops_a_ble_limit` |
| TestDrain::test_drain_times_out | The drain honours its timeout | COVERED | `test_drain_is_not_held_past_its_timeout_by_a_hung_attempt` |
| TestDrain::test_drain_when_idle_returns_immediately | An idle drain returns at once | COVERED | `test_reconciler_queues.py::test_a_drain_of_an_idle_queue_returns_at_once` |

## tests/unit/test_vehicle_endpoint.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_set_target_power_queues_on_change_or_after_refresh | 0 sends nothing; a repeat is deduped; a resend after 600 s; 100 W gives 1 A | COVERED | `test_vehicle_endpoint.py::test_set_target_power_sets_desired_amps` (0 gives none, 2400 W gives 10, 100 W gives 1, and 0 withdraws). The 600 s refresh is INTENTIONALLY CHANGED by R-resend and pinned by `test_unchanged_rate_is_never_resent` |

## tests/unit/test_vehicle_priority.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_command_policy_properties_delegate | `commandPolicy` and the override are exposed | COVERED | `test_provider_order.py::test_config_policy_overrides_settings` (Suppressions) |
| test_no_modules_returns_false | No providers: False | PLUMBING-ONLY | The facade is deleted; no candidate gives "no provider can deliver" (Reconciler.py:390-392) |
| test_walk_is_order_position_with_local_three_attempts_and_ha_last | Walk order, 3/2/1 attempts, HA last | INTENTIONALLY CHANGED | B (`Provider.attempts()` deleted); R-retry. The order part is in `test_fixed_order_is_tier_then_rank_regardless_of_registration` and `test_provider_registration.py::test_home_assistant_commands_after_free_providers_and_fleet` |
| test_ble_only_skips_cloud_commands_but_not_reads | ble_only blocks cloud commands, not reads | COVERED | `test_provider_order.py::test_ble_only_suppresses_remote_commands_not_reads`; `test_provider_registration.py::test_ble_only_drops_home_assistant_commands_but_not_its_reads` |
| test_api_only_walks_fleet_without_ble | api_only keeps BLE out of commands and reads | COVERED | `test_provider_order.py::test_api_only_suppresses_ble_for_everything`; `TestCheckChargeRefreshesEachModuleOnce::test_api_only_keeps_ble_out` |
| test_broadcast_skips_a_provider_that_is_not_available | An Owner-only Fleet (unavailable) never gets a vehicle-less command | COVERED | `test_provider_order.py::test_candidates_require_readiness_and_ordered_requires_availability` |
| test_targeted_call_skips_providers_not_ready_for_that_car | Per-car readiness | COVERED | As above |
| test_set_charge_rate_targets_the_car | A rate below the TWC floor goes to Fleet for that car | COVERED | `test_provider_order.py::test_default_fleet_amps_rule_uses_target_and_range` (4 A gives FleetAPI); `test_amps_reconciler.py::test_fleet_never_sets_a_rate_the_twc_covers_but_carries_a_lift` (4 A reaches Fleet) |
| test_set_charge_rate_zero_still_reaches_the_vehicle | A 0 A rate is clamped to 1 and still sent | INTENTIONALLY CHANGED | B (`max(1, amps)`). A 0 offer withdraws the rate: `test_zero_offer_withdraws_the_cars_rate_but_not_a_lift`, `test_set_target_power_sets_desired_amps`. The heartbeat cannot desire 0 (its mode-2/3 branch is reached only at ≥ minAmpsToOffer ≥ 1). A 0 desire, were one written, would match no provider (Order.py:96-100) rather than main's 1 A |
| test_set_amps_dispatches_through_the_order | setAmps reaches BLE by VIN; an unknown VIN gives False | COVERED | `test_amps_reconciler.py::test_amps_use_the_cars_request_not_the_pilot` (BLE setAmps by VIN); an unknown key is skipped in `pass_` (Reconciler.py:269-271) |
| test_queue_dispatches_set_amps | The VCQ `_execute` and `_key` for setAmps | PLUMBING-ONLY | B |
| test_same_module_under_two_providers_is_walked_once | Owner and Fleet share one module, refreshed once | COVERED | `TestCheckChargeRefreshesEachModuleOnce::test_read_only_api_still_refreshes_once` (Owner+Fleet registered, `call_count == 1`) |
| test_exceptions_count_as_failures_and_dunder_probes_do_not_walk | An exception is a failure; `__deepcopy__` does not walk | COVERED | The exception part: `test_bad_return_and_exception_become_error_outcomes_without_a_stamp`. The dunder probe is facade plumbing |
| test_registration_finds_no_providers_on_the_facade | The facade registers no providers | PLUMBING-ONLY | The facade is deleted |
| test_rate_raise_reaches_fleet_on_a_fleet_only_install | A raise to the wiring max reaches Fleet past a covering TWC (#660) | COVERED | `test_fleet_never_sets_a_rate_the_twc_covers_but_carries_a_lift` (lift 32 goes to Fleet once, paid counted) |
| test_set_amps_keeps_the_local_amps_rule | A distributor rate the TWC covers never goes to Fleet | COVERED | Same test (10 A: `f.calls == []`); `test_default_fleet_amps_rule_uses_target_and_range` |
| test_attempts_match_todays_priorities | Fleet ×2, HA ×1 on failure | INTENTIONALLY CHANGED | B (`attempts()` deleted); R-retry: one send plus one blind retry, `test_failed_paid_rate_retries_once_then_waits_for_a_new_value` |
| test_home_assistant_gets_its_own_vehicle_for_set_charge_rate | HA commands its own HaVehicle and never the TeslaAPI car | COVERED | `test_provider_registration.py::test_home_assistant_provider_follows_entities` (not ready without the HA attachment; the entity comes from it) |
| test_disabled_home_assistant_gets_no_broadcast | A disabled HA gets no rate and no charge refresh | **GAP** | Present: HomeAssistantProvider.py:308-317 (`available`/`ready` check `enabled()`), TWCMaster.py:503. Unpinned: a mutation ignoring `enabled()` in the provider survived, and so did dropping `p.available(READ_CHARGE)` from `updateChargeAtHome` |

## tests/unit/test_vehicle_priority_returns.py

| Deleted test | Behaviour protected | Class | Evidence / replacement test or ruling |
|---|---|---|---|
| test_a_none_return_is_a_failure_and_the_walk_continues | A None return is a failure | COVERED | `test_bad_return_and_exception_become_error_outcomes_without_a_stamp` (any non-Outcome gives ERROR). The walk continuing is facade-only |
| test_update_charge_at_home_ends_at_teslaapi_when_it_holds_cars | checkCharge stops at TeslaAPI when it holds cars; HA is not refreshed | INTENTIONALLY CHANGED | B ("checkCharge calls each unsuppressed module's `updateChargeAtHome()` once"); report concern 4 (HA REST reads are free) |
| test_update_charge_at_home_reaches_ha_when_teslaapi_holds_no_car | HA is refreshed by checkCharge | **GAP** | Present (TWCMaster.py:492-510), but `TestCheckChargeRefreshesEachModuleOnce` registers only BLE and TeslaAPI; no test shows HA's `updateChargeAtHome` being called |
| test_home_assistant_update_charge_at_home_returns_true | HA's refresh returns True, to end the walk | PLUMBING-ONLY | The return value is unused now |
| test_ha_after_a_fleet_failure_is_held_to_fleets_cadence | HA reached after a Fleet failure is held to Fleet's 60 s cadence per car and command | **PARTIAL** | Present and stricter: Fleet and HA share one paid record. A probe with Fleet ERROR "500" plus HA, desire unchanged for 1 h, gave Fleet 2 sends and HA 0; with Fleet REFUSED "403" it gave Fleet 1 and HA 0 until a new value, then HA 1. Unpinned for AMPS with Fleet+HA (see the observation below) |
| test_the_hold_is_per_car_and_per_command | The hold is per car and per command | **PARTIAL** | Records are per (key, aspect) by construction (Desired.py); no Fleet+HA amps test with two cars |
| test_ha_only_install_keeps_its_own_cadence | An HA-only install sends every call (10 s apart) | INTENTIONALLY CHANGED | R-resend and R-retry: an unchanged rate is never resent, and a changed one is paced by MIN_SEND_GAP[AMPS] = 15 s (R-15s). Pinned for Fleet (`test_fluctuating_offer_sends_at_most_one_rate_per_15s`); the gap is per aspect whatever the provider |

## GAPs and PARTIALs

Each item gives a proposed test name and a concrete assertion; "behaviour lost" is noted where it applies.

### GAPs

1. **test_teslaapi_chargerate::test_post_has_timeout.**
   - Behaviour present: TeslaAPI.py:76 `COMMAND_TIMEOUT = 10`, TeslaAPI.py:1284 `timeout=self.COMMAND_TIMEOUT`. A mutation to `None` survived.
   - Proposed: `test_provider_outcomes_cloud.py::test_paid_posts_time_out_after_ten_seconds`:
     - `api, reg, p = fleet(requests_mock); p.setAmps(VIN, 10)`;
     - `assert calls(requests_mock, "set_charging_amps")[0].timeout == 10`;
     - the same for `wake_up` after an "asleep" online check.

2. **TestRefusalLogging::test_logged_once_per_state_change (behaviour lost).**
   - R-hint says restore it. At 9d3fb64 no INFO "read-only" log exists: TeslaAPI.py:1235-1237 returns `REFUSED "no command token"` silently, and Reconciler.py:577-586 logs the outcome at DEBUG. Main logs it at TeslaAPI.py:1766.
   - Proposed: `test_teslaapi_readonly_gate.py::TestRefusalHint::test_logged_once_per_state_change`:
     - owner-only api, `fleet.setAmps(VIN, 10); fleet.setAmps(VIN, 12); fleet.wake(VIN)` gives exactly 1 INFO record containing "read-only";
     - `storeToken(fleet_token()); fleetSlot.clear(); setAmps ×2` gives 2 in total.

3. **TestRefusalLogging::test_resync_of_owner_token_does_not_log_again (behaviour lost).**
   - Same evidence as 2.
   - Proposed: `TestRefusalHint::test_resync_of_owner_token_does_not_log_again`: `setAmps`, then `storeToken(owner_token(jti="rotated"))`, then `setAmps` gives 1 INFO record.

4. **TestWakeNeverSent::test_connection_error_does_not_crash.**
   - Behaviour present: TeslaAPI.py:1286-1287 turns a RequestException into `Outcome(ERROR, "ConnectionError")` with no refresh. Unpinned.
   - Proposed: `test_provider_outcomes_cloud.py::test_a_wake_or_command_that_never_left_is_an_error_and_refreshes_nothing`:
     - online check "asleep", `wake_up` `exc=ConnectionError`, refresh mock on FLEET_REFRESH_URL;
     - `assert p.wake(VIN) == O.Outcome(O.ERROR, "ConnectionError") and not refresh.called and not api.fleetSlot.empty()`;
     - the same for `p.setAmps(VIN, 10)` with `command/set_charging_amps` raising.

5. **TestWake::test_request_never_sent.** Same behaviour and proposed test as 4.

6. **test_vehicle_priority::test_disabled_home_assistant_gets_no_broadcast.**
   - Behaviour present: HomeAssistantProvider.py:308-317 and TWCMaster.py:503. Both mutations survived.
   - Proposed: `test_provider_registration.py::test_disabled_home_assistant_is_never_a_candidate_nor_refreshed`:
     - `ha, reg = make_ha(enabled=False)`, register its provider, attach an hv with `has_charge_current_number=True`;
     - `assert not p.available(C.SET_AMPS) and order.candidates(v, C.SET_AMPS) == []`;
     - with `ha.updateChargeAtHome = Mock()`, `TWCMaster.updateChargeAtHome(master)` leaves `ha.updateChargeAtHome.called is False`.

7. **test_vehicle_priority_returns::test_update_charge_at_home_reaches_ha_when_teslaapi_holds_no_car.**
   - Behaviour present: TWCMaster.py:492-510. HA is now refreshed even when TeslaAPI holds cars (report concern 4).
   - Proposed: `TestCheckChargeRefreshesEachModuleOnce::test_home_assistant_refreshes_once_alongside_teslaapi`:
     - register an enabled HA provider whose module is a Mock;
     - `TWCMaster.updateChargeAtHome(master)` gives `ha.updateChargeAtHome.call_count == 1` and `api.updateChargeAtHome.call_count == 1`.

### PARTIALs

1. **test_teslaapi_chargerate::test_garbage_rate_is_rejected.**
   - Order.py:145-149 rejects these; only ±inf is pinned.
   - Proposed: extend `test_debug_command_refuses_an_infinite_rate`'s params with `'{"charge_rate": "lots"}'`, `'{"charge_rate": null}'` and `'{"charge_rate": NaN}'` (`json.loads` accepts NaN). Assert False and `f.calls == []`.

2. **test_low_rate_not_recorded_when_resend_fails** and 3. **test_low_rate_not_recorded_when_resend_rejected.**
   - TeslaAPIProviders.py:157-165. A mutation that ignores the second outcome, and always sends the second request, survived.
   - Proposed: `test_provider_outcomes_cloud.py::test_a_low_rate_is_done_only_when_both_sends_land`:
     - POST responses `[ok, 500]`: `p.setAmps(VIN, 4) == Outcome(ERROR, "500")` with 2 requests;
     - `[ok, {"result": False}]`: kind ERROR;
     - a first `{"result": False}`: 1 request only (no second send after an unsettled first);
     - through `runAttempt`, no `chargeCurrentRequest` stamp in the failing cases.

4. **TestTeslaAPIRefusesCommands::test_set_charge_rate.**
   - The `lastAPIAccessTime` assertion was dropped.
   - Proposed: add `car = owner_api.getCarApiVehicles()[0]; before = car.lastAPIAccessTime; …; assert car.lastAPIAccessTime == before` to `TestFleetProviderRefusesCommands::test_no_command_token_sends_nothing`.

5. **TestFleetRefreshUnchanged::test_wake_401_refreshes_a_fleet_token_at_fleet_auth.**
   - Proposed: `test_provider_outcomes_cloud.py::test_an_expired_token_on_wake_is_refreshed_at_fleet_auth_once`:
     - online check "asleep"; `wake_up` responses `[401 "token expired", {"response": {"state": "online"}}]`; `time.sleep` mocked;
     - `p.wake(VIN).kind == DONE`, the FLEET_REFRESH_URL mock has call_count 1, and the AUTH_TOKEN_URL (Owner) mock has call_count 0.

6. **test_unproven_and_pairing_keys_are_still_commanded.**
   - TeslaBLE.py:1634-1635. A mutation excluding "pairing" and "pairing_failed" survived.
   - Proposed: `test_teslable_pairing_status.py::test_pairing_and_pairing_failed_keys_are_claimed_and_commandable`:
     - settings with `ble.status` "pairing" (VIN2) and "pairing_failed" (VIN3) on the upgrade boot;
     - after `updateSettings()`, `"TeslaBLE" in reg.get(VIN2).claims` and the same for VIN3, and `p.ready(reg.get(VIN2), C.SET_AMPS)`.

7. **test_ha_after_a_fleet_failure_is_held_to_fleets_cadence** and 8. **test_the_hold_is_per_car_and_per_command.**
   - Proposed: `test_amps_reconciler.py::test_home_assistant_after_a_failed_fleet_rate_spends_from_the_same_paid_budget` (paid counted):
     - `fleet(Outcome(ERROR, "500"))` plus an HA ScriptedProvider declaring `SET_AMPS: HA_BILLED`, both ready;
     - 3600 one-second passes with `e.setTargetPower(10*240)` give `len(f.calls) == 2 and h.calls == []`;
     - a variant with `fleet(Outcome(REFUSED, "403"))` gives `f.calls == 1, h.calls == []` for the hour, then `setTargetPower(11*240)` gives `h.calls == [("setAmps", VIN, 11)]`;
     - a second VIN with its own desire gets its own send in the same pass.
   - These numbers come from a probe at 9d3fb64.

## Behaviour lost, and other observations

- **Lost (acknowledged; ruling R-hint not yet applied at 9d3fb64):** the read-only INFO hint. Evidence: GAP 2 above.
- **No other behaviour was lost.**
  - The <5 A double send survives on Fleet only (TeslaAPIProviders.py:157-165) and is pinned by `test_low_amps_are_sent_twice_and_counted`. Main sent it twice on Fleet only too (origin/main TeslaAPI.py:1849-1858; main's BLE and HA did not).
  - The POST timeout (10 s) survives (TeslaAPI.py:1284), unpinned.
  - "No wake for a rate" survives: Reconciler.py:460 `(p.local or aspect != AMPS)`. A mutation fails 7 amps tests.
  - Read-only sends nothing: TeslaAPI.py:1236-1237, pinned.
  - BLE skips refused and keyless VINs: claims, pinned.
  - HA disabled: present, unpinned.
  - api_only keeps BLE out: pinned.
  - 403 on wake refuses wakes only: pinned by `test_a_403_on_wake_refuses_wakes_only`.
  - Fleet pacing at 15 s: pinned by `test_amps_gap_is_fifteen_seconds` and `test_fluctuating_offer…` (mutation verified).
- **Observation, a parity question rather than a cost one.** For amps, Reconciler.py:427-429 always picks `paid[0]` (FleetAPI). So while Fleet fails retryably (5xx, timeouts), Home Assistant is never tried: Fleet gets 1 send plus 1 blind retry per desire, then waits for a new value, which again goes to Fleet. BASE tried HA after a Fleet failure, held to Fleet's cadence. This costs less, but a Fleet outage with a working HA leaves the car's rate stale. The coordinator should rule on it.
- **Observation, ruling not implemented.** The VIN-less Gen2 fan-out at 9d3fb64 (TWCSlave.py:101-110 through Targets.py:44-57 `broadcastVehicles`) still reaches every at-home or unlocated TeslaAPI car and every BLE-claimed VIN. The ruling limits it to at-home cars whose latest reading shows them plugged in or charging, else main's `vehicles[0]`. `test_an_anonymous_twc_rates_the_cars_main_s_broadcast_reached` pins today's broader shape and will need updating with the fix.
