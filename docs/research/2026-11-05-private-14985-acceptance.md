# Linux 1.7.4985 rev1269 private acceptance record — 2026-11-05

## Scope and provenance

- Repository: `pengin0503/RimWorld-for-mod-test`, public source only
- Exact supported game target: Linux x86_64, RimWorld `1.7.4985 rev1269`, bundled WaylithClr
- Main integration: PR #51 (`90adfdec`), PR #52 (`7d6e8c2b`)
- Private one-time acceptance launcher: PR #57 (`7a051fb0`)
- [Private acceptance Actions run](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41949193678)
- [Merged-main public CI](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41949193761): all eight public synthetic jobs passed
- No third-party MOD bytes, raw logs, identifiers from the private index, private file paths, or R2 credentials are published in this report

## Evidence available at authoring

| Case | Narrow acceptance outcome | General qualification |
| --- | --- | --- |
| D v2, direct `game.tick` / mismatch / baseline-cache | **3 of 3 passed** (`ok=true`, GitHub Actions private job completed successfully) | **Not qualified**; experimental Worker-owned finite-tick observation only |
| Profile S real-MOD A regression | Pending private job outcome | No speedup claim |
| Profile M real-MOD A regression | Requires S success | No speedup claim |
| Real-MOD Btrfs COW vs forced copy | Requires eligible private Btrfs job and integrity checks | No speedup claim |

D v2 verifies the fixed 60-tick observation and the intentionally incorrect
expectation, as well as baseline cache reuse. Its Controller additionally
requires A and map to be completed, and rejects unexpected diagnostic or
incomplete reason codes. This establishes only the observed experimental
scenario, not general gameplay correctness.

The independent comparison with the official `-headless -quicktest` runtime
has **not been performed**. Apparel, job, blueprint and other arbitrary
gameplay MOD observations are outside the accepted three-case D smoke test.

## Acceptance gates still open

Issue #54 requires measured S then M validation including the exact selected
dependency closure and load order, five successful uncached / one cache-fill /
five cached samples, separated cold acquisition, measured baseline+target
peak RSS, and actual Btrfs results. Partial/failed cases must not be
aggregated into a synthetic performance improvement.

Issue #55 still requires independent official behavior comparison and
additional trusted scenario fixtures. C and D remain experimental, even
after the narrow private three-case D v2 acceptance succeeds.

RimWorld 1.7.4995 and Windows new features were excluded by user scope.
