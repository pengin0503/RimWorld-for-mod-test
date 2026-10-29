# Linux qualification experiments implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; one final review.

**Goal:** Complete reproducible COW measurement and independent D comparison with honest qualification limits.
**Architecture:** Separate development-only experiments; keep production behavior unchanged until evidence justifies scoped qualification.
**Tech Stack:** Python, Linux FICLONE/FIEMAP, Btrfs loopback, C#/Harmony, official headless quicktest.
**Spec:** ../specs/2026-10-29-linux-qualification-design.md

## Global constraints

Linux x86_64, RimWorld 1.7.4985 rev1269, bundled WaylithClr only. R2 read-only; one snapshot/job. No private assets/logs, Windows features, C qualification or automatic merge.

## Review focus

- Empty/missing official observations must never compare equal.
- Extra ticks and initialization/frame differences must be visible.
- Physical accounting must deduplicate extents and exclude unknown allocations.
- Cross-filesystem fallback must not be reported as reflink.
- Summary must not publish exception messages or private paths.

### Task 1: COW measurement
Files: tests/test_cow_measurement.py, experiments/cow-measurement/measure.py, dedicated private workflow.
Interface: run(root, repeats=5) returns whitelisted JSON with copy/reflink modes, time, unique data bytes, isolation, fallback.
- [ ] Tests first: union physical intervals, missing FIEMAP, native copy independence, stale hashes and summary.
- [ ] Run failing tests, implement, rerun.
- [ ] Run CI on newly mounted loopback Btrfs and record timings/data/isolation.

### Task 2: Independent D comparison
Files: development-only TickQualification fixture, experiments/official-comparison/compare_ticks.py, tests/test_tick_comparison.py and private workflow.
Interface: compare(product, official, count) rejects missing/duplicate/extra rows, setup/view mismatch, errors, bad increments and unexpected fixture values.
- [ ] Tests first for positive and negative comparison sensitivity.
- [ ] Implement official bounded probe, isolated process execution, finite supervisor and sanitized summary.
- [ ] Run real 60/600 and fault/sensitivity controls, repeated normal cases.

### Task 3: Evidence and integration
- [ ] Record actual evidence and remaining stopping conditions. Lift qualification only for demonstrated scoped conditions; otherwise keep experimental.
- [ ] Run relevant tests and public CI; one whole-branch review and fix material findings.
- [ ] Create reviewable non-draft PR; leave merge to explicit user instruction.
