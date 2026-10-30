# Clear a restore once the car is back at its normal limit

Branch: `fix/satisfied-restore-clears` (b02b778b), against `main`

## Summary

When a car leaves, the reconciler puts its normal (outside) limit back. Once that restore succeeds, nothing is held, but the restore desire stayed in place. Two things followed from that:

- **A limit set while away was adopted.** If the user changed the limit away from home, the reading differed from the restore we had written, so the reconciler treated it as a change by hand and adopted it as a desire.
- **The adopted value blocked the next approach.** An adopted value holds until the next decision, and a routine policy pass is not one. So when the car came home, the policy's limit was not set on approach. It went out only at plug-in, after the car had already started charging, and the car then stopped.

Seen live: the car left at 17:29 with its limit restored, and the user set 100% while charging elsewhere at 18:14 ("charge limit set elsewhere to 100; adopted"). It parked at home at 21:03 with no limit sent, then charged for six seconds after plugging in at 21:05 before the 50% hold stopped it.

The fix: once a restore is satisfied, clear the desire as well as any held entry. A limit set while away then simply becomes the car's normal limit.

## Tests

- New: `test_a_restore_that_lands_clears_so_a_limit_set_away_is_not_adopted`. It fails without the fix.
- `test_a_restores_own_ble_reply_re_applies_nothing` asserted the leftover desire was settled. It now asserts the desire is gone, and still that only one command was sent.
- Unit suite (`--ignore=tests/API --ignore=tests/integration`): 2426 passed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
