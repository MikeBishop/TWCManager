Move the base and minor Docker tags with each release

The release job pushes only the exact tag (`twcmanager/twcmanager:<ref>`). As a result:
- A post release such as `v1.3.4.post1` leaves everyone pinned to `v1.3.4` on the image it replaces.
- No tag follows a minor line, so pinning `v1.3` isn't possible.

Each release now also pushes:
- **its base version:** `v1.3.4` for `v1.3.4.postN`;
- **its minor line:** `v1.3`, but only when it is the newest base version in that line (checked against the repo's tags). A late post release of an older patch can't move `v1.3` backward.

I ran the tag logic against the repo's real tags:

| release | tags pushed |
|---|---|
| `v1.3.4` | `v1.3.4`, `v1.3` |
| `v1.3.4.post1` | `v1.3.4.post1`, `v1.3.4`, `v1.3` |
| `v1.3.3.post1` | `v1.3.3.post1`, `v1.3.3` |
| `v1.4.0` | `v1.4.0`, `v1.4` |

I also ran the step's script as extracted from the YAML, under `bash -e` as Actions runs it. `workflow_dispatch` with `release_version` gets the same tags.

The release job reads its workflow from the tagged commit, so the same change is in two PRs:
- this one, on `main`, for 1.4.x;
- one on `release/1.3.4`, for `v1.3.4.post1`.

It needs to merge before `v1.3.4.post1` is tagged, so the fixed image (#PR_1_3_4) reaches people pinned to `v1.3.4`. A dry run with `workflow_dispatch` before tagging would confirm the tag list on the real runner.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
