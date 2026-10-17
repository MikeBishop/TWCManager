### Task 9: Tighten the default `atHomeRadius` to 1,000 ft

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`is_location_home` and its comment), `lib/TWCManager/Vehicle/HomeAssistant.py` (`is_location_home`), `etc/twcmanager/config.json`, `etc/twcmanager/.testconfig.json`, `etc/twcmanager/demo.json` (comments: "The default value is 1000 feet"), `CHANGELOG.md` (v1.4.0)
- Test: `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_homeassistant_presence.py`

**Interfaces:**
- Produces: a module constant `DEFAULT_AT_HOME_RADIUS_FEET = 1000` in TeslaAPI.py and another in HomeAssistant.py. Each module uses its own, so HomeAssistant doesn't import TeslaAPI.
- CHANGELOG line, under v1.4.0 Features, verbatim: `* (@MikeBishop) - Vehicle presence follows the charge cable: a car is home when it is plugged in here, and charge limits are applied only then and restored on unplug. The default atHomeRadius is now 1,000 ft (was 10,560 ft / 2 miles); configs that never set atHomeRadius get the tighter default, so set it explicitly (e.g. 10560) to keep the old radius.`

- [ ] **Step 1: Write the failing tests**

```python
def test_default_radius_is_1000_feet():   # home (0,0); a point 900 ft north -> True; 1100 ft -> False (1 deg = 364488.888 ft)
def test_explicit_radius_still_overrides():  # config atHomeRadius 10560: 5000 ft -> True
# the same two tests for HomeAssistant.is_location_home
```

- [ ] **Step 2: Run the tests and confirm they fail**
- [ ] **Step 3: Implement the constants, comments and CHANGELOG entry**
- [ ] **Step 4: Run the tests and confirm they pass**
- [ ] **Step 5: Commit**

Subject: `Default atHomeRadius to 1,000 ft`.

---

