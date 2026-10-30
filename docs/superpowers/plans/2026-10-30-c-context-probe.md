# C0 context probe Implementation Plan

> Execute inline with superpowers:executing-plans. User requests continuous execution without subagents.

**Goal:** Measure real UI-row reachability and queue/FinalizeInit order before independent C qualification.
**Architecture:** Development-only Harmony observer and official boot, fixed C-context evidence classifier, explicit private-validation suite. Product C predicates are neither copied nor replaced.
**Tech Stack:** Python 3.12, .NET 10, Harmony 2.4.3, Linux.
**Spec:** ../specs/2026-10-30-c-context-probe-design.md

## Constraints

RimWorld 1.7.4985 rev1269 / WaylithClr / Linux only. R2 read-only, prepare once per job, no secrets during build/run. No game assets, private logs or raw exceptions published. Official process: 180 seconds, 2 GiB RSS polling, 8 MiB combined stdout/Player.log, descendant cleanup. C0=false and experimental remain unchanged.

## Review focus

Incomplete, duplicate, reordered or context-shifted traces must fail; renderer exceptions never become visible=false; compiler failures must not hide another independent case; logs outside stdout are budgeted even after fast process exit; no output from unknown strings.

### Task 1: trace classification and private research runner

- [x] RED tests/test_c_context.py for queue before/after FinalizeInit, malformed/duplicate/missing traces, real row requirements, diagnostics and interruption.
- [x] Implement tools/c_context_evidence.py and independent CContext fixture. Bind row method only after audit #7 confirms ThingDef, Int32, Map signature.
- [x] Implement experiments/official-comparison/probe_c_context.py using existing fixed fixture inputs, private staging and supervisor; run both independent cases even if one fails.
- [x] RED→GREEN: private Player.log is part of the 8 MiB bound, including post-exit check; Controller process state is adapted explicitly.
- [ ] GREEN related Python tests, synthetic Worker/scanner tests and full public CI. Self-review, merge.

### Task 2: common entry and real-game gates

- [x] Add explicit c-context suite to private validation, fixed evidence reconstruction, no C0 promotion.
- [x] Preserve existing all selection (five operational suites); research is explicit only, to avoid silently expanding normal validation scope.
- [ ] Execute main c-context. Verify process exit, context phase order, reachability and diagnostics; record exact case stop reasons.
- [ ] If a gate fails, do not proceed to qualification for that case. If it passes, continue the pre-existing independent comparison plan with three positives, mutations and missing-fixture checks.
