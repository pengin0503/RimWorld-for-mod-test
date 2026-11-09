# Rimworld-Statistics — private real-game A-level smoke (2026-11-09)

## Purpose

Validate the compiled, precisely pinned [Rimworld-Statistics](https://github.com/pengin0503/Rimworld-Statistics) mod against the actual Linux RimWorld 1.7.4985 rev1269 WaylithClr runtime and installed Harmony from the private R2 game/MOD library, using the existing RWMT **qualified A-level** validation host. Compare with a baseline without Statistics.

The source is checked out by fixed commit SHA and compiled with `UseNuGetRefs=true`. The Worker and Statistics are built before the private R2 preparation step. R2 credentials are scoped to the preparation step and absent when running third-party MOD code. No user saves, private game binaries, private MOD payloads, or raw game logs are published by this workflow.

## Initial verified run

- [Actions run 42555484465](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/42555484465)
- Statistics code pinned in that run: `fbf3ce6b05303405996b65b04429dfb0230e63ef`
- Result: `status=passed`, `fidelity=qualified`, `stages.A.status=completed`, `reasons=[]`, `newErrorCount=0`.
- Real game, full Core+Royalty+Ideology+Biotech+Odyssey content, Harmony from R2. Only Statistics was the target (excluded from the baseline).
- The verified result applies to the A-level MOD load/initialization and diagnostic-diff scope of the pinned RWMT 1.7.4985 game host. It does **not** prove Statistics' title-screen UI or save import.
- A subsequent pinned Statistics main commit `9e411dde8abc7e5f5f6ef6d1510835fb17788360` contains two additional **test-only** wealth history regression cases. The workflow source pin is updated to this commit for subsequent runs.

## Running later

Open **Actions → Private Rimworld-Statistics A-level game loader smoke → Run workflow** on `main`. Do not run a forked or unreviewed workflow with private R2 credentials. This workflow is a manual/explicit regression gate and deliberately does not run expensive R2 tests on every PR.

## What is still NOT tested

- Loading either full `Test1.7.rws` (1.7.5000) or the 1.7.4995 legacy save into RimWorld: both saves were created by newer game builds than the 1.7.4985 pinned RWMT host, and the original bytes are not in this repo.
- Full original-byte `SaveReader.ReadDetailed` / `ImportEngine.Run` under .NET 10; only anonymized synthetic inputs and the **authentic original raw-DEFLATE Wealth_Total recorder bytes** are exercised in the separate Statistics repo's CI.
- Saved checkpoints, reload, stats profile content, UI, optional SDK event providers, performance/TPS, and save-write overhead.
- B-level Harmony target checks (A does not guarantee each registered patch or execution-time behavior); C/D are separately experimental.

Any further CI claims must include the exact SHA, real game build, and validated stage. A passed status is scoped to the A-level criteria only.
