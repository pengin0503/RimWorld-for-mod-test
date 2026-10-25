# 検証ホストの依存と必要資材

確認日：2026-10-25。確認環境：Claude のクラウド Linux x86_64 コンテナ。入力：ユーザーが自分の PC（`D:\rimworld-linux`）から渡した RimWorld Linux 版一式。コンテナ上の作業コピーはセッション限りで、公開リポジトリには入れない。

## ビルド識別

| 項目 | 値 |
|---|---|
| Version.txt | `1.7.4985 rev1269` |
| RimWorld.dll / Assembly-CSharp.dll | 1.7.4985.1269 / 1.7.9790.38077（同じ commit 535691cc） |
| Waylith.dll | 1.0.0（commit 03494be0） |
| ランタイム | 同梱の WaylithClr `10.0.13-waylithclr.dev`（`runtimepack.Microsoft.NETCore.App.Runtime.linux-x64`、managed 171・native 15） |
| 構成 | ファイル 2,094 個、約 1.0 GB。Data は Core・Royalty・Ideology・Biotech・Odyssey（Anomaly なし） |
| 以前の Windows 版との関係 | Assembly-CSharp、RimWorld、Waylith、Waylith.UnityCompat、Waylith.AssetBake、UnityStubs はバイト単位で同一。BCL・ネイティブ・Steamworks・apphost が異なる |

Controller の Adapter 表（`tools/validation_host.py` の `ADAPTERS`）は、上記ゲーム DLL 5 個の SHA-256 でビルドを識別する。適格化（qualified）はさらに Linux x64・WaylithClr の `libcoreclr.so` と `System.Private.CoreLib.dll` の SHA-256 が一致する場合に限る。ハッシュはゲームの内容を含まない識別子なので公開してよいと判断した。

## 実行に必要なもの

| 工程 | 必要なもの | 確認方法 | 欠けた場合 |
|---|---|---|---|
| 準備（prepare-game） | `Version.txt`、ゲーム DLL 5 個、`RimWorld.runtimeconfig.json`、`RimWorld.deps.json`、`Assets.zip`、`libhostfxr.so`、`libcoreclr.so`、`System.Private.CoreLib.dll`、`Data/Core/About/About.xml` | 存在確認、全ファイル SHA-256 | `blocked`（`missingGameFiles`） |
| Worker 起動 | 上記に加え deps.json に載る managed/native 依存一式（66 パッケージ） | 自前 apphost が依存を解決して起動 | 起動失敗→結果なしで `incomplete` |
| engineInit | `Assets.zip`（マニフェスト 5,907 項目、エントリ 6,132）、`Rendering/Shaders`（GLSL 4 個） | `AssetPackBoot.Open` の結果を記録 | マニフェスト空で失敗。`-NoAssetPack` 相当の欠損無視はしない |
| A：実ローダー | 要求した公式 Data フォルダ、対象と依存 MOD、言語（Core の `Languages/*.tar` またはフォルダ） | 実ロード、言語の実適用（`activeLanguage`） | 不足は `blocked`、言語の未適用は `incomplete` |
| B：DLL・Harmony | 対象 MOD の DLL と、その MOD が依存する Harmony MOD（0Harmony.dll 同梱） | 読み込まれた Harmony の版・mvid、登録一覧 | Harmony を同梱する MOD がなければ `blocked`（`harmonyMissing`） |

ネイティブ依存は `ldd` で全て解決した（グラフィック・音声ライブラリを含む）。headless でも `libwaylithaudio.so` などはロードされる。Steam（`libsteam_api.so`）は存在するが Worker は初期化しない。

## 開発環境で追加に使ったもの

- .NET SDK 10（Worker と fixture DLL のビルド）。Worker の実行自体はゲーム同梱の WaylithClr を使う。
- Lib.Harmony 2.4.3（NuGet、MIT、net10.0 版 0Harmony.dll。nupkg SHA-256 `f07af11a…3e88`）。fixture 用の私有入力で、コミットしない。

## 標準 .NET と WaylithClr の違い

`--runtime standard` は .NET 10.0.13 の通常ランタイムで Worker を動かす実験用モード。ゲームの runtimeconfig から `WaylithClr.*` 設定を外し、ランタイムパックのファイルを run ディレクトリに置かない。WaylithClr が設定で行う Unity 名の振り替え（`UnityEngine*` 等→`UnityStubs`）だけは Worker が `AssemblyLoadContext.Resolving` で代行する。

確認した違い：

- WaylithClr の設定（緩い binding、アクセスチェック省略、Mono 互換の文字列ハッシュ・浮動小数書式、JIT のインライン抑制など 20 項目）は再現しない。
- 実害の例：`ProfilerBootStart` の静的コンストラクタが `TypeLoadException`（System.Runtime に `WaylithClr.MethodBodyUpdater` がない）で失敗する。
- 製品の Worker で確認した 2 ケース（`standard-runtime-ok`、`standard-runtime-bad-reference`）と、試作段階の 6 構成では、fixture の故障検出結果は WaylithClr と同じだった。上記の `ProfilerBootStart` エラーはベースラインにも出るため、差分判定では新しいエラーにならない。ただし差の影響範囲を証明していないため、標準 .NET の結果は常に `fidelity=experimental`、`status=incomplete` とする。

## 不足・未確認

- 実際の利用者 MOD の検証には、その MOD 一式と依存 MOD（多くは `brrainz.harmony`）が必要。まだ受け取っていない。
- このコンテナ上のゲームファイルはセッション限り。新しいセッションでは再びユーザーの PC から受け取る必要がある。プロジェクト共有領域に保管する場合も公開リポジトリには入れない。
- Windows 版での実行（apphost .exe、Windows ネイティブ、パス）は未確認。
