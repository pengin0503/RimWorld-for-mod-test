# Residual branch triage and carried-forward work (2026-11-05)

This document records a **selective safe consolidation**, not a claim that all
historical branch commits or file trees can be merged. The repository is a
public, game-less validator subject to AGENTS.md. Some old branch trees contain
copyrighted third-party MOD binaries or source fragments and must not become
reachable through `main`. A merge commit with `-s ours` would also be unsafe:
the excluded files would remain reachable in public Git history.

Base for review: main `1500286a4ee1e9138e67ea616cb06ee6e5e9d81f` (PR #53).
Inspect each original branch HEAD below before any eventual cleanup. Branches
are not evidence of game-verified successful MOD behavior.

| Branch | Reviewed HEAD | Disposition |
|---|---|---|
| `build/immersive-filter-1-7` | `edced5ae3fb7f0d69b4f5a94cd4af650746e8661` | **Excluded**. Contains compiled ImmersiveFilter.dll, base64-encoded source/binary archives and native overlay; cannot publish these via main. The native GLSL/Def port is MOD-specific and was not independently qualified. |
| `ci/keepaimnshoot-build-20261104` | `07cf75ad5dde14203f0d463ffb6a3b2d4c017cde` | **Superseded one-shot workflow**. Tied to that branch and a private source archive; would not execute correctly on main. No runtime result inferred. |
| `ci/keepaimnshoot-review2-20261104` | `d21ce4e89c71d08020f12467c3e941d35ae72789` | **Superseded one-shot workflow**. Same branch-only model, private patch/object keys, and non-main trigger. No production change. |
| `ci/pr22-real-game-20261027` | `db2fd68f44fe8d6109679a2652320a2658633fe1` | **Superseded**. No branch-only paths compared to main; old controller/workflow versions must not overwrite qualified newer versions. |
| `claude/project-thread-poug58` | `941b851f9ecf1645ce97c2027bcd091fe7e45e1e` | **Superseded**. Old Windows preflight GUI was retired/frozen; no further Windows GUI development authorized. |
| `docs/headless-audit-and-design` | `620f196a72dc1109404f85cde59d3efa9a41def3` | **Superseded**. Old docs and notes are already represented or revised in main, with no branch-only paths. |
| `docs/private-14985-acceptance-20261105` | `9ca26e7ce3e09b78d570ec1da84d75a055616fb8` | **Superseded**. Private 1.7.4985 acceptance report is in main; omitted the explicitly temporary main-triggered one-shot workload workflow. |
| `feat/build-14995-readiness-20261105` | `71f034de9dbe23fff6871ed862d63f175a8beefc` | **Merged** by PR #53 (squash SHA `1500286a4ee1e9138e67ea616cb06ee6e5e9d81f`), all 8 post-merge public jobs passed. 1.7.4995 remains *not qualified*. |
| `feat/dpa-csv-exporter-private-validation-20261027` | `7da01d67847a006ece5b554884963b130efc65b0` | **Partially integrated**. Carry forward self-authored DPA CSV Exporter source, About metadata and isolated CSV-format tests. **Excluded** stale R2-specific workflows and its old private-preflight report (blocked due to then-missing secrets). Runtime UI and exporter DLL not verified. |
| `feat/melee-animation-net10-port-20261104` | `9bb3ed532e745e83a3643690ebd96395d575c472` | **Excluded**. Private-port transformation has extensive source-fragment matches from a third-party MOD; public test host is not an authorized distribution channel. |
| `feat/qol-three-mod-load-smoke-20261101` | `e206005b21ff4845c1053ff6659ee272c5a9257c` | **Superseded**. Old branch-specific three-MOD A-load workflow fixes stale commits; do not activate on main or mistake for runtime evidence. |
| `work/three-mod-verification-20261101` | `2892a00cde1513b4edc025f92d098035d16810d4` | **Superseded**. Another stale workflow for same three QoL MODs with old hashes and experimental bounded-tick checks. |

## Remaining work

**An exact all-branches content merge is not possible under existing public
repository rules** without introducing third-party MOD materials and overwriting
newer validated host implementations. The DPA original addon is kept isolated
and non-qualified. Any remaining third-party MOD work belongs in an explicitly
licensed separate MOD project/private workspace, not main history.

After this PR is merged and its CI verified, the original branch pointers may
be retired **only if** a private, fully verified recovery bundle contains all
twelve exact original HEADs, the main SHA is rechecked, and the operator chooses
to remove them. A local bundle was proposed in the separate
`rwmt_main_only_cleanup.py` tool; this repository has not verified that the
operator ran it. Do not claim branches deleted or protected material merged
until the live GitHub refs confirm it.

The final public branch topology can be main-only while some historical
contents remain only in the operator's private bundle. The distinction is
intentional and must not be hidden.
