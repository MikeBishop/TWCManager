### Spec Compliance
Matches the brief and controller rulings. Focused run: tests/unit/test_vehicles_page.py + test_httpcontrol.py, 30 passed.
- Template: registry table (VIN link / anonymous "Unknown car on TWC <point>" unlinked, Name, Tier, Providers, Last seen, Held limit), "Charge history" retitle, form, red error. vehicles.html.j2.
- ageText, heldLimitText (VIN then TeslaAPI numeric ID; found/applied rendering), addVehicleByVIN (format check, upper-case, user-asserted, settings entry under settingsLock with case-insensitive check, scanForVehicles outside the lock, saveSettings, redirect), /vehicle/add route, addVehicleError set before webroutes loop, globals ageText/heldLimitText/registry: HTTPControl.py:25-68, ~257, ~1237, ~1580.
- Key generation traced: scanForVehicles (TeslaBLE.py:906) fills privKey/pubKey/pubKeyPEM for every settings["Vehicles"] entry lacking privKey; peerWithVehicle -> _settingsKey (case-insensitive) -> sendPublicKey uses that entry. New VIN is stored upper-case, so pairing is possible. No TeslaBLE module: getModuleByName None, scan skipped, entry still created (keys generated later when BLE starts).
- Page with no TeslaAPI module / anonymous vehicles: heldLimitText skips VIN lookup when vin falsy, attachment() returns None safely; anonymous rows render via row.point. Escaping test covers name and error (autoescape on).
- Lock order: addUserAsserted (registry lock, released) -> settingsLock -> released -> scanForVehicles. No nesting inversion.

### Strengths
- Small pure helpers, testable without HTTP; error redirect carries only the fixed ValueError message; Location is built from a validated ASCII VIN, so no header injection.
- Escaping test; idempotent duplicate add (one registry row, one settings entry).
- Error text is reflected only through autoescape; spoofable red text via crafted ?error= is within the app's existing posture (no CSRF tokens anywhere).

### Issues
Critical: none.
Important: none.
Minor:
1. HTTPControl.py:48 `(vin or "").strip()` crashes with AttributeError for an all-digit 17-character input: getFieldValue (HTTPControl.py:1659) returns int for numeric strings. Reproduced: addVehicleByVIN(m, 12345678901234567) raises; the handler thread dies with no response. Nothing is mutated, but it is a garbage-input robustness hole. Fix: `str(vin).strip()` when vin is not None, or read self.fields["vin"] directly.
2. Adding an already-known VIN (observed by TWC/API/BLE) sets userAsserted=True, so it never expires (VehicleRegistry.py:122, expire skips it). This is consistent with "user-asserted, never expires" and arguably right (the user explicitly listed it), but it is silent and irreversible until Phase 6 Forget; worth a one-line note in the changelog/page text.
3. Lowercase input is upper-cased and accepted (tested). A pre-existing settings entry under a different case is detected and not duplicated; fine.
4. Test gaps (non-blocking): no test for the numeric-input case, nor for a known-VIN add, nor for case-insensitive settings-key dedupe.

### Assessment
**Task quality:** Approved
**Reasoning:** All spec items, rulings and lock ordering are met, pairing for a new VIN is traceable end to end, and rendering is safe with no TeslaAPI and with anonymous vehicles. The only real defect is the minor numeric-field crash in the POST path, which should be fixed opportunistically but does not undermine trust in the task.
