# Residual branches: safe integration design (2026-11-05)

## Goal

Consolidate all public-safe, still-useful work from twelve residual historical branches into the supported main tree without regressing the Linux 1.7.4985 validation host, weakening provenance requirements, or accidentally making previously temporary/private jobs active. This does not mean attaching each old commit as a parent to main: source branches can contain third-party game/MOD binaries that must never become reachable from main history.

## Architecture decisions

1. One supported live implementation to carry forward: separately authored DPA CSV Exporter addon (author metadata pengin0503) from the historical DPA branch. Copy only source, About metadata, README and isolated CSV-format tests into addons/DPA-CSV-Exporter. Mark as optional, unqualified and requiring privately supplied game references for a real build. Source itself must not embed game/MOD code. Run the CSV serialization test in public synthetic-only CI with .NET 10. Never compile the addon against game DLLs in public CI.
2. Historical one-shot workflows for Keep Aim N Shoot, Immersive Filter, and private acceptance are NOT installed under .github/workflows on main. Their event triggers are tied to deleted branch names, and Immersive Filter's branch contains a binary and base64-encoded third-party MOD/source content prohibited by AGENTS.md. The independently produced experimental Melee Animation source transformation also contains copyrighted source-match fragments and is NOT imported into the public host.
3. Old headless design, PR22 probe, preflight GUI and R2 workflows are superseded or retired. No legacy source replaces newer main implementation. QoL three-mod workflows pin obsolete MOD commits; preserve their purpose in the carry-forward inventory rather than activating stale R2 runs.
4. PR #53 1.7.4995 readiness is already merged via squash commit 1500286a4ee1e9138e67ea616cb06ee6e5e9d81f. No further build qualification is inferred.
5. The proposed integration report must give each historical branch name/HEAD, what is carried forward, what remains excluded and why. This is a provenance record, NOT a claim that all original content was merged. Remaining branch deletion only after separately verified archival and owner action, and GitHub tool in this session has no delete-branch operation.

## Safety and test requirements

- No third-party DLLs, compiled .NET assemblies, game XML/assets, Workshop content, base64-encoded source archives, private index, credentials, raw logs or personal paths.
- The DPA exporter cannot be represented as runtime-verified. Its 11+ CSV-format assertions cover only serialization.
- Existing eight public CI jobs must remain passing after integration, including Python tests and two .NET Worker builds.
- Preserve 1.7.4985 runtime qualification status unchanged. Do not bring abandoned Windows GUI work back.
- Do not direct-merge branches whose file trees have diverged heavily from main: such a merge may overwrite qualified Worker/controller code.
