# Task 13 report: deploy/presence-3

**Status: DONE**

The worktree is `.../8798f608-.../scratchpad/wt-plug`, on `deploy/presence-3`, with a clean tree. Nothing was pushed. These branches were left untouched:
- presence/4-fleet-rate-queue: 14ae080
- feat/token-slots: fe764ff
- deploy/presence-2: 92dae4d

## Commits

- `a8ef9cb` **Merge feat/token-slots (#692) into deploy/presence-3**
  - Parents: 14ae080 and fe764ff.
  - It had 5 conflict hunks, all in TeslaAPI.py. They are resolved as deploy/presence-2 resolved them.
  - One addition on top of that: presence's new atHome wake gate, without the `lat != 10000` exemption.
- `3b7fdd0` **Port the plug-presence code to the Tesla API token slots**
  - It starts from a cherry-pick (`-n`) of 92dae4d. The only conflict was in test_vehicle_presence.py, a class the presence stack had already deleted, so that file keeps HEAD's version.
  - It also ports the sites the presence stack added after 92dae4d:
    - the scenario World and FakeFleet
    - TestChargeTargets and TestWakeOnlyForAHomeCar
    - one test in test_teslable_presence
  - It adds `TestDeployRegression20261011`, which has 3 tests.

The details are in `.superpowers/deploy-presence-3-merge-report.md`.

## Gate outputs

```
$ <PY> -m pytest tests/unit -q
======================= 1330 passed, 1 warning in 6.75s ========================
$ <PY> -m pytest tests/unit/test_plug_presence_scenarios.py -q
============================== 19 passed in 0.57s ==============================
   (16 existing scenarios, assertions unchanged, + 3 deploy regression tests)
$ <PY> -m black --check TeslaAPI.py PresenceSources.py PresenceHandlers.py \
    test_plug_presence_scenarios.py test_presence_handlers.py \
    test_teslaapi_chargerate.py test_presence_sources.py
All done! 7 files would be left unchanged.
$ git log --format="%h %p %s" -2
3b7fdd0 a8ef9cb Port the plug-presence code to the Tesla API token slots
a8ef9cb 14ae080 fe764ff Merge feat/token-slots (#692) into deploy/presence-3
$ git status --short
(empty)
```

**Baseline counts:**
- presence/4-fleet-rate-queue alone: 1160 passed.
- feat/token-slots alone: 764 passed.
- At the merge commit: 1323 collected, 59 failed. All 59 come from token setup through removed accessors, in three files:
  - scenarios: 11
  - chargerate: 11
  - teslaapi_presence: 37

**Test-ID check:** no test was dropped.
- Every collected node ID on presence/4 and on feat/token-slots is also collected on deploy/presence-3.
- `comm -23` prints nothing for both.

**Leftover-accessor grep (the brief's command):**
- It prints only `slot.baseURL` uses (the new slot attribute), FakeFleet's `baseURLs`, and the settings.html.j2 form field.
- With those filtered out, it prints nothing.
- `\.(carApiBearerToken|carApiRefreshToken|carApiTokenExpireTime)\b` also prints nothing.

**Token-in-log check:** I ran `git diff presence/4-fleet-rate-queue -- lib | grep -nE '^\+.*log.*(oken|Bearer)'`.
- It finds 8 hits, all in token-slot code that came in with the merge. None interpolates a token.
- The port commit adds 0 hits.

**Startup sanity script** (no network): the results match deploy/presence-2.
- With an Owner token saved as synced, the read slot is Owner, there is no command slot, and `readOnly` is True.
- It made 0 network calls.
- The one import failure is SolarEdge, which is a venv pymodbus problem in this environment.

**Mutation check:** I reverted `hasRemoteChannel` to `slotFor("read")`. `test_fleet_fallback_restore_needs_a_command_slot` then fails.

## Concerns

- **The brief's leftover grep can't print nothing as written.** `\.baseURL` now matches the legitimate `slot.baseURL`, so the check above uses the filtered form.
- **One existing test was passing for the wrong reason.** `test_teslable_presence::test_policy_wide_apply_skips_departing_on_every_channel` only passed after the merge because a stale `carApiBearerToken` made TeslaAPI read-only. It now stores a Fleet token, so it tests the real skip.
- **Things to watch on the box**, carried over from presence-2 (listed in the merge report):
  - an Owner-only token means TeslaAPI is read-only and there is no remote restore;
  - `/products` for the online read;
  - the first-boot order of token sync;
  - the Fleet wake gate follows presence: a car with no location fix is presumed home and IS woken; only DEPARTING/NOT_HOME cars are skipped;
  - the token-slots charge_start/stop and wake_up POSTs have no timeout.

## Fix round 1

**Commit:** `cce331f` Make the TeslaAPI away-skip and no-fix wake tests discriminate. It is a new commit on deploy/presence-3; a8ef9cb and 3b7fdd0 are unchanged.

**What changed:**
1. `test_teslable_presence::test_policy_wide_apply_skips_departing_on_every_channel` now makes the TeslaAPI car `ready()`, gives it a readable `update_charge`, and sets `chargeLimit = 80`. It used to stop at "vehicle not ready" before the skip.
2. `TestDeployRegression20261011::test_departing_car_inside_radius_gets_nothing_on_any_channel`: the policy moves to 60% while the car is departing. The car still holds 50%, and TeslaMate reports it live, so the read does not short-circuit the apply.
3. New test: `test_teslaapi_presence::TestWakeOnlyForAHomeCar::test_presumed_car_with_no_location_fix_is_woken`, adapted from the reviewer's probe. It uses a real CarApiVehicle (lat 10000, raw atHome False) and a real tracker with no evidence. The car is PRESUMED, and `car_api_available(charge=True)` wakes it over the Fleet API.
4. Wording: the merge report's watch item and the concern above now say that a car with no fix IS woken while presumed. The no-timeout item now covers both the charge_start/stop and wake_up POSTs.

**Mutation proofs.** I ran them in a scratch copy: `scratchpad/mut`, built by `scratchpad/mutrun.sh` from `git ls-files` with a mutated TeslaAPI.py. I did not use stash, and the worktree was never mutated.

Mutation A: TeslaAPI.applyChargeLimit's `if vin is None and not vehicle.atHome:` replaced by `if False:`.
```
test_teslable_presence -k skips_departing: unmutated 1 passed; mutant 1 failed
test_plug_presence_scenarios -k Deploy:    unmutated 3 passed; mutant 1 failed, 2 passed
  FAILED ...test_departing_car_inside_radius_gets_nothing_on_any_channel[fleet_command]
  E   Left contains one more item: ('5YJ3E1EA1KF000001', {'percent': 60})
```
- The `owner_read_only` case still passes under mutation A. That is expected, because a read-only API refuses before the skip.
- The other test that still passes is `test_fleet_fallback_restore_needs_a_command_slot`, which is guarded by the `hasRemoteChannel` mutation instead.

Mutation B: the wake gate's `if not vehicle.atHome:` replaced by `if not vehicle._locationAtHome:` (raw location instead of presence).
```
test_teslaapi_presence -k no_location_fix: unmutated 1 passed; mutant 1 failed
```

**Gates:**
```
$ <PY> -m pytest tests/unit -q
======================= 1331 passed, 1 warning in 7.53s ========================
$ <PY> -m black tests/unit/test_plug_presence_scenarios.py
1 file left unchanged.
```
- I ran black only on the scenario file, which was black-clean.
- test_teslaapi_presence.py and test_teslable_presence.py were not black-clean before, so they were not reformatted. Black would change none of the lines I added.

**Carry back to presence/3-plug-presence (3e20776) before PRs open:**
- **The test_teslable_presence and test_teslaapi_presence hunks of cce331f.** They need no token slots.
  - On presence/3, the teslable test keeps `api.carApiBearerToken = "token"` instead of `storeToken(fleet_token())`.
  - Add the `ready` / `update_charge` / `chargeLimit` lines and the new no-fix wake test as written.
  - Check the no-fix wake test on presence/3: it relies on `_wake_api` and `make_api` setting up a non-read-only API there.
- **The 60% policy change, applied to `test_2026_10_11_unplug_ble_silence_inside_radius_policy_cycles_send_nothing`.** It has the same blind spot: the car already holds 50%. It should get the same change on presence/3 (and in turn presence/4). I left it unchanged on this branch because its assertions were to stay as they were for the deploy port. TestDeployRegression20261011 covers the gap here.
- The TestDeployRegression20261011 hunk itself is deploy-only. It depends on token slots.
