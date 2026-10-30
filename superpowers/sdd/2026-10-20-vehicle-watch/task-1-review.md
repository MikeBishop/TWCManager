# Task 1 review: charge-port door and keyless ping (52a2652c..4e23c85c)

## Verdicts

- **Spec compliance: PASS.** Field, `_noteSleep` door parse, keyless `body-controller-state`, `ping(scan=)`, `_plug`/`noteObservation`/`pluggedNow`/`unpluggedAt` over three fields, `checkPlug` and `pick` changes all match the brief and spec "What each observation does". The two deviations are justified; nothing extra was added.
- **Quality: APPROVE with one Important fix** (unclaimed cars should not scan). The rest are minor.

## The questions asked

### 1. A CLOSED door takes `was` from the plug marks: correct and safe

`was = was if plugIn == unplug else plugIn > unplug`, Presence.py:145-148.

- **No plug ever known.** Both marks are NEVER, so `was` stays `_plug(previous door)`: None or False. No unplug is marked. Safe.
- **Repeat CLOSED readings.** The first one sets `unplug > plugIn`, so later ones get `was` False and mark nothing. Idempotent.
- **Retained or stale readings.** The door's source is TeslaBLE only. It is never in `TELEMETRY_SOURCES`, so the retained-copy guard is irrelevant. Every door reading is a live ping answer.
- **An old plugIn with no unplug ever marked.** Example: the car left with only a cloud API watching. The first awake CLOSED door then marks `unplug` now. That is late but true. The same ping writes `bleReach` True afterwards, so `contact >= unplug` and `decide` gives HOME (or PRESUMED on a tied test clock), never NOT_HOME. The brief's "same rule as pluggedIn" could not pass its own test. Using the marks is the right reading of the spec's "marks unplug exactly as for a pluggedIn False", and it is safer than marking on every CLOSED reading.

### 2. Unclaimed cars ping with `scan=True`: they should not

Today, `checkPlug` (Presence.py:224) and `pick.fits` (Presence.py:424) pinged only claimed cars. Now every candidate is pinged.

- **BLE-lane time.** For an unclaimed car that does not answer, the cost is the 15 s `commandTimeout` plus an 8 s scan (12 s timeout), all on the BLE worker. That is per candidate, per attribution or plug-session check, serially, ahead of user commands.
- **Bookkeeping.** A scan miss writes `bleReach` False, which marks `absent` (Presence.py:111-113). It also writes `_rangeScan` entries for cars that have no record.
- **Spec conflict.** The spec says "one miss says nothing" (spec :111) and gives scan budgeting to later tasks (spec :58, :151). Extending the one-miss `absent` writer to cars that never had it goes against that direction.
- **Nothing gained.** Neither caller needs the scan to decide: `checkPlug` uses only asleep and door, and `fits` uses only the door and sleep.
- **Fix:** `ble.ping(v.vin, scan="TeslaBLE" in v.claims)` at both sites. Claimed cars keep today's behaviour. Unclaimed cars get the door and sleep state at the cost of one tesla-control run, and no new `absent` marks.

### 3. Keyless ping: no leak

`_tool` (TeslaBLE.py:589-611):

- The keyless branch is taken only when `args == ("body-controller-state",)` exactly. Any other subcommand, including `body-controller-state` with extra args, takes the keyed branch: record check, then `sendPrivateKey`, then `-key-file`.
- The keyless branch never calls `sendPrivateKey` and never adds `-key-file`. It does require a well-formed str VIN.
- `_ensure_pipe_closed` in `finally` is harmless when no pipe was opened.
- A keyless answer does not call `_noteBleProof`, so it cannot prove a key.
- `_noteScan` only updates an existing record, so a scan never creates the settings record that would let keyed commands pass the record check.
- `Reconcile/Run.py:161` still pings only on TeslaBLE provider attempts, which go to claimed cars.

### 4. OPEN door and asleep

- `_plug` returns None for True, so OPEN never marks `plugIn` and never counts in `pluggedNow`; `unpluggedAt` counts only False.
- `_noteSleep` observes the door only when `closureStatuses.chargePort` is present. That block is absent asleep, so asleep gives no door observation. Tested.
- The parse is not gated on AWAKE. It does not need to be: a present block is still the car's own report.

### 5. Locks, I/O, comments, size

- **Locks and I/O.** `_tool` holds `_bleLock`, then takes `settingsLock` briefly in `_settingsKey`/`sendPrivateKey` (record lookup). That order is correct. `_noteSleep`'s registry observes run after `_tool` returns, so no lock is held. No new I/O happens under locks.
- **Comments.** They say why, with no history or IDs.
- **Size.** Lib grows by +42 (71/-29). Small trims are listed below. None is required.

## Findings, ranked

1. **Important**, Presence.py:224 and :424. Unclaimed cars ping with the default `scan=True`: up to 15 s + 12 s of BLE lane each, and a one-miss `absent` mark the spec is moving away from. Fix: `ping(v.vin, scan="TeslaBLE" in v.claims)`.
2. **Minor**, Presence.py:208-211 (`_doorClosed` in `pick.fits`). With `since=NEVER` (the default `pick`), any old CLOSED reading excludes the car. The unplug test on the line above guards against `> NEVER`. Production always passes the anonymous session's plugIn mark, so this is latent. Fix: guard on `since > NEVER`, or document that callers pass a real `since`.
3. **Minor**, Presence.py:214-221. The `checkPlug` comment does not mention the new branch. Fix: add a short clause such as "an awake car's closed door is no cable".
4. **Minor**, TeslaBLE.py:658. The `ping` docstring still leads with "only an unanswered run is absence", which no longer holds for `scan=False`. Fix: "True answered; False a scan ran and missed; None no answer (or no scan asked)".
5. **Nit/size**, Presence.py:195-200. The black wrap adds 2 lines to `unpluggedAt`. Fix: keep a one-line form (for example `f`/`o` over `_PLUG_FIELDS` with a shorter filter) or accept it.
6. **Nit/size**, TeslaBLE.py:661-664. `return answer is True if scan else answer` could be dropped if `_runPing` returned a bool when `scan=True`. It is optional, and the current form is clear enough.
