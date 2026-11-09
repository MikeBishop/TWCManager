Readability: name what the vehicle reconciler's values hold

This is a readability pass over the vehicle reconciler (`Vehicle/Reconcile/`), the provider order and the vehicle registry entry. It changes no behaviour. Most of it is renames: names that read as speech or puns (`said`, `standIn`, `uncompleted`) now say what they return. One name said the opposite of its contents: `VEHICLE_SOURCES_EXCLUDED` holds the TWC sources. In `plan()`, one-letter names and words reused for different things (`wakes` had three meanings, `held` and `limit` two each) now each have one name per meaning.

The rest are small in-place changes. Tuples read by index (`Presence.decide(...)[1]`, `applicable(...)[0]`) are unpacked where they are used. `and`/`or` chains that leaned on precedence are parenthesised, and the hardest ones (`paidAgain`, the held-branch exit) are split into named conditions. A `pass` branch and a bool added to an int are gone. The magic paid-send count `2` and the unread-limit reason string are now named constants. Compressed comments are rewritten as plain sentences. `ProviderOrder` drops an index tie-break, because the sort is stable and the list is already in registration order.

Where a condition used to evaluate lazily (`Presence.decide`, `Presence.applicable`, the paid retry checks), the rewrite keeps the same short-circuiting, so nothing that was skipped before runs now.

Main renames (old -> new):

- `Rules.VEHICLE_SOURCES_EXCLUDED` -> `TWC_SOURCES`
- `VehicleReconciler.said` / `_said` / `_sayOnce` -> `blockedReason` / `_blockedReasons` / `_logBlockedOnce`
- `VehicleReconciler.wake()` -> `nudge()`, since it only wakes the reconciler's loop
- `Belief.standIn` -> `twcChargingState`, `uncompleted` -> `unlessLimitRaised`, `handsOff` -> `whyHandsOff`, `_newer` -> `newerReadings` (now public; the reconciler used it)
- `AttemptRecord.paidSaw` -> `beliefAtPaidSend`
- In `plan()`: `d` -> `want`, `k` -> `belief`, `p` -> `provider`, `ch` -> `freeChannel`, `dl`/`limit` -> `limitWant`/`limitRec`, `back` -> `returnedAt`, `ride` -> `startWillWake`, `asleep` -> `notSeenAwake`, `holder` -> `lastProvider`, `held` -> `saved` (and `_held()` -> `_saved()`); `wakes` split into `asleepHoldNowWanted`, `wantsWake`, `wakes`; new `retryDue`, `wakeCheckDue`
- In `Run.runAttempt`: `ble`/`quiet`/`known`/`check` -> `bleCommand`/`noWakeBle`/`sleepInWindow`/`pingFirst`
- In `Rules`: `HeldLimit` parameters `held` -> `saved`, `ours` -> `heldLimit` (a percentage, not a time)
- New constants: `PAID_SENDS_PER_ARM`, `Outcome.UNREAD_REASON`
- The `B.`/`R.` module aliases in the reconciler are now direct imports

Evidence: full suite (`pytest tests --ignore=tests/API --ignore=tests/integration`): 2618 passed, 1 xfailed. The only test changes follow the renames.

Changelog: none (no behaviour change)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
