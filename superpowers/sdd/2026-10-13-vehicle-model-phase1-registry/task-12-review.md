### Spec Compliance
Matches the brief: registry set before the enabled check, getOrCreate/attach/observe name/claim, observations after parse, HomeAssistantReadSource (order 1, canRead = attachment, fetch refreshes and returns {}), registered once enabled. 7 focused tests pass. Spec deviation is only the brief's own design flaw (see Important 1).

### Strengths
- Observes only values parsed in that pass; forgotten vehicle not recreated (HomeAssistant.py:151-156).
- ValueError from getOrCreate is guarded and logged; VIN is already VIN_REGEX-checked and Tesla-only filtered before the registry, so non-Tesla/no-VIN devices never reach it.
- Tests cover forgotten vehicle, disabled, charging/location.

### Issues
Critical: none.

Important
1. Sources.py:~114-118 / HomeAssistant.py:157: fetch always returns {} and refresh_from_home_assistant always returns True (even when HA is down or every entity 404s). Cascade (ReadSource.py:56) stops on `{}` when a latest value exists. Consequences: (a) HA down or entity missing (e.g. no location_tracker, no charge_limit_number) with a stale/older latest from BLE/API -> stale value returned, TeslaAPI never asked; (b) unobserved advertised fields (voltage, phases, actualCurrent, timeToFullCharge, gpsAsOf) with any latest -> same. Order: HA and TeslaAPI are both order=1, ties broken by registration order (TeslaAPI.py:144 vs HomeAssistant.py:242, i.e. module load order), so HA can precede the cloud API. BLE (order 0) is unaffected. Fix: fetch should return the dict of fields this pass actually observed (filtered to the requested/advertised set) or None when `field` was not freshly observed; narrow `fields` to the six actually observed; return None if no state fetched.
Related: each fetch does up to 5 sequential REST calls with 5 s timeouts under _rest_lock, and a cascade of N stale fields calls refresh N times; with HA down that is long blocking (not serial thread, but still). Consider returning None fast on first failure.

Minor
2. HomeAssistant.py:~380: hv appended to carApiVehicles before getOrCreate; on ValueError the car works in HA but is outside the registry. Acceptable (guarded, logged at debug, near-unreachable); log at warning or append after success for consistency.
3. Batching at end of refresh: harmless; one registry.get per refresh. Fine. Note observations skipped if refresh raises midway; trivial.
4. Claim static bool: since discovery requires charge_switch, the bool is always True (constant), so the `or` chain is dead logic. Not runtime-sensitive in the current code (carApiVehicles is never pruned), but a callable (e.g. HA reachable and hv in carApiVehicles) would match TeslaBLE/API and let tier fall to observed when HA is down; defer unless Phase 2 uses tier for commands.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** Plumbing, identity handling and tests are sound, but the read source's unconditional `{}` can end a cascade on stale data before TeslaAPI (same order, registration-order tie), and returns success when HA is unreachable. Fix by returning observed fields or None. The rest is minor.
