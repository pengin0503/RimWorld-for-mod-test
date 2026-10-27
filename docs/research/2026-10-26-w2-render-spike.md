# W2 の試作：ゲームの描画で検証用の画面を出す

日付：2026-10-26。対象：RimWorld 1.7.4985 rev1269（Linux 版、WaylithClr）。ユーザーが W2 の方式として「ゲームの描画で作る」を選んだので、遊べる状態にせずに描画だけを起動できるかを、クラウドの Linux で試した。試作のコードは私有領域に置き、公開しない。逆コンパイルの本文も公開しない（API 名と順序だけを記す）。

## 結果

自前のホストから、本家の部品で描いた検証用の窓を表示できた。公式の起動経路のうち、メインメニュー（`Root_Entry`・`UIRoot_Entry`）・Steam・`Game` の生成は通らない。

画面写真は、ゲームの背景画像を含むので公開リポジトリには入れず、ユーザーとの非公開のやり取りでだけ渡した。

- 窓・見出し・チェックボックス・区切り線・区画・ボタンは、本家の `Verse.Window`・`Listing_Standard`・`Widgets` がそのまま描いた。背景は本家の `UI_BackgroundMain`。
- 日本語の翻訳（`Japanese (日本語).tar`）が読み込まれ、`LanguageDatabase.activeLanguage` は日本語。日本語の文字は、ゲームの代替フォントの探索（Linux では `NotoSansCJK-Regular.ttc`、Windows では `meiryo.ttc`・`YuGothM.ttc` など）で描かれた。クラウドでは `fonts-noto-cjk` を入れる必要があった（入れる前は豆腐になった）。
- 公式 5 コンテンツ（Core と 4 DLC）を読み込み、ThingDef は 3,145 件。
- 起動から画面写真まで約 56 秒（クラウドの CPU 描画 llvmpipe、Def の読み込みを含む）。実際の GPU ではもっと短いと見込むが、未測定。

## 動かし方（クラウドの Linux）

- `mesa-vulkan-drivers`（lavapipe）と `xvfb` を入れ、`VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json` で `xvfb-run` の中から起動する。GPU は `llvmpipe` として選ばれた。
- 比較のため、公式の実行ファイルも同じ条件で（使い捨ての配置、私有の HOME）起動し、本家の画面が描けることを先に確かめた。その画面は Steam がないという本家のダイアログだった。これは開発時の確認だけで、製品の流れでは公式の実行ファイルを起動しない。

## 試作の起動手順

`EngineApplication.Run` を `Headless=false` で呼び、初期化のコールバックで公式の `Bootstrap.Initialize` に沿って次を行った。

1. `UnityRuntime` を作り、`ConfigurePaths` に実行ディレクトリの中のパスを渡す（利用者の AppData を使わない）。シェーダーキャッシュ、`AssetPackBoot.Open`、シェーダー置き場の登録。
2. `Bootstrap` の非公開の手順をリフレクションで呼ぶ：`ConfigureTextureRuntime`、`ConfigureInput`、`ConfigureFrameRenderer`、`RegisterExecutionOrders`、`RegisterResources`。`RegisterResources` が使う `Bootstrap._unityRuntime` は先に設定する。
3. 毎フレームの処理は公式と同じ順（ウィンドウの大きさの同期、`EndOfFrame`、`FrameStart`、`BeginFrame`、ImGui の入力、`Update`、音声）。`Current.Game` ができたら止める。
4. 独自のシーンを登録する。カメラと、`Verse.Root` を継承した自前の Root を置く。
5. 自前の Root の `Start` は、`Root.Start` の代わりに次を行う：`Current` の Root とカメラを設定、英語カルチャ、`CopyUnityData`、`Prefs.Init`、ログの接続、`StaticConstructorOnStartupUtility.CallAll`、`LoadAllPlayData`（非同期）、最後に `SoundRoot` と自前の `UIRoot` を作る。Steam は初期化しない。
6. 自前の `UIRoot` は、基底の `UIRootOnGUI` の後に背景、並べ替えとドラッグの部品、`WindowStack`、`Widgets.WidgetsOnGUI` を描く（`UIRoot_Entry` からメインメニューと世界の描画を除いた順）。

## 分かった制約

- 窓や Root はゲームの型（`Verse.Window`・`Verse.Root`・`Verse.UIRoot`）を継承するので、ゲームの DLL を参照してコンパイルする必要がある。ゲームの DLL は公開できないので、**この画面は公開 CI ではビルドできない**。Worker（リフレクションだけで結び付け、CI でビルドできる）とは違う。
- 本家の MOD 管理画面（`Page_ModsConfig`）は、閉じるときに MOD の変更を保存してゲームを再起動する作りなので、そのままは使えない。同じ部品で自前の窓を作る。
- Steam を初期化しないので、Workshop の MOD は `ModLister` に自動では載らない。Workshop のフォルダを実行ディレクトリの `Mods` にリンクする必要がある。
