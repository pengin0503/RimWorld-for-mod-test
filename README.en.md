# RimWorld-for-mod-test

[日本語](README.md) | **English**

A test-only tool for validating RimWorld mod loading and selected game logic on Linux. It is not a playable game and does not launch the official game executable. Legally supplied game files are required; the game is not distributed here.

## Usage

See the [validation host guide](docs/validation-host.md) for setup and execution, the [R2 guide](docs/r2-on-demand.md) for fetching required files from Cloudflare R2, and the [result contract](docs/contracts/mod-validation-v1.md) for interpreting results. These guides are in Japanese.

## Supported scope

The combination of Linux x86_64, RimWorld 1.7.4985 rev1269 and the bundled WaylithClr is qualified for mod loading, XML patches, reference resolution, Def checks and selected Harmony checks. Map generation is separately qualified.

Bill ingredient candidates, limited event choices and bounded-tick validation are experimental and not independently qualified. The tool does not validate all behavior of arbitrary mods. Static checks report `gameVerification=notRun` and do not establish successful game-logic validation.

Windows game validation is unsupported. Successful Linux results do not guarantee Windows behavior.
