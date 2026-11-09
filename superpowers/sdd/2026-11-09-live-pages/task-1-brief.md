### Task 1: Node toolchain and core formatters

**Files:**
- Create: `lib/TWCManager/Control/static/js/format.js`
- Test: `tests/js/format.test.js`

**Interfaces:**
- Produces (all on global `Format`, exported via `module.exports`):
  - `age(seconds: number|null) -> string`
  - `ageAt(at: number|null, ctx) -> string` = `age(at == null ? null : ctx.data.now - at)`
  - `sourceName(raw: string) -> string`
  - `usd(amount: number) -> string`
  - `count(n: number) -> string` (en-US thousands separators)
  - `pyStr(v) -> string`
  - `duration(seconds: number) -> string`

- [ ] **Step 1: Install Node if missing**

Run: `node --version || (apt-get update && apt-get install -y nodejs)`
Expected: `v18` or later (needed for `node --test` with a directory).

- [ ] **Step 2: Write the failing tests** in `tests/js/format.test.js`

```js
const test = require("node:test");
const assert = require("node:assert/strict");
const F = require("../../lib/TWCManager/Control/static/js/format.js");

test("age", () => {
  assert.equal(F.age(null), "never");
  assert.equal(F.age(30), "30 s ago");
  assert.equal(F.age(90), "1 min ago");
  assert.equal(F.age(3600 * 5), "5 h ago");
  assert.equal(F.age(86400 * 3), "3 d ago");
  assert.equal(F.age(59.9), "59 s ago"); // int() truncation
  assert.equal(F.ageAt(100, { data: { now: 130 } }), "30 s ago");
  assert.equal(F.ageAt(null, { data: { now: 130 } }), "never");
});

test("sourceName", () => {
  assert.equal(F.sourceName("Gen2TWC"), "TWC");
  assert.equal(F.sourceName("TeslaBLE"), "BLE");
  assert.equal(F.sourceName("FleetAPICached"), "Fleet API (cached)");
  assert.equal(F.sourceName("Gen3TWC"), "Gen3 Wall Connector");
  assert.equal(F.sourceName("SomethingNew"), "SomethingNew");
});

test("usd keeps a third decimal below one cent", () => {
  assert.equal(F.usd(0), "$0.00");
  assert.equal(F.usd(0.002), "$0.002");
  assert.equal(F.usd(0.31), "$0.31");
});

test("count", () => assert.equal(F.count(41800), "41,800"));

test("pyStr matches Python str() for JSON values", () => {
  assert.equal(F.pyStr(true), "True");
  assert.equal(F.pyStr(null), "None");
  assert.equal(F.pyStr(5), "5");
  assert.equal(F.pyStr(0.5), "0.5");
  assert.equal(F.pyStr("tm_hour"), "tm_hour");
  assert.equal(F.pyStr(["a", 1, false]), "['a', 1, False]");
});

test("duration matches str(timedelta) without microseconds", () => {
  assert.equal(F.duration(3723.9), "1:02:03");
  assert.equal(F.duration(86400 + 5), "1 day, 0:00:05");
  assert.equal(F.duration(2 * 86400), "2 days, 0:00:00");
});
```

- [ ] **Step 3: Run to verify failure**

Run: `node --test tests/js/`
Expected: FAIL, `Cannot find module .../format.js`.

- [ ] **Step 4: Implement `format.js`**

Wrapper shape (the rest of the file follows it):

```js
var Format = (function () {
  var F = {};
  // ... functions ...
  return F;
})();
if (typeof module !== "undefined") { module.exports = Format; }
```

Values copied from `HTTPControl.py:37-65` (`ageText`, `SOURCE_NAMES`) and `:132-134` (`_usd`). `pyStr`: strings as-is; `true/false/null` → `True/False/None`; numbers `String(n)` (a float with an integral value prints without `.0`, the one unavoidable difference after JSON); arrays `"[" + items.map(repr).join(", ") + "]"` where `repr` quotes strings with `'`. `count`: `n.toLocaleString("en-US")`.

- [ ] **Step 5: Run to verify pass**

Run: `node --test tests/js/`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/TWCManager/Control/static/js/format.js tests/js/format.test.js
git commit -m "Live pages: format.js core rules under node --test"
```

---

