# Private R2 49-save Rimworld-Statistics production reader acceptance — 2026-11-10

**Workflow:** `.github/workflows/private-statistics-r2-reader.yml`  
**Reader pin:** `pengin0503/Rimworld-Statistics@91c2203e1f0c2800759f9d717f14a27b336e55fc` (draft PR #102, unmerged).  
**Dataset:** private `rimworld-17/Saves/` object bodies, 49 `.rws` / `.rws.old` files, 824,593,049 bytes at 2026-11-10 census.  
**Security:** PR builds/tests never have R2 credentials. On main push/explicit dispatch only, a dedicated step temporarily reads originals using GitHub Actions secrets; .NET parsing has no credentials. Files live only in `$RUNNER_TEMP/statistics-private-saves`, are named synthetic aliases, are never uploaded as artifacts, and are erased by an unconditional cleanup step. Raw input names, hashes, IDs, path values and exception messages are not printed.

## Exact execution and evidence

1. Public PR `public-preflight`: checkout exact Statistics 40-char SHA; validate source pin; Python-syntax-check the R2 fetcher; compile `tools/RealSaveImport/RealSaveImport.csproj` and run current Core tests on public NuGet reference assemblies. **No R2 secrets.**
2. Main-only `private-r2-originals`: ensure pinned source, install pinned botocore, then R2 `list_objects_v2` with `prefix=Saves/`, full paginator and exactly 49 originals / 824,593,049 bytes. Stream each `get_object` to a 0600 ephemeral synthetic filename. Compare R2 ETag between list/get and the expected declared object size during download; fail closed. No PUT or DELETE requests.
3. Run the **production `SaveReader.ReadDetailed`** from exactly the pinned Stats source over all 49 real local copies, one at a time. The tool checks that each local byte SHA256, size and modification time are unchanged; records `Ok`, `Unidentifiable`, `Error`, checkpoint count, exact build counts and per-file timings/managed allocations; prints only aggregated counts and p50/p95.
4. Compare the parsed 12-build counts against the pinned 2026-11-10 anonymous census from `Rimworld-Statistics/docs/research/2026-11-10-r2-save-compatibility-census.md`. Reject missing/extra original files, modified bucket inventory, unknown build signatures, invented checkpoint data, failed preservation checks or a different build distribution.
5. Erase all private files on success/failure/cancellation. This job does not mutate the R2 bucket, GitHub saves, or the user's local saves.

## Status and limitations

**MERGED and EXECUTED.** [RWMT PR #71](https://github.com/pengin0503/RimWorld-for-mod-test/pull/71) was squash-merged to `main@d2a80116b0e8b1c43a8a1c4a9c8ac9da0e2f93cd`. Exact [run #42830780995](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/42830780995): `public-preflight` **success** and main-only `private-r2-originals` **success**. The production .NET SaveReader parsed/read the 49 original files with 0 errors, verified all 49 SHA/size/mtime unchanged and zero checkpoints, and matched all 12-build counts. Read-time **p50 36.808 ms, p95 125.850 ms**, managed allocations **median 808,696 bytes**. Ephemeral private originals were erased by the `Always` step. The safe log asserts Ok+Unidentifiable=49 but does not separately print these statuses; do not claim all 49 were fully identifiable. Real-file reader acceptance does not establish game-side semantic correctness, 55+ input scaling or TPS.

These originals cover **12 exact builds**: 1.5 (22), 1.6 (20), 1.7 (7). Six originals match the R2 `Game-Linux` 1.7.4985 build at game version only, but have 239–252 mods each. A parse-pass is **not** a proof of runtime player-faction or `ResearchProjectDef.IsFinished` correctness, Harmony detours, game TPS, save-time overhead or cross-MOD semantics. The 49 original R2 files contain no Statistics checkpoint and thus test historical fallback and legacy compatibility. They are not the five attached 1.7.5000 192-MOD samples (nor 55+ independent real originals).

**Refresh rule:** When the Stats PR head changes, update both workflow pins and rerun PR preflight. When R2 source inventory changes, first audit/record the new private dataset in the Statistics source's R2 evidence manifest; update the count/bytes/build matrix with evidence, not by silencing failures. Do not run unpinned private source code with R2 secrets.

**Related:** [Statistics implementation draft PR #102](https://github.com/pengin0503/Rimworld-Statistics/pull/102) and [source inventory research](https://github.com/pengin0503/Rimworld-Statistics/blob/feat/post-v1.4-coverage-and-full-leaderboards-20261110/docs/research/2026-11-10-r2-private-reference-inventory.md).

## 2026-11-10 follow-up: actual RimWorld 1.7 smoke and production reader v11

**New implementation pin (PR #102, not merged):** `pengin0503/Rimworld-Statistics@52cb84de435e65197157a98c212b78546949715f`, after in-repository CI [#42837643992](https://github.com/pengin0503/Rimworld-Statistics/actions/runs/42837643992). Reader version increases **v10 → v11**, keeping checkpoint format v1 and all 415 metric definitions unchanged. This addition records the new source pin **without overwriting the earlier v10 run provenance** above.

1. `private-statistics-r2-reader.yml` public preflight compiles/tests the pinned code; main-only secret-isolated job fetches the 49 R2 originals in an ephemeral directory and re-reads with the **actual v11 .NET reader**, checking that no file changed, errors are zero, exact build census remains unchanged, and any recovered research observations are **Partial**, never Verified. CSV only logs aggregate `research_observed,research_partial`, no identifiers.
2. `private-statistics-smoke.yml` public preflight compiles/tests the identical pinned code; main-only secret-isolated job fetches the 1.7.4985 game/Harmony from R2 and performs the existing real RimWorld A-level startup comparison and B-level Harmony registration checks.
3. **User policy:** 1.7.4985 and 1.7.5000 are provisionally assumed equivalent because the 1.7 branch remains unstable. This does not prove byte-for-byte sameness or the 192-mod runtime DefDatabase and cannot make inferred research finished counts Verified. The saved research/official-game IL/122 research Def evidence is in [Stats R2 research file](https://github.com/pengin0503/Rimworld-Statistics/blob/feat/post-v1.4-coverage-and-full-leaderboards-20261110/docs/research/2026-11-10-r2-game-source-1-7-research-recovery.md).
4. No 1.7.5000 save game was loaded by the A+B smoke. The 49 R2 reader tests are **offline .NET**; the A+B smoke covers actual game load but does **not** prove stat value parity in all recorded MODs, new data UI, save performance or TPS. Record the execution outcome before claiming v11 real-game validation succeeded.

**Do not retrospectively relabel** the old [v10 49-original run #42830780995](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/42830780995) as a v11 result. Append the v11 specific run ID and result separately.

## Actual completed v11 game and 49-original result (2026-11-10)

After merging [RWMT PR #72](https://github.com/pengin0503/RimWorld-for-mod-test/pull/72) to **`main@fdbe5d907ac380ad35c25b012a33504244549c6c`**, the two qualified jobs executed pinned `Statistics@52cb84de435e65197157a98c212b78546949715f`, **SaveReader v11**, against genuinely private R2 inputs:

| GitHub Actions run | Final result | Actual evidence in safe log |
| --- | --- | --- |
| [#42838545431 — 49 original .NET reader](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/42838545431) | Both jobs **success** | All 49 read, all 49 unchanged SHA/size/mtime, 0 errors, 0 embedded checkpoints, 12 exact game builds match, **7/7 1.7 originals produced Partial research**; p50 **53.132 ms**, p95 **142.153 ms**, median **809,400** managed bytes |
| [#42838545527 — actual RimWorld 1.7 A+B smoke](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/42838545527) | Both jobs **success** | Actual game source 1.7.4985/Harmony R2; A-stage status **passed**, fidelity **qualified**, `newErrorCount=0`, `stageA.checks=0`. B-stage status **passed**, fidelity **qualified**, two expected Statistics menu-prefix patches; `unexpectedPatches=9` additional non-contract patches not individually attributed |

This updates the prior 'not yet executed' wording in the preceding section. The **earlier v10 run #42830780995 remains separate, valid historical evidence**.

Do **not** conflate A+B successful real-game launch/registration with per-pawn, per-research or in-game item count verification. The game smoke started **1.7.4985**, while the user's eight newest private samples are **1.7.5000** from one modded campaign. At user direction, differences within unstable 1.7 are provisionally treated as semantically irrelevant, but neither actual loaded MOD cost patches nor the exact 1.7.5000 engine were measured. The 7 reconstructed 1.7 research values remain **Partial**, and the other 42 1.5/1.6 files are not interpreted under the 1.7 reference. No source originals/credentials were uploaded.

## Proposed reader v13 qualification — owned turret and Core stock lower bounds

**Branch/PR under public review** updates the existing workflows to exact Statistics source pin `fe85905a5840742a288490b7c40e981dfe0ac120` (draft [Statistics PR #102](https://github.com/pengin0503/Rimworld-Statistics/pull/102)). The immutable source includes SaveReader **v13** and anonymous `RealSaveImport` schema **2**. Main Stats v1.4.0 is still v10; no Statistics merge or release is intended.

The previously verified real-game A+B job remains separate from a 49-original **offline** .NET reader pass. This workflow extends the privacy-safe CSV to report the number of 1.7 originals yielding positive `Partial` research, turret, direct-home Silver and direct-home three-Core-medicine observations. The gate requires all observed reconstructed values to be `Partial`, and none to appear in more than the seven 1.7 originals; it does not publish per-file values or identities. Exact build census, SHA/size/mtime invariants and safe deletion remain mandatory. Actual positive counts cannot be asserted before this pinned workflow executes.

Real 1.7.4985 class/Def source and eight private 1.7.5000 originals were inspected separately, with evidence in [Stats source audit](https://github.com/pengin0503/Rimworld-Statistics/blob/feat/post-v1.4-coverage-and-full-leaderboards-20261110/docs/research/2026-11-10-r2-1-7-historical-home-stock-turret-evidence.md). The user-approved 1.7 sub-build equivalence is provisional and not a proof of modded runtime item ownership, all items in containers or in-game exact counts.

**Do not update prior v10/v11 results or treat them as proof of v13.** After this harness-only PR passes public preflight, a main-only run can examine private R2 originals; append its new run ID and observed metrics here separately. Re-run the actual game load smoke on v13 before claiming v13 in-game startup acceptance.

## Completed v13 qualification on actual R2 data and real RimWorld 1.7 (2026-11-10)

**RWMT PR #73 merged** to `main@52ffea80a9944f4cd87881ef2d8118d96bdc8617`. Both workflows pinned exact **Statistics@fe85905a5840742a288490b7c40e981dfe0ac120** (`SaveReader.Version=13`, candidate draft PR #102). The previous v10/v11 results above belong to older immutable pins and remain independent.

| Evidence | Completed outcome |
| --- | --- |
| [#42846305788](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/42846305788), public + private production .NET reader | Both jobs **success**; **49/49** read-only original R2 file copies SHA/length/mtime unchanged, **0 errors**, 12 exact-build anonymous census valid, 0 embedded checkpoints, all extracted 1.7 values **Partial**. Positive research observations **7/7 eligible**, owned home-map turret observations **0/7** (unknown, not proof of zero actual turrets), Silver **6/7**, three Core medicines **6/7**. p50 **67.846ms**, p95 **205.922ms**, median allocated **809,480 bytes**; no attribution of change vs previous v11 run without controlled same-host A/B. |
| [#42846305625](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/42846305625), public + actual R2 game private A+B | Both jobs **success**; A `status=passed`, `fidelity=qualified`, `newErrorCount=0`, `stageA.checks=0`; B `status=passed`, `fidelity=qualified`, 2 expected Statistics title-menu patches, 9 other un-attributed patches. Actual engine from R2 is **1.7.4985 rev1269** with Harmony. |

These gates demonstrate safe parsing of 49 real saves and real-game **startup/Harmony registration**, but **not loaded 192-MOD per-metric in-game equality, TPS, medical-bed state, working generator status, free/slave/pawn classification**, or complete inventory in nested holders. The user's newest eight 1.7.5000 originals form one different private campaign, independently structurally checked, not input to these R2 49 original runs. All unstable 1.7 sub-build differences are provisionally treated as compatible at user direction, not claimed identical. The Stats candidate remains **unmerged**; this PR only changes validation infrastructure.

Source evidence and outcome: [Stats v13 original-file acceptance](https://github.com/pengin0503/Rimworld-Statistics/blob/feat/post-v1.4-coverage-and-full-leaderboards-20261110/docs/testing/2026-11-10-r2-49-original-reader-v13-acceptance.md) and [Stats v13 actual-game acceptance](https://github.com/pengin0503/Rimworld-Statistics/blob/feat/post-v1.4-coverage-and-full-leaderboards-20261110/docs/testing/2026-11-10-rimworld-1-7-v13-actual-game-smoke.md).
