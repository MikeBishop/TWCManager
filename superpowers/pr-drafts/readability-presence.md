Name the tuples and tri-states in Presence and the watch

Presence.py and Watch.py read much of their state out of tuples by index (`best[0][0]`, `home[1]`, `seen[2]`, `want[1]`, `source[0]`, `(scan or source or (None,))[0]`), indexed `RETRY` by a bool, and built tri-state answers from `and`/`or` chains such as `None if plugged else plugged`. This makes the code hard to follow when checking what a car's plug or presence decision rests on.

This change unpacks those tuples into named locals, makes the watch's asked-for read an `Ask` namedtuple, writes `pick.fits` as one explicit return per case, renames the timestamp helpers for what they return, and splits a few compressed comments into plain sentences. It is a readability change only, with no change in behaviour. Each tri-state rewrite returns True, False and None in exactly the cases it did before. Outside these two files only call sites change: one line each in `Reconciler.py` and `Belief.py`, plus the tests that use the renamed names.

Main renames:

- `Presence.leaving` / `arriving` / `returned` -> `leftAt` / `arrivedAt` / `returnedAt`
- `pluggedNow(..., unknown=)` -> `pluggedNow(..., ifUnknown=)`, now passed by keyword at every call site
- `pluggedNow`'s `best` tuple -> `bestKey`, `plugged`, `readBy`, `readAt`
- `decide`'s `home[0]` / `home[1]` -> `homeAt`, `homeWhy`
- `pick(offered=)` -> `pick(offerSource=)`; `_awayCharger.since` -> `sameReport`
- `departed`'s `away` -> `wasHere` / `leftHome`; `applicable`'s reused `named`/`at` -> `twcVin`, `namedAt`, `named`
- Watch: the `(cls, exempt)` tuple -> `Ask`; `RETRY[bool]` -> `RETRY_EXEMPT` / `RETRY_COURTEOUS`
- Watch: `last, at` / `tried, lastRead` -> `statusAnswer, statusAt` / `readAnswer, readAt`; `was[0..3]` -> `wasState, wasWhere, wasPlugIn, wasDoor`
- Watch: `fix` -> `forPosition`; `api` flag -> `useApi`; `n` -> `phases`, `carMinAmps` -> `minAmpsPerPhase`; `LoadStep._held` -> `_pending`, its `held` -> `confirmed`

Evidence: full unit suite (`pytest tests --ignore=tests/API --ignore=tests/integration`): 2618 passed, 1 xfailed.

Changelog: none (no behaviour change)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
