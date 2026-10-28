# Private preparation measurement

Goal: obtain the first real R2 preparation breakdown from PR #25 and verify the resulting snapshot with A only.

Use the existing Python orchestration and Linux Actions runner. Select Harmony through the private index, acquire its metadata before payload, and prepare one runtime with the existing language/debug filter. Reuse that snapshot for the reuse check and A validation. Cloudflare read-only API confirmed the excluded Anomaly prefix is empty before this run.

The alternative of repeating a full download for every timing sample is rejected: this run establishes one baseline, not a statistical speedup claim. Transport optimization follows evidence from this measurement.

- [x] Test the public summary whitelist and A-only scope guard with synthetic inputs.
- [x] Implement a prepare/run/publish helper and a branch-scoped private workflow. Give R2 credentials only to preparation; keep all assets and raw logs outside checkout and out of artifacts.
- [x] Run local checks and public CI. Run the private workflow once, inspect only the numeric/enum summary, and record the exact SHA, scope, counts, timing boundaries, and limitations in PR #25.

Results: [initial preparation measurement](../../research/2026-10-28-initial-preparation-measurement.md). Acquisition took 706.566 of 707.831 seconds; the same snapshot was reused, and A completed with passed / completed / qualified.

No merge, Windows feature, C/D validation, R2 write, or unrelated MOD change.
