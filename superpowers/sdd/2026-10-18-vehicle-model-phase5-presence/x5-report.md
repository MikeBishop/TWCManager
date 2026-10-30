# X5 report

Status: done. Commits 5a1e908c (Import vehicle-model modules by name), a2af43c5 (Trim comments that restate the code). Not pushed.

## Tier B (commit 1): lib -128 (211 ins, 339 del), target -110
Converted the exploded `Capability` and `Outcome` blocks to `from ..Providers import Capability as C` / `from . import Outcome as O`, and the Reconciler's `Belief as B` and `Rules as R`. A tokenize-based script rewrote call sites; names bound locally were checked for shadowing (none).
Files: TWCMaster, Vehicle/HomeAssistant, Vehicle/TeslaAPI, Vehicle/TeslaBLE, Providers/{Gen2TWC,Gen3TWC,HomeAssistant,TeslaAPI,TeslaBLE}Provider(s), Reconcile/{Desired,Reconciler,Run,Targets}.
Left alone: blocks importing classes or functions rather than vocabulary modules (Registry.VIN in HTTPControl and TeslaBLE, TeslaAPIProviders classes, WallConnectorVins), and the single-line Belief/Rules/Desired imports elsewhere (no line saved, alias would cost readability).
Tests: no edits. No test patches these names. Undefined-name AST check clean; `import TWCManager.TWCMaster` OK; black --check lib clean.

## Tier C (commit 2): lib -56 (71 ins, 127 del), target -95
Trimmed headers/docstrings: Reconciler, HeldLimits, VehicleCommandQueue, WallConnectorVins, Run, Outcome, Desired, Rules.decideChargeLimit and needsLiveRead, _blindTWCs, vehicleEndpoints, VehicleEndpoint and ChargingPoint headers.
Short of the estimate by about 39 because I kept every statement that explains why (Reconciler paid-send rules, HeldLimits legacy-ID migration, the unverified-on-hardware notes). Trimming further would drop whys.

## Totals
Lib 26,382 -> 26,198 (-184 vs BASE da198c2e; estimate -205). Tests 2093 passed, 1 warning after each commit.

## Concerns
decideChargeLimit's docstring no longer lists the restore and already-at-target rules; the branches below carry them. The Reconciler header's paid-send wording is compressed, so check it against the CHANGELOG contract.
