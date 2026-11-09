# Task 7 report
Changed: docs/modules/Vehicle_TeslaAPI.md (new FAQ section before Troubleshooting, one entry); CHANGELOG.md (one Features line after the free-charge-state line, linking the FAQ).
Tag check: `git describe --tags --abbrev=0` -> v1.4.0; `git show v1.4.0:lib/TWCManager/Vehicle/Watch.py` -> fatal, path not in v1.4.0. Watch unreleased, so Features line, not Bugfixes.
Existing unreleased lines cover the watch and /api/getHistory generally, but none covers Fleet-only charge history, so I added the line.
No doc/changelog tests exist in tests/unit; none run.
Concern: FAQ anchor in the changelog link is GitHub-style slug of the heading.
