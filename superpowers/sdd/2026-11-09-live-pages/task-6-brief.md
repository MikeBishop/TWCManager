### Task 6: Page formatters

**Files:**
- Modify: `lib/TWCManager/Control/static/js/format.js`
- Test: `tests/js/format.test.js`

**Interfaces:**
- Consumes: the response shapes of Tasks 3–5; `ctx = {data, el, item}`.
- Produces (each a `Format.<name>(value, ctx)`; the source rule each ports is in brackets):
  - `presence(p)`: `home`→`Home`, `presumed`→`Probably home`, `notHome`→`Away` [`PRESENCE_TEXT`]
  - `watchLine(s, ctx)`: uses `ctx.data.now`, `ctx.data.budget` [`watchLine`, `HTTPControl.py:105-122`; `"covered by "` prefix]
  - `providerLine(claim) -> string` and `providerLines(claims) -> string` joined with `"\n"` (templates style the cell `white-space: pre-line`) [`providerLines` `:68-92`]
  - `lastSeen(entry, ctx)`: `ageAt(entry.lastSeenAt) + " via " + sourceName(entry.lastSeenSource)`
  - `heldLimit(l)`: `null`→`"—"`, else `"80% (90%)"` (`held`, then `outside`) [`heldLimitText`]
  - `fleetLine(spend)` / `telemetryLine(spend)`: the two summary lines; `""` when that flag is false [`spendLines`, `_lastMonth`, `_teleText`]
  - `spendCell(entry, ctx)` [`carSpend().cell`], `spendHeading(entry, ctx)` [`.heading`], `spendTelemetry(entry, ctx)` [`.telemetry`]; all read `ctx.data.spend.fleet/telemetry`
  - `spendTypeRow(t, ctx) -> [kind, String(count), usd(cost), ageAt(last)]`, `fieldRow(f) -> [field, count(count)]`
  - `pendingRow(p, ctx) -> [label, why]`: label `"Charge limit → 50%"` / `"Charge limit → car's own"` (value −1) / `"Charging → start|stop"` / `"Charge rate → 16 A"`; why per `pendingCommands` order: in flight `"sending via BLE, started 12 s ago"`; else `said`; else last outcome `"<detail or kind> via <source>, <age>"`; else `"not tried yet"`
  - `bleLabel(b)`: label + `" (scanning unavailable)"` when `!canScan && label === "Range unknown"`; `bleSince(b, ctx)`: `"since " + ageAt(b.since)` or `""`; `bleAttempt(b, ctx)`: `message + (" (" + ageAt(at) + ")" if at is a number)`; `bleLastScan(b, ctx)`: `ageAt(b.scannedAt)`; `bleRepair(b)`: `status in ("paired","refused")`; `bleScanBlocked(b)`: `"No range scan: " + scanBlocked` or `""`
  - `resolved(v, ctx)`: `""` when `JSON.stringify(v) === ctx.el.dataset.literal`, else `" (" + pyStr(v) + ")"` [`render_leaf`]
  - `pointKind(controllers)`: first local of `Gen2TWCs`→`TWC`, `Gen3TWCs`→`Gen3 Wall Connector`; no local → `EVSE via car`
  - `blank(v)`: `null`/`undefined` → `""`, else `String(v)` (Gen2-only cells)
  - `fixed2(v)`: `Number(v || 0).toFixed(2)`; `volts(list)`: `"a / b / c"` with each `Math.round`; `secondsSince(at, ctx)`: `String(Math.round((now - at) * 100) / 100)`; `chargeTime(since, ctx)`: `since == null ? "--:--:--" : duration(now - since)`
  - `scheduledStart(status)`: `start` unless `start != flex`, then `start + "(Flex " + flex + ")"` (status = `ctx.data`, so hooks use `data-field="scheduledChargingStartHour" data-format="scheduledStart"` with `value` ignored) [Default `jsrefresh.html.j2:16-20`]
  - `powerValue(w)` / `powerUnit(w)`: `w > 1000` → `(w*0.001).toFixed(2)` / `kW`, else `Math.round(w)` / `Watt` [Modern `jsrefresh.html.j2:17-24`]; `surplusWatts(_, ctx)` / `surplusUnit(_, ctx)` / `surplusAmps(_, ctx)` from generation − consumption (`0` when not positive) [`:29-48`]
  - `pluralS(list)`: `"s"` when `list.length > 1`
  - Predicates for `data-show-if`: `isEmpty(list)` (`!list || !list.length`), `not(v)` (`!Live-truthy`: false for `null`, `undefined`, `false`, `0`, `""`, `[]`), `bleNotRepair(b)` (`!bleRepair(b)`)

- [ ] **Step 1: Write the failing tests**, one per rule, with the exact strings the Python tests pin today:

```js
const now = 1_000_000;
const ctx = (data, el) => ({ data: Object.assign({ now, budget: 2.5 }, data), el: el || { dataset: {} } });

test("presence", () => { /* Home / Probably home / Away */ });
test("watch line", () => {
  assert.equal(F.watchLine({ watched: false, why: "off" }, ctx()), "Not watched: off");
  assert.equal(F.watchLine({ watched: false, why: "covered by TeslaMateVehicle" }, ctx()), "Not watched: covered by TeslaMate");
  const s = { watched: true, why: "", via: "ble", last: "asleep", lastAt: now - 120, nextAt: null };
  assert.equal(F.watchLine(s, ctx()), "Watched: asleep 2 min ago via ble; budget $2.50");
  assert.equal(F.watchLine({ ...s, via: null, why: "no status source" }, ctx()), "Not watched: no status source");
  assert.match(F.watchLine({ ...s, nextAt: now + 150 }, ctx()), /, next in 3 min;/);
});
test("provider lines", () => {
  const c = (provider, status, commands, readOnlyReason = null) => ({ provider, status, commands, readOnlyReason });
  assert.equal(F.providerLines([c("TeslaBLE", "paired", true), c("TeslaMateVehicle", "reports", false), c("Gen3TWC", "", true)]),
    "BLE: paired\nTeslaMate: reports, read-only\nGen3 Wall Connector: commands");
  assert.equal(F.providerLine(c("FleetAPI", "listed", false, "token lacks command scope")), "Fleet API: read-only (token lacks command scope)");
  assert.equal(F.providerLine(c("TeslaBLE", "unproven", false)), "BLE: unproven");
  assert.equal(F.providerLine(c("HomeAssistant", "entities", true)), "Home Assistant: entities, commands");
  assert.equal(F.providerLine(c("TeslaBLE", "paired", false)), "BLE: paired, read-only");
  assert.equal(F.providerLine(c("OwnerAPI", "listed", true)), "Owner API: commands");
});
test("held limit", () => { assert.equal(F.heldLimit({ held: 80, outside: 90 }), "80% (90%)"); assert.equal(F.heldLimit(null), "—"); });
test("fleet summary line with pace and last month", () => {
  const m = { api: 0.31, telemetry: 0, signals: 0, last: { api: 0, telemetry: 0 }, pace: { api: 0.62, telemetry: 0, by: "Dec 1" } };
  assert.equal(F.fleetLine({ fleet: true, month: m }), "Fleet API this month: $0.31 · on pace for $0.62 by Dec 1");
  assert.equal(F.fleetLine({ fleet: true, month: { ...m, api: 0, pace: null } }), "Fleet API this month: $0.00");
  assert.equal(F.fleetLine({ fleet: true, month: { ...m, pace: null, last: { api: 0.02, telemetry: 0 } } }), "Fleet API this month: $0.31 · Last month: $0.02");
  assert.equal(F.fleetLine({ fleet: false, month: m }), "");
});
test("telemetry line is approximate", () => {
  const m = { api: 0, telemetry: 0.28, signals: 41800, last: { api: 0, telemetry: 0 }, pace: null };
  assert.equal(F.telemetryLine({ telemetry: true, month: m }), "Fleet Telemetry this month: approx. 41,800 signals, $0.28");
  assert.equal(F.telemetryLine({ telemetry: true, month: { ...m, telemetry: 0.002, signals: 300 } }), "Fleet Telemetry this month: approx. 300 signals, $0.002");
});
test("car spend cell, heading and telemetry", () => {
  const car = { api: 0.02, telemetry: 0.002, requests: 1, signals: 300, types: [], fields: [], last: { api: 0, telemetry: 0 } };
  const both = ctx({ spend: { fleet: true, telemetry: true } });
  assert.equal(F.spendCell({ spend: car }, both), "$0.02 + approx. $0.002 telemetry");
  assert.equal(F.spendHeading({ spend: car }, both), "Fleet API this month: $0.02 in 1 request");
  assert.equal(F.spendHeading({ spend: { ...car, requests: 2, api: 0.04 } }, both), "Fleet API this month: $0.04 in 2 requests");
  assert.equal(F.spendTelemetry({ spend: { ...car, signals: 3 } }, both).startsWith("Fleet Telemetry this month: approx. 3 signals"), true);
  assert.deepEqual(F.spendTypeRow({ kind: "wake_up", count: 2, cost: 0.04, last: now - 30 }, both), ["wake_up", "2", "$0.04", "30 s ago"]);
});
test("pending rows", () => {
  const p = (o) => Object.assign({ aspect: "chargeLimit", value: 50, inFlight: null, said: null, lastOutcome: null }, o);
  assert.deepEqual(F.pendingRow(p({ inFlight: { provider: "TeslaBLE", since: now - 12 } }), ctx()), ["Charge limit → 50%", "sending via BLE, started 12 s ago"]);
  assert.deepEqual(F.pendingRow(p({ value: -1 }), ctx()), ["Charge limit → car's own", "not tried yet"]);
  assert.equal(F.pendingRow(p({ aspect: "charging", value: true }), ctx())[0], "Charging → start");
  assert.equal(F.pendingRow(p({ aspect: "amps", value: 16 }), ctx())[0], "Charge rate → 16 A");
  const last = { kind: "unreachable", detail: "", provider: "TeslaBLE", at: now - 120 };
  assert.equal(F.pendingRow(p({ lastOutcome: last }), ctx())[1], "unreachable via BLE, 2 min ago");
  assert.equal(F.pendingRow(p({ lastOutcome: { ...last, detail: "backoff" } }), ctx())[1], "backoff via BLE, 2 min ago");
  assert.equal(F.pendingRow(p({ lastOutcome: last, said: "no provider can deliver" }), ctx())[1], "no provider can deliver");
  assert.match(F.pendingRow(p({ lastOutcome: { ...last, detail: "held: driving", provider: "Gen2TWC" } }), ctx())[1], /^held: driving via TWC, /);
});
test("ble", () => {
  const b = (o) => Object.assign({ status: "unpaired", label: "In range (not paired)", canScan: true, since: null, scannedAt: now - 42, scanPending: false, scanBlocked: null, attempt: null }, o);
  assert.equal(F.bleLabel(b({ label: "Range unknown", canScan: false })), "Range unknown (scanning unavailable)");
  assert.equal(F.bleLabel(b()), "In range (not paired)");
  assert.equal(F.bleSince(b({ since: now - 120 }), ctx()), "since 2 min ago");
  assert.equal(F.bleSince(b(), ctx()), "");
  assert.equal(F.bleAttempt(b({ attempt: { ok: false, at: now - 120, message: "<b>timed out</b>" } }), ctx()), "<b>timed out</b> (2 min ago)");
  assert.equal(F.bleLastScan(b(), ctx()), "42 s ago");
  assert.equal(F.bleLastScan(b({ scannedAt: null }), ctx()), "never");
  assert.equal(F.bleRepair(b({ status: "refused" })), true);
  assert.equal(F.bleRepair(b()), false);
  assert.equal(F.bleNotRepair(b()), true);
  const why = "Bluetooth adapter is powered off or blocked (rfkill)";
  assert.equal(F.bleScanBlocked(b({ canScan: false, scanBlocked: why })), "No range scan: " + why);
});
test("predicates", () => {
  assert.equal(F.isEmpty([]), true); assert.equal(F.isEmpty([1]), false);
  assert.equal(F.not(false), true); assert.equal(F.not(true), false);
});
test("policy resolved suffix", () => {
  const el = (lit) => ({ dataset: { literal: JSON.stringify(lit) } });
  assert.equal(F.resolved(5, ctx({}, el("settings.x"))), " (5)");
  assert.equal(F.resolved(5, ctx({}, el(5))), "");
  assert.equal(F.resolved(true, ctx({}, el("x"))), " (True)");
});
test("home", () => {
  assert.equal(F.pointKind(["Gen2TWCs", "VehicleEndpoints"]), "TWC");
  assert.equal(F.pointKind(["Gen3TWCs"]), "Gen3 Wall Connector");
  assert.equal(F.pointKind(["VehicleEndpoints"]), "EVSE via car");
  assert.equal(F.blank(null), "");
  assert.equal(F.chargeTime(null, ctx()), "--:--:--");
  assert.equal(F.volts([240, 0, 0]), "240 / 0 / 0");
  assert.equal(F.scheduledStart(null, ctx({ scheduledChargingStartHour: 22, scheduledChargingFlexStart: 21 })), "22(Flex 21)");
  assert.equal(F.scheduledStart(null, ctx({ scheduledChargingStartHour: 22, scheduledChargingFlexStart: 22 })), "22");
  assert.equal(F.powerValue(1500) + " " + F.powerUnit(1500), "1.50 kW");
  assert.equal(F.powerValue(800) + " " + F.powerUnit(800), "800 Watt");
});
```

Fill the two `/* ... */` bodies with the asserted strings named in them (from `test_vehicle_detail_page.py:39-96`).

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/js/*.test.js`
Expected: FAIL (`F.presence is not a function`, ...).

- [ ] **Step 3: Implement the formatters**

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/js/*.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Control/static/js/format.js tests/js/format.test.js
git commit -m "Live pages: page wording rules move to format.js"
```

---

