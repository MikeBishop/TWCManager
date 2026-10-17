# Deleted-test audit: d98d643..8b22849 (slim Tasks 10, 11, 12a)

Read-only audit. For each test deleted or weakened under `tests/` in d98d643..8b22849, this file names the behaviour it protected and the test at 8b22849 that now pins it.

Method:
- `git diff -M d98d643 8b22849 -- tests`, compared function by function.
- A per-commit scan, which found two tests added and deleted inside the range (rows 78 and 79).
- Coverage was checked by reading the tests and lib at 8b22849, using `git archive 8b22849`.

"Ledger L*n*" means line *n* of `progress.md` in this directory.

Classes:
- **COVERED:** a named test pins the same behaviour.
- **PARTIAL:** something pins part of it; the row says what is missing.
- **GAP:** nothing pins it.
- **INTENTIONALLY CHANGED:** the behaviour was changed on purpose, with a ruling cited.
- **PLUMBING-ONLY:** the test checked plumbing whose subject no longer exists.

## Counts

Deleted tests (79):

| Class | Count |
|---|---|
| COVERED | 45 |
| PLUMBING-ONLY | 12 |
| INTENTIONALLY CHANGED | 10 |
| PARTIAL | 11 |
| GAP | 1 |

Rewritten tests with removed or weakened assertions (22 rows):

| Class | Count |
|---|---|
| INTENTIONALLY CHANGED | 11 |
| PLUMBING-ONLY | 6 |
| COVERED | 4 |
| PARTIAL | 1 |

## A. Deleted tests

### test_held_limits.py (23cb7e8)

| # | Deleted test | Behaviour it protected | Class | Evidence at 8b22849 |
|---|---|---|---|---|
| 1 | test_adopt_keeps_an_existing_vin_entry | A legacy ID entry never overwrites a held limit the VIN already has | COVERED | `test_held_limits::test_resolving_keeps_an_existing_vin_entry`; `test_limit_wiring::test_legacy_ids_resolve_once_from_the_first_vehicle_list` (the store's own VIN4 wins) |
| 2 | test_bind_skips_the_lock_when_the_vin_already_has_an_entry | A per-rebind adoption check does not take settingsLock | PLUMBING-ONLY | The `CarApiVehicle._bind` adoption is deleted; nothing runs on a rebind (slim-task-11 report l.46) |
| 3 | test_both_keys_present_warns_once | Both keys present: one warning, and the store wins | INTENTIONALLY CHANGED | Now no warning for a car the store keeps (2ecf54f). Pinned by `test_both_keys_present_the_store_wins`. Migration runs once and removes `chargeLimits`, so a repeat warning cannot happen |
| 4 | test_existing_store_wins_and_legacy_key_is_left_alone | An existing store was never merged; the legacy key was left on disk | INTENTIONALLY CHANGED | Ledger L104 (decision 3, migrate once) and L141 (I1, merge later VINs). Pinned by `test_an_existing_store_keeps_its_own_cars` and `test_a_limit_recorded_while_an_id_waits_keeps_the_legacy_normal` |
| 5 | test_listing_before_load_is_adopted | A vehicle list loaded before `loadSettings` still resolves legacy IDs | COVERED | `test_listing_before_load_is_resolved_on_the_next_check`, which also checks that only free GETs are made |
| 6 | test_rebind_adopts_an_entry_that_appeared_later | An `id:` store entry that appears after listing is adopted on a rebind | PLUMBING-ONLY | `id:` store keys no longer exist; IDs wait in `chargeLimits` and resolve from a list (ledger L104 decision 3) |
| 7 | test_set_remove_and_wrappers_keep_working | set, get and remove of a held limit | COVERED | `test_set_and_remove`. The wrapper half is plumbing (wrappers deleted, slim-task-11 l.80) |
| 8 | test_teslaapi_listing_adopts_the_legacy_id_once | A listing resolves a legacy ID once, with one save | COVERED | `test_legacy_ids_resolve_once_from_the_first_vehicle_list` (`tasks == [saveSettings]`; the second load makes no list call) |
| 9 | test_wrapper_never_stores_the_sentinel | `-1` and `0` are never stored as a held value | COVERED | `test_set_refuses_a_non_vin_and_maps_zero_to_none`; `test_rules_need_no_sentinel`; `test_legacy_ids_resolve_once_...` (`[80, -1]` becomes held None) |
| 10 | test_wrappers_resolve_a_numeric_id_through_teslaapi | A numeric-ID limit reaches its VIN through TeslaAPI's list | COVERED | `test_legacy_ids_resolve_once_from_the_first_vehicle_list` (Owner and Fleet lists, real requests) |

### test_limit_reconciler.py

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 11 | test_a_satisfied_restore_settles_the_held_limit_and_its_desire (23cb7e8) | A restore the car already satisfies sends nothing and settles | INTENTIONALLY CHANGED | c6 (ledger L95): the held record is now removed, not left as `(90, None)`. Pinned by `test_limit_wiring::test_a_satisfied_restore_removes_the_held_record` |
| 12 | test_rate_limited_provider_is_skipped_at_plan_time (44c4ddb) | A Fleet limit is not sent faster than its declared 1-per-60 s per car | INTENTIONALLY CHANGED | Ledger L104 (decision 6; redundant rate limits folded in): one `MIN_SEND_GAP` (10/10/15 s) plus at most 4 paid sends per desire. Pinned by `test_min_send_gap_spaces_a_start_stop_flip_on_any_provider`, `test_amps_gap_is_fifteen_seconds`, `test_streaming_telemetry_with_fleet_408_is_bounded_per_desire` and `test_failed_paid_call_retries_once_then_waits...` |

### test_outcome_desired.py (44c4ddb)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 13 | test_a_raising_change_callback_is_dropped_and_others_still_run | A raising change hook never breaks a desired-state write | COVERED | `test_a_raising_change_callback_does_not_break_the_write`. The multi-callback list is deleted (slim-task-10 l.51) |

### test_own_write_stamps.py (23cb7e8)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 14 | test_ble_apply_charge_limit_stamps_on_success | A delivered limit is recorded as our write, with its value | COVERED | `test_reconciler_queues::test_inline_lane_runs_reports_and_stamps_the_write` (value, source, wall-clock); `test_limit_reconciler::test_limit_is_sent_once_and_recorded_as_held` |
| 15 | test_ble_apply_charge_limit_failure_no_stamp | A failed send records no write | COVERED | `test_bad_return_and_exception_become_error_outcomes_without_a_stamp`. Run.py stamps only on DONE or a stamped SATISFIED |
| 16 | test_ble_restore_stamps_the_restored_value | A restore stamps the outside value it sent, not a sentinel | PARTIAL | The stamp path is generic and has no sentinel (`test_rules_need_no_sentinel`). But no test asserts `lastWrite("chargeLimit").value == outside` after a restore DONE |
| 17 | test_api_apply_charge_limit_stamps_on_success | As 14, Fleet | COVERED | The same runner tests (the provider is generic). The stamp source is now the provider name (`FleetAPI`) |
| 18 | test_api_apply_charge_limit_failure_no_stamp | As 15, Fleet | COVERED | As 15; `test_fleet_command_outcomes_and_one_request_each` (a 500 is ERROR) |
| 19 | test_ha_apply_charge_limit_stamps_on_success | As 14, HA | COVERED | As 14 |
| 20 | test_ha_apply_charge_limit_failure_no_stamp | As 15, HA | COVERED | As 15; `test_ha_outcomes` |

### test_provider_order.py, test_provider_outcomes_cloud.py (44c4ddb, c563d70)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 21 | test_debug_command_without_workers_submits_nothing | The debug route sends nothing without a runner | COVERED | Renamed `test_debug_command_without_a_reconciler_submits_nothing` |
| 22 | test_an_ended_need_gets_a_fresh_grace_on_the_legacy_path | A need that ended starts a fresh wake grace and buys no wake | COVERED | `test_an_ended_need_gets_a_fresh_grace_through_wake_outcome` |
| 23 | test_ha_outcomes_and_per_car_rate_limit | HA start and stop are spaced at least 10 s apart per car | COVERED | `test_ha_outcomes`; `test_limit_reconciler::test_min_send_gap_spaces_a_start_stop_flip_on_any_provider` (HA and BLE); `test_min_send_gap_holds_when_the_flip_lands_while_the_start_is_in_flight` |

### test_targeted_charge_limit.py (whole file, c4d9037)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 24 | test_ble_broadcast_limit_is_unchanged | A policy limit reaches every BLE-keyed car | COVERED | `test_limit_wiring::test_present_rule_until_phase_5` (a BLE-only car is present); `test_policy_limit_sets_desired_for_present_cars_and_none_restores` |
| 25 | test_ble_declines_a_remote_only_limit | A departure restore is never tried over BLE | INTENTIONALLY CHANGED | Ledger L66 (Q3, fixed hourly restore retry) and plan Task 14 row 17a: BLE retries hourly and never wakes. Pinned by `test_restore_to_an_absent_car_retries_hourly_and_never_wakes` and `test_departure_restores_a_held_limit_for_an_absent_car_once` (no BLE claim: nothing sent) |
| 26 | test_ble_targeted_limit_touches_only_that_car | A limit for one car is sent to that car only | COVERED | Desires are per key; `TeslaBLEProvider` takes one VIN (`test_ble_outcomes_follow_tesla_control_output` asserts `sendCommand(VIN, ...)`) |
| 27 | test_teslaapi_broadcast_limit_is_unchanged | A policy limit reaches every at-home API car | COVERED | `test_policy_limit_sets_desired_for_present_cars_and_none_restores`; `test_present_rule_until_phase_5` |
| 28 | test_teslaapi_targeted_limit_never_wakes_another_car | Cost: a limit for car A never sends a paid wake to at-home car B | PARTIAL | `test_fleet_commands_resolve_the_car_by_vin` covers only mocked `api.command` and `wakeOutcome`. No real-`requests_mock` test lists two cars and checks that B's URL never appears |
| 29 | test_teslaapi_targeted_limit_touches_only_that_car | A targeted limit commands and reads only that car | PARTIAL | As 28 |

### test_teslaapi_charge_vin.py (whole file, c563d70)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 30 | test_no_vin_still_commands_every_vehicle | An unaddressed stop reaches every at-home API car | COVERED | `test_charging_reconciler::test_an_anonymous_point_fans_out_as_main_did`; `test_twcmaster::test_empty_vin_is_every_present_car_with_a_stop_candidate` (desired-state level) |
| 31 | test_vin_start_does_not_wake_other_vehicles | Cost: a VIN start never wakes or reads another car, or resets its wake hold | PARTIAL | As 28. The desired-state isolation is pinned (`test_stop_replaces_the_start_for_that_car_only`); the wire-level isolation is not |
| 32 | test_vin_stop_commands_only_that_vehicle | A VIN stop posts `charge_stop` for that car only | PARTIAL | As 31 |

### test_teslaapi_readonly_gate.py, test_teslaapi_token_classification.py (c563d70)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 33 | TestTeslaAPIRefusesCommands::test_apply_charge_limit | An Owner (read-only) token never commands a limit, and records no API error | COVERED | `test_tables_match_the_declarations_they_replace` (OwnerAPI declares no commands); `test_a_data_only_fleet_token_reads_but_never_commands`; `test_command_refused_without_usable_fleet` |
| 34 | TestTeslaAPIRefusesCommands::test_car_api_available_skips_wake_loop | A read-only token never wakes | COVERED | OwnerAPI declares no WAKE; `TestTeslaAPIRefusesCommands::test_wake`; `test_a_data_only_fleet_token...` (`available(WAKE)` is False) |
| 35 | TestTeslaAPIRefusesCommands::test_start_and_stop_charge | A read-only token never starts or stops | COVERED | As 33; `test_a_command_412_retires_commands_and_wakes_until_the_token_changes` (start, stop and limit: zero requests) |
| 36 | TestNoBaseURLLogLine::test_no_token_yet | The log says "no Tesla API token yet", and no request is made | COVERED | `test_charging_reconciler::test_load_list_logs_why_no_token_is_usable_once_per_reason`; `test_teslaapi_token_slots::test_no_usable_slot_makes_no_requests` |
| 37 | TestNoBaseURLLogLine::test_unknown_token | The log says "token type unknown" | COVERED | As 36 |

### test_twcmaster.py (f8b20ce)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 38 | test_cancel_stop_for_all | Cancelling with no VIN removes every pending stop | COVERED | `test_empty_vin_is_every_present_car_with_a_stop_candidate` (`cancelStopCarsCharging("") == 2`) |
| 39 | test_cancel_stop_for_vin_leaves_other_stops | A cancel for one car leaves others' stops | COVERED | `test_cancel_stop_for_a_car_leaves_other_stops` |
| 40 | test_delayed_charge_routed_when_due | A delayed `charge` task reaches the vehicle queue when due | PLUMBING-ONLY | No `charge` task exists. Only `getVehicleVIN` used `delay=` at d98d643 |
| 41 | test_empty_vin_is_treated_as_none | `""` means every car | COVERED | `test_empty_vin_is_every_present_car_with_a_stop_candidate` |
| 42 | test_start_passes_vin_in_stop_mode_1 | A mode-1 start names its car | COVERED | `test_start_names_its_car_and_clears_the_override_in_mode_1` |
| 43 | test_stop_cancels_pending_start_for_that_vin_and_vehicleless | A stop replaces that car's pending start | COVERED | `test_stop_replaces_the_start_for_that_car_only`. The vehicleless half has no subject: desired state is re-decided every cycle (12a) |
| 44 | test_stop_for_all_cancels_every_pending_start | A stop for all replaces every start | COVERED | `test_empty_vin_is_every_present_car_with_a_stop_candidate` |
| 45 | test_vehicle_commands_routed | `charge` and `applyChargeLimit` tasks go to the vehicle queue | PLUMBING-ONLY | Those task kinds are deleted |

### test_vehicle_command_queue.py (23cb7e8, c563d70)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 46 | TestDispatch::test_apply_charge_limit | Dispatch of `applyChargeLimit` | PLUMBING-ONLY | Retargeted to `test_set_amps` |
| 47 | test_apply_charge_limit_latest_wins | The latest limit wins | COVERED | `test_limit_reconciler::test_a_limit_changed_while_in_flight_sends_the_new_value`; the queue's "replaced" in `test_queue_coalesces_per_key_aspect...`; the generic form in `test_set_amps_latest_wins` |
| 48 | test_apply_charge_limit_passes_vin_and_remote_only | Task kwargs forwarding | PLUMBING-ONLY | No task form remains |
| 49 | test_apply_charge_limit_per_vin_does_not_merge_with_policy_wide | Keying of the deleted queue | PLUMBING-ONLY | Desires are keyed per car |
| 50 | test_apply_charge_limit_without_vin_omits_vin_kwarg | Legacy module signature | PLUMBING-ONLY | No such module call |
| 51 | test_cancel_leaves_running_entry_alone | A running stop is never cancelled | COVERED | `test_reconciler_queues::test_cancel_leaves_a_running_stop_alone` |
| 52 | test_cancel_matches_command_name | Cancel filtered by `cmd` | PLUMBING-ONLY | Cancel takes only stops (`test_cancel_removes_only_stops_and_reports_them`) |
| 53 | test_cancel_removes_matching_pending_entries | Cancel removes pending stops and leaves starts | COVERED | `test_cancel_removes_only_stops_and_reports_them` |
| 54 | TestDispatch::test_charge | Dispatch of `charge` | PLUMBING-ONLY | Task kind deleted |
| 55 | test_charge_keyed_per_vin | Start then stop for one car coalesce; another car's start survives | COVERED | `test_queue_coalesces_per_key_aspect_stops_first_and_is_bounded_and_reports_the_losers` |
| 56 | TestDrain::test_drain_accepts_new_stop | A stop submitted during the shutdown drain still runs | PARTIAL | `VehicleCommandQueue.put` still accepts a high entry while `_draining and _live` (VehicleCommandQueue.py:137). Every surviving drain test submits its stop before the drain; `test_a_stop_put_as_the_worker_exits...` tests the closed case. The reconciler is stopped before the drain, but a pass already in flight can still submit |
| 57 | TestDrain::test_drain_runs_stops_and_drops_the_rest | The drain delivers pending stops and drops the rest | COVERED | `test_reconciler_queues::test_drain_runs_pending_stops_only`; `test_drain_delivers_a_cloud_stop_and_drops_a_ble_limit`; `test_sigterm_shutdown::test_vehicle_drains_leave_twenty_seconds_for_settings` |
| 58 | test_none_vin_is_distinct_from_named_vin | Queue keying for None | PLUMBING-ONLY | Anonymous cars have their own keys |
| 59 | TestPriority::test_start_is_not_high_priority | A start never jumps ahead of a pending limit | COVERED | `test_charging_reconciler::test_fleet_start_sends_the_limit_first` (real requests); `test_start_waits_five_seconds_after_a_limit_write_and_wakes`; `test_a_lowered_limit_that_failed_once_rides_the_start_s_wake` (the limit's write comes before the start's) |
| 60 | TestPriority::test_stop_runs_before_earlier_commands | A stop goes first | COVERED | `test_queue_coalesces_per_key_aspect_stops_first...` (`entries(q)[0]` is the stop) |

### test_vehicle_priority.py (c563d70)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 61 | test_broadcast_still_reaches_every_home_assistant_car | Main parity: an unaddressed stop or start reaches every at-home, connected HA car | **GAP** | `TWCMaster._chargeTargets` sends an anonymous point in mode 1 (and a mode-3 start) to `Targets.broadcastVehicles`. Its `reached()` checks only `TeslaAPI.atHome` and the `TeslaBLE` claim, never `HomeAssistant.at_home`. On main (d98d643 HomeAssistant.py:617) the HA `car_api_charge` with no VIN acted on every at-home connected HA car. Ledger L155 (I1) says "follow main exactly", but it lists only "TeslaAPI's list plus every BLE-known VIN". The ruling text and main's behaviour disagree for HA-only installs, which lose the mode-1 stop for an unrecognised car. Needs a ruling |
| 62 | test_failed_ble_stop_falls_back_to_fleet_before_the_list_loads | A Fleet-only car can be stopped before its list loads, after BLE fails | INTENTIONALLY CHANGED | Ledger L142 (I2) and the 12a report's C1 closure: no candidate until the free list load, which the periodic tick retries. Pinned by `test_a_fleet_only_car_is_stopped_once_the_list_loads`, `test_a_failed_boot_list_load_recovers_without_an_arrival` and `test_stop_falls_to_fleet_after_60s_once` |
| 63 | test_fleet_failure_falls_to_home_assistant_for_the_target_only | A Fleet failure falls to HA for that car | PARTIAL | Deliberately gone: `Reconciler.py` uses `p = paid[0]`, so HA is reached only once Fleet is excluded (plan Task 14 row 10). The pinning test the plan names, `test_fleet_then_ha_never_in_one_pass`, is absent at 8b22849, and no reconciler test has both Fleet and HA |
| 64 | test_fleet_only_targeted_commands_work_from_boot | Fleet commands work from boot; a failure is counted | INTENTIONALLY CHANGED | As 62. Also `test_vehicle_list_loads_without_any_legacy_command` and `test_failed_paid_call_retries_once...` |
| 65 | test_ha_only_targeted_stop_affects_only_the_target | An HA stop for one car toggles only that car's switch | COVERED | `HomeAssistantProvider._call(vin, ...)` resolves a single attachment (`test_ha_outcomes`); desired state is per car |
| 66 | test_loaded_list_without_the_car_still_skips_fleet | A car not on the account's list never gets a paid Fleet call | COVERED | `test_fleet_commands_resolve_the_car_by_vin` (UNSUPPORTED "not listed"); `test_fleet_command_outcomes_and_one_request_each`; `test_a_fleet_only_car_is_stopped_once_the_list_loads` (no candidate) |
| 67 | test_unknown_vin_affects_no_home_assistant_car | An unknown VIN makes no HA call | COVERED | `test_provider_registration::test_home_assistant_provider_follows_entities` (no attachment: not ready) |

### test_vehicle_priority_returns.py (23cb7e8, c563d70)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 68 | test_a_failed_fleet_start_still_falls_to_ha | A real Fleet start failure falls to HA | PARTIAL | As 63 |
| 69 | test_ha_is_not_reached_after_a_fleet_apply_charge_limit | Cost: a Fleet success never also bills HA | PARTIAL | True by construction (`paid[0]`; Fleet DONE settles), but no test has both Fleet and HA. Same missing test as 63 |
| 70 | test_teslaapi_apply_charge_limit_returns_success | Return-value shape of the deleted `applyChargeLimit` | PLUMBING-ONLY | Method deleted |
| 71 | test_the_pre_wake_hold_is_not_a_failure | Cost: a Fleet wake hold (wakeDelayMins) never hands the start or limit to HA | PARTIAL | The hold is NOT_SENT and unpaid (`test_a_wake_held_outcome_is_not_counted_as_the_paid_call`, `test_no_resubmit_loop_during_a_30_minute_wake_hold`). That HA is not substituted is unpinned; same missing test as 63 |
| 72 | test_throttled_apply_charge_limit_is_not_a_failure | Repeated policy limits buy no extra sends | COVERED | The throttle is gone; an unchanged desire is a no-op. Pinned by `test_limit_is_sent_once_and_recorded_as_held`, `test_periodic_reenforce_does_not_undo_an_adopted_limit` and `test_paid_calls_never_exceed_desired_changes` |
| 73 | test_throttled_start_is_not_a_failure | A heartbeat start every cycle buys no extra sends | COVERED | `test_a_start_that_keeps_failing_is_bounded`; `test_offer_flaps_do_not_multiply_paid_starts`; `test_heartbeat_stop_is_sent_once...` |

### test_wall_connector_vins.py, test_workers.py (44c4ddb)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 74 | test_a_provider_without_a_rate_limit_is_asked | The query asks the first candidate | COVERED | Renamed `test_query_asks_the_first_candidate_directly` |
| 75 | test_the_declared_rate_limit_bites_without_time_passing | `live_status` is bounded without time passing | INTENTIONALLY CHANGED | Ledger L116 (pre-flight r4 I7, a 30 s edge gap). Pinned by `test_wall_connector_edges_are_spaced_thirty_seconds` and `test_polling_slows_after_ten_unanswered_polls` |
| 76 | test_ha_start_and_stop_share_one_window_per_car | HA start and stop share one per-car window | COVERED | `test_min_send_gap_spaces_a_start_stop_flip_on_any_provider` (one CHARGING record per car) |
| 77 | test_rate_slot_is_used_only_when_a_command_is_sent | Cost: a read-satisfied or rules-settled attempt consumes no pacing budget | PARTIAL | The excluding and not-sent halves are pinned (`test_an_unsupported_free_provider_falls_through_without_the_gap`; `test_note_outcome_bookkeeping` "wake held"; `test_a_worker_error_that_made_no_request_counts_against_nothing`). Nothing asserts that SATISFIED "read" or "rules: ..." leaves `lastSentAt` at 0, though "read" is in `NOT_SENT` |

### Tests added and deleted inside the range (per-commit scan)

| # | Deleted test | Behaviour | Class | Evidence |
|---|---|---|---|---|
| 78 | test_limit_wiring::test_legacy_fleet_start_sends_no_limit_first (added 23cb7e8, deleted c563d70) | Fleet start sends no limit first (interim) | INTENTIONALLY CHANGED | Ledger L143 ("limit-before-start lost until 12a, by design and closed by 12a"). Reversed by `test_fleet_start_sends_the_limit_first` and `test_an_asleep_fleet_car_with_an_unknown_limit_is_woken_then_limited_then_started` |
| 79 | test_limit_reconciler::test_a_refused_limit_with_a_declared_but_unready_ble_still_blocks_the_start (added 44c4ddb, deleted bba7c4f) | A refused limit still blocks the start while BLE might deliver it | INTENTIONALLY CHANGED | Ledger L128 (I2: c4 over candidates; rewrite the M11 test). Pinned by `test_a_refused_limit_with_a_paired_ble_whose_radio_is_down_still_blocks_the_start` and `test_an_unpaired_ble_does_not_hold_the_start_of_a_car_ha_refused` |

## B. Rewritten tests with removed or weakened assertions

| # | Test | What changed | Class | Evidence |
|---|---|---|---|---|
| R1 | test_held_limits::test_legacy_charge_limits_migrate | `chargeLimits` is no longer gone after load; IDs wait | INTENTIONALLY CHANGED | Ledger L110 (unmatched dropped) and L120 (I9). Pinned by `test_an_unresolved_id_survives_a_restart` and `test_an_empty_vehicle_list_drops_nothing` |
| R2 | test_held_limits::test_realistic_settings_file_migrates | As R1 | INTENTIONALLY CHANGED | As R1 |
| R3 | test_held_limits::test_saved_file_carries_the_store_and_restarts_clean | As R1; the ID resolves after a restart | INTENTIONALLY CHANGED | As R1; the test itself now resolves after a reload |
| R4 | test_held_limits::test_integral_floats_round_trip_as_ints, test_set_rounds_finite_numbers | Wrapper assertions removed | PLUMBING-ONLY | Store-level float and rounding assertions kept |
| R5 | test_limit_reconciler::test_paid_sends_that_never_reached_the_car_rearm... | No fifth send on the same desire | INTENTIONALLY CHANGED | Ledger L117 (I2: one re-arm per desire, at most 4 sends) |
| R6 | test_limit_reconciler::test_a_stop_set_while_a_start_is_in_flight... | The stop now waits `MIN_SEND_GAP` | INTENTIONALLY CHANGED | Ledger L116 (I5) |
| R7 | test_limit_reconciler::test_stale_free_failure_gets_the_real_command_over_ble_before_paid | Paid waits the gap after a BLE try | INTENTIONALLY CHANGED | Ledger L104 (decision 6) and L116 |
| R8 | test_outcome_desired::test_a_superseded_attempt_feeds_the_free_channel... | `lastSentAt` is now stamped for a replaced desire | INTENTIONALLY CHANGED | I5, ledger L116 |
| R9 | test_reconciler_queues::test_a_raising_report_is_logged_by_type_name | Was "secret-token absent from all of caplog"; now absent at WARNING and above only (the DEBUG traceback may carry it) | PARTIAL | The only ruling, Task 6 M4 (ledger L74; slim-task-6-review l.150), covered legacy callbacks because "the legacy path's tasks and callbacks carry no tokens". That reason does not carry over to the reconciler's report path. Slim-task-10 report item 6 notes the change but has no ruling. `test_errors_log_type_names_only_and_warn_once` still pins DEBUG for provider exceptions, so the relaxation is narrow |
| R10 | test_reconciler_queues::test_local_providers_run_inline_even_when_workers_are_threaded | Summary assertions removed | PLUMBING-ONLY | Summaries deleted (ledger L104 decision 7) |
| R11 | test_reconciler_queues::test_an_inline_lane_is_busy_while_it_runs | Running-key summary removed | PLUMBING-ONLY | As R10 |
| R12 | test_reconciler_queues::test_a_raising_after_write_keeps_the_sent_command_done | The raising `cost` case moved from limit to amps | PLUMBING-ONLY | The rules read `cost` before a limit send; the send-once assertion is kept |
| R13 | test_gen2twc_provider::test_disruptive_stop_declared_very_high_cost_and_off_by_default | A mode-2 stop no longer silences the bus at once; desired state only | INTENTIONALLY CHANGED | 12a (stateless desired state). Pinned by `test_disruptive_stop_waits_for_ble_only_when_ble_is_set_up_for_the_car`, `test_non_tesla_car_on_a_twc_gets_the_disruptive_stop_at_once` and `test_twcmaster::test_modes_2_and_3_never_touch_the_bus_here` |
| R14 | test_provider_outcomes_local::test_gen2_stop_and_start_outcomes_and_the_billed_stop_suppression | Cloud start is now suppressed in mode 2 | INTENTIONALLY CHANGED | Ledger L156 (I2). Pinned by `test_mode_2_starts_no_paid_provider` and `test_provider_tables` `legacySuppressed` |
| R15 | test_provider_tables, test_provider_capabilities, test_teslaapi_providers, test_wall_connector_vins::test_fleet_waits_while_the_owner_slot_can_read_energy | Declared `RateLimit` assertions removed | INTENTIONALLY CHANGED | Ledger L104 (decision 6). `test_no_callback_lists_or_test_modes_in_lib` asserts that `RateLimit` is gone |
| R16 | test_wall_connector_vins::test_polling_slows_after_ten_unanswered_polls, test_disconnect_clears_the_cloud_vin... | +30 s before a new edge | INTENTIONALLY CHANGED | Ledger L116 (I7) |
| R17 | test_teslaapi_readonly_gate::test_every_command_method_skips (params), TestRefusalLogging | `car_api_charge` and `applyChargeLimit` dropped; retargeted to `wakeVehicle` | PLUMBING-ONLY | Methods deleted from VehiclePriority; refuse-once logging kept |
| R18 | test_teslaapi_token_slots::test_command_refused_without_usable_fleet | Start, stop and limit assertions removed | COVERED | `test_a_command_412_retires_commands...`; `test_a_data_only_fleet_token_reads_but_never_commands` |
| R19 | test_teslable_pairing_status: test_all_vehicle_commands_skip_a_refused_key, test_unproven_and_pairing_keys_are_still_commanded, test_no_usable_key_fails_the_all_vehicle_command | Start, stop and limit halves removed | COVERED | BLE readiness is the claim (TeslaBLEProvider.py:55). Refused means no claim: `test_update_settings_seeds_keyed_entries_as_unproven_and_paired_as_managed`, `test_later_boot_claims_held_and_paired_vins`. Unproven or pairing is still ready: `test_provider_is_local_free_and_ready_for_claimed_vins`, `test_pairing_is_an_unproven_claim`, `test_pairing_failure_keeps_an_unproven_claim`. A non-ready provider is skipped: `test_an_unpaired_ble_does_not_hold_the_start_of_a_car_ha_refused` |
| R20 | test_vehicle_priority / _returns walk, cadence and None-return tests | Retargeted from start/limit to `wakeVehicle` and `setChargeRate` | COVERED | The walk behaviour is kept for the methods that remain. For start, stop and limit, HA cadence after a Fleet failure is replaced by `paid[0]` plus `MIN_SEND_GAP` (see 63) |
| R21 | test_vehicle_priority::test_set_charge_rate_targets_the_car | `targetVIN("car_api_charge")` removed | PLUMBING-ONLY | Method deleted |
| R22 | test_teslaapi_token_classification::TestUnknownToken | `car_api_available()` replaced by `slotFor` | COVERED | Same assertion through `slotFor` |

## Focus areas

- **Cost safety.** Paid caps, wakes and retries are well pinned on ScriptedProviders, and the main Fleet paths use real requests. Three holes:
  - Wire-level two-car isolation for Fleet (rows 28, 29, 31, 32).
  - Fleet and HA together (rows 63, 68, 69, 71).
  - Read or rules outcomes and the gap (row 77).
- **Tokens.** Refused tokens are well pinned:
  - a 412 or 403 stops commands with zero requests (`test_a_command_412_...`);
  - a 401 retires the slot;
  - HA never logs the response body.

  One weakening: R9.
- **Main parity for stopChargingMode 1/2/3.** Mode 2 and 3 parity is pinned (rows 38–44, R13, R14, `test_an_anonymous_point_fans_out_as_main_did`, `test_mode_2_starts_no_paid_provider`, `test_modes_2_and_3_never_touch_the_bus_here`). The exception is the HA-only broadcast (row 61, GAP).
- **Held and normal limit restore.** Covered, including departure, hourly restore and c6. One missing assertion: row 16.
- **BLE pairing.** Covered through claims (R19, row 25).

## GAPs and PARTIALs, with proposed tests

| Rows | Proposed test | What it asserts |
|---|---|---|
| 61 (GAP) | `test_charging_reconciler::test_an_anonymous_point_reaches_at_home_home_assistant_cars` | An HA-only install with an anonymous Gen2 point in mode 1: `stopCarsCharging(anon.key)` sets CHARGING False for every at-home HA car, and one switch `turn_off` is sent per car. Or, if the ruling is to keep the exclusion, assert it explicitly and cite the ruling |
| 16 | `test_limit_reconciler::test_a_restore_stamps_the_outside_value` | After a restore attempt is DONE, `v.lastWrite("chargeLimit").value == held.outside` and its source is the provider |
| 28, 29, 31, 32 | `test_charging_reconciler::test_a_fleet_command_for_one_car_sends_nothing_for_another_listed_car` | Real TeslaAPI with two listed at-home cars, B asleep. Desires for A only: a raise, a start and a stop. No `request_history` URL contains B's VIN, and B's `firstChargeNeededTime` is unchanged |
| 56 | `test_reconciler_queues::test_a_stop_submitted_during_a_live_drain_is_still_sent` | A started cloud queue is busy and `drain(5)` runs in a thread. A stop submitted mid-drain runs; a limit submitted mid-drain is dropped |
| 63, 68, 69, 71 | `test_limit_reconciler::test_fleet_then_ha_never_in_one_desire` (plan Task 14 row 10) | Fleet and HA ScriptedProviders. Over an hour of passes, HA gets 0 calls when Fleet returns ERROR 500, "408", "wake held" or DONE, for a limit and for a start. HA is used only once Fleet is excluded (REFUSED) |
| 77 | `test_outcome_desired::test_read_and_rules_outcomes_spend_no_send_gap` | `noteOutcome` with SATISFIED "read" and with "rules: limit unknown" leaves `lastSentAt == 0`, `paidAt` None and `paidSends == 0` |
| R9 | `test_reconciler_queues::test_a_raising_report_logs_no_token_at_any_level` | A report that raises `ValueError("secret-token")` leaves "secret-token" absent from `caplog.text` at DEBUG. Or record a ruling that accepts DEBUG tracebacks on the reconciler path |
