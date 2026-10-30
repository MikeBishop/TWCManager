# Task 3 review: WatchBudget (1388b3e0)

Spec compliance: PASS. Quality: PASS with fixes.

Rules verified: rate monthly/(30*86400); cap one day; EVENT may spend to zero; ROUTINE keeps floor*capacity;
price<=0 always succeeds and refreshes the stamp; restart keeps stored tokens and refills for elapsed time via
the stored stamp; malformed/None load starts full; settings persisted under settingsLock beside vehicleRegistry,
loaded outside the lock like the registry. NaN/inf/list/str blobs load safely.

## Findings (ranked)
1. Log flag flaps (real bug, small). One `_empty` flag is shared by both classes. ROUTINE hits the floor ->
   "exhausted"; the next EVENT succeeds -> "available again" (bucket still under the floor); the next ROUTINE
   fails -> "exhausted". Logs alternate on mixed traffic, so "once" does not hold. Fix: key the transition on
   the class that failed (a dict/pair of flags, +2 lines) or log only for ROUTINE (the floor is the normal
   steady state). Or drop the log from the bucket (finding 5).
2. No lock; spend() is a read-modify-write called from BLE/cloud workers and the tick. Two concurrent spends can
   both read the same tokens and one write is lost (overspend by one price, ~$0.002), and toJSON can pair
   _tokens with a different spend's _at. Harm is small but cheap to remove: one threading.Lock held in
   spend/load/toJSON (+4 lines: import, init, three `with`s net ~+4). It is a leaf lock (spend only logs), so
   settingsLock -> budgetLock from saveSettings is safe; never call settingsLock from inside it.
3. Future stamp stalls refill. Clock step back is handled in spend (stamp rebased, nothing minted/destroyed
   beyond the step), but tokens() alone never rebases, and a loaded `at` ahead of now (saved with a fast
   clock, or restart after a backward NTP step) freezes refill until the clock catches up. Cheap fix in
   load(): `at = min(at, self._clock())` (+0 lines if folded into the final assignment). Forward steps
   mint at most a full day-cap: acceptable.
4. Epsilon 1e-9: keep. Integer micro-dollars would not remove it, since the refill rate (1.157 uUSD/s for $3)
   is fractional so tokens stay float anyway. The drift (0.1 - 49*0.002 lands just under 0.002) only matters
   for "bucket exactly holds the price", which is harmless in production but needed by the brief's tests (the
   refused 50th read leaves 0.002 behind and breaks the 0.1/24 +-0.001 assertion). Well-scaled for dollars, and
   the comment gives the why. Side effect: EVENT can leave tokens at -1e-9; harmless.
5. Size cuts (62 -> ~48-56):
   - Collapse the 9-line log call to one line, `logger.info("Paid-read budget %s", ...)`, dropping the
     tokens/capacity numbers: -6.
   - If the log-once flag is dropped (callers log skip decisions anyway; also fixes finding 1): flag init, the
     whole `if price > 0 and ok == self._empty` block, logging import + logger + EVENT-comment spacing: -14.
     Spec text asks for it, so this is the controller's call.
   - `max(price, 0.0)` in the subtraction is redundant for price>0; `tokens -= price if ok and price > 0`
     is no shorter, so ~0 saved. Leave.
   - Docstring-ish comments are all why-comments; none to cut. `_refill` returning a tuple is slightly awkward
     but inlining it into spend and tokens duplicates 2 lines; keep.
6. Comments: obey the rule (why, no history/IDs). "Anything but two numbers starts full" is a what; harmless.
7. Not wired: nothing marks settings dirty on spend, so persistence relies on the existing periodic/event
   saveSettings (50 call sites, a queued "saveSettings" task). A crash between saves restores a slightly fuller
   bucket; acceptable. Consumers (later tasks) need no extra save call.
8. Test nit: round-trip test mocks getModuleByName and copies config; fine. No test for clock-backwards or
   ROUTINE-below-floor-after-load; add one clock-back assert if finding 3 is taken (+3 test lines).
