### Task 6: Vehicles page: presence and pending commands (expected lib Δ ≈ +40)

User, 2026-10-18: fold presence into the Vehicles page; of the spec's per-car diagnostics, show only pending commands — what is in flight and/or why it is not being sent. The merged field view and per-provider panels are dropped from the spec.

- **List page** (`vehicles.html.j2`): a **Presence** column from `Presence.presence(v)` at render: HOME → "Home", PRESUMED → "Probably home", NOT_HOME → "Away".
- **Per-car page** (`vehicleDetail.html.j2`): a **Pending commands** section, one row per open desire in the reconciler's `DesiredStore` for that VIN (none → "Nothing pending"):
  - what: the aspect and desired value in words ("Charge limit → 50%", "Charging → start", "Charge rate → 16 A");
  - state, first that applies:
    - in flight (`rec.inFlight`): "Sending via <source name> (<age>)";
    - held (`rec.heldAt` set, last outcome `held: <why>`): "Waiting: <why>";
    - backing off / waiting for a free channel / paid budget spent / no provider can command: the reason the reconciler already computes for its log lines (`_whyNoWake`, the `excluded` map, `paidRetryDue`), in words, with when it retries if known;
    - otherwise the last outcome and its age ("Last try via BLE: unreachable, 2 min ago").
- One helper `pendingCommands(master, vin) -> list[dict]` in `HTTPControl.py` next to `providerLines`, reading registry/reconciler state under their locks at render; no HTTP, no reads, no new provider work. Source names through the existing `sourceName` mapping.
- Tests: `tests/unit/test_vehicles_page.py` rows: presence column for each state; pending section for in-flight, held, excluded/backoff, last-outcome, and empty.


---
## Controller addendum (user approved the audit plan, 2026-10-19): ≤ 0 net lib
Read "## 4. Building Tasks 4–6 at ≤ 0 net → Task 6" in audit-report.md (same directory) and its finding **A5** (trim `Vehicle.summary()`/`summaries()` to the keys the templates read; the WebIPC debug dump loses per-field detail). Take A5 in this task so it nets ≤ 0.
- Presence column: one template expression through a `presence` global (Presence.presence(master, v) → "Home"/"Probably home"/"Away").
- `pendingCommands(master, vin)` with a fixed vocabulary, reusing what exists: `rec.inFlight`, `rec.heldAt` + `rec.lastOutcome.detail` (held reasons from `applicable`'s why: "driving", "not plugged in", "away", "leaving", "tie", "not parked", …), `Reconciler._whyNoWake` strings (incl. "nothing offered"), the hands-off/no-provider messages (a public `said(key, aspect)` accessor rather than new wording), `sourceName`, `ageText`.
- No HTTP, no reads, no provider work at render; take locks only as existing readers do.
- Parked issue to fix here if cheap: an away car whose departure restore failed gets RELEASE set and cleared NOT_HERE on every policy pass (INFO log churn). If the page work touches that path, stop the churn (e.g. skip RELEASE for a car whose held entry is awaiting a departure restore); otherwise leave a note.
