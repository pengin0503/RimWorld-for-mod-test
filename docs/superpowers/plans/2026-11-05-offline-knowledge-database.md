# Implementation plan: built-in offline RimWorld 1.7 knowledge

Goal: a version-pinned reference-data store and useful local static checks without R2. Preserve current qualified real-game validators.

## Step 1 — RED contract tests

Add tests/test_knowledge_preflight.py with synthetic valid/invalid MOD directories. Assert exact build pinning, provenance-positive query, unknown instead of missing, no game/network, version and dependency uncertainty, selected load folders, DTD/symlink rejection, strict manifest, deterministic JSON CLI. Run offline Actions and observe import failures before implementation.

## Step 2 — minimal safe knowledge pack and engine

Implement tools/knowledge_preflight.py and validation-data/1.7.4985-rev1269/{manifest,types,methods,defs,harmony}. Publish only independently documented symbols from official-headless comparison, tagged partial. Reuse existing qualified 1.7 load-folder policy. Run RED tests GREEN.

## Step 3 — batch requirements and static-first orchestration

Extend synthetic tests to check exact-build requirement lists, future explicit pack isolation, and tools/codex_workflow.py static-preflight with R2 mocked unavailable. Observe RED, implement check command, optional exact custom packs, offline codex entry, confirm GREEN.

## Step 4 — documentation and final security review

Write docs/knowledge-database.md and link README/AGENTS. Clearly separate static statuses from runtime passed/qualified; preserve private index policy for external runtime MOD selection. Check no private data in diff. Run all 8 public CI jobs, fix errors, make PR ready for review and merge only when authorized by repository owner.

## Future deferred work

Generate separately verified 1.7 stable/1.8 packs from authorized metadata, without committing game files or claiming coverage not measured. User says this is a future preference, not a current acceptance gate.
