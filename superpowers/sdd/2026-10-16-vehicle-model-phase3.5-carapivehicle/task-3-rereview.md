# Task 3 re-review (7d946ab..c02e333)

Verdict: all addressed. No open findings.

- m1: `expire` now skips `v.attachmentNames()`. Attachments are never removed in lib (no detach), and TeslaAPI never drops its keepsAlive claims, so every attached car was already unexpirable once claimed. The change closes only the attach-to-claim window. Unattached stale cars still expire. Mutation: with the skip removed, `test_an_attached_car_is_never_expired` fails.
- m2: `test_a_failed_online_check_still_sends_the_stop` fails when `is False` becomes `is not True` at TeslaAPIProviders.py:167.
- Q2 savings are behaviour-neutral:
  - `say = functools.partial(logger.log, logging.INFO2)`: same level and text, all three messages kept.
  - `min(levels or [10000])` equals `min(..., default=10000)` for the empty and all-default cases. A None value is impossible because `v.value` supplies the default.
  - `getOrCreate` is now `attach=None` on one line. Optional, Tuple and Any are still used elsewhere in VehicleRegistry.
- Suite: 1782 passed, 1 xfailed. `black --check` is clean.
- Nit, not a finding: TeslaAPI.py:13 `Any` is unused. It was already unused at 7d946ab, so this fix did not introduce it.
