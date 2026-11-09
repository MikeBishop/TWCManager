# Task 3 report: /api/getChargingPoints

Commit: f18c8065 "Live pages: /api/getChargingPoints lists every charging point"

## Implemented
- `Views.slaveTotals(master)`: the `getSlaveTWCs` total loop and car-side desired-amps addition moved here unchanged (same keys, same rounding).
- `getSlaveTWCs` now sets `data["total"] = Views.slaveTotals(master)`. Its per-slave loop is untouched. The `AMPS` import in HTTPControl was left unused, so I removed it.
- `Views.chargingPointsView(master)`: returns `{fingerprint: fingerprint("home"), now, points, total}` with the keys in the brief. Members are picked by `isinstance(e, Gen2TWC/Gen3TWC)`, and Views imports those modules directly (R7). The values come from cached state only. Gen3 reads `vitals`/`currentAmps`/`lastTarget`. Car values come from `registry.get(point.key)` and `value()`. The numbers in the brief are coerced to float. `appearance` is `{}` when there is no car and `anonymous` is False.
- Route `GET /api/getChargingPoints` -> `self.sendJSON(Views.chargingPointsView(master))`.

## Tests (tests/unit/test_live_views.py)
- Fixtures are built on `test_charging_points.real()`/`car()` and `test_gen3twc_provider.vitals()`:
  - `gen2_master`: Gen2 8244 with VIN, plus car VIN2 on no TWC with desired AMPS 16.
  - `mixed_master`: the same plus a reachable Gen3 with no car.
  - `idle_master`: a heard-from idle Gen2 plus a Gen3 whose vitals are `{}`, still reachable.
- The 5 tests from the brief, with a few extra asserts: total of 32.33 = 16.333 + 16, Gen2 ampsOffered/ampsDrawn, view total equals slaveTotals, and the idle master has 2 points.
- RED: `pytest tests/unit/test_live_views.py -k "points or slave_totals"` failed with `ImportError: cannot import name 'chargingPointsView'`. This was expected.
- GREEN: `pytest tests/unit/test_live_views.py tests/unit/test_charging_points.py` gave 37 passed.
- Full unit suite: `pytest tests/unit -n 8` gave 2666 passed.
- A full `pytest` run also gave 208 errors, all in tests/integration. Those tests need a live server (`api_get` fixture), so the errors come from the environment and not from this change.
- Byte-identity check for /api/getSlaveTWCs: I took a fixture with Gen2, Gen3 and a car-only point, froze time.time, and captured the output at the pre-change code (git stash) and after the change. `cmp` reported the two outputs IDENTICAL.

## Concerns
- `chargingPointsView` calls `master.chargingPoints()` twice, once for points and once inside slaveTotals. This is cheap, and that function has no side effects apart from Gen3's existing stale-cache background queue.
- black and pyflakes are not installed in the venv, so I did not run them.
