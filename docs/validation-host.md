# 実ゲーム処理による MOD 検証の使い方（Linux・Windows）

`tools/validation_host.py` は、利用者が用意した RimWorld Linux 版のゲーム DLL を使い、MOD の実際の読み込み（A）と DLL・Harmony の登録（B）を検証して終了します。公式ゲーム実行ファイルは起動しません。ゲーム画面・メインメニュー・プレイ機能はありません。判定の意味は [契約](contracts/mod-validation-v1.md) を参照してください。

A/B とマップ生成の現在の対応：Linux x86_64、ゲーム同梱の WaylithClr、RimWorld 1.7.4985 rev1269。この組だけが `qualified` です。

Windows x64 でも `run` は動きます（W1。描画なし）。ただし Windows の実ゲームでの確認と公式との比較はまだなので、結果は常に `experimental`（全体は `incomplete`）です。Linux での合格を Windows の合格とは読み替えません。Windows では次の点が Linux と違います（[設計](superpowers/specs/2026-10-26-windows-host-design.md)）。

- スナップショットは、そのスナップショットと同じ OS 用のゲームでしか使えません。別 OS 用なら `platformMismatch` で `blocked`。
- 実行ディレクトリはシンボリックリンクではなく、ファイルのハードリンク（別ドライブなどで作れなければ複製）とフォルダのジャンクションで作ります。管理者権限や開発者モードは要りません。使った方式の数は `process.<run>.linkModes` に出ます。
- Worker は Job Object の中で動きます。メモリ上限はジョブ全体の確保量に対するハードな上限（`memoryHard=true`、`memoryMeasure=jobCommit`）で、上限を超える確保はその場で失敗します。時間切れ・Ctrl+C・子プロセスの残存はジョブごと止めます。上限で止まったときの `peakRssBytes` は、拒否された確保要求も数えるので上限より大きく出ることがあります。
- Worker に渡す環境変数は `PATH`・`SystemRoot`・`SystemDrive`・`windir` だけを引き継ぎ、`USERPROFILE`・`APPDATA`・`LOCALAPPDATA`・`TEMP`・`TMP` は実行ディレクトリの中を指します。

## 1. 準備（初回のみ）

必要なもの：Python 3.12+、.NET SDK 10（Worker のビルド用）、実行する OS 用の RimWorld のフォルダ。Windows でも下の同じコマンドで Worker をビルドします。`worker/bin` に `RimWorldValidationWorker.exe` ができていることを確かめてください（公開 CI でも確認しています）。

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

- `mods` は読み込み順。対象 MOD には `"target": true`。依存 MOD（Harmony など）も同じ一覧に入れます。`path` には MOD のフォルダか、配布された ZIP をそのまま指定できます。
- B を要求するときは期待する Harmony パッチを完全に指定します（上の対象メソッドは書式の例です。実際の MOD のパッチに合わせて書きます）。指定しないと `incomplete` です。
- 期待値を何も書かなくても、対象 MOD を入れたことで新しく出たエラー・警告は検出されます。
- 原因を確かめたうえで無害と判断した警告は、`allow` に正規表現と理由を書くと判定から外せます。外した警告も結果に理由付きで残ります。例（VEF の日本語）：

```json
"allow": {"translationErrors": [{
  "match": "^Couldn't inject (SchoolDesk\\.comps\\.CompStatEntrySchoolDesk\\.(reportText|statLabel)|Blackboard\\.comps\\.CompInspectStringBlackboard\\.inspectString) into Verse\\.ThingDef ",
  "reason": "VEF removes these comps on purpose (1.7/Patches/Biotech/LearningBonusPatches.xml)"
}]}
```

### マップを生成して確認する

建造物などをマップに置く MOD は、要求に `map` を足すとロード後に一時的なマップを 1 枚生成し、画像と内容の一覧を出します（遊べる状態にはしません）。

```json
"map": {"seed": "rwmt", "biome": "TemperateForest"},
"expectations": {"mapThings": [{"type": "ThingDef", "defName": "MyMod_Ruin", "minCount": 1}]}
```

`--out/map.png` が対象込みのマップ、`--out/map-baseline.png` が対象を外したマップです。対象 MOD の物はマゼンタで描かれます。ゲームの見た目ではなく、地形・岩・建物・植物・物・石の破片・ポーン・屋根を色分けした模式図です。詳しい項目と判定は [契約のマップ生成](contracts/mod-validation-v1.md#マップ生成) を参照してください。

マップ生成は Linux x64＋WaylithClr＋1.7.4985 rev1269 で公式の quick test と比べて適格化済みです（[マップ生成の適格化](research/map-qualification.md)）。このビルドでは**同じ種でも実行のたびに少し違うマップになります（公式も同じ）**。2 枚の画像は MOD と関係のない場所でも違って見えます。ランダムに置かれる物の正確な個数を `mapThings` の期待値にしないでください。

### クラフト材料の表示候補を調べる（C・実験）

`levels: ["A", "C"]`、`tests: ["bill-ingredient-options.v1"]` と `expectations.billIngredients` の `recipe` / `thing` / `visible` / `allowed` を指定します。[C の契約と要求例](contracts/mod-validation-v1.md#c製造指示の材料候補非描画experimental)を参照してください。

新規 Bill と、実ゲーム UI のカテゴリ・材料表示判定を使います。Linux では画面を描画しません。自作 fixture で特殊フィルターによる欠落を観測していますが、ケース固有の適格化は未完了です。現在は観測が揃っても全体 `incomplete` / `cNotQualified`。これは小麦粉 MOD や他の MOD の動作合格を意味しません。イベント/クエスト・Windows 描画は今後の別ケースです。

## 3. 実行

```bash
python3 tools/validation_host.py run --snapshot /private/rw-snapshot --request request.json --out /private/results/run-001 \
  --baseline-cache /private/results/baseline-cache
```

終了コード：0 passed、1 failed、2 blocked、3 incomplete。`--out` に `result.json` と、ベースライン・対象それぞれの `events.jsonl`、Worker の結果、ゲームのログが残ります。これらには私有パスが含まれるため、公開する場合は内容を確認してください。

| オプション | 用途 |
|---|---|
| `--baseline-cache DIR` | 同じ構成のベースラインを再利用して約半分の時間にする。マップを付けた実行では、ベースラインの `map-observation.json` の写しもここに置く（写しがなければキャッシュを使わない） |
| `--runtime standard` | 通常の .NET 10 で実行（実験。常に `incomplete`） |
| `--verify-full` | 実行前にスナップショット全体を再ハッシュ |
| `--keep-run-dirs` | 調査用に run ディレクトリを残す |
| `--allow-unknown-build` | Adapter のないビルドを実験扱いで実行 |

## 4. 結果の読み方

- `status` と `reasons`：何が理由でその判定になったか。
- `diagnostics.newInTarget`：対象 MOD を入れたときだけ出たエラー・警告（本文の先頭と全文）。
- `diagnostics.translationErrors.newInTarget`：対象で増えた個々の翻訳エラー（例：MOD が公式 Def の comp を消したため、公式翻訳の注入先がなくなった）。ゲームのログは「翻訳データに N 件のエラー」と件数しか出しませんが、判定はこの 1 件ずつの差で行います。
- `checks`：期待値ごとの実値と一致結果。Harmony は実際に登録されたパッチの一覧も含みます。
- `diagnostics.newInTarget[].knownNoise`：MOD と関係のないエンジンのメッセージとして、判定から外したもの（例：マップ生成後の終了時に出るネイティブメモリ解放漏れの警告）。理由付きで残ります。
- `scope.notChecked`：確認していない範囲（ほかの言語、マップ・tick・UI・描画・音声出力・Steam が必要な処理、パッチの実行時の効果、ほかの OS）。`map` を付けた場合は、生成したマップ以外（ほかの種・バイオーム、ゲーム開始後、tick）。
- `map`：マップ生成の結果（画像のパス、凡例、対象 MOD が置いた物と位置、`mapThings` の結果）。

`passed` は「要求した範囲で、対応環境の実物の処理で問題が見つからなかった」という意味です。プレイ中の挙動や Windows 固有の動作は保証しません。

## AI に任せる流れ（iPad から）

1. iPad から AI に MOD（または変更内容）と確認したいことを伝える。
2. AI がクラウドの Linux でスナップショットを用意し（ゲームファイルは Cloudflare R2 の `Game-Linux/`、MOD は `Workshop/<ID>/` から必要な分だけ取得。MOD はユーザーの索引で選ぶ）、要求ファイルを作って `run` する。
3. `failed` なら AI が MOD のソースや XML を直して再実行する。`blocked`/`incomplete` なら理由（入力不足など）を報告する。
4. AI が修正済み MOD と、使ったビルド・構成・検証範囲・未確認事項を報告する。遊ぶときは利用者が通常どおりゲームを起動する。

## 実物テスト（開発者向け）

```bash
python3 tests/integration/run_fixture_matrix.py --snapshot /private/rw-snapshot --harmony-dll /private/0Harmony.dll --out /private/matrix
```

自作 fixture の DLL をその場でビルドし、正常・故障のケース（マップ生成の 6 ケースを含む）を実行します。公開 CI では実行しません。

マップ生成を公式の開発者 quick test と比べる（開発専用。公式実行ファイルを `-headless -quicktest` で起動します）：

```bash
python3 experiments/official-comparison/compare_official.py --map --snapshot /private/rw-snapshot --harmony-dll /private/0Harmony.dll --out /private/compare-map
```

`mapprobe` fixture が公式側の種を製品の既定値に揃え、両方で生成直後のマップの設定と個数（物・カテゴリ・ThingDef・TerrainDef ごと）を記録します。生成が毎回違うため、各 `--repeat` 回（既定 5）動かして、設定とマップ生成終了までのエラーが全回で同一で、個数が公式のばらつきの範囲に入るかを比べます。`--reanalyze` で、残した実行から比較だけをやり直せます。基準は [マップ生成の適格化](research/map-qualification.md) を参照してください。
