# 作業メモ（AI用プロジェクトメモの写し）

Claude がこのプロジェクトで使っている作業メモの 2026-10-25 時点の写しです。原本はプロジェクトのメモリにあり、こちらは自動では更新されません。内容は当時の判断と確認済みの事実の記録で、仕様ではありません。

## 索引

- Goal: test-only validation host for RimWorld MODs (real game code, never playable). Repo: pengin0503/RimWorld-for-mod-test (public; never commit game DLLs/Data/decompiled code).
- Method (2026-10-25): independent host calling game DLLs; `play`/GUI launch removed. Feasibility proven on Linux + WaylithClr. Update 2026-10-25 14:43: user allows using the official exe where avoiding it causes any disadvantage (still never playable).
- Game files: official RimWorld 1.7 (Waylith engine, no Unity). Linux build 1.7.4985 rev1269 on user's PC at D:\rimworld-linux (cloud copy is session-local; PC often offline). Anomaly DLC not owned → out of scope.
- Scope: A + B done and merged to main (PR #5). C: map generation draft PR #6 (not yet run on real game); ticks/behavior later.
- Future policy (2026-10-25, saved only, not yet built): map results must be visible to the user; also want checks for crafting-screen bugs, events, quests. Windows version (user-facing) gets a unified GUI resembling the vanilla UI as closely as possible; Linux version is AI-only, output in the form easiest for AI.
- User mainly uses iPad; AI runs validation in the Claude cloud Linux env.
- Details: [rimworld-test-harness](rimworld-test-harness.md) — decisions/status; [rimworld-headless-spike](rimworld-headless-spike.md) — verified technical facts
- Product direction (2026-10-25, policy only): [rimworld-product-direction](rimworld-product-direction.md) — Windows GUI like vanilla UI, Linux AI-readable, future craft/event/quest checks
