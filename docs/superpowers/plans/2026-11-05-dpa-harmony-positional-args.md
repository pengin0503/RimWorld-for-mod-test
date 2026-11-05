# DPA exporter Harmony positional argument fix implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the DPA 1.7 export button Harmony patch bind reliably and add a genuine synthetic regression test.

**Architecture:** Compile original addon source with fake game/DPA entrypoints and the actual Harmony 3 NuGet package; assert patch applies to a fake DoWindowContents(Rect inRect), then that a click emits a CSV. Only alter the injected Rect argument of the real addon after the RED test.

**Tech Stack:** .NET 10, Lib.Harmony 3.0.0-rc.3, GitHub Actions Linux+Windows.

**Spec:** docs/superpowers/specs/2026-11-05-dpa-harmony-positional-args.md

## Global constraints
- No game DLLs, private R2 data, private Workshop payloads or source snapshots.
- Preserve the current qualification scope and old DPA CSV format regression tests.
- No branch deletions or ref cleanups.
- No automatic merge without user instruction.

## Review focus
- Compilation of fake-game classes with both addon source files.
- Actual Harmony 3 successful patch owner registration.
- Postfix parameter injection from original Rect with mismatched name.
- Generated CSV content (row count, cycles, sanitization and UTF-8 BOM).
- Accidental replacement of real tests with synthetic-only false claims.

## Tasks
- [ ] Add game-free synthetic fake DPA/Verse/RimWorld types and one execution harness that references actual addon source and Harmony package.
- [ ] Wire its runner into the two-platform public CI GUI-model jobs.
- [ ] Observe RED failure due to wrong postfix argument name (other setup errors must be fixed first).
- [ ] Replace only `rect` with positional `__0` in addon postfix. Rerun the same synthetic test and observe GREEN.
- [ ] Confirm all 8 public CI jobs, PR patch scope, and no binary/asset leakage; report limitations.
