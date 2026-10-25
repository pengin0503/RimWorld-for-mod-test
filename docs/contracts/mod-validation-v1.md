# MOD 検証の要求・結果契約 v1

対象：`tools/validation_host.py run` が読む `modValidationRequest` と、書き出す `modValidationResult`（どちらも `schemaVersion=1`）。既存の静的検査 `modPreflight` schema 1 とは別契約で、互いに読み替えません。

Controller と Worker の間の内部ファイル（`rwmtWorkerRequest` / `rwmtWorkerResult`、`events.jsonl`）は実装の詳細で、利用者が直接書くものではありません。

## 要求 `modValidationRequest`

```json
{
  "recordType": "modValidationRequest",
  "schemaVersion": 1,
  "levels": ["A", "B"],
  "official": ["Core", "Biotech"],
  "mods": [
    {"path": "mods/Harmony", "packageId": "brrainz.harmony"},
    {"path": "mods/MyMod", "target": true}
  ],
  "language": "Japanese",
  "expectations": {
    "defs": [{"type": "ThingDef", "defName": "My_Widget", "exists": true}],
    "defValues": [{"type": "ThingDef", "defName": "Steel", "path": "statBases[stat=MarketValue].value", "equals": "1.9"}],
    "keyed": [{"key": "My_Hello", "equals": "こんにちは"}],
    "harmonyPatches": [{
      "owner": "my.mod", "targetAssembly": "Assembly-CSharp", "targetType": "Verse.GenText",
      "targetMethod": "ToSpaceList", "targetParameters": ["System.Collections.Generic.IEnumerable`1[System.String]"],
      "kind": "postfix", "patchType": "MyMod.ToSpaceListPatch", "patchMethod": "Postfix"
    }]
  },
  "allow": {
    "diagnostics": [{"level": "warning", "match": "^Some known message", "reason": "why it is harmless"}],
    "translationErrors": [{"match": "^Couldn't inject SchoolDesk\\.comps\\.", "reason": "the mod removes this comp on purpose"}]
  },
  "limits": {"timeoutSeconds": 180, "memoryMiB": 4096, "logMiB": 32, "diagnostics": 2000, "messageKiB": 16}
}
```

| 項目 | 規則 |
|---|---|
| 未知のフィールド | 全階層で拒否（`blocked` / `invalidRequest`） |
| `levels` | `A` 必須。`B`（DLL・Harmony）と `C`（指定動作）は A の完了が前提。`C` は v1 では未実装で `blocked` |
| `official` | 既定 `["Core"]`。先頭は Core。Royalty/Ideology/Biotech/Odyssey から選ぶ。Anomaly は対象外（スナップショットにないため `officialContentMissing`） |
| `mods` | 読み込み順。公式コンテンツの後に並ぶ。`path` は要求ファイルからの相対パス可。`packageId` は任意で、指定時は About.xml と一致必須。`target: true` を 1 個以上。`path` が `.zip` で終わる場合は ZIP を `--out` の下へ展開して使う（下記） |
| `target` | 検証対象。ベースライン（同じ構成から対象だけ外した実行）との差分で、対象が持ち込んだ診断を判定する |
| `language` | Core の言語フォルダ名またはアーカイブ名（例 `Japanese (日本語)`）。括弧の前の英語名が一意なら受け付け、実名へ解決して結果に記録する |
| `expectations.defs` | `type` は Def の型名（一意でなければ完全名）。`exists` は真偽 |
| `expectations.defValues` | `path` はメンバー名の `.` 連結、`[n]`、`[key=value]`（Def は defName で比較）。`equals` は文字列。数値は相対 1e-6 で比較 |
| `expectations.keyed` | 選択言語での Keyed 翻訳。`equals` を省くと存在だけを見る |
| `expectations.harmonyPatches` | `B` 必須。対象メソッドは assembly・型・名前・引数型（`Type.ToString()` 形式）・任意の generic arity で一意に指定。`kind` は prefix/postfix/transpiler/finalizer |
| `allow.diagnostics` | 対象で新たに出た error/warning のうち、`level` が一致し、本文 1 行目に正規表現 `match`（Python の `re.search`）が一致するものを判定から外す。`reason` 必須。最大 200 件、`match` は 500 文字まで |
| `allow.translationErrors` | 対象で増えた個々の翻訳エラー（`diagnostics.translationErrors.newInTarget`）のうち、正規表現 `match` が一致するものを判定から外す。一致しないものが 1 件でもあれば `newTranslationErrors` で failed |
| `limits` | 既定値は上記。範囲外は拒否。`timeoutSeconds` は Worker 1 回あたり（ベースラインと対象で別々に適用） |
| `map` | 任意。指定するとロード完了後に一時的なワールドとマップを 1 枚生成する（下記「マップ生成」）。`A` が前提 |
| `expectations.mapThings` | `map` 必須。`type` は `ThingDef`（マップ上の個数）か `TerrainDef`（セル数）。`minCount`（既定 1）・`maxCount`（任意）の範囲に入れば一致。Controller がマップの観測結果から判定する |

## 結果 `modValidationResult`

主な項目：

- `status`、`executionStatus`（`completed` / `failed` / `notStarted` / `interrupted`）、`fidelity`（`qualified` / `experimental`）、`reasons[]`（`code` と `detail`）。
- `stages.A/B/C`：`completed` / `failed` / `incomplete` / `blocked` / `notRequested`。
- `request`（sha256、正規化後の levels/official/language/limits）、`game`（版、fingerprint、adapter、照合方法）、`platform`、`runtime`（実際の CLR 記述と WaylithClr 設定）、`tool.workerSha256`。
- `mods[]`（packageId、元パス、ZIP 入力なら `archive` の元パスと sha256、ファイル数、内容 sha256、同梱 0Harmony.dll）、`modOrder`（要求と実際）、`runningMods`、`modClasses`、`activeLanguage`、`loadedAssemblies`（mvid）。
- `checks`：期待値ごとの実値と `match` / `mismatch` / `missing` / `error`。Harmony は登録一覧、期待外の登録、読み込まれた Harmony の版も含む。
- `diagnostics.newInTarget`：ベースラインにない error/warning（多重集合の差）。`mentionsTargets` は本文に対象の packageId/フォルダ名が出るものの目安で、責任の確定ではない。
- `diagnostics.translationErrors`：ゲームが「Translation data for language X has N errors」と件数だけ出す翻訳エラーの中身。`targetCount`・`baselineCount`・`newInTarget`（ベースラインにない個々のエラー、多重集合の差）・`complete`（上限 `limits.diagnostics` で切り詰めていなければ true）。`allowed`（許可規則に一致したエラーと規則）・`notAllowed`。翻訳エラーは 1 件ずつ判定します。対象がエラーを 1 件直して別の 1 件を増やし、件数が変わらない場合も検出するためです。内訳が切り詰められていなければ、件数だけの警告は `supersededBy` を付けて判定から外します。切り詰められていれば、件数の警告も `newWarnings` として残します。読めなかった場合は `translationErrorsError` で incomplete。
- `workerStages`（engineInit → globalInit → staticConstructorsEarly → loadPlayData → lateLoadActions、各秒数と証拠）、`skippedOfficialSteps`、`deviations`、`scope`（確認した範囲と確認していない範囲）。
- `process`（終了コード、停止理由、最大 RSS、ログ量、上限の実施方式。メモリは監視ポーリングで `memoryHard=false`）、`timings`。

## 判定順序

1. **blocked**（`executionStatus=notStarted`）：要求不正、出力先が空でない（このときは出力先に何も書かず、何も消さない）、Linux x64 以外、未実装の C、Worker なし、スナップショット改変、公式コンテンツ・言語・MOD の不足、対応 Adapter のないビルド（`--allow-unknown-build` なし）、B で Harmony を同梱した MOD がない。
2. **incomplete**：Controller による停止（timeout/memoryLimit/logLimit）、Worker 結果の欠落・不正・古い nonce、Worker の未完了、ベースラインの未完了または信頼できないベースライン（診断の取りこぼし、Verse ログ上限、MOD 順序の不一致、翻訳エラーの切り詰め。キャッシュもしない）、`experimental`、診断の取りこぼし、Verse ログ上限、MOD 順序の不一致、言語が適用されない、期待値を評価できない、B で期待パッチ未指定。
3. **failed**：上記がなく、qualified な範囲で期待値の不一致、期待パッチの未登録、ロード例外、対象で新たに出た error/warning（`allow` で外したものを除く）、対象で増えた翻訳エラー（同）のいずれかを確認。
4. **passed**：上記のいずれもない。限定範囲の合格で、`scope.notChecked` は未検証。

incomplete でも、確認できた不一致や新しい診断は `reasons` と `diagnostics` に残します（例：`experimental` と `newErrors` の併記）。警告も合格の障害です。要求の `allow` で明示した場合だけ、個々の診断を判定から外します。外した診断も `diagnostics.newInTarget` に `allowedBy`（一致した規則と理由）付きで残り、件数は `diagnostics.allowedInTarget` に出ます。ツール側に組み込みの許可リストはありません。

## マップ生成

`map` を指定すると、Worker は A のロード完了後、ゲーム本体のコードで一時的なワールドとプレイヤー開始マップを 1 枚生成し、生成直後の状態を読み取って終了します。手順は公式の開発者向け quick test（`Root_Play.SetupForQuickTestPlay` → `GameInitData.PrepForMapGen` → `Scenario.PreMapGenerate` → `Game.InitNewGame` のうち `MapGenerator.GenerateMap` まで）と同じ順序で、値だけを要求から取ります。

```json
"map": {"seed": "rwmt", "size": 250, "planetCoverage": 0.3, "biome": "TemperateForest",
        "scenario": "Crashlanded", "storyteller": "Cassandra", "difficulty": "Rough",
        "mapGenerator": "Base_Player", "extraGenSteps": ["MyMod_RuinsStep"], "imageScale": 2}
```

| 項目 | 規則 |
|---|---|
| `seed` | ワールドの種文字列。既定 `rwmt`。ベースラインと対象は同じ種で生成する。ゲームの乱数状態もこの種から固定する（FNV-1a） |
| `size` | 50〜400。既定 250（quick test と同じ） |
| `planetCoverage` | 0.05〜1。既定 0.3（quick test と同じ）。小さいほどワールド生成が速い |
| `biome` / `tile` | どちらか一方。`biome` はそのバイオームの入植可能なタイルをゲームの関数で選ぶ。`tile` は地表レイヤーのタイル番号。どちらもなければゲームが開始タイルを選ぶ |
| `scenario`・`storyteller`・`difficulty` | defName。既定は quick test と同じ Crashlanded・Cassandra・Rough |
| `mapGenerator` | 任意。MapGeneratorDef を差し替える（既定は開始拠点のもの） |
| `extraGenSteps` | 任意。追加で実行する GenStepDef（最大 50） |
| `imageScale` | 画像の 1 セルあたりの画素数 1〜8（判定には影響しない） |
| `maxListedThings` | `map-observation.json` に位置付きで列挙する物の上限（既定 20000。植物・汚れ・自然の岩は数のみ） |

実行しない公式の手順（結果の `map.skippedOfficialSteps`）：Play シーン・カメラ・音楽・UI、`MapGenerator.GenerateMap` 後の `Game.InitNewGame` の残り（`Game.FinalizeInit`、`Scenario.PostGameStart`、`GameComponent.StartedNewGame` など）、tick。したがってゲーム開始時や時間経過で MOD が置く物は写りません。

結果：

- `stages.map`：`completed` / `failed` / `incomplete` / `notStarted` と `fidelity`。
- `map.image`（`--out/map.png`）と `map.baselineImage`（対象を外したベースラインのマップ）。1 セル 1 色の模式図で、ゲームの描画ではありません。対象 MOD の物はマゼンタ、対象 MOD の地形は薄いマゼンタ。凡例とセル数は `map.legend`。
- `map.summary`（タイル、バイオーム、地形の特徴、MapGeneratorDef、実行した GenStep 数、物の数）、`map.targetContent`（MOD 別の数、対象 MOD の物・地形と位置、対象 MOD の GenStep）、`map.checks`（`mapThings` の結果）、`map.observationFile`（全セルの層とパレット）。
- マップ生成中に出た error/warning は通常の診断として扱い、同じ種で生成したベースラインとの差分で判定します（例：対象 MOD の GenStep が例外を出すと `newErrors`）。

判定への追加：

- incomplete：`mapNotQualified`（このビルドでマップ生成を公式の quick test と比較して一致を確かめていない。現在はすべての環境がこれ）、`mapNotGenerated`（設定の誤りなどで生成できなかった。例：存在しないバイオーム）、`baselineMapIncomplete`（ベースラインのマップが生成できず、生成中の診断を比べられない）。
- failed：`mapGenerationFailed`（ベースラインは生成できたのに、対象では例外で生成が止まった）、`mapExpectationMismatch`。

## ZIP 入力

`mods[].path` に `.zip` を指定すると、Controller が `--out/inputs/` に展開して使います（`--keep-run-dirs` がなければ終了時に削除）。次の ZIP は `blocked`（`modInvalid`）です：絶対パス・ドライブ名・`..` を含む項目、シンボリックリンク、重複項目、10 万項目超、読めない ZIP、MOD が 1 個に定まらないもの。MOD の根は、ZIP の最上位に `About/About.xml` があればそこ、なければそれを持つ唯一の最上位フォルダです（`__MACOSX/` は無視）。展開後の合計は MOD 全体の 4 GiB 上限に含めます。

## 終了コード

`run`：0 passed、1 failed、2 blocked、3 incomplete。引数の誤りも argparse により 2 です。`prepare-game`：0 成功、2 blocked。

## 契約ケース（実装とテストの対応）

| ケース | 期待 | テスト |
|---|---|---|
| experimental 完走 | completed / incomplete | `EvaluationTests`、行列 `standard-runtime-ok` |
| B で期待パッチなし | incomplete（`noExpectedPatches`） | `EvaluationTests`、行列 `harmony-no-expectation` |
| 起動前の不足 | blocked | `RunTests.test_blocked_before_start`、行列 `harmony-not-provided` |
| qualified の不一致＋全体完了 | failed | `EvaluationTests`、行列 `expectation-mismatch` |
| 途中エラー＋timeout | incomplete、エラーも記録 | `EvaluationTests`、行列 `timeout` |
| 古い nonce | incomplete（`workerResultStale`） | `RunTests` |
| 対象なし | blocked（`invalidRequest`） | `RunTests`、`RequestTests` |
| B 未要求 | `stages.B=notRequested` | `EvaluationTests` |
| MOD 順序の変化 | incomplete（`modOrderMismatch`） | `RunTests` |
