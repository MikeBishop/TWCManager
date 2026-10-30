### Task 5: One attribution for VIN-less plugs; the fan-out over candidates (expected lib Δ ≈ +50)

**Ported verbatim** from `presence/3-plug-presence:lib/TWCManager/PresenceAttribution.py` (71 lines with comments) into `Presence.py`: `pickPluggedCar`, `Candidate` (with `fastChargerPresent`) and `PILOT_MATCH_TOLERANCE`.

**`Presence.attribute(master, pointId, offeredAmps, actualAmps, read=True) -> Optional[str]`:**
1. **BASE's single-car guess, decisive (F12):** if exactly one non-anonymous car without a valid `twcVin`, not NOT_HOME, has a plugged reading within `PLUGGED_JUST_NOW = 120` s (any source), it wins. That is BASE's `_correlate`, with the away test now `presence != NOT_HOME`.
2. Otherwise `pool = candidates(master)` (Task 2's one definition).
3. When `read`, for each `TeslaBLE`-claimed pool car: `v.read("availableCurrent", READ_MAX_AGE, providers=[local providers only])`. Never a wake, never TeslaAPI.
4. Build each `Candidate` from the registry:
   - `reach`, `inside`;
   - `pluggedIn`: False when NOT_HOME, else the `TeslaBLE` value ≤ 300 s old, else None;
   - `pilot`/`actual`/`fastCharger*`: `TeslaBLE` values ≤ 300 s old.
5. `pickPluggedCar`. A winner (from step 1 or step 5) → `registry.observeTwcVin(pointId, vin)` → `Targets.onArrival(master, winner)` (the one arrival for this plug-in). Ambiguity logs at INFO once per plug session.

**Callers:**
- Gen2: `_plugSession(slave, True)` queues `{"cmd": "attributePlug", …}`, deduped per point.
- Gen3: `_correlate`'s guess (:275–297) → `attribute(...)`. The cloud-VIN half is unchanged.
- Fan-out (h): `anonymousCars = [v for v in candidates(master, SET_AMPS) if pluggedHere(master, v)]`.
- The 00 session open (:1346) uses `pluggedHere` over `candidates`.
- `TWCSlave.pluggedCars` goes.

**Files:**
- Modify: `Vehicle/Presence.py`; `TWCMaster.py` (`_plugSession`, `_taskKey`, :1346); `TWCManager.py` (handler); `EVSEInstance/Gen3TWC.py:68, 239–297`; `EVSEInstance/ChargingPoint.py:182–190`; `TWCSlave.py:7–16, 121–141`.
- Tests:
  - `test_presence_attribution.py` (10 ported, only the import changes);
  - `test_presence.py`;
  - `test_amps_reconciler.py:8,157–187`;
  - the Gen3 `_correlate` tests: `test_charging_points.py` (2), `test_gen3twc_provider.py`, `test_vehicle_endpoint.py` (F17);
  - parity.

**Interfaces:**
- Produces: `Presence.Candidate`, `pickPluggedCar(...)`, `PILOT_MATCH_TOLERANCE = 1`, `PLUGGED_JUST_NOW = 120.0`, `attribute(...) -> Optional[str]`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_attribution_reads_only_local_providers(requests_mock):
def test_gen3_single_car_plugged_within_120_s_is_still_guessed_without_home_or_ble():   # F12
def test_a_single_candidate_inside_is_attributed_merges_the_session_and_arrives_once():
def test_two_candidates_attributed_by_ble_pilot():
def test_gen3_cloud_vin_still_corrects_a_guess():
def test_vin_less_single_candidate_plug_one_apply(requests_mock)             # scenario 3
def test_vin_less_two_candidates_ble_pilot_one_apply(requests_mock)          # scenario 4
def test_vinless_ambiguous_plug_rates_nobody_and_logs_once(requests_mock, caplog)   # scenario 5
def test_vinless_rate_never_falls_back_to_vehicles_0(requests_mock)          # (h)
def test_supercharger_telemetry_plugged_is_not_home(requests_mock)           # scenario 6
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS (row 25 unchanged).
- [ ] **Step 5: Grep** `pluggedCars|CORRELATE_WINDOW|_PLUGGED` → hits only in `Presence.py`. **Step 6: Full suite** → PASS. **Commit.** `git commit -m "Attribute a VIN-less plug with one picker for Gen2 and Gen3; fan out only to cars plugged in here"`

**Test mapping (Task 5):**
- `test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0`: INTENTIONALLY CHANGED (h).
- The Gen3 `_correlate` tests: rewritten through `attribute` (PLUMBING-ONLY; F12 keeps their outcomes).

---


---
## Controller addendum (user approved the audit plan, 2026-10-19): build at ≤ −17 net lib
Read "## 4. Building Tasks 4–6 at ≤ 0 net → Task 5" in audit-report.md (same directory) and follow it where it differs from the text above:
- do NOT port PresenceAttribution.py verbatim: pilot matching is a filter over `Presence.candidates(master)` (~25 lines) — keep cars whose TeslaBLE availableCurrent/actualCurrent are within 1 A of the point's offer and actual; the single-car guess stays decisive (F12). Rewrite test_presence_attribution.py's 10 tests against the filter (same scenarios, same expected winners).
- delete TWCSlave.pluggedCars (+ its imports), ChargingPoint.anonymousCars, Gen3TWC._correlate's candidate loop and CORRELATE_WINDOW, and the pluggedCars()[0] probe in TWCMaster — verify each by grep first; Gen3 behaviour must be preserved (Gen3 is essential; its single-car-within-120 s guess is kept per F11 — express it through the same filter if possible).
- no Candidate NamedTuple; use the existing Presence helpers (pluggedNow, inside, markAt("contact")).
- Task 4's unplug fallback (`_plugSession(slave, False)`'s single-candidates() car) should use the same filtered winner.

## Carried from Task 4's review (must do)
- **Returning car on an unnamed Gen2:** after a filtered unplug the car returns; BLE contact makes it HOME; the TWC reports 03 (asleep, max 6 A) with no VIN read yet → today a car-addressed start says "not here (not plugged in)". When attribution picks a single winner for an unnamed Gen2 00→03 (or Gen3 plug-in), record plug-in evidence for that car (a plugIn mark / pluggedIn reading from the point's source) so pluggedNow sees it. Test: unplug, return, 03 asleep, no VIN → car-addressed start SENDs over BLE, paid (0,0,0).
- **Single-candidate unplug fallback** must exclude cars whose twcVin names a *different* point (a car another TWC names at 00 must not be departed by this TWC's unplug). Test with two Gen2 slaves.
- **Anonymous fan-out and the nothing-offered rule:** cars reached through an unnamed point's fan-out are keyed by the TWC's key, so the no-wake-at-0-A rule doesn't see their offer. If attribution now resolves the car, key the offer/wake check by the winner; otherwise note what remains.
