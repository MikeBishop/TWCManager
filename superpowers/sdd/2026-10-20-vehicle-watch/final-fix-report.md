# Final-review fix round: vehicle watch, fea5cb7c..9fa1d9eb

Branch vehicle-model/phase6 (scratchpad wt-vm6). Not pushed.

Commits:
- 01ed66fe Look for a car that left while believed asleep, and read on a door (Watch.py, watch tests, docs, CHANGELOG)
- 3b1e3c19 Look scan addresses up only for an asked car the scan missed (TeslaBLE M4)
- 9fa1d9eb Merge the watch line's duplicate branch and shorten plug session logs (size cuts)

Suite: 2344 passed, 1 xfailed (BASE 2337 + 7 new tests; one test replaced). Parity file untouched, its tests pass.
lib: 26930 -> 26941 (+11). Watch.py: 374 -> 392 (+18).

## Per finding

| Finding | Change | Test | Mutation |
|---|---|---|---|
| C1 | `_source`: the second-miss ping scans whatever the car last said (`scan=again`). `again` now comes from the last answer (MISS or TWICE). | `test_a_miss_while_asleep_records_nothing` replaced by `test_a_car_believed_asleep_is_scanned_for_after_its_second_miss`: first miss, no scan and no bleReach (one miss says nothing); second miss, one scan and bleReach False | restoring `and asleep(v) is False`: caught |
| I1 | The `_seen` memo carries `chargePortOpen`. A not-True to True edge asks for an exempt EVENT read. No `where == HOME` gate: only a ping answer writes the door, and an answer means BLE contact, which `decide` treats as HOME (the comment says so). | `test_a_charge_port_opening_on_an_awake_car_at_home_reads_it_once`: wake read, then door opens inside courtesy, one more read, none after | dropping `or door and not was[3]`: caught |
| I2 | No scan possible and a car at home: the second ping miss returns `TWICE` (status answer "no answer twice"). The next check goes to the cloud when the car has a TeslaAPI attachment. An awake car gets `readNow(..., exempt=False)` (courtesy-bounded EVENT). While the last check was TWICE, `_read` drops local providers, so the read goes through the cloud. Without this a BLE-paired car's read went to the radio that had just missed it. Asleep cars get no ask (their wake asks). Charging cars get no ask (their own reads run, also cloud-only while deaf). | `test_where_no_scan_can_run_two_misses_at_home_ask_the_cloud_and_read_once` (BLE-claimed Fleet car that has left): 2 pings, then a cloud check rather than a third ping, 1 paid read, presence NOT_HOME, 0 BLE reads | cloud switch removed: caught; ask removed: caught; local filter removed: caught |
| I3 | `loadSample`: an "up" step debounces per car by `sleepCourtesySecs`; "down" stays 300 s. | `test_a_flapping_load_reads_a_car_once_in_five_minutes` became `test_a_cycling_load_reads_a_car_once_a_courtesy_window` (1 read at 0, still 1 at 600, 2 at 1200) | 300 for both directions: caught |
| I4 | `secs = chargingReadSecs if local else cloudChargingReadSecs` (named or not). | `test_a_twc_named_car_read_through_the_cloud_waits_the_cloud_cadence` | `if local or named`: caught |
| M1 | A failed asked EVENT read settles as `RETRY` (`_fetch`/`_submit` take the miss answer). `_read` turns RETRY into an exempt EVENT want once `chargingReadSecs` has passed. The retry itself settles as MISS, so it runs once. | `test_a_failed_read_asked_for_is_tried_once_more_a_cadence_later` (Fleet 500): not every pass, a second paid read at 300 s, then none | retry removed: caught; "once" removed: caught |
| M3 | `pass_` skips anonymous cars. | `test_an_anonymous_car_is_not_visited` | caught |
| M4 | `heard = ... if asked - found else None`. Comment trimmed to 3 lines. | `test_a_scan_looks_addresses_up_only_for_an_asked_car_it_missed` (no `devices` run) | old `found != set(names)`: caught |
| M5 | New `_listen(v, where, ble, api)` returns "scan", "ble" or None. `_visit` and `status()` both use it, so `status()` passes the TeslaAPI attachment to `_scanSecs`. | `test_status_shows_the_scan_cadence_of_a_lost_car_with_a_cloud_attachment` | `_scanSecs(v, False, ...)`: caught |
| M6 | `watchLine`: the two "Not watched" branches are merged. | refactor only, existing page tests | n/a |
| M8 | Settings.md "Away, awake" row: "one location read per awake stretch, repeated at the return time while it is driving". | docs | n/a |
| M2, M7 | Accepted, unchanged. | | |
| M9 | Note only. C1 makes it compound less, because a car believed asleep that has gone is now found out of range and stops being pinged. | | |

Docs and CHANGELOG changed:
- Charge reads: door opening listed as a trigger and exempt from the courtesy wait; the failed-read retry.
- New paragraph on two missed checks: the scan, the away no-scan case, and at home the cloud check plus a courtesy-bounded cloud read.
- TWC-named car cadence by provider.
- Consumption step: rise once per `sleepCourtesySecs`, fall once per 5 minutes.
- Vehicle_TeslaBLE.md "No range scan": what happens at home without a scan, and that without a Tesla API connection a departure from a non-TWC charger is not detected.
- CHANGELOG lines updated to match.

## Size cuts
- 1 (watchLine duplicate): −2.
- 2 (minBatteryLevelAtHome): a shared Presence helper costs about +4 against −3 saved, so it was not done. TeslaAPI's body now takes the same 2-line form as HA's: −1. Both properties stay public because policies and docs name them.
- 3 (`_listen` shared by `_visit` and `status`): about net 0 against the old inline code, and it fixes M5.
- 4 (plug session warnings): the shorter message "Plug session update failed" fits one line with `exc_info` at both sites: −6. A wrapper would not save lines, because the second site guards a whole block.
- 5: skipped, as the review advised.
- Also: DEFAULTS repacked into 4 statements (−2).

## Concerns
- lib grows by +11 after the cuts. Watch.py grows by 18 lines for six behaviour fixes. The added I2 cloud-read routing cost 1 line.
- I2: a present car at home whose BLE is RF-dead (no scan, Tesla API attached, awake) gets one cloud EVENT read at most every `sleepCourtesySecs`, on a ping, ping, cloud cycle. That is the courtesy bound the user set, not the car's own sleep timeout.
- The I1 door edge has no HOME gate; the reason is in the comment. A door seen open on a car that `decide` still places away would ask a read. That should not happen, because a ping answer is BLE contact.
- `status()` calls `_source` without the last answer, so after a TWICE it still shows "via ble" while the next check goes to the cloud. This is display only.

## Re-review round (I2 repeat, status last answer, retry exemption)

Commit `git log -1` on the branch: "Read a car Bluetooth stopped hearing once, not every cycle".

- I2 once per loss: `Watch._unheard` holds the VINs already read for a loss. The TWICE ask fires only when the car is HOME_AWAKE and not yet in the set, and adds it. A ping that answers removes it. Test: `test_a_car_at_home_bluetooth_stopped_hearing_is_read_once_until_it_answers` runs 6 h of missed pings on a car that is present (Fleet at HOME) and expects exactly 1 paid read. After one answered ping and a fresh loss it expects a second read. Mutations: no set check (the old behaviour) is caught; no clear on answer is caught.
- status() fetches the last status and scan answers first and passes the status answer to `_source`, so after a second miss with no scan it shows "cloud". Test: `test_status_shows_the_cloud_after_a_second_miss_at_home_with_no_scan`. Mutation (no last answer passed): caught.
- M1 retry keeps the ask's exemption. RETRY is now a pair indexed by the exempt flag. A courtesy-bounded ask's retry waits for the courtesy window, because `lastRead` is the failure time. Test: `test_a_failed_read_the_courtesy_window_bounds_is_retried_within_it`: a failed wake read is not retried at 960 s but is at 1200 s, then not again. Mutation (always exempt): caught.
- Docs: Settings.md line 118 now says "once, until Bluetooth answers again". The retry sentence and Vehicle_TeslaBLE.md were updated to match.
- Suite: 2347 passed, 1 xfailed. lib 26941 -> 26956 (+15). Watch.py 392 -> 407. Parity file untouched; its tests pass.
