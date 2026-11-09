### Task 3: Commanded-rate belief

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py:200-209` (`chargingAmps`, new `believedAmps`)
- Test: `tests/unit/test_watch_load_step.py` (belief), `tests/unit/test_charging_points.py` or `tests/unit/test_distributor_loop.py` (allocation pin; use whichever already builds two cloud cars on one circuit)

**Interfaces:**
- Consumes: `Vehicle.lastWrite(field) -> Optional[Observation]` (stamped by `Reconcile/Run.py:255` via `noteWrite` for DONE, and for SATISFIED on limit/amps), `Vehicle.latest(field)`.
- Produces:
  - `Watch.believedAmps(self, v) -> float`: if `lastWrite("chargingState")` or `lastWrite("chargeCurrentRequest")` is newer than `latest("actualCurrent")`, then `max(reading, commanded)` where a written `"Stopped"` commands nothing new and a written `"Charging"` makes the car count at `lastWrite("chargeCurrentRequest")` (else its `chargeCurrentRequestMax`); otherwise the reading, counted only while `situation == HOME_CHARGING` as today.
  - `Watch.chargingAmps(self, ledgered: bool = True) -> float`: sums `believedAmps`; `ledgered=False` leaves out Fleet-only cars (Task 6 uses it).

No change to `_drawAmps`/`_drawing`/`taken` (TWCMaster ~73-89, ~745): allocation already takes `max(given, draw)` and a cloud car's draw stays its last reading until a newer one. That is the spec's "never allocate on the assumption"; Step 1 pins it.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_accepted_start_counts_at_the_commanded_amps_until_a_reading(): ...   # chargingAmps == 32 after noteWrite("chargingState","Charging") + noteWrite("chargeCurrentRequest",32), car reading "Stopped"
def test_a_lowered_rate_keeps_the_old_draw_until_a_newer_reading(): ...          # reading 48 A, write 16 -> 48; new reading 16 -> 16
def test_a_raised_rate_counts_at_once(): ...                                       # reading 16, write 32 -> 32
def test_a_second_car_gets_its_full_share_only_once_the_first_reads_lower(): ... # allocation pin: two Fleet cars, one 48 A circuit
```

- [ ] **Step 2: Run, expect the first three FAIL; the allocation pin should already PASS** (if it fails, stop and report: the spec's assumption about `taken` is wrong)

- [ ] **Step 3: Implement `believedAmps` and switch `chargingAmps` to it**

- [ ] **Step 4: Run, expect PASS**, plus `tests/unit/test_watch*.py tests/unit/test_twcmaster.py -q`

- [ ] **Step 5: Commit** `feat: count a car at its commanded rate until a reading confirms it`

---

