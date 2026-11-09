# Expected-rate filter for load rises — design (short)

Branch: feat/fleet-charge-backfill.

## Why

On 2026-11-07 a 2.5 kW house rise at 21:12 counted as a possible arrival. It used `_mayBeBack`'s one early read per `sleepCourtesySecs` window. The car's real plug-in at 21:26 (+11.4 kW) then waited for the cadence read at 21:36: about 10 minutes and 2 kWh charging above the policy limit. On the same data, the replay found polls running during 51% of the car's home-awake-idle time. The PR gate allows 10-15%. Both come from small house rises being treated as possible car starts.

## Goal

A rise counts as a possible start for a car only if it is big enough to be that car starting at the rate it would start at with nothing commanding it.

Non-goals:
- Filtering falls; they already have the half-of-live-draw filter.
- Changing the step detector or its threshold.
- Resetting or restoring the car's amps on departure. The car's remembered amps is the only throttle on an EVSE TWCManager doesn't control, until the first command, so a low value may be intended. A command would also have to land while the car is still home, because cars remember amps per location.

Anti-goal: a real start filtered out. When unsure, count the rise.

## The expected rate (user's call)

- Learned only from readings of a car plugged in at home. The user's reason: a car plugged into a lower-power EVSE reports that EVSE's cap, while a car not plugged in reports its own maximum, which can't be trusted.
- One sample per plug-in at home: `chargeCurrentRequest` from the first reading after the plug-in (`markAt("plugIn")`) that is newer than the plug-in, sees the car at home and plugged in, and has no amps command (`lastWrite("chargeCurrentRequest")`) since the plug-in. That is the rate an uncommanded start draws. Mid-charge values set by green or policy commands are not samples. Any provider's reading counts: Fleet read or snapshot, BLE, or feed.
- Revised after review: the car keeps the last amps commanded at home for its next plug-in, per location. So each car also keeps the amps it holds for home now: the newest command or reading during this plug-in. That value counts alongside the samples.
- A reading not newer than the car's last fix outside the home radius is never a sample. Arrival heard only through BLE contact sets no arrival mark.
- Keep the last 5 samples per car. (My call: 5.)
- Global, not per car (user, mid-build). The charger caps the rate more often than the car, so every car's plug-ins describe the chargers at this location. Expected watts = `convertAmpsToWatts(min(all cars' samples and held amps))`, applied to every car. Every non-anonymous car is sampled, including covered and TWC-named ones: more samples can only lower the minimum. Using the lowest errs toward counting rises.
- No samples at all: no filter, which keeps today's behaviour.
- A unique identifier for the EVSE would allow more, but Tesla's charge state carries none, and returns diminish quickly (user).
- Samples persist across restarts in settings: plug-ins are rare and the filter needs them. They are kept per car, not in the ledger: the ledger holds Fleet-only cars and prunes empty ones, and BLE-watched cars need samples too. Where exactly to keep them is left to the builder.

## The rule

In `Watch.loadSample`, for an "up" step whose `size` (meter rise) is below half a car's expected watts, that car is skipped. Skipped means everything a rise does for that car:
- no suspicion
- no `readNow`
- no `_waking` online check
- no `_mayBeBack` window spent

`_mayBeBack` applies the same per-car test, so a rise too small for every car changes nothing.

Example, on the box: 48 A gives about 11.5 kW, so the cutoff is about 5.8 kW. The 21:12 rise (2.5 kW) is ignored; the 21:26 plug-in (11.4 kW) reads at once.

With several cars, every car is tested against the one location-wide expected rate.

## Unchanged

- Cars `notWatched()` excludes: TWC-named or covered by a feed. The filter sits after that.
- The fall filter and the belief explanation.
- Cadence and courtesy reads, which still catch anything the filter drops, within one window.

## Tests (for the plan)

- A rise under half the expected rate opens no suspicion, triggers no read, and leaves `_mayBeBack` unspent. A real-size rise 14 minutes later then reads at once: the 2026-11-07 case.
- With no samples, a small rise behaves as today.
- A sample is taken only from the first reading of a plug-in at home that comes before any amps command. Readings unplugged, away, or after a command add nothing.
- The 5-sample window and the lowest-sample rule.
- Samples survive a restart (save and load).
- A BLE-watched car is filtered the same way (`readNow` path).
- Replay check before deploy: `pollsim.py`'s filtered row, now per-car expected rate, on the 11-06 to 11-07 data.

## Approaches considered

1. **Plugged-in-at-home samples, first reading per plug-in, lowest of 5 (chosen).** This predicts the uncommanded start rate. It needs one home plug-in before it filters anything.
2. **Ledger segment watts.** Measured charging, but Fleet-only cars only, empty on a new install, and mid-charge commanded rates pull it down.
3. **Fixed share of the EVSE's maximum.** Wrong for a car whose home amps are set low, which could filter out its real start.

The user ruled out the car's reported amps from readings while not plugged in, because it reports the car's own maximum.
