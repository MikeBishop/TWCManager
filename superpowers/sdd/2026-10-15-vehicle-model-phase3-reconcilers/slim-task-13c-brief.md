### Task 13c: One TeslaAPI request helper (expected lib Δ ≈ −120)

Audit item 9.

**Files:**
- Modify: `Vehicle/TeslaAPI.py`. `CarApiVehicle.get_car_api`, `_paidPost` + `commandRefused`, `loadVehicleList` + `slotRequestFailed`, and `_energyGet` + `_energyRefused` + `_refuseWallConnectors` all go through one helper.
- Test: `test_teslaapi_request_errors.py` is extended. Existing status tests pass; the classifier keeps the per-path differences they pin (pre-flight M6):
  - the vehicle list does not retry after a 401 and starts no API backoff;
  - the energy path's 403 refuses purpose `"energy"` (Wall Connector reads only; Gen3 cloud VIN depends on it);
  - a command after a 401 retries once after a refresh, as today (no new paid call).
- `loadVehicleList` keeps Task 11's `heldLimits.resolveLegacyIds` call and Task 11's `updateChargeAtHome` loader.

**Interfaces:**
- `TeslaAPI._request(self, slot, method, path, purpose, body=None, timeout=10) -> Tuple[Optional[requests.Response], Optional[Outcome]]`. It builds the headers and makes one request.
- One status classifier, `_classify(slot, status, purpose, body) -> Optional[Outcome]`:
  - 401 refreshes once and retries once, else retires the slot;
  - 403 refuses `purpose`;
  - 410 pauses the slot;
  - 412 pauses it with `latch=True`;
  - 429 sets the backoff;
  - 408 is `UNREACHABLE`.
- Callers keep their own success parsing.

- [ ] **Step 1: Tests.** A table-driven `test_every_path_classifies_status_codes(path, status, expected)` over the 4 paths × 6 statuses, with the per-path expectations above, counting requests per URL.
- [ ] **Step 2–4:** FAIL → implement → full suite PASS.
- [ ] **Step 5: Commit.** `git commit -m "One TeslaAPI request helper and status classifier for reads, commands, the vehicle list and energy sites"`

