# 1.4.0 vehicle model: roadmap

**Spec:** `.superpowers/specs/2026-10-13-vehicle-model-design.md` (approved 2026-10-13).
**Inputs:** `.superpowers/gut-inventory.md` (deferred items A1-A39, architecture B1-B5), `.superpowers/settings-history.md`.

The spec spans several subsystems. Each phase below gets its own plan, written when the phase before it has landed (its interfaces are then real, not guessed). Every phase is shippable on main and tested on the user's box through a deploy branch before it goes upstream. No phase may regress a pure-Gen2 install (Docker `:latest` tracks main).

| Phase | Delivers | Replaces / closes | Plan |
|---|---|---|---|
| 0. Foundations | Per-VIN queue keys, `cancel`/`queued` (cherry-pick `presence/1-command-queue`, fixes #667); a lock or single writer for `settings` | inventory A20; B5 settings race | folded into Phase 1 plan, Task 1-2 |
| 1. Registry and reads | `Vehicle` per car (VIN or anonymous plug-session identity); `VehicleRegistry`; field store with value/source/time; `read(field, maxAge, allowWake=False)` cascading over read-capable sources; tiers observed/managed; VIN confirmation by TWC re-query; forgetting; session history split out; existing modules (TeslaAPI, TeslaBLE, TeslaMate/Telemetry, HA, Gen2 TWC) feed and read the registry through adapters; read-only Vehicles list from the registry | A4, A6 (no wake on read), A7, A33, A34; B2 split ownership | `2026-10-13-vehicle-model-phase1-registry.md` |
| 2. Providers and charging points | Provider interface: capabilities with ranges, per-operation cost, locality, readiness, rate-limit declaration; fixed order by cost then locality; per-provider/per-capability suppressions (defaults per spec, `commandPolicy` mapped); Owner and Fleet as separate providers; charging endpoints and generic grouping into charging points (replaces `MergedEVSE`/`getDedupedEVSEs`/type knowledge in `TeslaAPIController`); `VehiclePriority` kept as a façade over the order | A1, A2, A8, A9, A10, A17, A18, A24, A26 | written after Phase 1 |
| 3. Desired state and reconcilers | Desired state per car/aspect; attempt records (one in flight); per-channel lanes (BLE, cloud) with classified outcomes; time-aware paid fallback; re-assert/adopt/hands-off; user changes adopted (slow aspects until next decision, fast aspects as session bounds); charge limit first (port `ChargeLimitRules` + own-write stamps from `presence/2`), then charging on/off, then amps (layered actuators); disruptive stops as very-high-cost capabilities; refused retires slot/claim | A5, A11, A12, A13, A14, A19, A21; `-1` sentinel; three `lastChargeLimitApplied`; per-channel dedupe flags; `VehiclePriority` removed | after Phase 2 |
| 4. Control tick | ~1 s control tick; distributor off the serial loop; all installs on one distributor (pure-Gen2 per-slave allocation rules ported with tests: fair share, flex, dampening, 6 A spike workaround, 60 s gates, re-stop ≥ 4 A, idle TWC minimum for plug detection); RS-485 loop protocol-only; token refresh off the loop with per-slot lock | A15 prerequisite, A22, A36, A37 | after Phase 3 |
| 5. Presence port | Plug-presence rules on the model (from `presence/3-plug-presence`, tests ported); departure = desired limit back to outside value | A3, A27 basis, A28, A29, A31 notes | after Phase 4 |
| 6. Vehicles tab | Per-car page: merged fields with source/age, provider panels, reconciler state; Forget | spec "Vehicles tab" | after Phase 5 (list view lands in Phase 1) |
| Separate | Two-pass distributor (own design, after Phase 4); multi-car VIN-less fingerprinting (own design) | A15, A27 | own specs |

Token-slot leftovers (A23), #691, #698 are closed by whichever phase touches their code; each phase plan lists the inventory rows it closes.
