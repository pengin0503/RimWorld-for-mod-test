# Bounded D v2: trusted, allowlisted runtime observations (2026-11-05)

Scope: an **experimental** extension on the existing Linux x86_64
`1.7.4985 rev1269` WaylithClr Adapter. This does not independently qualify
D or alter the existing `bounded-tick.v1` request, result or cache identity.

## Purpose and trust model

The original D v1 only observes `fixture.counter` through a known,
version-checked self-authored `RWMT.TickProbe` GameComponent.
A separate optional parser for `RWMT-PROBE` warnings (PR #52) remains an
**untrusted private log diagnostic**.

D v2 adds an explicit `tick.observers` registry and a Worker-owned
`BoundedTickRunnerV2`. The Worker directly reads game state at each
controlled `TickManager.DoSingleTick` boundary. No untrusted warning text,
caller-provided member names, dynamic reflection or arbitrary method
invocation drives the new observation contract.

Initial registered IDs are deliberately narrow:

| ID | Source | Needs fixture MOD? |
| --- | --- | --- |
| `game.tick` | `TickApi.ReadTick(game)` / real `TicksGame` | No |
| `fixture.counter` | Existing verified `RWMT.TickProbe.TickProbeComponent.Counter` | Yes |

Unknown, repeated or unsorted IDs are rejected before running the Worker.
Each registered ID must appear in at least one typed Int64 expectation.
`tick.observers` is required **only for v2** and forbidden for v1.

## Private request example

```json
{
  "recordType": "modValidationRequest",
  "schemaVersion": 1,
  "levels": ["A", "D"],
  "mods": [{"path": "/private/target-mod", "packageId": "example.target", "target": true}],
  "map": {"seed": "rwmt"},
  "tests": ["bounded-tick.v2"],
  "tick": {"count": 60, "observeAt": [0, 60], "observers": ["game.tick"]},
  "expectations": {"tickObservations": [
    {"tick": 0, "id": "game.tick", "equals": 0},
    {"tick": 60, "id": "game.tick", "equals": 60}
  ]}
}
```

The example's expected game-tick values assume that the actual session
begins at tick zero. The Worker records `startTick` and absolute
`gameTick`; a real-game run must verify the observed start tick rather
than assuming it is always zero.

## Compatibility and safety

- `bounded-tick.v1`: unchanged two-key tick configuration; existing unknown
  observer names stay formally accepted but observationally incomplete.
- `bounded-tick.v2`: exactly `count`, `observeAt`, and `observers`.
  Current allowed IDs are `fixture.counter` and `game.tick`, sorted
  lexicographically, unique, at most two.
- Cache keys include case ID, observer version, selected IDs, tick points
  and expected values. An incomplete/forged/old-version baseline is not reused.
- The Controller validates count, points, names, monotonic real tick sequence,
  typed values and evidence metadata. Interrupted/exception cases remain
  incomplete even if the last sample was reached.
- Any error reported by RimWorld during a controlled tick aborts the D run;
  the Watchdog only reads checkpointed evidence, never game objects.
- D v2 remains `fidelity=experimental` and reports `dNotQualified` even
  when all values match. No claims about rendering, arbitrary MOD jobs,
  construction, apparel changes or map plant enumerations.

## Verification and further work

Public Python synthetic tests cover v1/v2 request separation, strict names,
missing/forged evidence and distinct cache identities. Public .NET synthetic
tests run both runners and reject extra keys. Worker builds on
Windows/Linux without game assets. Real-game D v2 acceptance and official
independent comparison **have not been performed**.

The v2 registry is extensible only by adding carefully reviewed,
build-specific Worker readers, typed expectation contracts and independent
game evidence. Adding arbitrary reflective paths or treating
self-reported log warnings as trusted observations would violate this design.
Apparel/job/blueprint fixtures and official headless comparison remain
tracked in Issue #55.
