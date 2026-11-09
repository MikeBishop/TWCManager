# Task 1 report: Observe charge_energy_added

Status: DONE_WITH_CONCERNS (see concerns)
Commit: b166b8f6 feat: observe the Fleet session energy (charge_energy_added)

## What was done

1. TDD RED: appended `test_a_snapshot_carries_the_session_energy` to tests/unit/test_watch_cached.py.
   Command: `PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch_cached.py::test_a_snapshot_carries_the_session_energy`
   Result: failed with `AttributeError: 'NoneType' object has no attribute 'value'` (latest("chargeEnergyAdded") was None).
2. Implementation (three one-line changes):
   - lib/TWCManager/Vehicle/Registry/Fields.py: `"chargeEnergyAdded"` added to FIELDS after `chargeCurrentRequestMax`, with a comment (battery-side kWh, the car's own count).
   - lib/TWCManager/Vehicle/Providers/Capability.py: `"chargeEnergyAdded"` added to CHARGE_FIELDS. The cached and paid Fleet providers enumerate CHARGE_FIELDS (FleetCachedProvider = CHARGE_FIELDS - {"phases"}, FleetAPI/Owner = CHARGE_FIELDS | LOCATION_FIELDS), so both get the field.
   - lib/TWCManager/Vehicle/TeslaAPI.py `_observeCharge`: `("charge_energy_added", "chargeEnergyAdded")` added to the mapping tuple.
3. Test update forced by the new field: tests/unit/test_registry_fields.py `test_constants` asserted `len(FIELDS) == 30`; changed to 31.
4. GREEN, related files: `PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch_cached.py tests/unit/test_registry_fields.py tests/unit/test_provider_tables.py tests/unit/test_teslaapi_providers.py` -> 150 passed.
5. Full suite (once): `PYTHONPATH=lib .venv/bin/python -m pytest -q --ignore=tests/API --ignore=tests/integration` -> 2586 passed, 1 xfailed, 1 warning in 305s (baseline 2585 passed + 1 xfailed; +1 is the new test).

## Files changed (commit b166b8f6)
- lib/TWCManager/Vehicle/Registry/Fields.py
- lib/TWCManager/Vehicle/Providers/Capability.py
- lib/TWCManager/Vehicle/TeslaAPI.py
- tests/unit/test_watch_cached.py
- tests/unit/test_registry_fields.py

## Deviations from the brief
- The brief's Files list named lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py for the provider FIELDS. No edit there was needed: the providers derive FIELDS from Capability.CHARGE_FIELDS, so the field went into Capability.py instead.
- The brief's test used `m.getModuleByName("TeslaAPI")` as written; it works (no adaptation needed).
- test_registry_fields.py was not in the brief's file list; its hard-coded count had to change.

## Concerns
- Commit attribution: common.md asks for `Co-Authored-By: Claude Opus 5.5`, but the session's attribution reminder says Haiku 5.5. I followed the session reminder (Haiku 5.5). Amend if Opus 5.5 is wanted.
- The test asserts only the value and stamp, not the source ("FleetAPICached"); the brief did not ask for it.
- Not pushed; .superpowers/ files other than this report untouched.

## Fix round 1 (review: BLE claimed chargeEnergyAdded without supplying it)

Commit: see `git log --oneline -1` after b166b8f6 (subject: fix: read the session energy over BLE too)

Change:
- lib/TWCManager/Vehicle/TeslaBLE.py `get_charge_state`: `"chargeEnergyAdded": cs.get("chargeEnergyAdded")` added beside the other keys. TeslaBLEProvider.FIELDS (CHARGE_FIELDS | LOCATION_FIELDS) is unchanged, so BLE now supplies the field it claims.
- The JSON key is inferred from the protojson camelCase convention used by the neighbouring keys (chargerActualCurrent, chargeLimitSoc). No BLE fixture or proto in the repo carries it, and a search of local caches found nothing, so this is UNVERIFIED against a real `tesla-control state charge` output. I found no evidence BLE cannot carry it, so I did not exclude it from the provider.
- tests/unit/test_teslable_pairing_status.py: `test_charge_read_reports_the_session_energy` (BLE charge read returns the key and observes chargeEnergyAdded through the provider fetch).
- tests/unit/test_watch_cached.py: now also asserts `obs.source == "FleetAPICached"`.

TDD RED: `pytest tests/unit/test_teslable_pairing_status.py::test_charge_read_reports_the_session_energy` -> `KeyError: 'chargeEnergyAdded'`.
GREEN subset: `PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_teslable_pairing_status.py tests/unit/test_teslable_provider.py tests/unit/test_watch_cached.py tests/unit/test_ble_jobs.py tests/unit/test_registry_fields.py tests/unit/test_teslaapi_providers.py` -> 183 passed.
Full suite: `PYTHONPATH=lib .venv/bin/python -m pytest -q --ignore=tests/API --ignore=tests/integration` -> 2587 passed, 1 xfailed, 1 warning in 305s.
