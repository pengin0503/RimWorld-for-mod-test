# Prevent cross-build static scan false positives — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent local MOD scans from certifying rules for unqualified RimWorld builds.

**Architecture:** Keep positive-evidence query/check independent of loader behavior. Add a build-scoped fail-closed entry gate at `inspect_mod`, retaining pinned `mod_load_plan` as-is.

**Tech Stack:** Python 3.12/3.13, unittest, existing cross-platform GitHub Actions.

**Spec:** docs/superpowers/specs/2026-11-05-static-preflight-build-isolation.md

## Global Constraints
- Only `1.7.4985 rev1269` static MOD scan uses `mod_load_plan`.
- No ref cleanup, third-party MOD DLLs, private R2, new runtime qualifications.
- Never merge PR without user instruction (AGENTS.md).

## Review Focus
- Exact-build pack accepted for query/check but rejected for scan.
- Correct CLI blocked code 2 instead of returning a positive.
- No misleading `versionMismatch`/invalid XML for future loader semantics.
- Existing legacy 1.7.4985 scans still pass.
- No changes to qualified host runtime.

## Tasks
- [ ] Add a failing regression test for both future 1.7.4995 and 1.8 with real `inspect_mod` and CLI; confirm RED.
- [ ] Add minimal pre-read pinned-build gate in `inspect_mod`; verify GREEN.
- [ ] Update offline knowledge database usage/limits.
- [ ] Execute full Linux/Windows public CI, inspect PR diff and report exact results.
