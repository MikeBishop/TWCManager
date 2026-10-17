# Slim Task 13c report: one TeslaAPI request helper and status classifier

Worktree wt-vm3, branch vehicle-model/phase3, BASE fc7bd2f. Not pushed.

**Status: DONE.**

## Commits

| SHA | Subject |
|---|---|
| 9ca6210 | Drive the vehicle list tests through requests_mock (test plumbing only) |
| f5d6a03 | One TeslaAPI request helper and status classifier for reads, commands, the vehicle list and energy sites |
| 7ea8250 | Pin that a status deferral ends the read walk; guard HA fetch without an attachment (13b Minors 1 and 3) |
| 9e888b2 | Log a failed Wall Connector VIN query's frames, never its message (12b parked item) |
| 1028283 | Pin that a wake answering online refreshes the free online check's cache (gap fill) |

## Tests

Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1711 passed, 1 xfailed**. BASE was 1675 passed, 1 xfailed. The +36 are 32 table cells, the Minor 1 test, the Minor 3 test, the traceback test and the wake-cache test. No test was deleted.

## Size

`git diff --numstat fc7bd2f -- lib`:

| File | + | − | Δ |
|---|---|---|---|
| Vehicle/TeslaAPI.py | 192 | 287 | −95 |
| Providers/HomeAssistantProvider.py | 5 | 1 | +4 |
| Providers/WallConnectorVins.py | 8 | 2 | +6 |
| **lib total** | 205 | 290 | **−85** |

The helper commit alone is −95. The two carried fixes add +10. That is about 35 lines short of the expected −120. The gap is the per-path differences the brief and pre-flight M6 require me to keep, which a uniform classifier would have dropped:
- energy refusals latch only the Wall Connector read;
- read and list 403/410/412 pause, while command and wake 403/412 refuse;
- a 410 on a command is an ERROR;
- only commands refuse after a failed refresh;
- the list does not resend.

I found no other duplication among the four paths. Storm Watch (EMS/TeslaPowerwall2.getStormWatch) is a fifth request path with its own semantics, outside this task (see Concerns).

## What changed

- `TeslaAPI._request(slot, method, path, purpose, body=None, timeout=10, vehicle=None)`:
  - builds the headers per attempt, so a resend after a refresh carries the new token;
  - sends to `path` under the API root, i.e. `slot.baseURL` minus `vehicles`, which covers the proxy too;
  - resends once only when `_classify` returns `_REFRESHED`;
  - returns `(response, None)` for a 200, otherwise `(response or None, Outcome)`;
  - turns a transport error into `Outcome(ERROR, type(e).__name__)` with nothing logged;
  - logs one INFO8 line with the method, path and status code. The path holds a VIN and never a token.
- `TeslaAPI._classify(slot, status, purpose, body, vehicle=None, retried=False)` holds all the status handling. `purpose` is `read`, `list`, `command`, `wake` or `energy`.
- `vehicle=` was added to both signatures, which the brief did not list. The 429 backoff is per car, so the classifier needs the car.
- Deleted: `slotRequestFailed`, `commandRefused`, `_energyGet`, `_energyURL`, `_energyRefused`, `ENERGY_REFUSALS`, `vehicleListURL`, `ENERGY_TIMEOUT` and `COMMAND_TIMEOUT`. Both timeout constants were 10, which is now the helper's default.
- `get_car_api`, `_paidPost`, `_vehicleList`, `_fetchEnergySites` and `wallConnectorVins` call the helper and keep their own success parsing.
- `get_car_api` keeps its 3-try loop for `could_not_wake_buses` and transient error bodies. The loop body was compacted.
- The dead `except TypeError` around `get_car_api` in `update_vehicle_data` is gone, because `get_car_api` always returns a pair.
- `loadVehicleList` is unchanged and still calls `heldLimits.resolveLegacyIds` (via `resolveHeldLimits`). `updateChargeAtHome` still loads through `loadList`.

### The classifier table (the spec, recorded from BASE before any lib change)

`test_every_path_classifies_status_codes` covers 4 paths × 8 answers: 401 expired, 401 rejected, 403, 408, 410, 412, 429 and never sent. Every cell asserts:
- the result;
- the request count on that path's URL;
- the refresh count;
- whether the token was kept, renewed or cleared;
- the pause (none, an hour, or latched);
- `refusedPurposes`;
- the Wall Connector latch;
- the API backoff;
- `last_request.timeout` (read 10, list 30, command 10, energy 10);
- that neither the access token, the renewed token nor the refresh token appears in caplog at level 1.

The "never sent" row raises a `RequestException` whose text contains the token.

At BASE every cell passed except the read row's timeouts (BASE had none) and read×401-expired, where BASE left the refreshed slot alone after a second 401. Both are listed under Intentional changes.

| | read | list | command | energy |
|---|---|---|---|---|
| 401 expired (refresh OK) | refresh, resend, 2nd 401 clears | refresh, **no resend**, no backoff | refresh, resend, 2nd 401 clears | WC latch, **no refresh**, token kept |
| 401 rejected | clear + save | clear + save | clear + save, REFUSED 401 | WC latch, token kept |
| 403 | pause 1 h | pause 1 h | refuse("command"), REFUSED 403 | WC latch + scope log (Storm Watch keeps `usable("energy")`) |
| 408 | False, no backoff | False, backoff | UNREACHABLE 408 | None |
| 410 | pause 1 h | pause 1 h | ERROR 410 | WC latch |
| 412 | pause latched | pause latched | refuse("command"), REFUSED 412, reads untouched | WC latch |
| 429 | car backoff | backoff | ERROR 429, car backoff | None, no backoff |
| never sent | False, no refresh | False, backoff | ERROR RequestException, no refresh | None |

Pre-flight M6 (preflight-r4.md) is covered as follows:
- "the list does not retry after a 401 and starts no backoff" is the list×401 cell;
- "the energy 403 retires Wall Connector reads only" is the energy×403 cell;
- "a command after a 401 retries once after a refresh" is the command×401 cell;
- the kept `resolveLegacyIds` call is pinned by test_limit_wiring::test_legacy_ids_resolve_once_from_the_first_vehicle_list, which passes.

Wake follows the command column. Its 403 is `UNREACHABLE "wake refused"` (pinned in test_provider_tables). A failed refresh refuses commands only on command and wake (test_a_503_refresh_keeps_the_tokens_and_stops_paying, test_an_unrefreshable_expired_token_is_retired). A refresh that is unreachable gives `UNREACHABLE "token refresh"`.

### Intentional changes

1. **Vehicle reads time out after 10 s.** At BASE `get_car_api` (vehicle_data and the free `vehicles/{vin}` check) had no timeout. This follows the brief's `timeout=10` and is pinned by the table's read row.
2. **A read whose refreshed token gets an "expired" 401 again now retires the slot**, as a command already did. At BASE the read path kept the slot, so every poll paid for another refresh with a token Tesla kept refusing. The task text says "401 with nothing to refresh retires the slot", and the brief says "401 refreshes once and retries once, else retires the slot". Pinned by the table's read×401 cell.
3. **A command's 429 raises the car's `errorCount` to 30**, not the module-wide one. The car's backoff is the same 10 minutes, because `getCarApiErrorRetryMins(vehicle)` takes the maximum of the two. Other cars' next backoff no longer jumps to 10 minutes. The vehicle list's 429 now sets errorCount ≥ 30 module-wide, so the list waits the full 10 minutes instead of escalating from 0.
4. **The vehicle list's DEBUG dump of the whole response body and its INFO6 "Response:" body line are gone**, as are the energy paths' DEBUG transport-error lines. The INFO8 status line in `_request` replaces them.

## Behaviour checklist (each has a test that fails if it breaks)

| Behaviour | Test(s) | Mutation (all on wt-vm3 after commit, each restored) |
|---|---|---|
| 10 s timeout | table `timeout` assertion; test_paid_posts_time_out_after_ten_seconds; wake-cache test | default 30: KILLED |
| 401 refreshes the requesting slot (Fleet auth for Fleet) | table 401 cells (refresh count on FLEET_REFRESH_URL); test_an_expired_token_on_wake_is_refreshed_at_fleet_auth_once | `refreshSlot(self.ownerSlot)`: KILLED |
| refresh once only | table read/command×401 (calls=2, refreshes=1); test_get_car_api_refreshes_at_most_once | ignore `retried`: KILLED |
| 401 with nothing to refresh retires | table "401 rejected" cells; test_owner_401_clears_owner_and_next_read_uses_fleet | drop `slot.clear()`: KILLED |
| list does not resend after 401 | table list×401 | always `_REFRESHED`: KILLED |
| 403/412 refuse commands, keep tokens | table command×403/412; test_a_command_412_retires_commands_and_wakes_until_the_token_changes | 412→pause: KILLED; drop reportScopeRefused: KILLED |
| energy refusals latch the WC read only | table energy cells | energy through the generic branch: KILLED |
| reads 403/410 pause 1 h, 412 latched | table read/list cells | always latch: KILLED |
| 408 unreachable | table command×408 | 408→ERROR: KILLED |
| 429 backs off | table 429 cells; test_backoff_429_and_412_send_nothing_more | no backoff: KILLED |
| transport errors never crash, never refresh | table "never sent" cells; test_a_wake_or_command_that_never_left_is_an_error_and_refreshes_nothing | (result/refresh asserted) |
| tokens never logged, incl. exception text | table caplog assertion at level 1 (every cell) | `logger.debug(str(e))`: KILLED |
| free online check cached 120 s | test_wake_checks_the_free_online_state_first_and_holds_between_wakes | cache 0 s: KILLED |
| wake "online" refreshes that cache | **new** test_a_wake_answering_online_refreshes_the_online_cache | drop `lastVehicleAwakeTime = now`: SURVIVED at BASE suite → KILLED with the new test |
| read-only INFO hint once per Fleet slot change | test_teslaapi_readonly_gate | log every time: KILLED |
| Gen3 cloud VIN via live_status | test_wall_connector_vins (unchanged, passing); the 30 s EDGE_MIN_GAP lives in WallConnectorVinReader, untouched | — |

Cost: no new paid request. Each path makes the same number of requests as at BASE. The table counts requests per URL in every cell. A command after a 401 is resent once after the refresh, as at BASE.

## Carried items

- **13b Minor 1.** Added test_reads_no_wake::test_a_status_deferral_ends_the_read_walk_before_home_assistant. It wires Owner and HA, both ready, with Owner deferred and a stored value, and asserts no `is_awake`, no `update_vehicle_data` and no `parse_from_home_assistant`. Mutating TeslaAPIProviders.py's deferral `return True` to `return False` fails it (KILLED). This corrects the 13b mapping row: this test, not test_status_deferral_counts_as_success_without_fetch, pins the walk ending at a deferral.
- **13b Minor 3.** `HomeAssistantProvider.fetch` returns False when the attachment is gone. test_homeassistant_registry::test_fetch_without_an_attachment_reads_nothing fails at BASE with an AttributeError.
- **12b parked item.** WallConnectorVins.apply logs the exception type plus `traceback.format_tb` (frames and source lines, never the message) in place of `exc_info=True`. test_wall_connector_vins::test_a_failed_query_never_logs_its_text has `order.candidates` raise `RuntimeError("Bearer <token>")`. It fails at BASE because the token appeared in the log.

## Deleted-test mapping

No test was deleted. These assertions were edited:

| Test | Change | Classification |
|---|---|---|
| test_teslaapi_vehiclelist::test_loads_once, test_failure_returns_false_and_records_error, test_no_token_makes_no_call | `patch("requests.get")` with a bare Mock → requests_mock, with the same assertions. `test_no_token_makes_no_call` now asserts an empty request history | PLUMBING-ONLY (a Mock has no status code to classify) |
| test_teslaapi_owner_read::test_owner_token_lists_vehicles_from_products | dropped `vehicleListURL(ownerSlot) == OWNER_PRODUCTS`. The test still asserts that the list loads from the mocked /products and that /vehicles gets 0 calls | PLUMBING-ONLY (`vehicleListURL` deleted) |
| test_teslaapi_owner_read::test_fleet_token_keeps_vehicles | `vehicleListURL(fleetSlot) == NA_VEHICLES` → loadVehicleList hits NA_VEHICLES exactly once | PLUMBING-ONLY |
| test_limit_wiring::test_legacy_ids_resolve_once_from_the_first_vehicle_list | its "were the low-level lines captured" guard now looks for the new INFO8 line `Car API get vehicles: HTTP 200` instead of the old INFO8 and DEBUG texts. The token-absence assertion is unchanged | PLUMBING-ONLY for the INFO8 line. The DEBUG body dump it also looked for was removed: INTENTIONALLY CHANGED (Intentional changes, item 4) |

## Locks

- `_request` and `_classify` take no lock.
- `loadVehicleList` still holds `vehicleListLock` across the list GET and any 401 refresh, exactly as at BASE (TeslaTokenSlot's REFRESH_TIMEOUT comment documents this). The order `vehicleListLock -> settingsLock` is unchanged.
- No new HTTP was added under a lock.

## Concerns

1. `vehicleListLock` is still held across the list's HTTP, as at BASE. It is bounded by the 30 s timeout and was not restructured, to keep behaviour unchanged.
2. Storm Watch (EMS/TeslaPowerwall2.getStormWatch) is a fifth Tesla API request path. It is not in this task's four. It sends with no timeout and logs `{e}` exception text at WARNING. It could go through `_request` later with its own purpose.
3. The lib delta is −85 against the expected ≈ −120 (see Size).

## Fix round 1 (slim-task-13c-review.md)

### Commits

| SHA | Subject |
|---|---|
| 2edf146 | Count a resend after a refresh against a read's three tries; pin the 429 scope |
| bcb4042 | Bound a token refresh at 10 s and log its catch-alls by type only |

**Suite:** 1717 passed, 1 xfailed.

**Lib delta:** this round is +28 (TeslaAPI.py +35/−12, TeslaTokenSlot.py +8/−3). Task 13c in total is now **−57**: TeslaAPI.py −72, TeslaTokenSlot.py +5, HomeAssistantProvider.py +4, WallConnectorVins.py +6. Most of the growth is black splitting `_request`'s signature, which now has 9 parameters, and the `get_car_api` call to it.

Every fix has a test that failed before the fix. The mutations below were each applied to the committed tree, run against the full unit suite, and then restored.

### I1: a resend after a refresh now counts against a read's 3 tries

- `get_car_api` counts every request sent, including `_request`'s resend after a refresh. Once one request is left, it passes `resend=False`, and after one refresh it passes `retried=True`.
- `_request` takes `resend=` and `retried=`. This replaces the classifier's special case for the vehicle list, which now passes `resend=False`.
- A read therefore sends at most 3 `vehicle_data` requests and refreshes at most once, as at BASE.
- One small difference from BASE: a refresh on the read's last try returns False without the module-wide `updateCarApiLastErrorTime`. BASE fell through to it.
- **Test:** `test_a_refresh_spends_one_of_a_reads_three_tries`. The answers are a 401 "token expired", a successful refresh, then `could_not_wake_buses`. It expects 3 GETs and 1 refresh, where the old code sent 4.
- **Mutations:**
  - resend not counted: KILLED;
  - `resend` ignored: KILLED.

### I2: the 429 backoff is pinned per car or per module (tests only)

- The table's `backoff` column now reads `"car"`, `"module"` or `"both"`. It looks at `lastErrorTime` and `errorCount` on both the car and the module.
- Read and command 429 expect `"car"`. List 408, list 429 and a list request that never left expect `"module"`.
- **Mutations:**
  - `target = self`: KILLED;
  - module-wide `updateCarApiLastErrorTime()`: KILLED.

### Minors

- **M1.** `test_a_fleet_401_never_refreshes_the_owner_slot[read|command]` stores both slots with refresh tokens and asserts Fleet auth gets 1 call and Owner auth 0. Mutation "also refresh the other slot": KILLED.
- **M2.** The vehicle list now uses the 10 s default timeout; it was 30 s. `REFRESH_TIMEOUT` is now 10 s; it was 30 s. The longest hold of `vehicleListLock` drops from about 60 s to about 20 s.
  - The pins are updated: `TIMEOUTS["list"] = 10`, and test_refresh_post_has_timeout now expects 10. Both are INTENTIONALLY CHANGED.
  - I did not restructure the lock.
- **M3.** `_vehicleList` now treats any REFUSED outcome as a refusal.
  - This is a deliberate choice: a 401 whose refresh never left (UNREACHABLE "token refresh") is a failed list. It backs off and logs, like the read and energy paths.
  - **Test:** `test_a_list_401_whose_refresh_never_left_backs_off`.
  - Mutation "treat UNREACHABLE as a refusal": KILLED.
- **M4.**
  - test_teslaapi_request_errors.py is black-clean again.
  - test_wall_connector_vins.py was not black-clean at BASE, and black would rewrite the whole file. I hand-formatted only the new test.
- **M5.**
  - **Intentional change 5 (added):** at BASE a read ignored a 403, 410 or 412 that came back after a refresh. It now pauses the slot for those, as on a first answer.
  - The two `refresh()` catch-alls in TeslaTokenSlot.py now log `type(e).__name__` instead of `{e}`.
  - **Test:** `test_refresh_never_logs_an_exceptions_text[parse|store]` raises `RuntimeError(<token>)` from each catch-all. Both cases failed before the fix.
