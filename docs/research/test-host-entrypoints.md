# 検証ホストの呼出し経路と終了点

対象ビルド：RimWorld 1.7.4985 rev1269（Linux 版。RimWorld.dll 1.7.4985.1269、Assembly-CSharp 1.7.9790.38077、共通 commit 535691cc、Waylith 1.0.0 commit 03494be0）。2026-10-25 に、ユーザー提供の Linux 版一式を私有領域で逆コンパイルして呼出し順を確認し、試作と製品 Worker で実行して裏付けた。逆コンパイル本文は公開しない。本書は API 名と順序だけを記す。

## 公式の起動経路（参照用）

1. `Program.Main` → `Waylith.EngineApplication.Run(options, Bootstrap.Initialize)`。
2. `EngineApplication` の構築：`-headless` ならウィンドウ・GPU を作らず、音声は `Initialize(noAudio)`。`RunHeadlessLoop` が `Quit` まで `OnUpdate` を回す。
3. `Bootstrap.Initialize`：`ConfigureRuntime`（`Environment.ProcessPath` からデータ・ユーザーデータのパスを決め、`Assets.zip` の有無を検査）、シェーダー置き場の登録、`OnUpdate` の設定、`RegisterResources`、`SpawnEntryScene`（`Root_Entry`）。
4. `Root.Start` → `CheckGlobalInit`：英語カルチャ固定、`UnityDataInitializer.CopyUnityData`、版の記録、`Prefs.Init`、Steam 初期化（`SteamManager.InitIfNeeded`）、ログ処理の接続、DevMode なら属性漏れの報告。その後 `StaticConstructorOnStartupUtility.CallAll` を同期の長いイベントとして、`PlayDataLoader.LoadAllPlayData` を非同期の長いイベントとして、さらに UI/音声ルートを作る `InitializingInterface` を積む。
5. `LoadAllPlayData` → `DoPlayLoad`：MOD 一覧と順序、XML パッチ、Def 生成、cross-reference 解決、翻訳。`ExecuteWhenFinished` で、背景（bios）、後半の翻訳注入、2 回目の `CallAll`、アトラス、GC、`Log.ResetMessageCount` がメインスレッドで続く。`DefDatabase.ErrorCheckAllDefs` は **DevMode のときだけ**走る。
6. `Root_Entry.Start`：メインメニュー。自動開始セーブがあれば読み込む。

注意点：

- `Prefs.resetModsConfigOnCrash`（既定 true）だと、ロード例外時に MOD 構成を Core だけに戻して再試行する。対象 MOD が黙って外れる。
- `ModsConfig` は `knownExpansions` にない拡張を自動で有効化する。`Data/` にある公式フォルダが探索される。
- データ・`Mods/` の位置は `UnityData.dataPath` の親、設定・セーブは `persistentDataPath`。
- `Verse.Log` は Brutal LogSystem のカテゴリ `Verse` を通り、10,000 件で記録を止める。
- Harmony は `GenTypes` 経由で `HarmonyLib.Harmony` を名前解決する（ゲーム自身は Harmony を同梱しない。MOD が持ち込む）。

## Worker の手順

製品の Worker（`worker/RimWorldValidation.Worker`）は公式実行ファイルを使わず、自前の apphost から同じエンジン API を呼ぶ。ゲーム型への参照はコンパイル時に持たず、`GameApi.Bind()` が全メンバーをリフレクションで事前に結び付ける。欠けていれば起動前に `adapterMismatch`（終了コード 4）。

| 段階 | 処理 | 公式との違い |
|---|---|---|
| 起動 | Controller が作った run ディレクトリ（実行ファイルの場所＝ゲームのルート）で、ゲームの runtimeconfig（WaylithClr 設定込み）と、ゲームの deps.json のルートを Worker に差し替えたものを使う | 公式 `RimWorld` 実行ファイル・`RimWorld.deps.json` は run ディレクトリに置かない |
| engineInit | `EngineApplication.Run`（Headless、`ShowCrashDialog=false`、MiniAudioBackend）。初期化コールバックで `UnityRuntime` を作り `ConfigurePaths` に run ディレクトリ内の明示パスを渡す。シェーダーキャッシュ、`AssetPackBoot.Open`（マニフェストが空なら失敗）、エンジンのエラー/警告ハンドラ、シェーダープリウォーム無効、シェーダー置き場登録 | `Bootstrap.ConfigureRuntime` は呼ばない（Windows では利用者の AppData を使うため）。`RegisterResources`・Entry シーンは作らない |
| globalInit | `CheckGlobalInit` と同じ順で英語カルチャ、`CopyUnityData`、版記録、`Prefs.Init`、ログ接続、属性漏れ報告。Prefs が要求通り（DevMode=true、resetModsConfigOnCrash=false、言語）か検証し、違えば失敗 | Steam を初期化しない |
| staticConstructorsEarly | `CallAll` を同期の長いイベントで実行 | 同じ |
| loadPlayData | `LoadAllPlayData(false)` を非同期の長いイベントで実行。例外ハンドラで捕捉 | 同じ |
| lateLoadActions | 公式と同じ `ExecuteWhenFinished` 群がメインスレッドで実行される。最後に積んだ目印のイベントで完了を確認 | `InitializingInterface` は積まない |
| checks | `PlayDataLoader.Loaded`、実有効 MOD と順序、Mod クラス、`activeLanguage`、期待値、Harmony 登録を読み取り、結果を一時ファイル→rename で書く | 読み取りのみ |
| 終了 | `EngineApplication.Quit` → `Environment.Exit` | 対話ループに入らない |

完了条件：目印のイベントが実行され、かつ `LongEventHandler.AnyEventNowOrWaiting` が偽。シーン変更の要求や `Current.Game` の生成を検出したら、遊べる状態へ進む前に失敗として止める。

有限性：Worker は毎フレームの締切確認に加え、締切＋2 秒でタイマースレッドから `interrupted` の結果を書いて終了する（メインスレッドがゲームコード内で長く止まる場合のため。行列の `timeout` ケースで確認）。Controller は別に、子孫を含むプロセスグループへの SIGKILL で時間・メモリ・ログ量の上限を強制する。

## 意図的な逸脱（結果の `deviations` に毎回記録）

- DevMode を true にする。公式の `ErrorCheckAllDefs` を走らせるため。通常のプレイヤー設定より厳しい。
- `resetModsConfigOnCrash=false`。対象が黙って外れる回復を起こさないため。
- シェーダープリウォーム無効（公式 headless と同じ）。

## 省略した公式工程（結果の `skippedOfficialSteps` に毎回記録）

Steam/Workshop 初期化、Entry シーン（メインメニュー・音楽・UIRoot・SoundRoot）、自動開始セーブ、`InitializingInterface`、`RegisterResources`/実行順の登録、起動完了後のテクスチャキャッシュ掃除。これらに依存する MOD の挙動は検証範囲外です。Steam を省くのは、Workshop の同じ packageId の別版が代わりに読み込まれることを防ぐためでもあります。

## 未確認

- Windows での同じ手順（`ConfigurePaths` 以外のパス、ネイティブ依存、apphost）。Controller の `run` は Windows では `blocked` を返す。
- C（指定動作）・D（マップ・tick）に必要な追加初期化。
