### Task 7: `live.js` and live vehicle pictures

**Files:**
- Create: `lib/TWCManager/Control/static/js/live.js`
- Modify: `lib/TWCManager/Control/static/js/vehicleImage.js`
- Test: `tests/js/live.test.js`

**Interfaces:**
- Consumes: `Format` (global in the browser, `require("./format.js")` under Node); the hook vocabulary above.
- Produces (global `Live`, exported under Node):
  - `Live.start({urls, interval, fingerprint})`: `urls` items are a string (response merged into the data object with `Object.assign`) or `[url, key]` (response stored at `data[key]`). Fetches all with `cache: "no-store"` on load and every `interval` ms; any 404, or any response whose `fingerprint` differs from the page's, calls `location.reload()`. On fetch failure: keeps last values, shows one notice element (created by live.js at the top of `<body>`, class `live-offline`, text `Can't reach TWCManager`), retries on the interval; hides it on the next success. Pauses while hidden; fetches immediately on `visibilitychange` to visible.
  - `Live.onData(fn)`: `fn(data)` after each successful bind (page-specific script: Charge Now button state, policy action buttons, consumption colour, active policy).
  - `Live.bind(root, data)`: applies every hook under `root`.
  - Pure, tested under Node: `Live._lookup(data, path, item)`, `Live._truthy(v)`, `Live._mustReload(pageFingerprint, responses: [{status, body}]) -> bool`.
  - `window.drawVehicleImage(img)`: the per-image body of today's `vehicleImage.js` loop; the on-ready loop now calls it.

- [ ] **Step 1: Write the failing tests**

```js
const L = require("../../lib/TWCManager/Control/static/js/live.js");
const fs = require("node:fs");

test("lookup by key, id, index and relative path", () => {
  const d = { vehicles: [{ key: "anon:8244", name: "" }, { key: "5YJ", name: "Car" }], points: [{ id: "Point-5YJ", amps: 16 }], policies: [{ nodes: { "g-0": { truth: true } } }] };
  assert.equal(L._lookup(d, "vehicles.5YJ.name"), "Car");
  assert.equal(L._lookup(d, "vehicles.anon:8244.name"), "");
  assert.equal(L._lookup(d, "points.Point-5YJ.amps"), 16);
  assert.equal(L._lookup(d, "policies.0.nodes.g-0.truth"), true);
  assert.equal(L._lookup(d, ".amps", d.points[0]), 16);
  assert.equal(L._lookup(d, "vehicles.nope.name"), undefined);
});
test("truthy", () => { for (const v of [null, undefined, false, 0, "", []]) assert.equal(L._truthy(v), false); assert.equal(L._truthy([1]), true); });
test("reload rules", () => {
  assert.equal(L._mustReload("abc", [{ status: 200, body: { fingerprint: "abc" } }]), false);
  assert.equal(L._mustReload("abc", [{ status: 200, body: { fingerprint: "def" } }]), true);
  assert.equal(L._mustReload("abc", [{ status: 200, body: { carsCharging: 1 } }, { status: 200, body: { fingerprint: "abc" } }]), false);
  assert.equal(L._mustReload("abc", [{ status: 404, body: {} }]), true);
});
test("live.js never assigns innerHTML", () => {  // Review Focus 3
  const src = fs.readFileSync(require.resolve("../../lib/TWCManager/Control/static/js/live.js"), "utf8");
  assert.doesNotMatch(src, /innerHTML|insertAdjacentHTML|document\.write/);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/js/*.test.js`
Expected: FAIL, `Cannot find module .../live.js`.

- [ ] **Step 3: Implement `live.js`; refactor `vehicleImage.js` to `drawVehicleImage`**

DOM code runs only when `typeof document !== "undefined"`. Elements are created with `document.createElement` and filled with `textContent`.

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/js/*.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Control/static/js/live.js lib/TWCManager/Control/static/js/vehicleImage.js tests/js/live.test.js
git commit -m "Live pages: shared poller live.js"
```

---

