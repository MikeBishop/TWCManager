# Readability review of the vehicle model (upstream main be211c81)

Two fresh Opus readers, read-only. Split: (A) Reconcile/Providers/Registry,
(B) Presence/Watch/ControlTick/EVSEInstance/TWCMaster admission. Spot-checked
against the code; one suggestion dropped (`str.removeprefix` needs 3.9).

## The pattern

Not mostly one-letter names. Three habits:

1. Tuples used as records, read by index: `best[0][0]`, `last[4]`, `seen[2]`,
   `want[1]`, `source[0]`, `RETRY[exempt]`, `Presence.decide(...)[1]`.
2. One short word reused for different things in the same file: `held`
   (record / dict / bool / `HeldLimit.held`), `wakes` (three meanings in
   `plan()`), `quiet`, `known`, `limit` (an AttemptRecord), `room`, `left`,
   `since`, `named`.
3. Tri-states and conditions built from unparenthesised `and`/`or` chains,
   double negatives, `pass` branches, `x if c else {}` tricks.

Plus: names that are adjectives or puns instead of saying what they return
(`said`, `known`, `standIn`, `uncompleted`, `handsOff`, `own`), one name that
says the opposite of its contents (`VEHICLE_SOURCES_EXCLUDED`), and comments
compressed past parsing.

Almost every fix is a rename or an in-place unpack; a few add 1-3 lines; one
(Order.py) removes code.

## High

| # | Where | Problem | Fix |
|---|---|---|---|
| 1 | `Reconciler.py:85,162-173,302,328` | `said`/`_said`/`_sayOnce`: the reason a desire is blocked, named as speech | `blockedReason` / `_blockedReasons` / `_logBlockedOnce` |
| 2 | `Rules.py:11` (+~10 uses) | `VEHICLE_SOURCES_EXCLUDED` holds the TWC sources | `TWC_SOURCES` |
| 3 | `TWCMaster.py:722` vs `_admit` return | returns `seated, held, shared, budgets`; caller unpacks `pool, given, left, budgets`; `left` means something else inside `_admit` | same names both sides; one line saying what the four are |
| 4 | `TWCMaster.py` | `held` = steady-reading record (`self._held`), points held at min (`_admit`), a bool; `hold` = a delay | `_steady`, `delaySecs`, `settled`; `held` only for points at minimum |
| 5 | `TWCMaster.py:656-662` | 5-tuple read as `last[:2]`, `last[2]`..`last[4]` | unpack once into named locals |
| 6 | `TWCMaster.py:781-789` | comment says drawing points sort first; key sorts wanting first. Comment unparseable | fix the comment (3-4 plain sentences) or the key |
| 7 | `TWCMaster.py:810-814` | `(a if c else b).append(p)`, `held.update({p: need} if cut else {})`, `-= need if cut else 0`; list `room` vs bool `room` | plain `if cut:` block; list → `standby` |
| 8 | `Reconciler.plan()` | `d`, `k`, `p`, `ch`, `dl`; `limit` holds an AttemptRecord | `want`, `belief`, `provider`, `freeChannel`, `limitWant`, `limitRec` |
| 9 | `Reconciler.py:251,349,357` | `wakes` reassigned with three meanings | `resumesFromHold`, `wantsWake`, final `wakes` |
| 10 | `Reconciler.py:369-402,501-511`, `Targets.py:82` | and/or chains relying on precedence; `paidAgain` hardest | name `retryDue`, `wakeCheckDue`; parenthesise the rest |
| 11 | `Run.py:551-567` | `ble`, `quiet`, `known`, `check` flags; `quiet`/`known` mean other things elsewhere | `noWakeBle`, `asleepLately`, `pingFirst` |
| 12 | `Belief.py:127-131` | `limit = believed = limit and limit.value`; double negation | 4 plain lines (belief, then pending, then held) |
| 13 | `Presence.py:198-211` `pluggedNow` | logic lives in `best[0][0]`, `best[1]`, `best[2]` | named locals |
| 14 | `Presence.py:190` | `unknown=` is the value returned when nothing says, passed positionally | `ifUnknown=`, by keyword at call sites |
| 15 | `Presence.py:464-490` `fits` | tri-state from `None if plugged else plugged`, `... or None` | explicit returns with a comment per case |
| 16 | `Watch.py:179,322-355` | ask `(cls, exempt)` read as `want[0]`/`want[1]`; `RETRY` indexed by a bool | `Ask` namedtuple; `RETRY_EXEMPT if exempt else RETRY_COURTEOUS` |
| 17 | `Watch.py:253-271` | `seen`/`was` 4-tuples by index, mixed and/or | unpack `wasState, wasWhere, ...` |
| 18 | `Watch.py:262-264` | `last`, `at`, `tried` (an answer, not a flag) | `statusAnswer, statusAt`, `readAnswer, readAt` |
| 19 | `Watch.py:301-306,453-458` | `_source`/`_listen` return tuples read by index; `(scan or source or (None,))[0]` | unpack after None check; plain conditional |

## Medium

- `Belief.py`: `standIn` → `twcChargingState`, `uncompleted` → `unlessLimitRaised`, `handsOff` → `whyHandsOff`; `handsOff`'s parameter `known` shadows the function.
- `held.held` (`HeldLimit` var named `held`): name such variables `saved`; `ours` → `heldAt`.
- `Desired.noteOutcome`: empty `if paid or held: pass` branch → `if not (paid or held):`.
- `VehicleReconciler.wake()` only sets the loop event → `nudge()`.
- `Presence.decide(...)[1]`, `applicable(...)[0]`; Outcome compared to a bare tuple → unpack, compare `O.Outcome(...)`.
- Held-branch exit test (`Reconciler.py:252-255`): name `asleepHoldNowWanted`.
- Magic `2` paid sends per arm → `PAID_SENDS_PER_ARM`.
- `Order.py`: index tie-break redundant (stable sort, registration order) → delete `_indexed`/`_key` (shrinks).
- `Vehicle.telemetryState` double negative → filter to telemetry sources directly.
- `Vehicle.observe` hook trick (`mine = ... if hook else prior`) → `if hook is not None:`.
- `B.`/`R.` aliases in Reconciler (and `B._newer` reaching into a private) → direct imports; make `newerReadings` public. `O.` and `C.` are consistent: leave.
- `_liveAt`/`sourceLiveAt` returns NOT_TRACKED / None / float, undocumented → one contract line.
- `Desired.py:318` bool arithmetic on a magic reason string → shared `UNREAD_REASON` constant, plain `+= 1`.
- `plan()` flags: `back` → `returnedAt`, `ride` → `startWillWake`, `asleep` → `notSeenAwake`, `holder` → `lastProvider`; field `paidSaw` → `beliefAtPaidSend`.
- `Presence._awayCharger`: inner `since` (elsewhere a time) and `o` → `sameReport`, `reading`; `pick.fresh` `o` → `reading`.
- `Presence.decide`: `home[0]`/`home[1]` → `homeAt, homeWhy`.
- `Presence.applicable`: `named` is an observation then a bool; `presumed` assigned twice; `a or b or c and d` → rename, parenthesise.
- `Presence.departed`: `away` means leaving; mixed and/or → `leftHome`, parenthesise.
- `leaving(v)`, `arriving(v)`, `returned(v)` return times → `leftAt`, `arrivedAt`, `returnedAt`.
- `Presence.attribute`: walrus inside getattr inside not → two lines.
- `pick`: parameter `offered` rebound → `offerSource`.
- `Watch.LoadStep.sample`: swap-and-clear one-liner, roundabout zero; `_held` → `_pending`.
- `Watch._source`: `api` bool then module → `useApi`; `fix` bool → `forPosition`; `n` → `phases`, name the 5-vs-1 A rule.
- `ChargingPoint`: `twc, car = self.carriers()` are bools → `twcCarries, carCarries`; `mine`/`own` → `heartbeatKeys`/`setHeartbeatRate`.
- `TWCMaster`: `_drawing`/`_drawAmps`/`_draws` near-identical, unrelated returns → `_draws` → `_budgetsOf`, loop `c` → `budget`; `self._willing` set inside a tuple assignment → own line.
- Comments to split into plain sentences: `Reconciler.py:72-73,342-344`, `Belief.py:62-64,149-150`, `Desired.py:95`, `Presence.py:18-20,243-248,269-271`, `TWCMaster.py:637-644`, `_admit`'s header.

## Low

- `CAPABILITY_FOR` is a function → `capabilityFor`. Unused `p` in `_whyNoWake`.
- `HeldLimits._entry(...)[0]` ×4 → unpack; `own` → `vinEntry`.
- Positional booleans → keywords (`Targets.py:83`, `Vehicle.py:263`, `Watch._read`'s 9 positional args).
- `self.key[5:]` → name the `"anon:"` prefix length (not `removeprefix`: Python 3.8).
- `configConfig` → `config`; repeated config lookup.
- `_waiting` → `_awaitingCloudVin`, `checked` → `asOutcome`, `event` → `eventAt`, loop var `attempt` → `poll`; `_STRONG` → `_PLACE_FREE_SOURCES`, `_PLUGS` → `_PLUG_FIELDS`, `scans` → `canScan`, `_reached` → `_heardRecently`, `spend(cls)` → `priority`; `ChargingPoint._caps` `k` → `requested`; `Gen2TWC.py:57` mixed-type `and`; `CACHED` constant mid-file; `Desired.set` double negation.

## Fine as is (both readers)

`v` vehicle, `obs` observation, `rec` AttemptRecord, `p`/`q` points or providers,
`e` endpoints/exceptions, `o`/`f`/`k` inside one-line comprehensions, `O.`/`C.`
module aliases, `pass_` (542 references), the `getattr(x, "value", None)`
idiom, documented tri-states (`asleep`, `_plug`, `inside`, `occupied`).
`WatchBudget.py`, `ControlTick.py`, `EVSEInstance.py`, `Gen3TWC.py`,
`VehicleEndpoint.py` clean.
