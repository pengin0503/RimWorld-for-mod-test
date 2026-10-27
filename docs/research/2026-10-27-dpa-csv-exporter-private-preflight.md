# DPA CSV Exporter — private R2 / test-host preflight (2026-10-27)

## Goal
Verify the existing Dubs Performance Analyzer dependency from the private R2 source using the existing **RimWorld-for-mod-test** Linux test-only host before testing the separate DPA CSV Exporter addon.

## Sources and invariants
- Private MOD index: `rimworld-17/rimworld-mod-index.zip`; use `codex_workflow.py` to resolve Dubs and Harmony. Never invent Workshop IDs.
- Game: `rimworld-17/Game-Linux/`; only fetch assets required by the validation level; use an existing qualified snapshot when available.
- MODs: `rimworld-17/Workshop/<resolved ID>/`, first metadata, then loader-selected inputs.
- Never publish private index, proprietary DLLs, Workshop payloads, paths, or raw logs.

## Actual current result
1. Cloudflare R2 API verified the bucket and the object metadata for `Assembly-CSharp.dll`, `UnityStubs.dll`, `Waylith.dll`, and the private index.
2. Workflow on this branch initially had an invalid job-level `runner.temp` expression; fixed.
3. The next GitHub Actions run reached the **Validate private connection prerequisites** step, then failed. The job environment showed empty `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `R2_ENDPOINT`. Therefore **no R2 GET, MOD resolution, game download, or validation was performed by this workflow**.
4. The previously produced DPA CSV Exporter source archive remains separate from this repository. This preflight does **not** yet compile or load that addon.

## GitHub Actions setup required
Configure `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` as repository **Actions secrets** with read-only access to `rimworld-17`; configure `R2_ENDPOINT` as an **Actions variable**, using the HTTPS S3 endpoint for the account. Do not put credential values in workflow files, PRs, or logs.

Then rerun the branch workflow. A success only establishes Dubs' A-level load behavior on the qualified Linux build, **not** Harmony registration of the exporter, CSV output, UI rendering, or Windows compatibility.

## Required subsequent checks for the exporter
1. Add the existing addon sources to a dedicated project/repository, build against private RimWorld 1.7 reference DLLs with .NET 10, and run CSV tests.
2. Validate A/B for the compiled exporter alongside indexed Harmony and Dubs, with explicit Harmony patch expectations where supported.
3. Test CSV serialization with a synthetic Analyzer log without graphical UI (CSV output + method metadata + Japanese).
4. Verify actual button rendering and click-to-export manually on Windows RimWorld 1.7; the current Linux test host cannot execute graphical UI interactions.

Status: **dependency preflight blocked by missing GitHub Actions configuration; addon validation not yet executed**.
