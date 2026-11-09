### Task 7: Docs and changelog

**Files:**
- Modify: `docs/modules/Vehicle_TeslaAPI.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1:** Add an installer FAQ entry: with Fleet only, charge history fills in a few minutes late but correct, at no API cost; for live data (green tracking that follows the sun minute by minute) use Fleet Telemetry, BLE, or an EVSE that reports current. Capabilities, not internals; "EVSE", not "charger".
- [ ] **Step 2:** `git describe --tags --abbrev=0`; check whether the TWC-less watch (`Watch.py` `cloudOnly`) shipped in that tag (`git show <tag>:lib/TWCManager/Vehicle/Watch.py`). Shipped: one Bugfixes line ("Fix charge history missing sessions for cars read only through the Fleet API."). Not shipped: one Features line. 1-2 sentences, verb first.
- [ ] **Step 3: Commit** `docs: explain Fleet-only charge history`

---

