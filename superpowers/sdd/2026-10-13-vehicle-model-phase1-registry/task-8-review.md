### Spec Compliance
Matches the brief and the controller rulings. Focused tests (test_twcmaster_registry, test_settings_lock, test_twcmanager) pass, 46 tests.
- TWCMaster.py saveSettings writes settings["vehicleRegistry"] = toJSON() inside the locked step 1, with the C-encoder comment above json.dumps.
- loadSettings reads the blob under settingsLock after the defaults merge and calls load() outside it, before module updateSettings. The no-file early return leaves the registry empty.
- expireVehicles() queues saveSettings only when something expired.
- lastVehicleExpiry is initialised to time.time() in __init__ (ruling).
- TWCManager.py: the expireVehicles elif is added. The hourly queueing sits after retryVINQuery, outside the fakeMaster block, so expiry is not gated on fakeMaster (ruling).

### Strengths
- No lock inversion. toJSON takes the registry lock (vehicles()) and then each v._lock while settingsLock is held. That follows the documented order (settingsLock -> registry/vehicle locks). Registry and vehicle locks are leaves: nothing under them calls out or touches settingsLock (grep of lib/TWCManager/Vehicle/Registry finds no settings access). Task 7's recordVehicleVIN calls observeTwcVin, which releases the registry lock on return, and only then takes settingsLock, so the locks are never nested the other way round (TWCMaster.py:1464 vs :1482).
- Startup cannot be stopped by a bad registry blob. load() returns early for non-dict data and catches per-vehicle errors. The "corrupt" string case is tested.
- The TWCManager.py expiry queueing is correct. lastVehicleExpiry is reset before queueing, so there is no flood. It runs on the main loop thread and queues to the background thread, where expiry takes only leaf locks. A failure inside expireVehicles is caught by the background thread's try/except.
- Comment placement is good, and tests are small and meaningful (including the init-time test).

### Issues
Critical: none.
Important: none.
Minor:
- TWCMaster.py (saveSettings): self.settings keeps the last serialised "vehicleRegistry" snapshot in memory. It is stale between saves and is never read back. Any code that dumps self.settings elsewhere would expose it. Harmless today.
- test_twcmaster_registry.py: the round-trip test does not check name, userAsserted or lastSeen, and the TWCManager.py wiring is untested (as the brief expected).

### Assessment
**Task quality:** Approved
**Reasoning:** The spec and rulings are met. The registry-under-settingsLock serialisation is lock-order safe, load cannot abort startup, and the untested main-loop and background expiry queueing is correct. Only polish items remain.
