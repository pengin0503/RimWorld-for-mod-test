# P4 workload regression: implementation and acceptance boundary (2026-11-05)

Scope: Linux x86_64 / RimWorld 1.7.4985 rev1269 / bundled WaylithClr. Based on
[the approved P4 plan](../superpowers/plans/2026-10-29-real-mod-regression.md).
Private games, index, third-party files, raw diagnostics and paths stay outside git.

## Added

- `tests/integration/run_workload_regression.py` provides fixed `prepare`, `run`, `publish` phases with no arbitrary repository, object key, command, script or R2 prefix input.
- `tools/codex_workflow.py` accepts **optional keyword-only** `max_selected_bytes`, `max_selected_files`, `max_mods` and `root_targets`. Existing calls without these arguments retain their existing behavior. For P4, aggregate caps are 256 MiB, 5,000 selected files and 20 selected MODs. Counts include cached selected objects. All metadata and dependency/LoadFolders selection happens before the cap is checked; *no payload GET starts before it passes*.
- S targets Vanilla Psycasts Expanded and mandatory dependencies. M targets both VPE and TD Enhancement Pack plus the mandatory dependency closure. Names are resolved from the private index and verified against About; no IDs are assumed from labels.
- Same snapshot and MOD request run 5 uncached validations, 1 cache-fill and 5 cached validations; uncached and cached trials are interleaved after the fill. Cached trials must actually show `baselineCached=true`.
- Only complete, qualified-scope A `passed` results with full MOD-order agreement, finite durations and valid peak RSS yield medians. Failure/incomplete/missing/duplicate cases and missing cache evidence yield `complete=false` and no timing medians. Timings are warm-OS-cache measurements, not a cold acquisition benchmark.
- Dedicated main-only manual workflow `linux-private-workload.yml` offers only S and M. R2 secrets are scoped to the preparation step; Worker runs without those credentials. The publish phase re-evaluates the private raw rows and emits a fixed-field summary without copying raw game or MOD data into GitHub artifacts.

## Synthetic verification

`tests/test_workload_regression.py` exercises fixed-profile selection, limits (including cached objects), duplicate root rejection, timing gates and safe summary reconstruction.
`tests/test_workload_runner.py` exercises CLI choices, result extraction and Worker credential isolation using a synthetic Controller.
The existing public CI on the PR tests Linux/Windows and builds the Worker with no game files.

## Remaining acceptance / scope limits

- The S and M real-game runs have **not yet been executed** on the merged main branch. They require private R2 and the pinned compatible game snapshot, and must not be reported as benchmark results before that.
- An opt-in real-selected-MOD Btrfs comparison has now been implemented: after `prepare` on a Btrfs private root, invoke `python tests/integration/run_workload_regression.py cow --profile S --private-root /private/path`. The benchmark uses five alternating `cp -a --reflink=never` / `--reflink=always` trials and SHA-256 content-tree checks, including a final source re-check. It creates/removes only its own temporary scratch directory, never MOD inputs. No such real-MOD measurement has been executed or claimed yet.
- On a non-Btrfs filesystem the command reports `status=unsupportedFilesystem`, `complete=false` and null medians. Do not interpret unsupported as zero benefit. The previously measured 39.8% relates only to a synthetic file-copy benchmark and cannot be added to the ~42% warm-cache result.
- Memory hard limits require an explicitly delegated writeable cgroup v2 tree (separate P5); soft RSS monitoring is unchanged.
- C/D independent qualification remains incomplete. No Windows new feature, non-headless gameplay or expanded arbitrary-MOD validation is implied.
- A new RimWorld build requires a separate snapshot and independent qualification; the P4 runner does not silently enable it.

The PR stays Draft until real-game acceptance and review. Do not merge automatically.

The GitHub Actions workflow's `runner.temp` interpolation is scoped to step-level `env`, not job-level `env` (the latter caused an invalid-workflow run with no jobs). Only step context has a `runner` binding. Both no-cache and cache-fill samples must prove `baselineCached=false` to avoid recording a contaminated baseline as an uncached performance measurement.
