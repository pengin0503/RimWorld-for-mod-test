# D private probe observation analysis (2026-11-05)

The existing `bounded-tick.v1` Controller/Worker validates only `fixture.counter`.
This experiment **does not change** its validated observer set, independent
qualification, cache eligibility or result contract.

The November 1 real-MOD investigation used a private `GameComponent` probe
and emitted human-readable `RWMT-PROBE` warnings. The new
`tools/probe_observations.py` is an *optional local analysis step*: a
private probe can emit structured warning messages for numeric observations
and the tool can compare them to fixed private expected values.

## Input contract

Each probe warning must be a single log message of the form:

```text
RWMT-PROBE {"schemaVersion":1,"tick":60,"id":"probe.food","value":9}
```

`tick` is the probe's own relative tick (0..60000). `value` is a signed
64-bit integer; booleans, floating point and arbitrary object trees are not
supported. `id` must start with `probe.` and is capped to a safe identifier
pattern. The probe itself is private and explicitly authored for the test.
It must not be obtained from untrusted descriptions or execute arbitrary
method names from external JSON.

Create a private expected-values JSON array:

```json
[
  {"tick":0,"id":"probe.food","equals":4},
  {"tick":60,"id":"probe.food","equals":9}
]
```

Then, **outside the public checkout's tracked files**, run:

```bash
python -m tools.probe_observations --events /private/run/events.jsonl --expectations /private/expected.json
```

The tool only reads local files; it never talks to R2. It ignores unrelated
warning messages and rejects malformed/duplicate probe evidence. It limits
log size (8 MiB), line size (8 KiB), event count (20,000), probe count
(256), expectation count (64), tick range and integer range. Structured
comparison states are `matched`, `mismatch`, and `incomplete`. The
fixed evidence fields always say `fidelity=experimental` and
`source=untrustedProbeLog`. No self-reported warning is promoted to
an independently qualified game observation.

## Not yet built

- Automatic generation of the private probe from a declarative scenario.
- A stable, trusted Worker observer plugin protocol; the current messages are
  private warning text and are not authenticated.
- Automatic Controller integration or promotion from D's experimental state.
- Real-game adoption of these new JSON messages in the November 1 probe.
- Validation of arbitrary jobs, weather, incidents, save/load or rendering.
- D's outstanding independent official comparison and camera/diagnostic gaps.

A later `bounded-tick.v2` would require a separately designed observer
registration/identity contract, a new versioned cache key and real-game
acceptance. Do not change `OBSERVERS={'fixture.counter'}` to accept
untrusted free-form IDs as if they were game-verified.
