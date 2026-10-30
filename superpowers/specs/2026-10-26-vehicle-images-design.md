# Vehicle images on the Vehicles pages

Status: open as ngardiner/TWCManager#731 (155b3beb on main d8f036d1), 2026-10-27. The live box runs it as an overlay. Small and whimsical; lands after the 1.4.0 vehicle model.
Inputs: MikeBishop/MMM-Powerwall#110 (`compositor.js`), `2026-10-13-vehicle-model-design.md` (registry, persistence), `2026-10-20-vehicle-watch-design.md` (watch, budget).

## Intent

Show a render of each car (its model, paint and wheels) on the Vehicles list and the Vehicle Detail page, using the Tesla compositor URL builder already written for MMM-Powerwall. Clicking the list picture opens the car's page.

## Non-goals

- No Python port of the mapping tables. One copy of the logic, shared with MMM-Powerwall.
- No image proxying or caching on the Pi. The browser fetches from `static-assets.tesla.com` directly.
- No wakes for an image. At most one extra read per car, and only where nothing else would have read its looks (§2).
- No Fleet Telemetry mapping. Anyone with Fleet Telemetry has a Fleet token, so the one-time read covers them.

## Design

### 1. Appearance on the registry

Five new registry fields: `carType`, `exteriorColor`, `wheelType`, `trimBadging` and `optionCodes`. `Fields.APPEARANCE` maps them to the Tesla API / `compositor.js` names (`car_type`, ...). Separate fields need no merge logic, because TeslaMate delivers one topic at a time anyway.

`Vehicle.appearance()` returns the fields that are set, keyed by the compositor names, and `summary()` includes it. `model_year` isn't stored; the page derives it from the VIN.

Persisted: `VehicleRegistry.toJSON` writes `appearance` beside `name` when it's non-empty. `_loadOne` restores each string value as an unseen (`seen=False`) observation from `persisted`. A car's looks don't change, so once known they're never read again.

### 2. Capture

- **Owner / Fleet API read** (`update_vehicle_data`): `vehicle_config` joins the `endpoints=` list. It rides on a read we already make, so no extra request; Fleet bills per request, not per endpoint. `option_codes` comes from the top level of the response when it's present.
- **TeslaMate**: `model`, `exterior_color`, `wheel_type` and `trim_badging` join `events`, each feeding its own field. `model` maps to `car_type` (`3` → `model3`, `Cybertruck` → `cybertruck`), as MMM-Powerwall's `node_helper.js` does.

  This is kept even though the cars never change. On Phase 6, TeslaMate attaches by VIN from its own database without another source, and while it covers a car the watch makes no cloud reads. On the live box, every appearance field came from TeslaMate, and there were no `vehicle_data` reads in 40 minutes.
- **One-time read** (`Watch._look`, `TeslaAPI.readAppearance`). The trigger: a car covered by a live feed, awake, listed on the Tesla API, with no `carType`. The watch then queues one `vehicle_data?endpoints=vehicle_config` read on the cloud worker.
  - It goes through the read slot (Owner when usable, else Fleet at $0.002).
  - It pays from the watch budget as a routine read. A refusal waits an hour.
  - `get_car_api`'s free online check runs first, so it never wakes the car.
  - A failed read is tried again an hour later. A successful one is never repeated, even if the response carried no config.

  This covers feeds that don't report looks (Fleet Telemetry, or an older TeslaMate).
- **BLE, HomeAssistant, Gen2/Gen3 TWC**: no source. The page falls back to the VIN. A BLE car no feed covers, whose reads all go over the radio, isn't covered by the one-time read; it keeps the VIN picture until a cloud read happens.

### 3. Rendering

- `compositor.js` is copied verbatim to `lib/TWCManager/Control/static/js/compositor.js`, with a header naming the MMM-Powerwall commit it came from (41b318ee). The existing `/static/` handler serves it, and `MANIFEST.in` already grafts `static/`.
- Both templates put each car's appearance JSON and VIN on a hidden `<img class="vehicleImage">` as `data-` attributes. `static/js/vehicleImage.js` then:
  1. builds `config` from the appearance, filling `model_year` from `TeslaCompositor.modelYearFromVin(vin)`;
  2. with no `car_type`, takes it from VIN character 4 (`3`/`Y`/`S`/`X`, plus `C` for Cybertruck), which gives the generation's default paint and wheels;
  3. calls `TeslaCompositor.build(config)` (a 400x225 render), which CSS scales to 160 px wide in the list;
  4. on a `null` URL or an image `onerror`, leaves the `<img>` hidden.
- Placement: a thumbnail column on the left of the Vehicles table, linked to `/vehicleDetail/<VIN>`, and an image above the Vehicle Details table.
- Themes: Modern overrides only its main page. The loader falls back to Default for everything else (`HTTPControl.py`, FileSystemLoader search path), so Modern shows the pictures with no change.

## Testing

- `tests/unit/test_vehicle_appearance.py` covers:
  - `vehicle_config` and `option_codes` mapping;
  - the TeslaMate topic table;
  - `appearance()` omitting unset fields;
  - the persistence round trip as an unseen observation, and a garbled persisted value being ignored;
  - one-time read: once for a covered awake car; none for a known or sleeping car; a failure retried after an hour.
- Changed tests:
  - `test_registry_fields` and `test_registry_vehicle`: they check the exact list of fields and summary keys.
  - `test_vehicles_page`: the first `/vehicleDetail/` link in a row is now the picture's, so its cell indexes shift by one.
  - `test_watch.py::test_a_covered_car_keeps_no_ask_for_later`: the car's looks are now known in that test, so the one-time read stays out of it.
- Live box: page carries TeslaMate's appearance; render fetched and checked by eye (red Model 3, aero wheels); no `vehicle_data` reads after the deploy.
- Not yet checked: the page in a real browser, and the one-time read against a real car (the box's car gets its looks from TeslaMate).
- No JS tests in this repo. `compositor.js` is tested upstream.

## Open questions

1. Is the copied file kept in sync with MMM-Powerwall by hand, or by a small sync script or CI diff check? Default: by hand, with the header recording the source commit.
2. Line budget: about 110 Python lines plus about 370 copied JS lines. The JS is a vendored static asset, not `lib/` logic, but say so in the PR given the shrink target.
