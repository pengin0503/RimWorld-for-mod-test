# Private static C audit implementation plan

> Execute with superpowers:executing-plans. The user has approved execution and prohibited subagents.

**Goal:** Safely inspect fixed C reference entrypoints in the qualified Linux game binaries without loading or executing them.

**Architecture:** A main-only workflow builds an independent metadata scanner, prepares verified private inputs, runs the scanner under bounded supervision, then reconstructs an allowlisted public summary. Static evidence never qualifies C0.

**Tech Stack:** Python 3.12, .NET 10 PEReader and System.Reflection.Metadata, GitHub Actions, existing R2 SDK.

**Spec:** `docs/superpowers/specs/2026-10-29-private-static-c-audit-design.md`.

## Global constraints

- Only the eight fixed Linux inputs and existing adapter hashes; 64 MiB per file, 128 MiB total; no Windows feature changes.
- Private assets and raw results never enter the repository, public logs, artifacts or caches.
- Use verified existing snapshots where possible; bind each session to main workflow identity and commit.
- No game assembly loading or execution; `c0Passed` is always false.
- Scanner bounds: 120 seconds, 2 GiB aggregate RSS, 8 MiB logs; parser limits and fixed publication grammar are specified in the design.
- Real acceptance requires the integrated workflow on main; synthetic CI alone cannot qualify C.

## Review focus

- Existing snapshots with symlink ancestors or modified bytes must never become trusted inputs.
- Duplicate, missing, oversized or dishonest R2 metadata must fail before publication, with no GET before preflight.
- Stale, duplicate or interrupted runs cannot reuse a prior success.
- Unknown signature atoms, malformed IL, excessive overloads or output must remain incomplete without leaking names or paths.
- Timeout, cancellation, output overflow and process descendants must not leave a success or running child.

## Task 1: fixed acquisition and identity

**Files:** `tools/private_static_audit.py`, `tests/test_private_static_audit.py`.
**Consumes:** `private_validation.current_identity`, `codex_workflow.r2_session`, `validation_host.ADAPTERS`.
**Produces:** verified private run-specific manifest and exactly eight files; failure leaves verified false.

- [ ] Write tests for exact key preflight, duplicates, per-file/total limits, version/hash/actual-size mismatch, identity, symlinks, snapshot reuse and interrupted or duplicate runs.
- [ ] Run tests and observe expected failures.
- [ ] Implement bounded acquisition, safe reuse and atomic identity-bound manifest; verify actual sizes and hashes.
- [ ] Run `python -m unittest tests.test_private_static_audit -v` and expect all pass; commit.

## Task 2: non-executing metadata and IL scanner

**Files:** `experiments/c-reference-audit/`, `tests/worker/CReferenceAudit/`, `.github/workflows/offline-audit.yml`.
**Consumes:** verified input paths and expected SHA256 values from Task 1.
**Produces:** private bounded structured results bound to identity and hashes of the parsed byte arrays.

- [ ] Add synthetic assembly tests for overloads, generic/ref/array signatures, instruction boundaries and call offsets, invalid/truncated PE and IL, budgets and a static constructor side-effect marker.
- [ ] Confirm tests fail before implementation; build scanner with PEReader, no Assembly.Load or game references.
- [ ] Parse only fixed candidate types and methods; preserve direct calls, offsets, branches and exception regions privately; fail closed on malformed inputs and exceeded budgets.
- [ ] Run synthetic tests in public Linux CI using SDK 10; expect all pass; commit.

## Task 3: supervised execution and safe publication

**Files:** `tools/private_static_audit.py`, `tests/test_private_static_audit.py`.
**Consumes:** Task 1 manifest and Task 2 private scanner results.
**Produces:** allowlisted schemaVersion 1 summary with `c0Passed=false`.

- [ ] Add tests for malformed/hostile signatures and output, stale identity, changed binary, invalid enum, unknown types and nonfinite data; assert no private text leaks and status is incomplete.
- [ ] Add supervision tests for credential-free environment, timeout, cancellation, RSS/log limits and child cleanup.
- [ ] Implement bounded child execution and reconstruct fields from fixed IDs, type atoms and known edges only; recheck files, manifest, identity, output and limits.
- [ ] Run targeted tests and Linux CI process tests; expect all pass; commit.

## Task 4: main-only workflow and acceptance

**Files:** `.github/workflows/linux-private-c-audit.yml`, documentation.
**Consumes:** Tasks 1–3.
**Produces:** manually dispatched main-only private audit, with sanitized summary and no private artifacts.

- [ ] Test workflow ref/repository/checkout guard and credential scope; test failure handling and lack of artifact upload.
- [ ] Build scanner without credentials; prepare only in credentialed step; supervise and publish without secrets, with a 20-minute job bound.
- [ ] Run full public CI and review the complete branch; inspect open PRs and checks.
- [ ] Main-only real acceptance requires the integrated workflow: dispatch only after authorized integration and report actual hashes, bounded status and any incomplete evidence without leaking private data.
