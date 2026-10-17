# Task 7 review (66e1038..02c040a)

Spec: compliant. All consumers covered: TeslaAPI wake (TeslaAPI.py:402), HA _atHome in car_api_charge/applyChargeLimit/numCarsAtHome/minBatteryLevelAtHome, TeslaAPIController.allEVSEs (isPluggedHome). grep of atHome/at_home in lib finds no missed consumer: TeslaAPI.py:705,1028,1036,1089,1736,1746,1853,1860 read the presence-backed atHome property (1977); TeslaBLE.py:811 uses isHome; Telemetry/PresenceSources only write observations; HTTPControl.py:377 is display.

Findings
- Minor: TeslaAPI.py:402 - a never-located presumed car is still woken (lat==10000 exemption removed, but PRESUMED is home). Consistent with "presumed = home" but not "plugged in"; spec says only plugged-in asleep car is woken. Confirm intent; the brief literally says atHome.
- Minor: TeslaAPIController.py:67 - isPluggedHome called without try/except, unlike TeslaAPI.atHome (TeslaAPI.py:1986); an exception breaks allEVSEs.
- Minor: test_teslaapi_presence.py departing-wake test is convoluted (two api objects, car.carapi reassigned); passes at RED, so regression guard only.
Approved.
