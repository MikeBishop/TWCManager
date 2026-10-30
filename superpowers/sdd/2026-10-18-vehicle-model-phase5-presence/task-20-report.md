# Task 20 report
Changed: FleetTelemetryMQTT.events maps FastChargerPresent, FastChargerType, ChargingCableType, ACChargingPower, ChargeCurrentRequestMax; doc fields regrouped and extended, fallback paragraph rewritten, connectivity note added beside `retained`.
Confirmed against teslamotors/fleet-telemetry protos/vehicle_data.proto (main): FastChargerPresent bool; FastChargerType enum FastCharger, values prefixed "FastCharger" (Supercharger, ACSingleWireCAN, MCSingleWireCAN, Combo, Unknown, SNA...), strip 11; ChargingCableType enum CableType, prefix "CableType" (IEC, SAE, GB_AC, GB_DC, SNA, Unknown), strip 9; ACChargingPower double; ChargeCurrentRequestMax numeric. DetailedChargeState prefix 19 already right.
Judgement: FastChargerUnknown/SNA map to "" (a home-type value, so not away-charger evidence). Cable Unknown/SNA kept as-is: Presence only treats "<invalid>"/"" as no cable.
Tests: test_a_telemetry_only_car_at_a_fast_charger_is_not_plug_evidence (test_presence.py) failed before (plugIn mark set), passes after. tests/unit + tests/EMS: 2190 passed.
Lib: 26356 -> 26368 (+12; brief estimated ~6, due to the fast-charger helper).
Concerns: none material; the float/bool payload shapes are from the proto (Datum), not a live capture.
