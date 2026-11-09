## Global Constraints

- Python 3.8 (`python_requires=">= 3.8"`): no `X | Y` types, no `list[str]` annotations, no `str.removeprefix`.
- Endpoints are GET, return JSON with `Cache-Control: no-store`, same access as the existing `/api/get*` routes; `/api/getVehicle/` is a prefix match.
- Handlers read cached state only: never `vehicle.read()`, `Gen3TWC.refreshVitals()`, or any provider/network I/O; no long-held locks.
- No token, refresh token, client secret or webhook URL in any response.
- Times are epoch seconds; each response carries `now` (server epoch seconds); ages are computed from `now`, never the browser clock.
- Python keeps no copy of wording JS produces. Templates render structure and placeholders, never a formatted live value.
- Today's text is the spec for every formatter (exact strings below). No layout or wording changes beyond what moving the formatting requires.
- `format.js` and `live.js` are classic scripts defining one global each (`Format`, `Live`) and `module.exports` when `module` exists. No `.mjs`. No jQuery in either.
- Scripts load per page in the templates that use them, not in `bootstrap.html.j2`.
- JS tests: `tests/js/*.test.js`, CommonJS, run with `node --test tests/js/*.test.js`. No package.json.
- Polling: 3 s on both home pages, 5 s on Policy, Vehicles, Vehicle details; paused while `document.visibilityState === "hidden"`, immediate fetch on return.
- User-facing docs describe capabilities, not internals; say "EVSE" or "charging station", never "charger", for the wall unit.
- `/api/getSlaveTWCs` keeps its exact output.
- Never commit `.github/workflows/` (the PAT rejects it); the CI step is handed to the operator in Task 11.

