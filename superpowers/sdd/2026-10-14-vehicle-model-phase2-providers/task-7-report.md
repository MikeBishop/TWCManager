# Task 7 report: Wall Connector VIN from the energy site

**Status:** DONE_WITH_CONCERNS

**Commits** (branch vehicle-model/phase2, worktree wt-vm2):
- `1f197e3` Identify the car on a Gen3 TWC from the energy site's free live_status before falling back to a single candidate
- `9ba3504` Harden the Wall Connector VIN reader and skip the version fetch when a DIN is configured

**Tests:** The full suite (`tests --ignore=tests/API --ignore=tests/integration`) gives 1255 passed, 1 xfailed. That is 1228 + 27 new tests in `tests/unit/test_wall_connector_vins.py`. The brief's Step 4 set (wall_connector_vins, gen3twc_provider, teslaapi_providers, teslapowerwall2_ems) also passes.

## Fail-before

```
ImportError while importing test module '.../tests/unit/test_wall_connector_vins.py'.
E   ModuleNotFoundError: No module named 'TWCManager.Vehicle.Providers.WallConnectorVins'
```

I also showed the N1 test failing on its own, with the new guard disabled (`if True:`):
```
E   AssertionError: assert (<...Vehicle object at 0x...> is None)
E    +  where <...Vehicle...> = get(('anon:' + 'Gen3TWC-10.0.0.1'))
```

## What was built

- **`lib/TWCManager/Vehicle/Providers/WallConnectorVins.py`** (new): `WallConnectorVinReader`.
  - It provides `POLL_SECONDS = 60.0`, `noteConnect`, `due`, `query`, `match` and `apply`. `self.clock` is the only clock it reads.
  - Rate limiting: each provider has a list of call stamps pruned to its declared `RateLimit`. Every attempt counts, including one that is refused.
  - The edge flag clears and `lastQuery` is stamped whenever a query is attempted.
  - `apply()` catches any exception and logs it at DEBUG with `exc_info`, so the reader can never break the vitals loop.
  - When no provider is ready, one INFO line explains that an energy-scope token is needed.
- **`TeslaAPI`**:
  - Adds `ENERGY_SITES_TTL = 3600`, `energySites(slot=None)`, `wallConnectorVins(slot)` and `wallConnectorVinsReady(slot)`.
  - State is kept per slot kind: `_energySites` (the cache, keyed by `slot.changes`), `_energySitesEmpty`, `_wallConnectorSitesDropped` and `_wallConnectorsRefused`.
  - Requests go through `requests.get` with a 10 s timeout. URLs are built as `vehicleListURL` builds them.
  - A 401/403 calls `reportScopeRefused("energy", refused=True)`, latches against `slot.changes` and logs the brief's INFO line once. It does not call `slotRequestFailed`, so vehicle reads are never paused.
  - `refreshTokenIfNeeded()` runs first, as it does for Storm Watch.
- **`TeslaAPIProviders`**:
  - Both providers declare `READ_WALL_CONNECTOR_VINS → Declaration(CLOUD_FREE, RateLimit(2, 60))` and have `wallConnectorVins()`.
  - `ready(None, READ_WALL_CONNECTOR_VINS)` is relaxed (carry 1). Owner returns `wallConnectorVinsReady(ownerSlot)`. Fleet returns its own readiness only when the Owner slot is not ready.
  - Every other capability still returns False for a None vehicle (tested).
  - `FleetAPIProvider.available()` sends this capability to the energy gate, not to `usable("read")`.
- **`Gen3TWC`**:
  - Adds `_version`, the `din` property (config key, then `<part>--<serial>`, then None) and `refreshVersion()` (urllib, background thread).
  - `cloudVin` is cleared on the falling edge.
  - **N1 fix (carry 2):** on a rising edge, `beginPlugSession`/`_correlate` run only when `vehicleAt(pointId)` is None or anonymous. A retried edge whose first attempt already named the car (and then raised) no longer creates an orphan `anon:` vehicle.
- **`Gen3TWCs`**:
  - Adds `self.vinReader`.
  - `noteVitals` runs `republish()` first. It then calls `refreshVersion()` while `_version is None`, unless a `din` is configured. It calls `noteConnect()` on a rising edge, then `apply(devices())`. All of this is on the background thread with no lock held.
- **Late VIN (carry 4):** `apply` runs every poll while a session is anonymous. It sets `cloudVin` and calls `_correlate()`, which feeds `observeTwcVin`. Tests cover an edge answer with no `vin` followed by a later one: an unknown car is pending, then confirmed on the next poll, and a known car attaches at once.
- **Docs (carry 3):** `docs/modules/Controller_Gen3TWCs.md` now:
  - documents the `din` device key;
  - replaces the "later release" line with the cloud lookup: free, never touches the car, needs the Gen3 in the Tesla app, needs a token with `energy_device_data` (Owner tried first), and takes an optional `din` override;
  - marks the lookup untested on hardware.
- `TeslaTokenSlot.SCOPE_LABELS["energy"]` now says "Powerwall Storm Watch and Gen3 Wall Connector VINs".

## Cost check

`onlyFreeCalls` asserts that every recorded request is a GET to `/api/1/products` or `/energy_sites/<id>/live_status`. It is used in the rate-limit, late-VIN and Owner-to-Fleet tests. The brief's `wake_up|vehicle_data` assertion is also kept. The code adds no vehicle endpoint.

## Deviations from the brief (decisions)

- `_energySitesEmpty[kind]` stores the time the sites were found empty and re-arms after `ENERGY_SITES_TTL`. The brief has it as a bare `True`, which would disable the feature until restart. It is set only after a successful answer, or when every site has been dropped for having no `wall_connectors`. A failed fetch is never cached as empty.
- `match()` returns `{unit: vin}`, because the brief's own `apply` line iterates `unit, vin`. The brief's `Dict[str, str]` cannot be right.
- The "no DIN match" INFO is also logged for a known DIN that matches nothing, once per unit per session. The DIN format is a guess, and this log line is the user's only sign that they should set `din`.
- A 401/403 on `/products` latches the same refusal as a 401/403 on live_status.
- With several sites, `wallConnectorVins` returns the merged map if any site answered. It returns None only if none answered.
- The Owner-to-Fleet fallback happens on the next poll, not within the same query, because candidates are computed before the call. This follows the brief's `query` contract.

## Concerns

1. **Correlation order.**
   - What happens: at the edge, `_plugEdges` runs the single-candidate rule before the cloud is asked. Once `vehicleKey` is a VIN the reader stops, as the brief specifies, so the cloud never corrects a wrong single-candidate pick.
   - The conflict: this matches the brief's `test_din_mismatch_falls_to_single_candidate`. It contradicts Step 3's wording ("cloud VIN, single candidate, anonymous") and the commit title I was given ("before falling back to a single candidate").
   - The docs describe what the code actually does. The reviewer should decide whether the cloud ought to override a guess.
2. **Cloud lag at disconnect** (unverified). If live_status still reports the departed car's VIN when the next car connects, a known VIN confirms at once and the new car is misattributed.
3. **Version fetch cost.** While `/api/1/version` keeps failing, a unit retries it on every vitals poll, a 3 s timeout roughly every 5 s on the shared background thread. That is the brief's "retried on the next refresh". It is skipped when `din` is configured. A backoff may be worth adding.
4. **Single-unit fallback across sites.** With one local unit, no DIN and exactly one cloud connector, the match is made even if that connector is at another site.
5. **Unverified on hardware**, and marked so in code comments and docs:
   - the live_status `wall_connectors` shape;
   - the `<part_number>--<serial_number>` DIN format;
   - whether the Owner API serves live_status;
   - whether a `teslaProxy` base URL forwards energy paths (Storm Watch makes the same assumption).
6. M2 (the ramp overshoot) from Task 4 is not addressed here; it was optional.

## Fix round 1

**Commit:** `61ca7ea` Let the cloud VIN outrank a Gen3 plug-in guess and guard against the departed car's VIN (on top of 9ba3504).

**Tests:** full suite 1266 passed, 1 xfailed. That is 1255 plus 11 new tests, with 1 test rewritten and 1 test changed.

### Fail-before

I wrote the tests before the fix. Against 9ba3504 they gave `12 failed, 26 passed`:

```
FAILED test_din_mismatch_keeps_the_single_candidate_guess_and_keeps_asking
FAILED test_a_differing_known_cloud_vin_replaces_the_guess
FAILED test_a_differing_unknown_cloud_vin_replaces_the_guess_once_confirmed
FAILED test_an_equal_cloud_vin_confirms_the_guess_and_polling_stops
FAILED test_the_departed_cars_vin_is_ignored_on_the_next_cars_edge
FAILED test_the_same_car_replugged_is_named_a_poll_later
FAILED test_owner_412_latches_and_fleet_is_asked_next
FAILED test_owner_404_from_live_status_latches
FAILED test_fleet_404_does_not_latch_and_only_403_reports_a_scope
FAILED test_polling_slows_after_ten_unanswered_polls
FAILED test_a_failing_version_fetch_backs_off_for_ten_minutes   (urlopen call_count 2 == 1)
FAILED test_a_404_version_is_final                               (refreshVersion() False is True)
```

Two examples of the failure text:
- I1: `assert 0 == 1` on live calls (the reader stopped once the car was guessed); `'...0002' == '...0001'` (the guess was not replaced).
- I2: `'5YJ3E1EA1KF000001' == 'anon:Gen3TWC-10.0.0.1'` (the departed car was accepted at the edge).

### Fixes

- **I1. The cloud VIN outranks the plug-in guess** (`WallConnectorVins._waiting`, `Gen3TWC._correlate`).
  - `_waiting` now means: the unit is occupied, and its vehicle key is not its cloud VIN (compared case-insensitively). Polling therefore continues while the session is anonymous, guessed, or holds a pending cloud VIN. It stops once the cloud VIN names the session.
  - In `_correlate`, a confirmed cloud VIN that differs from the guess un-attributes the guess. The guess is looked up with `registry.get` and never created. Its `twcVin` is cleared (`seen=False`), `pluggedIn` is set to False under source `Gen3TWC`, and one INFO line is logged. A pending unknown VIN leaves the guess in place until it confirms.
  - Tests: `test_din_mismatch_falls_to_single_candidate` is rewritten as `..._keeps_the_single_candidate_guess_and_keeps_asking`. New tests cover replacement by a known cloud VIN, replacement by an unknown one (after it confirms), and confirmation by an equal one (after which polling stops).
  - Docs: the cloud VIN is listed first, and the plug-in rule is described as a guess that the cloud corrects. The limitation is noted.
- **I2. The departed car's VIN is guarded.**
  - `noteConnect(unit)` stamps the unit's edge time. `Gen3TWC._plugEdges` calls `vinReader.noteDisconnect(unit, vehicleAt.key)` on the falling edge, before the session ends.
  - In `match`, the departed VIN is skipped until `clock() - edgeAt >= POLL_SECONDS`. The unit stays waiting. The guard is cleared once a VIN is accepted.
  - Tests: the two-car swap (A, then B while the cloud still says A, then B on the next poll), and A re-plugged (accepted on the poll 60 s later).
  - **Changed test:** `test_disconnect_clears_the_cloud_vin_and_the_next_car_queries_again` now expects the re-plugged car to stay anonymous after the edge query and be named one poll later. This is the cost of I2 that the review predicted, not a regression.
- **I3. Version fetch backoff.** `_versionRetryAt` is a monotonic time; after a failed fetch there is no retry for 600 s. An HTTP 404 is final: `_version = {}`, so `din` is None. Tests: backoff, and 404 final.
- **I4. More answers latch the read.**
  - `ENERGY_REFUSALS = (401, 403, 410, 412)` latches both `/products` and live_status.
  - A 404 from live_status latches too, on the Owner slot only.
  - `reportScopeRefused` is called only on a 403 (this also fixes M3).
  - The INFO line now carries the HTTP code.
  - Tests: Owner 412 followed by Fleet on the next poll, with the Owner slot asked only once; Owner 404 latches; on Fleet, a 404 does not latch while 401/410/412 latch without a scope report and a 403 reports once.
- **M1 (fixed).** After `SLOW_AFTER = 10` polls in a row that name no car, polling slows to `SLOW_POLL_SECONDS = 600`. A connect edge, or a car being named, resets the count. A pending cloud VIN counts as unanswered, so a session the registry has *rejected* (three differing reports) also slows to 10-minute polls.
- **M3 (fixed):** see I4.

### Not fixed (noted only)

- M2: the single-unit rule counts only connectors that report a VIN.
- M4: up to 10 s blocking per site request.
- M5: an hourly Owner/Fleet flap when the Owner API answers live_status without `wall_connectors`. I did not latch that case.
- The optional lazy `providerOrder` lookup.

### Residual risk in I2 (follows from the chosen option)

- `_endedVin` records whatever `vehicleAt` held at the falling edge. If a session ended on a wrong plug-in guess that the cloud never corrected, the guard protects against the guess's VIN, not the true departed car's.
- When an anonymous session ends, the guard is cleared, so a stale VIN that survives two sessions is not caught.
- If live_status lags by more than 60 s, the stale VIN is accepted on the first later poll.

All three depend on live_status lag, which is unverified on hardware.
