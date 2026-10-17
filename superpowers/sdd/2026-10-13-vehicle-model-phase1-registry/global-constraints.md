## Global Constraints

- Nothing blocks or delays the RS-485 heartbeat loop: registry calls made from the serial thread (`TWCMaster.num_cars_charging_now`, `recordVehicleVIN`, `TWCSlave`) are dict operations under short locks; `Vehicle.read()` (which may do I/O) is never called from the serial thread or an MQTT callback thread.
- Lock order: `TeslaBLE._bleLock` → `master.settingsLock` → `VehicleRegistry._lock` → `Vehicle._lock`. Registry and vehicle locks are leaves: never call a module, take `_bleLock`, or do I/O while holding one. No lock is held across I/O (the read cascade releases locks before calling a source; `saveSettings` serialises under the lock and writes outside it).
- `config.json` and `settings.json` stay backward compatible: no existing key changes meaning; new keys are optional (`vehicle.forgetAfterDays`, `settings["vehicleRegistry"]`, `settings["Vehicles"][vin]["ble"]`); an old `settings.json` without them loads unchanged.
- Python 3.8 syntax floor: no `X | Y` unions, no `dataclass(slots=True)`, no `match`; use `typing.Optional/Dict/List`.
- `black` only on files you touched (`black <file>`); the repo venv's black reformats untouched files, so never run `black .`.
- Tests: `python -m pytest tests/unit -q` must pass after every task.
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (the two cherry-picked commits in Task 1 keep their original trailer; do not amend them).
- No log line may contain a token (access, refresh, HA long-lived, BLE private key).
- `settings["Vehicles"]` (charge sessions, kWh, BLE keys) is session history / key storage, never registry membership: session stats never create or keep a vehicle. The one reader is TeslaBLE's `updateSettings` (Task 13), which turns stored BLE keys into claims (ruling P9).
- Docker `:latest` tracks main: every task leaves a pure-Gen2 install working (no Vehicle module loaded).

## Review Focus
