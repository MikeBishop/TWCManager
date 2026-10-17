# Slim Task 13c re-review 1 (1028283..bcb4042)

Method: each fix reverted or mutated in wt-vm3, tests run, tree restored (git status clean).
Baseline: test_teslaapi_request_errors.py + test_teslatokenslot.py 75 passed.

- I1 ADDRESSED. get_car_api counts sends (sent<3), passes resend=sent<2 and retried=refreshed; a refresh is detected by the access token changing. Read: max 3 vehicle_data GETs, max 1 refresh. Revert TeslaAPI.py to 1028283: test_a_refresh_spends_one_of_a_reads_three_tries FAILS. Command (_paidPost): one _request, max 2 POSTs, as BASE (no loop). List: resend=False, 1 GET. Energy: no caller loop, max 2 per call, as BASE. No over-count elsewhere.
- I2 ADDRESSED. `target = self`: read-429 and command-429 cells FAIL. Module-wide updateCarApiLastErrorTime(): same two cells FAIL. backoff_of distinguishes car/module/both.
- M1 ADDRESSED. Mutation "also refresh the other slot": both owner-slot tests FAIL.
- M2 ADDRESSED (list timeout 10, REFRESH_TIMEOUT 10). Hold is now about 20 s; lock not restructured (as ruled).
- M3 ADDRESSED. `outcome.kind == REFUSED`; test_a_list_401_whose_refresh_never_left_backs_off FAILS when TeslaAPI.py reverted.
- M4 ADDRESSED for the request-errors file and the new test in wall_connector_vins.
- M5 ADDRESSED. Reverting TeslaTokenSlot.py: test_refresh_post_has_timeout and both test_refresh_never_logs_an_exceptions_text cases FAIL.
- Token logging: refresh() catch-alls now log type(e).__name__; other refresh log lines are static or str(Response) ("<Response [200]>"); _request logs method, path, status and exception type only. No token text at any level in these paths. The parse/store tests run caplog at level 1.
- _request 9 parameters: Minor. resend and retried are one concept (sends left for this call) and could collapse into one `tries` argument, saving a parameter and the `sent < 2` arithmetic in the caller. Black accounts for most of the line growth. Not blocking.

## Notes
- TeslaAPI.py:1783-1785: refresh detection by `slot.accessToken != token` would also count a concurrent refresh from another thread. This only spends a try early; harmless. Nit.
- A refresh on the read's last try returns False without a module-wide backoff (BASE fell through to it). Reported by the author, benign.

APPROVED
