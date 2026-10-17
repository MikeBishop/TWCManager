# Task 5 report
Status: DONE. Commit 6a76b2e on vehicle-model/phase1. 856 passed.
RED was verified retroactively (collection ModuleNotFoundError with ReadSource removed), not before implementing.
Added ReadSource.py (ReadSource, cascade), Vehicle.read, test_registry_read_cascade.py (brief's 6 tests + raising source, {} result, no-registry).
Concerns:
- Modified tests/unit/test_registry_vehicle.py: removed the "read is a stub" assertion (renamed test).
- cascade does not sort by order; registry.readSources() must return sorted.
- canRead is inside the same try as fetch (a raising canRead is skipped); brief only specified fetch.
- Source exceptions are logged at DEBUG with traceback; Fleet/BLE sources must keep tokens out of exception text.
- read() does latest() then age() under separate lock acquisitions; harmless race.
- Brief's allowWake test relies on wall-clock advance with maxAge=0 (real time.time).

## Fix round 1
Items 1-6 done (tests 1-3 shown failing first: 4 failed, then green). 860 passed. Fetch exceptions log type name and source name only. read() treats a value as fresh only if trusted() accepts it. A result lacking the field moves to the next source (observations still recorded; {} counts as self-written if latest exists). allowWake test uses maxAge=-1. The lock check records a flag asserted after the read (asserted in the stale-cascade test only).
