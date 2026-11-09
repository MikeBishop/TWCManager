# PR: refactor/readability-reconcile

````markdown
Readability: name what the vehicle reconciler's values hold

This is a readability pass over the vehicle reconciler (`Vehicle/Reconcile/`), the provider order and the vehicle registry entry. It changes no behaviour. Most of it is renames: names that read as speech or puns (`said`, `standIn`, `uncompleted`) now say what they return. One name said the opposite of its contents: `VEHICLE_SOURCES_EXCLUDED` holds the TWC sources. In `plan()`, one-letter names and words reused for different things (`wakes` had three meanings, `held` and `limit` two each) now each have one name per meaning.

The rest are small in-place changes. Tuples read by index (`Presence.decide(...)[1]`, `applicable(...)[0]`) are unpacked where they are used. `and`/`or` chains that leaned on precedence are parenthesised, and the hardest ones (`paidAgain`, the held-branch exit) are split into named conditions. A `pass` branch and a bool added to an int are gone. The magic paid-send count `2` and the unread-limit reason string are now named constants. Compressed comments are rewritten as plain sentences. `ProviderOrder` drops an index tie-break, because the sort is stable and the list is already in registration order.

Where a condition used to evaluate lazily (`Presence.decide`, `Presence.applicable`, the paid retry checks), the rewrite keeps the same short-circuiting, so nothing that was skipped before runs now.

Main renames (old -> new):

- `Rules.VEHICLE_SOURCES_EXCLUDED` -> `TWC_SOURCES`
- `VehicleReconciler.said` / `_said` / `_sayOnce` -> `blockedReason` / `_blockedReasons` / `_logBlockedOnce`
- `VehicleReconciler.wake()` -> `nudge()`, since it only wakes the reconciler's loop
- `Belief.standIn` -> `twcChargingState`, `uncompleted` -> `unlessLimitRaised`, `handsOff` -> `whyHandsOff`, `_newer` -> `newerReadings` (now public; the reconciler used it)
- `AttemptRecord.paidSaw` -> `beliefAtPaidSend`
- In `plan()`: `d` -> `want`, `k` -> `belief`, `p` -> `provider`, `ch` -> `freeChannel`, `dl`/`limit` -> `limitWant`/`limitRec`, `back` -> `returnedAt`, `ride` -> `startWillWake`, `asleep` -> `notSeenAwake`, `holder` -> `lastProvider`, `held` -> `saved` (and `_held()` -> `_saved()`); `wakes` split into `asleepHoldNowWanted`, `wantsWake`, `wakes`; new `retryDue`, `wakeCheckDue`
- In `Run.runAttempt`: `ble`/`quiet`/`known`/`check` -> `bleCommand`/`noWakeBle`/`sleepInWindow`/`pingFirst`
- In `Rules`: `HeldLimit` parameters `held` -> `saved`, `ours` -> `heldLimit` (a percentage, not a time)
- New constants: `PAID_SENDS_PER_ARM`, `Outcome.UNREAD_REASON`
- The `B.`/`R.` module aliases in the reconciler are now direct imports

Evidence: full suite (`pytest tests --ignore=tests/API --ignore=tests/integration`): 2618 passed, 1 xfailed. The only test changes follow the renames.

Changelog: none (no behaviour change)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
````

## Commits
```
cd0dc968 Tighten names left ambiguous by the readability pass
0db7178d Simplify telemetryState and the observe hook in Vehicle
5136699a Drop the redundant registration-index tie-break in ProviderOrder
4c4c01b9 Name what the reconciler's plan and belief helpers hold
```
## Diff
```diff
diff --git a/lib/TWCManager/Control/HTTPControl.py b/lib/TWCManager/Control/HTTPControl.py
index fe7d448a..f7d75217 100644
--- a/lib/TWCManager/Control/HTTPControl.py
+++ b/lib/TWCManager/Control/HTTPControl.py
@@ -211,7 +211,7 @@ def pendingCommands(master, vehicle):
         if rec is None:
             continue
         sent, last = rec.inFlight, rec.lastOutcome
-        why = master.reconciler.said(vehicle.key, aspect)
+        why = master.reconciler.blockedReason(vehicle.key, aspect)
         if sent:
             why = "sending via %s, started %s" % (
                 sourceName(sent.provider),
diff --git a/lib/TWCManager/Vehicle/Providers/Order.py b/lib/TWCManager/Vehicle/Providers/Order.py
index 576cc630..9727af22 100644
--- a/lib/TWCManager/Vehicle/Providers/Order.py
+++ b/lib/TWCManager/Vehicle/Providers/Order.py
@@ -1,7 +1,7 @@
 # The fixed provider order: cheapest cost tier first, then the provider's
-# rank, then registration order. Every vehicle operation walks it. Nothing
-# here holds a lock; the provider list is replaced, never mutated, so a walk
-# works on a snapshot.
+# rank, then registration order (the sorts are stable). Every vehicle
+# operation walks it. Nothing here holds a lock; the provider list is
+# replaced, never mutated, so a walk works on a snapshot.
 import json
 import logging
 import time
@@ -40,18 +40,12 @@ class ProviderOrder:
                 return p
         return None
 
-    def _indexed(self):
-        return list(enumerate(self._providers))
-
     def providers(self) -> List[Provider]:
-        return [p for _, p in sorted(self._indexed(), key=lambda e: (e[1].rank, e[0]))]
-
-    def _key(self, provider, capability, index) -> tuple:
-        return (provider.cost(capability).tier, provider.rank, index)
+        return sorted(self._providers, key=lambda p: p.rank)
 
     def ordered(self, capability) -> List[Provider]:
         found = []
-        for index, p in self._indexed():
+        for p in self._providers:
             if capability not in p.declarations():
                 continue
             if self.suppressions.suppressed(p, capability):
@@ -62,8 +56,8 @@ class ProviderOrder:
             except Exception as e:
                 logger.debug("%s available() raised %s", p.name, type(e).__name__)
                 continue
-            found.append((self._key(p, capability, index), p))
-        return [p for _, p in sorted(found, key=lambda e: e[0])]
+            found.append(p)
+        return sorted(found, key=lambda p: (p.cost(capability).tier, p.rank))
 
     def _ready(self, provider, vehicle, capability) -> bool:
         try:
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index 5e6d6325..46c3d6c9 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -6,7 +6,7 @@ from typing import Optional
 from ..Registry.Fields import FEED_LAG
 from ..Presence import NOT_HOME, pluggedNow, presence
 from .Desired import AMPS, CHARGE_LIMIT, CHARGING, FIELD_FOR
-from .Rules import releases, VEHICLE_SOURCES_EXCLUDED
+from .Rules import releases, TWC_SOURCES
 
 # Sources whose every reading came from the car itself. Exact source
 # names; Fleet Telemetry always counts
@@ -17,21 +17,19 @@ LIVE_READ_SOURCES = frozenset(
 POWER_FLOWING_AMPS = 1.0
 
 
-def _newer(vehicle, field, since, twc=False):
+def newerReadings(vehicle, field, since, twc=False):
     # Each vehicle (or TWC) source's own newest reading of field after since:
     # a republish by one source never hides another's live read
     return [
         obs
         for source, obs in vehicle.reported(field).items()
-        if (source in VEHICLE_SOURCES_EXCLUDED) == twc
-        and obs.at > since
-        and obs.value is not None
+        if (source in TWC_SOURCES) == twc and obs.at > since and obs.value is not None
     ]
 
 
-def standIn(vehicle):
+def twcChargingState(vehicle):
     # The newest TWC current, as the car's charging state
-    reads = _newer(vehicle, "actualCurrent", float("-inf"), twc=True)
+    reads = newerReadings(vehicle, "actualCurrent", float("-inf"), twc=True)
     if not reads:
         return None
     obs = max(reads, key=lambda r: r.at)
@@ -39,7 +37,7 @@ def standIn(vehicle):
     return obs._replace(value="Charging" if flowing else "Stopped")
 
 
-def uncompleted(vehicle, obs):
+def unlessLimitRaised(vehicle, obs):
     # "Complete" read before our last limit write above the battery level
     # (or with the level unknown) is no longer true: the car can charge again
     write = vehicle.lastWrite(FIELD_FOR[CHARGE_LIMIT])
@@ -51,17 +49,17 @@ def uncompleted(vehicle, obs):
 
 
 def known(vehicle, aspect, desired=None):
-    obs = vehicle.believed(FIELD_FOR[aspect], exclude=VEHICLE_SOURCES_EXCLUDED)
+    obs = vehicle.believed(FIELD_FOR[aspect], exclude=TWC_SOURCES)
     if aspect != CHARGING:
         return obs
-    obs, twc = uncompleted(vehicle, obs), standIn(vehicle)
+    obs, twc = unlessLimitRaised(vehicle, obs), twcChargingState(vehicle)
     if obs is None:
         # A car no vehicle source describes (anonymous, non-Tesla): the TWC
         # current stands in. It never adopts
         return twc
-    # For a start, current at the car's TWC now (a heartbeat within
-    # FEED_LAG) and since its last reading is the car charging: without a
-    # live feed that reading may be stale
+    # For a start, the TWC current wins when it is recent (a heartbeat
+    # within FEED_LAG), newer than the car's last reading, and flowing.
+    # Without a live feed the car's reading may be stale.
     fresh = twc and twc.at > max(obs.at, vehicle._clock() - FEED_LAG)
     if desired is True and fresh and twc.value == "Charging":
         return twc
@@ -70,12 +68,12 @@ def known(vehicle, aspect, desired=None):
 
 def newerReading(vehicle, aspect, since) -> bool:
     field = FIELD_FOR[aspect]
-    if aspect == CHARGING and vehicle.believed(field, VEHICLE_SOURCES_EXCLUDED) is None:
-        # Only while known uses the stand-in: for a car a vehicle source
-        # describes, the heartbeat's readings are never evidence
-        obs = standIn(vehicle)
+    if aspect == CHARGING and vehicle.believed(field, TWC_SOURCES) is None:
+        # Only while known uses the TWC's charging state: for a car a vehicle
+        # source describes, the heartbeat's readings are never evidence
+        obs = twcChargingState(vehicle)
         return obs is not None and obs.at > since
-    return bool(_newer(vehicle, field, since))
+    return bool(newerReadings(vehicle, field, since))
 
 
 def reachedCar(vehicle, field, since, beliefAtSend) -> bool:
@@ -83,11 +81,11 @@ def reachedCar(vehicle, field, since, beliefAtSend) -> bool:
     # TeslaMate republishing an unchanged value is no evidence
     return any(
         obs.source in LIVE_READ_SOURCES or obs.value != beliefAtSend
-        for obs in _newer(vehicle, field, since)
+        for obs in newerReadings(vehicle, field, since)
     )
 
 
-def handsOff(vehicle, aspect, desired, known, config=None) -> Optional[str]:
+def whyHandsOff(vehicle, aspect, desired, believed, config=None) -> Optional[str]:
     if aspect != CHARGING:
         return None
     config = config or {}
@@ -98,18 +96,18 @@ def handsOff(vehicle, aspect, desired, known, config=None) -> Optional[str]:
             return "battery below minChargeLevel"
         return None
     # Our own write counts until a newer reading
-    limit = vehicle.believed("chargeLimit", VEHICLE_SOURCES_EXCLUDED)
+    limit = vehicle.believed("chargeLimit", TWC_SOURCES)
     limit = limit.value if limit is not None else None
     if battery and limit and battery >= limit:
         # The car would refuse the start
         return "battery at its charge limit"
-    return _refusesStart(vehicle, known, config)
+    return _refusesStart(vehicle, believed, config)
 
 
-def _refusesStart(vehicle, known, config) -> Optional[str]:
+def _refusesStart(vehicle, believed, config) -> Optional[str]:
     # Whatever its limit, the car cannot take a start, or must not get one
-    if known is not None and known.value in ("Disconnected", "NoPower"):
-        return "the car cannot charge (%s)" % known.value
+    if believed is not None and believed.value in ("Disconnected", "NoPower"):
+        return "the car cannot charge (%s)" % believed.value
     if vehicle.value("scheduledChargingPending") is True and config.get(
         "respectVehicleSchedule", True
     ):
@@ -123,12 +121,18 @@ def _wontCharge(master, vehicle) -> Optional[str]:
     # is applied; None when it would (unknown limit or battery: it would)
     key, desired = vehicle.key, master.desired
     pending = desired.get(key, CHARGE_LIMIT)
-    held = master.heldLimits.get(vehicle.vin) if vehicle.vin else None
-    limit, battery = known(vehicle, CHARGE_LIMIT), vehicle.value("batteryLevel")
-    limit = believed = limit and limit.value
+    saved = master.heldLimits.get(vehicle.vin) if vehicle.vin else None
+    battery = vehicle.value("batteryLevel")
+    belief = known(vehicle, CHARGE_LIMIT)
+    believed = belief.value if belief is not None else None
     state = known(vehicle, CHARGING)
-    if pending is not None and not (releases(pending) and not held):
-        limit = held.outside if releases(pending) else pending.value
+    # The limit once pending is applied: a release puts back the saved
+    # outside limit, and with none saved leaves the car's own
+    limit = believed
+    if pending is not None and not releases(pending):
+        limit = pending.value
+    elif pending is not None and saved is not None:
+        limit = saved.outside
     # Unplugged is known only by a reading
     plugged = pluggedNow(master, vehicle, None)
     if presence(master, vehicle) == NOT_HOME or plugged is False:
@@ -146,8 +150,9 @@ def wouldCharge(master, vehicle) -> bool:
 
 
 def whyQuiet(master, vehicle) -> Optional[str]:
-    # Why the car is expected to quiesce, or None when it will charge. Room
-    # is the control tick's admission, a set swapped whole
+    # Why the car is expected to stay quiet, or None when it will charge.
+    # Room to start is the control tick's admission set, which the tick
+    # replaces whole rather than changing in place.
     reason = _wontCharge(master, vehicle)
     if reason or vehicle.key not in getattr(master, "admission", ()):
         return reason or "no room to start"
diff --git a/lib/TWCManager/Vehicle/Reconcile/Desired.py b/lib/TWCManager/Vehicle/Reconcile/Desired.py
index 4827ae95..7501d9eb 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Desired.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Desired.py
@@ -85,16 +85,16 @@ class AttemptRecord:
         paidSends=0,
         paidReached=False,  # one of them got an answer other than UNREACHABLE
         paidAt=None,
-        paidSaw=None,
+        beliefAtPaidSend=None,
         paidRetryDue=False,  # that request failed and its one blind retry is unused
         rearmed=False,  # the desire's one re-arm of its paid sends is used
         # The provider whose wake the car did not answer on the last paid
         # send: the command never went (Reconciler's WAKE_CHECK)
         wakeCheckBy=None,
         settledAt=None,
-        heldAt=None,  # a hold: when, and the paid requests attempts that held made
+        heldAt=None,  # when the last attempt held, sending nothing
         checkedAt=0,  # a cloud hold's last free online check
-        paidSpent=0,
+        paidSpent=0,  # the paid requests (wake, read) that attempts which held made
         unread=0,  # sends that found the current value unreadable (a limit's backstop)
         clearedValue=None,  # the value a clearIf withdrew; set() may take the record back
     )
@@ -315,7 +315,8 @@ class DesiredStore:
                 record.lastOutcome = outcome
                 record.lastOutcomeAt = now
                 record.lastProvider = attempt.provider
-                record.unread += outcome.detail.startswith("rules: could not read")
+                if outcome.detail == O.RULES + O.UNREAD_REASON:
+                    record.unread += 1
             sent = not O.isNotSent(outcome)
             if sent and outcome.kind not in O.EXCLUDING:
                 # Even for a replaced desire: a start still in flight when
@@ -342,19 +343,18 @@ class DesiredStore:
                     record.paidAt = now
             if current and outcome.kind in O.SETTLED and not held:
                 record.settledAt = now
-            if paid or held:
-                pass
-            elif outcome.kind in O.SETTLED or outcome.detail == "pairing":
-                # Inside the pairing window the car answers, refusing the key
-                # until the card is tapped: the channel works, and the paid
-                # fallback waits
-                state.free.success(now)
-            elif sent and (
-                # A failure of the free channel needs a request to it
-                outcome.kind in O.RETRYABLE
-                or outcome.kind == O.REFUSED
-            ):
-                state.free.failure(now)
+            if not (paid or held):
+                if outcome.kind in O.SETTLED or outcome.detail == "pairing":
+                    # Inside the pairing window the car answers, refusing the
+                    # key until the card is tapped: the channel works, and the
+                    # paid fallback waits
+                    state.free.success(now)
+                elif sent and (
+                    # A failure of the free channel needs a request to it
+                    outcome.kind in O.RETRYABLE
+                    or outcome.kind == O.REFUSED
+                ):
+                    state.free.failure(now)
             if outcome.kind == O.REFUSED or (current and outcome.kind in O.EXCLUDING):
                 # UNSUPPORTED can depend on the value: a superseded one's not
                 record.exclude(attempt.provider, outcome.kind)
diff --git a/lib/TWCManager/Vehicle/Reconcile/Outcome.py b/lib/TWCManager/Vehicle/Reconcile/Outcome.py
index 5dbc3bf6..f28269df 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Outcome.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Outcome.py
@@ -54,6 +54,8 @@ NOT_SENT = QUEUE_DETAILS | {
 RULES = "rules: "
 # A message the car's whereabouts hold back: kept, not settled
 HELD = RULES + "held: "
+# The rules could not read the car's current limit, so sent nothing
+UNREAD_REASON = "could not read the current limit; nothing sent"
 
 
 class Outcome(NamedTuple):
diff --git a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
index 6293760b..3f0ba451 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
@@ -24,8 +24,9 @@ from ..Providers import Capability as C
 from . import Run
 from .Desired import AMPS, CAPABILITY_FOR, CHARGE_LIMIT, CHARGING, FIELD_FOR, Attempt
 from . import Outcome as O
-from . import Belief as B
-from . import Rules as R
+from .Belief import known, newerReading, newerReadings, reachedCar
+from .Belief import whyHandsOff, whyQuiet
+from .Rules import TWC_SOURCES, decideChargeLimit, needsLiveRead, releases, satisfied
 
 logger = logging.getLogger(__name__.split(".")[0] + ".Vehicle.Reconcile")
 
@@ -52,6 +53,9 @@ LIMIT_THEN_START_GAP = 5.0
 MIN_SEND_GAP = {CHARGE_LIMIT: 10.0, CHARGING: 10.0, AMPS: 15.0}
 # The most paid sends, and wakes and reads for held attempts, per desire
 PAID_BUDGET = 4
+# The most paid sends per arm: one send, then one more after a failure or
+# a reading that reached the car. A desire is re-armed at most once
+PAID_SENDS_PER_ARM = 2
 # A limit held unsent for one of these (both NOT_SENT) cannot be delivered
 _REFUSALS = frozenset({"wake refused", "no command token"})
 
@@ -69,8 +73,9 @@ def _tier(provider, capability) -> int:
 
 
 class VehicleReconciler(threading.Thread):
-    # A car whose charging state nothing has given (after a restart) may be
-    # woken for a start once a run, which learns it; False: never
+    # After a restart, nothing may have given a car's charging state yet.
+    # Such a car may be woken for a start once per run, and that wake
+    # learns the state. False never wakes it for this.
     wakeUnreadOnce = True
 
     def __init__(self, master, clock=time.time):
@@ -82,7 +87,7 @@ class VehicleReconciler(threading.Thread):
         self._stopping = False
         # (key, aspect) -> the last hands-off or no-candidate message, so
         # each is logged once; pruned to the store's keys every pass
-        self._said: Dict[Tuple[str, str], str] = {}
+        self._blockedReasons: Dict[Tuple[str, str], str] = {}
         # The cars a start has woken, once its wake was sent
         self._wokeUnread = set()
         self.ble, self.cloud = (
@@ -97,9 +102,10 @@ class VehicleReconciler(threading.Thread):
             )
             for name in ("ble", "cloud")
         )
-        self.desired.changed = self.wake
+        self.desired.changed = self.nudge
 
-    def wake(self, *args) -> None:
+    def nudge(self, *args) -> None:
+        # Runs a pass now rather than at the next TICK
         self._event.set()
 
     def start(self) -> None:
@@ -159,18 +165,20 @@ class VehicleReconciler(threading.Thread):
             except Exception as e:
                 logger.warning("Vehicle reconciler pass raised %s", type(e).__name__)
 
-    def _sayOnce(self, key, aspect, message, level) -> None:
-        if self._said.get((key, aspect)) != message:
-            self._said[(key, aspect)] = message
+    def _logBlockedOnce(self, key, aspect, message, level) -> None:
+        if self._blockedReasons.get((key, aspect)) != message:
+            self._blockedReasons[(key, aspect)] = message
             logger.log(level, "%s %s: %s", key, aspect, message)
 
-    def said(self, key, aspect) -> Optional[str]:
-        return self._said.get((key, aspect))
+    def blockedReason(self, key, aspect) -> Optional[str]:
+        return self._blockedReasons.get((key, aspect))
 
     def pass_(self, now=None) -> int:
         now = self._clock() if now is None else now
         keys = self.desired.keys()
-        self._said = {k: m for k, m in self._said.items() if k[0] in keys}
+        self._blockedReasons = {
+            k: m for k, m in self._blockedReasons.items() if k[0] in keys
+        }
         planned = []
         for key in keys:
             vehicle = self.master.vehicleRegistry.get(key)
@@ -213,27 +221,29 @@ class VehicleReconciler(threading.Thread):
                 )
         return submitted
 
-    def _adoptable(self, vehicle, d) -> Optional[Any]:
+    def _adoptable(self, vehicle, want) -> Optional[Any]:
         # A vehicle read newer than our write and the desire, disagreeing
         # with what we wrote, is the user's change: the value, else None
         field = FIELD_FOR[CHARGE_LIMIT]
-        latest = vehicle.latestFrom(field, exclude=R.VEHICLE_SOURCES_EXCLUDED)
+        latest = vehicle.latestFrom(field, exclude=TWC_SOURCES)
         write = vehicle.lastWrite(field)
-        if latest is None or write is None or latest.at <= max(write.at, d.at):
+        if latest is None or write is None or latest.at <= max(write.at, want.at):
             return None
-        if vehicle.trusted(field, exclude=R.VEHICLE_SOURCES_EXCLUDED) != latest:
+        if vehicle.trusted(field, exclude=TWC_SOURCES) != latest:
             return None
         return latest.value if latest.value != write.value else None
 
     def plan(self, vehicle, aspect, now) -> Optional[Attempt]:
         key = vehicle.key
-        d = self.desired.get(key, aspect)
+        want = self.desired.get(key, aspect)
         rec = self.desired.record(key, aspect)
-        if d is None or rec.inFlight is not None:
+        if want is None or rec.inFlight is not None:
             return None
         # A drive's hold can change only once the car stops
-        driving = rec.lastOutcome == (O.SATISFIED, O.HELD + "driving")
-        driving = driving and Presence.decide(self.master, vehicle)[1] == "driving"
+        driving = rec.lastOutcome == O.Outcome(O.SATISFIED, O.HELD + "driving")
+        if driving:
+            _, decidedBy, _ = Presence.decide(self.master, vehicle)
+            driving = decidedBy == "driving"
         if self._asleepCheckDue(vehicle, rec, now):
             # The free online check alone: its answer is an observation, so
             # an awake car is a sign of life that plans this again, and an
@@ -244,19 +254,24 @@ class VehicleReconciler(threading.Thread):
             return None
         waiting = rec.heldAt is not None
         if waiting and (vehicle.lastObservedAt <= rec.heldAt or driving):
-            # Held: only newer evidence (or a new desire) plans it again. An
-            # asleep hold went without a wake, the car not then expected to
-            # charge; once it is (admitted, its plug no longer known
-            # unplugged), that changed here, with no word from the car
-            wakes = not (driving or d.restore or d.value is False)
-            if not (wakes and rec.lastOutcome == O.ASLEEP) or B.whyQuiet(
-                self.master, vehicle
-            ):
+            # Held: only newer evidence (or a new desire) plans it again. The
+            # exception is an asleep hold, which went without a wake because
+            # the car was not then expected to charge. Once it is (admitted,
+            # its plug no longer known unplugged), that changed here, with no
+            # word from the car.
+            asleepHoldNowWanted = (
+                not (driving or want.restore or want.value is False)
+                and rec.lastOutcome == O.ASLEEP
+                and not whyQuiet(self.master, vehicle)
+            )
+            if not asleepHoldNowWanted:
                 return None
-        k = B.known(vehicle, aspect, d.value)
-        if d.lift and (rec.settledAt is not None or R.satisfied(AMPS, d.value, k)):
+        belief = known(vehicle, aspect, want.value)
+        if want.lift and (
+            rec.settledAt is not None or satisfied(AMPS, want.value, belief)
+        ):
             # A lift is a one-shot desire: done once it settles
-            self.desired.clearIf(key, AMPS, d.value)
+            self.desired.clearIf(key, AMPS, want.value)
             return None
         if now - rec.lastSentAt < MIN_SEND_GAP[aspect]:
             return None
@@ -274,7 +289,7 @@ class VehicleReconciler(threading.Thread):
             # refusal excluded its provider, so the next one goes at once
             return None
         if aspect == CHARGE_LIMIT:
-            adopted = self._adoptable(vehicle, d)
+            adopted = self._adoptable(vehicle, want)
             if adopted is not None:
                 self.desired.adopt(key, aspect, adopted)
                 self._save(vehicle, adopted, None)
@@ -282,39 +297,39 @@ class VehicleReconciler(threading.Thread):
                     "%s charge limit set elsewhere to %s; adopted", key, adopted
                 )
                 return None
-        held = self._held(vehicle)
-        if R.satisfied(aspect, d.value, k):
-            if d.restore:
+        saved = self._saved(vehicle)
+        if satisfied(aspect, want.value, belief):
+            if want.restore:
                 # Back at the outside limit: nothing is held, and nothing is
                 # left to want; a lingering restore would adopt a limit set
                 # away and hold off the policy's limit on the way back
-                if held is not None and held.held is not None:
+                if saved is not None and saved.held is not None:
                     self.master.heldLimits.remove(vehicle.vin)
                 self.desired.clear(key, aspect)
             return None
-        if d.restore and (held is None or held.held is None):
+        if want.restore and (saved is None or saved.held is None):
             # Nothing to restore
             self.desired.clear(key, aspect)
             return None
         config = (getattr(self.master, "config", None) or {}).get("config")
-        reason = B.handsOff(vehicle, aspect, d.value, k, config)
+        reason = whyHandsOff(vehicle, aspect, want.value, belief, config)
         if reason is not None:
-            self._sayOnce(key, aspect, "hands off: " + reason, logging.INFO)
+            self._logBlockedOnce(key, aspect, "hands off: " + reason, logging.INFO)
             return None
         if rec.settledAt is not None and not (
-            B.newerReading(vehicle, aspect, rec.settledAt)
+            newerReading(vehicle, aspect, rec.settledAt)
             and now - rec.lastSentAt >= RETRY[aspect]
         ):
             # Settled without a stamp: wait for a newer reading
             return None
-        capability = CAPABILITY_FOR(aspect, d.value)
+        capability = CAPABILITY_FOR(aspect, want.value)
         cands = [
             p
             for p in self.master.providerOrder.candidates(
                 vehicle,
                 capability,
-                amps=d.value if aspect == AMPS else None,
-                localRule=aspect == AMPS and not d.lift,
+                amps=want.value if aspect == AMPS else None,
+                localRule=aspect == AMPS and not want.lift,
             )
             if p.name not in rec.excluded
             # The TWC target is the distributor's
@@ -325,46 +340,44 @@ class VehicleReconciler(threading.Thread):
             )
         ]
         if not cands:
-            self._sayOnce(key, aspect, "no provider can deliver", logging.DEBUG)
+            self._logBlockedOnce(key, aspect, "no provider can deliver", logging.DEBUG)
             return None
-        self._said.pop((key, aspect), None)
+        self._blockedReasons.pop((key, aspect), None)
         free = [p for p in cands if _tier(p, capability) < C.TIER_BILLED]
         paid = [p for p in cands if _tier(p, capability) >= C.TIER_BILLED]
-        ch = self.desired.free(key)
+        freeChannel = self.desired.free(key)
         # Free failures from before the car came back say nothing of it here
-        back = Presence.returned(vehicle)
+        returnedAt = Presence.returned(vehicle)
         freeFailed = not free or (
-            ch.failingSince is not None
-            and ch.lastAttemptAt >= back
-            and now - max(ch.failingSince, back) >= PAID_AFTER[aspect]
-            and now - ch.lastAttemptAt < PROBE_AFTER
+            freeChannel.failingSince is not None
+            and freeChannel.lastAttemptAt >= returnedAt
+            and now - max(freeChannel.failingSince, returnedAt) >= PAID_AFTER[aspect]
+            and now - freeChannel.lastAttemptAt < PROBE_AFTER
         )
-        # At most two paid sends per arm, and two arms per desire: one send,
-        # then one more after a failure or a reading that reached the car
         # A start goes with the limit first: its wake carries the limit
-        ride = aspect == CHARGE_LIMIT and self._startWanted(vehicle, config)
+        startWillWake = aspect == CHARGE_LIMIT and self._startWanted(vehicle, config)
         field = FIELD_FOR[aspect]
         # Only a car expected to charge is woken; a restore or stop never is,
         # nor waits on the question
-        wakes = not d.restore and d.value is not False
-        quiet = B.whyQuiet(self.master, vehicle) if wakes else None
-        if aspect == CHARGING and B.known(vehicle, CHARGING) is None:
+        wantsWake = not want.restore and want.value is not False
+        quiet = whyQuiet(self.master, vehicle) if wantsWake else None
+        if aspect == CHARGING and known(vehicle, CHARGING) is None:
             if key in self._wokeUnread or not self.wakeUnreadOnce:
                 quiet = quiet or "its charging state is unknown"
         if aspect == CHARGING and quiet == "no room to start":
             # The start waits for room, keeping its desire and its budget
             return None
-        wakes = wakes and quiet is None
-        asleep = Presence.asleep(vehicle, rec.heldAt or 0) is not False
+        wakes = wantsWake and quiet is None
+        notSeenAwake = Presence.asleep(vehicle, rec.heldAt or 0) is not False
         # A billed provider never wakes for amps
-        holder = self.master.providerOrder.provider(rec.lastProvider)
-        mayWake = wakes and (aspect != AMPS or getattr(holder, "local", False))
-        if not mayWake and last == O.ASLEEP and asleep:
+        lastProvider = self.master.providerOrder.provider(rec.lastProvider)
+        mayWake = wakes and (aspect != AMPS or getattr(lastProvider, "local", False))
+        if not mayWake and last == O.ASLEEP and notSeenAwake:
             # Asleep (or offline): only a sign of life since the hold (the
             # cloud's next check may find one), or a message that may wake
             return None
-        reached = rec.paidSends and B.reachedCar(
-            vehicle, field, rec.paidAt, rec.paidSaw
+        reached = rec.paidSends and reachedCar(
+            vehicle, field, rec.paidAt, rec.beliefAtPaidSend
         )
         if (
             rec.paidSends
@@ -373,11 +386,9 @@ class VehicleReconciler(threading.Thread):
             and now - rec.paidAt >= RETRY[aspect]
             and (
                 reached
-                or ride
+                or startWillWake
                 or self._chargingSince(vehicle, aspect, rec.paidAt)
-                or rec.paidSends >= 2
-                and rec.wakeCheckBy
-                and wakes
+                or (rec.paidSends >= PAID_SENDS_PER_ARM and rec.wakeCheckBy and wakes)
             )
         ):
             # No paid send reached the car: a reading shows it awake, a start
@@ -388,91 +399,94 @@ class VehicleReconciler(threading.Thread):
             rec.paidSends = 0
             rec.rearmed = True
             rec.paidRetryDue = False
-        paidAgain = rec.paidSends == 0 or (
-            rec.paidSends < 2
-            and (
-                now - rec.paidAt >= RETRY[aspect]
-                and (rec.paidRetryDue or reached)
-                # Its wake failed: the follow-up through it (WAKE_CHECK)
-                or now - rec.paidAt >= WAKE_CHECK
+        paidAgain = rec.paidSends == 0
+        if 0 < rec.paidSends < PAID_SENDS_PER_ARM:
+            sincePaid = now - rec.paidAt
+            retryDue = sincePaid >= RETRY[aspect] and (rec.paidRetryDue or reached)
+            # Its wake failed: the follow-up through it (WAKE_CHECK)
+            wakeCheckDue = (
+                sincePaid >= WAKE_CHECK
                 and wakes
                 and paid
                 and paid[0].name == rec.wakeCheckBy
             )
-        )
-        freeGap = RESTORE_RETRY if d.restore and rec.lastFreeAt else RETRY[aspect]
+            paidAgain = retryDue or wakeCheckDue
+        freeGap = RESTORE_RETRY if want.restore and rec.lastFreeAt else RETRY[aspect]
         # Spent only while the message would still not go
-        spent = rec.paidSends + rec.paidSpent >= PAID_BUDGET and (
-            Presence.applicable(self.master, vehicle, capability)[0] != Presence.SEND
-        )
+        spent = rec.paidSends + rec.paidSpent >= PAID_BUDGET
+        if spent:
+            verdict, _ = Presence.applicable(self.master, vehicle, capability)
+            spent = verdict != Presence.SEND
         if paid and freeFailed and paidAgain and not spent:
-            p = paid[0]
-            rec.paidSaw = k.value if k is not None else None
-        elif free and (now - rec.lastFreeAt >= freeGap or rec.lastFreeAt < back):
-            p = free[0]
+            provider = paid[0]
+            rec.beliefAtPaidSend = belief.value if belief is not None else None
+        elif free and (now - rec.lastFreeAt >= freeGap or rec.lastFreeAt < returnedAt):
+            provider = free[0]
         else:
             return None
-        if aspect == CHARGING and d.value is True:
-            dl = self.desired.get(key, CHARGE_LIMIT)
-            limit = self.desired.record(key, CHARGE_LIMIT)
+        if aspect == CHARGING and want.value is True:
+            limitWant = self.desired.get(key, CHARGE_LIMIT)
+            limitRec = self.desired.record(key, CHARGE_LIMIT)
             write = vehicle.lastWrite(FIELD_FOR[CHARGE_LIMIT])
             if (
-                limit.inFlight is not None
+                limitRec.inFlight is not None
                 or (write is not None and now - write.at < LIMIT_THEN_START_GAP)
                 # Tried, unsettled and not spent
-                or dl is not None
-                and limit.lastOutcome is not None
-                and not R.satisfied(
-                    CHARGE_LIMIT, dl.value, B.known(vehicle, CHARGE_LIMIT)
+                or (
+                    limitWant is not None
+                    and limitRec.lastOutcome is not None
+                    and not satisfied(
+                        CHARGE_LIMIT, limitWant.value, known(vehicle, CHARGE_LIMIT)
+                    )
+                    and not self._limitSpent(vehicle, limitRec)
                 )
-                and not self._limitSpent(vehicle, limit)
             ):
                 # A limit always goes first, and settles before a start
                 return None
         # The blind retry never wakes and reads nothing: the first
         # attempt read. A paid attempt reads only a value older than its
         # whole window
-        blind = p in paid and rec.paidRetryDue
-        wake = wakes and (p.local or aspect != AMPS) and not blind
+        blind = provider in paid and rec.paidRetryDue
+        wake = wakes and (provider.local or aspect != AMPS) and not blind
         attempt = Attempt(
             key,
             aspect,
             capability,
-            d.value,
-            p.name,
+            want.value,
+            provider.name,
             wake=wake,
             maxAge=(
                 None
                 if aspect == AMPS or blind
-                else READ_MAX_AGE + (PAID_AFTER[aspect] if p in paid else 0)
+                else READ_MAX_AGE + (PAID_AFTER[aspect] if provider in paid else 0)
             ),
-            restore=d.restore,
+            restore=want.restore,
             # A desire set after this pass began is still this attempt's
-            since=max(now, d.at),
+            since=max(now, want.at),
             force=aspect == CHARGE_LIMIT
-            and R.needsLiveRead(R.releases(d), k.value if k else None, held),
-            wakeSkipped=None if wake else self._whyNoWake(d, p, quiet, blind),
+            and needsLiveRead(releases(want), belief.value if belief else None, saved),
+            wakeSkipped=None if wake else self._whyNoWake(want, provider, quiet, blind),
             paidBefore=vehicle.paidRequests,
         )
         rec.inFlight = attempt
         return attempt
 
     @staticmethod
-    def _whyNoWake(d, p, quiet, blind) -> str:
+    def _whyNoWake(want, provider, quiet, blind) -> str:
         if blind:
             return "blind paid retry"
-        if d.restore or d.value is False:
+        if want.restore or want.value is False:
             return "restore or stop never wakes"
         return quiet or "billed provider never wakes for amps"
 
     def _startWanted(self, vehicle, config) -> bool:
         start = self.desired.get(vehicle.key, CHARGING)
-        k = B.known(vehicle, CHARGING, True)
+        belief = known(vehicle, CHARGING, True)
         return (
             start is not None
             and start.value is True
-            and not R.satisfied(CHARGING, True, k)
-            and B.handsOff(vehicle, CHARGING, True, k, config) is None
+            and not satisfied(CHARGING, True, belief)
+            and whyHandsOff(vehicle, CHARGING, True, belief, config) is None
             # A start that would itself spend a cloud wake (not mode 2's)
             and any(
                 not p.local and p.declares(C.WAKE)
@@ -486,10 +500,10 @@ class VehicleReconciler(threading.Thread):
         # Not "Complete": a finished car may be asleep
         return aspect == CHARGE_LIMIT and any(
             obs.value in _DRAWING
-            for obs in B._newer(vehicle, FIELD_FOR[CHARGING], since)
+            for obs in newerReadings(vehicle, FIELD_FOR[CHARGING], since)
         )
 
-    def _limitSpent(self, vehicle, limit) -> bool:
+    def _limitSpent(self, vehicle, limitRec) -> bool:
         # The limit cannot be delivered, so it no longer holds the start:
         # every provider that can serve this car is excluded (a paired
         # BLE with its radio down still can: readiness is the claim);
@@ -497,17 +511,13 @@ class VehicleReconciler(threading.Thread):
         # used with no blind retry left; a refusal holds it unsent; or the
         # car's limit could not be read twice, RETRY apart
         able = self.master.providerOrder.candidates(vehicle, C.SET_CHARGE_LIMIT)
-        last = limit.lastOutcome
+        last = limitRec.lastOutcome
         return (
-            all(p.name in limit.excluded for p in able)
-            or limit.paidSends >= 2
-            and limit.paidReached
-            or limit.paidSends
-            and limit.rearmed
-            and not limit.paidRetryDue
-            or last is not None
-            and last.detail in _REFUSALS
-            or limit.unread >= 2
+            all(p.name in limitRec.excluded for p in able)
+            or (limitRec.paidSends >= PAID_SENDS_PER_ARM and limitRec.paidReached)
+            or (limitRec.paidSends and limitRec.rearmed and not limitRec.paidRetryDue)
+            or (last is not None and last.detail in _REFUSALS)
+            or limitRec.unread >= 2
         )
 
     def _asleepCheckDue(self, vehicle, rec, now) -> bool:
@@ -524,7 +534,7 @@ class VehicleReconciler(threading.Thread):
         due = now - max(rec.lastOutcomeAt, rec.checkedAt) >= gap
         return due and not Presence.covered(self.master, vehicle)
 
-    def _held(self, vehicle):
+    def _saved(self, vehicle):
         return self.master.heldLimits.get(vehicle.vin) if vehicle.vin else None
 
     def _save(self, vehicle, outside, held) -> None:
@@ -554,11 +564,11 @@ class VehicleReconciler(threading.Thread):
         early = None if provider.module is None else self.inapplicable(vehicle, attempt)
         if early is not None or attempt.aspect != CHARGE_LIMIT:
             return attempt.value, early
-        decision = R.decideChargeLimit(
+        decision = decideChargeLimit(
             attempt.value,
             attempt.restore,
             believed.value if believed is not None else None,
-            self._held(vehicle),
+            self._saved(vehicle),
         )
         if decision.saveNow is not None:
             self._save(vehicle, *decision.saveNow)
@@ -623,4 +633,4 @@ class VehicleReconciler(threading.Thread):
             paid=_tier(provider, attempt.capability) >= C.TIER_BILLED,
             spent=vehicle.paidRequests - attempt.paidBefore if vehicle else 0,
         )
-        self.wake()
+        self.nudge()
diff --git a/lib/TWCManager/Vehicle/Reconcile/Rules.py b/lib/TWCManager/Vehicle/Reconcile/Rules.py
index 29c4fb66..ecfaefc7 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Rules.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Rules.py
@@ -1,14 +1,17 @@
 # The charge-limit decision rules. decideChargeLimit is pure: no I/O, no
 # master. The reconciler's beforeWrite runs it on the worker after the read,
-# then saves, sends or settles as it says. The saved record is a HeldLimit (HeldLimits.py): None is nothing
-# held; a save with held None removes the record.
+# then saves, sends or settles as it says. The saved record is a HeldLimit
+# (HeldLimits.py): None is nothing held; a save with held None removes the
+# record.
 from typing import NamedTuple, Optional
 
 from .Desired import CHARGE_LIMIT, CHARGING, RELEASE
+from .Outcome import UNREAD_REASON
 from .HeldLimits import MAX_LIMIT, MIN_LIMIT, HeldLimit
 
-# Observations that never adopt and never stand for the car's own state
-VEHICLE_SOURCES_EXCLUDED = frozenset({"TWC", "Gen2TWC", "Gen3TWC"})
+# The TWC sources: their observations never adopt and never stand for the
+# car's own state
+TWC_SOURCES = frozenset({"TWC", "Gen2TWC", "Gen3TWC"})
 _CHARGING_LIKE = frozenset({"Charging", "Starting", "Complete"})
 _STOPPED_LIKE = frozenset({"Stopped", "Complete", "Disconnected", "NoPower"})
 
@@ -48,14 +51,14 @@ def _clamped(limit):
 
 
 def decideChargeLimit(
-    desired, restore: bool, current, held: Optional[HeldLimit]
+    desired, restore: bool, current, saved: Optional[HeldLimit]
 ) -> ChargeLimitDecision:
     """Decide how to apply `desired` (50-100), or with restore=True how to
     put back the normal limit.
 
     current: the car's limit now, or None if no source knows it: then
         nothing is decided or sent (the reconciler retries).
-    held: the HeldLimit saved for the car, or None.
+    saved: the HeldLimit saved for the car, or None.
 
     With the current limit known, a limit we don't hold is the car's normal
     one, and a held limit the car is no longer at was set by hand and is the
@@ -63,25 +66,23 @@ def decideChargeLimit(
     """
     # A release puts back the outside limit as a restore does
     restore = restore or desired == RELEASE
-    outside = _clamped(held.outside) if held is not None else None
-    ours = held.held if held is not None else None
+    outside = _clamped(saved.outside) if saved is not None else None
+    heldLimit = saved.held if saved is not None else None
     target = None if restore else _clamped(desired)
 
     if current is None:
-        return ChargeLimitDecision(
-            None, None, None, False, "could not read the current limit; nothing sent"
-        )
+        return ChargeLimitDecision(None, None, None, False, UNREAD_REASON)
 
-    if restore and held is None:
+    if restore and saved is None:
         return ChargeLimitDecision(
             None, None, None, True, "no saved normal limit; nothing to restore"
         )
 
-    handSet = ours is not None and current != ours
-    normal = outside if ours is not None and not handSet else current
+    handSet = heldLimit is not None and current != heldLimit
+    normal = outside if heldLimit is not None and not handSet else current
 
     if restore:
-        if ours is not None and not handSet and current != normal:
+        if heldLimit is not None and not handSet and current != normal:
             return ChargeLimitDecision(
                 normal, None, HeldLimit(normal, None), False, "restore to %s%%" % normal
             )
@@ -111,14 +112,14 @@ def releases(desired) -> bool:
     return desired.restore or desired.value == RELEASE
 
 
-def needsLiveRead(restore: bool, telemetryCurrent, held: Optional[HeldLimit]) -> bool:
+def needsLiveRead(restore: bool, telemetryCurrent, saved: Optional[HeldLimit]) -> bool:
     """True when a restore hinges on a telemetry limit that can't be
     trusted: any value other than the held one may be hand-set or stale, and
     telemetry can't tell which. Applies keep the telemetry value."""
     return (
         restore
         and telemetryCurrent is not None
-        and held is not None
-        and held.held is not None
-        and telemetryCurrent != held.held
+        and saved is not None
+        and saved.held is not None
+        and telemetryCurrent != saved.held
     )
diff --git a/lib/TWCManager/Vehicle/Reconcile/Run.py b/lib/TWCManager/Vehicle/Reconcile/Run.py
index e739b749..4d24e6c9 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Run.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Run.py
@@ -13,8 +13,8 @@ from ..Presence import NOT_HOME, PRESUMED, REACH_WINDOW, asleep, drivingNow, pre
 from ..Providers import Capability as C
 from .Desired import AMPS, CHARGE_LIMIT, CHARGING, FIELD_FOR
 from . import Outcome as O
-from .Belief import uncompleted
-from .Rules import VEHICLE_SOURCES_EXCLUDED, satisfied
+from .Belief import unlessLimitRaised
+from .Rules import TWC_SOURCES, satisfied
 
 logger = logging.getLogger(__name__.split(".")[0] + ".Vehicle.Reconcile")
 
@@ -152,22 +152,22 @@ def runAttempt(reconciler, attempt) -> O.Outcome:
     # unknown, and a billed write never goes blind
     wakeFirst = attempt.wake and not provider.local and provider.declares(C.WAKE)
     try:
-        ble = provider.name == "TeslaBLE" and aspect and not isStop(attempt)
+        bleCommand = provider.name == "TeslaBLE" and aspect and not isStop(attempt)
         state = presence(master, vehicle)
         if provider.module is not None and (state == NOT_HOME or drivingNow(vehicle)):
             early = reconciler.inapplicable(vehicle, attempt)
             if early is not None:
                 return early
         # A message that may not wake leaves a sleeping car alone. The
-        # sleep-safe ping first for a car that may be away, or asleep and not
-        # seen awake lately
-        quiet = ble and not attempt.wake and state != NOT_HOME
-        known = asleep(vehicle, master.vehicleRegistry.now() - REACH_WINDOW)
-        check = state == PRESUMED or quiet and known is None
-        if ble and check and not (quiet and known):
+        # sleep-safe ping goes first to a car that may be away, or to one
+        # that may be asleep and has not been seen awake lately.
+        noWakeBle = bleCommand and not attempt.wake and state != NOT_HOME
+        sleepInWindow = asleep(vehicle, master.vehicleRegistry.now() - REACH_WINDOW)
+        pingFirst = state == PRESUMED or (noWakeBle and sleepInWindow is None)
+        if bleCommand and pingFirst and not (noWakeBle and sleepInWindow is True):
             if not provider.module.ping(vin):
                 return O.Outcome(O.UNREACHABLE, "no BLE answer")
-        if quiet and asleep(vehicle):
+        if noWakeBle and asleep(vehicle):
             return O.ASLEEP
         if wakeFirst:
             early = _wake(provider, vehicle, attempt.capability)
@@ -197,11 +197,9 @@ def runAttempt(reconciler, attempt) -> O.Outcome:
                 force=attempt.force,
                 since=event if recent else None,
             )
-        believed = (
-            vehicle.believed(field, exclude=VEHICLE_SOURCES_EXCLUDED) if field else None
-        )
+        believed = vehicle.believed(field, exclude=TWC_SOURCES) if field else None
         if aspect == CHARGING:
-            believed = uncompleted(vehicle, believed)
+            believed = unlessLimitRaised(vehicle, believed)
         if read and satisfied(aspect, attempt.value, believed):
             return O.Outcome(O.SATISFIED, "read")
         if not (provider.local or attempt.wake or isStop(attempt)):
diff --git a/lib/TWCManager/Vehicle/Reconcile/Targets.py b/lib/TWCManager/Vehicle/Reconcile/Targets.py
index 1141bca1..3183f444 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Targets.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Targets.py
@@ -37,9 +37,9 @@ def _apply(master, vehicle, limit, decision, restore=False) -> None:
     if limit is None and vehicle.vin not in master.heldLimits.holding():
         master.desired.clear(vehicle.key, CHARGE_LIMIT)
     elif restore:
-        held = master.heldLimits.get(vehicle.vin)
+        saved = master.heldLimits.get(vehicle.vin)
         master.desired.set(
-            vehicle.key, CHARGE_LIMIT, held.outside, "restore", decision, restore=True
+            vehicle.key, CHARGE_LIMIT, saved.outside, "restore", decision, restore=True
         )
     else:
         value = RELEASE if limit is None else limit
@@ -79,6 +79,6 @@ def _restoreDeparted(master) -> None:
         write = vehicle.lastWrite("chargeLimit")
         # <= on purpose: a retained MQTT position redelivered after our write
         # is stamped with that write's time, and is not a new fix
-        if at is None or write is not None and at <= write.at:
+        if at is None or (write is not None and at <= write.at):
             continue
         _apply(master, vehicle, None, True, restore=True)
diff --git a/lib/TWCManager/Vehicle/Registry/Vehicle.py b/lib/TWCManager/Vehicle/Registry/Vehicle.py
index a80ed8ef..32a37c19 100644
--- a/lib/TWCManager/Vehicle/Registry/Vehicle.py
+++ b/lib/TWCManager/Vehicle/Registry/Vehicle.py
@@ -130,7 +130,7 @@ class Vehicle:
         seen: bool = True,
     ) -> Observation:
         hook = getattr(self._registry, "onObserve", None)
-        prior = self.reported(field).get(source) if hook else None
+        prior = self.reported(field).get(source) if hook is not None else None
         obs = self._store(self._latest, field, value, source, at, True, seen)
         self.lastObservedAt = self._clock()
         if seen:
@@ -140,14 +140,15 @@ class Vehicle:
                 if at >= self.lastSeen:
                     self.lastSeen = at
                     self.lastSeenSource = obs.source
-        # The incoming reading, not the kept one: an older stamp is stored
-        # per source but loses the field's latest
-        mine = self.reported(field).get(source) if hook else prior
-        if mine is not prior:
-            try:
-                hook(self, field, mine, prior)
-            except Exception:
-                logger.exception("Observe hook failed")
+        if hook is not None:
+            # The incoming reading, not the kept one: an older stamp is stored
+            # per source but loses the field's latest
+            mine = self.reported(field).get(source)
+            if mine is not prior:
+                try:
+                    hook(self, field, mine, prior)
+                except Exception:
+                    logger.exception("Observe hook failed")
         return obs
 
     def mark(self, name: str, at: float) -> None:
@@ -202,6 +203,9 @@ class Vehicle:
     def _liveAt(
         self, field: str, obs: Optional[Observation], exclude: Collection[str] = ()
     ) -> Any:
+        # As sourceLiveAt for obs's source: NOT_TRACKED (no liveness) or None
+        # (not live), unless a live feed that reported field vouches for it:
+        # then the newest time one did
         if obs is None or self._registry is None:
             return NOT_TRACKED
         live = self._registry.sourceLiveAt(obs.source, self)
@@ -275,7 +279,9 @@ class Vehicle:
     # Sync state is a feed's own latest "state" observation and its age.
 
     def telemetryState(self) -> Tuple[Optional[Observation], Optional[float]]:
-        obs = self.latestFrom("state", set(self.reported("state")) - TELEMETRY_SOURCES)
+        # The newest telemetry reading
+        others = set(self.reported("state")) - TELEMETRY_SOURCES
+        obs = self.latestFrom("state", exclude=others)
         if obs is None:
             return self.latest("state"), None
         return obs, self._ageOf(obs, self._clock(), self._liveAt("state", obs))
diff --git a/lib/TWCManager/Vehicle/Watch.py b/lib/TWCManager/Vehicle/Watch.py
index 237c4b1b..9240a30d 100644
--- a/lib/TWCManager/Vehicle/Watch.py
+++ b/lib/TWCManager/Vehicle/Watch.py
@@ -15,7 +15,7 @@ from .Presence import HOME, NEVER, _ble, _fix, _FT_PER_DEGREE, asleep, decide, l
 from .Presence import AWAY_ASLEEP_SECS, HOME_ASLEEP_SECS, NOT_HOME, covered, presence
 from .Presence import twcVinAt
 from .Providers.Capability import READ_CHARGE, SET_AMPS
-from .Reconcile.Belief import standIn
+from .Reconcile.Belief import twcChargingState
 from .WatchBudget import EVENT, ROUTINE
 
 logger = logging.getLogger(__name__.split(".")[0] + ".Vehicle.Watch")
@@ -324,7 +324,7 @@ class Watch:
         if want and not want[1] and (named or state == HOME_AWAKE and recent):
             self._take(v.vin, want)
             want = None
-        flowing = getattr(standIn(v), "value", None) == "Charging"
+        flowing = getattr(twcChargingState(v), "value", None) == "Charging"
         if not want and not (flowing if named else state == HOME_CHARGING):
             return
         order = self.master.providerOrder
diff --git a/tests/unit/test_limit_wiring.py b/tests/unit/test_limit_wiring.py
index 27be0582..e1d19d9d 100644
--- a/tests/unit/test_limit_wiring.py
+++ b/tests/unit/test_limit_wiring.py
@@ -69,7 +69,7 @@ def test_no_module_holds_a_copy_of_the_policy_limit():
 # Wiring
 
 def test_master_wires_store_and_reconciler_on_one_clock():
-    m, s = make(); assert m.reconciler.master is m and m.desired._clock is time.time and m.desired.changed == m.reconciler.wake
+    m, s = make(); assert m.reconciler.master is m and m.desired._clock is time.time and m.desired.changed == m.reconciler.nudge
     m.vehicleRegistry.getOrCreate(VIN, "t"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); m.vehicleRegistry.forget(VIN)
     assert m.desired.peek(VIN) is None                                     # registry.removed wired
     assert m.policyLimit is UNDECIDED and m.reconciler.desired is m.desired
diff --git a/tests/unit/test_outcome_desired.py b/tests/unit/test_outcome_desired.py
index c656b60f..6cf8409f 100644
--- a/tests/unit/test_outcome_desired.py
+++ b/tests/unit/test_outcome_desired.py
@@ -83,11 +83,11 @@ def test_a_failed_paid_wake_sets_no_retry():
 def test_a_new_desire_resets_the_per_desire_stamps():
     s = DesiredStore(); s.set(VIN, CHARGE_LIMIT, 50, "policy"); r = s.record(VIN, CHARGE_LIMIT)
     r.lastFreeAt, r.paidAt, r.paidRetryDue, r.settledAt, r.lastSentAt = 1.0, 2.0, True, 3.0, 4.0
-    r.paidSends, r.paidSaw, r.lastOutcome, r.lastOutcomeAt = 1, 90, O.Outcome(O.UNREACHABLE, "wake held"), 5.0
+    r.paidSends, r.beliefAtPaidSend, r.lastOutcome, r.lastOutcomeAt = 1, 90, O.Outcome(O.UNREACHABLE, "wake held"), 5.0
     assert s.set(VIN, CHARGE_LIMIT, 50, "heartbeat") is False and r.paidAt == 2.0          # unchanged: nothing reset
     s.set(VIN, CHARGE_LIMIT, 60, "policy")
     assert (r.lastFreeAt, r.paidAt, r.paidRetryDue, r.settledAt, r.lastSentAt) == (0, None, False, None, 4.0)
-    assert (r.paidSends, r.paidSaw, r.lastOutcome, r.lastOutcomeAt) == (0, None, None, 0)   # the NOT_SENT hold is the old desire's (I1)
+    assert (r.paidSends, r.beliefAtPaidSend, r.lastOutcome, r.lastOutcomeAt) == (0, None, None, 0)   # the NOT_SENT hold is the old desire's (I1)
 
 def test_a_superseded_attempt_feeds_the_free_channel_but_never_the_new_desire():   # C1
     s = DesiredStore(clock=Clock(1000.0)); s.set(VIN, CHARGE_LIMIT, 50, "policy"); r = s.record(VIN, CHARGE_LIMIT)
@@ -174,7 +174,7 @@ def test_a_debug_one_shot_report_changes_nothing():
     assert s.noteOutcome(VIN, None, a, O.Outcome(O.DONE), 100.0, paid=True) is False and s.keys() == []
 
 
-@pytest.mark.parametrize("outcome", [O.Outcome(O.SATISFIED, "read"), O.Outcome(O.SATISFIED, "rules: limit unknown"), O.Outcome(O.UNREACHABLE, "rules: could not read")])
+@pytest.mark.parametrize("outcome", [O.Outcome(O.SATISFIED, "read"), O.Outcome(O.SATISFIED, "rules: limit unknown"), O.Outcome(O.UNREACHABLE, O.RULES + O.UNREAD_REASON)])
 def test_read_and_rules_outcomes_spend_no_send_gap(outcome):                 # deleted-test audit row 77
     c = Clock(0.0); s = DesiredStore(clock=c); s.set(VIN, CHARGE_LIMIT, 50, "policy"); r = s.record(VIN, CHARGE_LIMIT)
     a = attempt("FleetAPI"); r.inFlight = a
diff --git a/tests/unit/test_reconciler_queues.py b/tests/unit/test_reconciler_queues.py
index 60da2e9f..9cd6ca3a 100644
--- a/tests/unit/test_reconciler_queues.py
+++ b/tests/unit/test_reconciler_queues.py
@@ -407,7 +407,7 @@ def test_no_callback_lists_or_test_modes_in_lib():
     assert not hasattr(C, "RateLimit") and "rateLimit" not in C.Cost._fields
 
 def test_the_store_and_the_registry_each_call_one_callable_outside_their_locks():
-    m, r = reconciler(); woke = []; r.wake = lambda *a: woke.append(a)
+    m, r = reconciler(); woke = []; r.nudge = lambda *a: woke.append(a)
     assert m.desired.changed.__self__ is r                                   # bound at construction
     m.desired.changed = lambda key, aspect: woke.append((key, aspect, m.desired._lock.locked()))
     m.desired.set(VIN, CHARGING, True, "test"); assert woke == [(VIN, CHARGING, False)]
diff --git a/tests/unit/test_teslaapi_evse_unplugged.py b/tests/unit/test_teslaapi_evse_unplugged.py
index 0fb537e7..f8a545a7 100644
--- a/tests/unit/test_teslaapi_evse_unplugged.py
+++ b/tests/unit/test_teslaapi_evse_unplugged.py
@@ -55,11 +55,11 @@ def test_a_null_current_never_stands_in_for_charging():
     # Nothing reads a car's own actualCurrent. Its one reader is Belief's
     # stand-in for a car no vehicle source describes, which reads the TWC's
     # current: a null there is no reading, never 0 A or a TypeError
-    from TWCManager.Vehicle.Reconcile.Belief import standIn
+    from TWCManager.Vehicle.Reconcile.Belief import twcChargingState
 
     vehicle = endpoint().vehicle
     vehicle.observe("actualCurrent", None, "Gen2TWC")
-    assert standIn(vehicle) is None
+    assert twcChargingState(vehicle) is None
 
 
 def test_power_limits_for_unplugged_car():
diff --git a/tests/unit/test_vehicle_detail_page.py b/tests/unit/test_vehicle_detail_page.py
index 979479ae..a25d1a67 100644
--- a/tests/unit/test_vehicle_detail_page.py
+++ b/tests/unit/test_vehicle_detail_page.py
@@ -303,9 +303,9 @@ def test_pending_says_what_the_reconciler_said_over_the_last_outcome():
     m.desired.set(VIN, CHARGING, False, "distributor")
     rec = m.desired.record(VIN, CHARGING)
     rec.lastOutcome, rec.lastOutcomeAt = Outcome(UNREACHABLE), time.time() - 5
-    m.reconciler._said[(VIN, CHARGING)] = "hands off: battery below minChargeLevel"
+    m.reconciler._blockedReasons[(VIN, CHARGING)] = "hands off: battery below minChargeLevel"
     assert pending(m) == {CHARGING: "hands off: battery below minChargeLevel"}
-    m.reconciler._said[(VIN, CHARGING)] = "no provider can deliver"
+    m.reconciler._blockedReasons[(VIN, CHARGING)] = "no provider can deliver"
     assert pending(m) == {CHARGING: "no provider can deliver"}
 
 
```

# PR: refactor/readability-presence

````markdown
Name the tuples and tri-states in Presence and the watch

Presence.py and Watch.py read much of their state out of tuples by index (`best[0][0]`, `home[1]`, `seen[2]`, `want[1]`, `source[0]`, `(scan or source or (None,))[0]`), indexed `RETRY` by a bool, and built tri-state answers from `and`/`or` chains such as `None if plugged else plugged`. This makes the code hard to follow when checking what a car's plug or presence decision rests on.

This change unpacks those tuples into named locals, makes the watch's asked-for read an `Ask` namedtuple, writes `pick.fits` as one explicit return per case, renames the timestamp helpers for what they return, and splits a few compressed comments into plain sentences. It is a readability change only, with no change in behaviour. Each tri-state rewrite returns True, False and None in exactly the cases it did before. Outside these two files only call sites change: one line each in `Reconciler.py` and `Belief.py`, plus the tests that use the renamed names.

Main renames:

- `Presence.leaving` / `arriving` / `returned` -> `leftAt` / `arrivedAt` / `returnedAt`
- `pluggedNow(..., unknown=)` -> `pluggedNow(..., ifUnknown=)`, now passed by keyword at every call site
- `pluggedNow`'s `best` tuple -> `bestKey`, `plugged`, `readBy`, `readAt`
- `decide`'s `home[0]` / `home[1]` -> `homeAt`, `homeWhy`
- `pick(offered=)` -> `pick(offerSource=)`; `_awayCharger.since` -> `sameReport`
- `departed`'s `away` -> `wasHere` / `leftHome`; `applicable`'s reused `named`/`at` -> `twcVin`, `namedAt`, `named`
- Watch: the `(cls, exempt)` tuple -> `Ask`; `RETRY[bool]` -> `RETRY_EXEMPT` / `RETRY_COURTEOUS`
- Watch: `last, at` / `tried, lastRead` -> `statusAnswer, statusAt` / `readAnswer, readAt`; `was[0..3]` -> `wasState, wasWhere, wasPlugIn, wasDoor`
- Watch: `fix` -> `forPosition`; `api` flag -> `useApi`; `n` -> `phases`, `carMinAmps` -> `minAmpsPerPhase`; `LoadStep._held` -> `_pending`, its `held` -> `confirmed`

Evidence: full unit suite (`pytest tests --ignore=tests/API --ignore=tests/integration`): 2618 passed, 1 xfailed.

Changelog: none (no behaviour change)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
````

## Commits
```
763c6a62 Keep LoadStep's first-sample arithmetic exact
af564278 Unpack the watch's tuples into named parts
a36f2743 Name the parts of Presence's plug and home decisions
```
## Diff
```diff
diff --git a/lib/TWCManager/Vehicle/Presence.py b/lib/TWCManager/Vehicle/Presence.py
index 9a7ff7d4..7740bf5c 100644
--- a/lib/TWCManager/Vehicle/Presence.py
+++ b/lib/TWCManager/Vehicle/Presence.py
@@ -16,8 +16,9 @@ HOME_RADIUS_FT = 1000
 HOME_FIX_MAX_AGE = 600.0
 REACH_WINDOW = 300.0
 # The least time between status checks of a car known asleep that no live
-# feed reports on, at home and anywhere else: the watch's defaults, and a
-# held cloud command's own check of a car the watch leaves alone
+# feed reports on, at home and anywhere else. The watch uses them as its
+# defaults, and a held cloud command uses them for its own check of a car
+# the watch leaves alone.
 HOME_ASLEEP_SECS, AWAY_ASLEEP_SECS = 900.0, 1800.0
 PILOT_MATCH_TOLERANCE, PLUGGED_JUST_NOW = 1, 120.0
 _BLE_CHARGE = ("chargingState", "availableCurrent", "actualCurrent")
@@ -84,16 +85,16 @@ def _plug(field, obs) -> Optional[bool]:
 def _awayCharger(v, obs) -> bool:
     # A fast charger, no cable, or more power than the car's own AC maximum
     # at its voltage: plugged in, but not to a home charger
-    def since(field):
-        o = v.reported(field).get(obs.source)
-        return o.value if o is not None and o.at >= obs.at else None
+    def sameReport(field):
+        reading = v.reported(field).get(obs.source)
+        return reading.value if reading is not None and reading.at >= obs.at else None
 
-    kind, amps = since("fastChargerType"), since("chargeCurrentRequestMax")
-    power, volts = since("chargerPower") or 0, max(v.value("voltage") or 0, 240)
+    kind, amps = sameReport("fastChargerType"), sameReport("chargeCurrentRequestMax")
+    power, volts = sameReport("chargerPower") or 0, max(v.value("voltage") or 0, 240)
     return (
-        since("fastChargerPresent") is True
+        sameReport("fastChargerPresent") is True
         or kind not in HOME_CHARGER_TYPES | {None}
-        or since("connChargeCable") in ("<invalid>", "")
+        or sameReport("connChargeCable") in ("<invalid>", "")
         or (bool(amps) and power * 1000 > amps * volts * 1.1)
     )
 
@@ -187,31 +188,33 @@ def noteObservation(master, vehicle, field, obs, previous) -> None:
                 master.attributePlugs()
 
 
-def pluggedNow(master, v, unknown=False, since=NEVER) -> Optional[bool]:
-    # The newest plug reading after since; unknown when nothing says
-    here, best = inside(master, v), None
+def pluggedNow(master, v, ifUnknown=False, since=NEVER) -> Optional[bool]:
+    # The newest plug reading after since; ifUnknown when nothing says
+    here, bestKey = inside(master, v), None
+    plugged, readBy, readAt = None, None, NEVER
     for field in _PLUGS:
         for obs in v.reported(field).values():
             value = _plugEvidence(v, field, obs, here)
             # A Gen2's plug counts only while it names the car, below
             value = None if value and obs.source == "Gen2TWC" else value
             key = (obs.at, obs.source in _STRONG)
-            if value is not None and obs.at > since and (best is None or key > best[0]):
-                best = (key, value, obs.source)
+            newer = bestKey is None or key > bestKey
+            if value is not None and obs.at > since and newer:
+                bestKey, plugged, readBy, readAt = key, value, obs.source, obs.at
     # A charging point naming the car says plugged unless another source
     # read it unplugged since; a Gen2 re-plugged keeps its old naming
     named = twcVinAt(master, v)
     if named > NEVER and (
-        not best or best[1] or best[2] == "Gen2TWC" or best[0][0] <= named
+        plugged is not False or readBy == "Gen2TWC" or readAt <= named
     ):
         return True
     # A snapshot of the car plugged in since its unplug places it nowhere,
     # but the unplug is no longer known: a car that came back unseen
     cached = v.reported("chargingState").get(CACHED)
-    if best and best[1] is False and cached and cached.at > best[0][0]:
+    if plugged is False and cached and cached.at > readAt:
         if _plug("chargingState", cached):
-            return unknown
-    return unknown if best is None else best[1]
+            return ifUnknown
+    return ifUnknown if plugged is None else plugged
 
 
 def telemetryPlug(v, since=NEVER, seen=False) -> Optional[bool]:
@@ -240,12 +243,14 @@ def _doorClosed(v, since) -> bool:
 
 
 def checkPlug(master, v, since) -> Optional[bool]:
-    # Plugged in, after a charging point's status edge at since? Never wakes:
-    # a live feed reports a change in seconds (a retained copy is no report);
-    # an unplug wakes a sleeping car, and an awake car's door closes with it
-    # (a car with no key gets no range scan); else the read cascade, where a
-    # cloud API reads only a car its free online check finds awake, past the
-    # stored reading and online answer that an unplug just made stale
+    # Whether the car is plugged in after a charging point's status edge at
+    # since. It never wakes the car. A live feed reports a change within
+    # seconds, though a retained copy is no report. An unplug wakes a
+    # sleeping car, and an awake car's door closes with the cable; a car with
+    # no BLE key gets no range scan. Otherwise the read cascade answers: a
+    # cloud API reads only a car its free online check finds awake, and the
+    # read goes past the stored reading and online answer that an unplug
+    # just made stale.
     if (feed := telemetryPlug(v, since, seen=True)) is not None:
         return feed
     ble, now = _ble(master), master.vehicleRegistry.now()
@@ -262,13 +267,13 @@ def checkPlug(master, v, since) -> Optional[bool]:
     # since a snapshot's stamp can predate the unplug being checked
     reads = [p for p in master.providerOrder.providers() if p.name != CACHED]
     v.read("chargingState", 0, force=True, since=since, wait=False, providers=reads)
-    return pluggedNow(master, v, None, since)
+    return pluggedNow(master, v, ifUnknown=None, since=since)
 
 
 def drivingNow(v) -> bool:
-    # The feed's own state: a provider's sleep check never masks a drive. A
-    # car plugged in, named by a TWC or drawing current since that reading
-    # has stopped, whether or not the drive's end was reported
+    # The feed's own state, so a provider's sleep check never masks a drive.
+    # A car plugged in, named by a TWC or drawing current since that reading
+    # has stopped driving, whether or not the drive's end was reported.
     state, shift = v.telemetryState()[0], v.latest("shiftState")
     if shift is not None and (state is None or shift.at >= state.at):
         driving = shift if shift.value in _MOVING else None
@@ -334,19 +339,19 @@ def decide(master, v) -> Tuple[str, str, float]:
     # Parked: in P, or with no gear known, not driving
     shift = v.value("shiftState")
     parked = shift == "P" if shift is not None else not drivingNow(v)
-    home = max(
+    homeAt, homeWhy = max(
         (twcVinAt(master, v), "named by its charging point"),
         (v.markAt("plugIn"), "plugged in"),
         (v.markAt("contact"), "BLE contact"),
         (fixAt if here and parked else NEVER, "parked inside the radius"),
     )
-    if here is False and fixAt > home[0]:
+    if here is False and fixAt > homeAt:
         return NOT_HOME, "a fix outside the radius", fixAt
     if drivingNow(v):
         return PRESUMED, "driving", NEVER
-    if home[0] > max(v.markAt("driveStart"), v.markAt("absent"), v.markAt("unplug")):
-        return HOME, home[1], home[0]
-    if v.markAt("unplug") > home[0]:
+    if homeAt > max(v.markAt("driveStart"), v.markAt("absent"), v.markAt("unplug")):
+        return HOME, homeWhy, homeAt
+    if v.markAt("unplug") > homeAt:
         return NOT_HOME, "unplug", v.markAt("unplug")
     return PRESUMED, "no newer evidence", NEVER
 
@@ -359,15 +364,15 @@ def pluggedHere(master, v) -> bool:
     return presence(master, v) == HOME and pluggedNow(master, v)
 
 
-def leaving(v) -> float:
+def leftAt(v) -> float:
     return max(v.markAt("unplug"), v.markAt("driveStart"))
 
 
-def arriving(v) -> float:
+def arrivedAt(v) -> float:
     return max(v.markAt("outside"), v.markAt("driveEnd"))
 
 
-def returned(v) -> float:
+def returnedAt(v) -> float:
     # When the car last came back: parked inside the radius, or plugged in
     return max(v.markAt("driveEnd"), v.markAt("plugIn"))
 
@@ -378,33 +383,34 @@ def departed(master, v) -> Optional[float]:
     state, _, at = decide(master, v)
     if state == NOT_HOME:
         return at
-    away = state == HOME or drivingNow(v) and returned(v) > NEVER
-    away = away and leaving(v) > arriving(v) and not pluggedNow(master, v)
-    return leaving(v) if away else None
+    wasHere = state == HOME or (drivingNow(v) and returnedAt(v) > NEVER)
+    leftHome = wasHere and leftAt(v) > arrivedAt(v) and not pluggedNow(master, v)
+    return leftAt(v) if leftHome else None
 
 
 def applicable(master, v, capability) -> Tuple[str, str]:
     # Whether a message, a stop or a restore aside (those always go), still
     # fits where the car is, and the cell that says so. Missing event times
     # are NEVER; a tie holds
-    state, plugged = presence(master, v), pluggedNow(master, v, None)
+    state, plugged = presence(master, v), pluggedNow(master, v, ifUnknown=None)
     if state == NOT_HOME:
         return NOT_HERE, "away"
     if capability != SET_CHARGE_LIMIT:
         # A start or a rate needs the plug. A naming outlasts a Gen2 00 until
         # the car leaves or reads unplugged; a held car never unplugged stays
-        named = v.latest("twcVin")
-        at = named.at if named is not None and named.value else NEVER
-        named = at > leaving(v) and pluggedNow(master, v, True, since=at)
-        presumed = state == PRESUMED or plugged is None
-        presumed = presumed and v.markAt("unplug") == NEVER
-        if plugged or named or presumed and v.vin in master.heldLimits.holding():
+        twcVin = v.latest("twcVin")
+        namedAt = twcVin.at if twcVin is not None and twcVin.value else NEVER
+        named = namedAt > leftAt(v)
+        named = named and pluggedNow(master, v, ifUnknown=True, since=namedAt)
+        neverUnplugged = v.markAt("unplug") == NEVER
+        presumed = (state == PRESUMED or plugged is None) and neverUnplugged
+        if plugged or named or (presumed and v.vin in master.heldLimits.holding()):
             return SEND, "plugged in"
         return (NOT_HERE if state == HOME else HOLD), "not plugged in"
     if state == HOME:
         if departed(master, v) is not None:
             return NOT_HERE, "leaving"
-        tie = not plugged and leaving(v) == arriving(v) > NEVER
+        tie = not plugged and leftAt(v) == arrivedAt(v) > NEVER
         return (HOLD, "tie") if tie else (SEND, "home")
     if drivingNow(v):
         return HOLD, "driving"
@@ -443,17 +449,17 @@ def _reached(master, v) -> bool:
     return reach < v.markAt("contact")
 
 
-def pick(master, offered=None, actual=0, read=False, since=NEVER):
+def pick(master, offerSource=None, actual=0, read=False, since=NEVER):
     # A VIN-less plug's car (plugged in at since): plugged in just now, else
     # BLE-read at this pilot and draw (given an offer, or a function giving
     # the offer now), else reached or inside
     now, pool = master.vehicleRegistry.now(), candidates(master)
-    offer = offered if callable(offered) else lambda: offered
+    offer = offerSource if callable(offerSource) else lambda: offerSource
     offered = offer()
 
     def fresh(v, field, source="TeslaBLE", window=REACH_WINDOW):
-        o = v.reported(field).get(source) if source else v.latest(field)
-        return o if o is not None and now - o.at <= window else None
+        reading = v.reported(field).get(source) if source else v.latest(field)
+        return reading if reading is not None and now - reading.at <= window else None
 
     just = [(v, fresh(v, "pluggedIn", None, PLUGGED_JUST_NOW)) for v in pool]
     just = [v for v, o in just if o and _plugEvidence(v, "pluggedIn", o, True)]
@@ -462,9 +468,9 @@ def pick(master, offered=None, actual=0, read=False, since=NEVER):
         return just[0]
 
     def fits(v):
-        # BLE says: False not plugged in here, True at this pilot and draw;
-        # a live feed saying unplugged since the plug, or an unplug just
-        # before it, rules the car out
+        # False: not plugged in here. True: BLE reads it at this pilot and
+        # draw. None: nothing says either way. A live feed saying unplugged
+        # since the plug, or an unplug just before it, rules the car out
         if telemetryPlug(v, since) is False:
             return False
         if v.markAt("unplug") > since - REACH_WINDOW > NEVER:
@@ -479,15 +485,21 @@ def pick(master, offered=None, actual=0, read=False, since=NEVER):
         if stale and "TeslaBLE" in v.claims and asleep(v, now - REACH_WINDOW) is False:
             v.read("chargingState", 0, providers=("TeslaBLE",), force=True)
         state, pilot, amps = (fresh(v, f) for f in _BLE_CHARGE)
-        plugged = state and _plug("chargingState", state)
+        plugged = None if state is None else _plug("chargingState", state)
+        if plugged is False:
+            return False
         if not (plugged and pilot and offered is not None):
-            return None if plugged else plugged
+            # No fresh plugged reading, or no pilot or offer to match
+            return None
         # The offer may have changed during the read
         gap = min(abs(pilot.value - o) for o in (offered, offer()))
         if gap > PILOT_MATCH_TOLERANCE:
             return False
-        drawing = actual >= 1 and amps
-        return not drawing or abs(amps.value - actual) <= PILOT_MATCH_TOLERANCE or None
+        if actual < 1 or not amps:
+            # No draw to compare: the pilot match says so
+            return True
+        # A draw that differs from the car's own reading says nothing
+        return True if abs(amps.value - actual) <= PILOT_MATCH_TOLERANCE else None
 
     fit = [(v, fits(v)) for v in pool]
     left = [v for v, f in fit if f is not False]
@@ -499,7 +511,8 @@ def pick(master, offered=None, actual=0, read=False, since=NEVER):
 def attribute(master, pointId, source, offered=None, actual=0) -> Optional[str]:
     # Names an anonymous session's car, plugged in there. Given an offer it
     # may read over BLE, so it runs on the BLE worker
-    if not getattr(anon := master.vehicleRegistry.vehicleAt(pointId), "isAnonymous", 0):
+    anon = master.vehicleRegistry.vehicleAt(pointId)
+    if not getattr(anon, "isAnonymous", 0):
         return None
     read, plugIn = offered is not None, anon.markAt("plugIn")
     v = pick(master, offered, actual, read, plugIn)
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index 5e6d6325..b4751ac6 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -130,7 +130,7 @@ def _wontCharge(master, vehicle) -> Optional[str]:
     if pending is not None and not (releases(pending) and not held):
         limit = held.outside if releases(pending) else pending.value
     # Unplugged is known only by a reading
-    plugged = pluggedNow(master, vehicle, None)
+    plugged = pluggedNow(master, vehicle, ifUnknown=None)
     if presence(master, vehicle) == NOT_HOME or plugged is False:
         return "not plugged in here"
     if limit and battery and limit <= battery:
diff --git a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
index 6293760b..92f8d776 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
@@ -332,7 +332,7 @@ class VehicleReconciler(threading.Thread):
         paid = [p for p in cands if _tier(p, capability) >= C.TIER_BILLED]
         ch = self.desired.free(key)
         # Free failures from before the car came back say nothing of it here
-        back = Presence.returned(vehicle)
+        back = Presence.returnedAt(vehicle)
         freeFailed = not free or (
             ch.failingSince is not None
             and ch.lastAttemptAt >= back
diff --git a/lib/TWCManager/Vehicle/Watch.py b/lib/TWCManager/Vehicle/Watch.py
index 237c4b1b..1f1d452f 100644
--- a/lib/TWCManager/Vehicle/Watch.py
+++ b/lib/TWCManager/Vehicle/Watch.py
@@ -9,6 +9,7 @@ import logging
 import math
 import threading
 import time
+from collections import namedtuple
 from typing import Optional
 
 from .Presence import HOME, NEVER, _ble, _fix, _FT_PER_DEGREE, asleep, decide, lastLife
@@ -35,7 +36,10 @@ _CADENCE_OF = {HOME_CHARGING: HOME_AWAKE, UNKNOWN: AWAY_AWAKE}
 NO_SOURCE, NAMED, COVERED = "no status source", "named by TWC ", "covered by "
 MISS, AWAKE = "no answer", (HOME_AWAKE, HOME_CHARGING, AWAY_AWAKE)
 # A failed read asked for, retried as its ask was: courtesy-bounded or not
-RETRY, TWICE = ("failed, asking again later", "failed, asking again"), "no answer twice"
+RETRY_COURTEOUS, RETRY_EXEMPT = "failed, asking again later", "failed, asking again"
+RETRY, TWICE = (RETRY_COURTEOUS, RETRY_EXEMPT), "no answer twice"
+# A read asked for: its budget class, and whether the courtesy window yields
+Ask = namedtuple("Ask", "cls exempt")
 KINDS = ("status", "read", "scan")
 
 
@@ -97,15 +101,18 @@ class LoadStep:
     # A rise or fall of at least the threshold, reported once the next sample
     # holds it: a spike that falls back says nothing
     def __init__(self, thresholdWatts: float):
-        self.threshold, self._base, self._held = thresholdWatts, None, None
+        self.threshold, self._base, self._pending = thresholdWatts, None, None
 
     def sample(self, watts: float) -> Optional[str]:
+        # The first sample is its own base, and a NaN reading stays NaN
         moved = watts - (watts if self._base is None else self._base)
         step = None if abs(moved) < self.threshold else "up" if moved > 0 else "down"
-        held, self._held = self._held, None if step == self._held else step
-        if step is None or step == held:
+        confirmed = step == self._pending
+        # A step reported is no longer pending; a new one waits for the next
+        self._pending = None if confirmed else step
+        if step is None or confirmed:
             self._base = watts
-        return step if step == held else None
+        return step if confirmed else None
 
 
 class Watch:
@@ -114,15 +121,15 @@ class Watch:
         self._settings = settingsOf(master.config)
         # The least a car draws, or the meter's noise; the step's state is the
         # background-tasks thread's alone, where (vin, step) -> its last read
-        volts, n = master.getVoltageMeasurement()
-        least = max(self._settings["emsNoiseWatts"], (5 if n < 3 else 1) * volts * n)
+        volts, phases = master.getVoltageMeasurement()
+        minAmpsPerPhase = 5 if phases < 3 else 1
+        least = max(self._settings["emsNoiseWatts"], minAmpsPerPhase * volts * phases)
         self._step, self._triggered = LoadStep(least), {}
         # A leaf: never held across a registry or provider call, or a submit
         self._lock = threading.Lock()
         # (vin, job kind) queued or running, and its last answer and time,
         # which with the car's situation now sets the next; vin -> what the
-        # last pass saw; a read asked for: (budget class, whether the
-        # courtesy window yields to it)
+        # last pass saw; vin -> the read asked for, an Ask
         self._inflight, self._last, self._seen, self._want = set(), {}, {}, {}
         # Cars at home the radio stopped hearing, already read for it
         self._unheard = set()
@@ -138,8 +145,8 @@ class Watch:
         # a second miss is settled by the ping's scan whatever the car last
         # said; where none can run, away by the miss itself, at home by a read
         getModule, again = self.master.getModuleByName, last in (MISS, TWICE)
-        api = v.attachment("TeslaAPI") is not None and ble is None
-        api, deaf = api and getModule("TeslaAPI"), again and not scans(ble)
+        useApi = v.attachment("TeslaAPI") is not None and ble is None
+        api, deaf = useApi and getModule("TeslaAPI"), again and not scans(ble)
         if ble is not None and not lost(v, where):
 
             def ping():
@@ -176,8 +183,9 @@ class Watch:
 
     def _ask(self, vin, cls, exempt) -> None:
         # Under the lock; an event outranks a routine ask
-        was = self._want.get(vin, (cls, False))
-        self._want[vin] = (EVENT if EVENT in (cls, was[0]) else cls, exempt or was[1])
+        was = self._want.get(vin, Ask(cls, False))
+        cls = EVENT if EVENT in (cls, was.cls) else cls
+        self._want[vin] = Ask(cls, exempt or was.exempt)
 
     def _watched(self):
         for v in self.master.vehicleRegistry.vehicles():
@@ -250,25 +258,27 @@ class Watch:
     def _visit(self, v, now) -> None:
         vin, (where, _, since) = v.vin, decide(self.master, v)
         state, door = situation(self.master, v, where), v.value("chargePortOpen")
-        seen = (state, where, v.markAt("plugIn"), door)
+        plugIn = v.markAt("plugIn")
+        seen = (state, where, plugIn, door)
         why = notWatched(self.master, v)
         named, ble = bool(why) and why.startswith(NAMED), radio(self.master)
         with self._lock:
             # What a car was before a restart is no news: the first pass
             # only learns it. A car first seen later has arrived
             fresh = seen if not self._started else (None, None, NEVER, None)
-            was, self._seen[vin] = self._seen.get(vin, fresh), seen
+            wasState, wasWhere, wasPlugIn, wasDoor = self._seen.get(vin, fresh)
+            self._seen[vin] = seen
             busy = {kind for key, kind in self._inflight if key == vin}
-            (last, at), (tried, lastRead), (_, scanAt) = (
+            (statusAnswer, statusAt), (readAnswer, readAt), (_, scanAt) = (
                 self._last.get((vin, kind), ("", NEVER)) for kind in KINDS
             )
             # An arrival by any route, a wake, a plug-in (one a read made by
             # reporting it is already read), or an awake car's door opening,
             # which only a car in BLE range, so here, reports
-            woke = was[0] in (HOME_ASLEEP, AWAY_ASLEEP) and seen[0] in AWAKE
-            if woke or where == HOME and was[1] != HOME and since > lastRead:
+            woke = wasState in (HOME_ASLEEP, AWAY_ASLEEP) and state in AWAKE
+            if woke or (where == HOME and wasWhere != HOME and since > readAt):
                 self._ask(vin, EVENT, False)
-            if seen[2] > max(was[2], lastRead) or door and not was[3]:
+            if plugIn > max(wasPlugIn, readAt) or (door and not wasDoor):
                 self._ask(vin, EVENT, True)
             if why and not named:
                 # Covered or not watched: an old ask must not fire later
@@ -282,46 +292,53 @@ class Watch:
         # Only the cloud sees an awake car free to leave go, or come back once
         # it could: it is read once its fix is a courtesy window old
         fixAt, wait = _fix(self.master, v)[1], self._settings["sleepCourtesySecs"]
-        late = now >= max(fixAt, lastRead) + wait and cloudOnly(self.master, v)
-        if late and seen[0] in (HOME_AWAKE, AWAY_AWAKE):
-            want = want or (EVENT, False)
+        late = now >= max(fixAt, readAt) + wait and cloudOnly(self.master, v)
+        if late and state in (HOME_AWAKE, AWAY_AWAKE):
+            want = want or Ask(EVENT, False)
         # That read, and one on its wake, is for where the car is
-        fix = late or woke and cloudOnly(self.master, v)
+        forPosition = late or (woke and cloudOnly(self.master, v))
         if "read" not in busy and (why is None or named):
+            deaf = statusAnswer == TWICE
             self._read(
-                v, seen[0], named, want, tried, lastRead, now, last == TWICE, fix
+                v, state, named, want, readAnswer, readAt, now, deaf, forPosition
             )
-        if "status" not in busy and now >= at + self._cadence(seen[0]):
+        if "status" not in busy and now >= statusAt + self._cadence(state):
             # Coverage counts for the check only when it is due: a feed
             # blip between checks changes nothing
-            source = None if why else self._source(v, where, ble, last)
+            source = None if why else self._source(v, where, ble, statusAnswer)
             if source is None:
                 self._settle(vin, "status", now)
             else:
-                self._submit(v, "status", source[1], source[0])
-        if why is not None:
+                worker, check = source
+                self._submit(v, "status", check, worker)
+        if why is not None or "scan" in busy:
             return
-        listen = "scan" not in busy and self._listen(v, where, ble, now)
-        if listen and now >= scanAt + listen[1]:
-            if listen[0] == "scan":
+        listen = self._listen(v, where, ble, now)
+        if listen is None:
+            return
+        how, secs = listen
+        if now >= scanAt + secs:
+            if how == "scan":
                 ble.requestRangeScan(vin)
                 self._settle(vin, "scan", now)
             else:
                 self._submit(v, "scan", lambda: ble.ping(vin, scan=False), "ble")
 
-    def _read(self, v, state, named, want, tried, lastRead, now, deaf, fix) -> None:
+    def _read(
+        self, v, state, named, want, readAnswer, readAt, now, deaf, forPosition
+    ) -> None:
         # The charge read due now, if any; deaf: the radio missed it twice;
-        # fix: the read is for the car's position.
+        # forPosition: the read is for the car's position.
         # A TWC-named car is touched only for its plug-in, on request, and
         # while its TWC reports current
         if state in (HOME_ASLEEP, AWAY_ASLEEP):
             # Never woken for a read: an arrival waits for the wake
             return
-        if tried in RETRY and now >= lastRead + self._settings["chargingReadSecs"]:
+        if readAnswer in RETRY and now >= readAt + self._settings["chargingReadSecs"]:
             # A failed read asked for, once more, a charging read's cadence on
-            want = want or (EVENT, bool(RETRY.index(tried)))
-        recent = now < lastRead + self._settings["sleepCourtesySecs"]
-        if want and not want[1] and (named or state == HOME_AWAKE and recent):
+            want = want or Ask(EVENT, readAnswer == RETRY_EXEMPT)
+        recent = now < readAt + self._settings["sleepCourtesySecs"]
+        if want and not want.exempt and (named or (state == HOME_AWAKE and recent)):
             self._take(v.vin, want)
             want = None
         flowing = getattr(standIn(v), "value", None) == "Charging"
@@ -347,12 +364,15 @@ class Watch:
         # read buys the battery level, worth it only where a policy reads it:
         # the car's sleep says when its charge ended
         policy = self.master.getModuleByName("Policy")
-        due = now >= lastRead + secs and (not price or policy and policy.readsBattery())
+        due = now >= readAt + secs and (not price or policy and policy.readsBattery())
         if not want and not (due and order.candidates(v, SET_AMPS)):
             return
         self._take(v.vin, want)
-        cls = want[0] if want else ROUTINE
-        miss = RETRY[want[1]] if cls == EVENT and tried not in RETRY else MISS
+        cls = want.cls if want else ROUTINE
+        if cls == EVENT and readAnswer not in RETRY:
+            miss = RETRY_EXEMPT if want.exempt else RETRY_COURTEOUS
+        else:
+            miss = MISS
         worker = "ble" if found[0].local else "cloud"
 
         def read():
@@ -362,9 +382,9 @@ class Watch:
             # when there is none; a snapshot carries no location, so a read
             # for the position pays. A refusal waits its cadence as a settled
             # read, not a miss
-            if price and not fix:
+            if price and not forPosition:
                 snapshot = order.read(
-                    v, "chargingState", False, ["FleetAPICached"], cutoff=lastRead
+                    v, "chargingState", False, ["FleetAPICached"], cutoff=readAt
                 )
                 if snapshot is not None:
                     return True
@@ -449,8 +469,8 @@ class Watch:
             seen = self._seen.get(v.vin)
         source = self._source(v, where, ble, checked[0])
         # A lost car nothing else asks is listened for on the radio's back-off
-        scan = not source and self._listen(v, where, ble, now)
-        via = (scan or source or (None,))[0]
+        scan = None if source else self._listen(v, where, ble, now)
+        via = scan[0] if scan else (source[0] if source else None)
         why = notWatched(self.master, v) or ("" if via else NO_SOURCE)
         last, at = scanned if scan else checked
         nextAt = None
diff --git a/tests/unit/test_command_path_parity.py b/tests/unit/test_command_path_parity.py
index 1216e094..954765be 100644
--- a/tests/unit/test_command_path_parity.py
+++ b/tests/unit/test_command_path_parity.py
@@ -1512,7 +1512,7 @@ def test_a_20_s_drive_inside_the_radius_between_policy_passes_is_seen(
     c.t = t0 + 30
     m.setPolicyLimit(50, transition=False)
     r.pass_()
-    assert Presence.arriving(v) == t0 + 25 > Presence.leaving(v) == t0 + 5
+    assert Presence.arrivedAt(v) == t0 + 25 > Presence.leftAt(v) == t0 + 5
     assert bleCommands(b) == ["charging-set-limit"] and b.runs[-1][2] == 50
     assert requests_mock.call_count == 0
 
diff --git a/tests/unit/test_presence.py b/tests/unit/test_presence.py
index 4df624e8..7939ac11 100644
--- a/tests/unit/test_presence.py
+++ b/tests/unit/test_presence.py
@@ -103,7 +103,7 @@ def test_an_unplug_event_newer_than_home_evidence_is_a_departure():
     v.observe("pluggedIn", True, TM)
     later(c)
     v.observe("pluggedIn", False, TM)
-    assert P.decide(m, v) == (P.NOT_HOME, "unplug", c.t) and P.leaving(v) == c.t
+    assert P.decide(m, v) == (P.NOT_HOME, "unplug", c.t) and P.leftAt(v) == c.t
 
 
 def twcNames(m, v, c, state=0x03):
@@ -193,7 +193,7 @@ def test_marks_record_events_when_observed_not_when_evaluated():
     started = c.t
     later(c, 20)  # a 20 s drive, never evaluated in between
     v.observe("shiftState", "P", TM)
-    assert (P.leaving(v), P.arriving(v)) == (started, c.t)
+    assert (P.leftAt(v), P.arrivedAt(v)) == (started, c.t)
     assert P.presence(m, v) == P.PRESUMED  # the drive was seen
 
 
@@ -879,7 +879,7 @@ def test_a_restores_own_ble_reply_re_applies_nothing():
     assert p.calls == [("setChargeLimit", VIN, 90)] and m.heldLimits.get(VIN) is None
     later(c)
     v.observe("bleReach", True, "TeslaBLE")  # the restore's own reply
-    assert P.presence(m, v) == P.HOME and P.leaving(v) > P.arriving(v)
+    assert P.presence(m, v) == P.HOME and P.leftAt(v) > P.arrivedAt(v)
     for _ in range(3):
         later(c, 60)
         m.setPolicyLimit(50, transition=False)
@@ -1615,7 +1615,7 @@ def scanOnly(life):
 @pytest.mark.parametrize("life", [False, True])
 def test_an_attribution_never_reads_a_car_the_scan_alone_answered_for(life):
     m, v, c, b = scanOnly(life)
-    P.pick(m, offered=32, read=True, since=c.t)
+    P.pick(m, offerSource=32, read=True, since=c.t)
     assert b.pings == [VIN] and b.fetched == []
 
 
@@ -1776,7 +1776,7 @@ def test_a_closed_charge_port_while_awake_marks_an_unplug():
 def test_an_open_charge_port_is_not_plug_evidence():
     m, v, c = placed()
     v.observe("chargePortOpen", True, "TeslaBLE")
-    assert v.markAt("plugIn") == P.NEVER and P.pluggedNow(m, v, None) is None
+    assert v.markAt("plugIn") == P.NEVER and P.pluggedNow(m, v, ifUnknown=None) is None
 
 
 def test_check_plug_answers_from_an_awake_closed_door_without_a_read():
@@ -1842,10 +1842,10 @@ def test_a_cached_plug_after_an_unplug_leaves_the_plug_unknown():
     # It places the car on no EVSE, but the unplug is no longer known
     m, v, c = placed()
     v.observe("chargingState", "Disconnected", "FleetAPI")
-    assert P.pluggedNow(m, v, None) is False
+    assert P.pluggedNow(m, v, ifUnknown=None) is False
     later(c, 3600)
     v.observe("chargingState", "Complete", "FleetAPICached")
-    assert P.pluggedNow(m, v, None) is None and P.pluggedNow(m, v) is False
+    assert P.pluggedNow(m, v, ifUnknown=None) is None and P.pluggedNow(m, v) is False
     assert v.markAt("plugIn") == P.NEVER
 
 
```

# PR: refactor/readability-admission

````markdown
Readability: name admission's parts for what they hold

This is a readability pass over admission and distribution in `TWCMaster.py` and over `ChargingPoint.setTargetPower`. It changes no behaviour. Each name now means one thing, and the caller and `_admit` use the same names for the four values it returns:

- `_admit` result `pool, given, left, budgets` -> `seated, held, shared, budgets` on both sides (`given` is now a copy of `held` in the caller)
- `self._held` (per-car steady reading) -> `self._steady`, unpacked into `wasRoom, wasState, wasDraw, roomSince, steadySince` instead of read as `last[0]`..`last[4]`
- `hold` (a delay) -> `delaySecs`; `held` (a bool) -> `settled`; `held` now only names points held at their minimum
- `room` (list in `_admit`) -> `standby`; the `(a if c else b).append(p)` and `held.update(... if cut else {})` tricks -> a plain `if cut:` block and a `hold()` helper
- `_draws` -> `_budgetsOf`; loop variable `c` -> `budget`
- `self._willing` gets its own assignment, not one inside a tuple
- `ChargingPoint`: `twc, car` -> `twcCarries, carCarries`; `mine` -> `heartbeatKeys`; `own` -> `rateHeartbeatCars`
- The `_admit` and `_followAdmission` header comments are rewritten as plain sentences. `_admit`'s comment had said drawing points sort first; it now describes the order the code uses: points that want power first, and among those the ones already drawing, so a charging car keeps its seat.

Evidence: full unit suite (`pytest tests --ignore=tests/API --ignore=tests/integration`): 2618 passed, 1 xfailed. The only test changes follow the renames.

Changelog: none (no behaviour change)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
````

## Commits
```
e2a21016 Name ChargingPoint's rate carriers and heartbeat cars
81f2709c Name admission's parts for what they hold
```
## Diff
```diff
diff --git a/lib/TWCManager/EVSEInstance/ChargingPoint.py b/lib/TWCManager/EVSEInstance/ChargingPoint.py
index 87946620..0497c69d 100644
--- a/lib/TWCManager/EVSEInstance/ChargingPoint.py
+++ b/lib/TWCManager/EVSEInstance/ChargingPoint.py
@@ -131,7 +131,7 @@ class ChargingPoint(EVSEInstance):
         # A car member's rate goes through its endpoint; a car only the TWC
         # names gets the "heartbeat" rate
         desired, members = self.master.desired, {e.vehicleKey for e in cars}
-        mine = [k for k in self.carKeys if k not in members]
+        heartbeatKeys = [k for k in self.carKeys if k not in members]
 
         def withdraw(keys):
             # Only our own rate: never a lift, nor a car endpoint's
@@ -140,25 +140,25 @@ class ChargingPoint(EVSEInstance):
                 if d is not None and d.by == "heartbeat":
                     desired.clearIf(k, AMPS, d.value)
 
-        def own(amps, by, lift=False):
+        def rateHeartbeatCars(amps, by, lift=False):
             # A car that left the set keeps no rate of ours
-            withdraw([k for k in local._lastKeys if k not in mine])
-            local._lastKeys = mine
-            for k in mine:
+            withdraw([k for k in local._lastKeys if k not in heartbeatKeys])
+            local._lastKeys = heartbeatKeys
+            for k in heartbeatKeys:
                 desired.set(k, AMPS, int(amps), by, lift=lift)
 
-        twc, car = self.carriers()
+        twcCarries, carCarries = self.carriers()
         if not watts:
             # A stop is the charging aspect; a pending lift still goes
             local.setTargetPower(0)
             for e in cars:
                 e.setTargetPower(0)
-            if car:
+            if carCarries:
                 withdraw(local._lastKeys)
             return
         amps = self.convertWattsToAmps(watts, self.currentVoltage)
         floor = local.layerFloorAmps()
-        if twc and (not car or amps >= floor):
+        if twcCarries and (not carCarries or amps >= floor):
             local.setTargetPower(watts)
             for e in cars:
                 # The TWC carries: the car keeps no rate of ours
@@ -168,11 +168,13 @@ class ChargingPoint(EVSEInstance):
             # Once per session; in mode 3 only for a car member that would
             # cap below the offer (undershoot is safe; unknown is left
             # alone), a car only the TWC names always
-            lifts = [e.vehicleKey for e in cars if not car or self._caps(e, amps)]
+            lifts = [
+                e.vehicleKey for e in cars if not carCarries or self._caps(e, amps)
+            ]
             for k in lifts:
                 desired.set(k, AMPS, local.wiringMaxAmps, "lift", lift=True)
-            own(local.wiringMaxAmps, "lift", lift=True)
-            if lifts or mine:
+            rateHeartbeatCars(local.wiringMaxAmps, "lift", lift=True)
+            if lifts or heartbeatKeys:
                 local.liftedSession = local.plugSessions
             return
         # The car carries: the next return to the TWC may lift again. With
@@ -185,7 +187,7 @@ class ChargingPoint(EVSEInstance):
         )
         for e in cars:
             e.setTargetPower(watts)
-        own(amps, "heartbeat")
+        rateHeartbeatCars(amps, "heartbeat")
 
     @staticmethod
     def _caps(member, amps) -> bool:
diff --git a/lib/TWCManager/TWCMaster.py b/lib/TWCManager/TWCMaster.py
index d98435c2..2f57f99f 100644
--- a/lib/TWCManager/TWCMaster.py
+++ b/lib/TWCManager/TWCMaster.py
@@ -89,7 +89,8 @@ def _drawAmps(point) -> float:
     return max((v.value("actualCurrent") or 0 for v in charging), default=0)
 
 
-def _draws(point, budgets) -> set:
+def _budgetsOf(point, budgets) -> set:
+    # The names of the budgets the point draws from
     return budgets.keys() & {"all", *point.controllers}
 
 
@@ -208,8 +209,9 @@ class TWCMaster:
         self.vehicleRegistry.removed = self._vehicleRemoved
         self.reconciler = VehicleReconciler(self)
         # The control tick's admission (the cars with room), the cars that
-        # would charge, and each car's (room, state, draw, roomSince, since)
-        self.admission, self._willing, self._held = frozenset(), set(), {}
+        # would charge, and each car's last steady reading:
+        # (room, chargingState, draw, roomSince, steadySince)
+        self.admission, self._willing, self._steady = frozenset(), set(), {}
         # The policy's charge limit: None while it sets none, UNDECIDED before
         # its first pass
         self.policyLimit = UNDECIDED
@@ -630,21 +632,22 @@ class TWCMaster:
         self._followAdmission(self.admission - placed, None, now)
         # A car no point serves has gone: it comes back with no hold or cut
         self._cut &= placed
-        for key in self._held.keys() - placed - self.admission:
-            del self._held[key]
+        for key in self._steady.keys() - placed - self.admission:
+            del self._steady[key]
 
     def _followAdmission(self, keys, point, now) -> None:
-        # Wanted charging follows admission, each change once it has held
-        # startStopDelay with the draw steady: the EMS may read low once, a
-        # cut mid-negotiation could strand a car, and power at the edge must
-        # not toggle a command each pass. A fixed policy has no such noise,
-        # so it waits for nothing. Only a first start, or a Gen2's (its offer
-        # drops our stop), goes at once. At a Gen2 only protocol 2 stops, and
-        # only a draw over 4 A (one ramping or finishing is left alone); an
-        # anonymous car is left to its Gen2, as elsewhere it would fan out
+        # Wanted charging follows admission. Each change waits until the
+        # car's room, state and draw have held steady for startStopDelay:
+        # the EMS may read low once, a cut mid-negotiation could strand a
+        # car, and power at the edge must not toggle a command each pass.
+        # A fixed policy has no such noise, so it waits for nothing. Only a
+        # first start, or a start at a Gen2 (whose offer drops our stop),
+        # goes at once. At a Gen2 only protocol 2 stops, and only a draw
+        # over 4 A; a car ramping or finishing is left alone. An anonymous
+        # car is left to its Gen2, as anywhere else it would fan out.
         policy = self.getModuleByName("Policy")
         green = policy is None or policy.policyIsGreen()
-        hold = self.config["config"].get("startStopDelay", 60) if green else -1
+        delaySecs = self.config["config"].get("startStopDelay", 60) if green else -1
         ends = getattr(point, "localEndpoints", ())
         gen2 = [e for e in ends if hasattr(e, "pointAmps")]
         drawing = point is not None and _drawing(point)
@@ -653,20 +656,23 @@ class TWCMaster:
                 continue
             # The car's own readings, the same at each point it may be on
             room = v.key in self.admission
-            seen = (room, v.value("chargingState"), v.value("actualCurrent") or 0)
-            last = self._held.get(v.key)
-            if not last or last[:2] != seen[:2] or abs(last[2] - seen[2]) > 0.8:
-                begun = last[3] if last and last[0] == room else now
-                last = self._held[v.key] = (*seen, begun, now)
-            held = now - last[4] > hold
-            if room and now - last[3] > hold:
+            state, draw = v.value("chargingState"), v.value("actualCurrent") or 0
+            wasRoom, wasState, wasDraw, roomSince, steadySince = self._steady.get(
+                v.key, (None, None, 0, now, now)
+            )
+            if (wasRoom, wasState) != (room, state) or abs(wasDraw - draw) > 0.8:
+                roomSince = roomSince if wasRoom == room else now
+                steadySince = now
+                self._steady[v.key] = (room, state, draw, roomSince, steadySince)
+            settled = now - steadySince > delaySecs
+            if room and now - roomSince > delaySecs:
                 # Its cut ends on room alone: a draw at the minimum may wander
                 self._cut -= {v.key}
             want = getattr(self.desired.get(v.key, CHARGING), "value", None)
             if (
                 room
                 and v.key in self._willing
-                and (want is None or want is False and held)
+                and (want is None or (want is False and settled))
             ):
                 if not satisfied(CHARGING, True, known(v, CHARGING, True)):
                     self.cancelStopCarsCharging(v.key)
@@ -681,7 +687,7 @@ class TWCMaster:
                 # Each pass: in mode 1 a stop that has not taken lowers the
                 # limit. Until then the stop waits, and one undelivered is moot
                 sent = self.desired.record(v.key, CHARGING).lastSentAt
-                if held:
+                if settled:
                     self.stopCarsCharging(v.key)
                 elif want is not False or sent < self.desired.get(v.key, CHARGING).at:
                     self.cancelStopCarsCharging(v.key)
@@ -719,24 +725,27 @@ class TWCMaster:
         """
         try:
             points = self.chargingPoints()
-            pool, given, left, budgets = self._admit(points)
-            # The admitted points share what the held ones leave at one water
+            seated, held, shared, budgets = self._admit(points)
+            # The seated points share what the held ones leave at one water
             # level. Where a budget would be exceeded, its points share it
             # alone, the rest what remains
-            while pool:
-                share = waterLevel(pool, left["all"])
+            given = dict(held)
+            while seated:
+                share = waterLevel(seated, shared["all"])
                 spent = {
-                    c: sum(w for p, w in share.items() if c in _draws(p, left))
-                    for c in left
+                    b: sum(w for p, w in share.items() if b in _budgetsOf(p, shared))
+                    for b in shared
                 }
-                over = next((c for c in left if spent[c] > left[c]), None)
-                group = [p for p in pool if over in _draws(p, left)] if over else pool
-                share = waterLevel(group, left[over]) if over else share
+                over = next((b for b in shared if spent[b] > shared[b]), None)
+                group = seated
+                if over:
+                    group = [p for p in seated if over in _budgetsOf(p, shared)]
+                    share = waterLevel(group, shared[over])
                 for p in group:
                     given[p] = share[p]
-                    for c in _draws(p, left):
-                        left[c] -= share[p]
-                pool = [p for p in pool if p not in group]
+                    for budget in _budgetsOf(p, shared):
+                        shared[budget] -= share[p]
+                seated = [p for p in seated if p not in group]
             # A car comes up to a new share at once, but another comes down
             # to its own only as it ramps: each point gets no more than what
             # the others' shares, or their draws where higher, leave in each
@@ -747,13 +756,13 @@ class TWCMaster:
                 if not p.isReadOnly
             }
             for p, watts in list(given.items()):
-                for c in _draws(p, budgets):
+                for budget in _budgetsOf(p, budgets):
                     others = sum(
                         w
                         for q, w in taken.items()
-                        if q is not p and c in _draws(q, budgets)
+                        if q is not p and budget in _budgetsOf(q, budgets)
                     )
-                    watts = min(watts, max(budgets[c] - others, p.minPower))
+                    watts = min(watts, max(budgets[budget] - others, p.minPower))
                 given[p] = watts
             # Points neither admitted nor held get a target of 0. For an idle Gen2 TWC that
             # 0 goes out as its hardware minimum (the TWC treats an offer of 0
@@ -778,47 +787,63 @@ class TWCMaster:
         return points
 
     def _admit(self, points) -> tuple:
-        # Drawing points first, so a charging car keeps its seat; then, in
-        # point order, those that want power or whose car would charge, each
-        # while its minimum fits what is left in every budget it draws from.
-        # self.admission names their cars, then in turn those at other points
-        # whose minimum fits what is left (two never share it): the room a
-        # start would find. The policy's amps convert at the voltage the TWCs
-        # measure, as they convert back. A point drawing without a seat is
-        # held at its minimum, counted, while the hold decides whether the
-        # want of room lasts (a Gen2's 0 offer is its minimum already)
+        # Points that want power come first, and among those the ones already
+        # drawing, so a charging car keeps its seat and admission does not
+        # flap; ties keep point order. Each is admitted while its minimum
+        # fits every budget it draws from: seated if it wants power, else on
+        # standby, its minimum kept as the room a start would find. A point
+        # whose car was cut goes on standby, held at its minimum. A drawing
+        # point that does not fit is held at its minimum too, unless it is a
+        # Gen2, while the start and stop delay decides whether the want of
+        # room lasts.
+        # Returns the seated, the held (each at its minimum, in watts), what
+        # the budgets leave the seated to share, and the budgets.
+        # The policy's amps convert at the voltage the TWCs measure, as they
+        # convert back
         available = self.convertAmpsToWatts(self.getMaxAmpsToDivideAmongSlaves())
         budgets = dict(self._budgets(), all=available)
         cars = self.vehicleRegistry.vehicles()
         willing = {v.key for v in cars if v.vin and wouldCharge(self, v)}
-        left, seated, room, self._willing = dict(budgets), [], [], willing
-        held, shared = {}, dict(budgets)
+        self._willing = willing
+        left, shared, seated, standby, held = dict(budgets), dict(budgets), [], [], {}
 
         def wanted(p):
             return p.wantsToCharge or _carsAt(p) & willing
 
+        def hold(p, need):
+            # At its minimum, which the seated do not share
+            held[p] = need
+            for budget in _budgetsOf(p, shared):
+                shared[budget] -= need
+
         for p in sorted(points, key=lambda p: (not wanted(p), not _drawing(p))):
             if p.isReadOnly:
                 continue
             need = p.minPower
             if p.maxPower < need <= left["all"] and wanted(p):
                 self._noteRefusedPoint(p, left["all"])
-            elif need <= p.maxPower and all(need <= left[c] for c in _draws(p, left)):
+            elif need <= p.maxPower and all(
+                need <= left[b] for b in _budgetsOf(p, left)
+            ):
                 # One cut to its minimum stays there until room has held, or
                 # power at the edge would re-rate it each pass
                 cut = _carsAt(p) & self._cut
-                (seated if wanted(p) and not cut else room).append(p)
-                held.update({p: need} if cut else {})
-                for c in _draws(p, left):
-                    left[c] -= need
-                    shared[c] -= need if cut else 0
+                if cut:
+                    hold(p, need)
+                if wanted(p) and not cut:
+                    seated.append(p)
+                else:
+                    standby.append(p)
+                for budget in _budgetsOf(p, left):
+                    left[budget] -= need
             elif need <= p.maxPower and _drawing(p) and "Gen2TWCs" not in p.controllers:
-                # An anonymous car is never stopped, so never held back
-                held[p] = need
+                # A Gen2's 0 offer is its minimum already. An anonymous car is
+                # never stopped, so never held back
+                hold(p, need)
                 self._cut |= {k for k in _carsAt(p) if not isAnonKey(k)}
-                for c in _draws(p, left):
-                    left[c], shared[c] = left[c] - need, shared[c] - need
-        admission = set().union(*map(_carsAt, room + seated))
+                for budget in _budgetsOf(p, left):
+                    left[budget] -= need
+        admission = set().union(*map(_carsAt, standby + seated))
         if left["all"] >= self.convertAmpsToWatts(VehicleEndpoint.MIN_AMPS):
             # A car on no point of ours may start on what is left
             admission |= {v.key for v in cars}.difference(*map(_carsAt, points))
diff --git a/tests/unit/test_admission.py b/tests/unit/test_admission.py
index fada0439..5d148e2e 100644
--- a/tests/unit/test_admission.py
+++ b/tests/unit/test_admission.py
@@ -398,7 +398,7 @@ def test_a_failed_split_leaves_no_room():
     m, r, v, c, p = finished(limit=90, state="Stopped")
     m.setMaxAmpsToDivideAmongSlaves(32)
     m.controlPass(now=c())
-    assert VIN in m.admission and VIN in m._held
+    assert VIN in m.admission and VIN in m._steady
     points = m.chargingPoints()
     for point in points:
         point.setTargetPower = lambda watts: 1 / 0
@@ -646,7 +646,7 @@ def test_a_car_that_unplugs_while_cut_comes_back_with_its_share():
     assert rates(f) == [16, 5] and VIN in m._cut
     leave(v)
     run(m, r, c, 10)
-    assert VIN not in m._cut and VIN not in m._held
+    assert VIN not in m._cut and VIN not in m._steady
     c.t += 600
     v.observe("pluggedIn", True, "Gen3TWC")
     m.setMaxAmpsToDivideAmongSlaves(16)
diff --git a/tests/unit/test_charging_reconciler.py b/tests/unit/test_charging_reconciler.py
index 51dfc4d7..35e07f4a 100644
--- a/tests/unit/test_charging_reconciler.py
+++ b/tests/unit/test_charging_reconciler.py
@@ -27,7 +27,7 @@ def slave(m):
 
 def ready_to_stop(m):
     # The 60 s hold has run: each car without room drew this much for a minute
-    m._held = {k: (*h[:-1], h[-1] - 61) for k, h in m._held.items()}
+    m._steady = {k: (*h[:-1], h[-1] - 61) for k, h in m._steady.items()}
 
 # The heartbeat and the master
 
diff --git a/tests/unit/test_offer_characterization.py b/tests/unit/test_offer_characterization.py
index d42cc1fc..a89438cb 100644
--- a/tests/unit/test_offer_characterization.py
+++ b/tests/unit/test_offer_characterization.py
@@ -214,7 +214,7 @@ def calls(m):
 
 def age(m, seconds):
     # The car has been without room, its draw steady, seconds longer
-    m._held = {key: (*h[:-1], h[-1] - seconds) for key, h in m._held.items()}
+    m._steady = {key: (*h[:-1], h[-1] - seconds) for key, h in m._steady.items()}
 
 
 def test_a_car_drawing_over_4a_offered_zero_is_stopped_after_60s():
```

