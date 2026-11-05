# Static preflight must not reuse the 1.7.4985 loader for future knowledge packs

## Root cause
`tools/mod_load_plan.py` models only the independently qualified 1.7.4985 rev1269 loader and hardcodes `CURRENT=(1,7,4985)`, a special `1.7.4985` LoadFolders section, and version-dependent metadata rules. `tools/knowledge_preflight.py::load_database` correctly allows an explicit custom pack for a different exact build, but `inspect_mod` unconditionally calls the pinned 1.7.4985 loading planner. As a result an opt-in future pack can incorrectly return `staticChecksPassed` despite skipping 1.8-specific broken XML or choosing an older load-folder section.

## Requirement
- Only the exact qualified build `1.7.4985 rev1269` may use the current standalone static MOD scanner.
- Reject future/other build scans *before reading MOD content*, with explicit blocked outcome and no real-game qualification claim. `query`, `check`, and `validate-db` continue to accept a properly declared explicit exact-build pack; they only evaluate the pack's own positive assertions, never loader/runtime behavior.
- Do not auto-fallback to old loader and do not falsely report `staticIssuesFound` for a newer game's valid semantics.
- Later versions may be unblocked only by introducing a separately verified loader policy and tests, not by copying a pack manifest.
- No game files, private R2, third-party MOD contents or runtime qualification changes.

## Tests
- RED on current main: load a synthetic 1.7.4995/1.8 pack, scan a synthetic MOD with conflicting version-specific XML; verify direct `inspect_mod` rejects and the CLI produces `blocked` exit 2. Show same test permits a positive `query` and `check` with the explicit pack.
- GREEN: existing pinned-build scan and all public Linux/Windows jobs pass.
