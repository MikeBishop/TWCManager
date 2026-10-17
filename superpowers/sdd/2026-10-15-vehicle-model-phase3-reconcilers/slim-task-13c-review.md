# Slim Task 13c review: one TeslaAPI request helper and status classifier

Reviewed: wt-vm3, fc7bd2f..1028283 (9ca6210 f5d6a03 7ea8250 9e888b2 1028283).
Line numbers are for `lib/TWCManager/Vehicle/TeslaAPI.py` at 1028283 unless another file is named.

## Verdicts

- **Spec compliance: PASS, with 1 deviation (I1).** All four paths go through `_request` and `_classify`, callers keep their own success parsing, and the per-path differences from pre-flight M6 are kept and pinned. `loadVehicleList` still resolves legacy IDs. I1: one read can now send more paid `vehicle_data` requests than at BASE. That breaks the brief's "no new paid call" and the report's claim that the request counts are unchanged.
- **Quality/cost/security: NOT YET.** 0 Critical, 2 Important, 5 Minor.

Suite: 1711 passed, 1 xfailed, the same as the report. The tree is clean afterwards, with no processes left running.

## Mutation check (34 mutations, full unit suite each, every file restored)

31 were killed and 3 survived.

| Behaviour | Mutation | Result |
|---|---|---|
| 10 s timeout | default 30 | KILLED (test_paid_posts_time_out_after_ten_seconds) |
| | read with no timeout | KILLED (table read row) |
| | command/wake with no timeout | KILLED |
| | energy with no timeout | KILLED |
| 401 refreshes the requesting slot | `refreshSlot(self.ownerSlot)` | KILLED |
| | also refresh the *other* slot | **SURVIVED** (M1) |
| | ignore `retried` | KILLED |
| 401 with nothing to refresh retires the slot | drop `slot.clear()` | KILLED |
| 403/412 refuse, keep the tokens, send nothing more | 403 clears the tokens | KILLED |
| | 412 clears the tokens | KILLED |
| | 412 without `refuse("command")` | KILLED (test_backoff_429_and_412_send_nothing_more) |
| | 403 without reportScopeRefused | KILLED |
| | a wake 403 refuses commands | KILLED (test_a_403_on_wake_refuses_wakes_only) |
| 408 | 408 gives ERROR | KILLED |
| 120 s online cache | 0 s | KILLED |
| | 600 s | KILLED |
| | a wake answering online does not refresh the cache | KILLED (the new test) |
| 429 per car | `target = self` (module errorCount) | **SURVIVED** (I2) |
| | `updateCarApiLastErrorTime()` module-wide | **SURVIVED** (I2) |
| | no backoff at all | KILLED |
| | no errorCount 30 | KILLED |
| Connection errors | the except refreshes | KILLED |
| | catch ConnectionError only | KILLED |
| Tokens in logs | log `str(e)` at level 1 | KILLED |
| | `exc_info=True` at level 1 | KILLED |
| | log the request headers in the INFO8 line | KILLED |
| | WallConnectorVins `exc_info=True` | KILLED |
| Read-only hint | log it every time | KILLED |
| Energy and list differences | energy through the generic branch | KILLED |
| | the list resends after a refresh | KILLED |
| | the list backs off on a refusal | KILLED |
| Gen3 | EDGE_MIN_GAP 0 | KILLED |
| | an extra GET on the energy path | KILLED |
| HA guard | guard removed | KILLED |

## Critical

None.

## Important

### I1. A refresh no longer uses up one of `get_car_api`'s three tries, so one read can pay for 4+ `vehicle_data` requests (BASE: 3)

**Evidence.**
- TeslaAPI.py:1755 loops `for _ in range(0, 3)` around `self.carapi._request(...)`.
- `_request` (TeslaAPI.py:296) resends internally after a refresh. Its `retried` flag starts fresh on every call.
- At BASE the refresh was a `continue` inside the same 3-iteration loop, so the resend used up one of the three tries.

**Reproduced** with a temporary probe, since removed. The sequence was 401 "token expired", then a successful refresh, then `could_not_wake_buses` on every answer. `vehicle_data` was requested **4** times (BASE: 3).

**Further exposure.** Each loop iteration can refresh again: three 401 expiries in one read gives three refreshes and six GETs. This is rare in practice. Still, it is a new paid call ($0.002 per `vehicle_data`), the brief forbids that ("no new paid call"), and the report says each path's request count is unchanged.

**Fix (a few lines).** Make the 3-try budget cover all requests sent, as BASE did. One option: `_request` returns the number of attempts, or takes `retried=` from the caller, and `get_car_api` subtracts it. Simpler: the loop in `get_car_api` counts tries and breaks once `hit.call_count` reaches 3. Pin it with a test: 401 expired, then refresh OK, then `could_not_wake_buses` every time, and expect 3 `vehicle_data` requests and 1 refresh.

### I2. "429 backs off per car" works but is not pinned

**Evidence.** TeslaAPI.py:404-406 sets `target = vehicle or self` and calls `updateCarApiLastErrorTime(vehicle)`.

A probe confirmed per-car behaviour on a command 429:
- the car has `errorCount` 31 and a `lastErrorTime`;
- the module has `carApiLastErrorTime` 0 and `errorCount` 0;
- `getCarApiRetryRemaining()` with no car returns 0.

Two mutations survived the full suite:
- `target = self`, which brings back BASE's module errorCount;
- `self.updateCarApiLastErrorTime()` with no car, which blocks every car and the vehicle list for 10 minutes.

The table's `backoff=bool(api.carApiLastErrorTime or car.lastErrorTime)` cannot tell the two apart. This is the intentional change 3 that the report claims, so it needs a pin.

**Fix (test only).** For read and command 429, assert:
- `car.lastErrorTime > 0` and `api.carApiLastErrorTime == 0`;
- `api.getCarApiRetryRemaining() == 0` while `getCarApiRetryRemaining(car) > 0`.

For list 429, assert that the module backoff is set. A table column `backoff="car" | "module" | None` covers all of it.

## Minor

### M1. Nothing pins that a Fleet 401 never contacts Owner auth when both slots hold refresh tokens

The table stores only a Fleet token. A mutation that also refreshes the other slot survived. `refreshSlot(self.ownerSlot)` alone is killed, so the main risk is covered.

**Fix:** in one 401 cell, also store an Owner token with a refresh token, mock the Owner refresh URL, and assert it gets 0 calls.

### M2. The vehicle list still uses a 30 s timeout, held under `vehicleListLock`, plus a refresh of up to 30 s

TeslaAPI.py:542 has `timeout=30`; TeslaTokenSlot.py:33 has `REFRESH_TIMEOUT = 30`. Both are pre-existing and pinned (`TIMEOUTS["list"] = 30`). So "10 s on every request" holds for read, command, wake and energy, but not for the list.

**Lock analysis.** `vehicleListLock` is taken only in `loadVehicleList` (TeslaAPI.py:459). Its callers are:
- the background-task thread (`loadList`, TWCManager.py:321);
- `Telemetry.updateVehicles` with `loadList=True` (Telemetry.py:363-369), on the MQTT thread.

The main/serial loop and the reconciler never take it (TWCManager.py:1024 only queues the task). Nothing under the lock takes `settingsLock`:
- `refreshSlot` and `_classify` queue `saveSettings` rather than lock;
- `resolveHeldLimits` runs after the lock is released (TeslaAPI.py:480).

So `vehicleListLock -> settingsLock` cannot be inverted. The worst-case hold is about 60 s, and it stalls only the background queue and an MQTT callback for a car missing from the list.

**Fix (Task 13, as ruled):** drop the list timeout to 10 s and set REFRESH_TIMEOUT to 10 s, or release the lock around the GET. That needs a "listing in flight" flag so that two callers do not both list.

### M3. `_vehicleList` repeats the classifier's list of refusal status codes

TeslaAPI.py:544 has `refused = req is not None and req.status_code in (401, 403, 410, 412)`. This duplicates `_classify`'s knowledge.

**Fix:** use `outcome.kind == REFUSED` (saves a line). The one difference: a 401 whose refresh was unreachable returns UNREACHABLE, so it would back off rather than return None. That matches what the energy and read paths already do; choose deliberately.

The other size question:
- −85 is honest: numstat shows TeslaAPI.py +192/−287, HA +5/−1, WC +8/−2;
- the per-path branches in `_classify` are the brief's required differences, not duplication;
- the Owner live_status 404 check (TeslaAPI.py:711-715) could move into the energy branch of `_classify`, but only with a "live" flag, so it saves almost nothing.

### M4. Two test files are no longer black-clean

- test_teslaapi_request_errors.py was black-clean at BASE and is not now: long `NO = dict(...)`, the `EXPECTED.update({` block, and long one-line cells.
- test_wall_connector_vins.py has new code with `;`-joined statements and one blank line before a def.

autoblack.yml reformats these on push to main. **Fix:** run black on the two files.

### M5. Unreported or out-of-scope behaviour and token-log notes

- **Second answer after a refresh.** At BASE the read path ignored a 403/410/412 that came back after a refresh, because `not refreshed and ...` short-circuited. It now pauses the slot. This is benign (arguably a fix) but missing from Intentional changes.
- **Token text in refresh logs (pre-existing, outside this diff).** TeslaTokenSlot.py:243-244 and :256-257 log `{e}` at WARNING from `refresh()`'s catch-alls. A KeyError there names the key, not the value, but a `setTokens` or decode error's text is not controlled. **Fix:** log `type(e).__name__` only. Bundle it with the Storm Watch item already ruled for Task 13.
- **WallConnectorVins.py:152-158 is safe.** `traceback.format_tb` prints frames and source lines, never exception messages or chained exceptions, and the pinning test kills `exc_info=True`.
- **The `_request` INFO8 line is safe.** It logs the method, a VIN path and the status. It never includes headers (killed by the `log_headers` mutation).

## Checked and fine

**Paid calls and slots**
- Commands and wakes use `slotFor("command")`, which is Fleet only, because Owner never grants command.
- The free online check uses the command slot when it can read, otherwise the read slot.
- A 401 refreshes the requesting slot's own `refreshURL`.
- The energy path stays on the free `/products` and `live_status`, never a vehicle endpoint.
- There is no new wake.
- The command path makes at most 2 POSTs: 1 plus 1 resend after a refresh, as at BASE.

**Gen3**
- The cloud VIN from Fleet live_status still flows. WallConnectorVinReader is unchanged apart from the log.
- The 30 s EDGE_MIN_GAP is pinned (the mutation was killed).
- An energy 403 latches only the Wall Connector read.

**Carried items**
- The status-deferral test (7ea8250) pins that the read walk ends at a deferral.
- The HA guard is pinned.
- The wake-online cache test is new and kills its mutation.

**Accepted rulings**
- The 10 s read timeout is pinned by the read row.
- A refreshed token refused again now retires the slot (pinned by read×401).
