# 実ゲーム処理による MOD 検証の使い方（Linux）

`tools/validation_host.py` は、利用者が用意した RimWorld Linux 版のゲーム DLL を使い、MOD の実際の読み込み（A）と DLL・Harmony の登録（B）を検証して終了します。公式ゲーム実行ファイルは起動しません。ゲーム画面・メインメニュー・プレイ機能はありません。判定の意味は [契約](contracts/mod-validation-v1.md) を参照してください。

現在の対応：Linux x86_64、ゲーム同梱の WaylithClr、RimWorld 1.7.4985 rev1269。この組だけが `qualified` です。Windows での `run` は未対応で `blocked` を返します。

## 1. 準備（初回のみ）

必要なもの：Python 3.12+、.NET SDK 10（Worker のビルド用）、RimWorld Linux 版のフォルダ。

```bash
dotnet build worker/RimWorldValidation.Worker -c Release -o worker/bin
python3 tools/validation_host.py prepare-game --source /private/rimworld-linux --snapshot /private/rw-snapshot
```

`prepare-game` はゲームフォルダを私有のスナップショットへコピーし、全ファイルの SHA-256 を記録して読み取り専用にします（約 1 GB、ローカルディスク上で約 5 秒）。元のフォルダは変更しません。スナップショットとゲームファイルは公開リポジトリやチャットに置かないでください。

## 2. 要求ファイル

```json
{
  "recordType": "modValidationRequest",
  "schemaVersion": 1,
  "levels": ["A", "B"],
  "official": ["Core", "Biotech"],
  "mods": [
    {"path": "/private/mods/Harmony"},
    {"path": "/private/mods/MyMod", "target": true}
  ],
  "language": "Japanese",
  "expectations": {
    "defs": [{"type": "ThingDef", "defName": "MyMod_Widget", "exists": true}],
    "harmonyPatches": [{
      "owner": "my.mod.harmony.id", "targetAssembly": "Assembly-CSharp", "targetType": "RimWorld.Pawn_HealthTracker",
      "targetMethod": "PostApplyDamage", "targetParameters": ["Verse.DamageInfo", "System.Single"],
      "kind": "postfix", "patchType": "MyMod.Patches.PostApplyDamage_Patch", "patchMethod": "Postfix"
    }]
  }
}
```

- `mods` は読み込み順。対象 MOD には `"target": true`。依存 MOD（Harmony など）も同じ一覧に入れます。
- B を要求するときは期待する Harmony パッチを完全に指定します（上の対象メソッドは書式の例です。実際の MOD のパッチに合わせて書きます）。指定しないと `incomplete` です。
- 期待値を何も書かなくても、対象 MOD を入れたことで新しく出たエラー・警告は検出されます。

## 3. 実行

```bash
python3 tools/validation_host.py run --snapshot /private/rw-snapshot --request request.json --out /private/results/run-001 \
  --baseline-cache /private/results/baseline-cache
```

終了コード：0 passed、1 failed、2 blocked、3 incomplete。`--out` に `result.json` と、ベースライン・対象それぞれの `events.jsonl`、Worker の結果、ゲームのログが残ります。これらには私有パスが含まれるため、公開する場合は内容を確認してください。

| オプション | 用途 |
|---|---|
| `--baseline-cache DIR` | 同じ構成のベースラインを再利用して約半分の時間にする |
| `--runtime standard` | 通常の .NET 10 で実行（実験。常に `incomplete`） |
| `--verify-full` | 実行前にスナップショット全体を再ハッシュ |
| `--keep-run-dirs` | 調査用に run ディレクトリを残す |
| `--allow-unknown-build` | Adapter のないビルドを実験扱いで実行 |

## 4. 結果の読み方

- `status` と `reasons`：何が理由でその判定になったか。
- `diagnostics.newInTarget`：対象 MOD を入れたときだけ出たエラー・警告（本文の先頭と全文）。
- `diagnostics.translationErrors.newInTarget`：日本語などで「翻訳データに N 件のエラー」の警告が増えたとき、増えた個々のエラー（例：MOD が公式 Def の comp を消したため、公式翻訳の注入先がなくなった）。
- `checks`：期待値ごとの実値と一致結果。Harmony は実際に登録されたパッチの一覧も含みます。
- `scope.notChecked`：確認していない範囲（ほかの言語、マップ・tick・UI・描画・音声出力・Steam が必要な処理、パッチの実行時の効果、ほかの OS）。

`passed` は「要求した範囲で、対応環境の実物の処理で問題が見つからなかった」という意味です。プレイ中の挙動や Windows 固有の動作は保証しません。

## AI に任せる流れ（iPad から）

1. iPad から AI に MOD（または変更内容）と確認したいことを伝える。
2. AI がクラウドの Linux でスナップショットを用意し（ゲームファイルが必要。PC 上のフォルダを一度受け渡す）、要求ファイルを作って `run` する。
3. `failed` なら AI が MOD のソースや XML を直して再実行する。`blocked`/`incomplete` なら理由（入力不足など）を報告する。
4. AI が修正済み MOD と、使ったビルド・構成・検証範囲・未確認事項を報告する。遊ぶときは利用者が通常どおりゲームを起動する。

## 実物テスト（開発者向け）

```bash
python3 tests/integration/run_fixture_matrix.py --snapshot /private/rw-snapshot --harmony-dll /private/0Harmony.dll --out /private/matrix
```

自作 fixture の DLL をその場でビルドし、正常・故障の 16 ケースを実行します。公開 CI では実行しません。
