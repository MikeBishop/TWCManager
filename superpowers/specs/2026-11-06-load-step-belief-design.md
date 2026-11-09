# Load step: meter steps, explained by belief — design (short)

Branch: `feat/fleet-charge-backfill`. Files: `lib/TWCManager/Vehicle/Watch.py`
(`LoadStep`, `Watch.loadSample`), `tests/unit/test_watch*.py`.

## Why

The anti-goal for the vehicle watch is a stealth continuous poll. A 4.5-day
replay of the box's load log (`~/cachelog/load.jsonl`, 30 s samples) found
rises keeping the snapshot poll running 34% of the car's home-awake-idle time
(upper bound). Five of eleven polling stretches were not house load: they
were the main instance's believed charger load lagging the meter.

`LoadStep` steps on *unexplained* load (consumption − believed charger load),
so a belief change alone is a step. A Fleet-only car's belief follows its
snapshots, which trail the meter: at a stop the meter falls (a correct fall),
then the belief clears (a false 11.5 kW rise); at a start the meter rises (a
correct rise), then the belief arrives (a false fall).

## Goals

- A change in believed load alone is never a step.
- While a car is believed charging, a fall too small to be that car stopping
  does not act for it.
- No added delay to detecting a real charge start or stop.

## Non-goals

- Filtering house-load rises by the car's expected rate (deferred; separate
  design if pursued).
- Any change to hold length or threshold.

## Anti-goals

- More reads or polls than today in any case.
- Missing a start or stop that today's step catches, other than one fully
  explained by a belief change in the same direction.

## Approaches

- **A. Step on the meter; a matching belief change explains it (chosen).**
  `LoadStep` samples raw consumption. A reported step is dropped when the
  believed load moved the same way by at least half the step within the
  lookback window. Replay: belief artifacts 7 rises / 4 falls → 0; real stops
  kept; no car change missed.
- B. Mute any step for 2 minutes after a belief change. Simpler, but with
  several cars it mutes one plugging in while another's belief clears
  (caught only at the courtesy cadence, up to 20 min).
- Rejected: rebase the step on a belief jump. Fixes stops only; a late-learned
  start still makes a false fall.

## Design

1. **Step source.** Under `subtractChargerLoad`, `LoadStep` samples
   `getConsumption()`. Without it the meter does not see charging and belief
   explains nothing: sample consumption as today, no explanation check.
2. **Explanation.** Keep the believed charger load (`getChargerLoad()`) for
   the last 120 s of samples. When a step is reported, compare the belief now
   with the oldest belief in that window: if it moved the same direction by at
   least half the step's size, the step is explained and nothing acts.
   120 s covers the lag seen (belief trailing the meter 30–90 s); a start we
   commanded or a rate we set (belief leading the meter) falls in it too.
3. **Fall size while charging.** `LoadStep.sample` also returns the step's
   size. In `loadSample`, a fall acts for a car believed charging only if its
   size is at least half that car's believed draw (`liveWatts(vin)`).
   Replay: house-load falls while charging 8 → 0, real stops kept.
4. Rises are otherwise unchanged.

## Left to the builder

- Data structure for the 120 s belief window (time-based, not sample-count:
  the live pass cadence is not the logger's 30 s).
- Whether the window and the half-size fraction are constants or `watch`
  settings (default: constants, explained by a comment).
- Tests: belief clears after a meter fall (no rise); belief arrives after a
  meter rise (no fall); commanded start (belief leads, no step); unexplained
  start (rise acts); small fall while charging (ignored); car-sized fall while
  charging (acts); no `subtractChargerLoad` (no explanation applied).
- Keep lib growth minimal; line budgets are targets.
