# Linux validation execution plan

User authorized the previously proposed sequence and lighter validation on 2026-10-28.
Work is inline, on an isolated checkout of PR #22 (e2a5044); no merge is authorized.

1. Review PR #22, reuse its positive R2 regression evidence, extend private checks to mismatched expectations and unavailable observations. Keep C experimental.
2. Add Linux copy-on-write MOD staging with verified destination content and portable streaming fallback. Never hardlink MODs. Test independence, stale hashes, partial clone failure and native fallback before implementation.
3. In one ephemeral CI job, prepare the approved runtime once, resolve VPE and dependencies from the private index/About.xml, fetch only selected payloads, compare loader order and folders, and measure uncached versus cached runs.
4. Run material-C regression matrix against that same snapshot; do not claim independent qualification.
5. Specify finite-tick request bounds and observation semantics as a draft; no D runtime implementation.
6. Run public tests/builds, one branch review, publish a reviewable PR; report actual results and blocked work.

Review focus: fallback safety, MOD write isolation, credential removal before execution, no private artifacts, distinction between experimental observations and qualification.

## Decisions and evidence

- Standard Git transport unavailable: source files reconstructed through GitHub API at the exact PR22 SHA; remote updates use a tree based on that SHA.
- Existing PR22 comment records successful real-map Steel +10 observation; the earlier summary missed that comment.
- New copy tests failed before implementation (missing clone helper and missing mode return), then all 3 passed.
- Local filesystem does not support reflink: 128 MiB copies fell back successfully. No local speedup claimed.
- One independent branch reviewer found three important defects in the initial regression harness/metrics; all corrected. Loader-order and worker-failure guards have RED→GREEN tests; the original link-count regression is green again.
- Initial private preparation failed with missingDependencies. Investigation found optional loadAfter/loadBefore entries were being recursively selected as required MODs. Required dependency closure now precedes optional ordering; selected-MOD cycles still block. Synthetic regression reproduced the missing optional-MOD failure and is green after the fix.
- Preparation now resolves MOD inputs before downloading the runtime, and publishes only stage/type/reason code on failure. The missingDependencies failure now stops in seconds without a game download.
- Latest public suite includes 261 tests. The private real-game matrix is kept distinct from public checks and from independent C qualification.
- The earlier local full-suite run had environment/process-monitor failures (documented in PR23) plus the corrected link-count failure; the Linux/Windows CI matrix passes those tests. No claim that this sandbox's local full suite passed.
