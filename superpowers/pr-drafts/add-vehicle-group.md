# Make Add Group on the Vehicles page create the group

Branch: MikeBishop:fix/add-vehicle-group (ee7851b5, local only) -> ngardiner:main

Add Group on the Vehicles page has never worked: the form posted to `/vehicle/group`, which no route handles, and its two inputs had no `name`, so nothing reached settings.

The form came in with 1fdd781b (April 2021), so every release from v1.2.2 through v1.4.0 has the bug; no release ever handled `/vehicle/group`. If it's worth backporting, the fix doesn't cherry-pick cleanly onto v1.4.0 or release/1.3.4, because the neighbouring routes and tests it sits beside are newer. It would need a hand port: the handler and form change are self-contained.

- The form posts to a new `/vehicle/addGroup`, which saves the group with its description, no members, and `Built-in: 0`, then saves settings.
- A blank name, a name containing `/`, or a name already taken redirects back with an error shown above the form. `/` is refused because Delete reads the group name from the last segment of its URL path.
- The Delete link URL-encodes the group name, so a name with `?` or `#` (which Add Group now lets through) can still be deleted.
- CHANGELOG Bugfixes line.

Tested by unit tests, and on a live install: add, then a duplicate, then a name with `/`, then Delete, with settings.json checked at each step.

This touches the same Add Group form markup as ngardiner/TWCManager#735, so whichever merges second needs a small rebase.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
