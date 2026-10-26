# SDD ledger — plan: docs/superpowers/plans/2026-10-26-windows-gui-w2.md
Execution: inline (user said "その方向性で進めていって" 2026-10-26 10:40; no subagents without request).
Ruling: execution approved by the user's go-ahead on the spec; plan not separately reviewed — user works async and asked to proceed — cost if wrong: plan details revised later.
Pre-flight: Task 1 Model consumed by Tasks 3-6 (GuiRequest/RunSettings/ResultSummary); Task 2 writes gui-request.json read by GuiRequest.Load — field names must match (camelCase JSON).
Task 1: complete (commits 0964184..f88e03e, tests: dotnet test gui/RimWorldValidation.Gui.Model.Tests -c Release → 26/26; tests.test_gui_model_sync → 2/2)
Task 2: Ruling: launch re-matches the adapter (vh.match_adapter) instead of trusting snapshot.json's recorded adapter — same rule as the Controller per run — cost if wrong: none, stricter.
Task 2: Ruling: a missing mod root is skipped with a reason instead of crashing (found by test) — the GUI must open with a stale setting — cost if wrong: a typo'd root is only logged.
Task 2: Ruling: 'desktop' kept as a migration-error command like 'play' rather than deleted — old shortcuts get an explicit message — cost if wrong: one dead subcommand.
Task 2: complete (commits f88e03e..9f6fe63, tests: python3 -m unittest discover -s tests → 215 OK, 8 skipped)
Task 3: Ruling: added exit code 5 (test script step failed) beside the plan's 2/3/4 — a broken script must not look like a normal close — cost if wrong: one more code to document.
Task 3: Ruling: the exit-3 guards (Game created, Entry/Play scene, validation scene unloaded) were verified with a throwaway private build adding makeGame/loadScene steps, not a product hook — the product must have no way to create a Game — cost if wrong: guards regress unnoticed until re-checked by hand (no CI can run the game).
Task 3: Ruling: BundledVulkanLoaderPath set on Windows as the game's Program does (found in the official entry, not in the spike) — cost if wrong: Windows may use the system Vulkan loader.
Task 3: complete (commits 9f6fe63..a9b3445, tests: GUI build Release 0 warnings; cloud xvfb run exit 0 with 2 screenshots; guards exit 3 x3, script 5, args 2, mismatch 4; python boundary+gui_host tests OK)
Task 4: Ruling: "apply" (RunSettings) implemented in Task 4 for the MOD part, plus test-only steps importModsConfig/selectMod/waitSeconds — needed to photograph the tab states and to drive xdotool — cost if wrong: a few extra script verbs.
Task 4: Ruling: row target mark uses ButtonInvisible + CheckboxDraw instead of Widgets.Checkbox — real clicks were missed inside the reorderable list (xdotool, reproduced twice) — cost if wrong: none visible; same icon and sound.
Task 4: Ruling: double click to move a MOD left unverified — cloud lavapipe runs ~3 fps (291 frames/90 s) so two clicks merge; buttons do the same job and were verified — cost if wrong: double click may not move on the user's PC (to be checked in the Windows steps).
Task 4: complete (commits a9b3445..bbc67f7, tests: GUI build 0 warnings; cloud screenshots import/target/after-input; xdotool drag, checkbox, move button verified)
Task 5: Ruling: "run" only starts and "waitRun" waits (plan: run waits) — needed a screenshot and a real click on 中止 while running — cost if wrong: one more script verb.
Task 5: Ruling: Controller has no progress output, so the phase comes from the folders it creates (baseline/, target/, result.json) — cost if wrong: phase text is coarse.
Task 5: Ruling: cancel = Process.Kill(entireProcessTree) + "cancelled" marker + remove_run_host via the Controller's python routine (never clears read-only attrs shared with the snapshot) — cost if wrong: a slow cleanup process after cancel.
Task 5: Ruling: Model now rejects empty recipe/thing/seed and history reads targets from request.json for runs without a result (found while wiring the tab) — cost if wrong: none.
Task 5: complete (commits bbc67f7..58adbde, tests: model 30/30; python 215 OK; cloud: GUI-started A+B+C run wrote result; cancel by click left 0 Controller/Worker, host links removed)
Task 6: Ruling: added test-only script step "openResult" (opens a result folder like a history click) — cloud screenshots need a deterministic way to show a given result; xdotool clicks at 3 fps are unreliable — cost if wrong: one unused step in a test-only list.
Task 6: Ruling: map image path falls back to result/<file name> when the absolute path in result.json is gone — a moved/copied results folder still shows its maps — cost if wrong: a same-named file shown from a different run folder (only if the user copies files by hand).
Task 6: Ruling: bill outcomes shown as match/mismatch/other (the Controller's actual strings), not "matched" — verified against result.json — cost if wrong: none.
Task 6: Ruling: errors list sorts verdict-counted diagnostics first and labels the section "判定 N／除外 M"; supersededBy (translation count warning) treated as excluded like the Controller's _excused() — a run with 96 engine-noise leak warnings looked like 96 problems — cost if wrong: none; the Controller's verdict is unchanged.
Task 6: Ruling: targets shown by packageId (folder in brackets on the result view); a cancelled run without result.json still shows the folder name because request.json has no packageId — cost if wrong: workshop-number names on cancelled rows only.
Task 6: Ruling: verdict area height adapts to its reasons (cap 40% of the tab) — fixed 220 px left empty space — cost if wrong: none.
Task 6: complete (commits 58adbde..9293d30, tests: dotnet test Model.Tests → 31/31; python unittest → 215 OK, 8 skipped; cloud screenshots t6/t6b/t6c)
Task 7: docs updated (validation-host.md §5 tabs/script steps/exit codes, finished-product.md status, spec status, AGENTS.md CI note).
Final review: self-review (no subagent tool use — user rule: no subagents unless asked). Read gui_host.py, RunController, ResultsTab/HistoryTab, Model; Windows-only paths cannot be exercised in the cloud.
Final: minor (deferred): cancel cleanup (remove_run_host) runs asynchronously; closing the GUI right after 中止 can kill it and leave host links inside that run's result folder (links only; the snapshot is untouched).
Final: minor (deferred): double click in the MOD lists is unverified (cloud renders ~3 fps); arrow buttons are the verified path.
Final: minor (deferred): Windows GUI runs with the W1 private environment (PATH/SystemRoot/... only); a GPU driver needing other variables is untested until the user's PC run.
