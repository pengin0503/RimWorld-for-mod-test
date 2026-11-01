# 有限tick D を使ったMODの挙動確認：実施記録と知見（2026-11-01）

対象：Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱 WaylithClr。ホストのコードは変更していない。
確認したMOD（いずれも利用者自作）は次の3つ（v1.0.1）。

- [Colony Task Auditor](https://github.com/pengin0503/rimworld-Colony-Task-Auditor)
- [Animal Management](https://github.com/pengin0503/rimworld-Animal-Management)
- [Smart Apparel Upgrade](https://github.com/pengin0503/rimworld-Smart-Apparel-Upgrade)

この記録は、既存の `bounded-tick.v1` に**私有の観測用MOD（プローブ）**を重ねて、任意MODの具体的な挙動を確かめた手順と、その過程で分かったことをまとめたもの。D の独立適格化や、任意MODの合格を意味しない。結果は各MODの `docs/VALIDATION.md` に記録している。

## 結論

- 有限tick D は、MODの「実ゲームでしか出ない不具合」を見つけるのに有効だった。静的照合とモデル単体テストを通過していた3MODで、実ゲーム実行から次の3件の不具合が見つかった。
  1. ブループリントの `Thing.Stuff` は null（素材は `stuffToUse` に入っている）。`CostListAdjusted(null)` がスキャンのたびにエラーログを出していた。
  2. `listerThings.AllThings` を件数上限付きで走査すると、生成マップでは植物（木・草）で上限に達してしまい、食料まで届かなかった。
  3. バニラの `HasHediffsNeedingTend` / `ShouldSeekMedicalRest` は、慢性疾患（喘息など）の治療待ちでも true になる。開始ポーンの持病を「負傷」と誤判定し、自動処理が止まっていた。
- 比較用の操作を同じ実行に入れると、仮説を実ゲームで直接確かめられる。例：同じ着替えをバニラのプレイヤー指示（`TryTakeOrderedJob`）で行わせて、`OutfitForcedHandler.IsForced` が true になることを観測した。
- 所要時間は、初回のゲーム準備が約225秒（SDK経路、取得906MB）、プローブ付きの2,400tick実行が1回約45秒（生成マップ・Crashlanded、ベースラインはキャッシュから再利用）だった。修正 → 再実行の往復を十数回行っても実用的だった。

## 手順

1. `codex_workflow.py prepare --private-root $HOME/.cache/rwmt-private` で私有スナップショットを作る。SDK経路（`RWMT_R2_TRANSPORT=sdk`）を使った。
2. Harmony が必要な対象は、索引で `brrainz.harmony` / 2009463077 を確認してから `fetch-mods --dependency Harmony` で取得する（取得は約2.5MB）。
3. Worker は checkout の外へビルドする（`dotnet build worker/RimWorldValidation.Worker -c Release -o <私有dir>`）。
4. プローブMODを私有領域で作り、スナップショットの `game` と対象MODのDLLを参照してビルドする。出力から参照DLLのコピーは削除する。
   - 中身は1つの `GameComponent` で、`GameComponentTick` の回数を数え、決めたtickで状況の用意・操作・観測を行う。
   - 観測結果は `Log.Warning("RWMT-PROBE ...")` として出し、対象実行の `events.jsonl` から読む。
5. 要求：`levels: ["A","D"]`、`tests: ["bounded-tick.v1"]`、`map: {seed}`、`tick: {count, observeAt: [0, count]}`、`fixture.counter` の期待値。
   - MODの並び：TickProbe → 確認するMOD群 → プローブ（`target: true`）。
   - 確認するMODは非target依存としてベースラインにも載せる。そうすると、それらのMOD自身の既存の警告は新規扱いにならない。
6. `validation_host.run_validation(snapshot, request, out, worker, baseline_cache=...)` を Python から呼ぶ。全体の判定は常に `incomplete`（`dNotQualified`）。D 段階の `completed` と、プローブの出力を確認する。
7. Harmony パッチの登録確認は D と同時に要求できない。別途 `levels: ["A","B"]` と `expectations.harmonyPatches` の完全指定で実行する（約15秒）。

## 分かったこと（ホストの挙動）

- **tick 中にゲームがエラーを1件でも出すと、その時点で D は止まる**（`game tick emitted an error`、`advanced` はそこまで）。対象MODの `Log.Error` で停止した位置が分かるので、不具合の特定にはむしろ役立った。プローブ側のAPI誤用（例：`ClosestThingReachable` に `ThingRequestGroup.Everything` を渡す）でも同様に止まるので、プローブの失敗とMODの失敗を区別して読む。
- 警告は止まらない。プローブの報告を警告で出すと、結果に `newWarnings` が付く（プローブ自身の出力なので問題ない）。
- 生成マップ（Crashlanded）の状態：
  - 入植者3人、ペット1匹。
  - 初期物資の食料（MealSurvivalPack）はすべて**禁止状態**。食料関連の確認では、禁止を含める設定にするか、プローブで禁止を解除する必要がある。
  - 開始ポーンは古傷（永続）や喘息などの慢性疾患を持つことがある。健康状態を条件にするMODの確認では、この点が実際に効いた。
  - 植物が多く、`AllThings` の件数は12,000を超える。
- tick中の状況の用意は、ゲームAPIで直接行えた。いずれもプローブ内の操作で、ホストの機能ではない。
  - 衣服の生成・着用（`ThingMaker`、`apparel.Wear`）と、品質の設定（`CompQuality.SetQuality`）
  - ブループリントの設置（`GenConstruct.PlaceBlueprintForBuild`）と採掘指示（`DesignationManager.AddDesignation`）
  - 徴兵（`drafter.Drafted`）と待機Jobの開始
- `TicksGame` を直接書き換えると D の tick差分検査に反する。時間の経過が必要な確認は、プローブから対象MODの処理（例：スキャン）を短い間隔で直接呼んで代用した。
- MODの非公開メソッドの呼び出しやゲーム状態の取得は、プローブ内の反射で行える。ただし、その結果をMODの動作保証とは言わない。

## 限界

- 1枚の生成マップ・短い実行で確かめられるのは、用意した場面だけ。長時間のプレイ、セーブ・ロード、描画（アラートやウィンドウの表示）、睡眠の自然な発生、多数MODの環境は未確認のまま。
- `fixture.counter` 以外の観測IDはホストに登録していない。そのため、プローブの結果はホストの判定に入らず、私有ログを人が読む形になる。必要になれば、汎用の観測IDを登録できる形（たとえばプローブが私有ファイルへ書いた数値を `tickObservations` として読む）を、別途設計するとよい。
- プローブ・私有ログ・結果は公開していない。各MODのリポジトリには、安全な要約だけを記録した。
