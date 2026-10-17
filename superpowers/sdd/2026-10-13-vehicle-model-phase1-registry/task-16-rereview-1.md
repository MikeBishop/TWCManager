## Re-review, Task 16 fix round 1 (8e6c59a..2b91330)
1. All-digit input crash: ADDRESSED. HTTPControl.py addVehicleByVIN now uses str(vin or ""). Short int gives the format error; 17-digit int is accepted as well-formed (matches rule). Tested.
2. Test gaps: ADDRESSED. Numeric input, known-VIN add (user-asserted, one registry row), case-insensitive settings dedupe (existing lowercase key kept, data preserved) all added.
New breakage: none. 33 passed (test_vehicles_page + test_httpcontrol).
Residual Minor (pre-existing getFieldValue int coercion, not introduced here): an all-digit VIN with leading zeros loses them (int round trip) and gets the format error; all-zero gives None. Unrealistic for Tesla VINs; reading self.fields["vin"] raw would remove it. Not blocking.
Verdict: Approved.
