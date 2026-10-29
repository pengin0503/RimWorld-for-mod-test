# D: bounded tick v1 — accepted implementation scope

The user approved completion of the preceding finite-tick proposal on 2026-10-29.
Implement Linux x86_64 / RimWorld 1.7.4985 rev1269 / bundled WaylithClr only.
A completed load and a generated temporary map are prerequisites; C qualification and
COW performance measurement are independent. No Windows features or playable entry point.

Use `levels: ["A", "D"]`, `tests: ["bounded-tick.v1"]`, a map and
`tick: {count: 600, observeAt: [0,60,600]}`. Count is an integer 1..60000;
observeAt contains 1..64 sorted distinct integers 0..count and includes count.
Expectations are 1..64 `{tick,id,equals}` entries: registered fixture IDs and
integer equality only. Unknown IDs are observations unavailable, never a pass.
Initial acceptance uses 60/600 ticks. Reject combined B/C/D cases in v1.

Investigate real game-start and TickManager single-tick paths before binding APIs.
The old map path intentionally omits Game.FinalizeInit and start notifications.
Do not run ticks on that incomplete state or substitute successful stubs.
Record actual game start/end tick numbers, their difference, ordered observations
and independent fixture state. Observe tick 0 after initialization, before any tick.
Use separate baseline/target processes, with the observation probe present in both;
only target expectations are asserted. Do not tick once beyond count.

Controller independently validates evidence. Observed mismatch makes stage D failed;
missing/exception/limit/truncated evidence makes it incomplete. Unsupported environment
is blocked. D remains experimental and overall incomplete until independently qualified.
Preserve partial evidence, existing diagnostics and hard process termination backstops.
Include D case/version, tick settings and observations in baseline cache identity;
never reuse an A/B/C or partial D baseline. No changes to old requests' behavior.

Alternatives: COW-on-supported-FS measurement would improve performance evidence but
would not add time-dependent verification and is not a D prerequisite. D was selected
for extending coverage. Long-play, arbitrary MOD scenarios and rendering remain outside
this scope. R2 read-only, minimal fetch and existing snapshot reuse rules remain binding.
