---
name: rimworld-test-harness
description: RimWorld MOD test-only validation host project — goals, constraints, current method and decisions
metadata:
  type: project
  modified: 2026-10-25T13:21:10.597Z
---

Goal: validate RimWorld MODs with real game code where the game can't be opened; never playable. Repo github.com/pengin0503/RimWorld-for-mod-test (public). Never commit game DLLs/Data/decompiled source/personal data; public CI = self-made fixtures only.

Current decisions (2026-10-25, user handoff message):
- Primary use: user on iPad instructs AI; AI validates/fixes/re-validates on Linux without the user's PC. Secondary: Windows user self-validation.
- Method: independent test-only host calling needed game DLL code (spec docs/superpowers/specs/2026-10-25-test-only-host-design.md). No play/GUI launch. Don't silently switch methods.
- UPDATED 2026-10-25 14:43 (user): if not using the official executable causes any disadvantage, use it where possible (was: never launch it in the product). Still never playable. Known cases: qualifying map gen needs official `-headless -quicktest`; the host's map stage skips game start (Game.FinalizeInit/StartedNewGame) which an official quicktest run would cover — candidate opt-in official cross-check mode.
- Distinguish static checks vs real loader vs DLL/Harmony vs specified behavior. Linux success ≠ Windows guarantee. No fake success for missing inputs.
- Anomaly DLC out of scope (not owned).
- Work branch claude/project-thread-poug58. Everything is now on main; base new work on main. Default: leave a reviewable PR; merge only when the user asks (they did for #5).

Status 2026-10-25: A/B implemented and qualified on Linux x64+WaylithClr+1.7.4985 rev1269 (see [[rimworld-headless-spike]]). PR #3 (claude/project-thread-poug58 → base docs/headless-design-review, stacked on #1) merged by the user 2026-10-25 into docs/headless-design-review (CI green incl. Windows worker-build); reaches main only via PR #1. Follow-up work: restart the branch from the latest base. PR #4 (same branch → docs/headless-design-review, 2026-10-25): real-mod validation (Harmony + VEF) and translationErrors detail; merged by the user 2026-10-25. 2026-10-25 user asked to merge everything into main: PR #5 (claude/project-thread-poug58 → main) adds request "allow" rules + ZIP mod input; user explicitly approved merging it. PR #5 merged into main by the user 2026-10-25 13:20 (CI green; GitHub also marked PR #1 merged). Codex re-review of the final commit 941b851 was still running at merge time; any findings need a fresh follow-up PR (branch restarted from main). Next: user asked what other mods are wanted (suggested a VEF-dependent VE mod and a transpiler-heavy large mod). PR #1's head branch is not pushable by Claude, hence the stacked PR. Remaining: real user MODs + Harmony MOD (input pending), Windows run, C tests, known-warning allowlist.
User's Linux files live on their PC at D:\rimworld-linux; cloud copies are session-local, so a new session must re-stage (device folder access) unless an archive is saved to /mnt/project-files.

**Why:** avoid re-asking design decisions. **How to apply:** follow these; update when they change.

Map stage (2026-10-25): draft PR #6 (branch claude/project-thread-r9l616 → main) adds `map` request + map.png schematic + mapThings; NOT yet run on real game files (PC offline). Next with game files: run matrix map cases, `compare_official.py --map`, then add 'map' to adapter qualified.features. Lib.Harmony 2.4.3 net10 0Harmony.dll is fetchable from api.nuget.org in the cloud env; dotnet SDK via apt (dotnet-sdk-10.0), dot.net download is blocked.
