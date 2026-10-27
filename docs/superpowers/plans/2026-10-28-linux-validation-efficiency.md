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
