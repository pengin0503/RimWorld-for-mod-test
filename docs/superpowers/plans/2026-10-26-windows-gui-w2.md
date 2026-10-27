# W2：ゲームの描画で作る検証 GUI 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows のユーザーが、本家の部品で描いた画面から MOD と検証内容を選び、W1 の検証を実行し、結果を見られるようにする。

**Architecture:** Python の `tools/gui_host.py` が画面用の実行ディレクトリを作り、ゲームの DLL を参照してビルドした C# の画面プログラム `RimWorldValidationGui` を監視下で起動する。画面は検証のたびに `validation_host.py run` を子プロセスで呼び、`result.json` を表示するだけ。画面に依存しない処理はゲームを参照しない `RimWorldValidation.Gui.Model` に置き、公開 CI でテストする。

**Tech Stack:** Python 3.12+ 標準ライブラリ、.NET 10（C#）、xUnit（Model のテストだけ）、ゲームの Waylith・Verse の UI（画面プログラムだけ）。

**Spec:** `docs/superpowers/specs/2026-10-26-windows-gui-w2-design.md`（ユーザー承認 2026-10-26 10:40「その方向性で進めていって」）。試作の記録は `docs/research/2026-10-26-w2-render-spike.md`。

## Global Constraints

- 遊べる状態にしない：`Root_Entry`・`UIRoot_Entry`・メインメニューを作らない。`Current.Game` ができたら終了コード 3 で終了。シーン切り替えの要求でも終了。`Prefs.DevMode=false`。Steam を初期化しない。
- 画面は判定しない。合否・理由は `result.json` の値をそのまま出す。Windows の `experimental` も隠さない。
- 利用者の本家の設定を書き換えない。本家の `ModsConfig.xml` は読むだけ。画面のプロセスの設定・ログは実行ディレクトリの中。
- 公開リポジトリにゲームの DLL・素材・逆コンパイル本文・画面写真・私有パスを入れない。
- 画面プログラムはゲームの DLL を参照してビルドする（`-p:GameDir=<スナップショットの game>`）。公開 CI ではビルドしない。
- 公開 CI でゲームを起動しない。
- Python は標準ライブラリだけ。Windows（Job Object・ハードリンク・ジャンクション）と Linux（プロセスグループ・シンボリックリンク）の両方で動く。
- 文言は日本語。

## Review Focus

1. 画面の子プロセスとして動く検証が、画面を閉じたとき・強制終了したときに残らないこと（Windows は Job Object、Linux はプロセスグループ）。→ Task 2 のテスト `test_closing_the_gui_stops_its_children`。
2. MOD の候補に同じ packageId が複数あるとき（`Mods` と Workshop の両方など）、画面の一覧が壊れず、どれを使うかが決まっていること。→ Task 2 のテスト `test_duplicate_package_ids_keep_the_first_root`。
3. `result.json` に知らない理由コードや欠けた項目があっても、結果タブが落ちずにコードをそのまま出すこと。→ Task 1 のテスト `unknown_reason_code_is_shown_as_is`・`missing_sections_are_empty`。
4. 結果フォルダに書きかけ（`result.json` なし）の検証があっても履歴が落ちないこと。→ Task 1 のテスト `history_lists_unfinished_runs`。
5. 要求の自由入力（JSON）が壊れているときに、検証を始めずに理由を示すこと。→ Task 1 のテスト `invalid_extra_json_is_reported`。

---

### Task 1: 画面に依存しない Model ライブラリ

**Files:**
- Create: `gui/RimWorldValidation.Gui.Model/RimWorldValidation.Gui.Model.csproj`（net10.0、ゲーム参照なし、警告はエラー）
- Create: `gui/RimWorldValidation.Gui.Model/ResultSummary.cs`、`ReasonCatalog.cs`、`RunSettings.cs`、`RequestBuilder.cs`、`ModsConfigReader.cs`、`RunHistory.cs`、`GuiRequest.cs`
- Create: `gui/RimWorldValidation.Gui.Model.Tests/`（xUnit）
- Modify: `.github/workflows/offline-audit.yml`（`gui-model` ジョブ：ubuntu と windows で `dotnet test`）

**Interfaces（Produces）:**
- `ResultSummary.Load(string resultJsonPath) -> ResultSummary`：`Status`・`ExecutionStatus`・`Fidelity`・`Reasons (Code, Detail)`・`NewDiagnostics (Level, Category, Stage, FirstLine, Text, KnownNoise, AllowedBy)`・`MapImage`・`MapBaselineImage`・`BillChecks (Recipe, Thing, ExpectedVisible, ActualVisible, Allowed, Outcome, Reasons)`・`Checked`・`NotChecked`・`TotalSeconds`・`Platform`。欠けた節は空。
- `ReasonCatalog.Describe(string code) -> string`（日本語。知らないコードは `code` を返す）。`ReasonCatalog.StatusLabel(string status) -> string`（passed=合格、failed=不合格、incomplete=不完全、blocked=実行できず）。全理由コード（`validation_host.py` の `Blocked(...)` と `reasons` の全コード、`worker*` の 4 種）を網羅する。
- `RunSettings`：`Official (IReadOnlyList<string>)`、`Mods (IReadOnlyList<(string Path, bool Target)>)`、`Language`、`LevelB`、`Map (Seed, Biome)?`、`Bill (Recipe, Thing, Visible)?`、`ExtraJson`。
- `RequestBuilder.Build(RunSettings) -> JsonObject`：`modValidationRequest` v1。C は `levels` に C、`tests: ["bill-ingredient-options.v1"]`、`expectations.billIngredients`。`ExtraJson` は `expectations`・`allow` を持つオブジェクトとして合成。壊れていれば `RequestBuildException`（日本語の理由）。
- `ModsConfigReader.ReadActive(string path) -> IReadOnlyList<string>`（packageId を小文字で）。
- `RunHistory.List(string resultsDir) -> IReadOnlyList<HistoryEntry (Id, Dir, HasResult, Status, StartedAt, TargetNames)>`（新しい順）。`RunHistory.NewRunDir(string resultsDir, DateTime now) -> string`（`yyyyMMdd-HHmmss`、重複は `-2` など）。
- `GuiRequest.Load(string path)`：`HostDir`・`UserDataDir`・`ResultsDir`・`SnapshotDir`・`Python`・`Controller`・`WorkerDir`・`BaselineCache`・`ModsMap (link folder name → original path)`・`UserModsConfig?`・`Script?`。

- [ ] テストを先に書く：`unknown_reason_code_is_shown_as_is`、`missing_sections_are_empty`、`reads_real_shape`（`flour-bug` 相当の最小 JSON：C の mismatch・`notChecked`）、`every_controller_reason_code_has_text`（理由コード一覧を定数で持ち、全部に日本語）、`builds_minimal_request`、`builds_map_and_bill_request`、`invalid_extra_json_is_reported`、`reads_mods_config_active_list`、`history_lists_unfinished_runs`、`new_run_dir_is_unique`、`gui_request_round_trip`。
- [ ] 失敗を確認 → 実装 → `dotnet test gui/RimWorldValidation.Gui.Model.Tests` が通る。
- [ ] CI に `gui-model` ジョブを追加。コミット。

### Task 2: Python の起動役 `tools/gui_host.py`

**Files:**
- Create: `tools/gui_host.py`
- Create: `tests/test_gui_host.py`（偽の画面プログラム：Python スクリプト）
- Modify: `Start-Windows.cmd`（`py -3 tools\gui_host.py launch`）
- Delete: `tools/preflight_gui.py` と `mod_preflight.py desktop`、関連テスト（事前検査の CLI は残す）

**Interfaces（Consumes）:** `validation_host.load_snapshot`・`_win_fs`・`_win_job`・`_about_package_id`・`BUILD_FILES`・`GAME_EXCLUDED`・`OFFICIAL_ORDER`・`EXPANSION_IDS`・`resolve_language`。

**Interfaces（Produces）:**
- `GUI_NAME = 'RimWorldValidationGui'`。
- `settings_path() -> Path`（Windows `%LOCALAPPDATA%\rwmt\gui-settings.json`、他は `~/.config/rwmt/gui-settings.json`）。`setup` で `snapshot`・`results`・`mods[]`・`modsConfig`・`memoryMiB` を保存。
- `discover_mod_folders(roots) -> (list[dict(packageId, path, root)], list[dict(skipped)])`：`About/About.xml` があるフォルダ。同じ packageId は最初の root を使い、残りは `skipped`。
- `default_mod_roots(snapshot) -> list[Path]`：スナップショットの `sourcePath` の `Mods` と `../../workshop/content/294100`（あるものだけ）。
- `default_mods_config(snapshot) -> Path | None`：`sourcePath/RimWorld by Ludeon Studios/Config/ModsConfig.xml`、Windows の `LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config/ModsConfig.xml`、Linux の `~/.config/unity3d/...` の順で最初にあるもの。
- `build_gui_dir(run_dir, snapshot, gui_dir, mods, *, results, python, controller, worker_dir, baseline_cache, mods_config, script) -> dict`：`host/`（ゲームのリンク、公式は全部、`host/Mods/<n>-<フォルダ名>` に MOD のリンク）、`userdata/Config/Prefs.xml`（devMode=false、日本語）・`ModsConfig.xml`（公式だけ）、`gui-request.json`。
- `run_gui(run_dir, memory_mib, environment) -> dict`：Windows は Job Object、Linux はプロセスグループ。時間の上限なし。終了・Ctrl+C で子孫ごと止める。
- `gui_environment(run_dir, memory_mib)`：W1 と同じ私有の HOME 類。表示に要る `DISPLAY`・`WAYLAND_DISPLAY`・`XDG_RUNTIME_DIR`・`VK_ICD_FILENAMES` だけ追加で引き継ぐ。
- CLI：`setup`、`launch [--script FILE] [--keep-run-dir]`。`launch` は `load_snapshot`（adapter 不一致は止める）、`gui/bin` の有無、実行ディレクトリの作成、起動、後始末（`remove_run_host`）。

- [ ] テスト：`test_gui_dir_links_game_and_mods_and_writes_private_config`、`test_duplicate_package_ids_keep_the_first_root`、`test_default_roots_follow_the_steam_layout`、`test_launch_runs_the_gui_and_cleans_up`、`test_closing_the_gui_stops_its_children`、`test_missing_gui_build_is_reported`、`test_environment_keeps_only_display_variables`。Linux と Windows の CI で動く。
- [ ] 失敗を確認 → 実装 → `python -m unittest discover -s tests` が通る。
- [ ] 事前検査 GUI を削除し、`Start-Windows.cmd` を差し替える。コミット。

### Task 3: 画面プログラムの起動部分

**Files:**
- Create: `gui/RimWorldValidation.Gui/RimWorldValidation.Gui.csproj`（`GameDir` 必須、未指定ならビルドを止めて理由を出す。ゲーム DLL は `Private=false`。Model を参照）
- Create: `Program.cs`（`--gui-request` 必須。違えば終了コード 2）、`Boot.cs`（試作の初期化。非公開メンバーを起動前に全部確かめ、欠ければ終了コード 4）、`ValidationRoot.cs`、`ValidationUIRoot.cs`、`MainWindow.cs`（4 タブの枠）、`ScriptRunner.cs`（試験用の操作と画面写真）

**Interfaces（Produces）:** `GuiState`（`GuiRequest`、選択中の MOD・設定・表示中の結果）を全タブで共有。`ScriptRunner` の操作：`{"tab": "mods"|"settings"|"results"|"history"}`、`{"openResult": "<dir>"}`、`{"apply": <RunSettings JSON>}`、`{"run": true}`（終わるまで待つ）、`{"screenshot": "<path>"}`、`{"quit": true}`。

- [ ] クラウドで `xvfb-run` と lavapipe で起動し、空のタブ枠の写真を撮る。`Current.Game` 検出・不正な引数・アダプタ不一致の終了コードを確かめる。
- [ ] 文書：`docs/validation-host.md` に画面のビルドと起動。コミット。

### Task 4: MOD タブ

**Files:** `gui/RimWorldValidation.Gui/ModsTab.cs`

- 一覧は `ModLister.AllInstalledMods`。公式（`Official`）は上の DLC の選択欄へ、その他は左右の一覧へ。右（使う）は並べ替え可能（本家の `ReorderableWidget`）。対象の印は行の右のチェックボックス。選んだ MOD の `PreviewImage`・名前・作者・packageId・説明・依存（`Dependencies` のうち使う一覧にないものを警告）。
- 「本家の読み込み順を取り込む」：`ModsConfigReader.ReadActive(UserModsConfig)` の順に右の一覧を作る（見つからない packageId は件数で警告）。
- MOD のリンク名から元のパスへは `ModsMap` で引く。

- [ ] 写真で確かめる（取り込み後の状態、対象の印、依存警告）。コミット。

### Task 5: 検証内容タブと実行

**Files:** `SettingsTab.cs`、`RunController.cs`、`RunProgressWindow.cs`

- A は常に。B（Harmony の期待値は自由入力の JSON に書く）、言語（`LanguageDatabase.AllLoadedLanguages` のうち英語・日本語など Core にあるもの、要求には英語名の前半を渡す）、マップ（種の文字入力、バイオームは `DefDatabase<BiomeDef>` の一覧から `FloatMenu` で選ぶ）、C（レシピ・材料の defName 入力と、本家の Def から候補を `FloatMenu`）。自由入力 JSON。
- 「検証を始める」：`RunHistory.NewRunDir` に `request.json` を書き、`<Python> <Controller> run --snapshot … --request … --out <dir>/result --worker … --baseline-cache …` を起動。出力の行を進捗の窓に出す。中止でプロセスツリーを止める。終わったら結果タブへ。
- [ ] クラウドで実ゲームの検証を 1 回、画面から通す（`ScriptRunner` の `apply`→`run`）。コミット。

### Task 6: 結果タブと履歴タブ

**Files:** `ResultsTab.cs`、`HistoryTab.cs`

- 結果：先頭に `StatusLabel` と色、理由（`Describe` と `detail`）。下に切り替えで、新しいエラー（レベル・段階・1 行目、選ぶと全文）、マップ（`map.png` と `map-baseline.png` を `Texture2D.LoadImage` で読み、並べて表示）、製造指示（材料ごとの期待・実際・理由）、確認した範囲・確認していない範囲。結果フォルダを開くボタン（エクスプローラー）。
- 履歴：`RunHistory.List` の一覧。選ぶと結果タブ。
- [ ] 写真で確かめる（Linux の実結果、マップ付き、C の mismatch）。コミット。

### Task 7: 仕上げ

- `docs/validation-host.md`・`docs/roadmap/finished-product.md`・設計書の状態・`AGENTS.md`（画面プログラムは CI でビルドしない理由）を更新。
- ユーザー向けの Windows 手順書（Claude Doc）：.NET SDK、画面プログラムのビルド、`setup`、`launch`、確かめてほしい点。
- 全テストを実行し、クラウドで全タブの写真を撮ってユーザーに渡す（写真は公開しない）。
