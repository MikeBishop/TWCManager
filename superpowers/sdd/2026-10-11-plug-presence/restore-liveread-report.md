# Restore live-read fix report

Status: done. Nothing pushed; wt-plug left on deploy/presence-3.

Tips: presence/3-plug-presence b8b2fbd; presence/4-fleet-rate-queue (rebased, 13 commits) 44e9eef; deploy/presence-3 1535e71.
Full suite: presence/3 1158 passed; presence/4 1216; deploy 1386.

Change (b8b2fbd):
- ChargeLimitRules: ownWriteIsNewer(vehicle); telemetryChargeLimit(..., restore=False) returns None on a restore when our write is newer than the read; noteChargeLimitReadFor.
- TeslaBLE: restore passes restore=True, so current=None and it reads over BLE; _readChargeState stamps the vehicle (Minor 3).
- TeslaAPI: a restore whose own write is newer than the last read forces the live read, for any syncSource (including TeslaAPI, where update_charge may answer from a deferred/cached vehicle_data). A failed read sends nothing. Applies still use the written value.
Tests (fail before, pass after): TestRestoreReadsTheCarAfterOurWrite in TeslaBLE tests and in TeslaAPI tests (parametrized TeslaMateVehicle/TeslaAPI): apply 50, car hand-set to 90, telemetry 50 older than the write; restore reads live, sends nothing, saved becomes (90, -1). Plus a BLE _readChargeState stamp test. The TeslaAPI-source case was confirmed failing with the lib change reverted.

Merge: conflicts only in TeslaAPI.py and test_teslaapi_chargerate.py (slot-form areas); resolved by taking 8da7e41's versions and re-applying the presence/3 TeslaAPI diff. The +/- lines of git diff 8da7e41..deploy are byte-identical to git diff 8233d6b..b8b2fbd. git range-diff of the old and new presence/4: all 13 "=".

Concerns:
- Touched test files weren't black-clean before, so not reformatted. Trailer "Claude Opus 5.5" per global-constraints.md.
- _readChargeState now writes vehicle.chargeLimit from the BLE thread while telemetry may be live. Telemetry stamps only on change, so a lagging TeslaMate message with the pre-hand-set value counts as a change and re-stamps over the fresher BLE read. update_charge's BLE branch already had this exposure.
