# Task 5 review: port of #659 onto Phase 3.5 (6c4ba54..40f77ca)

Reviewer: independent, read-only. Code: wt-vm35 at 40f77ca (5190831, 3ffd8c8, 40f77ca).

**Spec: ✅ compliant.** **Quality: approved.** There are no blocking or medium findings, only low and info notes and some optional savings.

Verification run:
- Unit suite (`tests --ignore=tests/API --ignore=tests/integration`): **1829 passed, 1 xfailed** (matches the report).
- Lib line count recomputed with `git show` over `git ls-tree`: 27,098 -> 27,358, **+260** (confirmed).
- Test names added or removed: the reference adds 43 `def test_`/`class` lines; the port adds the same 43 plus `test_owner_only_off_car_matches_fleet_only`. The sets were diffed and nothing is missing.
- Scratch parity of the per-desire paid records, owner-only "off" against Fleet-only (not committed; `scratchpad/t5review/test_t5_paid_records.py`, run from inside tests/unit and then removed). Four scenarios: raise (asleep, wakes), retry (500 script), asleep-never-wakes (408), and stop. After **every pass** it compares `(paidSends, paidReached, paidRetryDue, paidAt, lastOutcome, lastOutcomeAt)` for CHARGE_LIMIT and CHARGING, plus the command list and the request method/path sequence. **All 4 are identical.**

## 1. Behavioural equivalence with the reference

The port is a near line-for-line copy of the reference's lib logic. The only differences are adaptations to the 3.5 structure:

| Requirement | Reference (phase3) | Port (3.5) | Equivalent? |
|---|---|---|---|
| command_signing recorded | `CarApiVehicle.__init__` sets `commandSigning`, `ownerCommandsRefused`, `refusalLoggedAt` | `CarApiState` class defaults (TeslaAPI.py:62-66); `addVehicle` sets `state.commandSigning` before `getOrCreate(attach=)` (TeslaAPI.py:244-249) | Yes. The attachment lands complete under the registry lock. `attach` always replaces, and the claim lambda captures the same `state` object, so the claim and the attachment cannot diverge |
| OwnerAPI claim | `lambda: carapi.ownerCommandsAllowed(self)` in `_bind` | `lambda: self.ownerCommandsAllowed(state)` (TeslaAPI.py:254) | Yes |
| readOnly / _signingState | iterate `carApiVehicles` | iterate `registry.attached("TeslaAPI")` pairs (TeslaAPI.py:492-501, 1305-1309) | Yes. An empty list behaves the same |
| commandSlotFor | Fleet first; Owner if `vehicle is not None and ownerCommandsAllowed(vehicle)` | Fleet first; `car = vehicle.attachment(...)`, and `ownerCommandsAllowed(car)` fails closed on None (TeslaAPI.py:509-517, 524-536) | Yes. `None` or unattached -> None, as in the reference for `None` |
| readOnlyFor | `commandSlotFor(v) is None` (its only lib caller was `refuseCommandFor`) | inlined as `commandSlotFor(vehicle) is not None` (TeslaAPI.py:1341) | Yes. Dropping it is equivalent; the tests map `readOnlyFor(car)` to `commandSlotFor(vehicle) is None` |
| command / wakeOutcome / stopCharging | `commandSlotFor` + `slot not in (None, chosen)` | same (TeslaAPI.py:1461-1464, 1542-1545; Providers:110-118) | Yes. stopCharging keeps 3.5's `onlineState(...) is False` (the reference's `is_awake`/`lastVehicleAwakeKnown` pair no longer exists) |
| Wake guard | `slot is self.fleetSlot and not slot.usable("wake")` | same | Yes |
| Methods moved to base, OWNER_COMMAND, Owner `ready`/`available`, TESLA_COMMAND | as reference | the same text, with `_car` -> 3.5's existing `_listed` | Yes |
| `_classify` owner branch (200 included; otherwise after the 401 refresh, before the generic 403/412) | as reference | the same placement; the `car=` -> `vehicle=` rename is applied to all 3 `_request` callers (TeslaAPI.py:1496-1502 `_paidPost`, 1818-1825 `get_car_api`; `list`/`energy` pass none). 429 derives `car` from `vehicle` (TeslaAPI.py:446) | Yes. The 429 target is the same per-car state as before |
| Latch: Owner 403 or VCP text | `noteOwnerCommandRefused` | same; adds a `car is not None` guard (a forget between send and answer), and still returns `_SIGNING_REQUIRED` | Yes, and safer |
| Slot-wide refusal: 410 / 412 / "only available on fleetapi" | `noteOwnerCommandsRetired`; stamps every car's `refusalLoggedAt` | same over `attached()` pairs | Yes |
| No error backoff on either path | yes | yes (neither calls `updateCarApiLastErrorTime`) | Yes |
| 3489e93 NOT_SENT + H2 | Outcome.py / Reconciler.py | applied verbatim | Yes |
| Finding 2 (wrong per-car reason when the Owner slot refuses "command") | fixed in 72439ec | the `refusedPurposes` branch comes first, and the flag is in `refusalState` (TeslaAPI.py:1327-1336, 1353-1358). Test: `TestOwnerCommandsRetired::test_per_car_line_names_the_token` | Yes |
| Finding 3 (200 + VCP error) | `_classify` runs `ownerRefusal` on a paid Owner 200 | same (TeslaAPI.py:369-372). Tests: `TestOwner403Latch::test_vcp_error_on_http_200_latches[command|wake]`, `test_retired_on_http_200` | Yes. The latch now happens in `_classify`, before `_paidPost`'s TypeError path. Main does this per command path; the observable behaviour is the same (one POST, latched, no backoff) |
| Docs / templates / VehicleEndpoint / TeslaTokenSlot | | identical hunks. The wording still holds on 3.5 ("reads the vehicle list once": `loadVehicleList` lists only while nothing is attached) | Yes |

Nothing the reference does was dropped. `readOnlyFor`, `_car`/`getVehicleByVIN`, and the `getattr(..., "commandSigning", None)` defensiveness are each replaced by an equivalent: the inline check, `_listed`, and the class defaults respectively.

## 2. No change for Fleet-only, BLE, HA and Gen3 beyond the intended ones

- `test_command_path_parity.py`: all 31 original rows pass unchanged.
- The `install()` edits do not mask a difference:
  - `p.clock = c` is now set on both providers. OwnerAPIProvider had no command methods before, so its clock was never read. FleetAPI's clock is set exactly as before.
  - `"command_signing": signing` with the default `None` is the same as the key being absent (`json.get`).
  - `FleetCar(api=FLEET)` defaults to the old base.
  - Every pre-existing owner row therefore still has a read-only car.
- The new row 3b compares request sequences. My scratch test extends it to per-pass paid-record identity across 4 scenarios, including the asleep-and-never-wakes one that the implementer did not cover. All are identical.
- Fleet-only walks: whenever `fleetSlot.usable("command")`, `commandSlotFor` returns `fleetSlot`, `OwnerAPIProvider.available(COMMANDS)` is False, and `FleetAPIProvider.ready/available` are textually unchanged. The budget key and costs are unchanged.
- The H2 relaxation (3489e93, kept by user decision) applies to every outcome that is both NOT_SENT and EXCLUDING. I enumerated them in lib: "no command token" (TeslaAPI), "not listed" (TeslaAPIProviders:94/134 **and HomeAssistantProvider.py:104**), "signing required" and "owner commands retired". `beforeWrite`'s rules outcomes are SATISFIED/UNREACHABLE/ERROR only (Reconciler.py:470-497), so they are unaffected. See finding L1.
- BLE and Gen3 are untouched: no BLE, Gen3 or TWC file is in the diff.

## 3. Thread safety, locks and logs

- The new `CarApiState` fields are plain attributes. Each write is a single store under the GIL. They are read by the claim lambda, which `Vehicle.tier` and `Claim.commands` run outside the vehicle lock (Vehicle.py:30-38, 238-240), and by provider `ready`. This is the same unlocked style as the existing per-car fields (`errorCount`, `online`, `onlineCheckedAt`).
- `refusalLoggedAt` check-then-set and `noteOwnerCommandsRetired`'s `"command" not in refusedPurposes` then `refuse` are unlocked. The worst race outcome is one duplicated INFO or ERROR line. The reference has the same race; see L3.
- `ownerSlot.refusedPurposes` is read with `in` while another thread may `add` to it or rebind it, which is safe for a set membership test. `TeslaTokenSlot` has no lock, as before.
- Lock order:
  - No new lock is taken. `readOnly`, `refuseCommandFor`, `noteOwnerCommandsRetired` and `_signingState` call `registry.attached()` (registry and vehicle leaf locks only) and iterate outside them.
  - The registry contract (VehicleRegistry.py:2-3: no claim callable runs under a registry lock) holds.
  - `addVehicle` still runs under `vehicleListLock` -> registry leaf, as on 3.5. Its `getOrCreate(attach=)` is unchanged in shape.
  - No `_bleLock` or `settingsLock` interaction.
- No new I/O under a lock. `ownerRefusal` runs inside `_classify` after the HTTP answer, outside any lock. The `list` purpose (under `vehicleListLock`) never takes the owner branch, because `paid` is False.
- Logs: the new lines interpolate `vehicle.name`, the HTTP status, the Tesla command name and `str(command_signing)[:40]`. No token is logged and no response body is logged; Tesla's error text is matched only.

## 4. Lib growth (+260; reference +267)

- The 7 lines saved against the reference come from `readOnlyFor` (-3), `_car` vs `_listed`, and the absence of `_bind`/`__init__` plumbing.
- I found no duplication of existing 3.5 code:
  - `ownerTokenHeld` overlaps `TeslaTokenSlot.usable`'s first check, but `usable("command")` cannot be used for the owner slot without changing `grants()`.
  - The repeated 4-line chooser block in `command`/`wakeOutcome` costs more as a helper (def plus 2 call sites) than it saves.

Behaviour-neutral or near-neutral savings:

| # | Where | Saving | Judgement |
|---|---|---|---|
| S1 | Drop `_signingState` (TeslaAPI.py:1305-1309, 6 lines incl. blank) and key `noteReadOnly` on `self.fleetSlot.changes` again (1316, plus 1-2 comment lines at 1313-1315 and 115-116) | **about -8** | **Do it.** The module-wide line runs only when no Owner token is held (1318). Its text never depends on signing, and with no Owner token `ownerCommandsAllowed` is False for every car whatever their signing. So the signing key only re-logs an identical line when cars get listed (no token -> line; listing -> same line again) or when a stale latch flips. This is noise, not information. Brief req 3 names `_signingState`, but only as "iterate attached pairs". Dropping it is the cleaner reading |
| S2 | `refuseCommandFor` (TeslaAPI.py:1369-1378): merge the `signing is None` and unknown-value branches into one "Tesla reports command_signing: %s for it ..., so it is treated as read-only" | about -4 | Optional. The log wording changes for the missing-field case (it would print "None"). Pure wording, not behaviour |
| S3 | The `readOnly` body (TeslaAPI.py:492-501) | about -6 | **Not recommended without the user.** Its only lib consumer is `noteReadOnly`, where after the `ownerTokenHeld()` early return it is exactly `not fleetSlot.usable("command")`. The per-car aggregate is test-only API. But brief req 3 and 5 gate-test asserts pin it |

With S1 the delta is about +252; with S1+S2, about +248.

## 5. Tests

- **Mapping.** Every rewritten test in the report's table checks out against the reference. A `diff` of the reference's test_teslaapi_readonly_gate.py against the port shows only these mechanical translations:
  - `carApiVehicles[i]` -> `registry.get`/`listed()`/`attached()`
  - `car.vehicle` -> the registry Vehicle
  - `readOnlyFor(car)` -> `commandSlotFor(vehicle) is None`
  - `car.update_vehicle_data()` -> `api.update_vehicle_data(vehicle)`
  - `car.batteryLevel` -> `vehicle.value("batteryLevel")`
  - the `test_carapivehicle_registry` import -> `test_teslaapi_registry`
- **No assertion was weakened.** Two-car tests rely on `attached()` returning VIN order instead of insertion order. They pass, so the off/required assignments line up.
- **The tests exercise the 3.5 code.** They drive the real `addVehicle` with a `/products` entry (`add_home_vehicle(command_signing=...)`), real providers, real `_classify` via requests_mock, and `TestThroughTheWalk` uses the real reconciler and order. My scratch test confirms the parity path is real: Owner requests hit owner-api URLs, and the commands are the same.
- Nits (L2):
  - test_teslaapi_readonly_gate.py:333-334 asserts `commandSlotFor(vehicle) is not None` and then `is api.ownerSlot`.
  - :350-351 asserts `commandSlotFor(vehicle) is None` twice.
  - Both are leftovers of the `readOnlyFor` substitution. Delete the redundant halves.

## Findings

- **L1 (low/info).** Reconciler.py:255 (3489e93, user-kept): the H2 skip for EXCLUDING outcomes also covers Home Assistant's `UNSUPPORTED "not listed"` (HomeAssistantProvider.py:104) and Fleet's `"not listed"`, which neither the commit message nor the brief names. The provider is already excluded for the record, so there is no resubmit loop: the next provider just goes at once instead of after RETRY. This is harmless and the same as the reference. Mention it in the PR so the HA change is not a surprise.
- **L2 (nit).** test_teslaapi_readonly_gate.py:333-334 and 350-351: duplicated or redundant `commandSlotFor` assertions left by the `readOnlyFor` substitution.
- **L3 (info).** TeslaAPI.py:1349-1351 and 1403-1406: unlocked check-then-set on `refusalLoggedAt` and the owner `refusedPurposes`. The worst case is one duplicated log line under a race between the cloud worker and the debug interface. This is the same as the reference and the existing per-car fields. No action.
- **L4 (info).** TeslaAPI.py:1305 `_signingState`: see S1. Recommend dropping it.

No finding on token logging, lock order, new I/O under locks, paid-call parity or dropped reference behaviour.
