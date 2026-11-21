# RimWorld-for-mod-test

[日本語](README.md) | **English**

A test-only tool for validating RimWorld mod loading and selected game logic on Linux. It is not a playable game and does not launch the official game executable. Legally supplied game files are required; the game is not distributed here.

## Built-in offline knowledge preflight

A **version-pinned 1.7.4985 rev1269** reference pack now supports local metadata/XML checks and evidence-backed API, Def and Harmony name queries **without R2, game files, or a private Workshop index**. Example: run `python tools/codex_workflow.py static-preflight --mod ./MyMod` or `python tools/knowledge_preflight.py validate-db`. The catalog is deliberately partial: missing entries mean **unknown**, not absent. Static checks never qualify actual game behavior. See [the knowledge database guide](docs/knowledge-database.md).

## Usage

See the [validation host guide](docs/validation-host.md) for setup and execution, the [R2 guide](docs/r2-on-demand.md) for fetching required files from Cloudflare R2, and the [result contract](docs/contracts/mod-validation-v1.md) for interpreting results. These guides are in Japanese.

## Supported scope

On Linux x86_64 with the bundled WaylithClr, mod loading, XML patches, reference resolution, Def checks and selected Harmony checks are qualified per game build. Qualified builds: RimWorld 1.7.4985 rev1269 and 1.7.5014 rev1195, both including map generation.

A new RimWorld 1.7 build runs without code changes, as experimental. It becomes qualified only when an automatic comparison with the official game of the same build agrees in every stage; see [following game updates](docs/build-updates.md). Another major.minor (such as 1.8) stops with `unknownBuild`.

Bill ingredient candidates, limited event choices and bounded-tick validation are experimental and not independently qualified. The tool does not validate all behavior of arbitrary mods. Static checks report `gameVerification=notRun` and do not establish successful game-logic validation.

Windows game validation is unsupported. Successful Linux results do not guarantee Windows behavior.
