Show each car's picture on the Vehicles pages

The Vehicles list and each vehicle's page now show a render of the car: its model, paint and wheels. Clicking the picture in the list opens the car's page.

## How

- **Drawing:** the image comes from Tesla's compositor, the same image service the Tesla app uses. The browser builds the URL with `compositor.js`, copied verbatim from MikeBishop/MMM-Powerwall@41b318ee (MMM-Powerwall#110), and fetches the picture straight from `static-assets.tesla.com`. Nothing is proxied or cached on the Pi.
- **Where the looks come from:** five new registry fields hold them (`carType`, `exteriorColor`, `wheelType`, `trimBadging`, `optionCodes`).
  - The Owner/Fleet `vehicle_data` read asks for `vehicle_config` too, with no extra request.
  - TeslaMate's `model`, `exterior_color`, `wheel_type` and `trim_badging` topics fill them as well.
  - The values are saved in `vehicleRegistry`, because a car's looks don't change and a sleeping car reports none.
- **A car a telemetry feed covers:** the watch makes no cloud reads of such a car, so when its looks are unknown and it's awake, the watch makes one `vehicle_data?endpoints=vehicle_config` read.
  - It goes through the read slot, so it's free on the Owner API and $0.002 on Fleet, and it's charged to the watch budget.
  - It never wakes the car, and a failed read is retried an hour later.
- **Fallback:** a car whose looks are unknown is drawn from its VIN, which gives its model's default paint and wheels. If the URL can't be built or the image doesn't load, the image stays hidden.
- **Themes:** Modern falls back to the Default templates for these pages, so it shows the pictures too.

## Size

About 120 lines in `lib/` Python and templates, and 370 lines of vendored JS (`static/js/compositor.js`). The JS is a static asset copied from MMM-Powerwall, not `lib/` logic. Its header names the source commit, and keeping it in sync is by hand.

## Testing

- `tests/unit/test_vehicle_appearance.py` covers the `vehicle_config` mapping, TeslaMate's topics, persistence (as an unseen observation), and the one-time read: once for a covered awake car, never for a known or sleeping car, and retried after an hour.
- Full unit suite: 2463 passed.
- Live box: TeslaMate supplied the looks and the render matched the car (a red Model 3 with aero wheels). No `vehicle_data` reads came from it.
- Not yet exercised live: the one-time read, since the box's car gets its looks from TeslaMate.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
