---
name: rimworld-product-direction
description: User's 2026-10-25 product direction for the RimWorld MOD test host: GUI on Windows mimicking vanilla UI, AI-readable Linux output, future craft/event/quest checks — saved as policy only, not yet implemented
metadata:
  type: project
  modified: 2026-10-25T14:52:55.789Z
---

User instruction 2026-10-25 14:52 (thread "検証ホストにマップ生成を追加"). SAVE AS POLICY ONLY — do not implement until the user asks (same as the work blocked on PC folder access).

- Map generation must be visible to the user (visual info matters). Current state: schematic map.png from PR #6.
- Future checks wanted: bugs in the crafting screen (bills/recipes), and bugs when events (incidents) and quests fire. These need a game in Playing state + ticks + UI windows → the C/D stages after map generation.
- All results, even ones that need no GUI, should be viewable in one unified GUI for the user's convenience.
- Windows build: used by the user themself → GUI. UI should resemble the vanilla RimWorld UI as closely as possible (convenience). Still a test tool, never playable.
- Linux build: used only by AI → output in whatever form is easiest for the AI to read (structured JSON/text + images it can open), no need for a human GUI.
- User relaxed the "never launch the official executable" rule: use it where not using it would be any disadvantage (see [[rimworld-test-harness]]).
- User said they cannot picture the finished product; explain the end state so they can give correct instructions (explanation doc made 2026-10-25).

**Why:** user wants to steer the roadmap correctly. **How to apply:** design future stages (ticks, crafting, incidents/quests) and the result viewer around this; ask before starting the GUI work.
