> **調査時点の記録。** DLL/データから確認した事実は調査資料として保持しますが、表の「設計への影響」や次の実行方針は [最新の独立ホスト設計](../docs/superpowers/specs/2026-10-25-test-only-host-design.md) が優先します。今回ゲームを実行した結果ではありません。

# 添付資料の確認結果（2026-10-25）

## 今回できたことと、できなかったこと

当初の ZIP 2 個に加え、追加の分割 Data ZIP 3 個も全エントリ読み出しで検査し、中央ディレクトリに記載された CRC との一致を確認しました。DLC アセット ZIP 4 個の CRC と、翻訳 TAR 77 個の読み出しも確認しました。詳しい Data の結果は [追加調査](../docs/research/2026-10-25-split-data-audit.md) にあります。ゲーム DLL の PE/CLI メタデータと、起動・読み込みに関係するメソッドの IL もローカルで調べました。ゲームのコードやユーザープロファイルは公開していません。

**ゲームは起動していません。Core/DLC の読み込み成功、MOD の動作、Harmony の適用成功を証明する結果はありません。** 前の試運転は [以前の報告](headless-spike-report.md) として保持し、今回の実測には含めません。

開始時のリポジトリは `8dd9703255182f73654f10fd1157ef21eb5ecdf2`、追跡ファイルは README のみでした。引き継ぎ資料にある `notes/spike-launcher/` のソースは、今回の添付・リポジトリのいずれにもありません。復元したものとして扱いません。

## 入力の分類

`__MACOSX/` の補助ファイルとディレクトリエントリを除いた数です。

| 入力 | 実際の内容 | 結果 |
|---|---|---|
| `Rim_Dll_All.zip` | Windows 版のインストール直下相当、284 ファイル。DLL 269 個、`.so` 0 個 | ZIP 整合性 OK。Linux の実行環境にはならない |
| `RimWorld by Ludeon Studios.zip` | ユーザープロファイル、1,370 ファイル。設定、セーブ、ログ、キャッシュなど | ZIP 整合性 OK。インストールフォルダではない |
| 同 ZIP 内の `ShaderCache/` | 1,144 ファイル。`.spv-cache` と `.layout-cache` | `Rendering/Shaders/*.glsl` の代用にはならない |
| `Rim_Data.zip` | 元の単一 ZIP は未受領。分割版で受け直した | 元との完全一致は未確認だが、元の再送は不要 |
| `Rim_data_1.zip` | Core、Ideology、Biotech、1,878 ファイル | CRC OK。Core アセットはない。`Core/Shaders/` に GLSL 225 個あり |
| `Rim_data_2.zip` | Royalty、185 ファイル | CRC OK。アセット ZIP あり |
| `Rim_data_3.zip` | Odyssey、270 ファイル | CRC OK。アセット ZIP あり |
| 引き継ぎ Markdown 3 個 | 方針、以前の試運転、Linux ファイル一覧 | 読み込み済み |

今回の環境には `dotnet`、ILSpy、Mono はありませんでした。静的調査には Python と `dnfile 0.18.0` / `dncil 1.0.2` / `pefile 2024.8.26` を一時領域で使用しました。これらは製品の依存関係ではありません。

ZIP 自体の SHA-256、展開後ファイルの識別情報は [JSON の調査記録](2026-10-25-source-audit.json) にあります。CRC 一致は読み出し時の破損検査であり、公式の署名や同一ビルドであることの証明ではありません。

## ビルドの識別

| ファイル | AssemblyVersion | InformationalVersion のコミット部分 | 対象 |
|---|---|---|---|
| `RimWorld.dll` | `1.7.4985.1269` | `535691cc7c6279fe45ab70da06a06f89e46297f6` | `.NETCoreApp,Version=v10.0` |
| `Assembly-CSharp.dll` | `1.7.9790.38077` | 同上 | 同上 |
| `UnityStubs.dll` | `1.0.0.0` | 同上 | 同上 |
| `Waylith.dll` | `1.0.0.0` | `03494be0f2ad22fac64915fa1bfda7a954985807` | 同上 |

**AssemblyVersion がファイル間で異なることだけで、ビルド混在とは判定しません。** ゲーム側 3 個のコミット部分は一致していますが、エンジンを含む一式の互換性は実行で確認する必要があります。Linux 版を受け取ったときも、今回の Windows DLL だけを上書きして混ぜず、Linux 版の一式を基準にします。

`RimWorld.deps.json` の runtime target は `.NETCoreApp,Version=v10.0/win-x64`、runtime pack は `10.0.13-waylithclr.dev` です。`RimWorld.exe` は PE32+ AMD64 でした。

`RimWorld.runtimeconfig.json` には `net10.0` と、`WaylithClr.AssemblyNameRedirects`、`LaxAssemblyBinding`、`JitPatchableAssemblies=Assembly-CSharp`、`MonoStringHashCode` などの独自設定があります。**これは設定の存在確認であり、Linux 版のネイティブランタイムを検証した結果ではありません。**

## 実物から確認した起動条件

以下のメソッド名と metadata token は、今回の DLL での照合用です。ベータ更新後には変わる可能性があります。IL 本体や逆コンパイルしたソースは含めていません。

| 確認事項 | 根拠となるメソッド | 設計への影響 |
|---|---|---|
| Headless の引数を読み、エンジンへ渡す | `RimWorldWaylith.Program.Main`、`RimWorld.dll:0x0600005b` | 公式の実行ファイルを使う |
| Headless 分岐で、Vulkan/ウィンドウを作る処理より前に戻る | `Waylith.EngineApplication` のコンストラクター | 描画用の独自スタブを作らない |
| Headless でも音声バックエンドを `Initialize(true)` で初期化する | 同上 | 無音出力でも Linux 音声ネイティブライブラリが不要とはいえない |
| ヘッドレスの更新ループがある | `Waylith.EngineApplication.RunHeadlessLoop`、`Waylith.dll:0x0600009f` | 描画ループと分けて確認できる |
| データの基準位置を `Environment.ProcessPath` から求める | `RimWorldWaylith.Bootstrap.ConfigureRuntime`、`RimWorld.dll:0x0600002d` | 外部の標準 `dotnet` でゲーム DLL を起動しない |
| GLSL の位置は `AppContext.BaseDirectory/Rendering/Shaders` | `RimWorldWaylith.Bootstrap.ResolveShaderSourceDirectory`、`RimWorld.dll:0x0600002c` | キャッシュだけを受け取っても起動条件は満たさない |
| `Assets.zip` または展開済みのリソース等を調べる処理がある | `RimWorldWaylith.Bootstrap.ConfigureRuntime` | 初回は完全な公式一式を使う。`-NoAssetPack` で欠損を隠した結果を合格にしない |
| Steam のライブラリが無い例外、または再起動要求で終了する。`SteamAPI.Init()` の失敗には警告で戻る経路がある | `Verse.Steam.SteamManager.InitIfNeeded`、`Assembly-CSharp.dll:0x06003b0a` | Steam を飛ばすパッチを本番に入れない。Steam 未起動で動くかは Linux 実行で確認する |

`-QuitAfterBoot` の 180 フレームという条件は引き継ぎ資料の報告です。今回のこの表ではフレーム数まで再確認した事実として扱っていません。実行時間の制限には、別プロセスの監視が必要です。

## 成功を誤判定しやすい点

### `-mod=` は厳密な選択リストではない

`Verse.ModsConfig.TryGetCommandLineModList`（`0x06001a0c`）は `-mod=...` と `-mod ...` を受け、コンマ・セミコロンで区切ります。

`ApplyCommandLineModList`（`0x06001a0d`）は、まず Core と、インストール済みでバージョン互換の公式 MOD を入れ、その後に指定された MOD を追加して `TrySortMods()` を呼びます。見つからない MOD は警告して先へ進む経路があります。

従って `-mod=probe` だけでは Core 単体になりません。設計案では検証専用コピーに必要な公式コンテンツだけを置き、独立した ModsConfig で選択し、**最終的に読み込まれた packageId と順序を期待値と照合**します。Anomaly は配置・有効化しません。

### 失敗後に Core 等へ戻して再起動する経路がある

`Verse.PlayDataLoader.LoadAllPlayData`（`0x0600093a`）には、`Prefs.ResetModsConfigOnCrash` が有効な場合、例外後に MOD 設定をリセットして読み直す処理があります。`Verse.PrefsData` の初期値ではこの設定は有効です。

設計案では検証用の独立した設定で無効にし、それでも実際のロード対象を照合します。終了コードが 0 でも、対象 MOD が消えた実行や完了レポートがない実行を合格にしません。

### 読み込み開始と、検査完了は別

`DoPlayLoad`（`0x0600093b`）には、XML の読み込み、クロス参照の解決、翻訳の前半注入に加え、`LongEventHandler.ExecuteWhenFinished` へ登録する後処理があります。後処理には翻訳の後半注入と `StaticConstructorOnStartupUtility.CallAll()` が含まれます。

そのため検証用 MOD のコンストラクターで直ちに「成功」と出すことはできません。`PlayDataLoader.Loaded`、遅延処理の状態、起動時 static constructor の完了を合わせて確認する設計にします。具体的な報告タイミングは Linux 実行での要検証事項です。

### DevMode と選択言語で検証範囲が変わる

`DoPlayLoad` の `ErrorCheckAllDefs` を呼ぶ分岐は `Prefs.DevMode` で条件付けされています。通常の起動だけでは、この検査が行われたとはいえません。

また `LanguageDatabase.InitAllMetadata()` は言語メタデータの初期化です。前半・後半の翻訳注入は `activeLanguage` を使います。「全言語の翻訳を検証済み」とは報告せず、言語を切り替えた別プロセスで検証します。

### `Verse.Log.Messages` だけでは過去のエラーが欠ける

`Verse.LogMessageQueue` の今回の初期上限は 1,000 件です。さらに、検証用 MOD が購読を始める前のログもあります。設計案では親プロセスが開始直後から標準出力・標準エラーとファイルログを回収します。MOD からの収集は補助で、重複や取りこぼしを無かったことにしません。

## 次の実行に必要なもの

[更新した受け入れ手順](linux-files-needed.md) に記載しています。今回不足しているのは主に以下です。

1. Linux 版の公式実行ファイル、WaylithClr、依存する `.so`、対応する managed DLL 一式。
2. 同じビルドの `Rendering/Shaders` と、存在する場合の `RimWorld_Data`。
3. 未受領の Core 用アセットパック。Core と対象 DLC の Data、DLC アセット 4 個は受領・静的検査済み。ただしインストール全体の完全性と Linux 一式とのビルド互換性は未確認。
4. B を実行する際の、1.7 に対応した Harmony MOD。今回の DLL ZIP に `0Harmony.dll` はない。

現在の実行準備は **blocked** です。これは MOD の失敗判定ではなく、検証前提が不足しているという結果です。
