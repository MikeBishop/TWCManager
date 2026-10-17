# Task 7 re-review 1: fix round 61ca7ea

Scope: the I1–I4 findings, the fix-now minors, and anything the fix diff
(9ba3504..61ca7ea) newly breaks. Checkout: scratchpad/wt-vm2 at 61ca7ea.

**Verdict: APPROVED.** All four Important findings are fixed. The fix adds no
Critical or Important issue. M1 and M3 are fixed. Leaving M2, M4 and M5 is
acceptable.

Tests: test_wall_connector_vins, test_gen3twc_provider,
test_teslaapi_providers and test_teslapowerwall2_ems give 79 passed. I wrote
two throwaway probes, ran them, and then removed them. Both passed. The
checkout is clean again.

- **Swap with a plug-in guess.** A is named by the cloud and leaves. B is
  then guessed by the plug-in rule while the cloud still says A. The edge
  query skips A, so the B guess stands and A is not re-attributed. The next
  poll reports B, which confirms the guess. B stays `pluggedIn=True`, and
  polling stops (3 live calls in total).
- **A rejected cloud candidate under a guess.** The cloud names six
  different unknown VINs. The guess stands, the registry rejects the
  candidate, and 30 minutes of 60 s ticks make at most 13 live calls.

## Findings

| # | Verdict | Notes |
|---|---|---|
| I1 | Fixed | See below. |
| I2 | Fixed | The residual risks are as stated in the report and are acceptable. |
| I3 | Fixed | |
| I4 | Fixed | M3 is fixed with it. |
| M1 | Fixed | |
| M2 | Left; acceptable | The behaviour is documented (c4), and the fix has to wait for a connector count from the cloud. |
| M4 | Left; acceptable | The block is bounded at 10 s per site, happens on a background thread and is rate-limited. |
| M5 | Left; acceptable | It costs one free products+live_status pair an hour. The I4 latch does not make it worse. |

### I1: the cloud VIN outranks the plug-in guess

- `_waiting` (WallConnectorVins.py:62-70) is True while the unit is
  occupied and its key is not the cloud VIN, compared case-insensitively.
  Polling therefore continues while the session is anonymous, while it holds
  a guess, and while a cloud VIN is still pending. It stops once the key
  equals the cloud VIN. A non-string key returns False, which is safe.
- `_correlate` (Gen3TWC.py:273-295) behaves as I1 asks:
  - It records `guessKey` before calling `observeTwcVin`.
  - The guess is un-attributed only on `"confirmed"` and only when the
    confirmed VIN differs from the guess.
  - The guess is looked up with `registry.get`, which only reads the dict
    under the lock (VehicleRegistry.py:93-95). A vehicle that is gone is
    skipped, so no vehicle is created or revived.
  - The only vehicle this path creates is the cloud car, through
    `observeTwcVin`'s `getOrCreate`. That is intended.
- `vehicleAt` returns the newest `twcVin` stamp, so the new car wins even
  before the guess's `twcVin` is cleared. A pending unknown VIN leaves the
  guess in place, and the next equal report confirms it.
- A rejected candidate keeps polling, but M1 slows it to every 10 minutes.
  The second probe confirms the bound.
- The tests cover the three cases I1 asked for, and the rewritten DIN
  mismatch test checks that polling continues.
- Docs: the cloud VIN is listed first, and the plug-in rule is described as
  a guess that the cloud corrects.

### I2: the departed car's VIN

- `noteDisconnect` runs on the falling edge before `endPlugSession`, so
  `vehicleAt` still returns the leaving session. It records a named key and
  clears the entry for an anonymous one.
- `noteConnect(unit)` stamps the edge using the reader's clock.
- `_stale` skips the departed VIN only while `clock() - edgeAt <
  POLL_SECONDS`. The skipped unit stays waiting, so the next poll asks
  again.
- A re-plugged car cannot be starved. The guard is purely time-based:
  - The first poll at least 60 s after the edge accepts the VIN.
  - `lastQuery` was set at the edge, so that poll is due at exactly
    edge + 60, when `_stale` is already False.
  - `test_the_same_car_replugged_is_named_a_poll_later` pins this.
  - The guard is cleared on acceptance, and a later anonymous session
    clears it too.
- The two-car swap test and my guess variant both pass.
- Residual risks: lag over 60 s, a session that ended on an uncorrected
  guess, and a stale VIN that survives two sessions. All three are as the
  report states, and acceptable until hardware shows the lag.

### I3: the version backoff

- A failed fetch sets `_versionRetryAt = monotonic + 600`, and a fetch
  before that time returns at once without HTTP.
- An `HTTPError` 404 is final (`{}`, so `din` is None). Other HTTP errors
  back off.
- `HTTPError` is caught before the generic `Exception`, so a 404 is not
  mistaken for a transient failure.
- The tests patch `Gen3TWC.time.monotonic` and show one `urlopen` call in a
  window and a successful retry 600 s later.

### I4: the latch codes

- `ENERGY_REFUSALS = (401, 403, 410, 412)` applies to both `/products` and
  live_status.
- A 404 latches only from live_status on the Owner slot. A 404 from
  `/products`, or from Fleet live_status, does not latch.
- `reportScopeRefused` is called only on a 403, which also fixes M3.
- The INFO line carries the code. The latch still stores `slot.changes`, so
  a token change re-arms it.
- Test: Owner live_status answers 412, the next poll asks Fleet, and the
  Owner slot is asked only once in total.

### Cost: only free endpoints

- `onlyFreeCalls` is unchanged, and it still asserts that every request is a
  GET to `products` or `energy_sites/<id>/live_status`.
- It is still asserted in the original tests, and the new I4 test adds one
  more assertion.
- The new paths add no endpoint: `noteDisconnect`, un-attribution and the
  backoff are all local.

## Newly broken by the fix

Nothing. Checked:

- `_waiting` has no callers outside the reader.
- `noteConnect`'s argument is optional, so the old no-argument test calls
  still work.
- The `_unanswered` counter is shared by all units:
  - Each reset needs an event: a new edge or a car being named.
  - Polling therefore stays bounded at one call every 10 minutes for each
    stretch without an event.
  - A busy multi-unit install may poll faster for a while, which is
    harmless.
- One more effect of I1: a guessed session with no ready provider now runs
  the reader loop. That loop makes no HTTP call, and M1 slows it.
- Checked, no finding: `_correlate` compares `guessKey` without upper-casing
  it. That is safe because `_getOrCreate` stores every VIN key uppercased
  (VehicleRegistry.py:78). An equal cloud VIN in a different case therefore
  cannot un-attribute the right car.
- Not a finding: the un-attributed guess keeps the `actualCurrent` and
  `voltage` it was given while guessed. Those are ordinary aging values.
