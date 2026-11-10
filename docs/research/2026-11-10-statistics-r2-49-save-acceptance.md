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
