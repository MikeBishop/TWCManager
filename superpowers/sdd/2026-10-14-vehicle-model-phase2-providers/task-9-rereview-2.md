# Task 9 re-review 2: fix round 3 (006818f..acd223f), scoped to N1 and m-1

**Verdict: PASS.** N1 and m-1 are fixed as ruled under option (b). The fix adds no new Critical or Important issue and no new paid call. One new Minor is noted below; it needs no action in Phase 2.

## Method

- **Harness.** I re-ran `scratchpad/probe-t9/harness2.py` against a fresh detached eee9425 worktree (removed afterwards) and against acd223f. The outputs are `old.3.json`, `new.3.json` and `diff3.txt`. The eee9425 output is byte-identical to the earlier run.
- **Real-HA probe.** The harness HA is a spy, so it only shows routing. I added `probe-t9/haprobe.py`, which drives HomeAssistant's real `car_api_charge` and `applyChargeLimit` over two stand-in HA cars and records `_call_service`. It reuses the round-3 `_haCars` fixture.
- **Focused tests:** 184 passed across:
  - `test_vehicle_priority`, `test_provider_order`, `test_homeassistant_registry`, `test_vehicle_command_queue`, `test_teslaapi_providers`: 105 passed;
  - `test_registry_callers`, `test_own_write_stamps`, `test_provider_registration`, `test_registry_membership`: 79 passed.

## Findings

| ID | Verdict | Evidence |
|---|---|---|
| N1 | **Fixed** | `HA{haCars 2}`, targeted start/stop/limit under prefer_ble and api_only: round 2 sent nothing (`-`); acd223f sends `HomeAssistant:1`, which matches eee9425's call counts. In the real-HA probe, a targeted stop on an HA-only install switches only the target's entity. |
| I1 (holds) | **Fixed** | `Fleet+HA{haCars 2}`, Fleet failing: the façade calls Fleet 2x, then HA once. In the probe, HA turns off only `switch.<target>` and the limit sets only `number.<target>`, so other cars are untouched. A broadcast still switches both cars. |
| m-1 | **Fixed** | The stale comment is gone, and `f.calls[1:] == [("setAmps", VIN, 3)]` now pins M1. |

## Checks requested

1. **No new differences besides N1's change.** Comparing 006818f with acd223f, only HA cells changed, and all of them are targeted `start(vin)`, `stop(vin)` and `limit80(vin)`:
   - **`HA{haCars 2}`:** these cells now match eee9425.
   - **`Fleet+HA{haCars 2}` (list loaded or not):** HA is reached last, once, after Fleet fails. This is the "HA joins targeted walks last" ruling, the same class as D5. Fleet's own counts are unchanged.

   No Fleet, BLE, Owner or ble_only cell moved.
2. **Fleet+HA with two cars no longer stops every car.** Confirmed with the real HA methods (above).
3. **No new paid calls.** Every TeslaAPI count is identical to round 2 and to eee9425. The only added calls are HA's, at 1 attempt, already accepted under D5.
4. **The HA VIN lookup cannot act on the wrong car.** Results from the real-HA probe:

   | Input | Result | Notes |
   |---|---|---|
   | Lower-case VIN | `success`, target only | Both methods |
   | Mixed-case VIN | `success`, target only | Both methods |
   | The other car's VIN | `success`, only that car | Both methods |
   | Unknown VIN | `"error"`, no service call | Both methods |
   | VIN in the registry but not attached to HA (a TWC-reported car) | `"error"`, no service call | |
   | VIN with a leading space | `"error"`, no call | Fails safe. The façade's `_vinOf` never pads, so this cannot occur through the façade. |
   | `vin` is `None` or `""`, or the task is a bare bool | Broadcast to every car | Unchanged |

   The lookup goes through `registry.get`, which normalises the key, and through the car's own HA attachment. So the only car it can return is the HA car attached to that VIN.
5. **Rate-limit stamp.**
   - Refusals do not stamp `carApiLastStartOrStopChargeTime`: an unknown VIN, an unattached VIN, and an unavailable HA all leave it at 0. The round-3 test also covers this.
   - A targeted call that passes the check stamps the time even when the car is away, which is the same as before.
   - See m-2 for one consequence of the shared stamp.

## New issues

### Minor

**m-2** (`HomeAssistant.car_api_charge`, the 10 s stamp is module-wide):
- **Behaviour now:** a targeted stop for car A, then a targeted stop for car B within 10 s, returns `"error"` for B, and nothing is sent to B (probe: `A success then B error`). At eee9425, A's stop acted on every HA car, so B was stopped as well.
- **Why it is not a lost command:** `TWCSlave` re-issues `stopCarsCharging(currentVIN)` every loop while the car still draws current (`TWCSlave.py:574`), and the queue keys `charge` per VIN. B is therefore stopped on a later tick, after a delay of 10 s or more.
- **Action:** none required in Phase 2. Phase 3's per-provider HA commands could keep the stamp per car.
