# Task 5 review (TeslaBLE provider, 607e6d1)

Spec compliance: PASS. Task quality: APPROVED (no Critical/Important findings).
Focused tests: 107 passed (test_teslable_provider, test_reads_no_wake, test_teslable_pairing_status).

Checked:
- Unproven seeded claims (upgrade boot, _claimKeyedVehicles/_claimUnproven) -> ready; refused drops claim / is never seeded -> not ready; keyless/anon (no vin) -> not ready.
- ready(): claims property under Vehicle leaf lock only; no settingsLock, no _bleLock, no I/O.
- ampsRange: (1, vehicleMaxAmps) never None for a ready vehicle; availableCurrent 0 falls through to wiring max; missing config -> (1, 32).
- canRead: for non-api_only users logic is identical to before (vin and claim); no new wakes or BLE timeouts. api_only now handled by order (concern 1, ruled).
- Names: TeslaBLEProvider, name/rank/local, module, readSource, ble.readSource, providers(), TeslaBLEReadSource.provider all exact. setAmps/wake call (int(amps), vin) / (vin) as briefed.

Concern 2 (inverted range if availableCurrent in (0,1)): Minor. Same rule as legacy vehicleMaxAmps; not new. Optional hardening: max(1, ...) in a later task.
Report lists only concerns 1-2 (no concern 3 present); the privKey-not-checked note is correct since claims are made only for keyed VINs.

Minor: ready() extra `capability not in CAPABILITIES` guard goes beyond brief but is harmless. Provider.readSource is None if binary missing, but module releases itself then, so providers() is not reached.
