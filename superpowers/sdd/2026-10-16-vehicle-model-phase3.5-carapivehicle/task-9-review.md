# Task 9 review

Verdict: approved with one fix (5e254a06). Items 1-7 match the brief.

## Checked, no change needed
- Reason logic: ownerReadOnlyReason has the same four conditions as the old ownerCommandsAllowed (which now calls it), so the two cannot drift. providerLines asks for a reason only when claim.commands is false; the claim stays the source of truth. fleetReadOnlyReason only explains a false usable("command"). No HTTP, and no lock beyond the claims/attachment locks already used.
- Retained MQTT: the claim is made only in the live branch of _observe, so retained messages never create, revive or claim. expire() skips cars with a keepsAlive claim, and the telemetry claim has keepsAlive=False, so the 30-day forget is unchanged. No provider walk uses claims for TeslaMate/Fleet Telemetry.
- Scan refresh: the meta refresh is emitted only while status.scanPending, and the PRG 302 is unchanged.
- Escaping: Jinja autoescape=True. The only raw markup is the template's own <br>; reasons and names are server strings.
- providerLines keeps the paired/unproven suppression only when capability matches status, which is what item 5 asked for.

## Fixed
- Deleted Vehicle.tier (ruling on item 1). ~30 test assertions mapped: X.tier == "managed" -> commands(X); == "observed" -> not commands(X), using tests/unit/vehicle_helpers.commands (any claim.commands). Files: test_registry_vehicle, test_registry_membership, test_homeassistant_registry, test_teslaapi_providers, test_teslaapi_readonly_gate, test_teslaapi_registry, test_teslable_pairing_status. test_identity_and_tier_default_observed -> test_identity_default_has_no_claims (asserts empty claims). test_anonymous_never_managed deleted (pinned tier-only semantics).
- Lib: 27420 -> 27414 net (-6).

## Remaining concerns
- Lib is +54 over ad029963 (27360); mostly the reason helpers and providerLines, which items 5/6 require. Could shrink further by dropping fleetReadOnlyReason's three-way split.
- TeslaMate claim is made once per Vehicle object; if a source stops reporting, the claim stays listed (age shown via last seen) until the car is forgotten.
- Rendering calls slot.usable("command"), whose reportScopeRefused side effect already existed via the claim.
