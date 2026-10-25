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
  "limits": {"timeoutSeconds": 180, "memoryMiB": 4096, "logMiB": 32, "diagnostics": 2000, "messageKiB": 16}
}
```

| 項目 | 規則 |
|---|---|
| 未知のフィールド | 全階層で拒否（`blocked` / `invalidRequest`） |
| `levels` | `A` 必須。`B`（DLL・Harmony）と `C`（指定動作）は A の完了が前提。`C` は v1 では未実装で `blocked` |
| `official` | 既定 `["Core"]`。先頭は Core。Royalty/Ideology/Biotech/Odyssey から選ぶ。Anomaly は対象外（スナップショットにないため `officialContentMissing`） |
| `mods` | 読み込み順。公式コンテンツの後に並ぶ。`path` は要求ファイルからの相対パス可。`packageId` は任意で、指定時は About.xml と一致必須。`target: true` を 1 個以上 |
| `target` | 検証対象。ベースライン（同じ構成から対象だけ外した実行）との差分で、対象が持ち込んだ診断を判定する |
| `language` | Core の言語フォルダ名またはアーカイブ名（例 `Japanese (日本語)`）。括弧の前の英語名が一意なら受け付け、実名へ解決して結果に記録する |
| `expectations.defs` | `type` は Def の型名（一意でなければ完全名）。`exists` は真偽 |
| `expectations.defValues` | `path` はメンバー名の `.` 連結、`[n]`、`[key=value]`（Def は defName で比較）。`equals` は文字列。数値は相対 1e-6 で比較 |
| `expectations.keyed` | 選択言語での Keyed 翻訳。`equals` を省くと存在だけを見る |
| `expectations.harmonyPatches` | `B` 必須。対象メソッドは assembly・型・名前・引数型（`Type.ToString()` 形式）・任意の generic arity で一意に指定。`kind` は prefix/postfix/transpiler/finalizer |
| `limits` | 既定値は上記。範囲外は拒否。`timeoutSeconds` は Worker 1 回あたり（ベースラインと対象で別々に適用） |

## 結果 `modValidationResult`

主な項目：

- `status`、`executionStatus`（`completed` / `failed` / `notStarted` / `interrupted`）、`fidelity`（`qualified` / `experimental`）、`reasons[]`（`code` と `detail`）。
- `stages.A/B/C`：`completed` / `failed` / `incomplete` / `blocked` / `notRequested`。
- `request`（sha256、正規化後の levels/official/language/limits）、`game`（版、fingerprint、adapter、照合方法）、`platform`、`runtime`（実際の CLR 記述と WaylithClr 設定）、`tool.workerSha256`。
- `mods[]`（packageId、元パス、ファイル数、内容 sha256、同梱 0Harmony.dll）、`modOrder`（要求と実際）、`runningMods`、`modClasses`、`activeLanguage`、`loadedAssemblies`（mvid）。
- `checks`：期待値ごとの実値と `match` / `mismatch` / `missing` / `error`。Harmony は登録一覧、期待外の登録、読み込まれた Harmony の版も含む。
- `diagnostics.newInTarget`：ベースラインにない error/warning（多重集合の差）。`mentionsTargets` は本文に対象の packageId/フォルダ名が出るものの目安で、責任の確定ではない。
- `workerStages`（engineInit → globalInit → staticConstructorsEarly → loadPlayData → lateLoadActions、各秒数と証拠）、`skippedOfficialSteps`、`deviations`、`scope`（確認した範囲と確認していない範囲）。
- `process`（終了コード、停止理由、最大 RSS、ログ量、上限の実施方式。メモリは監視ポーリングで `memoryHard=false`）、`timings`。

## 判定順序

1. **blocked**（`executionStatus=notStarted`）：要求不正、出力先が空でない、Linux x64 以外、未実装の C、Worker なし、スナップショット改変、公式コンテンツ・言語・MOD の不足、対応 Adapter のないビルド（`--allow-unknown-build` なし）、B で Harmony を同梱した MOD がない。
2. **incomplete**：Controller による停止（timeout/memoryLimit/logLimit）、Worker 結果の欠落・不正・古い nonce、Worker の未完了、ベースラインの未完了、`experimental`、診断の取りこぼし、Verse ログ上限、MOD 順序の不一致、言語が適用されない、期待値を評価できない、B で期待パッチ未指定。
3. **failed**：上記がなく、qualified な範囲で期待値の不一致、期待パッチの未登録、ロード例外、対象で新たに出た error/warning のいずれかを確認。
4. **passed**：上記のいずれもない。限定範囲の合格で、`scope.notChecked` は未検証。

incomplete でも、確認できた不一致や新しい診断は `reasons` と `diagnostics` に残します（例：`experimental` と `newErrors` の併記）。警告も初版では合格の障害です。既知の無害な警告を除外する規則は未実装です。

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
