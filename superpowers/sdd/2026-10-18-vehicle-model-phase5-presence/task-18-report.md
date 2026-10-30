# Task 18: a max that drops to 0 during a 00 run is an unplug

Commit **f5c6a769** on `vehicle-model/phase5` (parent 3b853066). Not pushed. Box untouched (read-only journal reads).

## Change (`TWCSlave.unplugStep`, lib +4)

- New class field `zeroMax`: the max on the heartbeat that began the current 00 run.
- `drop = zeroSince is not None and zeroMax and not reportedAmpsMax`: inside a 00 run, the max fell from > 0 to 0.
- The onset branch now also runs on `drop and getattr(self.offer, "amps", 0)`. In that case `before = ampsMaxBefore = zeroMax`, `zeroSince` is re-stamped to now, and `zeroMax` becomes 0, so it fires once. The existing early/grace/max checks follow, then the 60 s debounce branch, then `_plugSession(slave, False)` with its telemetry veto. All of this is unchanged.
- Log at INFO: `TWC 8244: during 00, max 47.00 A before, 0.00 A now: an unplug if it holds`. The onset text is unchanged, and `test_onset_logs_the_slave_max_amps` pins it.
- Serial thread: attribute reads and comparisons only.

## Guard finding: what `reportedAmpsMax` tracks

`reportedAmpsMax` is the TWC's echo of the master's offer. It is not the wiring max. Evidence from the box SHB log (protocol 2):
- 00:01:27: the master sends 46, and the slave reports 46 in the same second. 00:24:00: 48 → 48. Then back to 47 → 47.
- 12:14:06 → 07: the master moves from "no change" (offer = 47) to `09 00.00`. The slave goes 47 → **6**, not 0. A protocol 2 TWC with a car plugged floors a 0 offer at its 6 A hardware minimum.
- `M: 00` in the log means "no change". It is sent only when the offer equals the slave's max and is non-zero. So through 12:45:23–12:46:12 the offer was 47. The slave dropped to 0 at 12:46:12, and `M: 09 00.00` appears only at 12:46:14, after the drop. The box unplug passes the guard.
- The TWC reports max 0 only when it is empty (07:42–10:12, even with 6 A offered at 07:42:01) and for one plug-in transient heartbeat.
- `_amps_heartbeat`'s comment quotes a protocol 1 slave: `S 032e 0.25/0.00A: 03 0000 … M: 05 0000`. A v1 max follows a 0 offer to 0.

Conclusion: the guard is not needed on protocol 2. It is needed on protocol 1, where a policy drop to 0 during an awake 00 run would otherwise read as an unplug. **Kept.**
- It reads `self.offer` (what the heartbeat actually sends), not `lastAmpsOffered`, because `withdrawOffers` sets `offer = Offer(0, 0)` without touching `lastAmpsOffered`.
- A drop blocked by the guard keeps `zeroMax`. If the offer later rises and the max stays at 0, the drop counts then. If the car is there, the max follows the offer back up and no drop is seen.

## Tests (2175 → 2179; tests/unit + tests/EMS: 2179 passed, 1 warning)

New tests (`test_gen2_unplug.py` unless noted). The helper `box_unplug_inside_a_waking_00` sets a 32 A budget, then 03@47 for 60 s, then 00@47 for 49 s.
1. `test_a_max_that_drops_to_0_inside_a_waking_00_is_an_unplug`: a named car with no telemetry. At 50 s there is no unplug, and the "during 00" line is logged. At 70 s the unplug mark is made, the car is NOT_HOME and `twcVin` is None. **Red before.**
2. `test_an_unnamed_session_ends_at_a_max_that_drops_inside_a_waking_00`: an anonymous session is open at 50 s and gone at 70 s. **Red before.**
3. `test_presence.py::test_live_telemetry_plugged_vetoes_a_max_that_drops_inside_a_waking_00`: TeslaMate `pluggedIn True` means no unplug and `twcVin` is kept. It passes before the change by nature, since nothing fired then. With `telemetrySaysPlugged` patched to False it fails, so the veto is what holds it.
4. `test_a_waking_00_that_keeps_its_max_and_sleeps_again_is_never_an_unplug`: 00@47 for 600 s, then 03@6. A pin.
5. `test_a_max_following_our_own_0_offer_inside_a_00_is_never_an_unplug`: during 00@47 the budget goes to 0 (offer 0), the max follows to 0 for 300 s, then the budget and max return. No unplug. The rig is protocol 1 (`M: 05`), which matches the v1 behaviour. **Red with the guard removed.**

Moved test: `test_00_without_the_drop_on_the_first_00_heartbeat_is_never_an_unplug` is **INTENTIONALLY CHANGED** by the user's 2026-10-20 approval. Its second half, "the drop comes a heartbeat late" (00@47 then 00@0 → no unplug), is now an unplug by design. Its first half (00@47 for 600 s) is kept as test 4.

Black: clean on the three touched files.

## Parity
`test_command_path_parity.py` is untouched and passes. No count or timing moved. The box row holds max 47 through its 00 tail, so it has no drop.

## Lib delta
- `.py` lines: 26,338 → **26,342 (+4)**.
- `git diff --shortstat 3b853066 -- lib`: 1 file, +10/−6.

## Concerns
1. **Task 17 fallback widens to mid-run drops.** Re-stamping `zeroSince` at the drop means TWCMaster's fallback (`zeroSince == now and not (max or ampsMaxBefore)`) also fires when a mid-run drop is blocked only by link grace or a short plugged run. The anonymous session then closes at once, with no debounce, and the telemetry veto still applies. This is the same evidence the M1 ruling accepted for the onset. A drop blocked by the guard does not re-stamp, so the fallback doesn't fire for it.
2. **A protocol 2 miss.** While our offer is 0, the TWC's max sits at 6. An unplug then (6 → 0 during a 00 run) is held by the guard until the offer rises above 0. That is a missed unplug, not a false one. A telemetry feed still catches it.
3. The plugged-run check measures from the start of the non-00 run before the 00. The time spent awake at 00 therefore counts toward it at a mid-run drop.
