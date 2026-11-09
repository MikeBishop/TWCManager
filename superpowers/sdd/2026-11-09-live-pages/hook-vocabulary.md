### The hook vocabulary (used by Tasks 7–10)

`live.js` reads these attributes; templates write them. Paths are dot-separated over the merged response. A segment applied to an array selects the element whose `key` (else `id`) equals it, else a numeric index. A path starting with `.` is relative to the enclosing keyed-list item.

| Attribute | Effect each poll |
|---|---|
| `data-field="<path>"` `[data-format="<name>"]` | `el.textContent = Format[name](value, ctx)`; without `data-format`, `null`/`undefined` → `""`, else `String(value)`. `ctx = {data, el, item}`. |
| `data-show="<path>"` `[data-show-if="<name>"]` | `el.hidden = !(name ? Format[name](value, ctx) : Live._truthy(value))`. `_truthy`: false for `null`, `undefined`, `false`, `0`, `""`, `[]`. |
| `data-class-if="<path>" data-class-true="<c>" data-class-false="<c>"` | Toggles the two classes by `Live._truthy(value)`. |
| `data-list="<path>" data-row="<name>"` | Replaces the element's children with one `<tr>` per array item, one `<td>` per string in `Format[name](item, ctx)` (text only). |
| `data-keyed-list="<path>" data-template="<id>"` | Keyed by `item.key ?? item.id`: clones `<template id>` for a new key (sets `data-key`), removes gone keys, keeps order, binds hooks inside with `item`. |
| `img[data-image]` inside a keyed entry | On add: `img.dataset.vin = item.vin || ""`, `img.dataset.appearance = JSON.stringify(item.appearance || {})`, then `window.drawVehicleImage(img)` if defined. |

`live.js` never writes `.value`, `.checked` or `.disabled` of a form control and never assigns `innerHTML`.

---

