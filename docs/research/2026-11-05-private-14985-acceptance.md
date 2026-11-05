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
| Profile S real-MOD A regression | **11/11 successful** (5 uncached / 1 cache-fill / 5 cached); aggregate complete | A scope only, does not qualify all MOD gameplay |
| Profile M real-MOD A regression | First private preparation blocked by non-exact index name; exact-label fix PR #58, main-only M retry underway | No performance claim until the corrected M run finishes |
| Real-MOD Btrfs COW vs forced copy | **S succeeded**: five forced copies and five reflinks, integrity-checked | S selected files only; not a general game-speed claim |

D v2 verifies the fixed 60-tick observation and the intentionally incorrect
expectation, as well as baseline cache reuse. Its Controller additionally
requires A and map to be completed, and rejects unexpected diagnostic or
incomplete reason codes. This establishes only the observed experimental
scenario, not general gameplay correctness.

The independent comparison with the official `-headless -quicktest` runtime
has **not been performed**. Apparel, job, blueprint and other arbitrary
gameplay MOD observations are outside the accepted three-case D smoke test.

## Real profile S aggregate (validated safe job output)

The main-only private S job completed successfully in
[Actions run 41949193678](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41949193678).
The Controller measured a complete 5+1+5 A-only suite with verified
load ordering, diagnostic success, and observed cache states:

| S metric | Measured value |
| --- | ---: |
| Median 5 uncached validations (warm OS cache) | 16.87912 seconds |
| Median 5 cached validations (warm OS cache) | 10.06731 seconds |
| Relative validation-time reduction | **40.356%** |
| Maximum paired baseline/target peak RSS observed | 1,466,953,728 bytes |
| Private index-resolved MODs selected | 3 |
| Selected loader files / selected bytes | 934 / 65,008,117 bytes |
| First MOD index/metadata/payload acquisition | 167.6654 seconds |
| First game runtime fetch | 326.204 seconds |
| First snapshot preparation | 1.231 seconds |
| First complete preparation | 495.1094 seconds |
| Real-MOD forced-copy median (5 samples) | 0.14039 seconds |
| Real-MOD Btrfs reflink median (5 samples) | 0.05188 seconds |
| Copy-stage time reduction only | **63.043%** |
| One-off staging onto disposable Btrfs | 0.14331 seconds |

The 40.356% pertains to repeated validations only, and the 63.043%
pertains to forced copy versus reflink of S's selected files. They cannot
be summed, extrapolated to ~270 MODs or interpreted as a reduction in
game tick time. The peak RSS is an observed maximum, not a measured
memory saving. One-off staging is separately excluded from the copy
medians; initial remote acquisition is separately excluded from warm
validation medians.

## M exact-label repair

The first main-only M job did **not run game validation**: preparation
returned a sanitized `workflowError`. Read-only inspection of the
authoritative 279-record private R2 index established that the exact
label is `TD Enhancement Pack - Continued`, not `TD Enhancement Pack`.
PR #58 corrected the fixed root with a synthetic exact-resolution test
and launched only the M recheck:
[Actions run 41951889404](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41951889404).

No Workshop ID, private index contents, personal data or raw log is
published in this document.

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
