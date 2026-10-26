# Effective load folders implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent limited downloads from omitting the files selected by the qualified game's real loader.
**Architecture:** A pure, fail-closed load-plan module interprets listing paths, LoadFolders and versioned dependencies. Orchestration fetches metadata for every selected MOD before any payload, evaluates conditions using the complete requested MOD/DLC set, records the plan, and preserves its directory topology. Existing Controller/Worker own validation semantics.
**Tech Stack:** Python 3.12 stdlib, existing AWS CLI wrapper, qualified Linux game snapshot.
**Spec:** User-supplied prompt-for-codex-limited-fetch-fix-2026-10-26.md (six numbered requirements); public summary recorded here, original attachment remains outside Git.

## Global constraints

- Work on PR #9 branch, no merge; R2 read only, exact indexed MOD IDs.
- Reuse the game snapshot. Keep DLLs, decompiled text, index and raw logs outside Git.
- Derive folder/version/condition semantics from ModContentPack.InitLoadFolders, ModLoadFolders, LoadFolder.ShouldLoad and ModMetaDataInternal.InitVersionedData in 1.7.4985.
- Unknown/malformed selection or missing dependencies must block before payload/request generation. No implicit all-scope fallback.
- A only; no B/C/D, map or Windows support.

## Review focus

- Root-only data must not accidentally include sibling version folders.
- An inactive conditional folder must not change fallback selection.
- Unknown conditions and unsafe paths must block rather than disappear.
- Versioned dependency sections replace the generic list, including an empty section.
- Materialize selected folder directories even when filtering removes every file, so the real loader chooses the same topology.

## Task 1: Game-backed pure load plan

Files: create tools/mod_load_plan.py, tests/test_mod_load_plan.py; write research summary.
- [x] Verify private game methods and record only a paraphrased rules summary.
- [x] Write failing synthetic tests for fallback, custom folders, version-section precedence, conditions, unsafe/malformed/empty plans and dependency replacement/missing dependencies.
- [x] Implement load_folders(paths, xml, active) -> ordered relative paths and select_asset(relative, folders, language) -> bool; missing_dependencies(metadata, active) -> list. Use LoadPlanError.code for blocked reasons.
- [x] Run focused tests then full suite, commit the tested module.

## Task 2: Metadata-first orchestration

Files: tools/codex_workflow.py, tests/test_codex_workflow.py.
- [x] Add failing tests for dependency blocking before payload, malformed LoadFolders blocking, and custom-folder payload selection.
- [x] Fetch About and LoadFolders for all MODs first; check indexed identity/dependencies; compute plans and fetch payload only afterwards. Record effective folders/counts. Add explicit official-DLC request selection needed by conditional folders and dependencies.
- [x] Run focused and full suite, build Worker; commit.

## Task 3: Real parity evidence and review

Files: docs/research/2026-10-26-limited-fetch-parity.md and user-facing acquisition docs.
- [x] Resolve Harmony/VEF/VPE via cached private index and verify About dependencies.
- [x] Fetch scoped inputs, reuse snapshot, run A/Core/Royalty/English; repeat with explicitly requested all scope.
- [x] Compare status, actual mod order, Def counts and new diagnostic counts; investigate any difference.
- [x] Fresh review, address important findings with RED/GREEN tests, full suite, then push PR #9 without merging.

## Execution ledger

All three tasks executed in the existing isolated cloud checkout, on the user-specified PR branch. No extra worktree or merge. RED/GREEN tests preceded planner, orchestration, texture/sound and cache/dependency guards. Ruling: include images and audio only inside effective folders because private real-game runs demonstrated their necessity for A; comparison cache reused to avoid redundant GETs. Reviewer found duplicate/text-only dependencies; regression tests failed first and the guards were corrected. Ruling: conservatively reject noncanonical version directories and NUL-containing XML rather than infer loader behavior. Costs: some otherwise usable inputs require supported metadata normalization before limited acquisition; they never silently pass. Real parity and acquisition evidence are in docs/research/2026-10-26-limited-fetch-parity.md.
