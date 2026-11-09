# The user's rules for docs and changelog (binding)

Docs are for users and installers, not developers.
- An improved implementation of existing behavior is not a feature; mention it only through its user-visible effect.
- Setup actions and "why does X happen" answers belong in an FAQ, not a feature list.
- Say what the user must do and why. No internal names (registry, provider, reconciler, watch, ledger, snapshot poll, charging point, tier) in user prose.
- A "charger" is the car's onboard component; say "EVSE" or "charging station" for the wall unit.
- Version markers such as "(1.4.1)" only on new capabilities a user can use.

Changelog:
- 1-2 sentences, starting with an imperative verb ("Add", "Fix", "Show"); details live in docs, link them. Keep the existing `(@author) - ` prefix format used by neighboring lines.
- A Bugfixes line only for a bug present at the last release tag. Check with `git describe --tags --abbrev=0` and `git show <tag>:lib/TWCManager/Vehicle/Watch.py` (does the TWC-less/cloud-only watch exist there?). If the watch for cars no TWC names was not in that release, this is part of unreleased feature work: one Features line at most, or none if an existing unreleased line already covers Fleet-only charge history — then say so in your report.
