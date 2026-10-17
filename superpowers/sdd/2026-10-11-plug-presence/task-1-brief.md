### Task 1: Create the branch and carry over the surviving commits

**Files:** none edited by hand.

**Interfaces:**
- Produces: a branch whose tree equals `presence/4-arrive-depart` except `lib/TWCManager/VehiclePresence.py` and `tests/unit/test_vehicle_presence.py`. Those two stay at the version branch 3 had, without the telemetry-limit fill. Verified in a probe: 958 passed.
- Invariant for later tasks: the carried code calls these presence methods, and Task 2 must provide each with exactly this signature: `nominate(vin, reason, delays=(0,))`, `observeContact(vin, reachable, probe=False)`, `observeProof(vin, source)`, `observeUnplug(twc, vin, excluded=frozenset())`, `observePlug(twc, vinReading=False)`, `observeTelemetryPlug(vin, pluggedIn)`, `observeLocation(vin, atHome)`, `state(vin)`, `start()`, `stop()`. The suite is green after this task only because the callers are mocked.

- [ ] **Step 1: Create the worktree and branch**

```bash
git worktree add -b presence/3-plug-presence <scratch>/wt-plug presence/2-charge-limits
```

- [ ] **Step 2: Cherry-pick branch 3 minus the telemetry-limit fill (17 commits, all clean in the probe)**

Skipped: `f939ff8` and `490c7cb`. Their effect is removed again by `b3c692a`.

```bash
git cherry-pick 7277dd0 a73d5b3 ceacea0 15d6805 2cebb08 0972265 27a5e1f 93e6104 3b83505 b0ddcdf 7594e70 bb5837c b8e55a0 d4055ae 8cf363e a2855bb c7d4cf1
<PY> -m pytest tests/unit -q   # expect 905 passed
```

- [ ] **Step 3: Cherry-pick the branch-4 commits without their tracker hunks, in this order**

For each SHA in `c274d6c fada5b4 df426ed 07c06b2 7e9ca95 b3c692a 66acf97 87bb011 05437b7 11753a9 4c5a008 32d798a 94cf1c5`:

```bash
git cherry-pick -n <sha>
git checkout HEAD -- lib/TWCManager/VehiclePresence.py tests/unit/test_vehicle_presence.py
git commit -C <sha>          # "whole" rows below
git commit -F <msgfile>      # "partial" rows: message below
```

| SHA | Kind | Message |
|---|---|---|
| c274d6c | partial | original message, plus the paragraph below |
| fada5b4 | partial | subject `Add the departing handler: restore the limit over BLE on unplug`, original body, plus the paragraph below |
| df426ed, 7e9ca95, 87bb011, 11753a9, 4c5a008, 94cf1c5 | whole | `-C` |
| 07c06b2, b3c692a, 66acf97 | partial (only a tracker-test hunk or tracker comments dropped) | original message, plus the paragraph below |
| 05437b7 | partial | subject `TWC plug evidence says whether the TWC reads VINs`, original body, plus the paragraph below |
| 32d798a | partial | subject `Add CarApiVehicle.pluggedIn and a live-telemetry plug lookup`, original body, plus the paragraph below |

The paragraph to add, inserted before the trailer: `Carried without its VehiclePresence part; the plug-presence tracker replaces that.` The message must end with the original trailer and then the `Co-Authored-By: Claude Opus 5.5` line, if the original trailer isn't already that line.

Not carried at all, because the new tracker replaces them: `045160f 443b181 8764711 6805b0b b0a86f9 0b46958`.

- [ ] **Step 4: Verify the carry**

Run: `<PY> -m pytest tests/unit -q` → `958 passed`.
Run: `git diff --stat presence/4-arrive-depart` → only `lib/TWCManager/VehiclePresence.py` and `tests/unit/test_vehicle_presence.py` are listed.

---

