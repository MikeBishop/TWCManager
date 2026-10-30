Collect release notes from per-PR files

@ngardiner, this changes how we write the changelog and how a release is cut, so I'd like your explicit OK (or objections) before it goes anywhere. It's a draft until then.

## Why

Every PR edits the same "Upcoming" section of CHANGELOG.md, so PRs that are open at the same time conflict there. In the 1.4.1 cycle that meant rebasing each stacked vehicle-model PR just for the changelog. [Actual](https://github.com/actualbudget/actual) avoids this by having each PR add its own note file, which a script collects at release time. Because no two PRs touch the same file, the notes never conflict.

While moving the notes, I also shortened them. Entries before 1.4.0 averaged 12–20 words; the 1.4.1 section had grown to about 70, much of it detail that belongs in the docs. Each note is now one or two sentences starting with a verb, as in the older releases.

## What changes

- **Contributors:** a PR adds `changes/<slug>.<type>.md`, where type is `feature`, `architecture` or `bugfix`, containing only the text. You don't need the PR number or author: when a release is cut, the script asks GitHub which merged PR holds the commit that added the file, and credits that PR's author rather than whoever merged it. That works however the PR was merged: on GitHub or as a merge made in git and pushed. A note with no PR, such as a commit made straight on main, credits the commit's author. Optional front matter names the PR, or the authors, when a note is added for someone else's change. `changes/README.md` has the guide.
- **CI:** `.github/workflows/release_notes.yml` fails a PR that adds no note. It skips PRs that only touch docs, tests or CI, and PRs with a `no changelog` label. Notes over two sentences or 50 words get a warning, not a failure.
- **Release:** `python3 contrib/release_notes.py build --version X.Y.Z` writes the section into CHANGELOG.md in the existing `(@author) - text (#PR)` format and removes the note files. `draft` previews the section at any time. Cutting a release is documented in the Development Guide.
- **Post releases:** `build --version 1.4.0.post1`, run on `release/1.4.0`, lists the fixes under the 1.4.0 section as `### v1.4.0.post1`, after 1.4.0's own entries. Cherry-picking that commit onto main records the post release there and removes the shipped notes, so 1.4.1 doesn't list them again.
- **1.4.1:** the second commit moves the 1.4.1 Upcoming entries into note files, the third combines them and drops fixes to code 1.4.0 never shipped, and a later commit adds notes for what has merged since (39 notes in all). Each note is credited to the PRs that made the change.

The script uses only the standard library. Without `gh`, it falls back to the merge commit's subject (`Merge pull request #N from owner/branch`).

## Questions for you

1. Are you happy to cut releases with `release_notes.py build`?
2. Should a missing note fail CI, or only warn? It fails as written.
3. Can you create the `no changelog` label? I can, but it's your repo.
4. Are you OK with the shorter style for notes?
5. Should a post release be listed under its parent release, as written? Today the 1.3.4.postN sections are only on `release/1.3.4`, as separate top-level sections, and main's changelog doesn't have them.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
