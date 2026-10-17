# Task 3 report
Status: DONE. Added lib/TWCManager/Vehicle/Registry/{__init__,Fields}.py and tests/unit/test_registry_fields.py. Tests written first (collection failed on missing module), then implemented per brief. Black clean. tests/unit: 829 passed.
Notes: NOT_TRACKED is a module-level sentinel and also a FieldStore class attribute. noteWrite also rejects unknown fields (KeyError). trusted() returns None when nothing observed. Feed-lag exemption needs strictly > FEED_LAG. Extra tests cover constants and edge cases.
Concern: trailer follows global-constraints.md (Claude Opus 5.5) although the session model was Sonnet 5.5.

## Fix round 1
observe/noteWrite now share _store(): an older `at` never displaces a newer stored one (the kept entry is returned; equal `at` replaces), and the clock is read inside the lock when `at` is None. Tests added first (3 failed), then passing. Suite: 833 passed.
