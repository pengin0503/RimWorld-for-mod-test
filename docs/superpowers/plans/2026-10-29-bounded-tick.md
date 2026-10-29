# Bounded tick v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Observe a finite number of real Linux game ticks without providing play.
**Architecture:** Controller validates the fixed D request and independently judges game-tick and fixture evidence. Worker initializes the temporary game and drives real TickManager single ticks, with existing process supervision. A separate synthetic runner tests bounded execution; private Linux regression exercises the real build.
**Tech Stack:** Python unittest, .NET 10 C#, WaylithClr reflection adapter, private GitHub Actions.
**Spec:** docs/superpowers/specs/2026-10-29-bounded-tick-design.md

## Global Constraints
- Linux x86_64 / RimWorld 1.7.4985 rev1269 / bundled WaylithClr only.
- Count 1..60000; initial acceptance 60/600; at most 64 points and 64 expectations.
- No playable UI, indefinite execution, persistent save or Windows features.
- R2 read-only; reuse inputs; publish only whitelisted non-private summaries.
- D remains experimental / overall incomplete; C qualification is independent.

## Review Focus
- A frame counter cannot prove a game tick; require real tick differences and fixture state (Tasks 1/2).
- Game-start callbacks and the first observation must precede ticks (Task 2).
- A lost/duplicated point or overrun must never look complete (Tasks 1/2).
- Exceptions and watchdog exits must preserve available evidence (Tasks 1/2).
- Cached A/C or partial D results must not supply a D baseline (Task 3).

### Task 1: Request and evidence contract
**Files:** tools/bounded_tick.py, tools/validation_host.py, tests/test_bounded_tick.py.
**Interfaces:** validate_tick(request, levels, tests, map_request, expectations) returns normalized tick or None; evaluate_tick(request, evidence) returns stage, incomplete reasons, failed reasons.
- [x] Write tests for valid request, invalid bounds/types/points/combinations, unknown ID, complete/mismatch/missing/forged/partial tick evidence. Run `python -m unittest tests.test_bounded_tick -v`; expect failures before implementation.
- [x] Implement normalization and evidence checks; wire Controller request and stages. Expected: tests pass, unknown ID incomplete, no host-counter-only completion.
- [x] Run contract and existing C/request tests and commit.

### Task 2: Finite Worker execution and real API binding
**Files:** worker/RimWorldValidation.Worker/BoundedTick.cs, WorkerRequest.cs, Host.cs, Program.cs, MapGeneration.cs; tests/worker/BoundedTick; tests/fixtures/validation-mods-src/TickProbe; fixture About metadata.
**Interfaces:** TickRequest carries Count/ObserveAt; BoundedTickRunner uses game tick and registered probe delegates, exposes immutable captured evidence. TickApi binds supported build game-start and tick APIs.
- [x] Inspect matching private DLL, record semantic call-order findings without source bodies.
- [x] Add synthetic executable tests for 0/60/600, initial offset, no extra tick, missing probe, throw, deadline, frozen/jumping tick counter. Run `dotnet run --project tests/worker/BoundedTick -c Release`; expect failure before implementation.
- [x] Implement runner, strict Worker input, build-specific initialization and callbacks; route only D through this path. Preserve partial evidence in atomic result and event evidence.
- [x] Build Worker and run synthetic runner; run old category test; commit.

### Task 3: Cache, supervision and private Linux regression
**Files:** tools/validation_host.py, tests/test_bounded_tick.py, tests/integration/run_bounded_tick.py, .github/workflows/linux-private-bounded-tick.yml, .github/workflows/offline-audit.yml.
**Interfaces:** Tick baseline identity includes version/config/observation spec; private runner emits only status/codes/counts and booleans.
- [ ] Test cache segregation, partial evidence rejection, old-request compatibility and unsupported platform/build before execution. Run targeted tests; expect missing behavior failures.
- [ ] Implement cache and baseline checks. Add private real regression: 60/600, wrong value, unknown ID, absent probe, throwing probe, limits, process cleanup and existing A/map/C regression on reused snapshot. Fixed fixture has no third-party dependency.
- [ ] Run Python suite, Worker build and synthetic tests, then CI and private real-game job. Record exact unverified cases instead of widening claims; commit.

### Task 4: Document and review final scope
**Files:** docs/contracts/mod-validation-v1.md, docs/validation-host.md, docs/design/bounded-tick-v1-draft.md, docs/research/2026-10-29-bounded-tick.md, README.md, AGENTS.md.
**Interfaces:** docs reflect tested behavior, experimental scope and independent qualification stop conditions.
- [ ] Document real call path, measured cases, limits and gaps; update D status only where proven.
- [ ] Review full diff, fix material findings with regression tests, verify final checks, create a non-draft PR. Do not merge without explicit instruction.
