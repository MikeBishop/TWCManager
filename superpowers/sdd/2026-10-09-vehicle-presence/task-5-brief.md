### Task 5: VehiclePresence core (state, rules, scheduling, thread)

**Files:**
- Create: `lib/TWCManager/VehiclePresence.py`
- Modify: `lib/TWCManager/TWCMaster.py:18` (import), `:106-108` (construct after the vehicle queue)
- Test: `tests/unit/test_vehicle_presence.py` (create), `tests/unit/test_twcmaster.py`

**Interfaces:**
- Consumes: `master.config["vehicle"]["presenceSources"]` (optional), `master.settings["Vehicles"]`, `master.getModuleByName("TeslaAPI").getCarApiVehicles()`.
- Produces (`lib/TWCManager/VehiclePresence.py`):
  - constants `HOME = "home"`, `AWAY = "away"`, `UNKNOWN = "unknown"`, `DEFAULT_SOURCE_ORDER = ["telemetry", "ble", "api"]`.
  - `VehiclePresence(master, sources=None, onArrival=None, onDeparture=None, knownVehicles=None, sourceOrder=None, clock=time.monotonic)`.
    - `sources`: `{name: callable(vin) -> None | {"atHome": bool|None, "limit": int|None}}`. `None` = source does not apply; `atHome=None` = no answer. Default `{}` (Task 6 changes it to `buildSources(master)`).
    - `onArrival(vin, currentLimit)`, `onDeparture(vin, currentLimit)`: default `None` (Task 7 supplies defaults).
    - `knownVehicles() -> list[str]`: default = union of `settings["Vehicles"]` and API VINs.
  - `start()`, `stop()`, `state(vin)`, `nominate(vin, reason, delays=(0,))`, `observeContact(vin, reachable, probe=False)`, `observeLocation(vin, atHome)`, and `runPass()` (one synchronous pass; tests drive it directly).
  - Class attributes `PROBE_INTERVAL = 60`, `AWAY_AFTER_FAILED_PROBES = 2`.
  - `TWCMaster.vehiclePresence` is constructed in `__init__` with no thread started.

- [ ] **Step 1: Write the failing core tests**

Create `tests/unit/test_vehicle_presence.py`:

```python
"""
VehiclePresence core: decision rules, source fallback, scheduling, rate
limit, and the thread. Sources and handlers are injected callables; a fake
clock drives due times, so nothing here sleeps.
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from TWCManager.VehiclePresence import AWAY, HOME, UNKNOWN, VehiclePresence

WAIT = 2.0
V1 = "5YJ3E1EA1KF000001"
V2 = "5YJ3E1EA1KF000002"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Recorder:
    def __init__(self):
        self.arrivals = []
        self.departures = []

    def onArrival(self, vin, limit):
        self.arrivals.append((vin, limit))

    def onDeparture(self, vin, limit):
        self.departures.append((vin, limit))


def answer(atHome, limit=None):
    """A source that always gives this answer. atHome="n/a" means the source
    does not apply (returns None); None means "no answer"."""
    calls = []

    def source(vin):
        calls.append(vin)
        if atHome == "n/a":
            return None
        return {"atHome": atHome, "limit": limit}

    source.calls = calls
    return source


def make(sources, order=None, known=(V1, V2), clock=None, master=None):
    rec = Recorder()
    clock = clock or FakeClock()
    presence = VehiclePresence(
        master or Mock(),
        sources=sources,
        onArrival=rec.onArrival,
        onDeparture=rec.onDeparture,
        knownVehicles=lambda: list(known),
        sourceOrder=list(sources) if order is None else order,
        clock=clock,
    )
    return presence, rec, clock


def probe(presence, clock, vin=V1):
    """Nominate vin, step the clock past the rate limit, and run one pass."""
    clock.now += VehiclePresence.PROBE_INTERVAL + 1
    presence.nominate(vin, "test")
    presence.runPass()


class TestDecisionRules:
    def test_every_vin_starts_unknown(self):
        presence, rec, clock = make({})
        assert presence.state(V1) == UNKNOWN

    def test_unknown_to_home_runs_arrival(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, True)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert rec.arrivals == [(V1, None)]
        assert rec.departures == []

    def test_unknown_to_away_runs_nothing(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, False)
        presence.runPass()
        assert presence.state(V1) == AWAY
        assert rec.arrivals == [] and rec.departures == []

    def test_home_to_away_runs_departure(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, True)
        presence.runPass()
        presence.observeLocation(V1, False)
        presence.runPass()
        assert presence.state(V1) == AWAY
        assert rec.departures == [(V1, None)]

    def test_contact_success_sets_home(self):
        presence, rec, clock = make({})
        presence.observeContact(V1, True)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert rec.arrivals == [(V1, None)]

    def test_contact_failure_is_ignored_probe_or_not(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, True)
        presence.runPass()
        presence.observeContact(V1, False)
        presence.observeContact(V1, False, probe=True)
        presence.observeContact(V1, False, probe=True)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert rec.departures == []

    def test_contact_success_counts_even_when_location_said_away(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, False)
        presence.runPass()
        presence.observeContact(V1, True)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert rec.arrivals == [(V1, None)]

    def test_ble_probe_success_sets_home_with_limit(self):
        presence, rec, clock = make({"ble": answer(True, limit=80)})
        probe(presence, clock)
        assert presence.state(V1) == HOME
        assert rec.arrivals == [(V1, 80)]

    def test_two_consecutive_failed_ble_probes_make_away(self):
        presence, rec, clock = make({"ble": answer(None)})
        presence.observeLocation(V1, True)
        presence.runPass()
        probe(presence, clock)
        assert presence.state(V1) == HOME
        probe(presence, clock)
        assert presence.state(V1) == AWAY
        assert rec.departures == [(V1, None)]

    def test_successful_probe_resets_the_failure_count(self):
        answers = iter([None, True, None, None])
        source = lambda vin: {"atHome": next(answers), "limit": None}
        presence, rec, clock = make({"ble": source})
        probe(presence, clock)  # fail 1
        probe(presence, clock)  # success: count back to 0
        probe(presence, clock)  # fail 1
        assert presence.state(V1) == HOME
        probe(presence, clock)  # fail 2
        assert presence.state(V1) == AWAY

    def test_ble_failures_do_not_count_when_telemetry_is_live(self):
        presence, rec, clock = make(
            {"telemetry": answer(None), "ble": answer(None)},
            order=["telemetry", "ble"],
        )
        presence.observeLocation(V1, True)
        presence.runPass()
        for _ in range(3):
            probe(presence, clock)
        assert presence.state(V1) == HOME

    def test_ble_failures_do_not_count_when_a_later_source_answers(self):
        presence, rec, clock = make(
            {"ble": answer(None), "api": answer(True)}, order=["ble", "api"]
        )
        probe(presence, clock)
        probe(presence, clock)
        assert presence.state(V1) == HOME
        assert presence._failedProbes[V1] == 0


class TestSourceFallback:
    def test_first_definite_answer_wins(self):
        telemetry, ble = answer(False), answer(True)
        presence, rec, clock = make(
            {"telemetry": telemetry, "ble": ble}, order=["telemetry", "ble"]
        )
        probe(presence, clock)
        assert presence.state(V1) == AWAY
        assert ble.calls == []

    def test_inapplicable_source_is_skipped(self):
        telemetry, ble = answer("n/a"), answer(True)
        presence, rec, clock = make(
            {"telemetry": telemetry, "ble": ble}, order=["telemetry", "ble"]
        )
        probe(presence, clock)
        assert presence.state(V1) == HOME
        assert telemetry.calls == [V1]

    def test_order_follows_the_setting_and_skips_removed_entries(self):
        presence, rec, clock = make(
            {"telemetry": answer(True), "ble": answer(True), "api": answer(False)},
            order=["api"],
        )
        probe(presence, clock)
        assert presence.state(V1) == AWAY
        assert presence._order == ["api"]

    def test_unknown_source_name_is_ignored_with_a_warning(self):
        with patch("TWCManager.VehiclePresence.logger") as log:
            presence, rec, clock = make({"ble": answer(True)}, order=["bogus", "ble"])
        assert presence._order == ["ble"]
        log.warning.assert_called_once()

    def test_order_is_read_from_master_config(self):
        master = Mock()
        master.config = {"vehicle": {"presenceSources": ["api", "ble"]}}
        presence = VehiclePresence(
            master,
            sources={"telemetry": answer(True), "ble": answer(True), "api": answer(True)},
            knownVehicles=lambda: [],
        )
        assert presence._order == ["api", "ble"]

    def test_source_exception_counts_as_no_answer(self):
        def boom(vin):
            raise RuntimeError("adapter on fire")

        presence, rec, clock = make({"ble": boom, "api": answer(True)}, order=["ble", "api"])
        probe(presence, clock)
        assert presence.state(V1) == HOME

    def test_limit_comes_from_the_first_source_that_reports_one(self):
        presence, rec, clock = make(
            {
                "telemetry": lambda vin: {"atHome": None, "limit": 90},
                "api": answer(True, limit=70),
            },
            order=["telemetry", "api"],
        )
        probe(presence, clock)
        assert rec.arrivals == [(V1, 90)]


class TestScheduling:
    def test_nominate_none_expands_to_known_vins_when_due(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source}, known=(V1, V2))
        presence.nominate(None, "api")
        presence.runPass()
        assert source.calls == [V1, V2]
        assert [v for v, _ in rec.arrivals] == [V1, V2]

    def test_due_time_batching(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source})
        presence.nominate(V1, "unplug", delays=(100,))
        presence.nominate(V2, "power-start", delays=(0,))
        presence.runPass()
        assert source.calls == [V2]
        clock.now += 99
        presence.runPass()
        assert source.calls == [V2]
        clock.now += 1
        presence.runPass()
        assert source.calls == [V2, V1]

    def test_rate_limit_one_probe_per_vin_per_60s(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source})
        presence.nominate(V1, "a")
        presence.runPass()
        clock.now += 30
        presence.nominate(V1, "b")
        presence.runPass()
        assert source.calls == [V1]
        clock.now += 31
        presence.nominate(V1, "c")
        presence.runPass()
        assert source.calls == [V1, V1]

    def test_events_only_affect_the_vin_concerned(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, True)
        presence.observeLocation(V2, False)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert presence.state(V2) == AWAY
        assert rec.arrivals == [(V1, None)]
        presence.observeLocation(V2, True)
        presence.runPass()
        assert rec.arrivals == [(V1, None), (V2, None)]
        assert presence.state(V1) == HOME

    def test_observers_record_only(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source})
        presence.nominate(V1, "a")
        presence.observeLocation(V2, True)
        presence.observeContact(V2, True)
        assert source.calls == []
        assert rec.arrivals == []
        assert presence.state(V2) == UNKNOWN

    def test_handlers_run_without_the_presence_lock(self):
        seen = []
        presence = VehiclePresence(
            Mock(),
            sources={},
            onArrival=lambda vin, limit: seen.append(presence._lock.locked()),
            knownVehicles=lambda: [],
            sourceOrder=[],
            clock=FakeClock(),
        )
        presence.observeLocation(V1, True)
        presence.runPass()
        assert seen == [False]


class TestThread:
    def test_start_is_idempotent(self):
        presence, rec, clock = make({}, clock=time.monotonic)
        presence.start()
        thread = presence._thread
        presence.start()
        assert presence._thread is thread
        assert thread.daemon and thread.name == "VehiclePresence"
        presence.stop()
        thread.join(WAIT)
        assert not thread.is_alive()

    def test_thread_runs_a_pass_when_nominated(self):
        arrived = threading.Event()
        presence = VehiclePresence(
            Mock(),
            sources={"ble": answer(True)},
            onArrival=lambda vin, limit: arrived.set(),
            knownVehicles=lambda: [],
            sourceOrder=["ble"],
        )
        presence.start()
        presence.nominate(V1, "power-start")
        assert arrived.wait(WAIT)
        assert presence.state(V1) == HOME
        presence.stop()
        presence._thread.join(WAIT)

    def test_stop_prevents_new_passes(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source}, clock=time.monotonic)
        presence.start()
        presence.stop()
        presence._thread.join(WAIT)
        assert not presence._thread.is_alive()
        presence.nominate(V1, "late")
        assert source.calls == []
        assert presence.state(V1) == UNKNOWN

    def test_thread_survives_an_exception_in_a_pass(self):
        raised = threading.Event()
        arrived = threading.Event()

        def known():
            raised.set()
            raise RuntimeError("settings on fire")

        presence = VehiclePresence(
            Mock(),
            sources={"ble": answer(True)},
            onArrival=lambda vin, limit: arrived.set(),
            knownVehicles=known,
            sourceOrder=["ble"],
        )
        presence.start()
        presence.nominate(None, "api")
        assert raised.wait(WAIT)
        presence.nominate(V1, "power-start")
        assert arrived.wait(WAIT)
        presence.stop()
        presence._thread.join(WAIT)
```

Append to `tests/unit/test_twcmaster.py`, inside `class TestVehicleCommandRouting` (after `test_master_creates_unstarted_queue`):

```python
    def test_master_creates_unstarted_presence(self):
        from TWCManager.TWCMaster import TWCMaster
        from TWCManager.VehiclePresence import VehiclePresence

        m = TWCMaster(
            "AB",
            {
                "config": {
                    "wiringMaxAmpsAllTWCs": 80,
                    "maxAmpsAllowedFromGrid": None,
                }
            },
        )
        assert isinstance(m.vehiclePresence, VehiclePresence)
        assert m.vehiclePresence.master is m
        assert m.vehiclePresence._thread is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_vehicle_presence.py tests/unit/test_twcmaster.py -q -p no:cacheprovider -k "presence or Presence"`
Expected: collection error `ModuleNotFoundError: No module named 'TWCManager.VehiclePresence'`.

- [ ] **Step 3: Implement the core**

Create `lib/TWCManager/VehiclePresence.py`:

```python
# Tracks where each vehicle is (home / away / unknown), keyed by VIN.
#
# VehiclePresence is a client of the vehicle modules rather than part of any
# one of them. Observers (nominate, observeContact, observeLocation) may be
# called from any thread: they only record under the presence lock and set
# the wake event. One daemon thread does all the I/O: it probes due VINs
# through the configured sources, applies the decision rules, and runs the
# arrival/departure handlers, which only queue vehicle commands.
#
# Sources are callables vin -> None (source does not apply to this VIN) or
# {"atHome": True | False | None, "limit": int | None}, where atHome None
# means "no answer". Handlers are callables (vin, currentLimit).
import threading
import time
import traceback

from TWCManager.Logging.LoggerFactory import LoggerFactory

logger = LoggerFactory.get_logger("VehiclePresence", "Vehicle")

HOME = "home"
AWAY = "away"
UNKNOWN = "unknown"

DEFAULT_SOURCE_ORDER = ["telemetry", "ble", "api"]


class VehiclePresence:
    # No VIN is probed more often than this; a due time inside the window is
    # satisfied by the recent result.
    PROBE_INTERVAL = 60
    # BLE-only away rule: consecutive failed probes with no other answer.
    AWAY_AFTER_FAILED_PROBES = 2

    def __init__(
        self,
        master,
        sources=None,
        onArrival=None,
        onDeparture=None,
        knownVehicles=None,
        sourceOrder=None,
        clock=time.monotonic,
    ):
        self.master = master
        self._sources = {} if sources is None else dict(sources)
        self._onArrival = onArrival
        self._onDeparture = onDeparture
        self._knownVehicles = knownVehicles or self._defaultKnownVehicles
        self._clock = clock
        self._order = self._resolveOrder(sourceOrder)

        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None
        self._stopped = False
        self._state = {}  # vin -> HOME | AWAY | UNKNOWN
        self._failedProbes = {}  # vin -> consecutive BLE-only probe failures
        self._lastProbe = {}  # vin -> clock time of the last probe
        self._due = {}  # vin (None = all known) -> set of due clock times
        self._observations = []  # (kind, vin, value) awaiting the thread

    def _resolveOrder(self, sourceOrder):
        if sourceOrder is None:
            config = getattr(self.master, "config", None)
            vehicle = config.get("vehicle") if isinstance(config, dict) else None
            sourceOrder = (vehicle or {}).get("presenceSources", DEFAULT_SOURCE_ORDER)
        order = []
        for name in sourceOrder:
            if name not in DEFAULT_SOURCE_ORDER:
                logger.warning(
                    "Ignoring unknown presence source %r in vehicle.presenceSources",
                    name,
                )
            elif name in self._sources:
                order.append(name)
        return order

    def _defaultKnownVehicles(self):
        # Union of the VINs in settings["Vehicles"] and the API vehicle list.
        vins = []
        settings = getattr(self.master, "settings", None)
        if isinstance(settings, dict):
            vins.extend((settings.get("Vehicles") or {}).keys())
        api = self.master.getModuleByName("TeslaAPI")
        if api:
            try:
                for vehicle in api.getCarApiVehicles():
                    if vehicle.VIN and vehicle.VIN not in vins:
                        vins.append(vehicle.VIN)
            except Exception as e:
                logger.debug("Could not list API vehicles: %s", e)
        return vins

    # -- public interface: observers record only, no I/O -------------------

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopped = False
            self._thread = threading.Thread(
                target=self._run, name="VehiclePresence", daemon=True
            )
            thread = self._thread
        thread.start()

    def stop(self):
        # No new probes or handler commands after this. A pass already in
        # progress finishes. Returns immediately.
        with self._lock:
            self._stopped = True
        self._wake.set()

    def state(self, vin):
        with self._lock:
            return self._state.get(vin, UNKNOWN)

    def nominate(self, vin, reason, delays=(0,)):
        # Schedule a presence check for vin (None = every known vehicle) at
        # now + d for each d in delays.
        now = self._clock()
        with self._lock:
            self._due.setdefault(vin, set()).update(now + d for d in delays)
        logger.debug(
            "Presence check for %s nominated (%s) at +%s s",
            vin or "all vehicles",
            reason,
            ",".join(str(d) for d in delays),
        )
        self._wake.set()

    def observeContact(self, vin, reachable, probe=False):
        # A car that answered over BLE is home. A failed contact proves
        # nothing by itself (a command can fail for other reasons), and failed
        # probes are counted by the probe pass, which sees the result
        # directly; so only success is recorded here.
        if not reachable:
            return
        with self._lock:
            self._observations.append(("contact", vin, True))
        self._wake.set()

    def observeLocation(self, vin, atHome):
        # A location fix from telemetry or the API.
        with self._lock:
            self._observations.append(("location", vin, bool(atHome)))
        self._wake.set()

    # -- the thread --------------------------------------------------------

    def _run(self):
        try:
            while True:
                with self._lock:
                    if self._stopped:
                        return
                    timeout = self._timeUntilNextDue()
                self._wake.wait(timeout)
                self._wake.clear()
                with self._lock:
                    if self._stopped:
                        return
                try:
                    self.runPass()
                except Exception:
                    logger.error(
                        "VehiclePresence pass failed: %s", traceback.format_exc()
                    )
        except BaseException:
            logger.error(
                "VehiclePresence thread %s exiting: %s",
                threading.current_thread().name,
                traceback.format_exc(),
            )
            raise

    def _timeUntilNextDue(self):
        # Caller holds the lock. None means nothing is scheduled: wait for
        # an event.
        times = [t for due in self._due.values() for t in due]
        if not times:
            return None
        return max(0.0, min(times) - self._clock())

    def runPass(self):
        # One pass: apply recorded observations, probe due VINs, then run the
        # handlers for the VINs whose state changed. Public so tests can
        # drive it synchronously; the thread calls it on every wake.
        now = self._clock()
        with self._lock:
            observations, self._observations = self._observations, []
            dueVins = self._collectDue(now)

        transitions = []
        for kind, vin, value in observations:
            with self._lock:
                if kind == "contact":
                    transition = self._applyHome(vin)
                else:
                    transition = self._applyLocation(vin, value)
            if transition:
                transitions.append(transition)

        for vin in dueVins:
            with self._lock:
                if self._stopped:
                    break
                last = self._lastProbe.get(vin)
                if last is not None and now - last < self.PROBE_INTERVAL:
                    logger.debug(
                        "Presence probe for %s skipped: probed %.0f s ago",
                        vin,
                        now - last,
                    )
                    continue
                self._lastProbe[vin] = now
            outcome = self._probe(vin)  # I/O; the lock is not held
            with self._lock:
                transition = self._applyProbe(vin, outcome)
            if transition:
                transitions.append(transition)

        for vin, old, new, limit in transitions:
            with self._lock:
                stopped = self._stopped
            if stopped:
                return
            self._runHandler(vin, old, new, limit)

    def _collectDue(self, now):
        # Caller holds the lock. Pops every due time <= now and returns the
        # VINs to probe, in nomination order, without duplicates. None
        # expands to the known vehicles as of now.
        vins = []
        for key in list(self._due):
            ready = {t for t in self._due[key] if t <= now}
            if not ready:
                continue
            self._due[key] -= ready
            if not self._due[key]:
                del self._due[key]
            if key is None:
                vins.extend(self._knownVehicles())
            else:
                vins.append(key)
        return list(dict.fromkeys(vins))

    def _probe(self, vin):
        # Try the sources in order; the first definite answer decides.
        outcome = {
            "atHome": None,
            "limit": None,
            "bleFailed": False,
            "telemetryLive": False,
        }
        for name in self._order:
            try:
                result = self._sources[name](vin)
            except Exception as e:
                logger.debug("Presence source %s failed for %s: %s", name, vin, e)
                result = None
            if result is None:
                continue  # the source does not apply to this VIN
            if name == "telemetry":
                outcome["telemetryLive"] = True
            if outcome["limit"] is None and result.get("limit") is not None:
                outcome["limit"] = result["limit"]
            atHome = result.get("atHome")
            if atHome is None:
                if name == "ble":
                    outcome["bleFailed"] = True
                continue
            outcome["atHome"] = bool(atHome)
            logger.debug(
                "Presence source %s says %s is %s",
                name,
                vin,
                "home" if atHome else "away",
            )
            break
        return outcome

    # -- decision rules; callers hold the lock -----------------------------

    def _applyProbe(self, vin, outcome):
        if outcome["atHome"] is not None:
            self._failedProbes[vin] = 0
            return self._setState(
                vin, HOME if outcome["atHome"] else AWAY, outcome["limit"]
            )
        if outcome["bleFailed"] and not outcome["telemetryLive"]:
            # BLE-only away rule: nothing else can see the car, and BLE
            # couldn't reach it twice in a row.
            self._failedProbes[vin] = self._failedProbes.get(vin, 0) + 1
            if self._failedProbes[vin] >= self.AWAY_AFTER_FAILED_PROBES:
                return self._setState(vin, AWAY, outcome["limit"])
        return None

    def _applyHome(self, vin):
        self._failedProbes[vin] = 0
        return self._setState(vin, HOME, None)

    def _applyLocation(self, vin, atHome):
        return self._setState(vin, HOME if atHome else AWAY, None)

    def _setState(self, vin, new, limit):
        # Returns a (vin, old, new, limit) transition, or None if unchanged.
        old = self._state.get(vin, UNKNOWN)
        self._state[vin] = new
        if old == new:
            return None
        logger.info("Vehicle %s presence: %s -> %s", vin, old, new)
        return (vin, old, new, limit)

    # -- handlers; run without the lock ------------------------------------

    def _runHandler(self, vin, old, new, limit):
        if new == HOME:
            handler = self._onArrival
        elif new == AWAY and old == HOME:
            handler = self._onDeparture
        else:
            # unknown -> away: there is no evidence the car was ever home.
            handler = None
        if handler is None:
            return
        try:
            handler(vin, limit)
        except Exception:
            logger.error(
                "Presence handler for %s (%s -> %s) failed: %s",
                vin,
                old,
                new,
                traceback.format_exc(),
            )
```

In `lib/TWCManager/TWCMaster.py`, after line 18 (`from TWCManager.VehicleCommandQueue import VehicleCommandQueue`) add:

```python
from TWCManager.VehiclePresence import VehiclePresence
```

and after the `self.vehicleCommandQueue = VehicleCommandQueue(...)` statement in `__init__` (lines 106-108) add:

```python
        # Per-VIN presence tracking. Its thread is started by TWCManager.py
        # (only as a real master); until then observers record and nothing acts.
        self.vehiclePresence = VehiclePresence(self)
```

- [ ] **Step 4: Run the presence tests**

Run: `$VENV/bin/python -m pytest tests/unit/test_vehicle_presence.py tests/unit/test_twcmaster.py -q -p no:cacheprovider`
Expected: `92 passed` (`29` from `test_vehicle_presence.py`, `63` from `test_twcmaster.py`).

- [ ] **Step 5: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `582 passed, 1 warning`.

- [ ] **Step 6: Commit**

```bash
git add lib/TWCManager/VehiclePresence.py lib/TWCManager/TWCMaster.py tests/unit/test_vehicle_presence.py tests/unit/test_twcmaster.py
git commit -m "$(cat <<'EOF'
Add VehiclePresence: per-VIN home/away tracking on its own thread

Observers record from any thread; one daemon thread probes due VINs
through injected sources, applies the decision rules under a lock, and
runs the arrival/departure handlers without it. Sources and handlers
are wired in the next tasks.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

