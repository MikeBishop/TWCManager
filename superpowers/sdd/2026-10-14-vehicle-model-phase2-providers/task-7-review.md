# Task 7 review: Wall Connector VIN from the energy site

Range 70b53af..9ba3504 (1f197e3, 9ba3504). Checkout: scratchpad/wt-vm2.
Focused tests run: test_wall_connector_vins, test_gen3twc_provider,
test_teslaapi_providers, test_teslapowerwall2_ems: 68 passed.

## Verdicts

- **Spec compliance: PASS.** Every Interfaces item is present. Concern 1's
  behaviour (a single-candidate guess stops the cloud) follows the brief as
  written, including its own `test_din_mismatch_falls_to_single_candidate`.
  The coordinator's c1 ruling changes the spec, so that work is a fix-round
  item (I1), not a compliance failure.
- **Task quality: PASS WITH FIXES.** The cost discipline is sound. Four
  Important findings: c1 (I1), c2 (I2), c3 (I3), and an Owner-slot
  410/412/404 gap that can leave the feature dead (I4).

## Checks requested

| Check | Result |
|---|---|
| Only free endpoints | Pass. `_energyGet` is reached only with `products` and `energy_sites/<id>/live_status` (TeslaAPI.py:1322-1400). No vehicle endpoint, `vehicle_data`, wake or command is added. `onlyFreeCalls` pins this in four tests. |
| Rate limit | Pass. `RateLimit(2, 60)` is enforced per provider in `_allowed`, and every attempt counts, refused ones included. The poll is 60 s plus a connect edge. |
| No free-running loop | Pass. `apply` runs only from `noteVitals`, which runs only after a successful vitals fetch (about every 5 s), and `due()` gates it. A failed vitals fetch does not call `noteVitals`. |
| Polling bounded / stops | Pass against the brief: polling stops when the unit is unoccupied or the session has a VIN. It is unbounded in time while a session stays anonymous (M1). |
| No HTTP on serial thread / under locks | Pass. The path is `gen3Vitals` background task, then `refreshVitals`, `noteVitals`, `apply`. `noteVitals` takes no lock. `ready()` and `wallConnectorVinsReady` are cache-only. |
| Refusal latch | Pass for 401/403. It latches against `slot.changes`, logs one INFO, a token change re-arms it, and `slotRequestFailed` is not called, so vehicle reads are not paused. The latch misses 410/412/404 (I4). |
| No token in logs | Pass. Only `type(e).__name__` is logged, plus a DEBUG `exc_info` in `apply`. That traceback carries no headers, because requests exceptions are caught inside TeslaAPI. |
| Gen2-only installs | Pass. The reader exists only inside `Gen3TWCs` and only sees Gen3 units. With no Gen3 configured nothing is queried. `ready()` is cache-only and safe to broadcast. |
| Carry 1: ready(None) relaxed | Pass. It is scoped to `READ_WALL_CONNECTOR_VINS`, and every other capability still returns False for a None vehicle (tested). |
| Carry 2: N1 orphan | Pass. Gen3TWC.py:196 skips begin/correlate when the point already holds a named car. A retried edge can only arise when the previous rising attempt raised, so skipping is correct. The test fails without the guard (implementer showed this). |
| Carry 3: docs | Pass for the current behaviour. The ordering text must change under c1 (in I1). |
| Carry 4: late VIN attaches | Pass. Tests cover both an unknown VIN (pending, then confirmed) and a known VIN (attaches at once). |

## Deviation rulings

1. **`_energySitesEmpty` as a timestamp that re-arms after the TTL: ACCEPT.** The brief's bare `True` would kill the feature until restart, and a failed fetch is correctly never cached as empty.
2. **`match()` returns `{unit: vin}`: ACCEPT.** The brief's `Dict[str, str]` contradicts its own `apply`.
3. **"no DIN match" INFO also for a known DIN that matches nothing: ACCEPT.** It is once per unit per session, and it is the only signal to set `din`.
4. **401/403 on `/products` latches the same refusal: ACCEPT.** See also M3 on the message.
5. **Merged map when any site answers, None only if none answered: ACCEPT.**
6. **Owner-to-Fleet fallback on the next poll: ACCEPT.** It costs one minute, once per token.
7. **(Unlisted, 9ba3504) `refreshVersion()` skipped when a `din` is configured: ACCEPT.** The `din` property returns the configured value first, so the fetch would be wasted.

## Findings

### Critical

None.

### Important

**I1 (c1 ruling): a cloud VIN must outrank, and replace, a single-candidate guess.**
- Where: WallConnectorVins.py:43-45 (`_waiting`), :120, :129; Gen3TWC.py:215-245 (`_correlate`); docs Controller_Gen3TWCs.md:132-143.
- Current behaviour: `_waiting` requires an anonymous key, so a guessed VIN stops the reader at the edge.
- Fix:
  - Make `_waiting(unit)` be `unit.occupied is True and (unit.cloudVin is None or (unit.vehicleKey or "").upper() != unit.cloudVin.upper())`. With this, polling continues while the session is anonymous, while it holds a guess, and while a cloud VIN is still pending. It stops only once the session key equals the cloud VIN.
  - In `_correlate`, when `cloudVin` is set and `registry.vehicleAt(pointId)` is a named car with a different VIN (the guess), call `observeTwcVin(pointId, cloudVin)`. If that returns `"confirmed"`, un-attribute the guess:
    - `guess.observe("twcVin", None, "TWC", seen=False)`, as `endPlugSession` does;
    - `guess.observe("pluggedIn", False, "Gen3TWC")`.

    This stops the guess from looking "on another TWC" or plugged in. A pending unknown VIN leaves the guess in place until it confirms.
  - Rewrite `test_din_mismatch_falls_to_single_candidate`. The guess still holds when the DIN mismatches, but the reader keeps polling (live_status calls grow at 60 s).
  - Add tests:
    - a guess replaced by a differing known cloud VIN, with the old car un-attributed;
    - a guess replaced by a differing unknown cloud VIN after two reports;
    - a guess confirmed by an equal cloud VIN, after which polling stops.
  - Docs: list the cloud VIN first. The plug-in rule names the car provisionally and is corrected if the cloud later disagrees. Polling continues once a minute until the cloud names the car or it is unplugged.

**I2 (c2: stale VIN after the previous car left). Ruling: a real risk; apply the minimal mitigation.**
- Why it matters: one Gen3 shared by two cars that are swapped in the evening is the common household pattern this feature serves. A swap takes one to three minutes. The first query runs within about 5 s of the new car's connect edge. If live_status (whose lag is unverified) still carries the departed car's VIN, that VIN is *known*, so `observeTwcVin` confirms at once and the reader stops. Under I1 a cloud VIN is final, so the whole session would be attributed to the wrong car: its charge limits, policy and stats. An unknown stale VIN cannot cause this, because it needs two matching reports.
- Fix (minimal; keep all the stale-VIN state in the reader, keyed by `unit.ID`):
  - `noteConnect(unit)` takes the unit. It stamps `self._edgeAt[unit.ID] = self.clock()` and stores `self._endedVin[unit.ID]`, the VIN of the session that last ended on that unit.
  - Feed `_endedVin` from the falling edge. Either have `Gen3TWC._plugEdges` (Gen3TWC.py:199-207) hand the leaving vehicle's VIN (None if it was anonymous) to `controller.vinReader.noteDisconnect(unit, vin)` before `endPlugSession`, or have the reader remember `unit.vehicleKey` on each `apply` while the unit is occupied. Choose one.
  - In `match`, skip a cloud VIN equal to `_endedVin[unit.ID]` (case-insensitive) when it is the edge query, that is, when `clock() - _edgeAt[unit.ID] < POLL_SECONDS`. Leave the unit waiting so the next poll is asked.
  - Clear `_endedVin[unit.ID]` once a VIN is accepted.
- Chosen rule: the departed car's VIN is accepted from the first poll at least `POLL_SECONDS` after the edge.
- Residual risk: if live_status lags by more than 60 s, the stale VIN is still accepted on that poll. The rule is chosen for minimality. If hardware shows longer lag, raise the guard to two such polls.
- Cost: the same car re-plugged is named about a minute later. The plug-in rule may still name it provisionally in the meantime.
- Test: car A is known and named, then unplugged. Car B plugs in while live_status still says A. Assert the session is not A after the edge query, and that it is B after the next poll reports B. Also cover A re-plugging: A is accepted on the poll 60 s later.

**I3 (c3 ruling): back off a failing `/api/1/version`.**
- Where: Gen3TWCs.py:286-287; Gen3TWC.py:163-181.
- Current behaviour: while the fetch fails (unit firmware without the endpoint, or a timeout), every vitals poll spends up to 3 s on the shared background thread, about every 5 s, indefinitely.
- Fix:
  - Add `self._versionRetryAt = 0.0`. `refreshVersion()` returns at once while `time.monotonic() < _versionRetryAt`, and on failure sets it to `now + 600`.
  - Treat an HTTP 404 (`urllib.error.HTTPError` with code 404) as a definitive answer: `_version = {}`, never retried. `din` then falls to None, so the single-unit rule applies.
- Test: two refreshes within 600 s make one `urlopen` call, and one after 600 s makes a second. A 404 sets `{}`.

**I4: the Owner slot answering 410/412/404 is not latched, so Fleet is never asked.**
- Where: TeslaAPI.py:1332-1336 (`/products`) and :1395-1399 (`live_status`).
- What happens: only 401/403 latch. Any other non-200 is a silent `continue`/`return None`, and `wallConnectorVinsReady(ownerSlot)` stays True. Fleet's `ready` requires the Owner slot *not* ready (TeslaAPIProviders.py, Fleet `ready`), so Fleet is never a candidate.
- Why it matters: Tesla answers deprecated Owner API paths with 412 "only available on fleetapi" (TeslaAPI.py:1270-1273 notes this for `/vehicles`). The codebase already treats 403/410/412 as refusals (TeslaAPI.py:319, :396, :2405). If the Owner API answers live_status with 412 (or 404/410), an Owner+Fleet install never names a car, and it asks the Owner API once a minute for nothing.
- Fix:
  - Latch on `(401, 403, 410, 412)` for both requests, and also on 404 from live_status on the Owner slot.
  - Call `reportScopeRefused` only for 401/403, so the Fleet ERROR about a missing scope is not logged for a 412.
  - The INFO line can carry the code.
- Test: Owner live_status gets 412, then Fleet is asked on the next poll, and the Owner slot is not asked again until its token changes.

### Minor

- **M1: polling is unbounded in time.** It continues once a minute while a session stays anonymous (and, after I1, while it holds a guess). This includes a session whose candidate the registry has *rejected* (`observeTwcVin` returns "rejected" for the rest of the session) and a unit whose known DIN never matches. The calls are free and rate-limited, so this is acceptable. Optional: after about 10 polls with no accepted VIN, poll every 10 minutes. WallConnectorVins.py:49-51.
- **M2 (c4, accepted): the single-unit fallback counts only VIN-bearing connectors.** `len(cloud) == 1` counts connectors that report a VIN, not connectors on the account. A DIN-less local unit whose own connector has no VIN yet takes the car on *another* Wall Connector. Documented as c4. If `wallConnectorVins` ever returns the connector count, require exactly one connector. WallConnectorVins.py:97.
- **M3: a 401 on the Fleet slot logs a scope message.** A 401 on Fleet `/products` or live_status calls `reportScopeRefused(..., refused=True)`, which logs "token lacks energy_device_data". A 401 is an authentication failure, not a missing scope. Pass `refused=True` only for 403. TeslaAPI.py:1308-1314.
- **M4: up to 10 s blocking per request.** Each products/live_status request can block the shared background thread for up to `ENERGY_TIMEOUT` (10 s), multiplied by the number of sites. It is rare and rate-limited; noted only.
- **M5: an hourly Owner/Fleet flap is possible.**
  - Trigger: the Owner API's live_status answers without a `wall_connectors` key.
  - What happens: the Owner slot drops the site, `_energySitesEmpty[owner]` is set and Fleet takes over. After `ENERGY_SITES_TTL`, Owner re-arms. It then spends one products+live_status pair, during which Fleet is not ready, before dropping the site again.
  - Cost: free, once an hour, so noted only. If I4 latches Owner refusals, consider latching an Owner "no wall_connectors" while Fleet's answer does carry the key.
- Verified, no finding: `master.providerOrder` exists before `Gen3TWCs` is built (TWCMaster.py:123 runs before TWCManager.py:807), so the reader's construction-time `getattr` gets the real order. A lazy lookup in `query()` would still be more robust, but this is optional.
