# Rimworld-Statistics current-code acceptance on the qualified RWMT Linux host

**Prepared 2026-11-10; no new private A/B game execution is claimed by
this document until the main-only gate actually runs.**

## Baseline and exact versions

- RWMT source: `pengin0503/RimWorld-for-mod-test` (qualified Linux
  1.7.4985 rev1269 WaylithClr Adapter, pinned game in private R2).
- Statistics source: `pengin0503/Rimworld-Statistics`, immutable commit
  `7f6d3df4b55a2d388c62cb5aa5d1e7541a3374a3`
  (merged PR #80, SaveReader.Version 9).
- Existing proven A+B smoke used Statistics
  `9e411dde8abc7e5f5f6ef6d1510835fb17788360` on 2026-11-09:
  [run 42557038400](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/42557038400).
  It verified MOD initialization and **two** explicit Harmony Prefix registrations,
  not the title button's visibility, UI rendering, saves, or game ticks.
- The five actual checkpoint saves used by the separate Core acceptance
  are **1.7.5000 rev1275**, which is newer than the 1.7.4985 pinned
  game host. Never report an unperformed load as compatible.

## Implementation

Updated `.github/workflows/private-statistics-smoke.yml`:

1. **Public, credential-free pull-request preflight** fetches Statistics by
   immutable SHA, checks the two named patch classes, builds its production
   MOD with NuGet refs, runs its Core tests with no private inputs, and
   compiles the RWMT Worker.
2. **Private qualified A+B actual-game job** is explicitly gated on the
   repository's `main` ref, excludes `pull_request` events, and depends
   on the public preflight. It prepares the private game from R2 only in
   a credential-scoped step, then removes credentials before validation.
   It compares A-level load with/without Statistics and checks registered
   `GenScene.GoToMainMenu` and `OptionListingUtility.DrawOptionListing`
   Prefixes via B-level evidence.
3. A reviewed merge of this *workflow file itself* to `main` triggers
   its private game job **once**. Subsequent unrelated commits do not.
   `workflow_dispatch` permits deliberate later reruns on `main`.

This branch is only a proposal; **do not merge without the user explicitly
requesting it**, per repository AGENTS.md. A PR cannot access R2; public
preflight green does not mean a new real-game test was run.

## Acceptance semantics

| Item | Expected evidence | Status before private main job |
| --- | --- | --- |
| Latest Statistics compile | .NET 10 + public references | PR CI pending |
| Core tests | Public synthetic suite, private originals skip | PR CI pending |
| Host Worker compile | .NET 10, no game bytes | PR CI pending |
| A-level actual RimWorld 1.7.4985 | qualified, no new diagnostics | **NOT RUN for current Statistics** |
| B-level Harmony registration | exact two named Prefixes | **NOT RUN for current Statistics** |
| Five original 1.7.5000 saves via Core .NET | 5 checkpoints, two proven parent edges | **Previously passed outside RWMT**, see Statistics PR #80 |
| Load 1.7.5000 saves into actual RimWorld | version-aligned game runtime required | **BLOCKED / NOT RUN** |
| Title-screen UI button and details | host is non-rendering test-only; only patch registration observable | **NOT SUPPORTED by current host** |
| Runtime statistics events or TPS | dedicated qualified game-side probe and timings required | **NOT TESTED** |

## Privacy and test discipline

- R2 credentials are never provided to the public preflight, a PR job,
  an unmerged workflow, or the third-party MOD execution step.
- Full .rws saves, game binaries, DLLs, private index, complete MOD lists,
  raw diagnostics and secrets are not committed or uploaded.
- Keep raw private game logs in private runner paths; print only
  narrow results after the actual game test.
- Do not treat registered Harmony hooks as evidence that their UI
  callback or game-state capture code executed.
- Remain on the qualified 1.7.4985 host; upgrade to 1.7.5000 requires
  separately supplied/qualified runtime and adapter evidence, not a
  silent version override.
- Formal Statistics release `v1.2.2` is unchanged. Issues #71 and #72
  remain open until their respective missing acceptance criteria run.
