# Free Cached Vehicle Reads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read charge fields from Fleet `vehicle_data_cached` (free, never wakes) before paying for `vehicle_data`, judged by the car's own snapshot stamp.

**Architecture:** A new `FleetCachedProvider` (tier `CLOUD_FREE`, source `"FleetAPICached"`) joins the read cascade after the Owner read and before paid Fleet. The cascade gains a freshness cutoff (event time, else call time minus `maxAge`) that every fetched value must clear, so a stale snapshot falls through to paid. Reads triggered by an event wait up to 15 s for the car's post-event snapshot. Consumers' rules are unchanged; Presence ignores the new source as plug evidence.

**Tech Stack:** Python 3, requests, pytest + requests_mock.

**Spec:** `.superpowers/specs/2026-10-28-cached-vehicle-data-design.md` (read it first; it carries the live measurements and every decision).

## Global Constraints

- Data acquisition only: no consumer (`handsOff`, `uncompleted`, `satisfied`, Watch decisions, Presence rules, policies) changes what it does with a value. The one exception is Presence ignoring `"FleetAPICached"` as plug evidence.
- Never send `vehicle_data_cached` on `ownerSlot` (Owner answers 412).
- A cached 404/412 never calls `slot.pause` or `slot.refuse`; 412 latches only that car.
- Do not touch `_PAID`, `_PAID_PATH`, or the paid-request logging block in `TeslaAPI._request` (the fleet-spend branch owns it; rebase onto it if it has landed).
- Wait values: re-fetch every 3 s, give up after 15 s; event window 60 s.
- Comments say why the code is as it is, never history. Keep growth small: share the `charge_state` field mapping with `update_vehicle_data`, no copied parsing.
- Tests run with `.venv/bin/pytest tests/unit/` (create the venv first if missing: `python3 -m venv .venv && .venv/bin/pip install -e . pytest requests_mock`).

## Review Focus

1. A snapshot older than the cutoff ends a read (the cascade stops on "fetched" without checking the stamp): every cascade test must assert fall-through to the paid provider. (Task 1, Task 3)
2. A TeslaMate-covered car loses its "live feed vouches" freshness under the new cutoff and starts paying. (Task 1: liveness test)
3. A 412/404 from the cached endpoint pausing the Fleet slot for all reads. (Task 2)
4. Presence attributing a plug from a cached charging state with an old home fix, or `checkPlug` losing its paid answer because the cached source answered first. (Task 4)
5. An event-cutoff wait running when nothing will post (idle awake car, no event), adding 15 s before every paid read. (Task 3, Task 5)

---

### Task 1: Freshness cutoff through the read cascade

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/Vehicle.py` (`read`, around line 280)
- Modify: `lib/TWCManager/Vehicle/Providers/Order.py` (`read`, line 107)
- Modify: `lib/TWCManager/Vehicle/Providers/Provider.py` (`fetch` signature)
- Modify: every `fetch` override: `TeslaAPIProviders.py`, `TeslaBLEProvider.py`, `HomeAssistantProvider.py` (accept and ignore the new keywords)
- Test: `tests/unit/test_registry_vehicle.py`

**Interfaces:**
- Produces:
  - `Vehicle.read(field, maxAge, allowWake=False, providers=None, force=False, since: Optional[float]=None, wait: Optional[bool]=None) -> Optional[Observation]`. Effective cutoff = `since` if given, else `now - maxAge`. `wait` defaults to `since is not None`.
  - `Vehicle.freshAt(field: str) -> Optional[float]`: the value's freshness time, `max(obs.at, liveAt)` when a live feed vouches (reuse `_liveAt`), else `obs.at`; None when no value. `age()` becomes `now - freshAt` (clamped at 0) so both share one rule.
  - `ProviderOrder.read(vehicle, field, allowWake=False, providers=None, cutoff: Optional[float]=None, wait: bool=False)`: after each fetch, returns the value only if `cutoff is None or vehicle.freshAt(field) >= cutoff`; otherwise tries the next provider.
  - `Provider.fetch(vehicle, field, allowWake=False, cutoff: Optional[float]=None, wait: bool=False) -> bool`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_registry_vehicle.py`, using fake providers registered on a `ProviderOrder`:
  - `test_cascade_skips_a_value_older_than_the_cutoff`: provider A (free) observes `chargingState` stamped `now - 400`; provider B observes stamped `now`. `v.read("chargingState", 300)` returns B's value and both fetched.
  - `test_cascade_stops_at_a_value_inside_the_cutoff`: A stamps `now - 100`; `read(..., 300)` returns A's, B never fetched.
  - `test_event_cutoff_rejects_a_value_inside_max_age`: A stamps `t0 - 5`, B stamps `t0 + 3`; `read(..., 300, since=t0)` returns B's.
  - `test_event_cutoff_accepts_a_late_fetch_stamped_after_the_event`: clock at `t0 + 10`; A stamps `t0 + 3`; `read(..., 0, since=t0)` returns A's, B never fetched.
  - `test_shortcut_uses_the_event_cutoff`: stored value stamped `t0 - 5` (age 5 < maxAge 300); `read(..., 300, since=t0)` fetches.
  - `test_live_feed_still_vouches_under_a_cutoff`: value from a live report-on-change source stamped `now - 1000`, source live at `now`; `read(..., 300)` fetches nothing.
  - `test_wait_flag_reaches_fetch`: `read(..., 300, since=t0)` calls `fetch(..., cutoff=t0, wait=True)`; `read(..., 300)` calls it with `cutoff=now-300, wait=False`; `read(..., 0, since=t0, wait=False)` passes `wait=False`.

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/pytest tests/unit/test_registry_vehicle.py -k "cutoff or vouches or wait_flag" -v`
Expected: FAIL (unexpected keyword `since`, or wrong provider's value).

- [ ] **Step 3: Implement** the signatures above. `Vehicle.read` reads `now` once at the call and computes the cutoff from it; with `maxAge is None and since is None` it still fetches nothing.

- [ ] **Step 4: Run the new tests and the whole unit suite**

Run: `.venv/bin/pytest tests/unit/ -q`
Expected: all pass (existing callers pass no cutoff-changing arguments, and every existing source stamps at fetch time).

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle tests/unit/test_registry_vehicle.py
git commit -m "Judge cascade reads by a freshness cutoff"
```

---

### Task 2: TeslaAPI cached request and parsing

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`CarApiState`, `_classify`, a new method beside `update_vehicle_data`, and a shared charge-field helper extracted from `update_vehicle_data`)
- Test: `tests/unit/test_teslaapi_providers.py`

**Interfaces:**
- Consumes: Task 1's `observe(..., at=)` use is unchanged.
- Produces:
  - `CarApiState.cachedUnsupported = False` (set by a 412, cleared when the Fleet token changes: compare against `fleetSlot.changes` stored as `cachedRefusedAt`, or reset in the token-change path, builder's choice).
  - `TeslaAPI.read_cached(vehicle) -> Optional[float]`: one GET of `vehicles/<VIN>/vehicle_data_cached` on `fleetSlot` with purpose `"cached"`; on 200 observes the charge fields as source `"FleetAPICached"` at `charge_state.timestamp / 1000` and returns that stamp; else None.
  - `TeslaAPI._observeCharge(vehicle, charge: dict, source: str, at: float)`: the `(key, field)` loop now inside `update_vehicle_data`, used by both.
  - `scheduledChargingPending` from a snapshot: `mode != "Off" and start_time is not None and charging_state == "Stopped"` (spec; unverified for StartAt/DepartBy, see Task 7).

- [ ] **Step 1: Write the failing tests** (requests_mock on `FLEET_ANY`):
  - `test_read_cached_observes_with_the_snapshot_stamp`: response with `charge_state` `{"timestamp": 1793202825642, "charging_state": "Complete", "battery_level": 65, "charge_limit_soc": 50, "scheduled_charging_mode": "Off", "scheduled_charging_start_time": None, ...}`; after `read_cached`, `v.reported("batteryLevel")["FleetAPICached"]` has value 65 and `at == 1793202825.642`; `scheduledChargingPending` observed False; `chargePortOpen` observed from `charge_port_door_open`; no `lat`/`phases` observed.
  - `test_cached_pending_needs_mode_time_and_stopped`: `("StartAt", 1793210000, "Stopped") -> True`; `("StartAt", 1793210000, "Charging") -> False`; `("Off", None, "Stopped") -> False`.
  - `test_cached_412_latches_the_car_not_the_slot`: 412 answer; `read_cached` returns None; `car.cachedUnsupported` True; `api.fleetSlot.usable("read")` still True and no pause.
  - `test_cached_404_latches_nothing`: 404; returns None; `cachedUnsupported` False; slot usable.
  - `test_cached_is_never_logged_as_paid`: a 200 read leaves `v.paidRequests == 0`.
  - `test_cached_never_goes_to_the_owner_api`: with only an Owner token, `read_cached` returns None and no request reaches `owner-api.teslamotors.com`.
  - `test_update_vehicle_data_still_maps_every_field`: existing `vehicle_data` fixture produces the same observations as before the extraction.

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/pytest tests/unit/test_teslaapi_providers.py -k cached -v`
Expected: FAIL (`read_cached` missing).

- [ ] **Step 3: Implement.** In `_classify`, handle purpose `"cached"` before the generic read branch: 200 is None; 401 falls into today's refresh path; 412 sets the car's latch and returns `Outcome(REFUSED, "412")`; anything else returns `Outcome(ERROR, str(status))` without touching the slot or the API backoff. `vehicle_name` from `vehicle_state` is observed as in `update_vehicle_data`.

- [ ] **Step 4: Run the file**

Run: `.venv/bin/pytest tests/unit/test_teslaapi_providers.py tests/unit/test_teslaapi_token_slots.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/TeslaAPI.py tests/unit/test_teslaapi_providers.py
git commit -m "Read Fleet vehicle_data_cached into the registry"
```

---

### Task 3: FleetCachedProvider with the event wait

**Files:**
- Modify: `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py`
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`providers()` returns three)
- Modify: `lib/TWCManager/Vehicle/Reconcile/Belief.py` (`LIVE_READ_SOURCES` gains `"FleetAPICached"`)
- Test: `tests/unit/test_teslaapi_providers.py`

**Interfaces:**
- Consumes: `TeslaAPI.read_cached` (Task 2), `Provider.fetch(..., cutoff, wait)` (Task 1).
- Produces: `FleetCachedProvider` with `name = "FleetAPICached"`, `rank = 5`, `local = False`, `DECLARATIONS = {READ_CHARGE: CLOUD_FREE}`, `SUPPRESSED = CLOUD_SUPPRESSED`, `FIELDS = (CHARGE_FIELDS - {"phases"})`, class attrs `clock = time.time`, `sleep = time.sleep`, `POLL = 3.0`, `WAIT = 15.0`. It makes no claim on the vehicle (claims stay `{"OwnerAPI", "FleetAPI"}`).

- [ ] **Step 1: Write the failing tests:**
  - `test_cached_provider_sorts_after_owner_before_fleet`: with both tokens, `order.ordered(READ_CHARGE)` names are `["OwnerAPI", "FleetAPICached", "FleetAPI"]` (Owner first only when its slot is usable for reads).
  - `test_cached_ready_needs_fleet_read_and_no_latch`: ready with a Fleet token and an attached car, regardless of online state; not ready with only an Owner token; not ready after `cachedUnsupported`.
  - `test_cached_never_asks_online_or_wakes`: fetch on an asleep car makes no `vehicles/<VIN>` GET and no `wake_up`.
  - `test_cached_without_wait_fetches_once`: stale stamp, `wait=False`: exactly one request, returns False only if the stamp is below `cutoff` (True otherwise).
  - `test_cached_waits_for_a_post_event_snapshot`: fake clock/sleep; responses stamped `t0 - 60`, `t0 - 60`, `t0 + 4`; `fetch(v, "chargingState", cutoff=t0, wait=True)` returns True after 3 requests and sleeps of 3 s.
  - `test_cached_gives_up_after_fifteen_seconds`: every response stamped `t0 - 60`; returns False; total sleep ≤ 15 s; then the cascade's paid Fleet `vehicle_data` runs (end-to-end through `v.read(..., since=t0)`).
  - `test_stale_cached_falls_through_to_paid_fleet`: `v.read("batteryLevel", 300)` with a cached stamp 400 s old ends with one paid `vehicle_data` (Review Focus 1).

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/pytest tests/unit/test_teslaapi_providers.py -k "cached_provider or cached_ready or cached_never or cached_without or cached_waits or gives_up or falls_through" -v`
Expected: FAIL (no third provider).

- [ ] **Step 3: Implement** `FleetCachedProvider.fetch`: if the car is latched or the Fleet slot can't read, False; loop `read_cached`, return True when the stamp `>= cutoff` (or `cutoff is None`); when `wait` and time since the first request `< WAIT`, `sleep(POLL)` and retry; else return False. Update `test_two_providers_with_honest_costs` for three providers.

- [ ] **Step 4: Run the unit suite**

Run: `.venv/bin/pytest tests/unit/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle tests/unit/test_teslaapi_providers.py
git commit -m "Add the free FleetAPICached read provider"
```

---

### Task 4: Presence: no plug evidence from the cached source

**Files:**
- Modify: `lib/TWCManager/Vehicle/Presence.py` (`_plugEvidence` line 100; `checkPlug` read at line 241)
- Test: `tests/unit/test_presence.py`

**Interfaces:**
- Consumes: source name `"FleetAPICached"`; `Vehicle.read(..., since=, wait=)` (Task 1).

- [ ] **Step 1: Write the failing tests:**
  - `test_cached_charging_state_is_never_plug_evidence`: car's stored fix is home (hours old); observe `chargingState="Charging"` from `"FleetAPICached"`; no `plugIn` mark, `attributePlugs` not called, `pluggedNow` unchanged. Same for `"Disconnected"` (no `unplug` mark) and `chargePortOpen`.
  - `test_check_plug_reads_without_the_cached_source`: a Fleet-only car; `checkPlug(master, v, since)` issues the paid `vehicle_data` read and never `vehicle_data_cached`, and passes `since` as its cutoff.

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/pytest tests/unit/test_presence.py -k "cached or reads_without" -v`
Expected: FAIL.

- [ ] **Step 3: Implement.** `_plugEvidence` returns None for `obs.source == "FleetAPICached"`. `checkPlug` calls `v.read("chargingState", 0, force=True, since=since, wait=False, providers=<every provider but "FleetAPICached">)`.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/unit/test_presence.py tests/unit/test_gen2_unplug.py -q`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Presence.py tests/unit/test_presence.py
git commit -m "Keep cached snapshots out of plug evidence"
```

---

### Task 5: Event cutoff for the attempt pre-read

**Files:**
- Modify: `lib/TWCManager/Vehicle/Presence.py` (`noteObservation`: a `"drawStop"` mark)
- Modify: `lib/TWCManager/Vehicle/Reconcile/Run.py` (pre-read at line 175)
- Test: `tests/unit/test_charging_reconciler.py`

**Interfaces:**
- Consumes: `Vehicle.read(..., since=)` (Task 1); marks `"plugIn"`, `"unplug"`.
- Produces: mark `"drawStop"`: a TWC-source (`"TWC"`, `"Gen2TWC"`, `"Gen3TWC"`) `actualCurrent` reading below `POWER_FLOWING_AMPS` (1.0, Belief.py) whose same-source previous reading was at or above it. `EVENT_WINDOW = 60.0` in Run.py.

- [ ] **Step 1: Write the failing tests:**
  - `test_draw_stop_marks_the_current_falling`: TWC readings 6 A then 0 A mark `drawStop` at the 0 A reading's time; 0 A then 0 A does not.
  - `test_pre_read_after_a_draw_stop_waits_for_the_snapshot`: drawStop at `t0`, attempt pre-read at `t0 + 2` for `CHARGING`: `vehicle.read` gets `since=t0` (wait defaults True).
  - `test_pre_read_without_a_recent_event_has_no_event_cutoff`: newest mark older than 60 s: `since=None`, plain `maxAge`.
  - `test_amps_attempt_still_reads_nothing`: AMPS attempt (`maxAge None`) makes no read.

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/pytest tests/unit/test_charging_reconciler.py -k "draw_stop or pre_read or reads_nothing" -v`
Expected: FAIL.

- [ ] **Step 3: Implement.** In Run.py, `since` = newest of `markAt("drawStop")`, `markAt("plugIn")`, `markAt("unplug")` when within `EVENT_WINDOW` of `master.vehicleRegistry.now()`, else None; pass it to `vehicle.read`. Import `POWER_FLOWING_AMPS` in Presence lazily, as it imports `Targets`, to avoid an import cycle.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/unit/ -q`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle tests/unit/test_charging_reconciler.py
git commit -m "Give an attempt's read the event that prompted it"
```

---

### Task 6: Watch: cached first, budget only for a paid read

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py` (`_read`, lines 306-351)
- Test: `tests/unit/test_watch_load_step.py` (or a new `tests/unit/test_watch_cached.py` reusing its fixtures)

**Interfaces:**
- Consumes: `ProviderOrder.read(..., cutoff=)` (Task 1); provider name `"FleetAPICached"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_watch_cadence_ignores_the_cached_provider`: Fleet-only car charging at home: cadence is still `cloudChargingReadSecs` (900) and the policy gate still applies (today's `price` comes from the first non-cached candidate).
  - `test_watch_takes_a_snapshot_newer_than_its_last_read_for_free`: a cached snapshot stamped after `lastRead`: the read answers, budget unchanged, no paid request.
  - `test_watch_pays_only_when_the_cached_snapshot_is_older`: snapshot older than `lastRead`: budget spent once at Fleet's price and one paid `vehicle_data`.
  - `test_watch_budget_refusal_behaves_as_today`: stale snapshot and an empty budget: no paid request; the read settles as today's refusal does.
  - `test_watch_never_waits`: the cached fetch gets `wait=False`.

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/pytest tests/unit/ -k watch -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** Choose `found` and `price` from candidates without `"FleetAPICached"` (today's rule, unchanged). The submitted read first tries `order.read(v, "chargingState", False, ["FleetAPICached"], cutoff=lastRead)`; on None, spends the budget (`watchBudget.spend(price, cls)`) and on refusal settles as today, else runs today's `order.read(..., found)`.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/unit/ -q`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py tests/unit
git commit -m "Let the vehicle watch read cached snapshots first"
```

---

### Task 7: Docs, changelog, live verification

**Files:**
- Modify: `docs/modules/Vehicle_TeslaAPI.md` (a short section in "Owner API and Fleet API", FAQ style)
- Modify: `CHANGELOG.md` (one Features line under `v1.4.1 - Upcoming`, or the next upcoming release if 1.4.1 has shipped)

- [ ] **Step 1: Docs.** For installers: with a Fleet API token, TWCManager reads each car's last reported charge state for free, including while it sleeps, before paying for a live read; Owner API tokens can't. Capabilities, not internals; say "EVSE" not "charger".

- [ ] **Step 2: Changelog.** One Features line, `(@MikeBishop) - ...`, in the style of its neighbours. No Bugfixes line.

- [ ] **Step 3: Commit**

```bash
git add docs/modules/Vehicle_TeslaAPI.md CHANGELOG.md
git commit -m "Document free cached Fleet reads"
```

- [ ] **Step 4: Live verification on `ssh twcmanager`** (deploys pre-approved; record the box's HEAD for rollback first; it currently runs a DIAG build with an uncommitted vehicle-images overlay, so follow the box notes before deploying). Pass when:
  - an asleep car's battery/limit read logs no `Tesla fleet paid request`;
  - a car-initiated stop (Charge Now ended so the limit is restored below the battery level) produces no paid request and no start command, and the log shows the cached read answering within 15 s;
  - with a `StartAt` schedule set while plugged in, the cached `scheduledChargingPending` matches BLE's before and after the start time (if not, fix the rule in Task 2's helper and its test, then re-run).
