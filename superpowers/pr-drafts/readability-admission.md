Readability: name admission's parts for what they hold

This is a readability pass over admission and distribution in `TWCMaster.py` and over `ChargingPoint.setTargetPower`. It changes no behaviour. Each name now means one thing, and the caller and `_admit` use the same names for the four values it returns:

- `_admit` result `pool, given, left, budgets` -> `seated, held, shared, budgets` on both sides (`given` is now a copy of `held` in the caller)
- `self._held` (per-car steady reading) -> `self._steady`, unpacked into `wasRoom, wasState, wasDraw, roomSince, steadySince` instead of read as `last[0]`..`last[4]`
- `hold` (a delay) -> `delaySecs`; `held` (a bool) -> `settled`; `held` now only names points held at their minimum
- `room` (list in `_admit`) -> `standby`; the `(a if c else b).append(p)` and `held.update(... if cut else {})` tricks -> a plain `if cut:` block and a `hold()` helper
- `_draws` -> `_budgetsOf`; loop variable `c` -> `budget`
- `self._willing` gets its own assignment, not one inside a tuple
- `ChargingPoint`: `twc, car` -> `twcCarries, carCarries`; `mine` -> `heartbeatKeys`; `own` -> `rateHeartbeatCars`
- The `_admit` and `_followAdmission` header comments are rewritten as plain sentences. `_admit`'s comment had said drawing points sort first; it now describes the order the code uses: points that want power first, and among those the ones already drawing, so a charging car keeps its seat.

Evidence: full unit suite (`pytest tests --ignore=tests/API --ignore=tests/integration`): 2618 passed, 1 xfailed. The only test changes follow the renames.

Changelog: none (no behaviour change)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
