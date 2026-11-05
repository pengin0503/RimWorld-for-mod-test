# Offline knowledge database design — RimWorld 1.7 unstable

## Purpose

Make static validation of a locally supplied MOD available immediately, without private R2, game files, the private Workshop index, or a Worker launch. The only bundled build is Linux RimWorld 1.7.4985 rev1269, which was actually compared against official headless in the existing qualified report.

This is an additive first stage. No runtime A/B/C/D feature is removed or relabeled as static verification.

## Architecture

- Versioned safe reference pack in validation-data/1.7.4985-rev1269. Exactly one manifest, and provenance-linked positive facts in types, methods (documented argument types only), fields, defs, Harmony targets, official package identifiers and known warning JSON.
- Offline Python engine in tools/knowledge_preflight.py: query a fact, check an explicit requirement batch, scan local About/selected Defs and Patches XML, validate an entire pack.
- Reuse the qualified exact-build load-folder algorithm from tools/mod_load_plan.py, including 1.7 fallback rules. No approximation to unrelated future builds.
- tools/codex_workflow.py static-preflight is an offline convenience entry point. Existing fetch-mods and validate remain private-index / R2 and real-game authoritative.
- Future 1.7 stable / later versions: separate exact-build packs. Explicit --pack-dir can load a separately verified pack of the exact requested version; no silent fallback or automatic qualification.

## Critical evidence semantics

Existing public repo contains verified examples of GenText.ToSpaceList and the Steel Def; it does NOT contain the full set of game API signatures or all Defs. An unlisted API or Def is UNKNOWN, not absent. All records are explicitly marked as partial coverage with a source pointer. Never claim the tiny seed pack is exhaustive.

The static status vocabulary is separate from the runtime contract:
- staticChecksPassed: all performed static checks passed, no runtime assertion.
- staticIssuesFound: a definite syntax/declared-version/duplicate-local-definition error.
- staticIncomplete: cannot resolve a dependency with an incomplete selected active set, or a requirement is not in the partial catalog.
- blocked: invalid or unavailable pack/input.

All results preserve gameVerification=notRun and runtimeQualified=false; no static result can satisfy qualified A/B/C/D.

## Security / privacy

No executable code in pack, no DLLs, no copied game XML, no Workshop index, no private raw logs, no personal paths in printed diagnostics, no network access. Reject symlinks, DTDs/entities, oversized XML, duplicate symbols, unsupported schema and stale/mismatched build. Scan is bounded to 20,000 input files and 40,000 visited paths; 128 MiB applies only to metadata and selected XML **actually read** (not uninspected texture/audio assets), and selected XML is capped at 32 MiB, with 4 MiB per XML and for LoadFolders.xml. Large binary assets are not opened by the static scanner.

The mandatory private index still governs identification of external MODs for runtime validation. A user-supplied local MOD directory is not selected from the private index, so offline first-stage scanning needs no R2.

## Acceptance

First introduce failing synthetic regression tests (RED), then implement minimal engine (GREEN). CI must pass on Python 3.12/3.13 and Linux/Windows. Verify that the high-level codex workflow offline command cannot call R2, and that current game-dependent workflows remain untouched. Report actual seeded symbol coverage and explicitly list unverified behavior.

## Alternatives

- Putting the official game or private MOD binaries in Git would violate project rules and massively expand repository size: rejected.
- Guessing a complete API catalog or declaring missing symbols incompatible would produce false conclusions: rejected.
- Extracting full metadata from a private game installation is a possible future separate, user-authorized process. Only verified, sanitized metadata can be published; no extraction is simulated or claimed here.
