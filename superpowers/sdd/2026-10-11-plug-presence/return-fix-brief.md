# Fix: restore/arrival race on return (live bug 2026-10-12 09:17)

## What happened on the box (deploy/presence-3 1d4258b, commandPolicy ble_only, one car, VIN-reading TWC, TeslaMate telemetry)

- 09:01:05 TWC unplug -> not_home -> BLE restore (limit -1 -> outside 100%) failed: car out of range; breaker opened.
- 09:07:28 BLE gone 307 s -> remote route -> "no remote command channel ... keeps 50% until it returns". Correct.
- 09:17:35, one presence pass:
  1. "Vehicle ... is in BLE range; retrying its restore" -> "unplugged; restoring its normal charge limit over BLE now" (restore queued).
  2. "presence: not_home -> home (a BLE plug read)" -> "arrived; applying charge limit 50" (apply queued).
- 09:17:40 TeslaBLE "Restored ... to charge limit 100%" (the restore ran first).
- 09:17:43 TeslaBLE "Charge limit for ...: already at 50%; nothing sent" — the arrival apply's read-before-write took TeslaMate's telemetry limit (still 50, 3 s after our own write). Saved became [50, 50]. The car was actually at 100% and charged past 50 (TeslaMate at 09:30: limit 100, charging, 58%).

## Fix 1 (root cause, must): read-before-write must not trust a telemetry limit older than our own last write

After any successful charge-limit write (apply or restore, any channel: TeslaBLE, TeslaAPI), record per VIN the value we set and the time. When the next read-before-write would use a telemetry value (`telemetryChargeLimit` / `needsLiveRead` path in TeslaBLE; the equivalent in TeslaAPI's decide/read path), and that telemetry value was received before our last write, use our written value instead (or force the live read; choose the simpler one that's correct: if the recorded write is newer than the telemetry sample, the written value is authoritative). Find where telemetry timestamps live (TeslaMate vehicle attributes / lastChargeState fetch stamps). Put the shared logic in the existing shared charge-limit rules module (ChargeLimitRules.py) so both channels use one rule.

Test (TeslaBLE + one for TeslaAPI): telemetry says 50 (sampled at t0); restore writes 100 at t1>t0; apply(50) at t2 must send 50. Telemetry updated to 100 after t1 -> also sends 50. Telemetry sampled after the write and equal to target -> nothing sent.

## Fix 2: arrival wins over a pending or retried restore

- The reconciler's "in BLE range; retrying its restore" must not queue a restore for a car that the same pass (or its fresh evidence) shows plugged in here. Order the pass so plug evidence is applied before held-limit reconciliation, or have the retry check `isPluggedHome`/fresh plug evidence first.
- If a restore is already running when arrival happens, the arrival apply must run after it with a live read (Fix 1 makes that read correct). Verify the queue key behaviour: arrival apply replaces a still-pending restore; a running one completes first.

Test: scenario replay of 09:17 in tests/unit/test_plug_presence_scenarios.py — car departs, BLE restore fails, BLE gone >300 s, ble_only so no remote; car returns, single pass yields both BLE reachability and a BLE plug read. Assert final saved == (outside, 50) and the last limit command the fake car received leaves it at 50 (fake car's limit == 50), and ideally no restore to 100 is sent at all. Also a variant where the restore is already running when arrival happens: end state car at 50.

## Check 3 (verify, fix only if wrong)

At startup the box logged "BLE: no configured vehicle is a charge candidate; charge rate not sent" x3: `broadcastVINs()` excludes the car the VIN-reading TWC names. Confirm the charge-rate reaches that car via the targeted (VIN) path when it's on the TWC. If no targeted path sends the rate to the car on a VIN-naming TWC, that's a bug: a broadcast's candidates should include the car the TWC itself names when the broadcast is for that TWC (or the caller should target it). Report what you find; fix with a test if broken.

## Branch work

Worktree scratchpad/wt-plug (on deploy/presence-3 1d4258b, clean). Never push; never git stash (shared); don't move other branches.
1. presence/3-plug-presence (6c61310): Fix 1, Fix 2 (+ Check 3 if it lives there), each its own commit, tests first. Full suite green.
2. Rebase presence/4-fleet-rate-queue (8f47928) onto the new presence/3 tip (`git rebase --onto presence/3-plug-presence 6c61310 presence/4-fleet-rate-queue`). Full suite green.
3. deploy/presence-3: `git merge --no-ff presence/4-fleet-rate-queue`; resolve keeping the slot-API form; full suite green; black only touched lib files; token-in-log grep clean.

Report to return-fix-report.md in this directory: commits, tests with fail-before evidence, Check 3 finding, branch tips, suite counts.
