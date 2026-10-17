# Final fix

Commit 6c4ba54, on top of e7973a3 in wt-vm35. Not pushed.

## Result

- **Full suite** (`tests --ignore=tests/API --ignore=tests/integration`): 1783 passed, 1 xfailed. The baseline was 1782; the one added test is listed below.
- **tests/integration:** 212 collected.
- **Black:** all changed lib files are clean.
- **Lib count:** 27,123 → **27,098 (−25)**.

## Per item

| # | Item | Δ lib | Notes |
|---|---|---|---|
| 1 | TeslaBLE `sendCommand` dead `hasattr(vin, "VIN")` branch deleted | −3 | Done test-first. The guard regex in `test_no_caller_outside_teslaapi_reaches_for_its_list` gains `\.VIN\b([^ ]|$)`. That pattern ends `.VIN` at a word boundary that is not followed by a space, so it skips `from .VIN import`, `Registry.VIN import` and `.VINData`. The test failed on `TeslaBLE.py` before the deletion and passes after. Only that file matched; there are no other hits. |
| 2 | TeslaAPI `Vehicle` import dropped; uses `vehicle.SYNC_TIMEOUT` | −1 | Same class constant, read through the instance. |
| 3 | Shadowed `enabled = True` class attribute removed | −1 | The `def enabled` method already replaced it in the class body. |
| 4 | Listed-car-by-VIN helper | **0, not taken** | I implemented it and measured it: the helper is +5 lines and the two call sites each save 1, so +3 net after black. The review's −2 estimate does not hold. I reverted it under the must-shrink rule. Exact-case matching is unchanged. |
| 5 | `atHome` helper for the 3 `is_location_home` sites | **0, not taken** | Measured at +2 net: the helper is +6 lines, and `update_vehicle_data` still needs `lat`/`lon` locals for `is_far_from_home`. Reverted for the same reason. |
| 6 | `update_vehicle_data`'s three try/except blocks folded into one | −15 | A `missing` variable is set before each step. Messages, ERROR level, `return False` and the lat-before-lon observe order are all unchanged. The new test `test_teslaapi_registry::test_an_incomplete_vehicle_data_answer_logs_what_is_missing` pins all three messages, the level, the return value, and that `lat` is observed before a missing `lon`. It passes against both the old and the new code. |
| 7 | HeldLimits `_vins(store)` shared by the load and the migration | −2 | |
| 8 | Dead `__email`, `__password`, `__resp` removed | −3 | Grepped the whole repo first, including html and docs: no other reference. `_TeslaAPI__login*` is used by tests and was kept. |

Not touched, as instructed:
- the case-insensitive matching in `FleetAPIProvider._listed`;
- `expire` skipping attached cars (accepted by ruling);
- m3.
