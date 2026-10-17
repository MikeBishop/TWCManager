# Task 2 review: settings lock (ef9288a..86d26a7)

**Spec verdict: compliant.** Every writer the brief lists takes `settingsLock`. `saveSettings` serialises under the lock and writes outside it. `loadSettings` parses outside the lock and assigns under it. `getSetting` stays unlocked. The acceptance grep finds every assignment, `del` and `.append`/`.remove`/`.pop` in HTTPControl, MQTTControl, TWCManager and TeslaBLE inside a `with master.settingsLock:` block. The CHANGELOG line is there, the 5 brief tests are present verbatim, and `test_settings_lock.py` + `test_twcmaster.py` pass (64 passed, venv Python 3.12.3).

### Spec Compliance
- `TWCMaster.__init__`: `settingsLock = threading.RLock()` is created before `self.settings`, with a comment giving the lock order (TWCMaster.py:~110).
- `saveSettings` (TWCMaster.py:1559-1576): the token merge and `payload = json.dumps(self.settings)` run under the lock. A `TypeError` keeps the old handling (log, `lastSaveFailed=1`, return). The temp write, fsync, backup and replace run outside the lock.
- `loadSettings` (TWCMaster.py:1023-1185): the main file and backup are parsed into `loaded` with no lock held. Assignment, default merge, the missing-file default dict and the VehicleGroups/sunrise/sunset bridge happen under the lock. The step-2 module fan-out (`migrateSavedTokens`, `Vehicle.updateSettings`) stays outside it, as the brief requires.
- Master setters: `setSetting`, `saveNormalChargeLimit`, `removeNormalChargeLimit` (save is queued outside the lock via `changed`), `resetChargeNowAmps`, `setChargeNow*`, `setHomeLat/Lon`, `setHourResume…`, `setkWhDelivered`, `setNonScheduledAmpsMax`, `setSendServerTime`, `setScheduledAmps*` and `snapHistoryData` are all wrapped.
- External sites are wrapped: HTTPControl at :316, :513-518, :627, :813, :889-890, :929, :1332, :1467, :1478, :1625-1626, :1654-1735, :1782-1807 and :1825-1827; MQTTControl.py:178; TWCManager.py:591-592 and :632-633; TeslaBLE.py:868-895.

### Strengths
- **Risk (a), save racing an unlocked writer, is handled, and handled better than before.** The serial thread still adds keys without the lock: `recordVehicleVIN` adds a new VIN under `settings["Vehicles"]` (TWCMaster.py:1441), plus `SlaveTWCs` and `addkWhDelivered` (:145). The background thread can save at the same moment. Moving from `json.dump(self.settings, f)` to `json.dumps` matters here. `json.dump` goes through the pure-Python `_iterencode`, which can switch threads in the middle of iterating a dict. `json.dumps` with default arguments uses the C `_json.Encoder`, which does not run bytecode and so does not give up the GIL partway through. Measured: one thread kept adding and popping `Vehicles` keys while the main thread looped for 4 s on venv 3.12.3 with `switchinterval=1e-6`. `json.dump` raised `RuntimeError: dictionary changed size` 383 times; `json.dumps` raised it 0 times. So the unlocked serial-thread writers cannot crash a save. Before this change they could.
- **Risk (b), lock held across I/O or a module call: none found.** `send_response`, `queue_background_task`, `applyPolicyImmediately`, `carapi.storeToken`/`pasteRefreshToken` (network) and the sunrise HTTP fetch all run outside the lock. Under the lock there are only plain attribute reads of `TeslaTokenSlot` (no properties), `getFieldValue`, `convertAmpsToWatts`/`getRealPowerFactor` (pure master arithmetic), and BLE key serialisation (CPU-only crypto; key generation itself is outside the lock).
- **Risk (c), lock order: no inversion.** `settingsLock` is never held while taking `_bleLock`, `VehicleCommandQueue._cond` or `backgroundTasksLock`, because every `queue_background_task` call sits outside the `with` block. `scanForVehicles` runs only from `updateSettings` during `loadSettings` at startup, does not hold `_bleLock`, and is called after `loadSettings` has released the lock.
- `removeNormalChargeLimit` no longer saves when nothing was removed. `deleteGroup`/consumption-offset `pop(key, None)` avoids a KeyError when two deletes race.
- TeslaBLE iterates over a `list()` copy of the keys while it writes keys.

### Issues

**Critical:** none.

**Important:** none.

**Minor**
1. **A wrong premise in the brief; carry it forward as a spec correction, not as polish.** The brief exempts `stopCarsCharging`'s `respondToSlaves`/`respondToSlavesExpiry` writes (TWCMaster.py:1981-1983) on the grounds that they run on the serial thread. They are also reached from `TeslaAPIEVSE.stopCharging` (EVSEInstance/TeslaAPIEVSE.py:151, via `EVSEController`/`MergedEVSE`). Since #670 that path runs off the serial thread, on the policy thread. `startCarsCharging`'s `respondToSlaves = 1` (:1952) is reached the same way from TeslaAPIEVSE.py:148, and the brief does not list it. These are single-key stores, so they cannot break a save as long as the save stays on the C `dumps` encoder (item 2). That is why this rates Minor, but the ruling's thread premise should be corrected.
2. **The C-encoder guarantee carries weight and nothing protects it.** Approving the unlocked serial-thread writers (`recordVehicleVIN` adding VIN/`SlaveTWCs` keys) depends on `json.dumps(self.settings)` at TWCMaster.py:~1570 staying on `_json.Encoder`. Adding `indent=`, `default=` or `cls=` would silently drop it to the pure-Python `_iterencode`, and the `RuntimeError` race would return. Suggest a one-line comment on that call explaining why it must keep its default arguments.
3. `addkWhDelivered` (TWCMaster.py:145, serial thread, unlocked) is a read-modify-write, and `setkWhDelivered` locks while it does not. A concurrent `setkWhDelivered` can be lost or overwritten. This is exempt by ruling (serial-thread writer), and harmless to the save.
4. TeslaBLE readers at TeslaBLE.py:271-273, :628-630 and :695-697 iterate `settings["Vehicles"].keys()` live. A VIN added by `recordVehicleVIN` on the serial thread can raise `RuntimeError` there. This was already the case before this change and is outside its scope: ruling 3 keeps reads unlocked, and locking them would not help while the serial writer stays unlocked. Iterating over `list(...)` would fix it cheaply, and it belongs with Task 13's TeslaBLE work.
5. The tests cover only the TWCMaster side. Nothing checks that an HTTPControl, MQTT, sunrise or TeslaBLE site takes the lock; the grep acceptance step is the only guard. That is acceptable for a task gate.
6. `process_save_schedule` holds the lock over about 80 lines, including parsing that can raise (`int(...[:2])`, KeyError on `Schedule["Common"]`). The `with` releases the lock correctly on an exception, and none of it is I/O (I checked that `getFieldValue`, HTTPControl.py:1585, only parses `self.fields`), so this is only a note.

### Verification notes
- I checked: `getSlaveTWCs` (TWCMaster.py:957) returns a plain list and takes no lock, so `snapHistoryData` cannot invert `settingsLock`/`backgroundTasksLock`. The read-only aliases at HTTPControl.py:243 and :1539 are never written through. The `saveSettings` `PermissionError` and `(TypeError, OSError, IOError)` handlers, and the temp-file cleanup, are intact after the restructure. The commit trailer is `Co-Authored-By: Claude Opus 5.5`, which matches global-constraints, so the implementer's trailer worry is moot.
- I did not check: I ran only the focused tests (64). The full-suite "820 passed" is the implementer's claim.

### Assessment
**Task quality:** Approved

**Reasoning:** Every writer in the brief is covered, and the acceptance grep is clean. Saves snapshot under the lock and do their I/O outside it. No lock is held across I/O or a module call, and the lock order is consistent with `_bleLock → settingsLock → leaf locks`. The main concurrency risk, a save racing the unlocked serial-thread writers, is neutralised in practice by the switch to the C `json.dumps` encoder, which I measured. The remaining items are coverage notes for writers the brief exempts or does not list, none of which can corrupt or crash a save.
