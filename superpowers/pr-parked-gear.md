**Title:** Count a parked car's empty gear as the end of its drive

A Fleet API read of a parked car reports no gear (`shift_state` is null). The car reports `P` only while it is in use. Presence marked a drive's end only on a `state` change or a gear of `P`. So when a car drove off reading `D` and its next read came back home with no gear, the drive never ended: the car stayed "leaving", and its policy charge limit waited for a plug-in. A Fleet-only car may never be read after that plug-in, so the limit could wait indefinitely.

This change counts an empty gear as parked when a moving car's read finds it home (`Presence.noteObservation`). It is one condition in `Presence.py`, plus a regression test in `test_command_path_parity.py` that replays the 2026-11-02 case: a Fleet-only car reads `D` as it leaves, then 20 minutes later reads home with no gear and is plugged in seconds later. The limit is set on that read with one `set_charge_limit` command.

Evidence: full unit suite (`pytest tests --ignore=tests/API --ignore=tests/integration --ignore=tests/scenarios`): 2620 passed. Running on the live box since 2026-11-03.

Changelog: none (the drive-end logic is not in a release yet)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
