---
name: rimworld-headless-spike
description: Verified technical facts for the RimWorld 1.7 test-only validation host (Linux build, WaylithClr, call path, fixtures, comparison results)
metadata:
  type: project
  modified: 2026-10-25T10:26:39.623Z
---

Facts verified 2026-10-25 in the cloud Linux env (supersedes the older "official -headless" spike notes):
- User's Linux install was staged from device D:\rimworld-linux to /mnt/user-data/uploads/rimworld-linux (session-local, NOT persistent). Version.txt "1.7.4985 rev1269"; RimWorld.dll 1.7.4985.1269 and Assembly-CSharp 1.7.9790.38077 share commit 535691cc. Game managed DLLs (Assembly-CSharp, RimWorld, Waylith*, UnityStubs) are byte-identical to the earlier Windows set; only BCL/native/runtime differ. All native .so deps resolve (ldd). Shipped WaylithClr = 10.0.13-waylithclr.dev, libsteam_api.so and libwaylithaudio.so present.
- Working call path (no official exe): own apphost + game runtimeconfig (WaylithClr props) + deps.json derived from RimWorld.deps.json with the root project renamed → Waylith EngineApplication.Run(Headless, MiniAudioBackend) → replicate Bootstrap/Root.Start minus Entry scene/UI/Steam → LongEventHandler queues StaticConstructorOnStartupUtility.CallAll + PlayDataLoader.LoadAllPlayData(async) → pump LongEventsUpdate until Loaded && !AnyEventNowOrWaiting → Quit. Core-only ≈8 s, Core+4 DLC+Japanese ≈13.5 s.
- Run dir = exe dir: Data/ (only requested official folders, so ModsConfig won't auto-add DLC; also list all in knownExpansions), Mods/, userdata (ConfigurePaths). Prefs.xml devMode=true (else ErrorCheckAllDefs skipped), resetModsConfigOnCrash=false.
- Verse.Log goes through Brutal LogSystem category "Verse"; add own ILoggerProvider to capture. Verse.Log stops at 10000 msgs.
- Fault fixtures (tests/fixtures/validation-mods) all detected by real game code; diagnostics identical to a dev-only official `-headless -QuitAfterBoot` run (Steam warnings aside). Harmony (Lib.Harmony 2.4.3 net10) registration+effect identical too.
- Standard .NET 10.0.13 also runs but adds a real difference: ProfilerBootStart static ctor fails (WaylithClr.MethodBodyUpdater type missing) → standard = experimental.
- CORRECTION 2026-10-25: Core-only DevMode load has NO config errors (only a UnityStubs DrawTexture stub warning). The "Config error in Grenadier_Smoke/Villager: Cheapest weapon…" errors were caused by the old okxml fixture raising Steel MarketValue to 2.5 (now the `sideeffect` fixture). Full DLC + Japanese adds "Translation data for language Japanese has 28 errors". Diagnostics are still diffed against a baseline run (same config minus target mods).
- Language prefs must use the Core language folder/archive name: Languages ship as `Japanese (日本語).tar`; Prefs langFolderName "Japanese" silently falls back to English. Controller resolves "Japanese" → "Japanese (日本語)" and the Worker reports activeLanguage.
- Product implemented 2026-10-25: tools/validation_host.py (prepare-game/run) + worker/RimWorldValidation.Worker. Matrix tests/integration/run_fixture_matrix.py (16 cases) and dev-only experiments/official-comparison/compare_official.py (9 cases, errors+probe facts identical to official headless).

See [[rimworld-test-harness]] for decisions.
- Real mods (2026-10-25, user-supplied zips, session-local at /home/claude/rw/realmods): Harmony mod 3.0.1.0 (0Harmony 3.0.0.0-rc.3, brrainz.harmony) and Vanilla Expanded Framework 1.7 (OskarPotocki.VanillaFactionsExpanded.Core; 8 DLLs, 410 Harmony patches incl. 65 transpilers). Both pass A/B on Core and all-DLC English; all-DLC Japanese adds 3 translation errors (VEF's Biotech patch removes SchoolDesk/Blackboard comps that official Japanese DefInjected targets) → newWarnings. Worker now reports translationErrors items. Official headless matches product on these 4 cases. A failed load (missing Harmony) makes the official boot loop forever (Root_Entry.Update NRE each frame) — the Worker ends.
