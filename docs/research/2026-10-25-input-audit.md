# 受領資料・ゲームファイルの調査（2026-10-25）

この文書は主にメタデータ調査の記録です。その後に起動・読み込み処理の IL も確認しました。追加で確認した実行パスと判定への影響は [追加の調査記録](../../notes/2026-10-25-source-audit.md) にまとめています。以下の「引き継ぎ資料からの情報」の一部は、追加調査で静的に照合できましたが、Linux での実起動は引き続き未確認です。

## 結論

公式ヘッドレス起動＋検証用 MOD という合意済みの方向を変更する材料は見つからなかった。ただし、**この環境でゲームを起動できる Linux 一式は受領できていない**。今回の成果は静的調査と設計案であり、ゲームのビルド成功・起動成功・MOD 検証成功を意味しない。

## 調査対象と方法

- 引き継ぎ資料 `handoff-for-other-ai_md.md`、`linux-files-needed_md.md`、`headless-spike-report_md.md` を読んだ。
- 受領できた二つの ZIP のエントリー一覧、サイズ、CRC、SHA-256 を調べた。
- Windows 版 ZIP 内の runtimeconfig/deps、PE ヘッダー、CLI メタデータを静的に調べた。ゲームのメソッドは実行していない。
- 公開リポジトリの `main`（開始時点 `8dd9703255182f73654f10fd1157ef21eb5ecdf2`）、ブランチ一覧、PR 一覧を確認した。README のみで、`notes/spike-launcher/` などの既存実装はなかった。
- ZIP 本体、ゲームソース、ユーザー設定・セーブ・ログの内容はこのリポジトリに取り込んでいない。

識別用データは [input-inventory.json](input-inventory.json) に収録した。MVID は各モジュールの識別子であり、別モジュール間の一致を要求するものではない。

## 今回直接確認できたこと

| 入力 | 結果 | 作業への影響 |
|---|---|---|
| `Rim_Dll_All.zip` | メタデータ用の `__MACOSX/` とディレクトリを除き 284 ファイル、162,954,027 bytes。ZIP 全体の CRC 検査で不一致なし | Windows 版の静的な API 調査に使える |
| 同 ZIP の deps | runtime target は `.NETCoreApp,Version=v10.0/win-x64` | Linux 版として起動できるとは扱わない |
| 同 ZIP の runtimeconfig | TFM は `net10.0`、included framework は `10.0.13-waylithclr.dev`。`WaylithClr.*` 設定がある | 通常の .NET に置換した検証を正式判定に使わない |
| 同 ZIP のネイティブ部分 | `RimWorld.exe`、`coreclr.dll` は PE/AMD64。`.so` は 0 件 | Linux 実行ファイル・Linux ランタイムの追加が必要 |
| `RimWorld by Ludeon Studios.zip` | 同条件で 1,370 ファイル、154,220,584 bytes。ZIP 全体の CRC 検査で不一致なし。`Config/`、`Saves/`、`ShaderCache/`、`BundleCache/` を含む | ゲーム本体ではなくユーザーデータとして扱う。設定を検証環境へ流用しない |
| 利用可能な二つの ZIP | 公式 `Data/Core/`、`Rendering/Shaders/`、`Assets.zip` を確認できなかった | XML・アセットを使う起動検証は未実施 |
| `Rim_Data.zip` | 作業環境への転送失敗により未確認 | 含有ファイルも完全性も推測しない。再添付が必要 |
| この作業環境 | `dotnet`、`ilspycmd`、`mono` 系の実行・逆コンパイル用コマンドは利用できなかった | .NET ビルド、以前の試運転の再現は未実施 |

`ShaderCache/` のキャッシュが存在することは、インストール先の `Rendering/Shaders/` が揃っていることを意味しない。

### 起動・観測 API の存在確認

次の型・メソッド名は受領 DLL のメタデータで直接確認した。**存在確認であり、フックの安全性、引数・呼び出し順、Linux 版との同一性を検証したものではない。**

| アセンブリ | 型・メンバー | 用途の候補 |
|---|---|---|
| `RimWorld.dll` | `RimWorldWaylith.Program.Main` | 公式起動入口 |
| `Waylith.dll` | `Waylith.EngineApplication.RunHeadlessLoop`、`get_Headless`、`Quit`、`RequestShutdown` | ヘッドレス実行と終了 |
| `Assembly-CSharp.dll` | `Verse.PlayDataLoader.LoadAllPlayData`、`DoPlayLoad`、`get_Loaded` | 読み込み段階の観測 |
| 同上 | `Verse.LoadedModManager.LoadAllActiveMods`、`ApplyPatches`、`ErrorCheckPatches`、`ParseAndProcessXML` | XML・パッチ読み込みの観測 |
| 同上 | `Verse.LongEventHandler.ExecuteWhenFinished`、`Verse.StaticConstructorOnStartupUtility.CallAll` | 遅延処理と静的初期化の完了判定の候補 |
| 同上 | `Verse.LanguageDatabase.SelectLanguage`、`InitAllMetadata` | 言語処理の確認候補 |
| 同上 | `Verse.Log.Error`、`Warning`、`Notify_LogMessageReceived` | ゲーム側の診断観測候補 |
| `UnityStubs.dll` | `UnityEngine.Application.add_logMessageReceivedThreaded`、`Quit` | ログ通知・終了の候補 |

`RimWorld.dll` のユーザー文字列領域では `Headless`、`QuitAfterBoot`、`savedatafolder` も確認した。引き継ぎ資料のコマンドライン指定と整合するが、この環境ではその挙動を実行確認していない。

### DLL 一式の整合性について

ハッシュと MVID を記録したことで、次回との差分を識別できる。これは「混在していない」と証明するものではない。更新中に取得していない一式であることの申告、対応する deps/runtimeconfig、依存 DLL、Linux 上の実起動を合わせて確かめる必要がある。Windows 版と Linux 版のハッシュ一致も要求しない。

## 引き継ぎ資料からの情報（今回未再現）

- 標準 .NET 10 と使い捨てランチャーで、Core XML の解析開始まで進んだ。
- シェーダー不足で初期化が失敗した。
- 起動処理が `Environment.ProcessPath` を基準にインストール先を求める。
- Steam ネイティブライブラリ、音声バックエンドの不足が起動を妨げた。
- 無制限の反復エラーによってメモリ使用量が約 14 GB に達した。
- 公式 `-headless -QuitAfterBoot` の利用と Linux 版 WaylithClr の採用が合意済み。

これらは前任の試運転報告であり、今回の成功実績として数えない。試作ランチャーのソースも今回の添付・リポジトリにはないため、再利用可能とは扱わない。

## 次の確認の順序

1. [追加ファイル一覧](../linux-files-needed.md) に従って、同じ更新時点の Linux インストールを受領する。
2. 実行ファイル・ランタイム・Data・アセット・シェーダーの存在、形式、依存関係を起動前に確認する。
3. 個人設定を読ませない専用作業領域で、公式 MOD のみの `-headless -QuitAfterBoot` 起動を資源制限付きで試す。Anomaly は有効化しない。
4. 設計案の完了フック、ログ経路、ヘッドレス音声、翻訳検証経路を実際の Linux ビルドで確かめる。
5. 設計レビューを終え、実装計画を作る。仕様未確定の独自ホストや Steam 初期化の回避へ切り替えない。

一般の CI へゲームファイルを送信して、この不足を埋めることはしない。
