# Task 6 review: Owner API and Fleet API as separate providers (3f89dea)

Reviewed: the brief, the implementer report, the diff `607e6d1..3f89dea`, and the checkout at `wt-vm2` (read only). Probes and mutations ran in scratch copies, `scratchpad/probe-t6` (at 3f89dea) and `scratchpad/probe-t6-base` (at 607e6d1). The probe tests are in `scratchpad/t6tools/`.

## Verdicts

- **Spec compliance: PASS.** Every name, signature and behaviour in the brief's Interfaces is present as written. The implementation adds two things the brief did not ask for. Neither conflicts with it:
  - `get_car_api` short-circuits when it is given an explicit slot that is no longer `usable("read")` (`TeslaAPI.py:2214`).
  - `ready()` returns False for an undeclared capability or a `None` vehicle (`TeslaAPIProviders.py:47,79`).
- **Task quality: PASS WITH FIXES.** There are two Important test-quality findings and no Critical ones. The production code is sound and the cost gate sits in the right place. "Fleet reads only when Owner cannot" is enforced in `canRead` (`Sources.py:96`), not by registration order, so Task 8's reordering cannot create a paid read.

Focused run (the brief's Step 4 set plus `test_telemetry_registry.py`): 108 passed.

## Cost checks

- **New paid paths: none.** Commands and wake still go only through `setChargeRate`/`wakeVehicle` → `slotFor("command")`. `FleetAPIProvider.setAmps`/`wake` are not called by anything live yet (Task 9). Paths with no slot argument (`car_api_available`, `is_awake()`) still use `slotFor("read")`.
- **Fleet only when Owner cannot.** Fleet `canRead` and Fleet `ready(READ_*)` both require `not ownerSlot.usable("read")`. I mutation-checked this in `probe-t6`:
  - M1, Fleet `canRead` gate removed: caught by `test_fleet_reads_only_when_owner_cannot` and by the cost test `[unusable]`.
  - M6, provider read gate removed: caught.
  - M7, Fleet `slot()` returns Owner: caught.
  - M3, fetch drops `slot=`: caught.
  - M5, `get_car_api` ignores its `slot` argument: caught.
  - M8 and M9, Fleet claim made static or snapshotted: caught.
  - Survivors: M2, M4 and M10. See findings I1, I2 and m1.
- **Timing change: only the Concern 1 error path,** measured below.
- **Claims are live.** `"FleetAPI"` claims `lambda: carapi.fleetSlot.usable("command")`, so a Fleet token stored after the listing turns the car managed, and clearing the slot reverts it. `"OwnerAPI"` is `False`/`"listed"`. Both claims are made at every bind, and `"TeslaAPI"` is no longer claimed. No lib code reads a `"TeslaAPI"` claim; the only uses left are synthetic test claims in `test_registry_vehicle.py` and `test_registry_membership.py`.
- **`ready()` and `available()` do no I/O.** They read slot state only. The one side effect is `usable()` → `reportScopeRefused`, which writes one ERROR log line per token and purpose. That is existing slot behaviour, not network I/O.
- **No token in logs or reprs.** The new code logs nothing, and no `__repr__`/`__str__` exists on providers, sources or slots. `get_car_api` logs the URL and never the header.
- **Names later tasks consume.** All exist as named:
  - Task 7: `api.providers()` returns `[Owner, Fleet]`, plus `ownerSlot`/`fleetSlot`.
  - Task 9: `.module`, `.readSource.provider`, `FleetAPIProvider.available`, `OwnerAPI`/`FleetAPI`.
  - Task 10: `FleetAPIProvider.ready(..., SET_AMPS)` for read-only.
  - Forward note, not a Task 6 defect: Task 7 calls `ready(None, READ_WALL_CONNECTOR_VINS)`, and both providers return False today for `vehicle is None`. Task 7 lists `TeslaAPIProviders.py` readiness in its Modify set, so it must relax that guard there.

## Concern rulings

### Concern 1: Fleet reads in the same cascade after Owner 401/403/410/412. Ruling: KEEP.

**Mechanism.** The error handler `slotRequestFailed` clears the Owner slot (401) or pauses it for an hour (403/410/412). The Owner source then returns None, and the cascade reaches the Fleet source. Fleet `canRead` is now true, and Fleet's `is_awake` returns the Owner's cached 2-minute "online" without a request. So Fleet makes one `vehicle_data` ($0.002) in the same cascade. On base, the same Fleet read happened at the next read, through `slotFor("read")`.

**Per error event.** These counts come from `t6tools/test_probe_concern1.py`, run on both trees:
- Owner `vehicle_data` refused (403, 412, or a non-"expired" 401):
  - New tree: 1 Fleet `vehicle_data` in poll 1, then 0.
  - Base tree: 0 in poll 1 and 1 in poll 2.
  - Total over three polls: 1 on both.
  - When the same poll also reads location (`update_charge` + `update_location(0)`), base already paid the Fleet read inside poll 1, so the two trees are identical.
- Owner `vehicles/{vin}` refused: identical on both trees. The refusal is cached as not-awake for 2 minutes, and Fleet reads only once that cache lapses.

**Does a paused slot re-trigger it every poll? No.** While paused, `ownerSlot.usable("read")` is False, so the Owner source is skipped with no request and Fleet reads directly, exactly as `slotFor("read")` did on base. The event recurs only when the pause expires, once per `PAUSE_SECONDS = 3600`, and only if Tesla refuses again. A 401 clears the slot, so it happens once.

**Per hour.** These counts come from `t6tools/test_probe_hour.py`: a fake clock shared by the registry and `time.time`, the Owner token persistently refused, and 2 simulated hours.

| Poll cadence | Fleet `vehicle_data`, base | Fleet `vehicle_data`, new | Failed polls, base | Failed polls, new |
|---|---|---|---|---|
| 60 s (polls faster than `READ_MAX_AGE` = 300 s) | 20 | 20 | 2 | 0 |
| 400 s (every poll needs a read) | 16 | 18 | 2 | 0 |

- At 60 s polling the change costs nothing: the next poll's staleness-driven read is simply moved earlier.
- When every poll reads anyway, the new tree pays **+1 `vehicle_data` per error event**. That is the read base lost at the refused poll, when it returned False into `car_api_charge`/`applyChargeLimit`.
- Worst case: one extra read per car per hour, only while an Owner token keeps being refused with 403/410/412. That is $0.002/h, or about $1.45 per car per 30 days. A 401 costs at most one extra read, once.
- No wake and no command cost is added. Wake never comes from reads. On the error poll, a start/stop command can now go out one poll earlier, but it would have gone out on the next poll anyway.

**Why keep it.**
- The brief's `canRead` spec produces this behaviour directly.
- `slotRequestFailed` says it deliberately records no API error "so the next poll can use the other slot at once".
- The extra read buys data the old code dropped: a failed `update_charge` that blocks start/stop and charge-limit handling for that poll.
- It is bounded at one per hour per car.

**What restoring "wait for next poll" would need.** Per-cascade state, for example "the Owner slot became unusable during this read", threaded through `canRead`. That adds complexity to save at most $0.002/h in a misconfiguration that is already logged at ERROR every hour.

**If the persistent case matters,** the better lever is upstream of both trees: stop re-trying an Owner token that Tesla keeps refusing with 412 ("only available on fleetapi") every hour. That is out of scope for Task 6.

**Pin the behaviour.** It is not pinned today; see I2.

### Concern 2: black scope. Ruling: ACCEPT.

The touched lib files pass `black --check` (26.10.1). The venv black would reformat `tests/unit/test_teslaapi_providers.py` and `tests/unit/test_reads_no_wake.py`, but CI's autoblack excludes `tests/*` (`.github/workflows/autoblack.yml:35`). Running black over the whole of `lib/TWCManager/Vehicle/` would have touched files outside the task.

### Concern 3: fixture changes in `test_reads_no_wake.py` and `test_telemetry_registry.py`. Ruling: ACCEPT. The change was necessary.

`canRead` now requires a usable slot. Without a token, the API source would be skipped, and assertions such as `test_feed_vouches_for_a_value_the_api_reobserved`'s `get_car_api.called` would quietly change meaning. Storing an Owner token, and having the stand-ins accept `slot=None`, keeps what each test asserts.

### Concern 4: Fleet `ready()` refuses free READ_LIST/READ_ONLINE while Owner can read. Ruling: ACCEPT.

The brief's "for reads" has no exception, and Owner serves both for free.

### Concern 5: `registerProviders` not called yet. Ruling: ACCEPT.

This was already ruled acceptable until Task 8. Reads stay owner-first by registration order. Cost safety does not depend on that order, because the gate is in `canRead`.

## Findings

### Critical

None.

### Important

**I1. `test_a_paused_slot_sends_nothing` is vacuous.**
- Where: `tests/unit/test_teslaapi_providers.py:106-112`.
- Evidence: with the guard at `TeslaAPI.py:2214-2216` removed (mutation M4), the test still passes. The request really is sent: under `requests_mock` the unguarded call returns `(True, {...})`. The test passes only because the real network request fails. The report presents it as a paused-slot guard, but it guards nothing.
- Fix: take `requests_mock`, register `m = requests_mock.register_uri(ANY, ANY, json={"response": {"state": "online"}})`, then assert `(False, None)` and `m.call_count == 0`.

**I2. Nothing pins that a paused (not empty) Owner slot hands reads to Fleet, and nothing pins Concern 1's count.**
- Where: `tests/unit/test_teslaapi_providers.py`, beside `test_fleet_reads_when_owner_holds_no_token`, line 164.
- Evidence: mutation M2 survives the whole focused set. It changes the Fleet gate at `Sources.py:96` to `self.carapi.ownerSlot.empty()`. Under M2, a paused Owner slot means no cloud reads at all for an hour, and the Concern 1 ruling rests on exactly this paused-Owner path.
- Fix: add a test that holds both tokens, mocks Owner `vehicles/{vin}` online and Owner `vehicle_data` at 403, and mocks Fleet online plus data.
  - After `car.update_charge()`, assert `True`, Owner data `call_count == 1` and Fleet data `call_count == 1`.
  - Then call `update_charge()` again with the field stale and assert Owner URLs are not called again.
  - `t6tools/test_probe_concern1.py` is a ready starting point.

### Minor

**m1. The Fleet read-scope gate is not distinguished from the command-scope gate.**
- Where: `TeslaAPIProviders.py:93`.
- Evidence: mutation M10 survives. It changes `available(READ_*)` from `usable("read")` to `usable("command")`. Every test uses the full-scope `fleet_token()`.
- Fix: add a case with `fleet_token(scp=(<data scope only>,))` asserting `available(C.READ_CHARGE) is True and available(C.SET_AMPS) is False`, and `ready(v, C.SET_AMPS) is False`.

**m2. The vehicles page and vehicle detail page now show two claims for every listed Tesla.**
- Where: `vehicles.html.j2:32`, `vehicleDetail.html.j2:25`.
- Evidence: every car listed through the API now reads "OwnerAPI (listed), FleetAPI (listed)", even when no Owner token is held. This is cosmetic and is what the brief mandates.
- Fix: note it for Task 10's endpoint work, or have a later task show claim status, for example by hiding the Owner claim when the Owner slot is empty.

**m3. Fleet reads on the error poll skip their own free online check.**
- Where: `Sources.py:110`.
- Evidence: on the Concern 1 path, Fleet's `is_awake(slot=fleet)` uses the Owner's cached "online" from the same cascade. This is correct, since the cache is under 2 minutes old and the car is known online, and it saves a free call. It only means the Fleet `vehicle_data` there is not preceded by a Fleet `vehicles/{vin}`.
- Fix: none needed. Mention it in the I2 test's comment.
