# Default Policies

TWCManager ships with a set of four default policies which can be controlled by
the web interface:

- **Charge Now** charges at the maximum speed supported by the connector for 24
  hours when requested by the web interface
- **Scheduled Charging** charges at a specified rate during a timeframe
  specified on the web interface
- **Track Green Energy** attempts to route excess solar production to your car's
  battery during hours when solar production is likely
- **Non-Scheduled Charging** charges at a specified rate (typically zero) at all
  other times

The basic properties of these policies are set through the web interface.

## Charge Limits

Each of these policies has the ability to apply a different charge limit to your
vehicle when the policy comes into effect.  For instance, you might charge to
50% during scheduled charging to ensure the car always has plenty of range, but
charge up to 90% if excess solar production permits.

These limits are GPS-based.  They will be applied to cars at home when the
policy changes, and to cars which arrive while the policy is in effect.  The
car's original charge limit is remembered and restored when the car leaves or
when a new policy does not apply a limit.

Acceptable values are 50-100; -1 means not to apply a limit / restore the car's
original limit.

These limits are not exposed through the web interface, but can be configured in
the `config.json` file:

- `chargeNowLimit`
- `scheduledLimit`
- `greenEnergyLimit`
- `nonScheduledLimit`

# Defining Custom Policies

If you wish to add additional policies, they can be specified in the
`config.json` file as well.

## Anatomy of a Policy

Here is a sample policy:

    { "name": "Grid Offline",
      "match": [ "modules.TeslaPowerwall2.gridStatus" ],
      "condition": [ "eq" ],
      "value": [ "False" ],
      "charge_amps": 0,
      "charge_limit": -1
    }

The values in a policy definition are:

- `name`: The name of the policy, shown in the console output of TWCManager
- `match`:  An array of policy values to be tested
- `value`:  A corresponding array of values to be tested against
- `condition`:  An array of relationships between `match` and `value` elements for the
  policy to apply
- `charge_amps`:  The maximum current to permit while the policy is in effect
- `charge_limit`:  The charge limit to apply to vehicles while the policy is in
  effect (optional)
- `background_task`:  A background task to be run periodically while the policy
  is in effect (optional)
- `latch_period`:  If the conditions for this policy are ever matched, treat
  them as matched for this many minutes, even if they change. (optional)

### Policy Values

`match` and `value` can contain several different properties to check.

- Literal strings or numbers
- `true` and `false`: Boolean values; not case-sensitive
- `now`: The current time as seconds past the epoch; not case-sensitive
- `tm_hour`:  The current hour as an integer (0-23); not case-sensitive
- `config.*`: Retrieves a value from `config.json`
- `settings.*`:  Retrieves a value from `settings.json`
- `modules.*`:  Retrieves a value exposed by the specified module.  Some useful
  module properties are:
  - From `TeslaPowerwall2`:
    - `gridStatus`:  `True` if the grid is up and working properly; `False` if
      disconnected
    - `batteryLevel`:  Current charge state (0-100); note that this does not
      precisely match the value displayed in the Tesla app
    - `operatingMode`:  Current operating mode; one of `self_consumption`,
      `backup`, or `autonomous` (Advanced Time-of-Use)
    - `reservePercent`:  The percentage to reserve for backup events
    - `stormWatch`:  Whether Storm Watch is currently in effect
  - From `TeslaAPI`:
    - `numCarsAtHome`:  The number of (Tesla) vehicles currently believed to be
      at home
    - `minBatteryLevelAtHome`:  The lowest battery level (0-100) of any Tesla
      currently believed to be at home; `10000` if unknown / no cars are home.

(Note that TWCManager does not know which vehicle is connected to which TWC, so
only aggregate properties of all vehicles at home can be accessed.)

The comparisons which can be employed are:

- `gt`: Match must be greater than value
- `gte`: Match must be greater than or equal to value
- `lt`: Match must be less than value
- `lte`: Match must be less than or equal to value
- `eq`: Match must be equal to value
- `ne`: Match must not be equal to value
- `false`: Never true, regardless of values
- `none`: Always true, regardless of values

### Background Tasks

Most policies will not require a background task.  There are two exceptions:

- If defining a policy that behaves like **Track Green Energy**, the background
  task `checkGreenEnergy` will track generation and consumption metrics from the
  configured EMS plugins.  Set `charge_amps` to
  `getMaxAmpsToDivideGreenEnergy()` to retrieve the calculated value.
- If defining a policy that depends on `modules.TeslaAPI.minBatteryLevelAtHome`,
  the background task `checkBattery` will track the charge state of cars at home
  more closely while the policy is selected.

## Policy Extension Points

The simplest way to extend the default policies is to insert additional ones.
There are three extension points:

- `emergency` defines policies which apply before **Charge Now**, meaning they
  override explicit user commands.  Define policies here which should abort a
  manual charge command, such as not charging during a grid outage.
- `before` defines policies which apply between **Charge Now** and **Scheduled
  Charging**.  Define policies here which are exceptions to your normal schedule,
  such as charging at full speed when the battery is extremely low.
- `after` defines policies which apply between **Track Green Energy** and
  **Non-Scheduled Charging**.  Define policies here which augment your daily
  schedule.

## Policy Replacement

If you have unusual policy requirements, you can instead replace the built-in
policies.  Note that if you still need any of the default policies, you will
need to re-define them yourself.  For your convenience, the default policies are
present in `config.json` to use as a starting point.

**This is not recommended.**  The default policies will be improved over time,
while your copies of them will be left unchanged.