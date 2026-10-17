# Split small fixes (local only, not pushed)
- fix/distributor-skips-evses: head ea0e4a8 (1 commit, test amended into cherry-pick of 0a1e237); 4 new tests in tests/unit/test_distributor_loop.py; suite 605 passed; all 4 fail on origin/main TWCMaster.py.
- fix/car-api-charge-vin: head 487f256 (1 commit, 3e03a13 reworded, zero-share test removed); 3 tests in tests/unit/test_teslaapi_charge_vin.py; suite 604 passed; 2 vin tests fail on origin/main (no-vin test passes by design).
Worktrees: scratchpad/wt-loopfix, scratchpad/wt-vinfix.
