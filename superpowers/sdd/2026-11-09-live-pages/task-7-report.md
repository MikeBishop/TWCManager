# Task 7 report: live.js and live vehicle pictures

Commit: c70fd355 Live pages: shared poller live.js

## Implemented
- `lib/TWCManager/Control/static/js/live.js` (new): classic script, one global `Live`, `module.exports` under Node. No jQuery, no innerHTML/insertAdjacentHTML/document.write, never writes .value/.checked/.disabled.
  - Pure helpers: `_lookup` (key, then id, then numeric index on arrays; leading `.` = relative to item; `"."` = item itself), `_truthy`, `_mustReload`, `_itemKey` (key ?? id, stringified), `_callFormat` (empty/unknown name -> "no formatter", unknown warns once per name; a throwing formatter returns {ok:false} and logs console.error once per name).
  - `bind(root, data, item)`: keyed lists first, then data-list, data-field, data-show, data-class-if. Each hook belongs to its innermost `[data-key]` entry; entries are bound with their own item, so nested lists work and no hook is bound twice. A formatter throwing leaves that element unchanged. textContent/hidden only written when changed. data-list rows rebuilt only when the cell strings change; unknown/throwing row formatter leaves rows untouched.
  - Keyed list: clones `<template id>` first element child, sets data-key, removes gone keys, reorders with insertBefore (existing nodes are moved, not recreated), skips items with no key or duplicate key. New `img[data-image]` gets data-vin / data-appearance then `window.drawVehicleImage(img)` if defined.
  - `start({urls, interval, fingerprint})`: fetch all with `cache: "no-store"`; 404 or fingerprint mismatch -> `location.reload()`. Non-404 HTTP errors and network errors -> keep values, show `div.live-offline` "Can't reach TWCManager" at top of body; hidden on next success. setTimeout chain (no overlapping polls), paused while hidden, immediate fetch on visibilitychange to visible. Data object rebuilt each poll (string url -> Object.assign, [url,key] -> data[key]). `onData` handlers called after each bind, each in try/catch.
- `vehicleImage.js`: per-image body is now `window.drawVehicleImage(img)`; jQuery on-ready loop calls it. Behaviour unchanged.

## Tests
`node --test tests/js/*.test.js` -> 27/27 pass, no console noise.
tests/js/live.test.js: brief's four tests plus lookup edge cases, _itemKey, _callFormat (unknown warns once, throw logs once), and a source check that no form-control state is assigned.

TDD: RED: `node --test tests/js/live.test.js` -> "Error: Cannot find module '../../lib/TWCManager/Control/static/js/live.js'" (expected, file not yet created). GREEN: 27/27 after implementation.

## Concerns / decisions
- No browser or jsdom available (no npm), so DOM code (bind, keyed list, polling) is untested by execution; kept small and reviewed by hand.
- `_mustReload` skips the fingerprint comparison when the page passes no fingerprint (pageFingerprint == null), so pages without one never reload on fingerprint.
- Non-404 HTTP errors (e.g. 500) are treated like unreachable (notice shown), not reload.
- Templates must give `<template>` a single root element; uses `Element.replaceChildren` (modern browsers).

## Browser check (coordinator request): BLOCKED, not run
Playwright and Chromium are not in this container:
- `require('playwright')` gives MODULE_NOT_FOUND, with NODE_PATH empty and no playwright directory under any node_modules (searched to depth 6).
- There is no chromium/chrome binary and no ms-playwright cache (only AppArmor profiles /etc/apparmor.d/chromium and /etc/apparmor.d/chrome), and Python has no playwright module either.
- There is also no npm to install it with. I did not run `playwright install`, as instructed.

The harness is written and ready, outside the repo, in
/tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/livejs-check/
- page.html loads the real format.js and live.js through routes on http://t/.
- run.js routes the APIs through page.route. It covers everything on the request list: data-field with, without and unknown data-format, null to "", and the [url,key] merge; data-show and data-show-if; data-class-if; data-list rows, including no rebuild when unchanged; keyed-list add, update in place (checked by object identity), remove and reorder, with relative .field paths and the drawVehicleImage stub called only for new entries; the offline notice shown, values kept, notice hidden on recovery and created only once; visibility pause and the immediate fetch on return; reload on fingerprint mismatch and on 404; and a throwing formatter leaving its own element as it was while the others update.
Run with: `node run.js` from that directory once playwright and Chromium are available.
No changes to live.js. Nothing new to commit.

## Follow-up round
Commit: 1afe74dc Live pages: live.js isolates failures, times out requests, styles its notice
Only live.js and tests/js/live.test.js changed (live.js had not been touched since c70fd355).

### Fixes
1. Exceptions from outside formatters are now contained. Each hook element is bound inside `L._guard(selector, ...)`. Creating a keyed entry is guarded per entry: if the `<template>` is missing, that entry is skipped and retried on the next poll. `window.drawVehicleImage` is guarded per image, and the entry is still added if it throws. Each failure is logged once per key through `L._logOnce`.
2. Requests now time out: each poll gets an AbortController that aborts after 2× interval. An abort counts as a failure, so the offline notice shows and the next interval retries.
3. data-list now uses `L._rowCells(name, items, ctx)`, which returns null (rows left untouched) for an unknown or throwing row formatter. This now also holds for an empty array.
6. "update failed" is logged once (`_logOnce("update")`) and re-armed by `_clearLog("update")` only after a successful apply.
R13. The `.live-offline` notice is styled through el.style: padding, margin, background #f8d7da, colour #721c24, border 1px #f5c6cb, radius. The text is unchanged.

### Node tests
`node --test tests/js/*.test.js` gives tests 31, pass 31, fail 0. New tests:
- `_guard`: swallows the exception and logs once until cleared.
- `_logOnce` / `_clearLog`: re-arming.
- `_rowCells`: returns rows, and null for an unknown name (empty and non-empty arrays) and for a throwing formatter.

### Browser check (Playwright Python, Chromium)
Harness (outside the repo): /tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/livejs-check/run.py + page.html
Command: `/root/venv/bin/python run.py`. It loads the real format.js and live.js from the repo; the APIs are served through page.route.
All 36 checks PASS:
- data-field: plain value; with data-format (count); throwing formatter keeps its text while the others update; unknown formatter treated as none; missing value gives ""; [url,key] stored at data[key].
- data-show: truthy and flipped; data-show-if hides and flips.
- data-class-if: true and false classes.
- data-list: rows rendered, not rebuilt when unchanged, replaced when changed; unknown row formatter leaves the static rows alone for an empty array.
- Keyed list with <template>:
  - add, with relative `.name`/`.amps` paths through a formatter;
  - remove, add and reorder in one poll, and reorder only;
  - an existing entry is updated in place (same DOM node);
  - drawVehicleImage stub gets data-vin and data-appearance, is called only for new entries, and is isolated when it throws.
- Isolation: a missing <template id> and a class token with a space are each contained, and the rest of the page still binds.
- onData is called.
- Offline: the notice is the first child of body, with class live-offline, the exact text, and computed bg rgb(248,215,218) / colour rgb(114,28,36). Values are kept while offline. The notice is hidden on the next success, and only one notice element is ever made.
- A hung request times out: the notice shows, then clears on the next successful poll.
- Visibility: no requests while hidden; immediate fetch on becoming visible.
- Reload: fingerprint mismatch reloads; 404 reloads.
- Console: each guarded failure logged once per page load.

### Concern
A permanent 404 reloads the page on every first poll, so it reloads in a loop. That is what the spec asks for; the server page for a gone URL should not start live.js. Not changed.
The CancelledError tracebacks printed at exit are Playwright teardown of the deliberately hung route (harness noise).
