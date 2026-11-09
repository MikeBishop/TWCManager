Wake a car for a limit raise once it would charge

On a Fleet-only install (no TWC on RS-485, no BLE, no TeslaMate), the midnight Scheduled Charging raise didn't wake the car, which was plugged in at home. The Vehicles page showed the raise "held: asleep" until morning. Two things combined.

**1. A stale unplug.** The car was last read unplugged when it left. Nothing on a Fleet-only install reads it back home and plugged in. The free cached snapshot does see it plugged in, but #742 rightly keeps snapshots out of plug evidence: a snapshot carries no location, and paired with an old home position it could place an away car on the home EVSE. So at midnight the car was still "not plugged in here", and the raise went out without a wake.

Now, a snapshot saying plugged in that is newer than the newest plug reading, when that reading says unplugged, leaves the plug state **unknown** rather than unplugged. It still places the car on no EVSE. The wake's own paid read settles where the car is, and a car that turns out to be away gets nothing.

**2. A hold that only the car could end.** Once a raise is held asleep, it waits for newer word from the car before trying again. But the reason it went without a wake was TWCManager's own judgment: "not plugged in here", or "no room to start" when the reconciler ran before the control tick had admitted the car. Reproduced live: every restart inside the schedule window hits that race. Where the vehicle watch owns the cloud checks, a sleeping car gives no new word, so the hold lasted all night.

An asleep hold always means its attempt went without a wake. It now plans again as soon as the car would be woken, so the next pass after admission sends the raise with its wake.

**3. A refused start that was already done.** With the raise applied, the car started charging on its own, and the `charge_start` that followed was refused. Through the Vehicle Command proxy, the refusal reads `car could not execute command: is_charging`. The cloud path only accepted a bare reason code, so it logged "error not accepted" and sent one more paid `charge_start` a minute later. It now reads the car's code after the proxy's prefix, as TeslaBLE already does, so "already charging" counts as done. v1.4.0 misread the same text, so this one gets a changelog line.

## Evidence

- **Unit tests:** 2,587 passed, 1 xfailed. New tests:
  - a proxy-wrapped `is_charging` refusal counts as satisfied, and wrapped free text is still not carried;
  - a cached plug-in after an unplug leaves the plug unknown, and never marks a plug-in;
  - end to end on a scripted Fleet car: read unplugged as it left, then a snapshot showing it plugged in; the raise sends one `wake_up`, the limit and the start;
  - end to end: the raise is held asleep on a pass that admits nothing, with the reconciler's own online check off (as when the watch owns it). It then sends the limit with one wake. This test failed with nothing sent before the fix.
- **Live box (Fleet only):**
  - Before the fix, the restart inside the schedule window logged "no wake because no room to start" and stayed held. That came from a box-only diagnostic line, which isn't in this PR.
  - After the fix, the same race re-planned in the same second, with a wake. The wake went out at 01:11:44 (after the 3-minute startup delay) and the limit was set at 01:12:04. The car started charging at 01:12:12 and stopped at its new limit at 01:34, after about 5 kWh at 48 A.
  - The proxy's log shows both `charge_start` refusals.

**Changelog:** one Bugfixes line, for the proxy reason. Fixes 1 and 2 get none: cached reads (#742) and the admission-based wake (#734) haven't been released.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
