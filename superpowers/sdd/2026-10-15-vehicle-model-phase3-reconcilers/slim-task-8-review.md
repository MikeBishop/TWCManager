# Slim Task 8 review (ccbe58c..cf63e52)

Spec compliance: PASS.
Task quality: APPROVED (no Critical, no Important findings).

## Verified
- Tests: the 7 targeted files pass (206). Full suite: 1551 passed, 1 xfailed. Checkout untouched.
- Parity test is real: test_provider_tables.py:70 `legacySuppressed` is an independent verbatim copy of the ccbe58c rule. Mutations in probe-slim8 each failed it:
  CLOUD_SUPPRESSED localStops emptied (34 fail); TeslaBLE api_only emptied (15 fail); Gen2 SUPPRESSED given a ble_only entry (15 fail, parity cases).
- After a wake 403 (TeslaAPI.py:2098-2108) `refuse("wake")` retires the slot. wakeOutcome (2181) checks usable("wake") before the backoff and the free check, so no request goes out. Legacy wakeVehicle (2471) has the same guard. No other wake_up POST exists in lib; BLE wake is unaffected.
- Commands survive: 403 on wake leaves refusedPurposes={"wake"}; usable("command") stays true; setAmps DONE (test).
- New token lifts it: setTokens/clear/restore reset refusedPurposes (TeslaTokenSlot.py:66,90,119,286); test line 169.
- No-table provider fails closed: Provider.py suppressedFor treats non-dict SUPPRESSED as locality, and only `local is True` gets {}. A Mock with no `local` is cloud.
- attempts() present: Provider.py:85, HomeAssistantProvider.py:53.
- No token in logs: no new log lines; the scope message names only the scope.
- "wake refused" survives Run.py `_tagged(woke, "wake ")` unchanged (startswith "wake"), so it stays NOT_SENT.

## Concern judgements
1. noteOutcome skipping free.failure for NOT_SENT: CORRECT. A failure of the free channel needs a request to it. The guard is no broader than needed ("rules:" early returns made no BLE request). Caveat for Task 9: if a rules hook returns UNREACHABLE persistently for the free provider, the Fleet fallback timer never starts. Rules apply to every provider, so this is probably right; confirm when the reconciler exists.
2. Command 403 not retiring wakes: ACCEPTABLE. slotFor("command") returns None after a command 403, and both wake paths use it.
3. Lib delta +40 net: ACCEPTABLE. Explained (wake scope, carry-forwards, suppressedFor). The plan's -90 included the BLE probe that Task 6 already removed.

## Findings
### Critical / Important
None.

### Minor
- TeslaAPI.py:2467-2499 (legacy wakeVehicle): a 403 on the legacy wake is swallowed and never calls reportScopeRefused("wake"), so only the new path retires wakes. Legacy is deleted in Task 13 and the guard honours the refusal, so low value. Fix if kept: on 403 call slot.reportScopeRefused("wake", refused=True).
- TeslaAPI.py:2181: after a wake refusal even an already-online car returns "wake refused", so a command with attempt.wake=True is aborted although no paid wake is needed. This follows the brief literally (check before the free online check). Fix option: move the usable("wake") check after the free is_awake check. Decide in Task 9 if this matters.
- Run.py:125 `_tagged`: pre-existing; "backoff" becomes "wake backoff" and "no command token" becomes "wake no command token", which miss NOT_SENT / change classification. Not introduced here; fix in Task 9 by tagging only after the isNotSent check.
