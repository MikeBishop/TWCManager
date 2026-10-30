b48dd13b Recheck a cloud hold with the online check alone
ee237bd4 Count current at the car's TWC as the car charging, for a start
48474e05 Count a wake as done when the car connects seconds later

1:  01bbedb4 ! 1:  48474e05 Count a wake as done when the car connects seconds later
    @@ CHANGELOG.md: This document logs the changes per release of TWCManager.
          * (@MikeBishop) - A plug-in with no VIN from a Gen2 or Gen3 TWC is matched to the one car that can be there (plugged in just now, BLE-read at that pilot and draw, or BLE-reached) and left unnamed when several could be; on a Gen2 that reads VINs, the VIN read replaces the match; the match never BLE-reads a car known asleep; a Gen2's match runs on the BLE worker, and a Gen3's vitals never read BLE. An unnamed TWC's rate now goes only to cars plugged in here, no longer to the first car; a status 00 alone no longer opens an unnamed session, and a Gen2 plug counts only while the TWC reports one. A car charging away from a TWC with no telemetry feed is not watched for its departure (a separate feature is planned); the 5, 20 and 45 minute reads after a TWC's power drops are gone
          * (@MikeBishop) - Removed the `/api/checkArrival` and `/api/checkDeparture` hint endpoints (they now return 404); presence no longer needs them
          * (@MikeBishop) - A guest car on the same TWC can keep a car that left idle counted as home until that car reports a position outside the radius or starts driving; a VIN a TWC rejected during a charge session stays rejected until the unplug
    -+    * (@MikeBishop) - A Fleet API wake_up that answers asleep, offline or waking is no longer a failed wake: the car connects seconds later, so TWCManager checks for it with the free online check every 5 seconds for up to 45 seconds, then sends the command at once. Only a car still not online after that waits 30 minutes for the next wake_up
    ++    * (@MikeBishop) - A Tesla API wake_up that answers asleep, offline or waking is no longer a failed wake: the car connects seconds later, so TWCManager checks for it with the free online check every 5 seconds for up to 45 seconds, then sends the command at once. Only a car still not online after that waits 30 minutes for the next wake_up
          * Fix: Add missing module-level time import in HASS, EmonCMS, Growatt, IotaWatt, SmartMe and TCP modules, which crashed EMS polling and caused charge current oscillation (closes #644)
          * Fix: Restore minInterval parameter on update_location, fixing TypeError that broke API start/stop charging and home location correction
          * Fix: Correct invalid logging level in update_vehicle_data error handler which crashed when logging a failed API response
    @@ docs/modules/Vehicle_TeslaAPI.md: Set the following in the `config` section of `
      | `teslaApiRegion` | No | Only used with `teslaApiClientSecret`: `NA` (default), `EU` or `CN` |
      | `teslaApiScope` | No | Override the requested OAuth scopes |
     -| `wakeDelayMins` | No | Minutes to wait before sending a Fleet API wake command (default: 3). During the delay the car may self-start from the TWC power offer. Set to 0 to wake immediately. |
    -+| `wakeDelayMins` | No | Minutes to wait before sending a Fleet API wake command (default: 3). During the delay the car may self-start from the TWC power offer. Set to 0 to wake immediately. After a wake that answers asleep or offline, the free online check looks every 5 s for up to 45 s; a car still not online then waits 30 minutes for the next wake. |
    ++| `wakeDelayMins` | No | Minutes to wait before sending a Fleet API wake command (default: 3). During the delay the car may self-start from the TWC power offer. Set to 0 to wake immediately. After a wake that answers asleep, offline or waking, the free online check looks every 5 s for up to 45 s; a car still not online then waits 30 minutes for the next wake. |
      
      If you do set `teslaApiClientSecret`, keep `config.json` readable only by the
      `twcmanager` user.
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
          # Seconds between failed wake_up attempts on one car (a wake is $0.02)
          WAKE_RETRY_SECONDS = 30 * 60
     +    # After a wake_up that answered asleep/offline/waking, the free online
    -+    # check every WAKE_POLL_SECONDS, WAKE_POLLS times, before it has failed
    ++    # check every WAKE_POLL_SECONDS, at most WAKE_POLLS times and for at most
    ++    # their product in seconds (a slow GET retries), before it has failed
     +    WAKE_POLL_SECONDS = 5
     +    WAKE_POLLS = 9
          regionURL = {
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     +        if state in ("asleep", "waking", "offline"):
     +            # wake_up answers the state at that moment; the car connects
     +            # seconds later. Blocking ~45 s is fine: this is the cloud worker
    ++            deadline = time.monotonic() + self.WAKE_POLLS * self.WAKE_POLL_SECONDS
     +            for _ in range(self.WAKE_POLLS):
    ++                if time.monotonic() >= deadline:
    ++                    break
     +                time.sleep(self.WAKE_POLL_SECONDS)
     +                if self.onlineState(vehicle, slot=checkSlot, maxAge=0):
     +                    state = "online"
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
              if state == "online":
                  self.resetCarApiLastErrorTime()
                  self._wakeSettled(car)
    +-            # The wake's answer replaces the cached "asleep": the read that
    +-            # follows it goes out
    +-            car.online, car.onlineCheckedAt = True, now
    ++            # The wake's or a poll's answer replaces the cached "asleep": the
    ++            # read that follows it goes out
    ++            car.online, car.onlineCheckedAt = True, max(now, car.onlineCheckedAt)
    +             # A command sent at once after a wake can fail with
    +             # could_not_wake_buses; let the car settle
    +             time.sleep(5)
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
              )
              return False
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
              now = self.now() if now is None else now
              obs, age = vehicle.telemetryState()
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +         ):
                  return obs.value in ("online", "charging", "updating", "driving")
      
    -         # Don't check more often than every 2 minutes
    +-        # Don't check more often than every 2 minutes
     -        if now - car.onlineCheckedAt < 120 and car.onlineCheckedAt >= car.staleBefore:
    -+        if (
    -+            now - car.onlineCheckedAt < maxAge
    -+            and car.onlineCheckedAt >= car.staleBefore
    -+        ):
    ++        # Not more often than maxAge (120 s by default)
    ++        age = now - car.onlineCheckedAt
    ++        if age < maxAge and car.onlineCheckedAt >= car.staleBefore:
                  return car.online
              result, response = self.get_car_api(
                  vehicle, vehicle.vin, checkReady=False, slot=slot
    @@ tests/unit/test_teslaapi_wake.py: def test_stale_telemetry_asleep_falls_through_
     +    car = _car(api)
     +    assert car.delayNextWakeAttempt == 0 and car.firstWakeAttemptTime == 0
     +    assert car.online is True
    ++    # Cached from the poll that found it online, before the 5 s settle
    ++    assert car.onlineCheckedAt == clock.now - 5
     +    assert _no_vehicle_data(requests_mock)
     +
     +
    @@ tests/unit/test_teslaapi_wake.py: def test_stale_telemetry_asleep_falls_through_
     +    assert fleet.wake(VIN) == HELD
     +    assert _wakes(requests_mock) == 1
     +    assert _no_vehicle_data(requests_mock)
    ++
    ++
    ++def test_slow_polls_stop_at_the_deadline(
    ++    api, fleet, clock, car_state, requests_mock, monkeypatch
    ++):
    ++    # Each poll takes 20 s (a slow or retried GET): the polls stop once
    ++    # about 45 s have passed, not after a fixed count
    ++    import TWCManager.Vehicle.TeslaAPI as teslaapi
    ++
    ++    monkeypatch.setattr(teslaapi.time, "monotonic", clock)
    ++    assert fleet.wake(VIN) == HELD
    ++    clock.advance(api.wakeDelayMins * 60)
    ++    gets = _gets(requests_mock)
    ++    _poll_sleeps(monkeypatch, clock, car_state)
    ++    requests_mock.get(
    ++        STATE_URL,
    ++        json=lambda req, ctx: (
    ++            clock.advance(15),
    ++            {"response": {"state": "asleep", "vin": VIN}},
    ++        )[1],
    ++    )
    ++    assert fleet.wake(VIN) == O.Outcome(O.UNREACHABLE, "offline")
    ++    polls = _gets(requests_mock) - gets - 1
    ++    assert polls == 3  # at +20, +40 and +60 s; none after the 45 s deadline
    ++    assert _wakes(requests_mock) == 1
2:  d770b716 ! 2:  ee237bd4 Count current at the car's TWC as the car charging, for a start
    @@ CHANGELOG.md
     @@ CHANGELOG.md: This document logs the changes per release of TWCManager.
          * (@MikeBishop) - Removed the `/api/checkArrival` and `/api/checkDeparture` hint endpoints (they now return 404); presence no longer needs them
          * (@MikeBishop) - A guest car on the same TWC can keep a car that left idle counted as home until that car reports a position outside the radius or starts driving; a VIN a TWC rejected during a charge session stays rejected until the unplug
    -     * (@MikeBishop) - A Fleet API wake_up that answers asleep, offline or waking is no longer a failed wake: the car connects seconds later, so TWCManager checks for it with the free online check every 5 seconds for up to 45 seconds, then sends the command at once. Only a car still not online after that waits 30 minutes for the next wake_up
    -+    * (@MikeBishop) - A car whose TWC (Gen2 or Gen3) measures at least 1 A since the car's last report is charging, whatever that report said: no start command and no billed start retry goes to it. Without a live feed the car's report can be stale, and a car that started by itself when its limit rose was sent a start, refused, and retried
    +     * (@MikeBishop) - A Tesla API wake_up that answers asleep, offline or waking is no longer a failed wake: the car connects seconds later, so TWCManager checks for it with the free online check every 5 seconds for up to 45 seconds, then sends the command at once. Only a car still not online after that waits 30 minutes for the next wake_up
    ++    * (@MikeBishop) - A car whose TWC (Gen2 or Gen3) measures at least 1 A, in the last 30 seconds and since the car's last report, is charging, whatever that report said: no start command and no billed start retry goes to it. Without a live feed the car's report can be stale, and a car that started by itself when its limit rose was sent a start, refused, and retried
          * Fix: Add missing module-level time import in HASS, EmonCMS, Growatt, IotaWatt, SmartMe and TCP modules, which crashed EMS polling and caused charge current oscillation (closes #644)
          * Fix: Restore minInterval parameter on update_location, fixing TypeError that broke API start/stop charging and home location correction
          * Fix: Correct invalid logging level in update_vehicle_data error handler which crashed when logging a failed API response
    @@ docs/Settings.md: This setting specifies that any vehicle which requests to star
      ### Vehicle Command Policy
      
     -Vehicle commands (start and stop charging, set the charge rate, set the charge limit, wake) go to the first ready provider in a fixed order: the TWC itself, then BLE, then the cloud, with billed providers (the Owner API, which Tesla does not bill but which is paced like a billed provider, for a car Tesla lists with `command_signing: off`; then the Fleet API, then Home Assistant) last. Free providers are always tried first. A billed provider is used only when no free one can serve the car, or after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps), and sends each desired value at most four times. The Vehicle Command Policy suppresses providers in that order:
    -+Vehicle commands (start and stop charging, set the charge rate, set the charge limit, wake) go to the first ready provider in a fixed order: the TWC itself, then BLE, then the cloud, with billed providers (the Owner API, which Tesla does not bill but which is paced like a billed provider, for a car Tesla lists with `command_signing: off`; then the Fleet API, then Home Assistant) last. Free providers are always tried first. A billed provider is used only when no free one can serve the car, or after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps), and sends each desired value at most four times. A start is done once the TWC the car is plugged into measures at least 1 A since the car last reported, so no start or retry goes to a car already charging. The Vehicle Command Policy suppresses providers in that order:
    ++Vehicle commands (start and stop charging, set the charge rate, set the charge limit, wake) go to the first ready provider in a fixed order: the TWC itself, then BLE, then the cloud, with billed providers (the Owner API, which Tesla does not bill but which is paced like a billed provider, for a car Tesla lists with `command_signing: off`; then the Fleet API, then Home Assistant) last. Free providers are always tried first. A billed provider is used only when no free one can serve the car, or after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps), and sends each desired value at most four times. A start is done while the TWC the car is plugged into measures at least 1 A, in the last 30 seconds and since the car last reported, so no start or retry goes to a car already charging. The Vehicle Command Policy suppresses providers in that order:
      
         * `prefer_ble` - Prefer local (BLE), fall back to cloud after a delay. Nothing is suppressed. This is the default.
         * `ble_only` - Local only - never send billed cloud commands. Every non-local provider (the Fleet API and Home Assistant) is suppressed for commands; cloud reads still run.
    @@ lib/TWCManager/Control/HTTPControl.py: def pendingCommands(master, vehicle):
                  and not newerReading(vehicle, aspect, rec.settledAt)
     
      ## lib/TWCManager/Vehicle/Reconcile/Belief.py ##
    +@@
    + # layer reads known() from here without the reconciler thread.
    + from typing import Optional
    + 
    ++from ..Registry.Fields import FEED_LAG
    + from ..Presence import NOT_HOME, pluggedNow, presence
    + from .Desired import AMPS, CHARGE_LIMIT, CHARGING, FIELD_FOR
    + from .Rules import releases, VEHICLE_SOURCES_EXCLUDED
     @@ lib/TWCManager/Vehicle/Reconcile/Belief.py: def uncompleted(vehicle, obs):
          return obs._replace(value="Stopped") if raised else obs
      
    @@ lib/TWCManager/Vehicle/Reconcile/Belief.py: def uncompleted(vehicle, obs):
              # current stands in. It never adopts
     -        return _standIn(vehicle)
     +        return twc
    -+    if desired is True and twc and twc.value == "Charging" and twc.at > obs.at:
    -+        # For a start, current at the car's TWC since its last reading is
    -+        # the car charging: without a live feed that reading may be stale
    ++    # For a start, current at the car's TWC now (a heartbeat within
    ++    # FEED_LAG) and since its last reading is the car charging: without a
    ++    # live feed that reading may be stale
    ++    fresh = twc and twc.at > max(obs.at, vehicle._clock() - FEED_LAG)
    ++    if desired is True and fresh and twc.value == "Charging":
     +        return twc
          return obs
      
    @@ tests/unit/test_command_path_parity.py: def test_telemetry_rearm_on_a_start_is_o
          )  # within the cap of 4
      
      
    -+@pytest.mark.parametrize("drawing", [True, False])
    -+def test_fleet_only_start_no_retry_while_the_twc_draws(requests_mock, drawing):
    -+    # Fleet-only, no feed: the car's last chargingState is a stale read. The
    -+    # start is not accepted (the car started itself when its limit rose),
    -+    # and the car's TWC then measures 48 A: that is the car charging, so no
    -+    # retry goes out. Without current the retry goes as before
    ++def staleStopped(requests_mock, **car):
    ++    # Fleet-only, no feed: the car's last chargingState is a 10-minute-old
    ++    # "Stopped"
     +    m, r, v, c, api = install(fleet=True)
    -+    FleetCar(requests_mock, state="online", script=[(200, False, "")])
    ++    FleetCar(requests_mock, state="online", **car)
     +    for field, value in (
     +        ("chargingState", "Stopped"),
     +        ("chargeLimit", 80),
     +        ("batteryLevel", 40),
     +    ):
     +        v.observe(field, value, "FleetAPI", at=c() - 600)
    ++    return m, r, v, c
    ++
    ++
    ++@pytest.mark.parametrize("drawing", ["live", "stale", None])
    ++def test_fleet_only_start_no_retry_while_the_twc_draws(requests_mock, drawing):
    ++    # The start is not accepted (the car started itself when its limit
    ++    # rose), and the car's TWC then measures 48 A: that is the car charging,
    ++    # so no retry goes out. A TWC reading that stops coming goes stale and
    ++    # the retry goes, as it does with no current at all
    ++    m, r, v, c = staleStopped(requests_mock, script=[(200, False, "")])
    ++    seen = []
     +
     +    def each():
     +        m.startCarsCharging(VIN)
    -+        if drawing and commands(requests_mock):
    -+            v.observe("actualCurrent", 48, "Gen2TWC", seen=False)
    ++        if drawing and commands(requests_mock) and not (drawing == "stale" and seen):
    ++            seen.append(v.observe("actualCurrent", 48, "Gen2TWC", seen=False))
     +
     +    m.startCarsCharging(VIN)
     +    passes(r, c, 3600, step=5, each=each)
     +    starts = commands(requests_mock).count("charge_start")
    -+    assert starts == (1 if drawing else 2) and paid(requests_mock) == (1, 0, starts)
    -+    # A stop still sees the car's own reading
    -+    from TWCManager.Vehicle.Reconcile import Belief
    ++    want = 1 if drawing == "live" else 2
    ++    assert starts == want and paid(requests_mock) == (1, 0, starts)
    ++
    ++
    ++@pytest.mark.parametrize("drawing", [True, False])
    ++def test_fleet_only_stop_is_the_same_while_the_twc_draws(requests_mock, drawing):
    ++    # A stop plans on the car's own reading: current at its TWC changes nothing
    ++    m, r, v, c = staleStopped(requests_mock, charging="Charging")
    ++
    ++    def each():
    ++        m.stopCarsCharging(VIN)
    ++        if drawing:
    ++            v.observe("actualCurrent", 48, "Gen2TWC", seen=False)
     +
    -+    assert Belief.known(v, CHARGING).value == "Stopped"
    -+    want = "Charging" if drawing else "Stopped"
    -+    assert Belief.known(v, CHARGING, True).value == want
    ++    passes(r, c, 600, step=5, each=each)
    ++    # The stale "Stopped" settles it either way
    ++    assert commands(requests_mock) == [] and paid(requests_mock) == (0, 0, 0)
     +
     +
      # Row 21 (slim Task 12b M3): chargeRateControl 2, a rate Fleet cannot deliver
3:  3027a953 ! 3:  b48dd13b Recheck a cloud hold with the online check alone
    @@ lib/TWCManager/Vehicle/Reconcile/Reconciler.py: class VehicleReconciler(threadin
     -        if not (wakes or recheck) and last == O.ASLEEP and asleep:
     -            # Asleep (or offline): only a sign of life since the hold, a
     -            # message that may wake, or the cloud's next check
    -+        if not wakes and last == O.ASLEEP and asleep:
    ++        # A billed provider never wakes for amps
    ++        holder = self.master.providerOrder.provider(rec.lastProvider)
    ++        mayWake = wakes and (aspect != AMPS or getattr(holder, "local", False))
    ++        if not mayWake and last == O.ASLEEP and asleep:
     +            # Asleep (or offline): only a sign of life since the hold (the
     +            # cloud's next check may find one), or a message that may wake
                  return None
    @@ lib/TWCManager/Vehicle/Reconcile/Reconciler.py: class VehicleReconciler(threadin
      
          def _held(self, vehicle):
     
    + ## lib/TWCManager/Vehicle/Reconcile/Run.py ##
    +@@ lib/TWCManager/Vehicle/Reconcile/Run.py: _badReturns = set()
    + _badLock = threading.Lock()
    + 
    + 
    +-# BLE work that is no command (a scan, an attribution): one pending per
    +-# (key, kind), in turn on the BLE worker
    ++# Work that is no command (a scan, an attribution, an online check): one
    ++# pending per (key, kind), in turn on its worker
    + Job = collections.namedtuple("Job", "key kind run")
    + 
    + 
    +
      ## tests/unit/reconcile_helpers.py ##
     @@ tests/unit/reconcile_helpers.py: def make_order(settings=None, *providers):
      
    @@ tests/unit/test_sleeping_car.py: def test_a_newer_offline_is_not_a_sign_of_life(
     +    passes(r, c, 900, step=60, each=idle)
     +    assert commands(requests_mock) == ["set_charge_limit"]
     +    assert car.charge["charge_limit_soc"] == 90
    ++
    ++
    ++def test_a_fleet_rate_held_asleep_waits_for_life_not_heartbeats(requests_mock, caplog):
    ++    # Under mode 2 the Fleet API carries the rate, and a billed provider never
    ++    # wakes for amps: the rate holds on an asleep car. The TWC's heartbeat
    ++    # is no sign of life, so the hold is logged once; the free check that
    ++    # finds the car online sends the rate
    ++    from tests.unit.test_amps_reconciler import point
    ++
    ++    caplog.set_level(logging.INFO)
    ++    m, r, v, c, api = install(fleet=True)
    ++    car = FleetCar(requests_mock, state="asleep", charging="Charging")
    ++    pt, s = point(m, v, 2)
    ++    v.observe("chargingState", "Charging", "FleetAPI", at=c() - 600)
    ++
    ++    def each():
    ++        pt.setTargetPower(10 * 240)
    ++        v.observe("actualCurrent", 0, "Gen2TWC", seen=False)
    ++
    ++    passes(r, c, 2 * 3600, step=10, each=each)
    ++    assert len(helds(caplog)) == 1 and paid(requests_mock) == (0, 0, 0)
    ++    assert onlineChecks(requests_mock) <= 2 * 3600 // 900 + 2
    ++    car.state = "online"
    ++    passes(r, c, 900, step=10, each=each)
    ++    assert commands(requests_mock) == ["set_charging_amps"]
