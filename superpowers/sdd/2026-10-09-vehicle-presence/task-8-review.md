### Spec Compliance
- ✅ Spec compliant. Every brief file has its hunk. One extra, which the controller requested: the home-unset skip in Telemetry._reportLocation, with 3 tests.
- ⚠️ Cannot verify from diff: the 669-pass count and black cleanliness. I did not re-run them.

### Named risk checks
- (a) Serial loop: _checkPresenceTriggers calls only _nominatePresence, which calls VehiclePresence.nominate (VehiclePresence.py:123-135). nominate does a clock read, a short `with self._lock` set update, a debug log and Event.set. There is no I/O and no vehicle callback. OK. recordVehicleVIN (TWCMaster.py:1461) is the same.
- (b) Transient 00: previousState != 0 and reportedState == 0 fires on each flap and adds 3 absolute due times (now+300/1200/2700). nominate does not dedupe: it does `set.update(now + d ...)` on distinct clock values. Passes drain all ready times for a key at once (VehiclePresence.py:253-259), and probes are rate-limited to 60 s per VIN (:226). So probe load is bounded and the departure probes are harmless. Only the `_due` set grows with the flap rate, and entries expire within 45 min. See Minor 1.
- (c) Telemetry: the diff touches only the post-syncSource block in applyDataToVehicle, plus the new _reportLocation method. The vehicleNameTopic branch is untouched. OK.
- (d) Launcher: start() is gated by fakeMaster == 1 and placed after vehicleCommandQueue.start(). stop() sits right after shutdownDeadline, before saveSettings and the drain. vehiclePresence is built in TWCMaster.__init__ (TWCMaster.py:112), so the unconditional stop() is safe even when start() never ran. The lifecycle tests are source-text greps, so they are brittle but adequate.
- (e) HTTP 202: HTTPControl.py has no protocol_version set, so the handler speaks HTTP/1.0 and closes the connection after the response. It writes an empty body and end_headers, so the client does not hang. This is the same pattern as the pre-change code. Content-Length was not added and is not needed. The content-length read at :1374 is on the request side and is unaffected.

### Strengths
- The trigger logic is small and isolated, and previousState is captured before reportedState is overwritten (TWCSlave.py:633 vs :636).
- Tests assert exact nominate arguments, including the VIN fallback chain.
- The guard on home/coordinates avoids bogus "away" observations.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. VehiclePresence.py:128 (reached from TWCSlave.py:113): a Gen2 car flapping 00 and non-00 adds 3 timestamps per flap, never deduped. Memory is bounded by the 45 min expiry. Optionally coalesce delay times within a few seconds, or skip the "unplug" nomination while a departure nomination is already pending.
2. HTTPControl.py: /api/checkArrival and /api/checkDeparture are now identical bodies. Fold them into one branch (`in (...)`) if wanted.
3. tests/unit/test_twcmanager.py: the lifecycle tests grep source text. They check ordering but not behavior. The drain line also exceeds the black line length, but tests/ is excluded from black.

### Assessment
**Task quality:** Approved
**Reasoning:** Non-blocking observers on the serial path, correct gating and ordering, and the HTTP response is safe. Only minor nominate-accumulation and duplication nits remain.
