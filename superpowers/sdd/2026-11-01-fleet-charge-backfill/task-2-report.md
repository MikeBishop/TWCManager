# Task 2 report: ChargeLedger

Created lib/TWCManager/Vehicle/ChargeLedger.py and tests/unit/test_charge_ledger.py (12 tests, all brief names).
RED: with the module moved aside, `PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_charge_ledger.py` -> collection error (ModuleNotFoundError), 1 error.
GREEN: same command -> 12 passed. Full suite (--ignore=tests/API --ignore=tests/integration): 2599 passed, 1 xfailed.
Note: implementation was written before the RED run (module removed temporarily to show RED), not strictly test-first.

Design choices / concerns:
- observe returns True for any accepted snapshot that changed stored state (including open-session stamp advance), since the open state is persisted; False for stale/repeat or a non-Charging snapshot with no open session.
- Per-car "seen" stamp is persisted so stale snapshots are ignored after restart; it is dropped when a car has no segments and no open session at prune.
- Charging S where P or S energy is None: no segment written, open session advances to S (never invent energy).
- Closing snapshot with unknown energy or P.watts == 0: ends at P.stamp, nothing written.
- Segments with watts 0 are not stored.
- Lock is a leaf; live() is called outside it.
