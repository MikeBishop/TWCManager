# Month-to-date Fleet Spend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show month-to-date Fleet API spend and approximate Fleet Telemetry signal cost on the Vehicles overview and each car's page, persisted across restarts.

**Architecture:**
- **Counting.** One small `FleetSpend` class owns the counts: per car and per type for paid requests, per car and per field for telemetry signals, plus last month's totals. `TeslaAPI`'s existing paid-request site and `FleetTelemetryMQTT`'s message handler feed it.
- **Persistence.** `TWCMaster` holds it and persists it beside `watchBudget`, and the control tick's housekeeping queues a save at most every 10 minutes while counts change.
- **Rendering.** HTTPControl exposes template helpers, and the two Vehicles templates render them.

**Tech Stack:** Python 3.8, Jinja2 templates, pytest.

**Spec:** `.superpowers/specs/2026-10-28-fleet-spend-design.md`

## Global Constraints

- Python 3.8. The project treats lib growth as a red flag: keep it small and reuse what exists.
- Comments say why the code is what it is; no history, no phase or PR IDs.
- Informational only: nothing here may hold back a command or a read.
- Never put a VIN or URL in a log line. Request types are named as the existing paid log line names them (`command:set_charge_limit`, `wake_up`, `vehicle_data`).
- Telemetry figures are labelled "approx." on the page. There is no allowance or percentage anywhere.
- Black on touched code only. Run the suite with `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G <venv>/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider` and check the exit code.
- Coordination: another session may later add a free `vehicle_data_cached` read. It must stay free here (see Task 2's regex guard).

## Review Focus

1. **A restart across a month boundary.** Loading a blob saved in October on November 1 must make it "last month" and start November at zero. It must not add October's counts to November. Owned by Task 1.
2. **A corrupt or missing `fleetSpend` blob in settings.json.** It starts empty and never raises. Owned by Task 1.
3. **Retained MQTT redeliveries on every reconnect.** They must not count as signals; otherwise each restart inflates the figure. Owned by Task 2.
4. **Concurrent counting:** the cloud worker, the background thread and the MQTT thread all count while the settings saver reads. Losing an increment, or raising during `toJSON`, is wrong. Owned by Task 1 (lock) and Task 2.
5. **An install with no Fleet token and no telemetry.** The pages show no Fleet line and no column, and nothing raises. Owned by Task 3.

---

### Task 1: `FleetSpend` counts, month rollover, pace, persistence

**Files:**
- Create: `lib/TWCManager/Vehicle/FleetSpend.py`
- Test: `tests/unit/test_fleet_spend.py`

**Interfaces:**
- Produces:
  - `TELEMETRY_SIGNAL_USD: float`, the per-signal price.
  - `class FleetSpend(clock=time.time)`, with these methods:
    - `request(vin: Optional[str], kind: str, price: float, now=None) -> None`
    - `signal(vin: str, field: str, now=None) -> None`
    - `month(now=None) -> dict`, returning `{"api": float, "signals": int, "telemetry": float, "pace": Optional[dict], "last": {"api": float, "telemetry": float}}`, where `pace` is `{"api": float, "telemetry": float, "by": "Nov 1"}`, or `None` on the month's first day.
    - `car(vin: str, now=None) -> dict`, returning `{"api": float, "requests": int, "types": [{"kind", "count", "cost", "last"}], "signals": int, "telemetry": float, "fields": [{"field", "count"}], "last": {"api", "telemetry"}}`. Types are sorted by cost, descending; fields by count, descending.
    - `changed() -> bool`, which clears on read: whether anything was counted since the last call.
    - `toJSON() -> dict` and `load(data) -> None`.

- [ ] **Step 1: Look up and pin the telemetry price.** Check Tesla's Fleet API pricing page for streaming signals (the developer docs, "Pricing"). Set `TELEMETRY_SIGNAL_USD` to the published per-signal price, with a comment naming the source and the date checked. If the page can't be reached, stop and report; don't guess.

- [ ] **Step 2: Write the failing tests** in `tests/unit/test_fleet_spend.py`. Use a fake clock set to local times.
  - `test_requests_add_up_per_car_and_type`: two `command:set_charge_limit` at 0.001 and one `wake_up` at 0.02 for VIN A, plus one `vehicle_data` at 0.002 for VIN B. Then:
    - `month()["api"] == pytest.approx(0.024)`;
    - `car(A)["requests"] == 3`;
    - `car(A)["types"][0]["kind"] == "wake_up"`;
    - the `set_charge_limit` entry has `count == 2`;
    - each type's `last` is the clock at its newest request.
  - `test_a_request_with_no_car_counts_only_in_the_total`: `request(None, "vehicle_data", 0.002)` raises `month()["api"]` and appears in no `car()`.
  - `test_signals_count_per_field_and_price_the_total`: 3 `Location` and 1 `ChargeAmps` for A. Then `car(A)["signals"] == 4`, `fields[0] == {"field": "Location", "count": 3}`, and `month()["telemetry"] == pytest.approx(4 * TELEMETRY_SIGNAL_USD)`.
  - `test_a_new_month_moves_totals_to_last_month`: counts on Oct 20, then the clock moves to Nov 2. Then `month()["api"] == 0`, `month()["last"]["api"]` equals October's total, and `car(A)["types"] == []`.
  - `test_a_restart_across_the_month_boundary_rolls_over`: save on Oct 31 23:59, then `load()` into a new instance whose clock reads Nov 1 00:01. The result is the same as the previous test.
  - `test_two_months_on_last_month_is_zero`: after an October save, loading in December gives `last["api"] == 0`.
  - `test_pace_scales_spend_to_the_whole_month`: $0.30 spent by Nov 16 00:00 (15 of 30 days elapsed) gives `pace["api"] == pytest.approx(0.60)` and `pace["by"] == "Dec 1"`. On Nov 1 at 12:00, `pace is None`.
  - `test_a_bad_blob_starts_empty`: `load(None)`, `load({"month": 3})` and `load({"month": "2026-10", "cars": "x"})` each leave `month()["api"] == 0` and never raise.
  - `test_changed_clears_on_read`: false at start; true after `request`; false on the second call.
  - `test_counting_from_threads_loses_nothing`: 8 threads each run 1000 `signal()` calls. Then `car(A)["signals"] == 8000`.

- [ ] **Step 3: Run them and see them fail.**
  Run: `<venv>/bin/python -m pytest tests/unit/test_fleet_spend.py -q -p no:cacheprovider`. Expected: an ImportError.

- [ ] **Step 4: Implement `FleetSpend`** in `lib/TWCManager/Vehicle/FleetSpend.py`, shaped like `WatchBudget`:
  - one leaf `threading.Lock`;
  - an injectable clock;
  - the month key is `time.strftime("%Y-%m", time.localtime(now))`;
  - rollover happens lazily on every call: when the stored key differs from now's, the totals move to `last` only if the stored key is the immediately previous month, and to zero otherwise;
  - `toJSON` stores `{"month", "cars": {vin: {"types": {kind: [count, cost, last]}, "fields": {field: count}}}, "nocar": cost, "last": {"api", "telemetry"}}`;
  - `pace` multiplies spend by `secondsInMonth / secondsElapsed`.

- [ ] **Step 5: Run the tests to see them pass.** Same command; expected: all pass.

- [ ] **Step 6: Commit.**
  ```bash
  git add lib/TWCManager/Vehicle/FleetSpend.py tests/unit/test_fleet_spend.py
  git commit -m "Count month-to-date Fleet requests and telemetry signals"
  ```

### Task 2: Feed it, keep it, save it

**Files:**
- Modify: `lib/TWCManager/TWCMaster.py`. Construct it next to `self.watchBudget` (around line 135), load it next to `self.watchBudget.load` (around line 1244), and save it next to `self.settings["watchBudget"]` (around line 1759) as `self.settings["fleetSpend"]`.
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py`, the paid-request block (around line 346). Where it logs the paid line, also call `self.master.fleetSpend.request(vehicle.vin if vehicle else None, kind, price)`, with the price computed once and used by both the log and the count.
- Modify: `lib/TWCManager/Vehicle/FleetTelemetryMQTT.py`, `mqttMessage`. After the `retained` flag is computed and the prefix checked: for `len(topic) > 3 and topic[2] == "v" and not retained`, call `self.master.fleetSpend.signal(topic[1], topic[3])`.
- Modify: `lib/TWCManager/ControlTick.py`, `housekeeping`. If 600 s have passed since the last spend save and `master.fleetSpend.changed()`, queue `{"cmd": "saveSettings"}`. At shutdown the existing final save covers it.
- Test: `tests/unit/test_paid_logging.py` (extend), `tests/unit/test_fleet_spend.py` (extend).

**Interfaces:**
- Consumes: Task 1's `FleetSpend`.
- Produces: `master.fleetSpend: FleetSpend`.

- [ ] **Step 1: Write the failing tests.**
  - In `test_paid_logging.py`:
    - `test_a_paid_request_is_counted_for_its_car`: one Fleet `command/set_charge_limit` gives `master.fleetSpend.car(VIN)["types"][0] == {"kind": "command:set_charge_limit", "count": 1, "cost": pytest.approx(0.001), "last": ANY}`.
    - `test_an_owner_api_request_is_not_counted`: the same command on the Owner slot gives `month()["api"] == 0`.
    - `test_the_cached_read_stays_free`: `_PAID_PATH.search("/api/1/vehicles/X/vehicle_data_cached") is None`.
  - In `test_fleet_spend.py`:
    - `test_telemetry_counts_live_signals_only`: through `FleetTelemetryMQTT.mqttMessage` with a fake message, one live `telemetry/<VIN>/v/Location` counts 1, and the same message with `retain=True` doesn't count.
    - `test_spend_survives_a_settings_round_trip`: `saveSettings` then `loadSettings` on a master keeps `car(VIN)["requests"]`.
    - `test_housekeeping_saves_at_most_every_ten_minutes`: with counts changing on every tick, 3 ticks inside 600 s queue one save; a tick after 600 s queues another; with no changes, nothing is queued.

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Make the four changes listed under Files.**

- [ ] **Step 4: Run the new tests, then the full suite.** Expected: everything passes, and the parity paid counts are unchanged.

- [ ] **Step 5: Commit.**
  ```bash
  git commit -am "Count Fleet requests and telemetry signals as they happen, and keep them"
  ```

### Task 3: Show it on the Vehicles pages

**Files:**
- Modify: `lib/TWCManager/Control/HTTPControl.py`. Add `spendLines(master) -> list` and `carSpend(master, vin) -> Optional[dict]`, both registered as template globals next to `watchLine`.
  - `spendLines(master)` returns the overview's text lines.
  - `carSpend(master, vin)` returns `car()` plus formatted strings, or `None` when neither Fleet API nor telemetry applies.
  - "Fleet applies" means `TeslaAPI` is loaded and `fleetSlot.accessToken` is non-empty.
  - "Telemetry applies" means `getModuleByName("FleetTelemetryMQTT")` is not None.
- Modify: `lib/TWCManager/Control/themes/Default/vehicles.html.j2`. Add the lines above the table, and a "Fleet this month" column shown only when Fleet or telemetry applies.
- Modify: `lib/TWCManager/Control/themes/Default/vehicleDetail.html.j2`. Add a "Fleet spend" section after "Pending commands": the totals line, the types table (Request, Count, Cost, Last, with Last formatted via `ageText`), and, where telemetry applies and the car has signals, the fields table (Field, Signals).
- Test: `tests/unit/test_vehicles_page.py` (extend).

**Interfaces:**
- Consumes: `master.fleetSpend` (Task 2) and `FleetSpend.month/car` (Task 1).

The exact copy, from the spec:
- `Fleet API this month: $0.31 · on pace for $0.48 by Nov 1`, with the pace clause dropped when `pace` is None;
- `Fleet Telemetry this month: approx. 41,800 signals, $0.28 · on pace for $0.43`;
- `Last month: $X` appended to each line when last month's figure is non-zero;
- per-car column: `$0.28` or `$0.28 + approx. $0.25 telemetry`;
- the car page heading line: `Fleet API this month: $0.28 in 31 requests`.

Use two decimals for dollars. Use three for a type's cost under $0.01. Show signal counts with thousands separators.

- [ ] **Step 1: Write the failing tests** in `test_vehicles_page.py`, using the existing `master()` and `render()` helpers:
  - `test_no_fleet_no_spend_shown`: with no TeslaAPI module and no telemetry, "Fleet API this month" isn't in the overview and there's no "Fleet this month" header.
  - `test_fleet_spend_line_and_column`: with a Fleet token and $0.31 counted, the overview contains `Fleet API this month: $0.31`, and the car's cell shows its own figure.
  - `test_zero_spend_still_shows_with_a_fleet_token`: shows `$0.00`.
  - `test_telemetry_line_is_approximate`: with the telemetry module present and 41800 signals, the page contains `approx. 41,800 signals`.
  - `test_last_month_shows_only_when_nonzero`.
  - `test_vehicle_page_lists_types_and_fields`: the detail page has rows for `wake_up` and `Location`, with counts.

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Implement the helpers and the template changes.**

- [ ] **Step 4: Run the tests and the full suite.**

- [ ] **Step 5: Commit.**
  ```bash
  git commit -am "Show month-to-date Fleet spend on the Vehicles pages"
  ```

### Task 4: Docs and changelog

**Files:**
- Modify: `docs/modules/Vehicle_TeslaAPI.md` (the Fleet API section).
- Modify: `docs/modules/Vehicle_FleetTelemetryMQTT.md`.
- Modify: `CHANGELOG.md`, adding one Features line under the upcoming release.

- [ ] **Step 1: Write the docs.**
  - **Where it shows:** the month's spend appears on the Vehicles page and each car's page.
  - **TeslaAPI doc:** TWCManager counts only its own Fleet API requests. Another app on the same Tesla account doesn't appear, so the bill can be higher.
  - **Fleet Telemetry doc:**
    - The figure counts the signals TWCManager received. Tesla bills the signals the car sent. Signals sent while TWCManager was down, or fields it doesn't subscribe to, aren't counted. That's why it's labelled approx.
    - The per-field counts show which field to give a coarser `minimum_delta` if the cost is higher than you'd like.
  - **Docs rules:** written for installers, present tense, "EVSE" or "charging station" (never "charger" for the wall unit), no internals.
- [ ] **Step 2: Add the CHANGELOG line**, for example: "The Vehicles page shows this month's Fleet API spend and approximate Fleet Telemetry cost, in total and per car, with a breakdown on each car's page."
- [ ] **Step 3: Commit.**
  ```bash
  git commit -am "Document the Fleet spend figures"
  ```
