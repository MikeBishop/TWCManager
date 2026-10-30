# Keep vehicle group membership and built-in groups consistent

Branch: MikeBishop:fix/vehicle-group-membership (a56bf27f, local only) -> ngardiner:main

Three bugs in the group actions on the vehicle and Vehicles pages, all present since the group interface came in with 1fdd781b / 0daa3b12 (April 2021), so in every release from v1.2.2 through v1.4.0:

- **Add to Group listed a car twice** on a double submit or a resubmit from the back button, and one Remove then took out only one copy. With Deny Charging, the car stayed blocked after the user removed it. Add now lists a car once; Remove takes out every copy, which also clears duplicates saved by earlier versions.
- **A group deleted since the vehicle page was drawn** raised `KeyError` and dropped the request with no response. It's now logged and changes nothing. A group name of digits, which `getFieldValue` turns into an int, now finds its group.
- **Delete never checked `Built-in`**: the page hides the link, but `/vehicles/deleteGroup/Deny%20Charging` removed the group, and `checkVINEntitlement` then raised `KeyError` until a restart recreated it. Built-in groups now get a 400.

The handlers move into `vehicleGroupMgmt()` and `deleteVehicleGroup()` beside the other vehicle-page helpers, with unit tests. CHANGELOG Bugfixes line.

Tested by unit tests, and on a live install: a double add, one remove, a missing group, deleting a built-in group, and deleting through the page's link, with settings.json checked at each step.

Separate from ngardiner/TWCManager#736 (Add Group), which it doesn't conflict with apart from the CHANGELOG line. If backported, the handlers are self-contained, but it won't cherry-pick cleanly onto release branches.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
