# Residual branch safe integration implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task without agents.

**Goal:** Integrate public-safe original work while preserving exact provenance of remaining branch work that cannot legitimately enter main.

**Architecture:** Copy the self-authored optional DPA CSV exporter source and add its isolated formatting tests to public CI. Carry a residual branch disposition report into main, avoid resurrecting obsolete workflows or importing protected MOD binaries; keep main runtime code unchanged.

**Tech Stack:** GitHub pull request, .NET 10 synthetic test, existing Python 3.12/3.13 public CI.

**Spec:** docs/superpowers/specs/2026-11-05-residual-branch-safe-integration.md

## Global constraints
- Obey AGENTS.md; public repo must remain a test-only host.
- No private R2 downloads or game/MOD binaries in the public tree.
- Do not auto-enable private workflows.
- Main-only desired branch topology is a separate ref-cleanup action; do not delete unpreserved commits.

## Review focus
- Unexpected non-text/binary files in the import.
- User-supplied MOD-specific data published publicly.
- Stale workflows and secrets becoming active on main.
- DPA game-build claims exceeding isolated CSV test evidence.
- Changes to A/B adapter qualification and Worker.

## Tasks
- [x] Inspect all 12 branch heads, compare with main, classify unique changes and record protected content.
- [ ] Create source-independent CSV tests first and observe RED from missing source.
- [ ] Import only original addon source/metadata and tests; confirm isolated CSV tests GREEN.
- [ ] Update existing public CI to run format tests; preserve qualified host tests.
- [ ] Add branch-by-branch disposition report; explicitly note unmerged/discarded components.
- [ ] Verify full 8-job public CI and PR file diff contains no forbidden files.
- [ ] Merge PR after verification; verify current main and provide exact remaining branch cleanup steps.
