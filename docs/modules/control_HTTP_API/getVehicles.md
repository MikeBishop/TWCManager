# getVehicles API Command

## Introduction

The getVehicles API command returns every vehicle TWCManager knows, with where
each is, how TWCManager keeps track of it, and which services can reach it. The
Vehicles page reads this command every few seconds to keep itself current. No
token or other secret is ever included.

## Format of request

The getVehicles API command is not accompanied by any payload. You should send
a blank payload when requesting this command.

An example of how to call this function via cURL is:

```
curl -X GET -d "" http://192.168.1.1:8080/api/getVehicles
```

## Format of response

```json
{
    "fingerprint": "64c1b93c45ba",
    "now": 1794195366.67,
    "budget": 0.1,
    "spend": {
        "fleet": false,
        "telemetry": false,
        "month": null
    },
    "vehicles": [
        {
            "key": "5YJ3E1EA1KF000001",
            "vin": "5YJ3E1EA1KF000001",
            "name": "",
            "anonymous": false,
            "point": null,
            "appearance": {},
            "presence": "presumed",
            "watch": {
                "watched": true,
                "why": "no status source",
                "via": null,
                "last": "",
                "lastAt": null,
                "nextAt": null
            },
            "providers": [],
            "lastSeenAt": 1794195366.66,
            "lastSeenSource": "created",
            "heldLimit": null,
            "spend": null
        }
    ],
    "history": {
        "5YJ3E1EA1KF000001": {
            "chargeSessions": 0,
            "totalkWh": 0
        }
    }
}
```

Times are in seconds since the epoch (Unix time).

* `fingerprint` changes when the page's layout would (for example, when a
  vehicle is added or forgotten). Clients can ignore it.
* `now` is the server's time when the response was made. Work out how long ago
  something happened from `now`, not from the client's clock.
* `budget` is what is left, in US dollars, of the vehicle watch's budget for
  paid reads (see `watch.monthlyBudgetUSD` in Settings.md).
* `spend` says whether this month's Fleet API spend (`fleet`, with a Fleet API
  token) and Fleet Telemetry cost (`telemetry`, with the Fleet Telemetry
  module) are shown; `month` holds this month's totals when either is, and is
  `null` otherwise.
* `vehicles` lists each vehicle:
    * `key` identifies the vehicle: its VIN, or for a car known only by the TWC
      it is on (`anonymous` true), a key naming that TWC. `point` is the TWC
      the car is on, if known.
    * `vin`, `name` and `appearance` are its VIN, its name and its looks
      (model, paint, wheels) for drawing it.
    * `presence` is `home`, `presumed` (probably home) or `notHome` (away).
    * `watch` says whether the vehicle watch keeps the car current, and if not,
      why; and when it last checked the car and will next.
    * `providers` lists the services that can reach the car (such as
      `OwnerAPI`, `FleetAPI` or `TeslaBLE`), each with its status, whether it
      can send the car commands and, when it cannot, why (if known).
    * `lastSeenAt` and `lastSeenSource` say when the car was last heard from
      and what heard it.
    * `heldLimit` is set while TWCManager holds the car at a charge limit:
      `held` is that limit and `outside` the car's own limit, which it gets
      back when the hold ends. It is `null` otherwise.
    * `spend` is the car's share of this month's Fleet API and Fleet Telemetry
      spend, when `spend` above says it is shown.
* `history` gives each vehicle's charge sessions and total kWh charged here.
