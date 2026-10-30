### Task 1: Log what the next analysis needs (expected lib Δ ≈ +18)

This is the first change after Task 0, so the box can collect evidence while the rest lands. Logging only: no decision reads anything added here. Task 3's arrival trigger has its own hook (`Presence.noteObservation`) and never uses this one (F14).

**Changes:**
- `Reconciler.report` (:528–537): log every attempt's outcome at INFO (today DEBUG for aspects): aspect, capability, key, provider, `outcome.kind`, `outcome.detail`. The format is unchanged.
- `TeslaAPI._request` (:306): a request is paid by **provider and endpoint**, never by `purpose` (F14). Paid means the **Fleet** slot (`slot is self.fleetSlot`) and a path ending in `/vehicle_data`, `/wake_up` or `/command/<name>`. The Owner API, `vehicles/{vin}` and the vehicle list are free. After each paid request, one INFO line: `"Tesla %s paid request: %s ($%.3f)"` with the slot's token type, the endpoint type (`vehicle_data`, `wake_up` or `command:<name>`) and the price.
  - It never logs the URL, the VIN or a token.
  - A module-level `_PAID = {"vehicle_data": 0.002, "wake_up": 0.02, "command": 0.001}`.
  - The line is logged after the request whatever its status: an answered 408 is still a request.
- Telemetry: `TeslaMateVehicle` and `FleetTelemetryMQTT` log at INFO when `pluggedIn`, `state` or (TeslaMate) the `geofence` topic changes value for a car: `"%s: %s %s -> %s"`. `geofence` is logged only and is not a registry field. `pluggedIn`/`state` are logged in the shared observe path in `Telemetry.py`, behind a 2-name set; `geofence` is logged in `TeslaMateVehicle`.

**Files:**
- Modify: `Vehicle/Reconcile/Reconciler.py`, `Vehicle/TeslaAPI.py`, `Vehicle/Telemetry.py` (and `TeslaMateVehicle.py` for the geofence topic).
- Test: `tests/unit/test_paid_logging.py` (new).

- [ ] **Step 1: Write the failing tests.**

```python
def test_every_paid_request_logs_one_info_line_without_url_or_token(requests_mock, caplog):
    # Fleet vehicle_data, wake_up and a set_charge_limit command: 3 INFO lines naming
    # "vehicle_data", "wake_up", "command:set_charge_limit"; none contains the VIN, "https://" or the token
def test_free_requests_log_nothing(requests_mock, caplog):       # vehicles list, vehicles/{vin}, and Owner API vehicle_data/wake_up/commands
def test_every_attempt_outcome_is_logged_at_info(caplog):        # reconciler pass with a scripted provider
def test_telemetry_plug_state_and_geofence_changes_log_at_info(caplog):   # repeated same value: one line
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; parity unchanged.
- [ ] **Step 5: Full suite** → PASS. **Commit.** `git commit -m "Log reconciler outcomes, paid Tesla requests and telemetry plug changes at INFO"`


---

