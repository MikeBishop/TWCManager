# Squash Phase 5 history (user approved 2026-10-20: "Yes, do the squash now.")

Source: branch vehicle-model/phase5 at 4f2a3275 (backup branch backup/phase5-pre-squash = 4f2a3275). Base 044e5262 (Phase 4 tip, PR #710).
Numbered commit list: squash-commits.txt (same directory).

## Target groups (in this order where possible)
A Read config defaults as one-liners — 1–2
B Log reconciler outcomes, paid requests and telemetry changes at INFO — 3–4
C Compute presence from events; one home check — 5–7, 32
D One applicability rule per message; BLE ping; holds; paid budget counts real requests — 8–9, 35–37
E A policy with no limit is a release of the car's own limit — 10–11
F Size-audit cuts — 13–19
G A charging point's own commands always apply; plugged follows plug events — 21–22
H Attribute a VIN-less plug — 23–24, 31, 33, 46, 54, 56
I Vehicles page: presence and pending commands — 25–26, 44–45
J Leave a sleeping car alone; only live evidence is a sign of life — 39–40, 60–62
K Run BLE scans and attribution reads on the BLE worker — 42–43
L Wake a car only when it is expected to charge; wait for telemetry after a start — 12, 48–49, 57
M A returning car tries BLE first; restore at the drive start; hold a driving car quietly — 50–53, 55
N A BLE range scan is a sighting and survives a restart — 58–59
O A Gen2 status change means "check the car"; drop the timed departure reads — 20, 34, 63–73
P Import vehicle-model modules by name; trim comments — 27–28, 38
Q Docs and changelog — 29–30, 41, 47
(Any commit not listed: fold into the group it most belongs to and say so.)

## Rules
- Hard requirement: the final tree is byte-identical to 4f2a3275: `git diff 4f2a3275 <new tip>` prints nothing.
- Every new commit passes tests/unit + tests/EMS (run the suite at each new commit; record pass counts). If an intermediate group can't pass because a later group's code is needed, merge or reorder groups until each commit passes; say what you changed.
- Reordering far-apart commits may conflict. Prefer: interactive-style squash done non-interactively (`GIT_SEQUENCE_EDITOR` with a prepared todo, or cherry-picks onto a fresh branch from 044e5262 with `git commit --amend`/`--fixup` + autosquash). Where a move conflicts badly, fold into the nearest group instead and note the deviation.
- Work on a new branch `vehicle-model/phase5-squashed` in a new worktree; do not touch vehicle-model/phase5 or the backup branch. Do not push.
- Each commit message: a plain subject (the group title, refined), a short body saying what the change does and why (no history, no phase/PR/ruling IDs), ending with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Python 3.8 / black are unchanged (tree identical).
